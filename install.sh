#!/usr/bin/env bash
#
# antibot — server bootstrap (Debian/Ubuntu)
#
# Clones the repo into a single fixed directory (default /opt/antibot), then runs
# scripts/install-inner.sh. You do NOT need a second copy under ~/antibot for production.
#
# Usage:
#   sudo bash install.sh
#   sudo ANTIBOT_INSTALL_DIR=/srv/antibot bash install.sh
#   sudo ANTIBOT_REPO_URL=https://github.com/you/fork.git bash install.sh
#
# One-liner (uses GitHub default branch):
#   curl -fsSL https://raw.githubusercontent.com/nobodycp/antibot/main/install.sh | sudo bash
#
set -eo pipefail

if [ "${EUID:-$(id -u)}" -ne 0 ]; then
  echo "شغّل كـ root: sudo bash install.sh"
  echo "Run as root: sudo bash install.sh"
  exit 1
fi

REPO_URL="${ANTIBOT_REPO_URL:-https://github.com/nobodycp/antibot.git}"
INSTALL_DIR="${ANTIBOT_INSTALL_DIR:-/opt/antibot}"
SERVICE_NAME="antibot"

echo "=========================================="
echo " antibot bootstrap"
echo " Repo URL:     ${REPO_URL}"
echo " Install path: ${INSTALL_DIR}  (fixed — same path uninstall.sh removes)"
echo "=========================================="

# Never run from inside INSTALL_DIR: rm -rf would delete the script mid-flight.
case "$(pwd -P)/" in
  "${INSTALL_DIR}/"*)
    echo "ERROR: Do not run install.sh from inside ${INSTALL_DIR}."
    echo "Use: curl -fsSL …/install.sh | sudo bash   OR   cd ~ && sudo bash /path/to/install.sh"
    exit 1
    ;;
esac

echo "[0/2] Stopping previous service and removing old ${INSTALL_DIR}..."
systemctl stop "${SERVICE_NAME}" 2>/dev/null || true
systemctl disable "${SERVICE_NAME}" 2>/dev/null || true
rm -f "/etc/systemd/system/${SERVICE_NAME}.service"
systemctl daemon-reload

rm -rf "${INSTALL_DIR}"
mkdir -p "$(dirname "${INSTALL_DIR}")"

echo "[1/2] git clone → ${INSTALL_DIR}"
if ! git clone --depth 1 "${REPO_URL}" "${INSTALL_DIR}"; then
  echo "ERROR: git clone failed. Check network and ANTIBOT_REPO_URL."
  exit 1
fi

INNER="${INSTALL_DIR}/scripts/install-inner.sh"
if [ ! -f "${INNER}" ]; then
  echo "ERROR: Missing ${INNER} after clone."
  exit 1
fi

chmod +x "${INNER}"

echo "[2/2] Running install-inner.sh..."
export ANTIBOT_INSTALL_DIR="${INSTALL_DIR}"
exec bash "${INNER}"
