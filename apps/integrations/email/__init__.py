from django.conf import settings
from django.utils.module_loading import import_string

from apps.integrations.email.base import (
    MARKETING,
    TRANSACTIONAL,
    EmailAdapter,
    EmailEvent,
    EmailMessage,
    EmailMisconfigured,
    EmailRejected,
    EmailTemporarilyUnavailable,
)

__all__ = [
    "MARKETING",
    "TRANSACTIONAL",
    "EmailAdapter",
    "EmailEvent",
    "EmailMessage",
    "EmailMisconfigured",
    "EmailRejected",
    "EmailTemporarilyUnavailable",
    "get_email_adapter",
]


def get_email_adapter() -> EmailAdapter:
    """Adapter selected by the EMAIL_ADAPTER setting (dotted path)."""
    adapter_class = import_string(settings.EMAIL_ADAPTER)
    adapter: EmailAdapter = adapter_class()
    return adapter
