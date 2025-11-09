#!/usr/bin/env bash
set -Eeuo pipefail

APP_NAME="antibot"
PROJECT_DIR="/opt/${APP_NAME}"
REPO_URL="https://github.com/nobodycp/antibot.git"
VENV_DIR="${PROJECT_DIR}/env"
SERVICE_FILE="/etc/systemd/system/${APP_NAME}.service"
DJANGO_SETTINGS="${APP_NAME}.settings"
BIND_ADDR="0.0.0.0:8000"

echo "[+] Updating system packages..."
sudo apt update
sudo apt upgrade -y

echo "[+] Installing Python, pip, and Git..."
sudo apt install -y python3 python3-venv python3-pip git

echo "[+] Cloning the project into ${PROJECT_DIR}..."
sudo rm -rf "${PROJECT_DIR}"
sudo mkdir -p "${PROJECT_DIR}"
sudo chown -R "$USER":"$USER" "${PROJECT_DIR}"
git clone "${REPO_URL}" "${PROJECT_DIR}"
cd "${PROJECT_DIR}"

echo "[+] Creating virtual environment..."
python3 -m venv "${VENV_DIR}"
# shellcheck disable=SC1091
source "${VENV_DIR}/bin/activate"

echo "[+] Installing Python dependencies..."
pip install --upgrade pip
pip install -r requirements.txt
# نضمن وجود gunicorn
pip install gunicorn

echo "[+] Running Django migrations..."
python manage.py migrate

echo "[+] Collecting static files..."
python manage.py collectstatic --noinput || true

echo "[+] Creating Django superuser (admin:adminpass)..."
python <<'PYCODE'
import os, django
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "antibot.settings")
django.setup()
from django.contrib.auth import get_user_model
User = get_user_model()
if not User.objects.filter(username="admin").exists():
    User.objects.create_superuser("admin", "admin@example.com", "adminpass")
PYCODE

echo "[+] Creating systemd service file..."
sudo tee "${SERVICE_FILE}" >/dev/null <<EOF
[Unit]
Description=${APP_NAME} Django (gunicorn)
After=network.target

[Service]
User=www-data
Group=www-data
WorkingDirectory=${PROJECT_DIR}
Environment=DJANGO_SETTINGS_MODULE=${DJANGO_SETTINGS}
Environment=PATH=${VENV_DIR}/bin
ExecStart=${VENV_DIR}/bin/gunicorn ${APP_NAME}.wsgi:application --bind ${BIND_ADDR} --workers 3
Restart=on-failure

[Install]
WantedBy=multi-user.target
EOF

echo "[+] Reloading systemd daemon and enabling service..."
sudo systemctl daemon-reload
sudo systemctl enable --now "${APP_NAME}"

echo "[✓] ${APP_NAME} service is now running and will auto-start on reboot."
systemctl --no-pager status "${APP_NAME}" || true
