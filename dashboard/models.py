# Create your models here.
from django.db import models

class TelegramBackupSettings(models.Model):
    name = models.CharField(max_length=100, default="Main Backup Settings")
    bot_token = models.CharField(max_length=255, blank=True, default="")
    chat_id = models.CharField(max_length=100, blank=True, default="")

    is_enabled = models.BooleanField(default=False)
    backup_database = models.BooleanField(default=True)
    backup_media = models.BooleanField(default=False)

    interval_days = models.PositiveIntegerField(default=1)

    last_run_at = models.DateTimeField(null=True, blank=True)
    last_success_at = models.DateTimeField(null=True, blank=True)
    last_error = models.TextField(blank=True, default="")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name