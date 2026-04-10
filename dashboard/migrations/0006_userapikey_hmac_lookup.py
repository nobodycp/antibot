import hashlib
import hmac

from django.conf import settings
from django.db import migrations, models

import dashboard.models


def forwards_hmac_backfill(apps, schema_editor):
    UserAPIKey = apps.get_model("dashboard", "UserAPIKey")
    sec = settings.SECRET_KEY.encode("utf-8")
    prefix = "__hk__"
    for row in UserAPIKey.objects.all().iterator():
        k = (row.api_key or "").strip()
        if not k or k.startswith(prefix):
            continue
        digest = hmac.new(sec, k.encode("utf-8"), hashlib.sha256).hexdigest()
        if row.api_key_lookup_hash != digest:
            row.api_key_lookup_hash = digest
            row.save(update_fields=["api_key_lookup_hash"])


class Migration(migrations.Migration):
    dependencies = [
        ("dashboard", "0005_userapikey_lookup_hash"),
    ]

    operations = [
        migrations.AlterField(
            model_name="userapikey",
            name="api_key",
            field=models.CharField(
                db_index=True,
                default=dashboard.models._new_urlsafe_api_key,
                max_length=128,
            ),
        ),
        migrations.RunPython(forwards_hmac_backfill, migrations.RunPython.noop),
    ]
