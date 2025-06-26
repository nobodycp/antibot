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