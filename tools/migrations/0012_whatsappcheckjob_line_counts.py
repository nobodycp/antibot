from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("tools", "0011_whatsappcheckjob_previously_checked_nullable"),
    ]

    operations = [
        migrations.AddField(
            model_name="whatsappcheckjob",
            name="input_line_count",
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AddField(
            model_name="whatsappcheckjob",
            name="unique_number_count",
            field=models.PositiveIntegerField(default=0),
        ),
    ]
