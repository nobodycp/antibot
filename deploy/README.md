# Manual production deploy (systemd + Gunicorn)

Use **`install.sh`** for an automated server install, or follow these steps when you manage the host yourself.

## Prerequisites

- Python 3.9+ venv with `pip install -r requirements.txt`
- PostgreSQL and Redis running
- Node.js 18+ and `npm install` in `whatsapp/` (automated by **`install.sh`** on Debian/Ubuntu; set `NODE_BIN` in env if `node` is not on default PATH)
- Nginx (or similar) proxying to `127.0.0.1:8000` — do not expose Gunicorn directly on the public internet

Optional local PostgreSQL for testing:

```bash
docker compose up -d
export DATABASE_URL=postgres://antibot:antibot@127.0.0.1:5432/antibot
```

## Environment file

Create **`/etc/antibot/env`** (mode `600`) from **`.env.example`**. Required for production:

- `DJANGO_ENV=production`
- `DJANGO_SECRET_KEY` or `SECRET_KEY`
- `ALLOWED_HOSTS` (comma-separated)
- PostgreSQL via **`DATABASE_URL`**, **`POSTGRES_*`**, or legacy **`DB_*`** (see `.env.example`)
- `REDIS_URL` if not using default `redis://127.0.0.1:6379/1`

Omit all database variables only for **local development** (SQLite). Production settings **require** PostgreSQL.

## Deploy steps

From the project root (e.g. `/opt/antibot`):

```bash
source env/bin/activate   # or .venv/bin/activate
set -a && source /etc/antibot/env && set +a

python manage.py migrate
python manage.py collectstatic --noinput
python manage.py createsuperuser   # first install only
```

Install and start the service:

```bash
sudo cp deploy/antibot.service /etc/systemd/system/antibot.service
# Adjust User, WorkingDirectory, and ExecStart venv path in the unit if needed
sudo systemctl daemon-reload
sudo systemctl enable --now antibot
sudo systemctl status antibot
journalctl -u antibot -f
```

Gunicorn listens on **`127.0.0.1:8000`**. Point Nginx `proxy_pass` there and set `USE_X_FORWARDED_PROTO=1` / `CSRF_TRUSTED_ORIGINS` as in `.env.example`.

## Background jobs (later)

Cloudflare WAF sync and WhatsApp number-check jobs currently run in-process (threads / subprocess). For heavier production loads, move them to **Celery** workers backed by Redis — no Celery wiring is included yet; Redis is already used for Django cache and rate limits.
