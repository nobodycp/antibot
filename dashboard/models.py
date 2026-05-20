# Create your models here.
import secrets

from django.conf import settings
from django.db import models
from django.contrib.auth.models import User

from .api_key_crypto import (
    HIDDEN_API_KEY_PREFIX,
    api_key_hmac_digest,
    is_hidden_api_key_storage,
)


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


class UserStoredRSAPrivateKey(models.Model):
    """One PEM private key per user for Tools → RSA decrypt (encrypted at rest)."""

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="stored_rsa_private_key_row",
    )
    fernet_ciphertext = models.TextField(help_text="Fernet-encrypted PEM text")
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "User stored RSA private key"
        verbose_name_plural = "User stored RSA private keys"

    def __str__(self):
        return f"RSA PEM store for user {self.user_id}"


class UserAPIKey(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="api_key_row",
    )
    api_key = models.CharField(
        max_length=128,
        unique=False,
        db_index=True,
        default=_new_urlsafe_api_key,
    )
    # HMAC-SHA256 (SECRET_KEY) of raw key for lookup; legacy rows may still match via plain api_key.
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
        if self.api_key and not is_hidden_api_key_storage(self.api_key):
            self.api_key_lookup_hash = api_key_hmac_digest(self.api_key)
        super().save(*args, **kwargs)

    def regenerate(self) -> str:
        """
        Issue a new raw key (returned once to the caller). DB stores HMAC + placeholder only.
        """
        raw = secrets.token_urlsafe(32)
        self.api_key_lookup_hash = api_key_hmac_digest(raw)
        self.api_key = f"{HIDDEN_API_KEY_PREFIX}{secrets.token_urlsafe(24)}"
        self.save()
        return raw


class UserCloudflareDomain(models.Model):
    """Cloudflare zone + API token for pushing antibot WAF rules."""

    SYNC_OK = "ok"
    SYNC_ERROR = "error"
    SYNC_WARNING = "warning"
    SYNC_STATUS_CHOICES = [
        (SYNC_OK, "OK"),
        (SYNC_ERROR, "Error"),
        (SYNC_WARNING, "Warning"),
    ]

    # Enterprise-only at Cloudflare; kept for normalizing legacy DB rows.
    SECURITY_OFF = "off"
    SECURITY_ESSENTIALLY_OFF = "essentially_off"
    SECURITY_LOW = "low"
    SECURITY_MEDIUM = "medium"
    SECURITY_HIGH = "high"
    SECURITY_UNDER_ATTACK = "under_attack"
    SECURITY_LEVEL_CHOICES = [
        (SECURITY_ESSENTIALLY_OFF, "Essentially off"),
        (SECURITY_LOW, "Low"),
        (SECURITY_MEDIUM, "Medium"),
        (SECURITY_HIGH, "High"),
        (SECURITY_UNDER_ATTACK, "Under attack"),
    ]

    @classmethod
    def normalize_security_level(cls, value: str) -> str:
        """Map legacy Enterprise-only 'off' to a value valid on Free/Pro/Business."""
        if value == cls.SECURITY_OFF:
            return cls.SECURITY_ESSENTIALLY_OFF
        return value

    TLS_1_0 = "1.0"
    TLS_1_1 = "1.1"
    TLS_1_2 = "1.2"
    TLS_1_3 = "1.3"
    MIN_TLS_CHOICES = [
        (TLS_1_0, "TLS 1.0"),
        (TLS_1_1, "TLS 1.1"),
        (TLS_1_2, "TLS 1.2"),
        (TLS_1_3, "TLS 1.3"),
    ]

    SSL_OFF = "off"
    SSL_FLEXIBLE = "flexible"
    SSL_FULL = "full"
    SSL_STRICT = "strict"
    SSL_MODE_CHOICES = [
        (SSL_OFF, "Off"),
        (SSL_FLEXIBLE, "Flexible"),
        (SSL_FULL, "Full"),
        (SSL_STRICT, "Strict"),
    ]

    CHALLENGE_TTL_300 = 300
    CHALLENGE_TTL_900 = 900
    CHALLENGE_TTL_1800 = 1800
    CHALLENGE_TTL_3600 = 3600
    CHALLENGE_TTL_7200 = 7200
    CHALLENGE_TTL_86400 = 86400
    CHALLENGE_TTL_CHOICES = [
        (CHALLENGE_TTL_300, "5 minutes"),
        (CHALLENGE_TTL_900, "15 minutes"),
        (CHALLENGE_TTL_1800, "30 minutes"),
        (CHALLENGE_TTL_3600, "1 hour"),
        (CHALLENGE_TTL_7200, "2 hours"),
        (CHALLENGE_TTL_86400, "1 day"),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="cloudflare_domains",
    )
    domain_name = models.CharField(max_length=255)
    zone_id = models.CharField(max_length=64)
    api_token_ciphertext = models.TextField()
    is_active = models.BooleanField(default=True)
    bot_fight_mode = models.BooleanField(default=False)
    under_attack_mode = models.BooleanField(default=False)
    block_ai_bots = models.BooleanField(default=False)
    ai_labyrinth = models.BooleanField(default=False)
    ai_crawl_control = models.BooleanField(default=False)
    browser_integrity_check = models.BooleanField(default=False)
    always_use_https = models.BooleanField(default=False)
    http3_enabled = models.BooleanField(default=False)
    zero_rtt_enabled = models.BooleanField(default=False)
    automatic_https_rewrites = models.BooleanField(default=False)
    security_level = models.CharField(
        max_length=32,
        choices=SECURITY_LEVEL_CHOICES,
        default=SECURITY_MEDIUM,
    )
    min_tls_version = models.CharField(
        max_length=8,
        choices=MIN_TLS_CHOICES,
        default=TLS_1_2,
    )
    ssl_mode = models.CharField(
        max_length=16,
        choices=SSL_MODE_CHOICES,
        default=SSL_FULL,
    )
    challenge_ttl = models.PositiveIntegerField(
        choices=CHALLENGE_TTL_CHOICES,
        default=CHALLENGE_TTL_1800,
    )

    RATE_LIMIT_ACTION_BLOCK = "block"
    RATE_LIMIT_ACTION_CHALLENGE = "challenge"
    RATE_LIMIT_ACTION_JS_CHALLENGE = "js_challenge"
    RATE_LIMIT_ACTION_MANAGED_CHALLENGE = "managed_challenge"
    RATE_LIMIT_ACTION_CHOICES = [
        (RATE_LIMIT_ACTION_BLOCK, "Block"),
        (RATE_LIMIT_ACTION_CHALLENGE, "Challenge"),
        (RATE_LIMIT_ACTION_JS_CHALLENGE, "JS Challenge"),
        (RATE_LIMIT_ACTION_MANAGED_CHALLENGE, "Managed Challenge"),
    ]

    rate_limit_enabled = models.BooleanField(default=False)
    rate_limit_requests = models.PositiveIntegerField(default=30, null=True, blank=True)
    rate_limit_period_seconds = models.PositiveIntegerField(default=10)
    rate_limit_action = models.CharField(
        max_length=32,
        choices=RATE_LIMIT_ACTION_CHOICES,
        default=RATE_LIMIT_ACTION_BLOCK,
    )
    rate_limit_duration_seconds = models.PositiveIntegerField(default=10)

    last_synced_at = models.DateTimeField(null=True, blank=True)
    last_sync_status = models.CharField(
        max_length=16,
        choices=SYNC_STATUS_CHOICES,
        blank=True,
        default="",
    )
    last_sync_error = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["user", "domain_name"],
                name="dashboard_usercloudflaredomain_user_domain_uniq",
            ),
        ]
        ordering = ["domain_name"]

    def __str__(self):
        return f"{self.domain_name} ({self.user_id})"


class CloudflareSyncRun(models.Model):
    """Audit log for admin-triggered sync-all runs."""

    STATUS_RUNNING = "running"
    STATUS_SUCCESS = "success"
    STATUS_PARTIAL = "partial"
    STATUS_FAILED = "failed"
    STATUS_CHOICES = [
        (STATUS_RUNNING, "Running"),
        (STATUS_SUCCESS, "Success"),
        (STATUS_PARTIAL, "Partial"),
        (STATUS_FAILED, "Failed"),
    ]

    started_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    triggered_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="cloudflare_sync_runs",
    )
    status = models.CharField(
        max_length=16,
        choices=STATUS_CHOICES,
        default=STATUS_RUNNING,
    )
    domains_ok = models.PositiveIntegerField(default=0)
    domains_failed = models.PositiveIntegerField(default=0)
    log_text = models.TextField(blank=True, default="")

    class Meta:
        ordering = ["-started_at"]

    def __str__(self):
        return f"Cloudflare sync #{self.pk} ({self.status})"