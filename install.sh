#!/usr/bin/env bash
set -Eeuo pipefail

REPO_URL="https://github.com/nobodycp/antibot.git"
INSTALL_DIR="/opt/antibot"
VENV_PATH="${INSTALL_DIR}/env"
SERVICE_NAME="antibot"
BIND_ADDR="0.0.0.0:8000"
DJANGO_SUPERUSER="admin"
DJANGO_SUPERPASS="adminpass"
DJANGO_SUPEREMAIL="admin@example.com"

echo "[1/6] تثبيت المتطلبات..."
sudo apt update
sudo apt install -y python3 python3-venv python3-pip git

echo "[2/6] إعادة استنساخ المشروع في ${INSTALL_DIR}..."
cd /
sudo systemctl stop "${SERVICE_NAME}" 2>/dev/null || true
sudo systemctl disable "${SERVICE_NAME}" 2>/dev/null || true
sudo rm -f /etc/systemd/system/${SERVICE_NAME}.service
sudo systemctl daemon-reload
sudo rm -rf "${INSTALL_DIR}"
sudo git clone "${REPO_URL}" "${INSTALL_DIR}"

echo "[3/6] إنشاء وتفعيل venv وتثبيت الاعتمادات..."
python3 -m venv "${VENV_PATH}"
"${VENV_PATH}/bin/pip" install --upgrade pip
[ -f "${INSTALL_DIR}/requirements.txt" ] && \
  "${VENV_PATH}/bin/pip" install -r "${INSTALL_DIR}/requirements.txt"

echo "[4/6] ترحيلات وإنشاء سوبر يوزر..."
"${VENV_PATH}/bin/python" "${INSTALL_DIR}/manage.py" migrate
DJANGO_SUPERUSER_USERNAME="${DJANGO_SUPERUSER}" \
DJANGO_SUPERUSER_EMAIL="${DJANGO_SUPEREMAIL}" \
DJANGO_SUPERUSER_PASSWORD="${DJANGO_SUPERPASS}" \
"${VENV_PATH}/bin/python" "${INSTALL_DIR}/manage.py" createsuperuser --noinput || true

# اختياري: نجرب collectstatic، ولو فشل نتخطّاه
echo "[اختياري] collectstatic..."
"${VENV_PATH}/bin/python" "${INSTALL_DIR}/manage.py" collectstatic --noinput || \
  echo "تخطّي collectstatic (ربما STATIC_ROOT غير مُعرّف) — لا مشكلة."

echo "[5/6] إنشاء خدمة systemd وتشغيلها..."
sudo tee /etc/systemd/system/${SERVICE_NAME}.service >/dev/null <<EOF
[Unit]
Description=${SERVICE_NAME} Django Service
After=network.target

[Service]
User=$(whoami)
WorkingDirectory=${INSTALL_DIR}
Environment=PATH=${VENV_PATH}/bin
# manage.py يضبط DJANGO_SETTINGS_MODULE داخليًا؛ لا حاجة لضبطه هنا
ExecStart=${VENV_PATH}/bin/python ${INSTALL_DIR}/manage.py runserver ${BIND_ADDR}
Restart=on-failure

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable --now ${SERVICE_NAME}

echo "[6/6] الحالة:"
systemctl status ${SERVICE_NAME} --no-pager || true
