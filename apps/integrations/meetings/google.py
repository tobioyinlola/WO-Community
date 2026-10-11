"""Google Meet links, made as events on one platform Google Calendar.

The adapter trades a stored OAuth refresh token for a short lived access token, then asks the
Calendar API to create an event with a Meet conference. The event id doubles as the meeting id,
and the conference request id is derived from the booking, so a repeat of the same create asks
for the same conference instead of a second one. ``sendUpdates=none`` keeps Google from emailing
anyone; the platform sends its own notices.
"""

from datetime import UTC, datetime
from functools import cached_property
from typing import Any

import httpx
from django.conf import settings
from django.core.cache import cache
from django.core.exceptions import ImproperlyConfigured

from apps.integrations.meetings._http import TIMEOUT, raise_for, transport_failure
from apps.integrations.meetings.base import (
    Meeting,
    MeetingMisconfigured,
    MeetingProvider,
    MeetingRejected,
)

TOKEN_URL = "https://oauth2.googleapis.com/token"  # noqa: S105  # nosec B105
API_URL = "https://www.googleapis.com/calendar/v3"
TOKEN_CACHE_KEY = "meetings:google:token"  # noqa: S105  # nosec B105


def _iso(value: datetime) -> str:
    return value.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


class GoogleMeetProvider(MeetingProvider):
    name = "google_meet"

    def __init__(self, client: httpx.Client | None = None) -> None:
        if client is None and not (
            settings.GOOGLE_MEET_CLIENT_ID
            and settings.GOOGLE_MEET_CLIENT_SECRET
            and settings.GOOGLE_MEET_REFRESH_TOKEN
        ):
            raise ImproperlyConfigured("The Google Meet credentials are not set")
        self._client = client

    @cached_property
    def client(self) -> httpx.Client:
        return self._client or httpx.Client(timeout=TIMEOUT)

    # --- authentication ------------------------------------------------------------------------

    def _token(self) -> str:
        cached = cache.get(TOKEN_CACHE_KEY)
        if cached:
            return str(cached)
        try:
            response = self.client.post(
                TOKEN_URL,
                data={
                    "grant_type": "refresh_token",
                    "client_id": settings.GOOGLE_MEET_CLIENT_ID,
                    "client_secret": settings.GOOGLE_MEET_CLIENT_SECRET,
                    "refresh_token": settings.GOOGLE_MEET_REFRESH_TOKEN,
                },
            )
        except httpx.HTTPError as exc:
            transport_failure("google token", exc)
        if response.status_code in (400, 401):
            # invalid_grant and friends: the refresh token was revoked or is wrong.
            raise MeetingMisconfigured("google token: refresh token not accepted")
        if response.status_code != 200:
            raise_for(response, "google token")
        body = response.json()
        token = str(body["access_token"])
        cache.set(TOKEN_CACHE_KEY, token, max(60, int(body.get("expires_in", 3600)) - 120))
        return token

    def _send(self, method: str, path: str, what: str, **kwargs: Any) -> httpx.Response:
        url = f"{API_URL}/calendars/{settings.GOOGLE_MEET_CALENDAR_ID}/events{path}"
        for attempt in (1, 2):
            try:
                response = self.client.request(
                    method, url, headers={"Authorization": f"Bearer {self._token()}"}, **kwargs
                )
            except httpx.HTTPError as exc:
                transport_failure(what, exc)
            if response.status_code == 401 and attempt == 1:
                cache.delete(TOKEN_CACHE_KEY)  # the access token lapsed early; fetch another
                continue
            return response
        return response  # pragma: no cover

    # --- the interface -------------------------------------------------------------------------

    def create(
        self,
        *,
        title: str,
        starts_at: datetime,
        ends_at: datetime,
        attendee_emails: list[str],
        idempotency_key: str,
    ) -> Meeting:
        body = {
            "summary": title,
            "start": {"dateTime": _iso(starts_at), "timeZone": "UTC"},
            "end": {"dateTime": _iso(ends_at), "timeZone": "UTC"},
            "attendees": [{"email": email} for email in attendee_emails],
            "guestsCanInviteOthers": False,
            "guestsCanModify": False,
            "conferenceData": {
                "createRequest": {
                    "requestId": f"wo-{idempotency_key}",
                    "conferenceSolutionKey": {"type": "hangoutsMeet"},
                }
            },
        }
        response = self._send(
            "POST",
            "",
            "google create",
            params={"conferenceDataVersion": "1", "sendUpdates": "none"},
            json=body,
        )
        if response.status_code != 200:
            raise_for(response, "google create")
        event = response.json()
        link = event.get("hangoutLink") or next(
            (
                point.get("uri", "")
                for point in event.get("conferenceData", {}).get("entryPoints", [])
                if point.get("entryPointType") == "video"
            ),
            "",
        )
        if not link:
            raise MeetingRejected("google create: no meeting link in the response")
        return Meeting(self.name, str(event["id"]), str(link))

    def reschedule(self, *, external_id: str, starts_at: datetime, ends_at: datetime) -> None:
        response = self._send(
            "PATCH",
            f"/{external_id}",
            "google reschedule",
            params={"sendUpdates": "none"},
            json={
                "start": {"dateTime": _iso(starts_at), "timeZone": "UTC"},
                "end": {"dateTime": _iso(ends_at), "timeZone": "UTC"},
            },
        )
        if response.status_code != 200:
            raise_for(response, "google reschedule")

    def cancel(self, *, external_id: str) -> None:
        response = self._send(
            "DELETE", f"/{external_id}", "google cancel", params={"sendUpdates": "none"}
        )
        if response.status_code in (200, 204, 404, 410):
            return
        raise_for(response, "google cancel")
