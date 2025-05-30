from django.db import models

class ArchiveFile(models.Model):
    name = models.CharField(max_length=100)
    zip_file = models.FileField(upload_to='zips/')

    def __str__(self):
        return self.name
