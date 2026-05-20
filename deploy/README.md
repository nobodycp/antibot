# Manual production deploy (systemd + Gunicorn)

Use **`install.sh`** for an automated server install, or follow these steps when you manage the host yourself.

## Prerequisites

- Python 3.9+ venv with `pip install -r requirements.txt`
- PostgreSQL and Redis running
- **Node.js 20+** and `npm install` in `whatsapp/` (`@whiskeysockets/baileys` requires it). **`install.sh`** installs Node 20 via NodeSource on Debian/Ubuntu and writes `NODE_BIN` to project `.env`. Set `NODE_BIN` manually if `node` is not on the default PATH.
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

## WhatsApp check jobs and `systemctl restart`

`deploy/antibot.service` sets **`KillMode=process`**. Without it, systemd’s default `control-group` sends SIGTERM to **all** processes in the service cgroup on restart — including Node validators started for WhatsApp number-check jobs (even with `start_new_session=True`). That shows up as jobs stopping mid-run (e.g. at 188/198/248) with “Check stopped before finishing”.

After changing the unit file:

```bash
sudo cp deploy/antibot.service /etc/systemd/system/antibot.service
sudo systemctl daemon-reload
sudo systemctl restart antibot
```

Validators already use `start_new_session=True` and, when available, `systemd-run --scope` for an extra cgroup boundary. Set `WHATSAPP_SKIP_SYSTEMD_RUN=1` in `/etc/antibot/env` only if scope spawning causes issues on your host.

## Upgrade Node.js 12 → 20 (existing server)

Debian/Ubuntu often ship **Node 12** from `apt`. That is too old for `whatsapp/` (Baileys needs **Node 20+**). Run as **root** on the server (default install path `/opt/antibot`):

```bash
set -euo pipefail
INSTALL_DIR=/opt/antibot

node -v || true   # often v12.x from distro packages

apt-get update
apt-get remove -y nodejs npm libnode-dev nodejs-doc 2>/dev/null || true
curl -fsSL https://deb.nodesource.com/setup_20.x | bash -
apt-get install -y nodejs

node -v   # expect v20.x
npm -v
which node

NODE_PATH="$(command -v node)"
if [ -f "${INSTALL_DIR}/.env" ]; then
  if grep -q '^NODE_BIN=' "${INSTALL_DIR}/.env"; then
    sed -i "s|^NODE_BIN=.*|NODE_BIN=${NODE_PATH}|" "${INSTALL_DIR}/.env"
  else
    echo "NODE_BIN=${NODE_PATH}" >> "${INSTALL_DIR}/.env"
  fi
fi

cd "${INSTALL_DIR}/whatsapp"
rm -rf node_modules
npm install --omit=dev

systemctl restart antibot
systemctl status antibot --no-pager
```

If `npm install` still fails, confirm `node -v` is **20+** and that `NODE_BIN` in `${INSTALL_DIR}/.env` matches `which node`. Re-run only the WhatsApp step:

```bash
cd /opt/antibot/whatsapp && npm install --omit=dev
systemctl restart antibot
```

After pulling a newer `install.sh`, you can re-run the inner installer phase on an existing tree (does **not** wipe the repo): `cd /opt/antibot && sudo bash install.sh --inner` — it will upgrade Node if needed and refresh `.env` `NODE_BIN`.

## Cloudflare blocked-subnet IP list

When a zone has more than **25** blocked subnets, antibot syncs them to a zone IP list (`antibot_subnet_block`) via the Cloudflare API in **batches** (paginated GET, batched POST/DELETE), not a single giant request.

Optional cap in `/etc/antibot/env` (or project `.env`):

```bash
# Optional: limit how many BlockedSubnet rows are pushed per sync (logs a warning if DB has more)
# CF_IP_LIST_MAX_ITEMS=10000
```

If unset, all blocked subnets in the database are synced. Set this if you hit Cloudflare account list limits or need to stage rollout.

## Background jobs (later)

Cloudflare WAF sync and WhatsApp number-check jobs currently run in-process (threads / subprocess). For heavier production loads, move them to **Celery** workers backed by Redis — no Celery wiring is included yet; Redis is already used for Django cache and rate limits.
