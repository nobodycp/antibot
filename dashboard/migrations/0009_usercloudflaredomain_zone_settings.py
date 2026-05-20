from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("dashboard", "0008_usercloudflaredomain_cloudflaresyncrun_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="usercloudflaredomain",
            name="always_use_https",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="usercloudflaredomain",
            name="ai_crawl_control",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="usercloudflaredomain",
            name="ai_labyrinth",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="usercloudflaredomain",
            name="block_ai_bots",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="usercloudflaredomain",
            name="bot_fight_mode",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="usercloudflaredomain",
            name="browser_integrity_check",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="usercloudflaredomain",
            name="challenge_ttl",
            field=models.PositiveIntegerField(
                choices=[
                    (300, "5 minutes"),
                    (900, "15 minutes"),
                    (1800, "30 minutes"),
                    (3600, "1 hour"),
                    (7200, "2 hours"),
                    (86400, "1 day"),
                ],
                default=1800,
            ),
        ),
        migrations.AddField(
            model_name="usercloudflaredomain",
            name="min_tls_version",
            field=models.CharField(
                choices=[
                    ("1.0", "TLS 1.0"),
                    ("1.1", "TLS 1.1"),
                    ("1.2", "TLS 1.2"),
                    ("1.3", "TLS 1.3"),
                ],
                default="1.2",
                max_length=8,
            ),
        ),
        migrations.AddField(
            model_name="usercloudflaredomain",
            name="security_level",
            field=models.CharField(
                choices=[
                    ("off", "Off"),
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
        migrations.AddField(
            model_name="usercloudflaredomain",
            name="ssl_mode",
            field=models.CharField(
                choices=[
                    ("off", "Off"),
                    ("flexible", "Flexible"),
                    ("full", "Full"),
                    ("strict", "Strict"),
                ],
                default="full",
                max_length=16,
            ),
        ),
        migrations.AddField(
            model_name="usercloudflaredomain",
            name="under_attack_mode",
            field=models.BooleanField(default=False),
        ),
    ]
