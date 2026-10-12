import secrets

from django.db import migrations

ALPHABET = "23456789ABCDEFGHJKLMNPQRSTUVWXYZ"
BATCH = 500


def code() -> str:
    return "".join(secrets.choice(ALPHABET) for _ in range(8))


def give_everyone_a_code(apps, schema_editor):
    """Accounts made before codes existed get one. Safe to run twice: only blanks are filled."""
    User = apps.get_model("accounts", "User")
    taken = set(
        User.objects.exclude(referral_code__isnull=True).values_list("referral_code", flat=True)
    )
    pending = list(User.objects.filter(referral_code__isnull=True).only("id"))
    for start in range(0, len(pending), BATCH):
        chunk = pending[start : start + BATCH]
        for user in chunk:
            fresh = code()
            while fresh in taken:
                fresh = code()
            taken.add(fresh)
            user.referral_code = fresh
        User.objects.bulk_update(chunk, ["referral_code"])


class Migration(migrations.Migration):
    dependencies = [("accounts", "0008_referral_fields")]

    operations = [migrations.RunPython(give_everyone_a_code, migrations.RunPython.noop)]
