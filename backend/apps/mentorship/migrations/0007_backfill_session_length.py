from django.db import migrations
from django.db.models import ExpressionWrapper, F, IntegerField
from django.db.models.functions import Extract


def fill(apps, schema_editor):
    """Sessions made before lengths were kept get the length of their time span."""
    MentorSession = apps.get_model("mentorship", "MentorSession")
    minutes = ExpressionWrapper(
        Extract(F("ends_at") - F("starts_at"), "epoch") / 60, output_field=IntegerField()
    )
    MentorSession.objects.filter(length_minutes=0).update(length_minutes=minutes)


class Migration(migrations.Migration):
    dependencies = [("mentorship", "0006_mentor_settings")]

    operations = [migrations.RunPython(fill, migrations.RunPython.noop)]
