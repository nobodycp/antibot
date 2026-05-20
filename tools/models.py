import os
from django.db import models
from django.conf import settings  # للوصول إلى MEDIA_ROOT

def overwrite_upload_path(instance, filename):
    upload_path = os.path.join('zips', filename)
    full_path = os.path.join(settings.MEDIA_ROOT, upload_path)

    # حذف الملف إذا موجود مسبقًا بنفس الاسم
    if os.path.exists(full_path):
        os.remove(full_path)

    return upload_path

class ArchiveFile(models.Model):
    name = models.CharField(max_length=100)
    zip_file = models.FileField(upload_to=overwrite_upload_path)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name

class GoogleSafeCheck(models.Model):
    url = models.URLField(unique=True)
    status = models.CharField(max_length=20, blank=True)  # Working / Red Flag / Error
    last_checked = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.url

class RedirectCheck(models.Model):
    url = models.URLField()
    keyword = models.CharField(max_length=100)
    status = models.CharField(max_length=20, blank=True)  # working / not working / error
    last_checked = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.url} | {self.keyword}"


class WhatsAppAccount(models.Model):
    """Registry tying session folder names to owning users."""

    account_name = models.CharField(max_length=64, unique=True)
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="whatsapp_accounts",
        null=True,
        blank=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["account_name"]

    def __str__(self):
        owner = self.owner.username if self.owner_id else "unassigned"
        return f"{self.account_name} ({owner})"


class WhatsAppCheckJob(models.Model):
    STATUS_PENDING = "pending"
    STATUS_RUNNING = "running"
    STATUS_COMPLETED = "completed"
    STATUS_FAILED = "failed"
    STATUS_CANCELLED = "cancelled"
    STATUS_CHOICES = [
        (STATUS_PENDING, "Pending"),
        (STATUS_RUNNING, "Running"),
        (STATUS_COMPLETED, "Completed"),
        (STATUS_FAILED, "Failed"),
        (STATUS_CANCELLED, "Cancelled"),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="whatsapp_check_jobs",
    )
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_PENDING,
    )
    numbers_text = models.TextField()
    input_line_count = models.PositiveIntegerField(default=0)
    unique_number_count = models.PositiveIntegerField(default=0)
    local_trunk_country = models.CharField(max_length=8, blank=True)
    account_names = models.JSONField(default=list, blank=True)
    speed = models.CharField(max_length=16, default="normal")
    fetch_presence = models.BooleanField(default=False)
    pid = models.IntegerField(null=True, blank=True)
    run_dir = models.CharField(max_length=512, blank=True)
    checked_count = models.PositiveIntegerField(default=0)
    live_count = models.PositiveIntegerField(default=0)
    error_count = models.PositiveIntegerField(default=0)
    error_message = models.TextField(blank=True)
    result_summary = models.JSONField(null=True, blank=True)
    previously_checked_numbers = models.JSONField(
        default=list, blank=True, null=True
    )
    created_at = models.DateTimeField(auto_now_add=True)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    @property
    def status_label(self) -> str:
        """Human-readable status; handles legacy/invalid DB values."""
        labels = dict(self.STATUS_CHOICES)
        if self.status in labels:
            return labels[self.status]
        raw = (self.status or "").strip()
        return raw.replace("_", " ").title() if raw else "Unknown"

    @property
    def is_resumable(self) -> bool:
        from tools.services import whatsapp_service as wa

        return wa.job_is_resumable(self)

    def __str__(self):
        return f"WhatsApp job #{self.pk} ({self.status})"


class WhatsAppVerifiedNumber(models.Model):
    """Historically verified live WhatsApp numbers (E.164 digits, no +)."""

    phone = models.CharField(max_length=20, unique=True, db_index=True)
    first_seen = models.DateTimeField(auto_now_add=True)
    last_job = models.ForeignKey(
        WhatsAppCheckJob,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="verified_numbers_recorded",
    )

    class Meta:
        ordering = ["-first_seen"]

    def __str__(self):
        return self.phone

