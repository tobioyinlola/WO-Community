import uuid

import pytest

from apps.accounts.models import UserRole
from apps.audit.models import AuditLog
from apps.mentorship.models import MentorProfile
from apps.mentorship.tests.conftest import active, application_body

pytestmark = pytest.mark.django_db

MINE = "/api/v1/me/mentor-profile"
LIST = "/api/v1/mentors"
ADMIN = "/api/v1/admin/mentors"


def set_name(user, name, country="NG"):
    from apps.profiles.models import FounderProfile
    from apps.profiles.services import get_or_create_profile

    FounderProfile.objects.filter(pk=get_or_create_profile(user.pk).pk).update(
        full_name=name, country=country
    )


@pytest.fixture
def seeker_client(make_user, client_for):
    return client_for(active(make_user, "seeker@example.com"))


# --- the mentor section ---


def test_a_mentor_has_a_section_visible_to_members(mentor, seeker_client):
    set_name(mentor, "Ada Obi")
    body = seeker_client.get(f"{LIST}/{mentor.pk}").json()
    assert body["name"] == "Ada Obi" and body["company"] == "Savannah Capital"
    assert body["languages"] == [
        {"code": "en", "name": "English"},
        {"code": "fr", "name": "French"},
    ]
    assert body["rating_average"] is None and body["rating_count"] == 0
    assert "email" not in body and "linkedin_url" not in body


def test_members_who_are_not_mentors_have_no_section(seeker_client, other):
    assert seeker_client.get(f"{LIST}/{other.pk}").status_code == 404
    assert seeker_client.get(f"{LIST}/{uuid.uuid4()}").status_code == 404


def test_a_mentor_edits_their_section_and_can_pause(mentor, applicant_client, seeker_client):
    response = applicant_client.put(
        MINE,
        {"about": "Ask me about term sheets.", "capacity_per_week": 5, "paused": True},
        format="json",
    )
    assert response.status_code == 200 and response.json()["paused"] is True
    assert seeker_client.get(f"{LIST}/{mentor.pk}").status_code == 404  # paused: not listed
    assert applicant_client.get(f"{LIST}/{mentor.pk}").status_code == 200  # but visible to them
    assert seeker_client.get(LIST).json()["results"] == []
    applicant_client.put(MINE, {"paused": False}, format="json")
    assert len(seeker_client.get(LIST).json()["results"]) == 1


@pytest.mark.parametrize(
    "body",
    [
        {"capacity_per_week": 0},
        {"capacity_per_week": 21},
        {"expertise": []},
        {"timezone": "nowhere"},
        {"about": "x" * 1001},
        {"status": "active"},
    ],
)
def test_profile_changes_are_validated(mentor, applicant_client, body):
    assert applicant_client.put(MINE, body, format="json").status_code == 400


def test_members_who_are_not_mentors_cannot_create_a_section(seeker_client):
    assert seeker_client.put(MINE, {"paused": True}, format="json").status_code == 403
    assert seeker_client.get(MINE).status_code == 404


def test_an_invited_mentor_creates_the_section_with_a_first_save(make_user, client_for):
    invited = make_user(roles=("member", "mentor"), email="invited@example.com")
    client = client_for(invited)
    assert client.put(MINE, {"about": "Hello"}, format="json").status_code == 400  # incomplete
    full = application_body()
    for key in (
        "linkedin_url",
        "weekly_hours",
        "availability_note",
        "motivation",
        "accept_conduct",
    ):
        full.pop(key)
    response = client.put(MINE, full, format="json")
    assert response.status_code == 200 and MentorProfile.objects.get(user=invited)


def test_unauthenticated_callers_get_401(api_client, mentor):
    assert api_client.get(LIST).status_code == 401
    assert api_client.get(f"{LIST}/{mentor.pk}").status_code == 401
    assert api_client.get(MINE).status_code == 401
    assert api_client.put(MINE, {}, format="json").status_code == 401


# --- the directory ---


@pytest.fixture
def two_mentors(mentor, make_user, client_for, as_admin):
    set_name(mentor, "Ada Obi", "NG")
    second = active(make_user, "second@example.com")
    set_name(second, "Kofi Mensah", "GH")
    client = client_for(second)
    created = client.post(
        "/api/v1/mentor-applications",
        application_body(
            expertise=["Product design"],
            industries=["healthtech"],
            stages=["idea"],
            languages=["en"],
            company="Accra Labs",
        ),
        format="json",
    )
    as_admin.post(
        f"/api/v1/admin/mentor-applications/{created.json()['id']}/decision",
        {"decision": "approve"},
        format="json",
    )
    return mentor, second


@pytest.mark.parametrize(
    "query,expected",
    [
        ({}, {"Ada Obi", "Kofi Mensah"}),
        ({"expertise": "fundraising"}, {"Ada Obi"}),
        ({"expertise": "Product  Design"}, {"Kofi Mensah"}),
        ({"industry": "healthtech"}, {"Kofi Mensah"}),
        ({"stage": "seed"}, {"Ada Obi"}),
        ({"language": "fr"}, {"Ada Obi"}),
        ({"country": "GH"}, {"Kofi Mensah"}),
        ({"q": "kofi"}, {"Kofi Mensah"}),
        ({"q": "savannah"}, {"Ada Obi"}),
        ({"q": "product design"}, {"Kofi Mensah"}),
        ({"industry": "fintech", "language": "en"}, {"Ada Obi"}),
        ({"q": "nobody"}, set()),
    ],
)
def test_the_directory_filters(two_mentors, seeker_client, query, expected):
    names = {m["name"] for m in seeker_client.get(LIST, query).json()["results"]}
    assert names == expected


def test_the_directory_pages(two_mentors, seeker_client):
    first = seeker_client.get(LIST, {"limit": 1}).json()
    assert len(first["results"]) == 1 and first["next_cursor"]
    second = seeker_client.get(LIST, {"limit": 1, "cursor": first["next_cursor"]}).json()
    assert len(second["results"]) == 1 and second["next_cursor"] is None
    assert first["results"][0]["id"] != second["results"][0]["id"]
    assert seeker_client.get(LIST, {"cursor": "junk"}).status_code == 400


def test_a_suspended_mentor_disappears_from_the_directory(two_mentors, seeker_client):
    mentor, _ = two_mentors
    mentor.status = "suspended"
    mentor.save()
    assert {m["name"] for m in seeker_client.get(LIST).json()["results"]} == {"Kofi Mensah"}


# --- revoking and restoring ---


def test_revoking_removes_status_and_listing_and_is_audited(
    mentor, as_admin, seeker_client, run_outbox
):
    response = as_admin.post(
        f"{ADMIN}/{mentor.pk}/revoke", {"reason": "Conduct breach"}, format="json"
    )
    assert response.status_code == 200 and response.json()["status"] == "revoked"
    assert not UserRole.objects.filter(user=mentor, role="mentor").exists()
    assert seeker_client.get(f"{LIST}/{mentor.pk}").status_code == 404
    assert AuditLog.objects.get(action="mentors.revoke").reason == "Conduct breach"
    run_outbox()
    from apps.notifications.models import Notification

    assert Notification.objects.filter(user=mentor, type="mentor_revoked").exists()


def test_a_revocation_needs_a_reason_and_cannot_repeat(mentor, as_admin):
    assert as_admin.post(f"{ADMIN}/{mentor.pk}/revoke", {}, format="json").status_code == 400
    assert (
        as_admin.post(f"{ADMIN}/{mentor.pk}/revoke", {"reason": "x"}, format="json").status_code
        == 200
    )
    assert (
        as_admin.post(f"{ADMIN}/{mentor.pk}/revoke", {"reason": "x"}, format="json").status_code
        == 409
    )


def test_revoking_needs_a_recent_mfa_check(mentor, admin, client_for):
    stale = client_for(admin, mfa_age=100_000)
    assert stale.post(
        f"{ADMIN}/{mentor.pk}/revoke", {"reason": "x"}, format="json"
    ).status_code in (
        401,
        403,
    )
    assert MentorProfile.objects.get(user=mentor).status == "active"


def test_a_revoked_mentor_can_be_restored(mentor, as_admin, applicant_client):
    as_admin.post(f"{ADMIN}/{mentor.pk}/revoke", {"reason": "x"}, format="json")
    assert applicant_client.put(MINE, {"paused": True}, format="json").status_code == 403
    assert as_admin.post(f"{ADMIN}/{mentor.pk}/restore").status_code == 200
    assert UserRole.objects.filter(user=mentor, role="mentor").exists()
    assert as_admin.post(f"{ADMIN}/{mentor.pk}/restore").status_code == 409
    assert AuditLog.objects.filter(action="mentors.restore").exists()


def test_a_revoked_mentor_can_apply_and_be_approved_again(mentor, as_admin, applicant_client):
    as_admin.post(f"{ADMIN}/{mentor.pk}/revoke", {"reason": "x"}, format="json")
    created = applicant_client.post(
        "/api/v1/mentor-applications", application_body(company="Fresh Co"), format="json"
    )
    assert created.status_code == 201
    as_admin.post(
        f"/api/v1/admin/mentor-applications/{created.json()['id']}/decision",
        {"decision": "approve"},
        format="json",
    )
    profile = MentorProfile.objects.get(user=mentor)
    assert profile.status == "active" and profile.company == "Fresh Co"


def test_the_admin_list_shows_status(mentor, as_admin):
    assert as_admin.get(ADMIN, {"status": "active"}).json()["count"] == 1
    assert as_admin.get(ADMIN, {"status": "revoked"}).json()["count"] == 0
    assert as_admin.get(ADMIN, {"q": "zzz"}).json()["count"] == 0


def test_admin_mentor_routes_reject_the_wrong_callers(
    mentor, api_client, applicant_client, editor_client
):
    for client, expected in ((api_client, 401), (applicant_client, 403), (editor_client, 403)):
        assert client.get(ADMIN).status_code == expected
        assert (
            client.post(f"{ADMIN}/{mentor.pk}/revoke", {"reason": "x"}, format="json").status_code
            == expected
        )
        assert client.post(f"{ADMIN}/{mentor.pk}/restore").status_code == expected
    assert MentorProfile.objects.get(user=mentor).status == "active"


def test_unknown_mentors_are_404_for_admin_actions(as_admin):
    missing = uuid.uuid4()
    assert (
        as_admin.post(f"{ADMIN}/{missing}/revoke", {"reason": "x"}, format="json").status_code
        == 404
    )
    assert as_admin.post(f"{ADMIN}/{missing}/restore").status_code == 404


# --- elsewhere ---


def test_segments_and_dashboard_know_about_mentors(mentor, as_admin):
    from apps.mentorship import selectors

    assert mentor.pk in selectors.mentor_ids() and mentor.pk in selectors.applicant_ids()
    snapshot = as_admin.get("/api/v1/admin/dashboard").json()["mentorship"]
    assert snapshot["available"] is True and snapshot["active_mentors"] == 1
