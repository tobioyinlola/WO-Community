"""Which notifications a member wants, by type and channel."""

from typing import Any
from uuid import UUID

from django.db import transaction
from django.utils import timezone

from apps.notifications.models import NotificationPreference

CHANNELS = ("email", "in_app")

# Every type a member can control, with what they get until they choose.
DEFAULTS: dict[str, dict[str, bool]] = {
    "comments": {"email": True, "in_app": True},
    "mentions": {"email": True, "in_app": True},
    "mentorship": {"email": True, "in_app": True},
    "approvals": {"email": True, "in_app": True},
    "event_reminders": {"email": True, "in_app": True},
    "newsletter": {"email": False, "in_app": False},
}

# Account messages the member cannot switch off.
LOCKED: frozenset[tuple[str, str]] = frozenset({("approvals", "email")})


class InvalidPreferences(ValueError):
    def __init__(self, errors: dict[str, str]) -> None:
        super().__init__("invalid notification preferences")
        self.errors = errors


def _merge(stored: dict[str, Any]) -> dict[str, dict[str, bool]]:
    merged = {kind: dict(channels) for kind, channels in DEFAULTS.items()}
    for kind, channels in stored.items():
        if kind in merged:
            for channel, value in channels.items():
                if channel in merged[kind]:
                    merged[kind][channel] = bool(value)
    return merged


def get(user_id: UUID) -> tuple[dict[str, dict[str, bool]], bool]:
    """The member's full matrix and whether they have ever saved it."""
    row = NotificationPreference.objects.filter(user_id=user_id).first()
    if row is None:
        return _merge({}), False
    return _merge(row.choices), row.confirmed_at is not None


def validate(changes: dict[str, Any]) -> dict[str, str]:
    errors: dict[str, str] = {}
    for kind, channels in changes.items():
        if kind not in DEFAULTS:
            errors[kind] = "Unknown notification type."
            continue
        for channel, value in channels.items():
            if channel not in CHANNELS:
                errors[f"{kind}.{channel}"] = "Unknown channel."
            elif (kind, channel) in LOCKED and value is False:
                errors[f"{kind}.{channel}"] = "This message cannot be switched off."
    return errors


def update(user_id: UUID, changes: dict[str, dict[str, bool]]) -> dict[str, dict[str, bool]]:
    """Apply a partial change. Saving, even with no changes, marks the preferences as set."""
    errors = validate(changes)
    if errors:
        raise InvalidPreferences(errors)
    with transaction.atomic():
        row, _ = NotificationPreference.objects.select_for_update().get_or_create(user_id=user_id)
        merged = _merge(row.choices)
        for kind, channels in changes.items():
            merged[kind].update(channels)
        row.choices = {
            kind: {c: v for c, v in channels.items() if v != DEFAULTS[kind][c]}
            for kind, channels in merged.items()
            if channels != DEFAULTS[kind]
        }
        row.confirmed_at = row.confirmed_at or timezone.now()
        row.save(update_fields=["choices", "confirmed_at", "updated_at"])
    return merged


def has_confirmed(user_id: UUID) -> bool:
    return NotificationPreference.objects.filter(
        user_id=user_id, confirmed_at__isnull=False
    ).exists()


def allows(user_id: UUID, kind: str, channel: str) -> bool:
    """Whether to send ``kind`` over ``channel``. Locked account messages always go."""
    if (kind, channel) in LOCKED:
        return True
    return get(user_id)[0][kind][channel]
