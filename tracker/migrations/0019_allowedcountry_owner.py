from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


def copy_global_countries_to_each_user(apps, schema_editor):
    AllowedCountry = apps.get_model("tracker", "AllowedCountry")
    User = apps.get_model("auth", "User")
    rows = list(AllowedCountry.objects.values("code", "name"))
    if not rows:
        return
    user_ids = list(User.objects.filter(is_active=True).values_list("pk", flat=True))
    AllowedCountry.objects.all().delete()
    to_create = [
        AllowedCountry(owner_id=uid, code=row["code"], name=row["name"])
        for uid in user_ids
        for row in rows
    ]
    AllowedCountry.objects.bulk_create(to_create, ignore_conflicts=True)


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("tracker", "0018_log_ownership"),
    ]

    operations = [
        migrations.AddField(
            model_name="allowedcountry",
            name="owner",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="allowed_countries",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AlterField(
            model_name="allowedcountry",
            name="code",
            field=models.CharField(max_length=2),
        ),
        migrations.RunPython(
            copy_global_countries_to_each_user,
            migrations.RunPython.noop,
        ),
        migrations.AlterField(
            model_name="allowedcountry",
            name="owner",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="allowed_countries",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddConstraint(
            model_name="allowedcountry",
            constraint=models.UniqueConstraint(
                fields=("owner", "code"),
                name="tracker_allowedcountry_owner_code_uniq",
            ),
        ),
    ]
