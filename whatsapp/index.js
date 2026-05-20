'use strict';

/**
 * Advanced Multi-Account WhatsApp Number Validator
 * -------------------------------------------------
 * - Runs multiple Baileys sessions in parallel
 * - Splits numbers across accounts (max 2000 per account/day)
 * - Random delay 3-6s per check + 2min sleep every 50 checks
 * - Writes LIVE numbers to verified_active_numbers.txt
 */

const fs = require('fs-extra');
const path = require('path');
const readline = require('readline');
const pino = require('pino');
const qrcode = require('qrcode-terminal');
const {
  default: makeWASocket,
  useMultiFileAuthState,
  DisconnectReason,
  fetchLatestBaileysVersion,
  Browsers,
} = require('@whiskeysockets/baileys');

// ----------------------------- Config -----------------------------
const RUN_DIR = process.env.RUN_DIR
  ? path.resolve(process.env.RUN_DIR)
  : __dirname;
const SESSIONS_DIR = path.join(__dirname, 'sessions');
const NUMBERS_FILE = process.env.NUMBERS_FILE
  ? path.resolve(process.env.NUMBERS_FILE)
  : path.join(RUN_DIR, 'numbers.txt');
const WHITELIST_FILE = process.env.WHITELIST_FILE
  ? path.resolve(process.env.WHITELIST_FILE)
  : path.join(__dirname, 'whitelist.txt');
const OUTPUT_FILE = process.env.OUTPUT_FILE
  ? path.resolve(process.env.OUTPUT_FILE)
  : path.join(RUN_DIR, 'verified_active_numbers.txt');
const DETAILS_FILE = process.env.DETAILS_FILE
  ? path.resolve(process.env.DETAILS_FILE)
  : path.join(RUN_DIR, 'verified_details.csv');
const PROGRESS_FILE = process.env.PROGRESS_FILE
  ? path.resolve(process.env.PROGRESS_FILE)
  : path.join(RUN_DIR, 'progress.json');
const INVALID_FILE = process.env.INVALID_FILE
  ? path.resolve(process.env.INVALID_FILE)
  : path.join(RUN_DIR, 'not_registered_numbers.txt');
const ERROR_NUMBERS_FILE = process.env.ERROR_NUMBERS_FILE
  ? path.resolve(process.env.ERROR_NUMBERS_FILE)
  : path.join(RUN_DIR, 'check_error_numbers.txt');

/** e.g. 972 (IL) or 966 (SA): turns 05XXXXXXXX / 5XXXXXXXX into CC + national without trunk 0 */
const LOCAL_TRUNK_CC = (process.env.LOCAL_TRUNK_COUNTRY || '')
  .replace(/\D/g, '')
  .trim() || null;
/** When live, write WhatsApp canonical digits from onWhatsApp (shows 972… etc.). Set to 0 to keep query form. */
const CANONICAL_LIVE_OUTPUT = process.env.CANONICAL_LIVE_OUTPUT !== '0';

const MAX_ACCOUNTS_LIMIT = 20;          // Safety cap for prompt

// Presence probe settings
const FETCH_PRESENCE = process.env.FETCH_PRESENCE !== '0'; // default: on
const PRESENCE_WAIT_MS = parseInt(process.env.PRESENCE_WAIT_MS, 10) || 10000;
const DEBUG_PRESENCE = process.env.DEBUG_PRESENCE === '1';

// ------- Speed Profiles (anti-ban) -------
// Pick via env: SPEED=safe|normal|fast    (default: normal)
// Or override any field individually:
//   MIN_DELAY_MS, MAX_DELAY_MS, BATCH_SIZE, BATCH_SLEEP_MS, MAX_PER_ACCOUNT
const SPEED_PROFILES = {
  safe:   { MIN_DELAY_MS: 6000,  MAX_DELAY_MS: 10000, BATCH_SIZE: 30, BATCH_SLEEP_MS: 5 * 60 * 1000, MAX_PER_ACCOUNT: 1000 },
  normal: { MIN_DELAY_MS: 3000,  MAX_DELAY_MS: 6000,  BATCH_SIZE: 50, BATCH_SLEEP_MS: 2 * 60 * 1000, MAX_PER_ACCOUNT: 2000 },
  fast:   { MIN_DELAY_MS: 1500,  MAX_DELAY_MS: 3000,  BATCH_SIZE: 80, BATCH_SLEEP_MS: 1 * 60 * 1000, MAX_PER_ACCOUNT: 3000 },
};

const speedKey = (process.env.SPEED || 'normal').toLowerCase();
const profile = SPEED_PROFILES[speedKey] || SPEED_PROFILES.normal;

const toInt = (v, def) => {
  const n = parseInt(v, 10);
  return Number.isFinite(n) && n >= 0 ? n : def;
};

const MIN_DELAY_MS    = toInt(process.env.MIN_DELAY_MS,    profile.MIN_DELAY_MS);
const MAX_DELAY_MS    = Math.max(MIN_DELAY_MS, toInt(process.env.MAX_DELAY_MS, profile.MAX_DELAY_MS));
const BATCH_SIZE      = Math.max(1, toInt(process.env.BATCH_SIZE, profile.BATCH_SIZE));
const BATCH_SLEEP_MS  = toInt(process.env.BATCH_SLEEP_MS,  profile.BATCH_SLEEP_MS);
const MAX_PER_ACCOUNT = Math.max(1, toInt(process.env.MAX_PER_ACCOUNT, profile.MAX_PER_ACCOUNT));

const silentLogger = pino({ level: 'silent' });

// -------------------------- Shared State --------------------------
const foundMutex = { busy: false, queue: [] };
const activeSockets = new Set();
let shuttingDown = false;

// --------------------------- Utilities ----------------------------
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const randInt = (min, max) => Math.floor(Math.random() * (max - min + 1)) + min;

function log(label, msg) {
  const ts = new Date().toISOString().replace('T', ' ').slice(0, 19);
  console.log(`[${ts}] [${label}] ${msg}`);
}

function sanitizeNumber(raw) {
  if (!raw) return null;
  const digits = String(raw).replace(/[^\d]/g, '');
  if (digits.length < 6) return null;
  return digits;
}

/**
 * National mobile 05X + 8 digits (10) or 5X + 8 (9) → international without leading 0 after CC.
 * If digits already start with `cc`, returns as-is.
 */
function applyTrunkCountryCode(digits, cc) {
  if (!cc) return digits;
  const c = String(cc).replace(/\D/g, '');
  if (!c) return digits;
  if (digits.startsWith(c)) return digits;
  if (digits.length === 10 && /^05\d{8}$/.test(digits)) return c + digits.slice(1);
  if (digits.length === 9 && /^5\d{8}$/.test(digits)) return c + digits;
  return digits;
}

/**
 * One line from numbers.txt / whitelist.txt:
 * - `972:0531234567` or `972/0531234567` → force that country code for trunk strip
 * - otherwise optional global LOCAL_TRUNK_COUNTRY applies to 05… / 5… mobiles
 */
function parseNumberLine(line, defaultCc) {
  const t = String(line).trim();
  if (!t || t.startsWith('#')) return null;
  let cc = null;
  let rest = t;
  const m = t.match(/^(\d{2,4})[:/](.+)$/);
  if (m) {
    cc = m[1].replace(/\D/g, '');
    rest = String(m[2]).trim();
  }
  const fileDigits = sanitizeNumber(rest);
  if (!fileDigits) return null;
  const ccUse = cc || defaultCc || null;
  const queryDigits = applyTrunkCountryCode(fileDigits, ccUse);
  return { fileDigits, queryDigits };
}

async function readNumbers() {
  if (!(await fs.pathExists(NUMBERS_FILE))) {
    throw new Error(`numbers.txt not found at ${NUMBERS_FILE}`);
  }
  const raw = await fs.readFile(NUMBERS_FILE, 'utf8');
  const seen = new Set();
  const out = [];
  for (const line of raw.split(/\r?\n/)) {
    const parsed = parseNumberLine(line, LOCAL_TRUNK_CC);
    if (!parsed) continue;
    if (seen.has(parsed.queryDigits)) continue;
    seen.add(parsed.queryDigits);
    out.push(parsed);
  }
  return out;
}

async function readWhitelistSet() {
  const set = new Set();
  if (!(await fs.pathExists(WHITELIST_FILE))) return set;
  const raw = await fs.readFile(WHITELIST_FILE, 'utf8');
  for (const line of raw.split(/\r?\n/)) {
    const parsed = parseNumberLine(line, LOCAL_TRUNK_CC);
    if (!parsed) continue;
    set.add(parsed.fileDigits);
    set.add(parsed.queryDigits);
  }
  return set;
}

function isWhitelisted(whitelistSet, fileDigits, queryDigits) {
  if (!whitelistSet || whitelistSet.size === 0) return false;
  return whitelistSet.has(fileDigits) || whitelistSet.has(queryDigits);
}

async function withMutex(mutex, fn) {
  if (mutex.busy) {
    await new Promise((res) => mutex.queue.push(res));
  }
  mutex.busy = true;
  try {
    return await fn();
  } finally {
    mutex.busy = false;
    const next = mutex.queue.shift();
    if (next) next();
  }
}

async function appendLive(number) {
  await withMutex(foundMutex, () => fs.appendFile(OUTPUT_FILE, number + '\n'));
}

const invalidMutex = { busy: false, queue: [] };
async function appendInvalid(number) {
  await withMutex(invalidMutex, () => fs.appendFile(INVALID_FILE, number + '\n'));
}

const errorNumbersMutex = { busy: false, queue: [] };
async function appendErrorNumber(number) {
  await withMutex(errorNumbersMutex, () => fs.appendFile(ERROR_NUMBERS_FILE, number + '\n'));
}

const progressMutex = { busy: false, queue: [] };
const progressByAccount = new Map();
let progressTotalInput = 0;

async function flushProgressFile() {
  const results = [...progressByAccount.values()].sort((a, b) =>
    String(a.account).localeCompare(String(b.account))
  );
  const totals = results.reduce(
    (acc, row) => {
      acc.checked += row.checked;
      acc.live += row.live;
      acc.errors += row.errors;
      acc.invalid += row.invalid;
      return acc;
    },
    { checked: 0, live: 0, errors: 0, invalid: 0, total: progressTotalInput }
  );
  await fs.writeJson(
    PROGRESS_FILE,
    { timestamp: new Date().toISOString(), done: false, totals, results },
    { spaces: 2 }
  );
}

async function bumpProgress(accountName, delta) {
  await withMutex(progressMutex, async () => {
    const cur = progressByAccount.get(accountName) || {
      account: accountName,
      checked: 0,
      live: 0,
      errors: 0,
      invalid: 0,
    };
    cur.checked += delta.checked || 0;
    cur.live += delta.live || 0;
    cur.errors += delta.errors || 0;
    cur.invalid += delta.invalid || 0;
    progressByAccount.set(accountName, cur);
    await flushProgressFile();
  });
}

const detailsMutex = { busy: false, queue: [] };
function csvCell(v) {
  const s = String(v ?? '');
  return /[,"\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
}
async function appendDetails({
  number, sourceInput, name, presence, lastSeen, isBusiness, hasPicture, about,
  bizName, bizCategory, bizAddress, bizWebsite, bizEmail,
  account,
}) {
  await withMutex(detailsMutex, async () => {
    const exists = await fs.pathExists(DETAILS_FILE);
    if (!exists) {
      await fs.writeFile(
        DETAILS_FILE,
        'number,source_input,name,presence,last_seen,business,has_picture,about,biz_name,biz_category,biz_address,biz_website,biz_email,account,checked_at\n'
      );
    }
    const row = [
      number,
      sourceInput ?? '',
      name || '',
      presence || '',
      lastSeen || '',
      isBusiness ? 'yes' : 'no',
      hasPicture ? 'yes' : 'no',
      about || '',
      bizName || '',
      bizCategory || '',
      bizAddress || '',
      bizWebsite || '',
      bizEmail || '',
      account,
      new Date().toISOString(),
    ].map(csvCell).join(',');
    await fs.appendFile(DETAILS_FILE, row + '\n');
  });
}

function prompt(question) {
  const rl = readline.createInterface({ input: process.stdin, output: process.stdout });
  return new Promise((resolve) => {
    rl.question(question, (answer) => {
      rl.close();
      resolve(answer.trim());
    });
  });
}

async function listExistingSessions() {
  await fs.ensureDir(SESSIONS_DIR);
  const entries = await fs.readdir(SESSIONS_DIR, { withFileTypes: true });
  return entries
    .filter((e) => e.isDirectory())
    .map((e) => e.name)
    .sort();
}

async function resolveAccounts() {
  const existing = await listExistingSessions();

  if (existing.length > 0) {
    console.log(`\nFound ${existing.length} existing session(s): ${existing.join(', ')}`);
  } else {
    console.log('\nNo existing sessions found.');
  }

  const envCount = process.env.ACCOUNTS_COUNT ? parseInt(process.env.ACCOUNTS_COUNT, 10) : NaN;
  const envList = process.env.ACCOUNTS
    ? process.env.ACCOUNTS.split(',').map((s) => s.trim()).filter(Boolean)
    : null;

  if (process.env.NON_INTERACTIVE === '1') {
    if (envList && envList.length > 0) return envList;
    if (Number.isInteger(envCount) && envCount > 0) {
      const count = Math.max(1, Math.min(MAX_ACCOUNTS_LIMIT, envCount));
      const accounts = [];
      for (let i = 0; i < count; i++) {
        accounts.push(i < existing.length ? existing[i] : `acc_${i + 1}`);
      }
      return accounts;
    }
    if (existing.length > 0) return existing;
    throw new Error('NON_INTERACTIVE: set ACCOUNTS or ACCOUNTS_COUNT, or create session folders first.');
  }

  let count;
  if (envList && envList.length > 0) {
    return envList;
  }
  if (Number.isInteger(envCount) && envCount > 0) {
    count = envCount;
  } else {
    const suggestion = existing.length > 0 ? existing.length : 1;
    const answer = await prompt(
      `How many accounts would you like to run? [default: ${suggestion}, max: ${MAX_ACCOUNTS_LIMIT}]: `
    );
    const parsed = parseInt(answer, 10);
    count = Number.isInteger(parsed) && parsed > 0 ? parsed : suggestion;
  }

  count = Math.max(1, Math.min(MAX_ACCOUNTS_LIMIT, count));

  const accounts = [];
  for (let i = 0; i < count; i++) {
    if (i < existing.length) {
      accounts.push(existing[i]);
    } else {
      accounts.push(`acc_${i + 1}`);
    }
  }
  return accounts;
}

function splitNumbers(all, accountCount) {
  // Even split, capped at MAX_PER_ACCOUNT per account.
  const usable = all.slice(0, accountCount * MAX_PER_ACCOUNT);
  const chunks = Array.from({ length: accountCount }, () => []);
  const base = Math.floor(usable.length / accountCount);
  const extra = usable.length % accountCount;

  let cursor = 0;
  for (let i = 0; i < accountCount; i++) {
    const size = Math.min(MAX_PER_ACCOUNT, base + (i < extra ? 1 : 0));
    chunks[i] = usable.slice(cursor, cursor + size);
    cursor += size;
  }
  return chunks;
}

// ------------------------ Baileys Connection ----------------------
async function openSocketOnce(accountName, label, opts = {}) {
  const sessionPath = path.join(SESSIONS_DIR, accountName);
  await fs.ensureDir(sessionPath);

  const { state, saveCreds } = await useMultiFileAuthState(sessionPath);
  const { version } = await fetchLatestBaileysVersion();

  const sock = makeWASocket({
    version,
    logger: silentLogger,
    printQRInTerminal: false,
    auth: state,
    browser: Browsers.macOS('Desktop'),
    syncFullHistory: false,
    markOnlineOnConnect: false,
  });

  sock.ev.on('creds.update', saveCreds);

  return new Promise((resolve, reject) => {
    let settled = false;
    sock.ev.on('connection.update', (update) => {
      const { connection, lastDisconnect, qr } = update;

      if (qr) {
        if (typeof opts.onQr === 'function') {
          Promise.resolve(opts.onQr(qr)).catch((e) => {
            log(label, `onQr handler error: ${e?.message || e}`);
          });
        } else {
          console.log(`\n================ QR for ${label} (${accountName}) ================`);
          console.log('Scan this QR with WhatsApp > Linked Devices:');
          qrcode.generate(qr, { small: true });
          console.log(`================================================================\n`);
        }
      }

      if (connection === 'open') {
        if (!settled) {
          settled = true;
          log(label, 'Connected to WhatsApp.');
          resolve({ sock, outcome: 'open' });
        }
      } else if (connection === 'close') {
        const code = lastDisconnect?.error?.output?.statusCode;
        if (!settled) {
          settled = true;
          resolve({ sock: null, outcome: 'close', code });
        }
      }
    });
  });
}

function attachPresenceCapture(sock) {
  const presenceMap = new Map();
  const nameMap = new Map(); // jid (or lid) -> pushName / notify / verifiedName

  const storeName = (jid, name) => {
    if (!jid || !name) return;
    const clean = String(name).trim();
    if (!clean) return;
    // Avoid storing a JID as a name by mistake
    if (/@s\.whatsapp\.net$|@lid$|@c\.us$/.test(clean)) return;
    nameMap.set(jid, clean);
  };

  sock.ev.on('presence.update', (ev) => {
    if (DEBUG_PRESENCE) console.log('[DEBUG presence.update]', JSON.stringify(ev, null, 2));
    if (!ev) return;
    const inner = ev.presences || {};
    for (const [jid, entry] of Object.entries(inner)) {
      presenceMap.set(jid, {
        lastKnownPresence: entry?.lastKnownPresence,
        lastSeen: entry?.lastSeen,
        receivedAt: Date.now(),
      });
      // Some Baileys versions include `notify` or `pushName` here too.
      if (entry?.notify) storeName(jid, entry.notify);
      if (entry?.pushName) storeName(jid, entry.pushName);
    }
    if (ev.id) {
      const fallback = inner[ev.id] || Object.values(inner)[0];
      if (fallback) {
        presenceMap.set(ev.id, {
          lastKnownPresence: fallback.lastKnownPresence,
          lastSeen: fallback.lastSeen,
          receivedAt: Date.now(),
        });
      }
    }
  });

  const handleContacts = (arr) => {
    if (DEBUG_PRESENCE) console.log('[DEBUG contacts]', JSON.stringify(arr));
    if (!Array.isArray(arr)) return;
    for (const c of arr) {
      storeName(c?.id, c?.name || c?.notify || c?.verifiedName || c?.pushName);
    }
  };
  sock.ev.on('contacts.upsert', handleContacts);
  sock.ev.on('contacts.update', handleContacts);

  // Messages can carry pushName for their sender (only trust when not fromMe).
  const handleMsg = (msg) => {
    if (!msg || msg.key?.fromMe) return; // pushName on fromMe=true is OUR name
    const pushName = msg.pushName;
    if (!pushName) return;
    const remote = msg.key?.remoteJid;
    const senderPn = msg.key?.senderPn;
    if (remote) storeName(remote, pushName);
    if (senderPn) storeName(senderPn, pushName);
  };

  sock.ev.on('messages.upsert', (m) => {
    if (!m || !Array.isArray(m.messages)) return;
    for (const msg of m.messages) handleMsg(msg);
  });

  sock.ev.on('chats.update', (chats) => {
    if (DEBUG_PRESENCE) console.log('[DEBUG chats.update]', JSON.stringify(chats));
    if (!Array.isArray(chats)) return;
    for (const chat of chats) {
      if (!Array.isArray(chat?.messages)) continue;
      for (const wrap of chat.messages) {
        handleMsg(wrap?.message);
      }
    }
  });

  if (DEBUG_PRESENCE) {
    try {
      if (sock.ws && !sock.ws.__rawHooked) {
        sock.ws.__rawHooked = true;
        sock.ws.on('CB:presence', (node) => {
          console.log('[DEBUG raw CB:presence]', JSON.stringify(node));
        });
        sock.ws.on('CB:chatstate', (node) => {
          console.log('[DEBUG raw CB:chatstate]', JSON.stringify(node));
        });
      }
    } catch (_) {}
  }

  sock.__presenceMap = presenceMap;
  sock.__nameMap = nameMap;
}

async function connectAccount(accountName, label) {
  // Handle pairing restart (code 515) and transient close-before-open.
  const MAX_RETRIES = 5;
  for (let attempt = 1; attempt <= MAX_RETRIES; attempt++) {
    const result = await openSocketOnce(accountName, label);

    if (result.outcome === 'open') {
      activeSockets.add(result.sock);
      attachPresenceCapture(result.sock);
      return result.sock;
    }

    const { code } = result;

    if (code === DisconnectReason.loggedOut) {
      throw new Error(
        `Session ${accountName} logged out. Delete sessions/${accountName} and re-scan.`
      );
    }

    // 515 = restart required (expected right after QR pairing). Reconnect silently.
    if (code === 515 || code === DisconnectReason.restartRequired) {
      log(label, 'Pairing complete, restarting connection...');
      await sleep(1000);
      continue;
    }

    // Other transient closes: back off and retry a few times.
    log(label, `Connection closed before open (code=${code}). Retry ${attempt}/${MAX_RETRIES}...`);
    await sleep(3000 * attempt);
  }
  throw new Error(`Could not establish connection for ${accountName} after ${MAX_RETRIES} attempts.`);
}

// --------------------- Per-account Validation ---------------------
function formatLastSeen(secOrMs) {
  if (!secOrMs) return '';
  // Baileys usually returns seconds; normalize.
  const ms = secOrMs > 1e12 ? secOrMs : secOrMs * 1000;
  const d = new Date(ms);
  if (isNaN(d.getTime())) return '';
  return d.toISOString().replace('T', ' ').slice(0, 19);
}

async function fetchPresence(sock, jid, waitMs, lid) {
  // Snapshot existing map keys BEFORE subscribing.
  const presenceMap = sock.__presenceMap;
  const keysBefore = new Set(presenceMap ? presenceMap.keys() : []);
  const subscribeTime = Date.now();

  // Choose the subscribe targets (phone JID and LID).
  const subscribeTargets = [jid];
  if (lid && lid !== jid) subscribeTargets.push(lid);

  // Mimic what WhatsApp Web does when you open a chat:
  //   1) mark self online
  //   2) subscribe to peer's presence
  //   3) tell peer "we're viewing the chat" (per-target available)
  const openChatCycle = async () => {
    try { await sock.sendPresenceUpdate('available'); } catch (_) {}
    for (const target of subscribeTargets) {
      try { await sock.presenceSubscribe(target); } catch (_) {}
    }
    await sleep(200);
    for (const target of subscribeTargets) {
      try { await sock.sendPresenceUpdate('available', target); } catch (_) {}
    }
  };

  await openChatCycle();

  const findFreshEntry = () => {
    if (!presenceMap) return null;
    // 1) direct hit on the phone JID or LID
    for (const k of [jid, lid].filter(Boolean)) {
      const v = presenceMap.get(k);
      if (v && v.receivedAt >= subscribeTime) return v;
    }
    // 2) any NEW entry since subscribe
    let best = null;
    for (const [k, v] of presenceMap.entries()) {
      if (!keysBefore.has(k) && v.receivedAt >= subscribeTime) {
        if (!best || v.receivedAt > best.receivedAt) best = v;
      }
    }
    return best;
  };

  // Wait, re-subscribing every 8s to nudge WhatsApp to push an update.
  // Exit early only when we have a LAST_SEEN timestamp or presence=unavailable
  // (presence alone like 'available'/'composing' counts too, but we keep waiting
  // briefly in case lastSeen is coming right after).
  const start = Date.now();
  let lastResub = Date.now();
  let firstHitAt = 0;
  while (Date.now() - start < waitMs) {
    const e = findFreshEntry();
    if (e) {
      // We got something.
      if (e.lastSeen) break; // definitive - stop immediately
      if (!firstHitAt) firstHitAt = Date.now();
      // Keep waiting a short moment in case lastSeen comes next (~3s).
      if (Date.now() - firstHitAt > 3000) break;
    }
    // Re-trigger every 8s if nothing arrived yet.
    if (!e && Date.now() - lastResub > 8000) {
      lastResub = Date.now();
      await openChatCycle();
    }
    await sleep(250);
  }
  const entry = findFreshEntry();

  // Extras: profile picture + about (status) + business profile.
  let about = '';
  let hasPicture = false;
  let isBusinessExtra = false;
  try {
    const st = await sock.fetchStatus(jid);
    if (DEBUG_PRESENCE) console.log('[DEBUG fetchStatus]', JSON.stringify(st, null, 2));
    // Response shapes across Baileys versions:
    //   { status: 'text', setAt }
    //   [{ status: { status: 'text', setAt }, id }]
    //   { status: { status: 'text', setAt } }
    // We ONLY trust the inner `status.status` or top-level `status` string,
    // never any other field (to avoid accidentally picking up `id`/JID).
    const extract = (obj) => {
      if (!obj) return '';
      if (typeof obj === 'string') return obj;
      if (Array.isArray(obj)) return extract(obj[0]);
      if (typeof obj === 'object') {
        if (typeof obj.status === 'string') return obj.status;
        if (obj.status && typeof obj.status === 'object' && typeof obj.status.status === 'string') {
          return obj.status.status;
        }
      }
      return '';
    };
    about = extract(st).trim();
  } catch (_) {}
  try {
    const url = await sock.profilePictureUrl(jid, 'image');
    hasPicture = !!url;
  } catch (_) {}
  let bizInfo = null;
  try {
    if (typeof sock.getBusinessProfile === 'function') {
      const biz = await sock.getBusinessProfile(jid);
      if (DEBUG_PRESENCE) console.log('[DEBUG businessProfile]', JSON.stringify(biz, null, 2));
      if (biz && (biz.description || biz.email || biz.website || biz.category || biz.address)) {
        isBusinessExtra = true;
        bizInfo = {
          description: biz.description || '',
          category: biz.category || '',
          address: biz.address || '',
          email: biz.email || '',
          website: Array.isArray(biz.website) ? biz.website.join(' | ') : (biz.website || ''),
        };
      }
    }
  } catch (_) {}

  // Try multiple JID variants to find a stored display name.
  let name = '';
  const nameCandidates = [jid];
  if (presenceMap) {
    for (const k of presenceMap.keys()) {
      if (!keysBefore.has(k)) nameCandidates.push(k);
    }
  }
  for (const k of nameCandidates) {
    const n = sock.__nameMap?.get(k);
    if (n) { name = n; break; }
  }

  return {
    presence: entry?.lastKnownPresence || 'unknown',
    lastSeen: formatLastSeen(entry?.lastSeen),
    about,
    hasPicture,
    isBusinessExtra,
    bizInfo,
    name,
  };
}

async function checkNumber(sock, number) {
  const jid = number.includes('@') ? number : `${number}@s.whatsapp.net`;
  const res = await sock.onWhatsApp(jid);
  if (DEBUG_PRESENCE) console.log('[DEBUG onWhatsApp]', JSON.stringify(res, null, 2));
  if (!Array.isArray(res) || res.length === 0 || !res[0]?.exists) {
    return { live: false };
  }

  const entry = res[0];
  const canonicalDigits = entry.jid && typeof entry.jid === 'string'
    ? entry.jid.split('@')[0]
    : '';
  const lid = entry.lid || null; // Linked ID, used by newer WhatsApp accounts
  // Business detection: try multiple field names used across Baileys versions.
  const isBusiness =
    !!entry.isBusiness ||
    !!entry.verifiedName ||
    !!entry.businessProfile ||
    (typeof entry.type === 'string' && entry.type.toLowerCase().includes('business'));

  // Also look up display name from our ongoing name cache (may be populated
  // by earlier events even before we call fetchPresence).
  let pushName = sock.__nameMap?.get(entry.jid) || sock.__nameMap?.get(entry.lid) || '';

  const result = {
    live: true,
    jid: entry.jid,
    canonicalDigits,
    isBusiness,
    name: pushName,
    presence: 'not-fetched',
    lastSeen: '',
    about: '',
    hasPicture: false,
    bizName: '',
    bizCategory: '',
    bizAddress: '',
    bizWebsite: '',
    bizEmail: '',
  };

  if (FETCH_PRESENCE) {
    const p = await fetchPresence(sock, result.jid, PRESENCE_WAIT_MS, lid);
    result.presence = p.presence;
    result.lastSeen = p.lastSeen;
    result.about = p.about;
    result.hasPicture = p.hasPicture;
    if (p.isBusinessExtra) result.isBusiness = true;
    if (p.name && !result.name) result.name = p.name;
    if (p.bizInfo) {
      result.bizName = p.bizInfo.description;
      result.bizCategory = p.bizInfo.category;
      result.bizAddress = p.bizInfo.address;
      result.bizWebsite = p.bizInfo.website;
      result.bizEmail = p.bizInfo.email;
      // If no pushName, fall back to business name for display
      if (!result.name && p.bizInfo.description) result.name = p.bizInfo.description;
    }
  }
  return result;
}

async function runAccount({ accountName, label, numbers, whitelistSet }) {
  let sock;
  try {
    sock = await connectAccount(accountName, label);
  } catch (err) {
    log(label, `Failed to connect: ${err.message}`);
    return { account: accountName, checked: 0, live: 0, errors: 1 };
  }

  let checked = 0;
  let liveCount = 0;
  let errors = 0;

  log(label, `Assigned ${numbers.length} numbers.`);

  for (let i = 0; i < numbers.length; i++) {
    if (shuttingDown) {
      log(label, 'Shutdown requested, stopping worker.');
      break;
    }

    const { fileDigits, queryDigits } = numbers[i];
    const q = queryDigits;
    const short = q.length > 6 ? q.slice(0, 3) + 'xxx' + q.slice(-2) : q;

    try {
      let info;
      if (isWhitelisted(whitelistSet, fileDigits, queryDigits)) {
        info = {
          live: true,
          name: '',
          presence: 'whitelist',
          lastSeen: '',
          isBusiness: false,
          hasPicture: false,
          about: '',
          bizName: '',
          bizCategory: '',
          bizAddress: '',
          bizWebsite: '',
          bizEmail: '',
          canonicalDigits: queryDigits,
        };
      } else {
        info = await checkNumber(sock, q);
      }
      checked++;
      if (info.live) {
        liveCount++;
        const outNumber =
          CANONICAL_LIVE_OUTPUT && info.canonicalDigits
            ? info.canonicalDigits
            : q;
        await appendLive(outNumber);
        await bumpProgress(accountName, { checked: 1, live: 1 });
        await appendDetails({
          number: outNumber,
          sourceInput: fileDigits,
          name: info.name,
          presence: info.presence,
          lastSeen: info.lastSeen,
          isBusiness: info.isBusiness,
          hasPicture: info.hasPicture,
          about: info.about,
          bizName: info.bizName,
          bizCategory: info.bizCategory,
          bizAddress: info.bizAddress,
          bizWebsite: info.bizWebsite,
          bizEmail: info.bizEmail,
          account: accountName,
        });
        const nm = info.name ? ` | name="${info.name.slice(0, 30)}"` : '';
        const ls = info.lastSeen ? ` | lastSeen=${info.lastSeen}` : '';
        const biz = info.isBusiness
          ? ` | biz="${info.bizName ? info.bizName.slice(0, 30) : 'yes'}"`
          : '';
        const pic = info.hasPicture ? ' | pic=yes' : '';
        const ab = info.about && info.about.trim() ? ` | about="${info.about.slice(0, 40)}"` : '';
        log(label, `Checking ${short}: LIVE${nm} | presence=${info.presence}${ls}${biz}${pic}${ab}`);
      } else {
        await appendInvalid(fileDigits || q);
        await bumpProgress(accountName, { checked: 1, invalid: 1 });
        log(label, `Checking ${short}: not registered`);
      }
    } catch (err) {
      errors++;
      await appendErrorNumber(fileDigits || q);
      await bumpProgress(accountName, { errors: 1 });
      const msg = err?.message || String(err);
      log(label, `Error checking ${short}: ${msg}`);

      // Handle rate-limit / connection close gracefully: back off and continue.
      if (/rate|limit|overlimit|429/i.test(msg)) {
        log(label, 'Rate limit suspected, sleeping 60s...');
        await sleep(60 * 1000);
      } else if (/Connection Closed|connection closed|Stream Errored|Timed Out/i.test(msg)) {
        log(label, 'Connection issue, attempting reconnect in 15s...');
        await sleep(15 * 1000);
        try {
          try { sock.end?.(new Error('reconnect')); } catch (_) {}
          sock = await connectAccount(accountName, label);
        } catch (reErr) {
          log(label, `Reconnect failed: ${reErr.message}. Halting this account.`);
          break;
        }
      }
    }

    // Batch sleep every BATCH_SIZE checks
    if (checked > 0 && checked % BATCH_SIZE === 0 && i < numbers.length - 1) {
      log(label, `Batch of ${BATCH_SIZE} done. Sleeping ${BATCH_SLEEP_MS / 1000}s...`);
      await sleep(BATCH_SLEEP_MS);
    } else if (i < numbers.length - 1) {
      const delay = randInt(MIN_DELAY_MS, MAX_DELAY_MS);
      await sleep(delay);
    }
  }

  try { sock?.end?.(undefined); } catch (_) {}
  activeSockets.delete(sock);

  log(label, `Done. Checked=${checked}, Live=${liveCount}, Errors=${errors}`);
  return { account: accountName, checked, live: liveCount, errors };
}

// ------------------------- Graceful Exit --------------------------
async function gracefulShutdown(reason) {
  if (shuttingDown) return;
  shuttingDown = true;
  log('SYSTEM', `Shutdown signal received: ${reason}. Closing sockets...`);
  for (const sock of activeSockets) {
    try { sock.end?.(undefined); } catch (_) {}
  }
  // Give workers a moment to flush
  await sleep(1500);
  log('SYSTEM', 'Exit complete.');
  process.exit(0);
}

process.on('SIGINT', () => gracefulShutdown('SIGINT'));
process.on('SIGTERM', () => gracefulShutdown('SIGTERM'));
process.on('uncaughtException', (e) => log('SYSTEM', `uncaughtException: ${e?.message || e}`));
process.on('unhandledRejection', (e) => log('SYSTEM', `unhandledRejection: ${e?.message || e}`));

// ------------------------------ Main ------------------------------
async function start() {
  log('SYSTEM', 'Starting Multi-Account WhatsApp Number Validator...');
  log('SYSTEM', `Speed profile: ${speedKey.toUpperCase()} | delay=${MIN_DELAY_MS}-${MAX_DELAY_MS}ms | batch=${BATCH_SIZE} → ${BATCH_SLEEP_MS / 1000}s sleep | cap=${MAX_PER_ACCOUNT}/account`);
  log('SYSTEM', `Presence probe: ${FETCH_PRESENCE ? `ON (wait ${PRESENCE_WAIT_MS}ms/live)` : 'OFF'}`);

  await fs.ensureDir(SESSIONS_DIR);
  await fs.ensureFile(OUTPUT_FILE);
  await fs.ensureFile(INVALID_FILE);
  await fs.ensureFile(ERROR_NUMBERS_FILE);

  const numbers = await readNumbers();
  progressTotalInput = numbers.length;
  log('SYSTEM', `Loaded ${numbers.length} unique numbers from numbers.txt`);
  if (LOCAL_TRUNK_CC) {
    log('SYSTEM', `LOCAL_TRUNK_COUNTRY=${LOCAL_TRUNK_CC} (05XXXXXXXX → ${LOCAL_TRUNK_CC}5XXXXXXXX)`);
  }
  const whitelistSet = await readWhitelistSet();
  if (whitelistSet.size > 0) {
    log('SYSTEM', `Whitelist loaded: ${whitelistSet.size} key(s) from ${WHITELIST_FILE}`);
  }

  const accounts = await resolveAccounts();
  if (accounts.length === 0) {
    throw new Error('No accounts configured.');
  }

  log('SYSTEM', `Configured accounts (${accounts.length}): ${accounts.join(', ')}`);

  const chunks = splitNumbers(numbers, accounts.length);
  const totalAssigned = chunks.reduce((s, c) => s + c.length, 0);
  log('SYSTEM', `Assigning ${totalAssigned} numbers across ${accounts.length} account(s) (cap ${MAX_PER_ACCOUNT}/account).`);

  chunks.forEach((chunk, i) => {
    log('SYSTEM', `  ${accounts[i]} -> ${chunk.length} numbers`);
  });

  // Launch all workers in parallel
  const workers = accounts.map((accountName, idx) =>
    runAccount({
      accountName,
      label: `Account ${idx + 1}`,
      numbers: chunks[idx] || [],
      whitelistSet,
    })
  );

  const results = await Promise.all(workers);

  // Summary
  log('SYSTEM', '================ SUMMARY ================');
  let totalChecked = 0;
  let totalLive = 0;
  for (const r of results) {
    log('SYSTEM', `${r.account}: checked=${r.checked}, live=${r.live}, errors=${r.errors}`);
    totalChecked += r.checked;
    totalLive += r.live;
  }
  log('SYSTEM', `TOTAL checked=${totalChecked}, live=${totalLive}`);
  log('SYSTEM', `Live numbers written to ${OUTPUT_FILE}`);

  // Final progress snapshot (per-account rows + rolled-up totals)
  await withMutex(progressMutex, async () => {
    for (const r of results) {
      progressByAccount.set(r.account, {
        account: r.account,
        checked: r.checked,
        live: r.live,
        errors: r.errors,
        invalid: Math.max(0, r.checked - r.live - r.errors),
      });
    }
    await fs.writeJson(
      PROGRESS_FILE,
      {
        timestamp: new Date().toISOString(),
        done: true,
        totals: results.reduce(
          (acc, row) => {
            acc.checked += row.checked;
            acc.live += row.live;
            acc.errors += row.errors;
            acc.invalid += row.invalid;
            return acc;
          },
          { checked: 0, live: 0, errors: 0, invalid: 0, total: progressTotalInput }
        ),
        results,
      },
      { spaces: 2 }
    );
  });

  process.exit(0);
}

// ------------------------ Django / web pairing ----------------------
async function writePairingStatus(accountName, payload) {
  const sessionPath = path.join(SESSIONS_DIR, accountName);
  await fs.ensureDir(sessionPath);
  await fs.writeJson(
    path.join(sessionPath, 'pairing.json'),
    { ...payload, updated_at: new Date().toISOString() },
    { spaces: 2 }
  );
}

async function runPairOnly(accountName) {
  const safeName = String(accountName).replace(/[^a-zA-Z0-9_-]/g, '') || 'acc_1';
  let QRCodeLib;
  try {
    QRCodeLib = require('qrcode');
  } catch (_) {
    throw new Error('Install qrcode package: npm install qrcode');
  }

  await writePairingStatus(safeName, { status: 'connecting', message: 'Starting pairing…' });

  const MAX_RETRIES = 8;
  for (let attempt = 1; attempt <= MAX_RETRIES; attempt++) {
    const result = await openSocketOnce(safeName, 'Pair', {
      onQr: async (qr) => {
        const qr_data_url = await QRCodeLib.toDataURL(qr, { margin: 1, width: 280 });
        await writePairingStatus(safeName, {
          status: 'qr',
          message: 'Scan with WhatsApp → Linked Devices → Link a device',
          qr_data_url,
        });
      },
    });

    if (result.outcome === 'open') {
      await writePairingStatus(safeName, {
        status: 'connected',
        message: 'Account linked successfully.',
      });
      try { result.sock?.end?.(undefined); } catch (_) {}
      log('PAIR', `Account ${safeName} paired.`);
      return;
    }

    const { code } = result;
    if (code === DisconnectReason.loggedOut) {
      await writePairingStatus(safeName, {
        status: 'error',
        message: 'Session logged out. Delete the session folder and try again.',
      });
      throw new Error(`Session ${safeName} logged out.`);
    }
    if (code === 515 || code === DisconnectReason.restartRequired) {
      await writePairingStatus(safeName, { status: 'connecting', message: 'Pairing complete, reconnecting…' });
      await sleep(1000);
      continue;
    }
    await writePairingStatus(safeName, {
      status: 'connecting',
      message: `Reconnecting (attempt ${attempt}/${MAX_RETRIES})…`,
    });
    await sleep(3000 * attempt);
  }

  await writePairingStatus(safeName, {
    status: 'error',
    message: 'Could not complete pairing. Try again.',
  });
  throw new Error(`Pairing failed for ${safeName}`);
}

// ------------------------ Connection status probe ----------------------
async function writeConnectionStatus(accountName, payload) {
  const sessionPath = path.join(SESSIONS_DIR, accountName);
  await fs.ensureDir(sessionPath);
  await fs.writeJson(
    path.join(sessionPath, 'connection_status.json'),
    { ...payload, updated_at: new Date().toISOString() },
    { spaces: 2 }
  );
}

async function probeAccountConnection(accountName) {
  const safeName = String(accountName).replace(/[^a-zA-Z0-9_-]/g, '');
  if (!safeName) return 'unknown';

  const sessionPath = path.join(SESSIONS_DIR, safeName);
  const credsPath = path.join(sessionPath, 'creds.json');

  if (!(await fs.pathExists(credsPath))) {
    await writeConnectionStatus(safeName, { status: 'offline', message: 'Not linked' });
    return 'offline';
  }

  let pairing = {};
  const pairingPath = path.join(sessionPath, 'pairing.json');
  if (await fs.pathExists(pairingPath)) {
    try {
      pairing = await fs.readJson(pairingPath);
    } catch (_) {}
  }
  if (pairing.status === 'qr' || pairing.status === 'connecting') {
    await writeConnectionStatus(safeName, {
      status: 'pairing',
      message: pairing.message || 'Pairing in progress',
    });
    return 'pairing';
  }

  const TIMEOUT_MS = parseInt(process.env.STATUS_TIMEOUT_MS, 10) || 12000;
  let sock = null;
  try {
    const result = await Promise.race([
      openSocketOnce(safeName, 'Status'),
      sleep(TIMEOUT_MS).then(() => ({ outcome: 'timeout', sock: null, code: null })),
    ]);

    if (result.outcome === 'open') {
      sock = result.sock;
      await writeConnectionStatus(safeName, {
        status: 'online',
        message: 'Connected to WhatsApp.',
      });
      return 'online';
    }
    if (result.outcome === 'timeout') {
      await writeConnectionStatus(safeName, {
        status: 'offline',
        message: 'Connection timed out.',
      });
      return 'offline';
    }

    const { code } = result;
    if (code === DisconnectReason.loggedOut) {
      await writeConnectionStatus(safeName, {
        status: 'offline',
        message: 'Session logged out. Re-pair this account.',
      });
      return 'offline';
    }
    await writeConnectionStatus(safeName, {
      status: 'offline',
      message: `Connection closed (code=${code ?? 'unknown'}).`,
    });
    return 'offline';
  } catch (err) {
    await writeConnectionStatus(safeName, {
      status: 'offline',
      message: err?.message || String(err),
    });
    return 'offline';
  } finally {
    try {
      sock?.end?.(undefined);
    } catch (_) {}
  }
}

async function runStatusProbe() {
  const raw = process.env.STATUS_ACCOUNTS || '';
  const names = raw.split(',').map((s) => s.trim()).filter(Boolean);
  if (names.length === 0) {
    log('STATUS', 'No accounts to probe (STATUS_ACCOUNTS empty).');
    return;
  }
  log('STATUS', `Probing ${names.length} account(s): ${names.join(', ')}`);
  for (const name of names) {
    const status = await probeAccountConnection(name);
    log('STATUS', `${name}: ${status}`);
  }
}

if (process.env.STATUS_PROBE === '1') {
  runStatusProbe()
    .then(() => process.exit(0))
    .catch((err) => {
      log('STATUS', `Fatal: ${err?.message || err}`);
      process.exit(1);
    });
} else if (process.env.PAIR_ONLY === '1') {
  const pairAccount = (process.env.PAIR_ACCOUNT || 'acc_1').trim();
  runPairOnly(pairAccount)
    .then(() => process.exit(0))
    .catch(async (err) => {
      log('PAIR', `Fatal: ${err?.message || err}`);
      process.exit(1);
    });
} else {
  start().catch(async (err) => {
    log('SYSTEM', `Fatal error: ${err?.message || err}`);
    await gracefulShutdown('fatal');
  });
}
