from decimal import ROUND_HALF_UP, Decimal

from django.db import migrations


def fill_hours(apps, schema_editor):
    """Certificates issued before hours were kept get the course length as it is now."""
    Certificate = apps.get_model("learning", "Certificate")
    for certificate in Certificate.objects.filter(hours=0).select_related("enrolment__course"):
        seconds = certificate.enrolment.course.total_duration_seconds
        certificate.hours = (Decimal(seconds) / Decimal(3600)).quantize(
            Decimal("0.1"), rounding=ROUND_HALF_UP
        )
        certificate.save(update_fields=["hours"])


class Migration(migrations.Migration):
    dependencies = [("learning", "0005_certificates")]

    operations = [migrations.RunPython(fill_hours, migrations.RunPython.noop)]
