"""The newsletter sign up on the website, for anyone, member or not.

Double opt-in: a sign up only counts once the link we email is opened, so nobody can subscribe
someone else. The answer to a sign up is always the same, so it never says whether an address
is already on the list.
"""

from typing import Any
from uuid import UUID

from django.conf import settings
from django.core import signing
from django.db import IntegrityError, transaction
from django.db.models import Q, QuerySet
from django.utils import timezone

from apps.accounts import services as accounts
from apps.campaigns.models import NewsletterSubscriber
from apps.core import ratelimit
from apps.notifications import emails
from apps.notifications import services as notifications

CONFIRM_SALT = "campaigns.newsletter.confirm"
UNSUBSCRIBE_SALT = "campaigns.newsletter.unsubscribe"
CONFIRM_MAX_AGE = 7 * 24 * 3600
# One confirmation email per address every so often, however often the form is sent.
RESEND_AFTER_SECONDS = 600

Status = NewsletterSubscriber.Status


class InvalidLink(Exception):
    """A confirm or unsubscribe link that is damaged, expired or not ours."""


def _normalise(email: str) -> str:
    return email.strip().lower()


def confirm_token(email: str) -> str:
    return signing.dumps({"e": _normalise(email)}, salt=CONFIRM_SALT)


def unsubscribe_token(subscriber_id: UUID) -> str:
    return signing.dumps({"s": str(subscriber_id)}, salt=UNSUBSCRIBE_SALT)


def _app(path: str) -> str:
    return f"{settings.FRONTEND_BASE_URL}{path}"


def subscribe(email: str) -> None:
    """Ask for the newsletter. Sends the confirmation email unless already confirmed."""
    address = _normalise(email)
    try:
        with transaction.atomic():
            subscriber, _ = NewsletterSubscriber.objects.get_or_create(email=address)
    except IntegrityError:  # two sign ups at once
        subscriber = NewsletterSubscriber.objects.get(email=address)
    if subscriber.status == Status.CONFIRMED:
        return
    if subscriber.status == Status.UNSUBSCRIBED:
        # Signing up again is a fresh request; it still waits for the link to be opened.
        NewsletterSubscriber.objects.filter(pk=subscriber.pk).update(
            status=Status.PENDING, updated_at=timezone.now()
        )
    key = f"newsletter-confirm:{notifications.hash_email(address)}"
    if ratelimit.hit(key, RESEND_AFTER_SECONDS) > 1:
        return
    emails.send_templated(
        address,
        "newsletter_confirm",
        {"confirm_url": _app(f"/newsletter/confirm?token={confirm_token(address)}")},
        category="newsletter_confirm",
        no_reply=True,
    )


def confirm(token: str) -> NewsletterSubscriber:
    """Open the confirmation link: the address is now on the list."""
    try:
        data = signing.loads(token, salt=CONFIRM_SALT, max_age=CONFIRM_MAX_AGE)
        address = _normalise(str(data["e"]))
    except (signing.BadSignature, KeyError, TypeError) as exc:
        raise InvalidLink() from exc
    subscriber, _ = NewsletterSubscriber.objects.get_or_create(email=address)
    if subscriber.status != Status.CONFIRMED:
        now = timezone.now()
        subscriber.status, subscriber.confirmed_at = Status.CONFIRMED, now
        subscriber.unsubscribed_at = None
        subscriber.save(update_fields=["status", "confirmed_at", "unsubscribed_at", "updated_at"])
        notifications.unsuppress_unsubscribed(address)
        # A member who signs up here gets the newsletter through their account.
        member = accounts.user_id_for_email(address)
        if member is not None:
            accounts.set_marketing_consent(member, True)
    return subscriber


def unsubscribe(token: str) -> None:
    """Leave the list at once. Safe to repeat."""
    try:
        data = signing.loads(token, salt=UNSUBSCRIBE_SALT)
        subscriber_id = UUID(str(data["s"]))
    except (signing.BadSignature, KeyError, TypeError, ValueError) as exc:
        raise InvalidLink() from exc
    subscriber = NewsletterSubscriber.objects.filter(pk=subscriber_id).first()
    if subscriber is None or subscriber.status == Status.UNSUBSCRIBED:
        return
    with transaction.atomic():
        subscriber.status, subscriber.unsubscribed_at = Status.UNSUBSCRIBED, timezone.now()
        subscriber.save(update_fields=["status", "unsubscribed_at", "updated_at"])
        notifications.suppress(subscriber.email, "unsubscribed")


# --- for campaigns and the admin console ---


def sendable() -> QuerySet[NewsletterSubscriber]:
    """Confirmed subscribers who are not members (members are reached through their account)."""
    member_emails = accounts.all_member_emails()
    return NewsletterSubscriber.objects.filter(status=Status.CONFIRMED).exclude(
        email__in=member_emails
    )


def still_sendable(subscriber_id: UUID) -> NewsletterSubscriber | None:
    subscriber = NewsletterSubscriber.objects.filter(
        pk=subscriber_id, status=Status.CONFIRMED
    ).first()
    if subscriber is None or notifications.is_suppressed(subscriber.email):
        return None
    return subscriber


def search(*, status: str = "", q: str = "") -> QuerySet[NewsletterSubscriber]:
    rows = NewsletterSubscriber.objects.all().order_by("-created_at", "id")
    if status:
        rows = rows.filter(status=status)
    if q:
        rows = rows.filter(Q(email__icontains=q.strip().lower()))
    return rows


def counts() -> dict[str, Any]:
    rows = NewsletterSubscriber.objects
    return {
        "confirmed": rows.filter(status=Status.CONFIRMED).count(),
        "pending": rows.filter(status=Status.PENDING).count(),
        "unsubscribed": rows.filter(status=Status.UNSUBSCRIBED).count(),
    }
