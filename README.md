# AntiBot

A **Django** app for visitor monitoring and blocking rules (IP, subnets, ISP, browser, OS, hostname), with allowed/denied visit logs, a web dashboard, and a small HTTP API you can call from your sites or gateways.

---

## What is it for?

| Use case | Description |
|----------|-------------|
| **Bot and unwanted traffic** | Evaluate each check using IP, User-Agent, and rules stored in the database. |
| **Allowed countries** | `AllowedCountry` entries feed into allow/deny decisions. |
| **Logs and analysis** | Pages for allowed/denied traffic, IP details, and adding block rules from logs. |
| **Dashboard** | Stats, user management, profile settings, and optional Telegram backups. |
| **Utilities** | File uploads, Google Safe Browsing checks, redirect inspection, and Cloudflare WAF sync. |
| **Cloudflare edge** | Push global blocked subnets and per-user allowed countries to zone WAF custom rules (superuser **Sync All**). |

**Main integration point for external apps:** `POST /tracker/api/log/` — send header **`X-API-Key`** with the **per-user key** shown on **Dashboard → Profile settings** (each user gets a key when their account is created). JSON body: `ip`, `useragent`. Responses: allow (`201`) or deny (`403`) with a readable reason. Missing or wrong key returns `403` with `{"error": "..."}`.

---

## Requirements

- **Python 3.9+** (aligned with Django in `requirements.txt`)
- **Database:** SQLite when no postgres env is set (typical local dev). PostgreSQL when **`DATABASE_URL`**, **`POSTGRES_*`**, or legacy **`DB_*`** is set — see **`.env.example`**. Requires **`psycopg2-binary`** from `requirements.txt`. Production (`DJANGO_ENV=production`) requires PostgreSQL. Optional **`docker-compose.yml`** for local Postgres. Manual systemd steps: **`deploy/README.md`**.

---

## Server install (recommended) — `install.sh`

**Single deploy directory (default `/opt/antibot`).** There is **one installer file**: **`install.sh`**. It `git clone`s into that path, then runs **`install.sh --inner`** from the cloned copy (same script). The **curl URL** points to that same file — **username, password, and login URLs** are printed at the end of **`install.sh`**. You do **not** need a second copy like **`~/antibot`** for production — use **`curl | sudo bash`** or run **`install.sh`** from **`/tmp`** or your home.

| Path | Role |
|------|------|
| **`/opt/antibot`** (or **`ANTIBOT_INSTALL_DIR`**) | **Only** on-disk app + venv + `.env` — this is what **install** fills and **uninstall** removes. |
| **`~/antibot`** (or any clone) | Optional: dev / copy of the repo; **not** used by the server app unless you change **`ANTIBOT_INSTALL_DIR`**. |

**Public internet:** Do **not** leave port **8000** open to the world. **`install.sh` does not configure Nginx or TLS.** For production, use **Nginx** (or similar) — see **[Production: reverse proxy, static files, and HTTPS](#production-reverse-proxy-static-files-and-https)** below.

### Quick install on a fresh server (no local clone required)

```bash
curl -fsSL https://raw.githubusercontent.com/nobodycp/antibot/main/install.sh | sudo bash
```

(Uses the repository’s default branch from GitHub.)

### Or: run `install.sh` from a clone (not from inside `/opt/antibot`)

```bash
cd ~
git clone https://github.com/nobodycp/antibot.git antibot-bootstrap
sudo bash antibot-bootstrap/install.sh
# optional: rm -rf antibot-bootstrap
```

**Do not** `cd /opt/antibot` and run **`install.sh`** from there — the bootstrap **removes** **`/opt/antibot`** first; the script will refuse if your current directory is inside the install path.

**Overrides (optional):**

- **`ANTIBOT_INSTALL_DIR`** — deploy root (default **`/opt/antibot`**). **uninstall.sh** must use the **same** value.
- **`ANTIBOT_REPO_URL`** — git URL to clone (forks, private mirrors).

```bash
sudo ANTIBOT_INSTALL_DIR=/srv/antibot ANTIBOT_REPO_URL=https://github.com/you/antibot.git bash install.sh
```

**What runs after the clone (still `install.sh`, invoked as `install.sh --inner`)**

1. Installs **python3**, **venv**, **git**, **curl**, **openssl**, **postgresql**, **postgresql-contrib**, **redis-server**; enables **`redis-server`**.
2. Creates **`env/`** venv and **`pip install -r requirements.txt`** (includes **Gunicorn**).
3. PostgreSQL role/database **`antibot`**; writes **`${INSTALL_DIR}/.env`** (**`DJANGO_SECRET_KEY`**, **`DB_*`**, **`REDIS_URL`**, **`ALLOWED_HOSTS`** auto-detect unless **`ANTIBOT_ALLOWED_HOSTS`** / **`ANTIBOT_EXTRA_ALLOWED_HOSTS`**).
4. **`migrate`**, **`createsuperuser --noinput`** (password: **`ANTIBOT_SUPERUSER_PASSWORD`** or generated → **`/root/antibot_superuser_credentials.txt`**).
5. **`collectstatic`**, **systemd** **Gunicorn** on **`0.0.0.0:8000`**, **cron** for **`run_telegram_backup`**.
6. Prints **LOGIN CREDENTIALS** once at the end (username, password, **Login/Dashboard URLs use an IPv4 address**, not the server hostname).

After install, the app listens on **`http://<server>:8000`**. For the public internet, put **Nginx** in front — see the production section below.

**Rerun behavior:** If the superuser **already exists** in PostgreSQL, **`createsuperuser --noinput`** fails and is ignored — the **existing password is not changed**. To rotate the superuser password, use Django’s admin or `changepassword`. The installer still regenerates **`/opt/antibot/.env`** (and rotates the **database user** password to match); it does **not** rotate the Django superuser unless you supply **`ANTIBOT_SUPERUSER_PASSWORD`** on a run where the user does not yet exist, or you manage passwords outside the script.

**Data safety (existing SQLite on the server):** This installer does **not** migrate or import old SQLite data into PostgreSQL. Take a **backup** from the current environment first, deploy the new version, let **`migrate`** create the PostgreSQL schema, then **restore or import data manually** if you need historical rows. Until then, the app uses the new empty PostgreSQL database.

**Rerunning `install.sh` (summary):** Does not drop the PostgreSQL database. Resets **`/opt/antibot`**, regenerates **`.env`** (new **`DJANGO_SECRET_KEY`** and DB role **`DB_PASSWORD`**), re-runs **`migrate`**. **apt**, **Redis**, and **PostgreSQL** steps are idempotent. Superuser handling is described under **Rerun behavior** above.

### Uninstall (remove antibot from the server)

The repo includes **`uninstall.sh`**. It stops **`antibot`**, removes cron lines containing **`run_telegram_backup`**, kills leftover Gunicorn processes for **`/opt/antibot/env/bin/gunicorn`**, **deletes `/opt/antibot` early** (with a verify step — if removal fails, the script exits with an error and suggests **`lsof +D`**), then flushes **Redis DB 1**, drops PostgreSQL **`antibot`** DB and role, and removes **`/root/antibot_superuser_credentials.txt`**. It does **not** run **`apt remove`** on PostgreSQL, Redis, or Python.

**Important:** Removes only **`ANTIBOT_INSTALL_DIR`** (default **`/opt/antibot`**). A bootstrap clone under **`~/…`** is optional and **not** deleted.

```bash
curl -fsSL https://raw.githubusercontent.com/nobodycp/antibot/main/uninstall.sh -o /tmp/antibot-uninstall.sh
sudo bash /tmp/antibot-uninstall.sh          # type YES
sudo bash /tmp/antibot-uninstall.sh --yes    # non-interactive
```

Or from a repo checkout: **`sudo bash uninstall.sh`**.

Custom install path (must match deploy): **`sudo ANTIBOT_INSTALL_DIR=/srv/antibot bash uninstall.sh --yes`**

If the app directory is already deleted, still run **`uninstall.sh`** so PostgreSQL/cron/Redis/systemd are cleaned up.

---

## Production: reverse proxy, static files, and HTTPS

This section is **operator documentation** for Debian/Ubuntu. **`install.sh`** leaves **Gunicorn** on **`0.0.0.0:8000`**; it does **not** install or configure **Nginx** or certificates.

### 1) Role of the reverse proxy vs Gunicorn

- **Gunicorn** runs the Django WSGI app. It is appropriate behind a reverse proxy on the **same machine** (e.g. **`127.0.0.1:8000`**).
- **Do not** expose Gunicorn’s port **8000** directly on the public internet. Use a reverse proxy (**Nginx**, Caddy, Traefik, etc.) on **80/443** to terminate **TLS**, enforce sane timeouts, and serve **static** (and optionally **media**) files efficiently.
- Typical flow: **Browser → HTTPS → Nginx → HTTP → Gunicorn** on loopback.

### 2) Static files (`/static/`)

In **`analytics_project/settings/base.py`**:

- **`STATIC_URL`** is **`/static/`**.
- **`STATIC_ROOT`** is **`staticfiles/`** under the project root (e.g. **`/opt/antibot/staticfiles`** after **`collectstatic`**).
- App and theme assets also use **`STATICFILES_DIRS`** pointing at the project **`static/`** tree; **`collectstatic`** copies everything into **`STATIC_ROOT`**.

**Operator steps:**

1. On the server, after each deploy that changes static assets:

   ```bash
   cd /opt/antibot && source env/bin/activate && set -a && . .env && set +a && python manage.py collectstatic --noinput
   ```

2. **WhiteNoise** (middleware in **`base.py`**) serves **`/static/`** through **Gunicorn**. In production, **`WHITENOISE_USE_FINDERS`** defaults to **on** (see **`prod.py`**) so assets load from each app’s **`static/`** tree even if **`collectstatic`** was not run yet. Run **`collectstatic`** anyway for a normal deploy; set **`DJANGO_WHITENOISE_FINDERS=0`** in **`.env`** once **`staticfiles/`** is reliably populated. **`urls.py`** also registers **`django.views.static.serve`** for **`STATIC_ROOT`** as a fallback. For heavier traffic, add Nginx **`location /static/`** → **`STATIC_ROOT`**.

**Project `static/` directory (repo root):** holds shared assets collected via **`STATICFILES_DIRS`** (e.g. SVG icons under **`static/icons/`** for OS/browser). App-specific UI lives under **`dashboard/static/`**, **`tools/static/`**, etc. See **[`static/README.md`](static/README.md)**.

**Deploy checklist (after every `git pull` on the server):**

1. `source env/bin/activate` (or your venv path)
2. `pip install -r requirements.txt`
3. `python manage.py migrate` (when migrations ship)
4. `python manage.py collectstatic --noinput`
5. Restart Gunicorn (e.g. `sudo systemctl restart <service>`)
6. Smoke: open **`/accounts/login/`** and confirm CSS loads; optional **`GET /health/`** (JSON: **`ok`**, **`database`**, **`cache`**, **`static_design_system_css`** should be true when Redis and DB are up)

### 3) Media files (`/media/`)

- **`MEDIA_URL`** is **`/media/`**; **`MEDIA_ROOT`** is **`media/`** under the project root (e.g. **`/opt/antibot/media`**).
- The app uses uploaded files (e.g. profile avatars). **Gunicorn does not efficiently serve user uploads** at scale.

**Why avatars work locally but 404 on the server:** With **`DEBUG=False`**, Django’s **`static()`** helper for media is a **no-op** (it returns no URL patterns). This project, when **`DJANGO_SERVE_MEDIA=1`** is set, mounts **`/media/`** via **`django.views.static.serve`** explicitly. Prefer **`location /media/`** in Nginx for production; use **`DJANGO_SERVE_MEDIA=1`** only for simple setups (restart Gunicorn after changing **`.env`**).

**Operator steps:** Add a **`location /media/`** block in Nginx (or equivalent) pointing at **`MEDIA_ROOT`**, with correct permissions so the Nginx worker user can read files the app creates. Ensure the app user can write to **`MEDIA_ROOT`** (e.g. **`www-data`** vs **`antibot`** — align ownership with your chosen layout). Verify the file exists on disk at **`MEDIA_ROOT/avatars/...`** (same path as in the URL after **`/media/`**).

### 4) Proxy headers, HTTPS awareness, and Django settings

**Read from `.env` in production (`prod.py`):**

- **`ALLOWED_HOSTS`** — comma-separated hostnames/IPs (required for public access).
- **`USE_X_FORWARDED_PROTO=1`** — sets **`SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')`** so Django treats requests as HTTPS when the proxy sends that header. **Only** if Gunicorn is **not** reachable directly from untrusted clients (otherwise a client could spoof the header).
- **`CSRF_TRUSTED_ORIGINS`** — comma-separated full origins, e.g. **`https://example.com,https://www.example.com`** (needed for HTTPS POST/CSRF in Django 4+).
- **`DJANGO_SECURE_COOKIES=1`** — sets **`SESSION_COOKIE_SECURE`** and **`CSRF_COOKIE_SECURE`** (use when the site is HTTPS-only).

**Proxy configuration reminders:**

| Concern | What to do |
|--------|------------|
| **`Host`** header | Nginx should pass **`proxy_set_header Host $host;`** so Django’s host validation matches **`ALLOWED_HOSTS`**. |
| **`X-Forwarded-Proto`** | Set **`proxy_set_header X-Forwarded-Proto $scheme;`** on the reverse proxy when terminating TLS. |

### 5) Minimal Nginx example (operator guidance only)

Adjust paths, server name, and TLS certificate paths. **This file is not shipped by the repo.**

```nginx
# Example only — validate before use.
server {
    listen 443 ssl http2;
    server_name example.com;

    ssl_certificate     /etc/letsencrypt/live/example.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/example.com/privkey.pem;

    location /static/ {
        alias /opt/antibot/staticfiles/;
    }

    location /media/ {
        alias /opt/antibot/media/;
    }

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

Use **Certbot** (or your CA) for real certificates; add an **HTTP → HTTPS** redirect server block as usual.

### 6) Minimal production checklist (reverse-proxy deployment)

1. **TLS:** Certificates installed; **443** (and **80** redirect) served by Nginx only.
2. **Firewall / security group:** **443** (and **80**) open from the internet; **8000** **not** open publicly (Gunicorn reachable only from **127.0.0.1** on the app host).
3. **`ALLOWED_HOSTS`:** **`install.sh`** usually pre-fills this from detected IPs/hostname; add your **domain** via **`ANTIBOT_EXTRA_ALLOWED_HOSTS`** at install time or edit **`/opt/antibot/.env`** so values match **`server_name`** / how users reach the site, then **`sudo systemctl restart antibot`**.
4. **Static:** Run **`collectstatic`**; Nginx **`location /static/`** → **`STATIC_ROOT`**.
5. **Media:** Nginx **`location /media/`** → **`MEDIA_ROOT`**; permissions consistent with the app user.
6. **Services:** **`postgresql`**, **`redis-server`**, and **`antibot`** (Gunicorn) are **active** (`systemctl status …`).
7. **Smoke tests:** Open **`https://your-host/accounts/login/`** (login page loads, CSS from **`/static/`**); hit **`/dashboard/`** after login; confirm **`/tracker/api/log/`** still works from integrations (HTTPS and **`Host`** as expected).
8. **If needed:** Add **`SECURE_PROXY_SSL_HEADER`** and **`CSRF_TRUSTED_ORIGINS`** in Django settings per section 4 once the proxy is trusted and you see CSRF/secure-cookie issues.

---

## Local development (without `install.sh`)

Use this on macOS or Windows, or when you do not want systemd and `/opt/`:

```bash
git clone https://github.com/nobodycp/antibot.git
cd antibot

python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install --upgrade pip
pip install -r requirements.txt

cp .env.example .env
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

- [http://127.0.0.1:8000/dashboard/](http://127.0.0.1:8000/dashboard/)
- [http://127.0.0.1:8000/accounts/login/](http://127.0.0.1:8000/accounts/login/)

Settings load from `analytics_project.settings`: **dev** unless **`DJANGO_ENV=production`** (or **`prod`**) in `.env`. Omit postgres env vars to keep the default **SQLite** file. Put secrets in `.env`.

---

## Tracker: services, caching, and templates

### Visitor pipeline (API `/tracker/api/log/`)

1. **`visitor_context_service`** — Parses User-Agent, reverse DNS, then calls external IP APIs (ipwho.is, api.ipapi.is, ipinfo.io) to build a `VisitorContext`.
2. **`visitor_decision_service`** — Applies subnet/IP/ISP/OS/browser/country/hostname rules and allowed countries.
3. **`visitor_persistence_service`** — On allow: `Visitor`, `IPInfo`, `IPLog`; on deny: `RejectedVisitor`.

### IP enrichment cache

- Successful API enrichment is stored in Django’s cache so repeat lookups for the same IP skip HTTP calls until the entry expires.
- **Cache key:** `ip_context_<ip>` (e.g. `ip_context_203.0.113.10`).
- **Default TTL:** 6 hours (`21600` seconds), configurable via the **`TRACKER_IP_CONTEXT_CACHE_TIMEOUT`** environment variable (seconds).
- **Failures** (network/JSON errors) are **not** cached; the next request retries the APIs.
- **`CACHES`** in `analytics_project/settings/base.py` defaults to **django-redis** (`REDIS_URL`, default **`redis://127.0.0.1:6379/1`**). **Tests** may override with **LocMem** so CI does not require Redis.

### Tracker UI templates

- List and management pages under `tracker/templates/tracker/` reuse shared partials in `tracker/templates/tracker/partials/includes/` (headings, search inputs, table chrome, pagination, HTMX message-clear scripts) so behavior and layout stay aligned across blocked lists, logs, allowed countries, and IP info.

---

## Endpoints overview

Paths assume the app is mounted at the site root (e.g. `https://example.com`). Adjust for your deployment.

### API

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/tracker/api/log/` | Header `X-API-Key` required (user’s key from profile settings). JSON: `ip`, `useragent`. Returns `access_granted` or `access_denied` with a reason on deny. |

**API key storage**

- Lookup uses **HMAC-SHA256** with Django’s `SECRET_KEY` (field `api_key_lookup_hash`), not bare SHA-256. Migration **`dashboard.0006_userapikey_hmac_lookup`** backfills hashes from existing plaintext keys; run `python manage.py migrate` after deploy.
- **Regenerate** (profile settings) returns the new secret **once** in the UI/session; the database keeps only the digest plus an internal placeholder (`__hk__…`), not the full key.
- Keys created automatically at **user signup** may still live as plaintext until the user regenerates once; the API still resolves **HMAC**, legacy **SHA-256** digest, or plaintext for those rows.
- Rotating **`SECRET_KEY`** invalidates HMAC-based lookups until keys are re-issued or re-hashed.

**Example request**

```bash
curl -s -X POST http://127.0.0.1:8000/tracker/api/log/ \
  -H "Content-Type: application/json" \
  -H "X-API-Key: YOUR_USER_API_KEY_FROM_PROFILE_SETTINGS" \
  -d '{"ip":"203.0.113.10","useragent":"Mozilla/5.0 ..."}'
```

### Authentication (Django)

| Path | Description |
|------|-------------|
| `/accounts/login/` | Login |
| `/accounts/logout/` | Logout |
| `/accounts/password_change/` | Password change (authenticated) |

> Other `django.contrib.auth.urls` routes live under `/accounts/`.

### Dashboard — `dashboard`

| Path | Description |
|------|-------------|
| `/dashboard/` | Home |
| `/dashboard/home/stats/` | Stats partial (HTMX) |
| `/dashboard/home/secondary-stats/` | Secondary stats |
| `/dashboard/home/alerts/` | Alerts |
| `/dashboard/home/latest-logs/` | Latest logs |
| `/dashboard/home/top-ips/` | Top IPs |
| `/dashboard/users/` | User management |
| `/dashboard/users/add/` | Add user |
| `/dashboard/users/edit/<id>/` | Edit user |
| `/dashboard/users/delete/<id>/` | Delete user |
| `/dashboard/profile-settings/` | Profile settings |
| `/dashboard/telegram-backup-settings/` | Telegram backup settings |
| `/dashboard/telegram-test/` | Telegram test |
| `/dashboard/telegram-send-db-backup/` | Send DB backup |

### Tracker & blocking — `tracker`

| Path | Description |
|------|-------------|
| `/tracker/blocked-ips/` | Blocked IPs |
| `/tracker/blocked-subnets/` | Blocked subnets |
| `/tracker/blocked-isps/` | Blocked ISPs |
| `/tracker/blocked-browsers/` | Blocked browsers |
| `/tracker/blocked-os/` | Blocked OSes |
| `/tracker/blocked-hostnames/` | Blocked hostnames |
| `/tracker/allowed-countries/` | Allowed countries |
| `/tracker/allowed-logs/` | Allowed visit log |
| `/tracker/denied-logs/` | Denied visit log (+ add block rule) |
| `/tracker/ip-info/` | IP info (+ add block rule) |
| `/tracker/dinger-ip/` | IPs with high visit counts (`count > 10`); delete rows from `IPLog` |

**Table / partial URLs (HTMX)** — each screen has companion routes such as `.../table/` and `.../partial/` (e.g. `blocked-isps/partial/` for ISP). Templates use these; you rarely open them by hand.

### Tools — `tools`

| Path | Description |
|------|-------------|
| `/tools/upload-files/` | File upload |
| `/tools/google-safe-check/` | Google Safe Browsing check |
| `/tools/google-safe-check/partial/` | Results table partial |
| `/tools/redirect-check/` | Redirect check |
| `/tools/redirect-check/table/` | Redirect table partial |
| `/tools/cloudflare-domains/` | Cloudflare zones (logged-in user, own domains) |
| `/tools/cloud-sync/` | Cloudflare WAF sync (superuser) |
| `/dashboard/users/<id>/domains/` | Admin: manage a user's Cloudflare zones |

---

## Cloudflare WAF sync

Register zones under **Tools → Cloudflare Domains** (each user) or **Users → Domains** (superuser). API tokens are encrypted at rest and are not shown again after save.

**Superuser:** **Tools → Cloud Sync → Sync All** pushes rules to every **active** domain:

- **Subnets:** global `BlockedSubnet` list → `antibot:subnet-block`
- **Countries:** owner's `AllowedCountry` codes → `antibot:country-allow-<user_id>` (`not ip.geoip.country in {...}`)

Only WAF custom rules whose description starts with `antibot:` are replaced; other zone rules are left unchanged.

**Per-domain zone settings** (checkboxes and dropdowns on add/edit) are pushed after WAF rules on each **Sync** and on **Sync All**:

- Toggles: Bot Fight Mode, Under Attack Mode, Block AI Bots, AI Labyrinth, AI Crawl Control (maps to `content_bots_protection`), Browser Integrity Check, Always Use HTTPS, HTTP/3 (with QUIC), 0-RTT Connection Resumption, Automatic HTTPS Rewrites
- Dropdowns: Security level, minimum TLS, SSL/TLS mode, challenge passage TTL (`challenge_ttl`)

**Per-domain rate limit** (section **Rate limit** on add/edit domain forms):

- Enable checkbox, then set **Requests** (e.g. `30`), **Per** window in seconds (e.g. `10`), **Action** (`block`, `challenge`, `js_challenge`, `managed_challenge`), and **Duration** mitigation timeout in seconds (e.g. `10`).
- Sync pushes rule `antibot:rate-limit` to the zone `http_ratelimit` entrypoint ruleset (per client IP via `ip.src`). Disabled in the UI removes that rule from Cloudflare.

Bot/AI toggles use `GET`/`PUT` `/zones/{zone_id}/bot_management` (plan-dependent). Other fields use `GET`/`PATCH` `/zones/{zone_id}/settings/{id}`. Each setting is compared with Cloudflare before PATCH (no write when already matching). Rate limits use `GET`/`PUT` `/zones/{zone_id}/rulesets/phases/http_ratelimit/entrypoint` (and ruleset update by id).

### Cloudflare API token permissions

Use a **Bearer API token** only (paste the token string; the app sends `Authorization: Bearer …`).
**Do not** use the account **Global API Key** + email — Cloudflare returns *Authentication error* and sync will fail.

**Token type:** A **Zone API token** (one zone) or a **Custom token** with **Zone** permissions are both fine. An account-level custom token with **Zone Resources → All zones** (or **Include → Specific zone**) works the same way, as long as the permissions below are granted for every zone you register. Prefer **one zone per token** when possible.

**Zone resources:** Scope the token to **only the zone(s)** you add in antibot (`zone_id` + domain). **All zones** is OK for operators who manage many domains with one token; **Specific zone** is tighter.

| Tier | Permission resource | Permission | Access | Used for |
|------|---------------------|------------|--------|----------|
| **Minimum** | Zone | Zone | Read | `GET /zones/{id}`, `GET /zones?name=…` (save/verify) |
| **Minimum** | Zone | Zone Settings | Edit | `GET`/`PATCH /zones/{id}/settings/*` (HTTPS, TLS, security level, challenge TTL, …) |
| **Minimum** | Zone | WAF | Edit | `GET`/`PUT` `rulesets/.../http_request_firewall_custom/entrypoint` (subnet + country `antibot:*` rules) |
| **Recommended** | Zone | Firewall Services | Edit | Same rulesets API path; include if WAF-only token gets 403 on sync |
| **Recommended** | Zone | Bot Management | Edit | `GET`/`PUT /zones/{id}/bot_management` (Bot Fight, AI bots, Labyrinth, crawl control) |
| **Recommended** | Zone | WAF | Edit | `GET`/`PUT` `rulesets/.../http_ratelimit/entrypoint` (`antibot:rate-limit`) |
| **Recommended** | Account | Account Filter Lists | Edit | `GET`/`POST`/`PUT /zones/{id}/rules/lists*` when **>25** global blocked subnets (IP list `antibot_subnet_block`) |

Cloudflare’s UI may label access as **Edit** or **Write** depending on template age; use the write level for each row.

**If a permission is missing**

| Missing permission | What breaks |
|--------------------|-------------|
| Zone → Read | Cannot add/verify domain; sync auth errors |
| Zone Settings → Edit | Sync fails on first zone setting (`always_use_https`, `ssl`, …) |
| WAF → Edit | Subnet/country WAF rules not pushed; sync **error** |
| Firewall Services → Edit | Same as WAF if your account maps rulesets only to this permission |
| Bot Management → Edit | Bot/AI toggles not applied; sync **warning** only (DB values kept) |
| Account Filter Lists → Edit | Fails when global blocked subnets **>25** (IP list path); ≤25 inline subnets still work |
| WAF (rate limit phase) | Per-domain rate limit UI has no effect; sync **error** on rate-limit step |

**API surface (all calls in this repo):** `dashboard/helpers/cloudflare_zone.py` (zone verify); `tools/services/cloudflare_sync_service.py` (WAF custom + zone IP lists); `tools/services/cloudflare_zone_settings.py` (settings + bot management); `tools/services/cloudflare_rate_limit.py` (rate limit ruleset). No other Cloudflare HTTP clients.

---

## Tests

```bash
source .venv/bin/activate
python manage.py test tracker.tests tools.tests dashboard.tests
```

---

## License & contributing

See repository files for a license if one is provided. Contributions: use feature branches and clear pull requests to simplify review.
