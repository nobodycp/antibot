from django.contrib import admin
from .models import ArchiveFile
from django.utils.html import format_html

@admin.register(ArchiveFile)
class ArchiveFileAdmin(admin.ModelAdmin):
    list_display = ['name', 'zip_file_link']
    readonly_fields = ['zip_file_link']

    def zip_file_link(self, obj):
        if obj.zip_file:
            return format_html("<a href='{}' target='_blank'>📦 Download</a>", obj.zip_file.url)
        return "-"
