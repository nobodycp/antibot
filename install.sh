#!/usr/bin/env bash
# install.sh - idempotent installer for antibot
# شغّله بـ: bash install.sh
set -Eeuo pipefail

### قابل للتعديل:
REPO_URL="https://github.com/nobodycp/antibot.git"
INSTALL_DIR="/opt/antibot"
VENV_NAME="env"                # اسم مجلد الـ venv داخل INSTALL_DIR
SERVICE_NAME="antibot"
USE_GUNICORN="false"           # "true" لو حاب تستخدم gunicorn (أفضل للإنتاج)
BIND_ADDR="0.0.0.0:8000"       # عنوان التشغيل
DJANGO_SUPERUSER="admin"
DJANGO_SUPERPASS="adminpass"
DJANGO_SUPEREMAIL="admin@example.com"

# تأكد من وجود bash
if [ -z "$(command -v bash)" ]; then
  echo "خطأ: هذا السكربت يحتاج bash."
  exit 1
fi

echo "=== بدء التثبيت ==="

# 1) تحديث النظام وتثبيت المتطلبات الأساسية
echo "[1/8] تحديث النظام وتثبيت python/git..."
sudo apt update
sudo apt install -y python3 python3-venv python3-pip git || true

# 2) استنساخ الريبو في مسار ثابت (حذف القديم إذا لزم)
echo "[2/8] استنساخ المشروع إلى ${INSTALL_DIR}..."
sudo rm -rf "${INSTALL_DIR}"
sudo mkdir -p "$(dirname "${INSTALL_DIR}")"
sudo chown -R "$USER":"$USER" "$(dirname "${INSTALL_DIR}")"
git clone "${REPO_URL}" "${INSTALL_DIR}"

cd "${INSTALL_DIR}"

# 3) إنشاء virtualenv وتفعيلها
VENV_PATH="${INSTALL_DIR}/${VENV_NAME}"
echo "[3/8] إنشاء virtualenv في ${VENV_PATH}..."
python3 -m venv "${VENV_PATH}"
# shellcheck disable=SC1091
source "${VENV_PATH}/bin/activate"

echo "[4/8] تثبيت متطلبات Python..."
pip install --upgrade pip
if [ -f "requirements.txt" ]; then
  pip install -r requirements.txt
fi

# لو اخترت gunicorn تأكد من تثبيته
if [ "${USE_GUNICORN}" = "true" ]; then
  pip install gunicorn
fi

# 4) نبّه: اذا settings.py يحتاج متغيرات بيئية، سكربت لا يضبطها تلقائياً
# 5) تشغيل الترحيلات
echo "[5/8] تشغيل Django migrations..."
PYTHONPATH="${INSTALL_DIR}" DJANGO_SETTINGS_MODULE="$(basename "${INSTALL_DIR}") .settings" || true
python "${INSTALL_DIR}/manage.py" migrate

# 6) جمع static لو إعداد STATIC_ROOT معرف
echo "[6/8] محاولة جمع static (إن وُجد STATIC_ROOT) ..."
# نجرب جمع الستاتيك - لو إعداد STATIC_ROOT غير موجود سيفشل ويتجاهل
if python - <<'PY' 2>/dev/null; import importlib,sys; sys.path.insert(0,"${INSTALL_DIR}"); \
mod = importlib.import_module("manage"); print("ok") if True else None; PY; then
  # حاول collectstatic ولكن لا نفشل لو لم يُعرف STATIC_ROOT
  python "${INSTALL_DIR}/manage.py" collectstatic --noinput || echo "collectstatic فشل — تأكد من STATIC_ROOT إن احتجت"
else
  echo "تخطّي collectstatic — لا يمكن استيراد المشروع الآن"
fi

# 7) إنشاء superuser غير تكراري
echo "[7/8] إنشاء superuser (لو غير موجود)..."
python "${INSTALL_DIR}/manage.py" shell <<PYCODE || true
from django.contrib.auth import get_user_model
User = get_user_model()
if not User.objects.filter(username="${DJANGO_SUPERUSER}").exists():
    User.objects.create_superuser("${DJANGO_SUPERUSER}", "${DJANGO_SUPEREMAIL}", "${DJANGO_SUPERPASS}")
    print("superuser created")
else:
    print("superuser already exists")
PYCODE

# 8) إنشاء ملف systemd بطريقة آمنة
echo "[8/8] إنشاء ملف systemd وتشغيل الخدمة..."
SERVICE_FILE="/etc/systemd/system/${SERVICE_NAME}.service"
CURRENT_USER="$(whoami)"
PROJECT_PKG="$(basename "${INSTALL_DIR}")"  # افتراض: اسم الحزمة يساوي اسم المجلد

# اختَر ExecStart بناءً على اختيارك (runserver أم gunicorn)
if [ "${USE_GUNICORN}" = "true" ]; then
  EXEC_START="${VENV_PATH}/bin/gunicorn ${PROJECT_PKG}.wsgi:application --bind ${BIND_ADDR} --workers 3"
else
  EXEC_START="${VENV_PATH}/bin/python ${INSTALL_DIR}/manage.py runserver ${BIND_ADDR}"
fi

sudo tee "${SERVICE_FILE}" >/dev/null <<EOF
[Unit]
Description=${SERVICE_NAME} Django Service
After=network.target

[Service]
User=${CURRENT_USER}
WorkingDirectory=${INSTALL_DIR}
Environment=PATH=${VENV_PATH}/bin
Environment=DJANGO_SETTINGS_MODULE=${PROJECT_PKG}.settings
ExecStart=${EXEC_START}
Restart=on-failure

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable --now "${SERVICE_NAME}"

echo "=== انتهى التثبيت ==="
systemctl status "${SERVICE_NAME}" --no-pager || true

# نهاية السكربت
