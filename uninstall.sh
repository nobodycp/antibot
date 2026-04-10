#!/usr/bin/env bash
# Uninstall antibot from this server (Debian/Ubuntu).
# Removes: systemd unit, /opt/antibot, telegram-backup cron lines, PostgreSQL DB+role, Redis DB 1 flush.
# Does NOT remove: postgresql, redis-server, or other system packages (may be used by other apps).
#
# Only deletes the deployed copy at INSTALL_DIR (default /opt/antibot).
# Your git clone elsewhere (e.g. ~/antibot) is NOT removed — delete it manually if you want.
#
# Usage:
#   sudo bash uninstall.sh           # asks for confirmation
#   sudo bash uninstall.sh --yes     # non-interactive (CI / automation)
#
# Override install path: ANTIBOT_INSTALL_DIR=/path sudo -E bash uninstall.sh --yes
#
set -eo pipefail

INSTALL_DIR="${ANTIBOT_INSTALL_DIR:-/opt/antibot}"
SERVICE_NAME="antibot"
PG_DB_NAME="antibot"
PG_DB_USER="antibot"
CREDS_FILE="/root/antibot_superuser_credentials.txt"

SKIP_CONFIRM=false
for arg in "$@"; do
  case "$arg" in
    -y|--yes) SKIP_CONFIRM=true ;;
  esac
done

if [ "${EUID:-$(id -u)}" -ne 0 ]; then
  echo "يجب التشغيل كـ root: sudo bash uninstall.sh"
  echo "Run as root: sudo bash uninstall.sh"
  exit 1
fi

echo "This will remove the antibot deployment:"
echo "  - systemd service: ${SERVICE_NAME}"
echo "  - directory: ${INSTALL_DIR}"
echo "  - crontab lines matching: run_telegram_backup (root's crontab when using sudo)"
echo "  - PostgreSQL: DROP DATABASE ${PG_DB_NAME}; DROP ROLE ${PG_DB_USER}"
echo "  - Redis: FLUSHDB on logical database 1 (default REDIS_URL .../1)"
echo "  - file: ${CREDS_FILE} (if present)"
echo "  - NOT removed: apt packages; NOT removed: your git clone outside ${INSTALL_DIR}"
echo ""

if ! $SKIP_CONFIRM; then
  read -r -p "Type YES to continue: " reply
  if [ "${reply}" != "YES" ]; then
    echo "Aborted."
    exit 1
  fi
fi

echo "[1/7] Stopping and removing systemd unit..."
systemctl stop "${SERVICE_NAME}" 2>/dev/null || true
systemctl disable "${SERVICE_NAME}" 2>/dev/null || true
rm -f "/etc/systemd/system/${SERVICE_NAME}.service"
systemctl daemon-reload
systemctl reset-failed "${SERVICE_NAME}" 2>/dev/null || true

echo "[2/7] Removing cron jobs (run_telegram_backup)..."
if command -v crontab >/dev/null 2>&1 && crontab -l >/dev/null 2>&1; then
  _cron_new="$(crontab -l 2>/dev/null | { grep -v "run_telegram_backup" || true; })"
  if [ -n "${_cron_new}" ]; then
    echo "${_cron_new}" | crontab -
  else
    crontab -r 2>/dev/null || true
  fi
fi

echo "[3/7] Stopping leftover Gunicorn workers (this app only)..."
# Match install.sh venv path so we do not kill unrelated gunicorn instances.
if [ -n "${INSTALL_DIR}" ] && [ "${INSTALL_DIR}" != "/" ]; then
  pkill -f "${INSTALL_DIR}/env/bin/gunicorn" 2>/dev/null || true
fi
sleep 2

echo "[4/7] Removing project directory: ${INSTALL_DIR}"
if [ -e "${INSTALL_DIR}" ]; then
  chmod -R u+rwX "${INSTALL_DIR}" 2>/dev/null || true
  if ! command rm -rf -- "${INSTALL_DIR}"; then
    echo "ERROR: failed to remove ${INSTALL_DIR}. Try: sudo lsof +D ${INSTALL_DIR}"
    echo "خطأ: تعذر حذف المجلد. تحقق من عمليات تستخدم الملفات."
    exit 1
  fi
fi
if [ -e "${INSTALL_DIR}" ]; then
  echo "ERROR: ${INSTALL_DIR} still exists after rm -rf."
  echo "خطأ: المجلد ما زال موجوداً بعد الحذف."
  exit 1
fi
echo "  Removed ${INSTALL_DIR} OK."

echo "[5/7] Flushing Redis database 1..."
if command -v redis-cli >/dev/null 2>&1; then
  redis-cli -n 1 FLUSHDB >/dev/null 2>&1 && echo "  Redis DB 1 flushed." || echo "  (Redis flush skipped or failed — check redis-server.)"
else
  echo "  redis-cli not found; skip Redis flush."
fi

echo "[6/7] Dropping PostgreSQL database and role..."
if command -v psql >/dev/null 2>&1 && systemctl is-active --quiet postgresql 2>/dev/null; then
  sudo -u postgres psql -v ON_ERROR_STOP=1 -d postgres -c \
    "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = '${PG_DB_NAME}' AND pid <> pg_backend_pid();" \
    2>/dev/null || true
  sudo -u postgres psql -v ON_ERROR_STOP=1 -d postgres -c "DROP DATABASE IF EXISTS ${PG_DB_NAME};" 2>/dev/null || true
  sudo -u postgres psql -v ON_ERROR_STOP=1 -d postgres -c "DROP ROLE IF EXISTS ${PG_DB_USER};" 2>/dev/null || true
  echo "  PostgreSQL cleanup attempted."
else
  echo "  PostgreSQL not active or psql missing; skip DB drop (remove DB/role manually if needed)."
fi

echo "[7/7] Removing superuser credentials file..."
rm -f "${CREDS_FILE}"

echo "Done / تم."
echo "Antibot uninstall finished. System packages (postgresql, redis-server, etc.) were left installed."
echo "Note: if you cloned the repo under ~/antibot (or elsewhere), remove that folder yourself if needed."
