from typing import Any

import sentry_sdk
from django.conf import settings

from apps.core.logging import redact


def _scrub(event: dict[str, Any], _hint: dict[str, Any]) -> dict[str, Any]:
    request = event.get("request")
    if isinstance(request, dict):
        request.pop("cookies", None)
        request.pop("data", None)
        if "headers" in request:
            request["headers"] = redact(dict(request["headers"]))
    return event


def init_sentry() -> None:
    if not settings.SENTRY_DSN:
        return
    sentry_sdk.init(
        dsn=settings.SENTRY_DSN,
        environment=settings.ENVIRONMENT,
        release=settings.RELEASE,
        send_default_pii=False,
        before_send=_scrub,  # type: ignore[arg-type]
    )
