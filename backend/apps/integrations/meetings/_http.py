"""Shared handling of provider HTTP failures, so each adapter sorts them the same way."""

from typing import NoReturn

import httpx

from apps.integrations.meetings.base import (
    MeetingMisconfigured,
    MeetingRejected,
    MeetingTemporarilyUnavailable,
)

TIMEOUT = httpx.Timeout(10.0, connect=5.0)


def retry_after(response: httpx.Response) -> float | None:
    try:
        return float(response.headers.get("retry-after", ""))
    except ValueError:
        return None


def raise_for(response: httpx.Response, what: str) -> NoReturn:
    """Turn a failed provider response into one of the three adapter errors."""
    status = response.status_code
    detail = f"{what}: {status}"
    if status in (401, 403):
        raise MeetingMisconfigured(detail)
    if status in (408, 409, 425, 429) or status >= 500:
        raise MeetingTemporarilyUnavailable(detail, retry_after(response))
    raise MeetingRejected(detail)


def transport_failure(what: str, exc: Exception) -> NoReturn:
    raise MeetingTemporarilyUnavailable(f"{what}: {type(exc).__name__}") from exc
