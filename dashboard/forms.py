from django import forms


class TelegramBackupSettingsForm(forms.Form):
    """POST payload for telegram backup settings (mirrors previous view parsing)."""

    bot_token = forms.CharField(required=False, strip=True, max_length=255)
    chat_id = forms.CharField(required=False, strip=True, max_length=100)
    is_enabled = forms.BooleanField(required=False, initial=False)
    backup_database = forms.BooleanField(required=False, initial=False)
    backup_media = forms.BooleanField(required=False, initial=False)
    interval_days = forms.CharField(required=False, max_length=32)

    def clean_interval_days(self):
        raw = (self.cleaned_data.get("interval_days") or "1").strip()
        try:
            return max(1, int(raw))
        except ValueError:
            return 1


class AddUserForm(forms.Form):
    username = forms.CharField(required=True, strip=True, max_length=150)
    email = forms.CharField(required=False, strip=True, max_length=254)
    password = forms.CharField(required=True, strip=False, max_length=4096)
    is_superuser = forms.BooleanField(required=False, initial=False)


class EditUserForm(forms.Form):
    username = forms.CharField(required=True, strip=True, max_length=150)
    email = forms.CharField(required=False, strip=True, max_length=254)
    password = forms.CharField(required=False, strip=False, max_length=4096)
    is_superuser = forms.BooleanField(required=False, initial=False)
    is_staff = forms.BooleanField(required=False, initial=False)


class ProfileUpdateForm(forms.Form):
    username = forms.CharField(required=True, strip=True, max_length=150)
    email = forms.CharField(required=False, strip=True, max_length=254)
    avatar = forms.ImageField(required=False)


class ProfilePasswordForm(forms.Form):
    old_password = forms.CharField(required=False, strip=True, max_length=4096)
    new_password = forms.CharField(required=False, strip=False, max_length=4096)
    confirm_password = forms.CharField(required=False, strip=False, max_length=4096)


class CloudflareDomainForm(forms.Form):
    domain_name = forms.CharField(required=True, strip=True, max_length=255)
    zone_id = forms.CharField(required=True, strip=True, max_length=64)
    api_token = forms.CharField(
        required=False,
        strip=True,
        max_length=512,
        widget=forms.PasswordInput(render_value=False),
    )
    is_active = forms.BooleanField(required=False, initial=True)
    bot_fight_mode = forms.BooleanField(required=False, initial=False)
    under_attack_mode = forms.BooleanField(required=False, initial=False)
    block_ai_bots = forms.BooleanField(required=False, initial=False)
    ai_labyrinth = forms.BooleanField(required=False, initial=False)
    ai_crawl_control = forms.BooleanField(required=False, initial=False)
    browser_integrity_check = forms.BooleanField(required=False, initial=False)
    always_use_https = forms.BooleanField(required=False, initial=False)
    http3_enabled = forms.BooleanField(required=False, initial=False)
    zero_rtt_enabled = forms.BooleanField(required=False, initial=False)
    automatic_https_rewrites = forms.BooleanField(required=False, initial=False)
    security_level = forms.CharField(required=True)
    min_tls_version = forms.ChoiceField(
        required=True,
        choices=[],
    )
    ssl_mode = forms.ChoiceField(
        required=True,
        choices=[],
    )
    challenge_ttl = forms.ChoiceField(
        required=True,
        choices=[],
    )
    rate_limit_enabled = forms.BooleanField(required=False, initial=False)
    rate_limit_requests = forms.IntegerField(required=False, min_value=1)
    rate_limit_period_seconds = forms.IntegerField(required=False, min_value=1)
    rate_limit_action = forms.ChoiceField(required=False, choices=[])
    rate_limit_duration_seconds = forms.IntegerField(required=False, min_value=1)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from dashboard.models import UserCloudflareDomain

        self.fields["security_level"].widget = forms.Select(
            choices=UserCloudflareDomain.SECURITY_LEVEL_CHOICES,
        )
        self.fields["min_tls_version"].choices = UserCloudflareDomain.MIN_TLS_CHOICES
        self.fields["ssl_mode"].choices = UserCloudflareDomain.SSL_MODE_CHOICES
        self.fields["challenge_ttl"].choices = [
            (str(v), label) for v, label in UserCloudflareDomain.CHALLENGE_TTL_CHOICES
        ]
        self.fields["rate_limit_action"].choices = (
            UserCloudflareDomain.RATE_LIMIT_ACTION_CHOICES
        )

    def clean_domain_name(self):
        from dashboard.helpers.cloudflare_zone import normalize_domain_name

        return normalize_domain_name(self.cleaned_data.get("domain_name") or "")

    def clean_zone_id(self):
        from dashboard.helpers.cloudflare_zone import normalize_zone_id

        return normalize_zone_id(self.cleaned_data.get("zone_id") or "")

    def clean_challenge_ttl(self):
        raw = self.cleaned_data.get("challenge_ttl")
        try:
            return int(raw)
        except (TypeError, ValueError):
            from dashboard.models import UserCloudflareDomain

            return UserCloudflareDomain.CHALLENGE_TTL_1800

    def clean_rate_limit_requests(self):
        raw = self.cleaned_data.get("rate_limit_requests")
        if raw in (None, ""):
            return None
        return max(1, int(raw))

    def clean_rate_limit_period_seconds(self):
        raw = self.cleaned_data.get("rate_limit_period_seconds")
        if raw in (None, ""):
            return 10
        return max(1, int(raw))

    def clean_rate_limit_duration_seconds(self):
        raw = self.cleaned_data.get("rate_limit_duration_seconds")
        if raw in (None, ""):
            return 10
        return max(1, int(raw))

    def clean_security_level(self):
        from dashboard.models import UserCloudflareDomain

        raw = (self.cleaned_data.get("security_level") or "").strip()
        value = UserCloudflareDomain.normalize_security_level(raw)
        valid = {c[0] for c in UserCloudflareDomain.SECURITY_LEVEL_CHOICES}
        if value not in valid:
            raise forms.ValidationError("Select a valid security level.")
        return value

    def clean_rate_limit_action(self):
        raw = self.cleaned_data.get("rate_limit_action")
        from dashboard.models import UserCloudflareDomain

        valid = {c[0] for c in UserCloudflareDomain.RATE_LIMIT_ACTION_CHOICES}
        if raw in valid:
            return raw
        return UserCloudflareDomain.RATE_LIMIT_ACTION_BLOCK

    def clean(self):
        cleaned = super().clean()
        from dashboard.models import UserCloudflareDomain

        if cleaned.get("under_attack_mode"):
            cleaned["security_level"] = UserCloudflareDomain.SECURITY_UNDER_ATTACK
        elif (
            cleaned.get("security_level") == UserCloudflareDomain.SECURITY_UNDER_ATTACK
        ):
            cleaned["security_level"] = UserCloudflareDomain.SECURITY_MEDIUM
        return cleaned


def apply_cloudflare_domain_form(
    domain,
    cleaned_data: dict,
    *,
    include_identity: bool = True,
) -> None:
    """Copy validated CloudflareDomainForm data onto a UserCloudflareDomain."""
    if include_identity:
        domain.domain_name = cleaned_data["domain_name"]
        domain.zone_id = cleaned_data["zone_id"]
        domain.is_active = cleaned_data.get("is_active", domain.is_active)

    domain.bot_fight_mode = cleaned_data.get("bot_fight_mode", False)
    domain.under_attack_mode = cleaned_data.get("under_attack_mode", False)
    domain.block_ai_bots = cleaned_data.get("block_ai_bots", False)
    domain.ai_labyrinth = cleaned_data.get("ai_labyrinth", False)
    domain.ai_crawl_control = cleaned_data.get("ai_crawl_control", False)
    domain.browser_integrity_check = cleaned_data.get("browser_integrity_check", False)
    domain.always_use_https = cleaned_data.get("always_use_https", False)
    domain.http3_enabled = cleaned_data.get("http3_enabled", False)
    domain.zero_rtt_enabled = cleaned_data.get("zero_rtt_enabled", False)
    domain.automatic_https_rewrites = cleaned_data.get(
        "automatic_https_rewrites", False
    )
    domain.security_level = cleaned_data["security_level"]
    domain.min_tls_version = cleaned_data["min_tls_version"]
    domain.ssl_mode = cleaned_data["ssl_mode"]
    domain.challenge_ttl = cleaned_data["challenge_ttl"]
    domain.rate_limit_enabled = cleaned_data.get("rate_limit_enabled", False)
    domain.rate_limit_requests = cleaned_data.get("rate_limit_requests")
    domain.rate_limit_period_seconds = cleaned_data.get(
        "rate_limit_period_seconds", domain.rate_limit_period_seconds
    )
    domain.rate_limit_action = cleaned_data.get(
        "rate_limit_action", domain.rate_limit_action
    )
    domain.rate_limit_duration_seconds = cleaned_data.get(
        "rate_limit_duration_seconds", domain.rate_limit_duration_seconds
    )

