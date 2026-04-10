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
| **Utilities** | File uploads, Google Safe Browsing checks, and redirect inspection. |

**Main integration point for external apps:** `POST /tracker/api/log/` — send header **`X-API-Key`** with the **per-user key** shown on **Dashboard → Profile settings** (each user gets a key when their account is created). JSON body: `ip`, `useragent`. Responses: allow (`201`) or deny (`403`) with a readable reason. Missing or wrong key returns `403` with `{"error": "..."}`.

---

## Requirements

- **Python 3.9+** (aligned with Django in `requirements.txt`)
- **Database:** SQLite when **`DB_NAME`** is unset (typical local dev). PostgreSQL when **`DB_NAME`** and related **`DB_*`** vars are set — see **`.env.example`**. Requires **`psycopg2-binary`** from `requirements.txt`. The **`install.sh`** path provisions PostgreSQL and writes `.env` with **`DB_*`** automatically.

---

## Server install (recommended) — `install.sh`

This repo ships **`install.sh`** for automated deployment on **Debian/Ubuntu**: system packages (including **PostgreSQL**, **Redis** `redis-server`, and **Gunicorn** via `requirements.txt`), local **PostgreSQL** database and role, **`redis-server`** enabled and started (so **`REDIS_URL=redis://127.0.0.1:6379/1`** matches the local instance unless you change it later), `/opt/antibot/.env` with **`DJANGO_ENV=production`**, **`DB_*`**, **`DJANGO_SECRET_KEY`**, **`REDIS_URL`**, and **`ALLOWED_HOSTS`**, clone to `/opt/antibot`, virtualenv at `env`, **`migrate` against PostgreSQL**, initial Django superuser (see below), a **systemd** unit running **Gunicorn** bound to **`0.0.0.0:8000`** (with **`EnvironmentFile`** for `.env`, ordered after **`postgresql.service`** and **`redis-server.service`**), and a **cron** job for Telegram backup.

**Public internet:** Do **not** leave port **8000** open to the world. **`install.sh` does not configure Nginx or TLS.** For production, terminate HTTPS on **Nginx** (or similar) and proxy to **Gunicorn** on localhost — see **[Production: reverse proxy, static files, and HTTPS](#production-reverse-proxy-static-files-and-https)** below.

From your machine (after cloning the repo):

```bash
git clone https://github.com/nobodycp/antibot.git
cd antibot
sudo bash install.sh
```

The script creates `/opt/antibot` if needed before writing the inner installer.

**What it does internally**

1. Ensures `/opt/antibot` exists, writes the real installer to `/opt/antibot/install.sh`, then runs it.
2. Installs **python3**, **venv**, **git**, **openssl**, **postgresql**, **postgresql-contrib**, and **redis-server**; enables and starts **`redis-server`** (Debian/Ubuntu unit name).
3. Stops any existing `antibot` service, **wipes** `/opt/antibot`, and clones the repo again (do not rely on uncommitted edits under `/opt` only).
4. Creates the venv at `/opt/antibot/env` and installs `requirements.txt` (includes **Gunicorn**).
5. Enables and starts **PostgreSQL**; idempotently ensures a role and database (defaults: **`antibot`** / **`127.0.0.1:5432`**). A strong random **`DB_PASSWORD`** is written to **`/opt/antibot/.env`** (existing role password is updated on reinstall). No `DROP DATABASE`.
6. Writes **`/opt/antibot/.env`** with **`DJANGO_ENV=production`**, **`DB_*`**, **`DJANGO_SECRET_KEY`**, **`REDIS_URL`**, **`ALLOWED_HOSTS`** (edit **`ALLOWED_HOSTS`** for your public hostname or IP).
7. **Django superuser (first install):** There is **no default password** in the script. Either set **`ANTIBOT_SUPERUSER_PASSWORD`** in the environment when running the installer (for example `sudo -E bash install.sh` after `export`, or `sudo env ANTIBOT_SUPERUSER_PASSWORD='…' bash install.sh`), or omit it and the script generates a password and writes **`/root/antibot_superuser_credentials.txt`** (mode **600**). Optional: **`ANTIBOT_SUPERUSER_USERNAME`**, **`ANTIBOT_SUPERUSER_EMAIL`**. Then **`migrate`** and **`createsuperuser --noinput`** run.
8. Installs/enables the **systemd** service using **Gunicorn** (`analytics_project.wsgi:application`, **2** workers, **120** s timeout).
9. Configures the Telegram backup **cron** job and prints service status.

After install, the app listens on **`http://<server>:8000`** (all interfaces). For a quick LAN check that is fine; for the public internet, put **Nginx** in front (HTTPS on **443**, proxy to **`127.0.0.1:8000`**) and follow the production section below. Open the **dashboard** at `/dashboard/` and sign in at `/accounts/login/` using the superuser credentials from your chosen method above.

**Rerun behavior:** If the superuser **already exists** in PostgreSQL, **`createsuperuser --noinput`** fails and is ignored — the **existing password is not changed**. To rotate the superuser password, use Django’s admin or `changepassword`. The installer still regenerates **`/opt/antibot/.env`** (and rotates the **database user** password to match); it does **not** rotate the Django superuser unless you supply **`ANTIBOT_SUPERUSER_PASSWORD`** on a run where the user does not yet exist, or you manage passwords outside the script.

**Data safety (existing SQLite on the server):** This installer does **not** migrate or import old SQLite data into PostgreSQL. Take a **backup** from the current environment first, deploy the new version, let **`migrate`** create the PostgreSQL schema, then **restore or import data manually** if you need historical rows. Until then, the app uses the new empty PostgreSQL database.

**Rerunning `install.sh` (summary):** Does not drop the PostgreSQL database. Resets **`/opt/antibot`**, regenerates **`.env`** (new **`DJANGO_SECRET_KEY`** and DB role **`DB_PASSWORD`**), re-runs **`migrate`**. **apt**, **Redis**, and **PostgreSQL** steps are idempotent. Superuser handling is described under **Rerun behavior** above.

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

2. Configure the reverse proxy to serve **`/static/`** as **files** from **`STATIC_ROOT`** (e.g. `alias /opt/antibot/staticfiles/;`), with a **`location /static/`** block. Do **not** rely on Gunicorn to serve collected static in production.

### 3) Media files (`/media/`)

- **`MEDIA_URL`** is **`/media/`**; **`MEDIA_ROOT`** is **`media/`** under the project root (e.g. **`/opt/antibot/media`**).
- The app uses uploaded files (e.g. profile avatars). **Gunicorn does not efficiently serve user uploads** at scale.

**Operator steps:** Add a **`location /media/`** block in Nginx (or equivalent) pointing at **`MEDIA_ROOT`**, with correct permissions so the Nginx worker user can read files the app creates. Ensure the app user can write to **`MEDIA_ROOT`** (e.g. **`www-data`** vs **`antibot`** — align ownership with your chosen layout).

### 4) Proxy headers, HTTPS awareness, and Django settings

**Currently in code:**

- **`analytics_project/settings/prod.py`** reads **`ALLOWED_HOSTS`** from the **`ALLOWED_HOSTS`** environment variable (comma-separated). **`install.sh`** sets loopback-only hosts until you edit **`/opt/antibot/.env`** to include your public **hostname(s) and/or IP(s)**.

**Not currently wired from `.env` in this project** (document here so you know what to add if needed):

| Concern | What to do |
|--------|------------|
| **`Host`** header | Nginx should pass **`proxy_set_header Host $host;`** (or your canonical host) so Django’s host validation matches **`ALLOWED_HOSTS`**. |
| **`X-Forwarded-Proto`** | Set **`proxy_set_header X-Forwarded-Proto $scheme;`** so the upstream knows the client used HTTPS. |
| Django **`request.is_secure()`** / redirects | Django only treats the request as HTTPS behind a proxy if **`SECURE_PROXY_SSL_HEADER`** is set (e.g. **`('HTTP_X_FORWARDED_PROTO', 'https')`**). **This is not set in the repo today.** If you need secure cookies or correct “https” URLs from Django’s point of view, add that in **`prod.py`** (or **`base.py`** under production) after you trust the proxy — **never** set it if clients can reach Gunicorn directly with a spoofed header. |
| **CSRF** (Django 4.x + HTTPS) | Logins and forms may require **`CSRF_TRUSTED_ORIGINS`** (e.g. **`https://example.com`**). **Not read from `.env` in this repo yet.** If you see CSRF failures behind HTTPS, add the appropriate list in settings (often mirroring your public URLs). |

Until those are added in settings, many deployments still work for basic pages if the proxy and **`ALLOWED_HOSTS`** are correct; add **`SECURE_PROXY_SSL_HEADER`** and **`CSRF_TRUSTED_ORIGINS`** when you enable stricter cookie/CSRF behavior or see related errors.

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
3. **`ALLOWED_HOSTS`:** In **`/opt/antibot/.env`**, set **`ALLOWED_HOSTS`** to your public hostname(s) and IP(s), comma-separated, matching **`server_name`** / how users reach the site.
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

Settings load from `analytics_project.settings`: **dev** unless **`DJANGO_ENV=production`** (or **`prod`**) in `.env`. Omit **`DB_NAME`** to keep the default **SQLite** file. Put secrets in `.env`.

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

---

## Tests

```bash
source .venv/bin/activate
python manage.py test tracker.tests
```

---

## License & contributing

See repository files for a license if one is provided. Contributions: use feature branches and clear pull requests to simplify review.
