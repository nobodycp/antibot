import os
import tempfile
import requests

from django.core.management import BaseCommand, call_command
from django.utils import timezone

from dashboard.models import TelegramBackupSettings


class Command(BaseCommand):
    help = "Run Telegram database backup if due"

    def handle(self, *args, **options):
        settings_obj = TelegramBackupSettings.objects.first()

        if not settings_obj:
            self.stdout.write(self.style.ERROR("No TelegramBackupSettings found"))
            return

        if not settings_obj.is_enabled:
            self.stdout.write(self.style.WARNING("Backup is disabled"))
            return

        if not settings_obj.bot_token or not settings_obj.chat_id:
            self.stdout.write(self.style.ERROR("Bot token or chat id missing"))
            return

        if not settings_obj.backup_database:
            self.stdout.write(self.style.WARNING("Database backup is disabled"))
            return

        now = timezone.now()

        if settings_obj.last_success_at:
            next_run = settings_obj.last_success_at + timezone.timedelta(days=settings_obj.interval_days)
            if now < next_run:
                self.stdout.write(
                    self.style.WARNING(
                        f"Backup is not due yet. Next run: {next_run}"
                    )
                )
                return

        backup_path = None

        try:
            settings_obj.last_run_at = now
            settings_obj.last_error = ""
            settings_obj.save(update_fields=["last_run_at", "last_error"])

            with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tmp:
                backup_path = tmp.name

            call_command("dumpdata", output=backup_path, indent=2)

            url = f"https://api.telegram.org/bot{settings_obj.bot_token}/sendDocument"

            with open(backup_path, "rb") as f:
                res = requests.post(
                    url,
                    data={
                        "chat_id": settings_obj.chat_id,
                        "caption": "✅ Scheduled Antibot database backup"
                    },
                    files={"document": f},
                    timeout=60
                )

            if res.ok and res.json().get("ok"):
                settings_obj.last_success_at = timezone.now()
                settings_obj.last_error = ""
                settings_obj.save(update_fields=["last_success_at", "last_error"])
                self.stdout.write(self.style.SUCCESS("Backup sent successfully"))
            else:
                settings_obj.last_error = res.text
                settings_obj.save(update_fields=["last_error"])
                self.stdout.write(self.style.ERROR(res.text))

        except Exception as e:
            settings_obj.last_error = str(e)
            settings_obj.save(update_fields=["last_error"])
            self.stdout.write(self.style.ERROR(str(e)))

        finally:
            if backup_path and os.path.exists(backup_path):
                os.remove(backup_path)