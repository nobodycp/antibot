import re
from pathlib import Path

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


def assign_existing_session_accounts(apps, schema_editor):
    WhatsAppAccount = apps.get_model("tools", "WhatsAppAccount")
    User = apps.get_model(*settings.AUTH_USER_MODEL.split("."))
    first_super = User.objects.filter(is_superuser=True).order_by("pk").first()

    sessions_root = Path(settings.WHATSAPP_ROOT) / "sessions"
    if not sessions_root.is_dir():
        return

    account_re = re.compile(r"^[a-zA-Z0-9_-]{1,64}$")
    for entry in sorted(sessions_root.iterdir()):
        if not entry.is_dir() or not account_re.match(entry.name):
            continue
        WhatsAppAccount.objects.update_or_create(
            account_name=entry.name,
            defaults={"owner": first_super},
        )


class Migration(migrations.Migration):

    dependencies = [
        ("tools", "0009_whatsappverifiednumber_and_job_skipped"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="WhatsAppAccount",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("account_name", models.CharField(max_length=64, unique=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "owner",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="whatsapp_accounts",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "ordering": ["account_name"],
            },
        ),
        migrations.RunPython(
            assign_existing_session_accounts,
            migrations.RunPython.noop,
        ),
    ]
