import secrets
from datetime import timedelta

from django.utils import timezone

from apps.profiles.models import FounderProfile
from apps.profiles.services import get_or_create_profile
from apps.uploads.models import Upload

TICKETS = "/api/v1/support/tickets"
ADMIN_TICKETS = "/api/v1/admin/support/tickets"

MESSAGE = "I cannot find the button to update my startup profile after the latest change."


def active(make_user, email, name="", roles=("member",), **fields):
    user = make_user(
        email=email,
        roles=roles,
        approved_at=timezone.now(),
        email_verified_at=timezone.now(),
        **fields,
    )
    if name:
        profile = get_or_create_profile(user.pk)
        FounderProfile.objects.filter(pk=profile.pk).update(full_name=name)
    return user


def body(**overrides):
    return {
        "category": "profile",
        "subject": "Cannot edit my startup",
        "message": MESSAGE,
        **overrides,
    }


def ready_attachment(owner, name="screenshot.pdf", content_type="application/pdf") -> Upload:
    """An upload that has been scanned and is waiting to be attached to something."""
    return Upload.objects.create(
        owner=owner,
        purpose="support_attachment",
        status="ready",
        declared_content_type=content_type,
        declared_size=2048,
        size=2048,
        original_filename=name,
        quarantine_key=f"support_attachment/{secrets.token_hex(8)}",
        base_key=f"private/support_attachment/{secrets.token_hex(8)}",
        expires_at=timezone.now() + timedelta(days=1),
        ready_at=timezone.now(),
    )
