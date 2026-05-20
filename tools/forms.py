"""Model forms for tools app upload and checker features."""
from django import forms
from .models import ArchiveFile, GoogleSafeCheck, RedirectCheck

class ArchiveFileForm(forms.ModelForm):
    class Meta:
        model = ArchiveFile
        fields = ['name', 'zip_file']

class GoogleSafeCheckForm(forms.ModelForm):
    class Meta:
        model = GoogleSafeCheck
        fields = ['url']


class RedirectCheckForm(forms.ModelForm):
    class Meta:
        model = RedirectCheck
        fields = ['url', 'keyword']


class WhatsAppCheckForm(forms.Form):
    SPEED_CHOICES = [
        ("safe", "Safe (slower, lower ban risk)"),
        ("normal", "Normal"),
        ("fast", "Fast (aged accounts only)"),
    ]

    numbers = forms.CharField(
        widget=forms.Textarea(
            attrs={
                "rows": 12,
                "placeholder": "One number per line (E.164 digits, e.g. 966501234567)\n"
                "Optional prefix: 972:0531234567",
                "class": "ds-input w-full font-mono text-sm",
            }
        ),
        label="Phone numbers",
    )
    country_prefix = forms.CharField(
        required=False,
        widget=forms.TextInput(
            attrs={
                "placeholder": "972 or 972:",
                "class": "ds-input ds-input--compact w-full max-w-[8rem] font-mono text-sm",
                "autocomplete": "off",
            }
        ),
        label="Local trunk prefix",
        help_text=(
            "For lines without an explicit 972:053… prefix. "
            "Converts 05XXXXXXXX to international (e.g. 972 + 5XXXXXXXX)."
        ),
    )
    accounts = forms.MultipleChoiceField(
        required=False,
        widget=forms.CheckboxSelectMultiple,
        label="Accounts to use",
        help_text="Leave all unchecked to use every linked account.",
    )
    speed = forms.ChoiceField(choices=SPEED_CHOICES, initial="normal", label="Speed profile")
    fetch_presence = forms.BooleanField(
        required=False,
        initial=False,
        label="Fetch presence / last seen (slower)",
    )

    def __init__(self, *args, account_choices=None, **kwargs):
        super().__init__(*args, **kwargs)
        choices = account_choices or []
        self.fields["accounts"].choices = [(n, n) for n in choices]
