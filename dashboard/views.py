from django.contrib.auth.decorators import login_required
from .models import TelegramBackupSettings
from django.contrib import messages
from django.shortcuts import render, redirect
from django.http import HttpResponse
import requests
import tempfile
from django.core.management import call_command
import os


@login_required
def dashboard_home(request):
    return render(request, 'home.html')


@login_required
def telegram_backup_settings_view(request):
    settings_obj, _ = TelegramBackupSettings.objects.get_or_create(id=1)

    if request.method == "POST":
        settings_obj.bot_token = request.POST.get("bot_token", "").strip()
        settings_obj.chat_id = request.POST.get("chat_id", "").strip()
        settings_obj.is_enabled = bool(request.POST.get("is_enabled"))
        settings_obj.backup_database = bool(request.POST.get("backup_database"))
        settings_obj.backup_media = bool(request.POST.get("backup_media"))

        interval = request.POST.get("interval_days", "1").strip()
        try:
            settings_obj.interval_days = max(1, int(interval))
        except ValueError:
            settings_obj.interval_days = 1

        settings_obj.save()
        messages.success(request, "✅ Settings saved successfully.")
        return redirect("dashboard:telegram_backup_settings")

    return render(request, "admin_settings.html", {
        "settings_obj": settings_obj
    })

@login_required
def telegram_test_backup(request):
    settings_obj = TelegramBackupSettings.objects.first()

    if not settings_obj or not settings_obj.bot_token or not settings_obj.chat_id:
        messages.error(request, "Telegram settings not configured")
        return redirect("dashboard:telegram_backup_settings")

    url = f"https://api.telegram.org/bot{settings_obj.bot_token}/sendMessage"

    try:
        res = requests.post(url, data={
            "chat_id": settings_obj.chat_id,
            "text": "✅ Test backup message from antibot"
        }, timeout=20)

        data = res.json()

        if res.ok and data.get("ok"):
            messages.success(request, "✅ Test message sent successfully")
        else:
            messages.error(request, f"❌ Telegram error: {data}")

    except Exception as e:
        messages.error(request, f"❌ Request failed: {str(e)}")

    return redirect("dashboard:telegram_backup_settings")
@login_required
def telegram_send_db_backup(request):
    settings_obj = TelegramBackupSettings.objects.first()

    if not settings_obj or not settings_obj.bot_token or not settings_obj.chat_id:
        messages.error(request, "Telegram settings not configured")
        return redirect("dashboard:telegram_backup_settings")

    backup_path = None

    try:
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tmp:
            backup_path = tmp.name

        call_command("dumpdata", output=backup_path, indent=2)

        url = f"https://api.telegram.org/bot{settings_obj.bot_token}/sendDocument"

        with open(backup_path, "rb") as f:
            res = requests.post(
                url,
                data={
                    "chat_id": settings_obj.chat_id,
                    "caption": "✅ Antibot database backup"
                },
                files={"document": f},
                timeout=60
            )

        data = res.json()

        if res.ok and data.get("ok"):
            messages.success(request, "✅ Backup sent successfully")
        else:
            messages.error(request, f"❌ Telegram error: {data}")

    except Exception as e:
        messages.error(request, f"❌ Backup failed: {str(e)}")

    finally:
        if backup_path and os.path.exists(backup_path):
            os.remove(backup_path)

    return redirect("dashboard:telegram_backup_settings")