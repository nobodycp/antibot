from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("tools", "0006_whatsappcheckjob"),
    ]

    operations = [
        migrations.AddField(
            model_name="whatsappcheckjob",
            name="local_trunk_country",
            field=models.CharField(blank=True, max_length=8),
        ),
    ]
