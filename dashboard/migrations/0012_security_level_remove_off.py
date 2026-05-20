from django.db import migrations, models


def migrate_off_to_essentially_off(apps, schema_editor):
    UserCloudflareDomain = apps.get_model("dashboard", "UserCloudflareDomain")
    UserCloudflareDomain.objects.filter(security_level="off").update(
        security_level="essentially_off"
    )


class Migration(migrations.Migration):

    dependencies = [
        ("dashboard", "0011_usercloudflaredomain_rate_limit"),
    ]

    operations = [
        migrations.RunPython(
            migrate_off_to_essentially_off,
            migrations.RunPython.noop,
        ),
        migrations.AlterField(
            model_name="usercloudflaredomain",
            name="security_level",
            field=models.CharField(
                choices=[
                    ("essentially_off", "Essentially off"),
                    ("low", "Low"),
                    ("medium", "Medium"),
                    ("high", "High"),
                    ("under_attack", "Under attack"),
                ],
                default="medium",
                max_length=32,
            ),
        ),
    ]
