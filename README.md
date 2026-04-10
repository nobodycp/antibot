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

**Main integration point for external apps:** `POST /tracker/api/log/` — send `ip` and `useragent` in JSON; responses indicate allow (`201`) or deny (`403`) with a readable reason.

---

## Requirements

- **Python 3.9+** (aligned with Django in `requirements.txt`)
- **Database:** SQLite by default (fine for dev; use PostgreSQL in production with settings changes)

---

## Server install (recommended) — `install.sh`

This repo ships **`install.sh`** for automated deployment on **Debian/Ubuntu**: system packages, clone to `/opt/antibot`, virtualenv at `env`, `migrate`, a superuser, a **systemd** unit running `runserver` on `0.0.0.0:8000`, and a **cron** job for Telegram backup.

From your machine (after cloning the repo):

```bash
git clone https://github.com/nobodycp/antibot.git
cd antibot
sudo bash install.sh
```

The script creates `/opt/antibot` if needed before writing the inner installer.

**What it does internally**

1. Ensures `/opt/antibot` exists, writes the real installer to `/opt/antibot/install.sh`, then runs it.
2. Stops any existing `antibot` service, **wipes** `/opt/antibot`, and clones the repo again (do not rely on uncommitted edits under `/opt` only).
3. Creates the venv at `/opt/antibot/env` and installs `requirements.txt`.
4. Runs `migrate` and `createsuperuser` with defaults baked into the script (`admin` / `adminpass` — **change these immediately** via Django admin or the shell).
5. Enables the systemd service and prints status.

Then open the **dashboard** at `http://<server>:8000/dashboard/` and sign in at `/accounts/login/`.

> For serious production, prefer **Gunicorn/uWSGI** behind **Nginx**, turn off `DEBUG`, and set `SECRET_KEY` via `.env` (see `.env.example`).

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

Settings load from `analytics_project.settings` (default **dev**). Put secrets in `.env`.

---

## Endpoints overview

Paths assume the app is mounted at the site root (e.g. `https://example.com`). Adjust for your deployment.

### API

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/tracker/api/log/` | JSON body: `ip`, `useragent`. Returns `access_granted` or `access_denied` with a reason on deny. |

**Example request**

```bash
curl -s -X POST http://127.0.0.1:8000/tracker/api/log/ \
  -H "Content-Type: application/json" \
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
| `/tracker/blocked-isp/` | Blocked ISPs |
| `/tracker/blocked-browser/` | Blocked browsers |
| `/tracker/blocked-os/` | Blocked OSes |
| `/tracker/blocked-hostname/` | Blocked hostnames |
| `/tracker/allowed-country/` | Allowed countries |
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
