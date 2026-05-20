from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("dashboard", "0010_usercloudflaredomain_http3_0rtt_https_rewrites"),
    ]

    operations = [
        migrations.AddField(
            model_name="usercloudflaredomain",
            name="rate_limit_enabled",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="usercloudflaredomain",
            name="rate_limit_requests",
            field=models.PositiveIntegerField(blank=True, default=30, null=True),
        ),
        migrations.AddField(
            model_name="usercloudflaredomain",
            name="rate_limit_period_seconds",
            field=models.PositiveIntegerField(default=10),
        ),
        migrations.AddField(
            model_name="usercloudflaredomain",
            name="rate_limit_action",
            field=models.CharField(
                choices=[
                    ("block", "Block"),
                    ("challenge", "Challenge"),
                    ("js_challenge", "JS Challenge"),
                    ("managed_challenge", "Managed Challenge"),
                ],
                default="block",
                max_length=32,
            ),
        ),
        migrations.AddField(
            model_name="usercloudflaredomain",
            name="rate_limit_duration_seconds",
            field=models.PositiveIntegerField(default=10),
        ),
    ]
