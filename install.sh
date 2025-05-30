#!/bin/bash

echo "[+] Updating system packages..."
sudo apt update && sudo apt upgrade -y

echo "[+] Installing Python, pip, and Git..."
sudo apt install python3 python3-pip python3-venv git -y

echo "[+] Cloning the project from GitHub..."
git clone https://github.com/nobodycp/antibot.git
cd antibot

echo "[+] Creating virtual environment..."
python3 -m venv env
source env/bin/activate

echo "[+] Installing Python dependencies..."
pip install --upgrade pip
pip install -r requirements.txt

echo "[+] Running Django migrations..."
python manage.py migrate

echo "[+] Creating Django superuser (admin:adminpass)..."
python manage.py shell <<EOF
from django.contrib.auth import get_user_model
User = get_user_model()
if not User.objects.filter(username='admin').exists():
    User.objects.create_superuser('admin', 'admin@example.com', 'adminpass')
EOF

echo "[+] Creating systemd service file..."

SERVICE_FILE=/etc/systemd/system/antibot.service

sudo bash -c "cat > \$SERVICE_FILE" <<EOF
[Unit]
Description=AntiBot Django Service
After=network.target

[Service]
User=$USER
WorkingDirectory=$(pwd)
ExecStart=$(pwd)/env/bin/python manage.py runserver 0.0.0.0:8000
Restart=always

[Install]
WantedBy=multi-user.target
EOF

echo "[+] Reloading systemd daemon and enabling service..."
sudo systemctl daemon-reexec
sudo systemctl daemon-reload
sudo systemctl enable antibot
sudo systemctl start antibot

echo "[✓] AntiBot service is now running and will auto-start on reboot."
