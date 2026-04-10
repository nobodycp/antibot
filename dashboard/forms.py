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
