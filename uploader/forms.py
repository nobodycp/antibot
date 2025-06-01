from django import forms
from .models import ArchiveFile

class ArchiveFileForm(forms.ModelForm):
    class Meta:
        model = ArchiveFile
        fields = ['name', 'zip_file']