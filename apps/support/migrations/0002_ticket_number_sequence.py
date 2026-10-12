from django.db import migrations


class Migration(migrations.Migration):
    """Ticket numbers come from a sequence, so two requests can never be given the same one."""

    dependencies = [("support", "0001_tickets")]

    operations = [
        migrations.RunSQL(
            "CREATE SEQUENCE support_ticket_number_seq START 1001",
            reverse_sql="DROP SEQUENCE support_ticket_number_seq",
        )
    ]
