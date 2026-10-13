from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("learning", "0006_backfill_certificate_hours")]

    operations = [
        migrations.AddField(
            model_name="certificate",
            name="show_on_profile",
            field=models.BooleanField(default=False),
        ),
    ]
