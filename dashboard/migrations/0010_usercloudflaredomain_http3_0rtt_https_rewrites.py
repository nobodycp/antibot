from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("dashboard", "0009_usercloudflaredomain_zone_settings"),
    ]

    operations = [
        migrations.AddField(
            model_name="usercloudflaredomain",
            name="http3_enabled",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="usercloudflaredomain",
            name="zero_rtt_enabled",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="usercloudflaredomain",
            name="automatic_https_rewrites",
            field=models.BooleanField(default=False),
        ),
    ]
