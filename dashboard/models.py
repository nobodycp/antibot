# Create your models here.
import hashlib
import secrets

from django.conf import settings
from django.db import models
from django.contrib.auth.models import User


def _new_urlsafe_api_key():
    return secrets.token_urlsafe(32)

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

class UserProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    avatar = models.ImageField(upload_to='avatars/', blank=True, null=True)

    def __str__(self):
        return self.user.username


class UserAPIKey(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="api_key_row",
    )
    api_key = models.CharField(
        max_length=128,
        unique=True,
        db_index=True,
        default=_new_urlsafe_api_key,
    )
    # SHA-256 hex of api_key for indexed lookup (plaintext api_key remains for UI; remove later).
    api_key_lookup_hash = models.CharField(
        max_length=64,
        unique=True,
        db_index=True,
        editable=False,
        default="",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "User API key"
        verbose_name_plural = "User API keys"

    def __str__(self):
        return f"API key for {self.user_id}"

    def save(self, *args, **kwargs):
        if self.api_key:
            self.api_key_lookup_hash = hashlib.sha256(
                self.api_key.encode("utf-8")
            ).hexdigest()
        super().save(*args, **kwargs)

    def regenerate(self):
        for _ in range(10):
            candidate = secrets.token_urlsafe(32)
            if UserAPIKey.objects.filter(api_key=candidate).exclude(pk=self.pk).exists():
                continue
            self.api_key = candidate
            self.save()
            return
        raise RuntimeError("Could not generate a unique API key")