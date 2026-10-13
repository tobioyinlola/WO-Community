"""Zoom meetings, made with a Server-to-Server OAuth app on the platform account.

Zoom has no idempotency key, so the booking id is not sent; callers record the meeting id as soon
as the call returns and never create twice for one booking.
"""

from datetime import UTC, datetime
from functools import cached_property
from typing import Any

import httpx
from django.conf import settings
from django.core.cache import cache
from django.core.exceptions import ImproperlyConfigured

from apps.integrations.meetings._http import TIMEOUT, raise_for, transport_failure
from apps.integrations.meetings.base import Meeting, MeetingMisconfigured, MeetingProvider

TOKEN_URL = "https://zoom.us/oauth/token"  # noqa: S105  # nosec B105
API_URL = "https://api.zoom.us/v2"
TOKEN_CACHE_KEY = "meetings:zoom:token"  # noqa: S105  # nosec B105


def _iso(value: datetime) -> str:
    return value.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


class ZoomProvider(MeetingProvider):
    name = "zoom"

    def __init__(self, client: httpx.Client | None = None) -> None:
        if client is None and not (
            settings.ZOOM_ACCOUNT_ID and settings.ZOOM_CLIENT_ID and settings.ZOOM_CLIENT_SECRET
        ):
            raise ImproperlyConfigured("The Zoom credentials are not set")
        self._client = client

    @cached_property
    def client(self) -> httpx.Client:
        return self._client or httpx.Client(timeout=TIMEOUT)

    def _token(self) -> str:
        cached = cache.get(TOKEN_CACHE_KEY)
        if cached:
            return str(cached)
        try:
            response = self.client.post(
                TOKEN_URL,
                params={
                    "grant_type": "account_credentials",
                    "account_id": settings.ZOOM_ACCOUNT_ID,
                },
                auth=(settings.ZOOM_CLIENT_ID, settings.ZOOM_CLIENT_SECRET),
            )
        except httpx.HTTPError as exc:
            transport_failure("zoom token", exc)
        if response.status_code in (400, 401):
            raise MeetingMisconfigured("zoom token: credentials not accepted")
        if response.status_code != 200:
            raise_for(response, "zoom token")
        body = response.json()
        token = str(body["access_token"])
        cache.set(TOKEN_CACHE_KEY, token, max(60, int(body.get("expires_in", 3600)) - 120))
        return token

    def _send(self, method: str, path: str, what: str, **kwargs: Any) -> httpx.Response:
        for attempt in (1, 2):
            try:
                response = self.client.request(
                    method,
                    f"{API_URL}{path}",
                    headers={"Authorization": f"Bearer {self._token()}"},
                    **kwargs,
                )
            except httpx.HTTPError as exc:
                transport_failure(what, exc)
            if response.status_code == 401 and attempt == 1:
                cache.delete(TOKEN_CACHE_KEY)
                continue
            return response
        return response  # pragma: no cover

    def create(
        self,
        *,
        title: str,
        starts_at: datetime,
        ends_at: datetime,
        attendee_emails: list[str],
        idempotency_key: str,
    ) -> Meeting:
        minutes = int((ends_at - starts_at).total_seconds() // 60)
        response = self._send(
            "POST",
            "/users/me/meetings",
            "zoom create",
            json={
                "topic": title,
                "type": 2,  # a scheduled meeting
                "start_time": _iso(starts_at),
                "duration": minutes,
                "timezone": "UTC",
                "settings": {
                    "waiting_room": True,
                    "join_before_host": False,
                    "approval_type": 2,  # no registration
                    "meeting_authentication": False,
                    "email_notification": False,
                },
            },
        )
        if response.status_code != 201:
            raise_for(response, "zoom create")
        body = response.json()
        return Meeting(self.name, str(body["id"]), str(body["join_url"]))

    def reschedule(self, *, external_id: str, starts_at: datetime, ends_at: datetime) -> None:
        minutes = int((ends_at - starts_at).total_seconds() // 60)
        response = self._send(
            "PATCH",
            f"/meetings/{external_id}",
            "zoom reschedule",
            json={"start_time": _iso(starts_at), "duration": minutes, "timezone": "UTC"},
        )
        if response.status_code != 204:
            raise_for(response, "zoom reschedule")

    def cancel(self, *, external_id: str) -> None:
        response = self._send(
            "DELETE",
            f"/meetings/{external_id}",
            "zoom cancel",
            params={"schedule_for_reminder": "false", "cancel_meeting_reminder": "false"},
        )
        if response.status_code in (200, 204, 404):
            return
        raise_for(response, "zoom cancel")
