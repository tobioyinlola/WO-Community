import json
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from django.core.cache import cache
from django.core.exceptions import ImproperlyConfigured

from apps.integrations.meetings import (
    MeetingMisconfigured,
    MeetingRejected,
    MeetingTemporarilyUnavailable,
    get_meeting_provider,
)
from apps.integrations.meetings.fake import FakeMeetingProvider
from apps.integrations.meetings.google import GoogleMeetProvider
from apps.integrations.meetings.zoom import ZoomProvider

START = datetime(2026, 11, 3, 9, 0, tzinfo=UTC)
END = START + timedelta(minutes=45)
ARGS = {
    "title": "WO Community mentoring: Fundraising",
    "starts_at": START,
    "ends_at": END,
    "attendee_emails": ["ada@example.com", "kofi@example.com"],
    "idempotency_key": "session-1",
}


class Recorder:
    """A fake provider API: records requests and answers with the canned response."""

    def __init__(self, handler):
        self.handler = handler
        self.requests: list[httpx.Request] = []

    def __call__(self, request):
        self.requests.append(request)
        return self.handler(request)

    def calls(self, path_part):
        return [r for r in self.requests if path_part in r.url.path]


def client_for(recorder):
    return httpx.Client(transport=httpx.MockTransport(recorder))


@pytest.fixture(autouse=True)
def _credentials(settings):
    settings.GOOGLE_MEET_CLIENT_ID = "gid"
    settings.GOOGLE_MEET_CLIENT_SECRET = "gsecret"  # noqa: S105  # nosec B105
    settings.GOOGLE_MEET_REFRESH_TOKEN = "grefresh"  # noqa: S105  # nosec B105
    settings.GOOGLE_MEET_CALENDAR_ID = "primary"
    settings.ZOOM_ACCOUNT_ID = "zacct"
    settings.ZOOM_CLIENT_ID = "zid"
    settings.ZOOM_CLIENT_SECRET = "zsecret"  # noqa: S105  # nosec B105
    cache.clear()


# --- Google Meet ---


def google_ok(request):
    if request.url.host == "oauth2.googleapis.com":
        return httpx.Response(200, json={"access_token": "tok-1", "expires_in": 3600})
    if request.method == "POST":
        return httpx.Response(
            200, json={"id": "evt1", "hangoutLink": "https://meet.google.com/abc-defg-hij"}
        )
    return httpx.Response(200, json={"id": "evt1"})


def test_google_creates_an_event_with_a_meet_link():
    recorder = Recorder(google_ok)
    meeting = GoogleMeetProvider(client_for(recorder)).create(**ARGS)
    assert (meeting.provider, meeting.external_id) == ("google_meet", "evt1")
    assert meeting.join_url == "https://meet.google.com/abc-defg-hij"

    token = recorder.calls("/token")[0]
    assert b"grant_type=refresh_token" in token.content and b"grefresh" in token.content
    create = recorder.calls("/events")[0]
    assert create.headers["authorization"] == "Bearer tok-1"
    assert create.url.params["conferenceDataVersion"] == "1"
    assert create.url.params["sendUpdates"] == "none"  # the platform sends its own notices
    body = json.loads(create.content)
    assert body["start"]["dateTime"] == "2026-11-03T09:00:00Z"
    assert body["end"]["dateTime"] == "2026-11-03T09:45:00Z"
    assert body["attendees"] == [{"email": "ada@example.com"}, {"email": "kofi@example.com"}]
    assert body["conferenceData"]["createRequest"]["requestId"] == "wo-session-1"


def test_google_reuses_the_access_token_and_refreshes_a_rejected_one():
    state = {"first": True}

    def handler(request):
        if request.url.host == "oauth2.googleapis.com":
            n = len([r for r in recorder.requests if r.url.host == "oauth2.googleapis.com"])
            return httpx.Response(200, json={"access_token": f"tok-{n}", "expires_in": 3600})
        if request.headers["authorization"] == "Bearer tok-1" and state["first"]:
            state["first"] = False
            return httpx.Response(401, json={"error": "expired"})
        return httpx.Response(200, json={"id": "evt1", "hangoutLink": "https://meet.google.com/x"})

    recorder = Recorder(handler)
    provider = GoogleMeetProvider(client_for(recorder))
    provider.create(**ARGS)
    assert len(recorder.calls("/token")) == 2  # the 401 forced one more
    provider.create(**ARGS)
    assert len(recorder.calls("/token")) == 2  # then the token was reused


def test_google_moves_and_deletes_events():
    recorder = Recorder(google_ok)
    provider = GoogleMeetProvider(client_for(recorder))
    provider.reschedule(external_id="evt1", starts_at=START, ends_at=END)
    patch = recorder.calls("/events/evt1")[0]
    assert patch.method == "PATCH"
    assert json.loads(patch.content)["start"]["dateTime"] == "2026-11-03T09:00:00Z"

    gone = Recorder(lambda r: httpx.Response(410) if r.method == "DELETE" else google_ok(r))
    GoogleMeetProvider(client_for(gone)).cancel(external_id="evt1")  # already deleted: fine


@pytest.mark.parametrize(
    ("status", "error"),
    [
        (400, MeetingRejected),
        (404, MeetingRejected),
        (403, MeetingMisconfigured),
        (429, MeetingTemporarilyUnavailable),
        (503, MeetingTemporarilyUnavailable),
    ],
)
def test_google_failures_are_sorted_by_whether_retrying_helps(status, error):
    def handler(request):
        if request.url.host == "oauth2.googleapis.com":
            return httpx.Response(200, json={"access_token": "t", "expires_in": 3600})
        return httpx.Response(status, json={"error": "x"})

    with pytest.raises(error):
        GoogleMeetProvider(client_for(Recorder(handler))).create(**ARGS)


def test_google_without_a_meeting_link_is_a_rejection():
    def handler(request):
        if request.url.host == "oauth2.googleapis.com":
            return httpx.Response(200, json={"access_token": "t", "expires_in": 3600})
        return httpx.Response(200, json={"id": "evt1"})

    with pytest.raises(MeetingRejected):
        GoogleMeetProvider(client_for(Recorder(handler))).create(**ARGS)


def test_a_revoked_google_token_is_a_configuration_problem():
    def handler(request):
        return httpx.Response(400, json={"error": "invalid_grant"})

    with pytest.raises(MeetingMisconfigured):
        GoogleMeetProvider(client_for(Recorder(handler))).create(**ARGS)


def test_network_failures_are_temporary():
    def handler(request):
        raise httpx.ConnectTimeout("slow")

    with pytest.raises(MeetingTemporarilyUnavailable):
        GoogleMeetProvider(client_for(Recorder(handler))).create(**ARGS)


def test_google_needs_credentials(settings):
    settings.GOOGLE_MEET_REFRESH_TOKEN = ""
    with pytest.raises(ImproperlyConfigured):
        GoogleMeetProvider()


# --- Zoom ---


def zoom_ok(request):
    if request.url.host == "zoom.us":
        return httpx.Response(200, json={"access_token": "ztok", "expires_in": 3600})
    if request.method == "POST":
        return httpx.Response(
            201, json={"id": 987654321, "join_url": "https://zoom.us/j/987654321"}
        )
    return httpx.Response(204)


def test_zoom_creates_a_scheduled_meeting():
    recorder = Recorder(zoom_ok)
    meeting = ZoomProvider(client_for(recorder)).create(**ARGS)
    assert (meeting.provider, meeting.external_id) == ("zoom", "987654321")
    assert meeting.join_url == "https://zoom.us/j/987654321"

    token = recorder.calls("/oauth/token")[0]
    assert token.url.params["grant_type"] == "account_credentials"
    assert token.url.params["account_id"] == "zacct"
    assert token.headers["authorization"].startswith("Basic ")
    create = recorder.calls("/meetings")[0]
    body = json.loads(create.content)
    assert body["start_time"] == "2026-11-03T09:00:00Z" and body["duration"] == 45
    assert body["settings"]["waiting_room"] is True
    assert body["settings"]["email_notification"] is False


def test_zoom_moves_and_deletes_meetings():
    recorder = Recorder(zoom_ok)
    provider = ZoomProvider(client_for(recorder))
    provider.reschedule(external_id="987654321", starts_at=START, ends_at=END)
    provider.cancel(external_id="987654321")
    methods = [r.method for r in recorder.requests if "/meetings/987654321" in r.url.path]
    assert methods == ["PATCH", "DELETE"]
    missing = Recorder(lambda r: httpx.Response(404) if r.method == "DELETE" else zoom_ok(r))
    ZoomProvider(client_for(missing)).cancel(external_id="1")  # already gone: fine


@pytest.mark.parametrize(
    ("status", "error"),
    [
        (400, MeetingRejected),
        (429, MeetingTemporarilyUnavailable),
        (500, MeetingTemporarilyUnavailable),
        (403, MeetingMisconfigured),
    ],
)
def test_zoom_failures_are_sorted_by_whether_retrying_helps(status, error):
    def handler(request):
        if request.url.host == "zoom.us":
            return httpx.Response(200, json={"access_token": "t", "expires_in": 3600})
        return httpx.Response(status, json={})

    with pytest.raises(error):
        ZoomProvider(client_for(Recorder(handler))).create(**ARGS)


def test_zoom_needs_credentials(settings):
    settings.ZOOM_CLIENT_SECRET = ""
    with pytest.raises(ImproperlyConfigured):
        ZoomProvider()


# --- choosing an adapter ---


def test_the_provider_is_chosen_by_name_with_a_platform_default(settings):
    settings.MEETING_DEFAULT_PROVIDER = "zoom"
    assert get_meeting_provider("google_meet").name == "google_meet"
    assert get_meeting_provider().name == "zoom"
    assert isinstance(get_meeting_provider("zoom"), FakeMeetingProvider)  # the test settings
    with pytest.raises(MeetingMisconfigured):
        get_meeting_provider("skype")
