# Multi-Account WhatsApp Number Validator

Advanced WhatsApp number validator built with [@whiskeysockets/baileys](https://github.com/WhiskeySockets/Baileys) that runs multiple accounts in parallel, splits numbers evenly, and uses anti-ban delays.

## Features

- **Multi-session**: each account stored in `sessions/<account_name>/`
- **Auto QR login** per account on first run
- **Smart load balancing**: splits `numbers.txt` across all accounts, capped at **2000/account/day**
- **Parallel execution** with `Promise.all`
- **Anti-ban**: random 3–6s delay per check, 2-minute batch sleep every 50 checks
- **Error resilient**: rate-limit / connection-close handling per account (doesn't crash others)
- **Consolidated output**: live numbers saved to `verified_active_numbers.txt`
- **Graceful shutdown** on SIGINT/SIGTERM

## Install

```bash
npm install
```

## Configure

1. Put one phone number per line in `numbers.txt` (E.164 digits, e.g. `966501234567`, no `+`).
2. When you run the script, it will ask you **how many accounts** you want to open.

## Run

```bash
npm start
```

The script will prompt:

```
How many accounts would you like to run? [default: 1, max: 20]:
```

- If existing sessions already exist in `sessions/`, the default suggestion equals their count, and they'll be reused (no re-scan needed).
- New accounts beyond the existing ones are named `acc_N` automatically and will show a QR to scan.

You can skip the prompt by setting either:

```bash
# Just a count (auto-names: acc_1, acc_2, ...)
ACCOUNTS_COUNT=5 npm start

# Or explicit folder names
ACCOUNTS="main,backup,tester" npm start
```

On first run, each account prints a QR code labeled with its name. Scan it in WhatsApp → **Linked Devices** → **Link a Device**. Sessions persist in `sessions/<account_name>/` and will reconnect silently next time.

## Speed Profiles (anti-ban)

Pick via `SPEED` env var:

| Profile  | Delay/check | Batch pause           | Daily cap  | Use when                   |
|----------|-------------|-----------------------|------------|----------------------------|
| `safe`   | 6–10s       | 5 min every 30 checks | 1000/acc   | Warm-up or fresh accounts  |
| `normal` | 3–6s        | 2 min every 50 checks | 2000/acc   | Default                    |
| `fast`   | 1.5–3s      | 1 min every 80 checks | 3000/acc   | Aged/trusted accounts only |

```bash
SPEED=safe npm start
SPEED=fast ACCOUNTS_COUNT=3 npm start
```

### Fine-tuning (override any field)

```bash
# Exactly one check every 5 seconds (no randomness):
MIN_DELAY_MS=5000 MAX_DELAY_MS=5000 npm start

# Custom: 4-7 sec delay, pause 3 min every 40 checks
MIN_DELAY_MS=4000 MAX_DELAY_MS=7000 BATCH_SIZE=40 BATCH_SLEEP_MS=180000 npm start
```

## Output

- `verified_active_numbers.txt` — plain list of LIVE numbers
- `verified_details.csv` — enriched data: `number, presence, last_seen, business, account, checked_at`
- `progress.json` — summary snapshot after the run

### Presence / Last Seen

For each LIVE number the script also subscribes to presence for a few seconds and captures:

- **presence**: `available` (online), `unavailable` (offline), `composing` (typing), `recording`, `paused`, or `unknown`
- **last_seen**: only available when the target has **Last Seen = Everyone** in their privacy settings (usually empty for strangers)
- **business**: whether the account is a WhatsApp Business account

Disable presence probing (faster runs):

```bash
FETCH_PRESENCE=0 npm start
```

Tune the probe wait time per number (default 4000ms):

```bash
PRESENCE_WAIT_MS=2500 npm start
```

## Example

With 10,000 numbers and 5 accounts, each account processes 2,000 numbers in parallel. Expected runtime per account ≈ `2000 × ~4.5s + 40 × 120s ≈ 2.8 hours`.

## Notes

- Keep accounts warm (use them normally) to reduce ban risk.
- Daily cap is enforced at 2,000/account — extra numbers beyond `accounts × 2000` are ignored for this run.
- To force a new login for an account, delete its folder in `sessions/`.
