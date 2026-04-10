#!/usr/bin/env bash
#
# antibot — single server installer (Debian/Ubuntu)
#
# One file only: bootstrap clones the repo, then re-runs this same script with --inner.
# Direct install URL (same file for everything, including login credentials at the end):
#   curl -fsSL https://raw.githubusercontent.com/nobodycp/antibot/main/install.sh | sudo bash
#
# Usage:
#   sudo bash install.sh
#   sudo ANTIBOT_INSTALL_DIR=/srv/antibot bash install.sh
#   sudo ANTIBOT_REPO_URL=https://github.com/you/fork.git bash install.sh
#
set -eo pipefail

# =============================================================================
# Inner phase: repo already exists at INSTALL_DIR (do not run by hand first time)
# =============================================================================
if [ "${1:-}" = "--inner" ]; then
  shift

  if [ "${EUID:-$(id -u)}" -ne 0 ]; then
    echo "Run as root: sudo bash install.sh"
    exit 1
  fi

  INSTALL_DIR="${ANTIBOT_INSTALL_DIR:-/opt/antibot}"
  VENV_PATH="${INSTALL_DIR}/env"
  SERVICE_NAME="antibot"
  BIND_ADDR="0.0.0.0:8000"

  if [ ! -f "${INSTALL_DIR}/manage.py" ]; then
    echo "ERROR: Django project not found at ${INSTALL_DIR} (missing manage.py)."
    exit 1
  fi

  SU_USER="${ANTIBOT_SUPERUSER_USERNAME:-admin}"
  SU_EMAIL="${ANTIBOT_SUPERUSER_EMAIL:-admin@localhost}"

  PG_DB_NAME="antibot"
  PG_DB_USER="antibot"
  PG_DB_HOST="127.0.0.1"
  PG_DB_PORT="5432"

  echo "[1/8] Installing packages (apt, Redis, PostgreSQL, then .env, migrate, Gunicorn, cron)..."
  sudo apt update
  sudo apt install -y python3 python3-venv python3-pip git curl openssl postgresql postgresql-contrib redis-server

  echo "[2/8] Redis..."
  sudo systemctl enable redis-server
  sudo systemctl start redis-server

  echo "[3/8] Creating/updating Python venv..."
  python3 -m venv "${VENV_PATH}"
  "${VENV_PATH}/bin/pip" install --upgrade pip
  [ -f "${INSTALL_DIR}/requirements.txt" ] && \
    "${VENV_PATH}/bin/pip" install -r "${INSTALL_DIR}/requirements.txt"

  echo "[4/8] PostgreSQL and .env file..."
  sudo systemctl enable postgresql
  sudo systemctl start postgresql

  PG_PASSWORD="$(openssl rand -hex 32)"

  if ! sudo -u postgres psql -tAc "SELECT 1 FROM pg_roles WHERE rolname='${PG_DB_USER}'" | grep -q 1; then
    sudo -u postgres psql -v ON_ERROR_STOP=1 -c "CREATE USER ${PG_DB_USER} WITH PASSWORD '${PG_PASSWORD}';"
  else
    sudo -u postgres psql -v ON_ERROR_STOP=1 -c "ALTER USER ${PG_DB_USER} WITH PASSWORD '${PG_PASSWORD}';"
  fi

  if ! sudo -u postgres psql -tAc "SELECT 1 FROM pg_database WHERE datname='${PG_DB_NAME}'" | grep -q 1; then
    sudo -u postgres psql -v ON_ERROR_STOP=1 -c "CREATE DATABASE ${PG_DB_NAME} OWNER ${PG_DB_USER};"
  fi

  sudo -u postgres psql -v ON_ERROR_STOP=1 -c "GRANT ALL PRIVILEGES ON DATABASE ${PG_DB_NAME} TO ${PG_DB_USER};"
  sudo -u postgres psql -v ON_ERROR_STOP=1 -d "${PG_DB_NAME}" -c "GRANT ALL ON SCHEMA public TO ${PG_DB_USER};" || true
  sudo -u postgres psql -v ON_ERROR_STOP=1 -d "${PG_DB_NAME}" -c "GRANT CREATE ON SCHEMA public TO ${PG_DB_USER};" || true
  sudo -u postgres psql -d "${PG_DB_NAME}" -c "ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO ${PG_DB_USER};" 2>/dev/null || true
  sudo -u postgres psql -d "${PG_DB_NAME}" -c "ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON SEQUENCES TO ${PG_DB_USER};" 2>/dev/null || true

  if [ -n "${ANTIBOT_ALLOWED_HOSTS:-}" ]; then
    ALLOWED_HOSTS_VALUE="${ANTIBOT_ALLOWED_HOSTS}"
    echo "[env] ALLOWED_HOSTS from ANTIBOT_ALLOWED_HOSTS (override)."
  else
    ALLOWED_HOSTS_VALUE="$(
      {
        echo "127.0.0.1"
        echo "localhost"
        _hn="$(hostname 2>/dev/null || true)"
        if [ -n "${_hn}" ] && [ "${_hn}" != "localhost" ]; then echo "${_hn}"; fi
        if command -v ip >/dev/null 2>&1; then
          ip -4 route get 8.8.8.8 2>/dev/null | awk '{ for (i = 1; i < NF; i++) if ($i == "src") { print $(i + 1); exit } }' || true
        fi
        _hi="$(hostname -I 2>/dev/null || true)"
        if [ -n "${_hi}" ]; then
          echo "${_hi}" | awk '{ print $1 }'
        fi
        if command -v curl >/dev/null 2>&1; then
          curl -fsS --max-time 3 --connect-timeout 2 "https://api.ipify.org" 2>/dev/null || true
        fi
        if [ -n "${ANTIBOT_EXTRA_ALLOWED_HOSTS:-}" ]; then
          echo "${ANTIBOT_EXTRA_ALLOWED_HOSTS}" | tr ',' '\n'
        fi
      } | sed '/^$/d' | awk 'NF && !seen[$0]++' | paste -sd ','
    )"
    echo "[env] ALLOWED_HOSTS auto-detected: ${ALLOWED_HOSTS_VALUE}"
  fi
  if [ -z "${ALLOWED_HOSTS_VALUE}" ]; then
    ALLOWED_HOSTS_VALUE="127.0.0.1,localhost"
    echo "[warn] ALLOWED_HOSTS empty after detection; using 127.0.0.1,localhost only."
  fi

  _antibot_print_access_info() {
    local _port="${BIND_ADDR##*:}"
    local _url_ip="" _last_public="" _first_private="" _h _oa _ob _oc _od
    local IFS=,
    for _h in ${ALLOWED_HOSTS_VALUE}; do
      _h="$(echo "${_h}" | tr -d '[:space:]')"
      [[ "${_h}" =~ ^[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}$ ]] || continue
      [ "${_h}" = "127.0.0.1" ] && continue
      IFS=. read -r _oa _ob _oc _od <<< "${_h}" || continue
      if [ "${_oa}" = "10" ] || { [ "${_oa}" = "172" ] && [ "${_ob}" -ge 16 ] && [ "${_ob}" -le 31 ]; } \
        || { [ "${_oa}" = "192" ] && [ "${_ob}" = "168" ]; }; then
        [ -z "${_first_private}" ] && _first_private="${_h}"
      else
        _last_public="${_h}"
      fi
    done
    _url_ip="${_last_public:-${_first_private}}"
    if [ -z "${_url_ip}" ] && command -v ip >/dev/null 2>&1; then
      _url_ip="$(ip -4 route get 8.8.8.8 2>/dev/null | awk '{ for (i = 1; i < NF; i++) if ($i == "src") { print $(i + 1); exit } }')"
    fi
    [ -z "${_url_ip}" ] && _url_ip="127.0.0.1"
    echo ""
    echo "══════════════════════════════════════════════════════════════"
    echo "  LOGIN CREDENTIALS (save this output)"
    echo "══════════════════════════════════════════════════════════════"
    echo "  Username:       ${SU_USER}"
    echo "  Password:       ${SU_PASS}"
    echo "  Login URL:      http://${_url_ip}:${_port}/accounts/login/"
    echo "  Dashboard URL:  http://${_url_ip}:${_port}/dashboard/"
    echo "  Local URL:      http://127.0.0.1:${_port}/accounts/login/"
    echo "  ALLOWED_HOSTS:  ${ALLOWED_HOSTS_VALUE}"
    echo "══════════════════════════════════════════════════════════════"
    echo "  Also saved (if password was generated): /root/antibot_superuser_credentials.txt"
    echo "  If superuser already existed, password above may not match DB — use changepassword."
    echo "══════════════════════════════════════════════════════════════"
    echo ""
  }

  ENV_FILE="${INSTALL_DIR}/.env"
  DJANGO_SECRET_VALUE="$(openssl rand -hex 48)"
  umask 077
  cat > "${ENV_FILE}" <<ENVEOF
# Generated by install.sh. Edit ALLOWED_HOSTS or use ANTIBOT_* on next install.
DJANGO_ENV=production
DJANGO_SECRET_KEY=${DJANGO_SECRET_VALUE}
ALLOWED_HOSTS=${ALLOWED_HOSTS_VALUE}
REDIS_URL=redis://127.0.0.1:6379/1
DB_NAME=${PG_DB_NAME}
DB_USER=${PG_DB_USER}
DB_PASSWORD=${PG_PASSWORD}
DB_HOST=${PG_DB_HOST}
DB_PORT=${PG_DB_PORT}
ENVEOF
  chmod 600 "${ENV_FILE}" || true
  echo "[DB] Wrote ${ENV_FILE} (PostgreSQL database=${PG_DB_NAME} user=${PG_DB_USER})."

  if [ -n "${ANTIBOT_SUPERUSER_PASSWORD:-}" ]; then
    SU_PASS="${ANTIBOT_SUPERUSER_PASSWORD}"
    echo "[auth] Using Django superuser password from environment (ANTIBOT_SUPERUSER_PASSWORD)."
  else
    SU_PASS="$(openssl rand -base64 32 | tr -d '\n')"
    CREDS_FILE="/root/antibot_superuser_credentials.txt"
    umask 077
    {
      echo "# Generated by install.sh — delete after storing credentials securely."
      echo "ANTIBOT_SUPERUSER_USERNAME=${SU_USER}"
      echo "ANTIBOT_SUPERUSER_PASSWORD=${SU_PASS}"
      echo "ANTIBOT_SUPERUSER_EMAIL=${SU_EMAIL}"
    } > "${CREDS_FILE}"
    chmod 600 "${CREDS_FILE}" || true
    echo "[auth] Generated Django superuser password; read with: sudo cat ${CREDS_FILE}"
  fi

  echo "[5/8] migrate + superuser..."
  cd "${INSTALL_DIR}"
  "${VENV_PATH}/bin/python" "${INSTALL_DIR}/manage.py" migrate
  DJANGO_SUPERUSER_USERNAME="${SU_USER}" \
  DJANGO_SUPERUSER_EMAIL="${SU_EMAIL}" \
  DJANGO_SUPERUSER_PASSWORD="${SU_PASS}" \
  "${VENV_PATH}/bin/python" "${INSTALL_DIR}/manage.py" createsuperuser --noinput || true

  echo "[collectstatic] Collecting static files..."
  "${VENV_PATH}/bin/python" "${INSTALL_DIR}/manage.py" collectstatic --noinput || \
    echo "[warn] collectstatic failed — check logs and STATIC_ROOT in settings."

  echo "[6/8] Creating systemd unit (Gunicorn)..."
  sudo tee /etc/systemd/system/${SERVICE_NAME}.service >/dev/null <<EOF
[Unit]
Description=${SERVICE_NAME} Django (Gunicorn)
After=network.target postgresql.service redis-server.service
Wants=postgresql.service redis-server.service

[Service]
User=$(whoami)
WorkingDirectory=${INSTALL_DIR}
Environment=PATH=${VENV_PATH}/bin
EnvironmentFile=-${INSTALL_DIR}/.env
ExecStart=${VENV_PATH}/bin/gunicorn --bind ${BIND_ADDR} --workers 2 --timeout 120 analytics_project.wsgi:application
Restart=on-failure

[Install]
WantedBy=multi-user.target
EOF

  sudo systemctl daemon-reload
  if ! systemctl enable --now "${SERVICE_NAME}"; then
    echo "[warn] systemctl enable --now failed. Check: journalctl -u ${SERVICE_NAME} -n 40 --no-pager"
  fi

  echo "[7/8] Configuring cron (Telegram backup)..."
  CRON_CMD="*/10 * * * * cd ${INSTALL_DIR} && set -a && . ${INSTALL_DIR}/.env && set +a && ${VENV_PATH}/bin/python manage.py run_telegram_backup >> ${INSTALL_DIR}/backup.log 2>&1"

  ( crontab -l 2>/dev/null | grep -v "run_telegram_backup" || true; echo "${CRON_CMD}" ) | crontab - || \
    echo "[warn] crontab update failed"

  echo "Cron job added:"
  crontab -l 2>/dev/null || true

  echo "[8/8] Service status:"
  systemctl status "${SERVICE_NAME}" --no-pager || true

  echo "Install finished."
  _antibot_print_access_info
  echo "Deploy path: ${INSTALL_DIR} — use uninstall.sh to remove this install only."
  echo "Password reset: cd ${INSTALL_DIR} && source env/bin/activate && set -a && . .env && set +a && python manage.py changepassword ${SU_USER}"

  exit 0
fi

# =============================================================================
# Bootstrap: clone repo, then run this script again from disk with --inner
# =============================================================================

if [ "${EUID:-$(id -u)}" -ne 0 ]; then
  echo "Run as root: sudo bash install.sh"
  exit 1
fi

REPO_URL="${ANTIBOT_REPO_URL:-https://github.com/nobodycp/antibot.git}"
INSTALL_DIR="${ANTIBOT_INSTALL_DIR:-/opt/antibot}"
SERVICE_NAME="antibot"

echo "=========================================="
echo " antibot install (single file: install.sh)"
echo " Repo URL:     ${REPO_URL}"
echo " Install path: ${INSTALL_DIR}"
echo "=========================================="

case "$(pwd -P)/" in
  "${INSTALL_DIR}/"*)
    echo "ERROR: Do not run install.sh from inside ${INSTALL_DIR}."
    echo "Use: curl -fsSL …/install.sh | sudo bash   OR   cd ~ && sudo bash /path/to/install.sh"
    exit 1
    ;;
esac

echo "[bootstrap] Stopping previous service and removing old ${INSTALL_DIR}..."
systemctl stop "${SERVICE_NAME}" 2>/dev/null || true
systemctl disable "${SERVICE_NAME}" 2>/dev/null || true
rm -f "/etc/systemd/system/${SERVICE_NAME}.service"
systemctl daemon-reload

rm -rf "${INSTALL_DIR}"
mkdir -p "$(dirname "${INSTALL_DIR}")"

echo "[bootstrap] git clone → ${INSTALL_DIR}"
if ! git clone --depth 1 "${REPO_URL}" "${INSTALL_DIR}"; then
  echo "ERROR: git clone failed. Check network and ANTIBOT_REPO_URL."
  exit 1
fi

DISK_INSTALL="${INSTALL_DIR}/install.sh"
if [ ! -f "${DISK_INSTALL}" ]; then
  echo "ERROR: Missing ${DISK_INSTALL} after clone."
  exit 1
fi

chmod +x "${DISK_INSTALL}"

echo "[bootstrap] Running ${DISK_INSTALL} --inner (same file; credentials shown at end)..."
export ANTIBOT_INSTALL_DIR="${INSTALL_DIR}"
exec bash "${DISK_INSTALL}" --inner
