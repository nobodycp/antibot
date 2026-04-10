import hashlib

from django.db import migrations, models


def _backfill_api_key_lookup_hash(apps, schema_editor):
    UserAPIKey = apps.get_model("dashboard", "UserAPIKey")
    for row in UserAPIKey.objects.all().iterator():
        if row.api_key:
            row.api_key_lookup_hash = hashlib.sha256(
                row.api_key.encode("utf-8")
            ).hexdigest()
            row.save(update_fields=["api_key_lookup_hash"])


class Migration(migrations.Migration):

    dependencies = [
        ("dashboard", "0004_user_api_key"),
    ]

    operations = [
        migrations.AddField(
            model_name="userapikey",
            name="api_key_lookup_hash",
            field=models.CharField(
                db_index=True,
                editable=False,
                max_length=64,
                null=True,
                unique=False,
            ),
        ),
        migrations.RunPython(_backfill_api_key_lookup_hash, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="userapikey",
            name="api_key_lookup_hash",
            field=models.CharField(
                db_index=True,
                default="",
                editable=False,
                max_length=64,
                unique=True,
            ),
        ),
    ]
