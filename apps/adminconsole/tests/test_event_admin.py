import csv
import io
import uuid
from datetime import timedelta

import pytest
from django.utils import timezone

from apps.audit.models import AuditLog
from apps.events.models import Event, EventRegistration

pytestmark = pytest.mark.django_db

ADMIN = "/api/v1/admin/events"
MEMBER_EVENTS = "/api/v1/events"


def payload(**overrides):
    start = timezone.now() + timedelta(days=5)
    body = {
        "type": "meetup",
        "title": "Founders meetup",
        "description": "<p>Come and meet.</p>",
        "starts_at": start.isoformat(),
        "ends_at": (start + timedelta(hours=3)).isoformat(),
        "timezone": "Africa/Nairobi",
        "location": "Nairobi",
    }
    body.update(overrides)
    return body


@pytest.fixture
def admin(make_user):
    return make_user(roles=("community_admin",), email="admin@example.com")


@pytest.fixture
def as_admin(admin, client_for):
    return client_for(admin, mfa_age=5)


@pytest.fixture
def as_admin_stale(admin, client_for):
    """MFA passed an hour ago: fine for most things, not for personal data."""
    return client_for(admin, mfa_age=3600)


@pytest.fixture
def member(make_user):
    return make_user(
        email="member@example.com", approved_at=timezone.now(), email_verified_at=timezone.now()
    )


@pytest.fixture
def member_client(member, client_for):
    return client_for(member)


@pytest.fixture
def other_client(make_user, client_for):
    return client_for(
        make_user(
            email="other@example.com", approved_at=timezone.now(), email_verified_at=timezone.now()
        )
    )


def create(client, **overrides):
    response = client.post(ADMIN, payload(**overrides), format="json")
    assert response.status_code == 201, response.content
    return response.json()


def published(client, **overrides):
    event = create(client, **overrides)
    assert client.post(f"{ADMIN}/{event['id']}/publish").status_code == 200
    return event


# --- creating and editing ---


def test_an_admin_creates_a_draft_that_members_cannot_see(as_admin, member_client):
    event = create(as_admin, capacity=50, public=True)
    assert (
        event["status"] == "draft"
        and event["capacity"] == 50
        and event["timezone"] == "Africa/Nairobi"
    )
    assert member_client.get(f"{MEMBER_EVENTS}/{event['id']}").status_code == 404
    assert AuditLog.objects.filter(action="events.created").exists()


@pytest.mark.parametrize(
    "overrides",
    [
        {"type": "party"},
        {"title": ""},
        {"description": "<p></p>"},
        {"timezone": "Mars/Olympus"},
        {"capacity": 0},
        {"link": "http://insecure.example.com"},
        {"recording_url": "javascript:alert(1)"},
        {"ends_at": (timezone.now() + timedelta(days=4)).isoformat()},  # before the start
        {"ends_at": (timezone.now() + timedelta(days=40)).isoformat()},  # longer than 14 days
        {"status": "published"},
        {"slug": "x"},
    ],
)
def test_invalid_events_are_refused(as_admin, overrides):
    assert as_admin.post(ADMIN, payload(**overrides), format="json").status_code == 400
    assert Event.objects.count() == 0


def test_rich_text_is_cleaned(as_admin):
    event = create(as_admin, description="<h2>Plan</h2><script>x()</script><p onclick='y()'>go</p>")
    assert "<script" not in event["description"] and "onclick" not in event["description"]


def test_editing_needs_the_etag_and_a_cancelled_event_is_frozen(as_admin):
    event = create(as_admin)
    url = f"{ADMIN}/{event['id']}"
    etag = as_admin.get(url)["ETag"]
    assert (
        as_admin.patch(url, {"title": "Renamed"}, format="json", HTTP_IF_MATCH=etag).json()["title"]
        == "Renamed"
    )
    assert as_admin.patch(url, {"title": "x"}, format="json").status_code == 428
    assert as_admin.patch(url, {"title": "x"}, format="json", HTTP_IF_MATCH=etag).status_code == 412
    as_admin.post(f"{ADMIN}/{event['id']}/publish")
    as_admin.post(f"{ADMIN}/{event['id']}/cancel")
    fresh = as_admin.get(url)["ETag"]
    assert (
        as_admin.patch(url, {"title": "x"}, format="json", HTTP_IF_MATCH=fresh).status_code == 409
    )


def test_capacity_cannot_drop_below_the_number_registered(as_admin, member_client, other_client):
    event = published(as_admin, capacity=5)
    member_client.post(f"{MEMBER_EVENTS}/{event['id']}/register")
    other_client.post(f"{MEMBER_EVENTS}/{event['id']}/register")
    url = f"{ADMIN}/{event['id']}"
    etag = as_admin.get(url)["ETag"]
    assert (
        as_admin.patch(url, {"capacity": 1}, format="json", HTTP_IF_MATCH=etag).status_code == 400
    )
    assert (
        as_admin.patch(url, {"capacity": 2}, format="json", HTTP_IF_MATCH=etag).status_code == 200
    )


def test_the_archive_fields_can_be_added_after_the_event(as_admin, member_client):
    event = published(as_admin)
    Event.objects.filter(pk=event["id"]).update(
        starts_at=timezone.now() - timedelta(days=1), ends_at=timezone.now() - timedelta(hours=22)
    )
    url = f"{ADMIN}/{event['id']}"
    etag = as_admin.get(url)["ETag"]
    done = as_admin.patch(
        url,
        {"recording_url": "https://video.example.com/r", "summary": "<p>Great night</p>"},
        format="json",
        HTTP_IF_MATCH=etag,
    )
    assert done.status_code == 200
    seen = member_client.get(f"{MEMBER_EVENTS}/{event['id']}").json()
    assert (
        seen["recording_url"] == "https://video.example.com/r"
        and seen["summary"] == "<p>Great night</p>"
    )


# --- publishing, unpublishing, cancelling ---


def test_publishing_needs_a_future_start(as_admin):
    event = create(as_admin)
    Event.objects.filter(pk=event["id"]).update(
        starts_at=timezone.now() - timedelta(days=1), ends_at=timezone.now() - timedelta(hours=23)
    )
    assert as_admin.post(f"{ADMIN}/{event['id']}/publish").status_code == 400


def test_the_lifecycle_actions_enforce_the_state(as_admin, member_client):
    event = create(as_admin)
    base = f"{ADMIN}/{event['id']}"
    assert as_admin.post(f"{base}/cancel").status_code == 409  # not published yet
    assert as_admin.post(f"{base}/unpublish").status_code == 409
    assert as_admin.post(f"{base}/publish").json()["status"] == "published"
    assert as_admin.post(f"{base}/publish").status_code == 409
    assert as_admin.post(f"{base}/unpublish").json()["status"] == "draft"
    as_admin.post(f"{base}/publish")
    member_client.post(f"{MEMBER_EVENTS}/{event['id']}/register")
    assert (
        as_admin.post(f"{base}/unpublish").status_code == 409
    )  # people registered: cancel instead
    cancelled = as_admin.post(f"{base}/cancel", {"reason": "Venue flooded"}, format="json")
    assert (
        cancelled.json()["status"] == "cancelled" and cancelled.json()["registration_open"] is False
    )
    assert AuditLog.objects.filter(action="events.cancelled", reason="Venue flooded").exists()


def test_removing_hides_an_event_everywhere(as_admin, member_client):
    event = published(as_admin)
    assert as_admin.delete(f"{ADMIN}/{event['id']}").status_code == 204
    assert member_client.get(f"{MEMBER_EVENTS}/{event['id']}").status_code == 404
    assert as_admin.get(f"{ADMIN}/{event['id']}").status_code == 404
    assert as_admin.delete(f"{ADMIN}/{event['id']}").status_code == 404


def test_the_listing_filters(as_admin):
    create(as_admin, title="Alpha meetup", type="meetup")
    published(as_admin, title="Beta workshop", type="workshop")
    assert as_admin.get(ADMIN).json()["count"] == 2
    assert as_admin.get(ADMIN, {"status": "published"}).json()["count"] == 1
    assert as_admin.get(ADMIN, {"type": "meetup"}).json()["count"] == 1
    assert as_admin.get(ADMIN, {"q": "beta"}).json()["count"] == 1


@pytest.mark.parametrize("params", [{"status": "removed"}, {"type": "x"}, {"limit": 0}, {"z": 1}])
def test_bad_listing_queries_are_refused(as_admin, params):
    assert as_admin.get(ADMIN, params).status_code == 400


# --- demo days ---


def test_a_demo_day_gets_its_pitch_order(as_admin, member_client, make_user, client_for):
    from apps.startups.tests.conftest import STARTUPS, new_startup_body

    founder = client_for(
        make_user(
            email="f@example.com", approved_at=timezone.now(), email_verified_at=timezone.now()
        )
    )
    a = founder.post(STARTUPS, new_startup_body(name="Alpha")).json()["id"]
    b = founder.post(STARTUPS, new_startup_body(name="Beta")).json()["id"]
    event = published(as_admin, type="demo_day")
    url = f"{ADMIN}/{event['id']}/slots"
    done = as_admin.put(
        url,
        {
            "slots": [
                {"startup_id": b, "pitch_link": "https://pitch.example.com/b"},
                {"startup_id": a},
            ]
        },
        format="json",
    )
    assert done.status_code == 200
    assert [(s["position"], s["startup"]["name"]) for s in done.json()["slots"]] == [
        (1, "Beta"),
        (2, "Alpha"),
    ]
    swapped = as_admin.put(
        url, {"slots": [{"startup_id": a}, {"startup_id": b}]}, format="json"
    ).json()
    assert [s["startup"]["name"] for s in swapped["slots"]] == ["Alpha", "Beta"]
    assert as_admin.put(url, {"slots": []}, format="json").json()["slots"] == []


def test_slots_are_validated(as_admin):
    event = published(as_admin, type="demo_day")
    url = f"{ADMIN}/{event['id']}/slots"
    unknown = str(uuid.uuid4())
    assert as_admin.put(url, {"slots": [{"startup_id": unknown}]}, format="json").status_code == 400
    assert (
        as_admin.put(url, {"slots": [{"startup_id": unknown}] * 2}, format="json").status_code
        == 400
    )
    assert (
        as_admin.put(url, {"slots": [{"startup_id": unknown}] * 21}, format="json").status_code
        == 400
    )
    assert (
        as_admin.put(
            url,
            {"slots": [{"startup_id": unknown, "pitch_link": "http://x.example.com"}]},
            format="json",
        ).status_code
        == 400
    )
    meetup = published(as_admin, type="meetup")
    assert (
        as_admin.put(f"{ADMIN}/{meetup['id']}/slots", {"slots": []}, format="json").status_code
        == 409
    )


# --- rescheduling ---


def test_moving_a_published_event_tells_registrants(as_admin, member_client, member, run_outbox):
    event = published(as_admin)
    member_client.post(f"{MEMBER_EVENTS}/{event['id']}/register")
    url = f"{ADMIN}/{event['id']}"
    etag = as_admin.get(url)["ETag"]
    start = timezone.now() + timedelta(days=9)
    as_admin.patch(
        url,
        {"starts_at": start.isoformat(), "ends_at": (start + timedelta(hours=2)).isoformat()},
        format="json",
        HTTP_IF_MATCH=etag,
    )
    run_outbox()
    titles = [n["title"] for n in member_client.get("/api/v1/notifications").json()["results"]]
    assert any("has new times" in t for t in titles)


# --- attendees ---


def test_the_attendee_list_shows_names_and_emails_and_is_logged(as_admin, member_client, member):
    event = published(as_admin)
    member_client.post(f"{MEMBER_EVENTS}/{event['id']}/register")
    page = as_admin.get(f"{ADMIN}/{event['id']}/attendees").json()
    assert page["count"] == 1
    row = page["results"][0]
    assert row["email"] == "member@example.com" and row["user_id"] == str(member.pk)
    assert row["checked_in_at"] is None
    assert AuditLog.objects.filter(action="events.attendees_viewed").count() == 1


def test_the_csv_export_is_safe_for_spreadsheets_and_logged(as_admin, member_client, member):
    from apps.profiles.services import get_or_create_profile

    profile = get_or_create_profile(member.pk)
    profile.full_name = '=HYPERLINK("http://evil.example")'
    profile.save()
    event = published(as_admin)
    member_client.post(f"{MEMBER_EVENTS}/{event['id']}/register")
    response = as_admin.get(f"{ADMIN}/{event['id']}/attendees.csv")
    assert response.status_code == 200 and response["Content-Type"].startswith("text/csv")
    assert (
        response["Content-Disposition"].endswith('-attendees.csv"')
        and response["Cache-Control"] == "private, no-store"
    )
    rows = list(csv.reader(io.StringIO(response.content.decode())))
    assert rows[0] == ["name", "email", "registered_at", "checked_in_at"]
    assert rows[1][0].startswith("'=") and rows[1][1] == "member@example.com"
    assert AuditLog.objects.filter(action="events.attendees_exported").count() == 1


def test_personal_data_needs_a_fresh_mfa_check(as_admin, as_admin_stale):
    event = published(as_admin)
    assert as_admin_stale.get(ADMIN).status_code == 200  # ordinary admin work is fine
    for tail in ("/attendees", "/attendees.csv"):
        response = as_admin_stale.get(f"{ADMIN}/{event['id']}{tail}")
        assert response.status_code == 403 and response.json()["code"] == "step_up_required"


def test_check_in_and_out(as_admin, member_client, member):
    event = published(as_admin)
    member_client.post(f"{MEMBER_EVENTS}/{event['id']}/register")
    url = f"{ADMIN}/{event['id']}/attendees/{member.pk}/check-in"
    assert as_admin.post(url, {}, format="json").status_code == 204
    assert EventRegistration.objects.get().checked_in_at is not None
    assert as_admin.post(url, {"present": False}, format="json").status_code == 204
    assert EventRegistration.objects.get().checked_in_at is None
    assert (
        as_admin.post(
            f"{ADMIN}/{event['id']}/attendees/{uuid.uuid4()}/check-in", {}, format="json"
        ).status_code
        == 404
    )
    assert AuditLog.objects.filter(action="events.check_in").exists()


def test_unknown_events_are_404_for_attendee_tools(as_admin):
    assert as_admin.get(f"{ADMIN}/{uuid.uuid4()}/attendees").status_code == 404
    assert as_admin.get(f"{ADMIN}/{uuid.uuid4()}/attendees.csv").status_code == 404


# --- access control ---


ENDPOINTS = [
    ("get", ADMIN),
    ("post", ADMIN),
    ("get", f"{ADMIN}/{uuid.uuid4()}"),
    ("patch", f"{ADMIN}/{uuid.uuid4()}"),
    ("delete", f"{ADMIN}/{uuid.uuid4()}"),
    ("post", f"{ADMIN}/{uuid.uuid4()}/publish"),
    ("post", f"{ADMIN}/{uuid.uuid4()}/unpublish"),
    ("post", f"{ADMIN}/{uuid.uuid4()}/cancel"),
    ("put", f"{ADMIN}/{uuid.uuid4()}/slots"),
    ("get", f"{ADMIN}/{uuid.uuid4()}/attendees"),
    ("get", f"{ADMIN}/{uuid.uuid4()}/attendees.csv"),
    ("post", f"{ADMIN}/{uuid.uuid4()}/attendees/{uuid.uuid4()}/check-in"),
]


@pytest.mark.parametrize("method, url", ENDPOINTS)
def test_visitors_and_members_cannot_use_the_event_tools(api_client, member_client, method, url):
    assert getattr(api_client, method)(url).status_code == 401
    assert getattr(member_client, method)(url).status_code == 403


@pytest.mark.parametrize("method, url", ENDPOINTS)
def test_content_editors_cannot_manage_events(make_user, client_for, method, url):
    editor = client_for(make_user(roles=("content_editor",), email="e@example.com"), mfa_age=5)
    assert getattr(editor, method)(url).status_code == 403


@pytest.mark.parametrize("method, url", ENDPOINTS)
def test_admins_without_a_recent_mfa_check_are_refused(admin, client_for, method, url):
    assert getattr(client_for(admin), method)(url).status_code == 403
