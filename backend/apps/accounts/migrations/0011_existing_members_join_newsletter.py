"""Existing members join the newsletter, as new members now do when they sign up.

Until now the newsletter was an unticked box at sign up, so most members left it off. Each member
whose only choice was that sign up box, or who never had one, is now recorded as agreeing. Anyone
who changed their mind later (withdrew in settings or from a newsletter), or whose address is on
the do-not-mail list (unsubscribed, bounced or complained), is left exactly as they are. Members can
leave at any time from Settings or from any newsletter.
"""

import hashlib

from django.db import migrations
from django.db.models import Count, Q

MEMBER_ROLES = ("member", "mentor")
MEMBER_STATUSES = ("active", "pending")


def _hash(email: str) -> str:
    return hashlib.sha256(email.strip().lower().encode()).hexdigest()


def join(apps, schema_editor):
    User = apps.get_model("accounts", "User")
    ConsentRecord = apps.get_model("accounts", "ConsentRecord")
    Suppression = apps.get_model("notifications", "Suppression")

    blocked = set(Suppression.objects.values_list("email_hash", flat=True))
    members = (
        User.objects.filter(status__in=MEMBER_STATUSES, user_roles__role__in=MEMBER_ROLES)
        .annotate(
            choices=Count("consents", filter=Q(consents__document="marketing"), distinct=True),
            agreed=Count(
                "consents",
                filter=Q(consents__document="marketing", consents__granted=True),
                distinct=True,
            ),
        )
        .filter(choices__lte=1, agreed=0)  # only the sign up box, left unticked, or nothing
        .distinct()
    )
    ConsentRecord.objects.bulk_create(
        [
            ConsentRecord(user_id=user_id, document="marketing", version="1", granted=True)
            for user_id, email in members.values_list("pk", "email")
            if _hash(email) not in blocked
        ],
        batch_size=500,
    )


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0010_referral_code_unique"),
        ("notifications", "0005_admin_alerts"),
    ]

    # Going back keeps the records: they are history, and later choices build on them.
    operations = [migrations.RunPython(join, migrations.RunPython.noop)]
