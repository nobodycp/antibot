# 1) اكتب سكربت جديد مكان القديم
sudo tee /opt/antibot/install.sh >/dev/null <<'BASH'
#!/usr/bin/env bash
set -e

REPO_URL="https://github.com/nobodycp/antibot.git"
INSTALL_DIR="/opt/antibot"
VENV_PATH="${INSTALL_DIR}/env"
SERVICE_NAME="antibot"
BIND_ADDR="0.0.0.0:8000"
DJANGO_SUPERUSER="admin"
DJANGO_SUPERPASS="adminpass"
DJANGO_SUPEREMAIL="admin@example.com"

echo "[1/7] تثبيت المتطلبات..."
sudo apt update
sudo apt install -y python3 python3-venv python3-pip git

echo "[2/7] تنظيف ثم استنساخ المشروع..."
sudo systemctl stop "${SERVICE_NAME}" 2>/dev/null || true
sudo systemctl disable "${SERVICE_NAME}" 2>/dev/null || true
sudo rm -f /etc/systemd/system/${SERVICE_NAME}.service
sudo systemctl daemon-reload
sudo rm -rf "${INSTALL_DIR}"
sudo git clone "${REPO_URL}" "${INSTALL_DIR}"

echo "[3/7] إنشاء وتحديث venv..."
python3 -m venv "${VENV_PATH}"
"${VENV_PATH}/bin/pip" install --upgrade pip
[ -f "${INSTALL_DIR}/requirements.txt" ] && \
  "${VENV_PATH}/bin/pip" install -r "${INSTALL_DIR}/requirements.txt"

echo "[4/7] migrate + superuser..."
"${VENV_PATH}/bin/python" "${INSTALL_DIR}/manage.py" migrate
DJANGO_SUPERUSER_USERNAME="${DJANGO_SUPERUSER}" \
DJANGO_SUPERUSER_EMAIL="${DJANGO_SUPEREMAIL}" \
DJANGO_SUPERUSER_PASSWORD="${DJANGO_SUPERPASS}" \
"${VENV_PATH}/bin/python" "${INSTALL_DIR}/manage.py" createsuperuser --noinput || true

echo "[اختياري] collectstatic (يتخطى عند غياب STATIC_ROOT)..."
"${VENV_PATH}/bin/python" "${INSTALL_DIR}/manage.py" collectstatic --noinput || \
  echo "تخطّي collectstatic — غالباً STATIC_ROOT غير مُعرّف، وهذا طبيعي."

echo "[5/7] إنشاء خدمة systemd وتشغيلها (runserver)..."
sudo tee /etc/systemd/system/${SERVICE_NAME}.service >/dev/null <<EOF
[Unit]
Description=${SERVICE_NAME} Django Service
After=network.target

[Service]
User=$(whoami)
WorkingDirectory=${INSTALL_DIR}
Environment=PATH=${VENV_PATH}/bin
ExecStart=${VENV_PATH}/bin/python ${INSTALL_DIR}/manage.py runserver ${BIND_ADDR}
Restart=on-failure

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable --now ${SERVICE_NAME}

echo "[6/7] إعداد cron للباك اب التلقائي..."
CRON_CMD="*/10 * * * * cd ${INSTALL_DIR} && ${VENV_PATH}/bin/python manage.py run_telegram_backup >> ${INSTALL_DIR}/backup.log 2>&1"

(crontab -l 2>/dev/null | grep -v "run_telegram_backup"; echo "$CRON_CMD") | crontab -

echo "Cron job added:"
crontab -l

echo "[7/7] الحالة:"
systemctl status ${SERVICE_NAME} --no-pager || true
BASH

# 2) شغّل السكربت الجديد
sudo chmod +x /opt/antibot/install.sh
bash /opt/antibot/install.sh