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
