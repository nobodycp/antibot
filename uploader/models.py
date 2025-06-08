import os
from django.db import models
from django.conf import settings  # هذا السطر مهم للوصول إلى MEDIA_ROOT

def overwrite_upload_path(instance, filename):
    upload_path = os.path.join('zips', filename)
    full_path = os.path.join(settings.MEDIA_ROOT, upload_path)

    # حذف الملف لو موجود بنفس الاسم
    if os.path.exists(full_path):
        os.remove(full_path)

    return upload_path

class ArchiveFile(models.Model):
    name = models.CharField(max_length=100)
    zip_file = models.FileField(upload_to=overwrite_upload_path)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name
