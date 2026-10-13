import pytest
from django.utils import timezone

from apps.accounts.models import UserRole
from apps.audit.models import AuditLog
from apps.mentorship.models import MentorApplication, MentorProfile
from apps.mentorship.tests.conftest import application_body
from apps.notifications.models import Notification

pytestmark = pytest.mark.django_db

APPLY = "/api/v1/mentor-applications"
MINE = "/api/v1/me/mentor-application"
QUEUE = "/api/v1/admin/mentor-applications"


def decision(client, application_id, **body):
    return client.post(f"{QUEUE}/{application_id}/decision", body, format="json")


@pytest.fixture
def submitted(applicant_client):
    response = applicant_client.post(APPLY, application_body(), format="json")
    assert response.status_code == 201, response.content
    return response.json()


# --- applying ---


def test_a_member_can_apply_and_sees_it_pending(applicant_client, submitted):
    assert submitted["status"] == "pending"
    assert submitted["expertise"] == ["fundraising", "go-to-market"]
    assert submitted["industries"] == [{"slug": "fintech", "name": "Fintech"}]
    assert applicant_client.get(MINE).json()["id"] == submitted["id"]


def test_applying_does_not_grant_mentor_status(applicant, submitted):
    assert not UserRole.objects.filter(user=applicant, role="mentor").exists()
    assert not MentorProfile.objects.exists()


def test_the_conduct_policy_must_be_accepted(applicant_client):
    response = applicant_client.post(APPLY, application_body(accept_conduct=False), format="json")
    assert response.status_code == 400


@pytest.mark.parametrize(
    "overrides",
    [
        {"expertise": []},
        {"expertise": ["x"]},
        {"expertise": [f"area {i}" for i in range(9)]},
        {"years_experience": 0},
        {"years_experience": 61},
        {"linkedin_url": "https://example.com/in/ada"},
        {"linkedin_url": "http://www.linkedin.com/in/ada"},
        {"linkedin_url": ""},
        {"industries": ["not-a-sector"]},
        {"industries": []},
        {"stages": ["not-a-stage"]},
        {"languages": ["xx"]},
        {"timezone": "Mars/Base"},
        {"weekly_hours": 0},
        {"weekly_hours": 41},
        {"motivation": "Too short."},
        {"current_role": "   "},
    ],
)
def test_invalid_applications_are_refused(applicant_client, overrides):
    response = applicant_client.post(APPLY, application_body(**overrides), format="json")
    assert response.status_code == 400
    assert not MentorApplication.objects.exists()


def test_missing_and_unknown_fields_are_refused(applicant_client):
    body = application_body()
    del body["motivation"]
    assert applicant_client.post(APPLY, body, format="json").status_code == 400
    extra = application_body(status="approved")
    assert applicant_client.post(APPLY, extra, format="json").status_code == 400


def test_markup_is_stripped_from_free_text(applicant_client):
    response = applicant_client.post(
        APPLY,
        application_body(company="<b>Acme</b><script>x()</script>"),
        format="json",
    )
    assert response.json()["company"] == "Acme"


def test_only_one_application_can_be_open(applicant_client, submitted):
    assert applicant_client.post(APPLY, application_body(), format="json").status_code == 409


def test_a_mentor_cannot_apply_again(mentor, applicant_client):
    assert applicant_client.post(APPLY, application_body(), format="json").status_code == 409


def test_a_declined_applicant_waits_thirty_days(applicant_client, as_admin, submitted):
    assert (
        decision(as_admin, submitted["id"], decision="decline", reason="Not yet").status_code == 200
    )
    assert applicant_client.post(APPLY, application_body(), format="json").status_code == 409
    MentorApplication.objects.update(decided_at=timezone.now() - timezone.timedelta(days=31))
    assert applicant_client.post(APPLY, application_body(), format="json").status_code == 201


def test_applying_needs_login_and_an_active_account(api_client, make_user, client_for):
    assert api_client.post(APPLY, application_body(), format="json").status_code == 401
    pending = make_user(email="pending@example.com", status="pending")
    assert client_for(pending).post(APPLY, application_body(), format="json").status_code == 403


def test_an_application_event_is_recorded(applicant, submitted):
    from apps.analytics.models import AnalyticsEvent

    assert AnalyticsEvent.objects.filter(name="mentor_application_submitted").exists()


# --- the applicant's own application ---


def test_there_is_nothing_to_show_before_applying(applicant_client):
    assert applicant_client.get(MINE).status_code == 404


def test_an_open_application_can_be_edited(applicant_client, submitted):
    response = applicant_client.patch(
        f"{APPLY}/{submitted['id']}", {"weekly_hours": 6, "company": "New Co"}, format="json"
    )
    assert response.status_code == 200
    assert response.json()["weekly_hours"] == 6 and response.json()["company"] == "New Co"
    assert response.json()["status"] == "pending"


def test_an_edit_is_validated(applicant_client, submitted):
    response = applicant_client.patch(
        f"{APPLY}/{submitted['id']}", {"timezone": "x"}, format="json"
    )
    assert response.status_code == 400


def test_an_application_can_be_withdrawn_once(applicant_client, submitted):
    assert applicant_client.delete(f"{APPLY}/{submitted['id']}").json()["status"] == "withdrawn"
    assert applicant_client.delete(f"{APPLY}/{submitted['id']}").status_code == 409
    assert (
        applicant_client.patch(
            f"{APPLY}/{submitted['id']}", {"weekly_hours": 2}, format="json"
        ).status_code
        == 409
    )
    assert applicant_client.post(APPLY, application_body(), format="json").status_code == 201


def test_applications_belong_to_their_owner(other_client, submitted):
    url = f"{APPLY}/{submitted['id']}"
    assert other_client.patch(url, {"weekly_hours": 2}, format="json").status_code == 404
    assert other_client.delete(url).status_code == 404
    assert other_client.get(MINE).status_code == 404


def test_unauthenticated_callers_cannot_touch_applications(api_client, submitted):
    url = f"{APPLY}/{submitted['id']}"
    assert api_client.patch(url, {}, format="json").status_code == 401
    assert api_client.delete(url).status_code == 401
    assert api_client.get(MINE).status_code == 401


# --- the admin decision ---


def test_approval_makes_a_mentor_with_a_profile_and_a_badge(
    applicant, applicant_client, as_admin, submitted, run_outbox
):
    response = decision(as_admin, submitted["id"], decision="approve")
    assert response.status_code == 200 and response.json()["status"] == "approved"
    assert UserRole.objects.filter(user=applicant, role="mentor").exists()
    profile = MentorProfile.objects.get(user=applicant)
    assert profile.expertise == ["fundraising", "go-to-market"] and profile.capacity_per_week == 3
    run_outbox()
    item = Notification.objects.get(user=applicant, type="mentor_application_decision")
    assert item.payload["decision"] == "approved"
    from apps.accounts import services as accounts

    assert "mentor" in accounts.badges_for([applicant.pk])[applicant.pk]
    assert AuditLog.objects.filter(action="mentors.approve").exists()


def test_a_decline_needs_a_reason_that_the_applicant_sees(
    applicant, applicant_client, as_admin, submitted, run_outbox
):
    assert decision(as_admin, submitted["id"], decision="decline").status_code == 400
    assert decision(as_admin, submitted["id"], decision="decline", reason="  ").status_code == 400
    response = decision(
        as_admin, submitted["id"], decision="decline", reason="Need more experience"
    )
    assert response.json()["status"] == "declined"
    assert applicant_client.get(MINE).json()["decision_reason"] == "Need more experience"
    run_outbox()
    item = Notification.objects.get(user=applicant, type="mentor_application_decision")
    assert item.payload["reason"] == "Need more experience"
    assert not UserRole.objects.filter(user=applicant, role="mentor").exists()
    assert AuditLog.objects.get(action="mentors.decline").reason == "Need more experience"


def test_the_admin_can_ask_for_more_information_and_the_applicant_answers(
    applicant_client, as_admin, submitted
):
    assert decision(as_admin, submitted["id"], decision="request_info").status_code == 400
    sent = decision(as_admin, submitted["id"], decision="request_info", reason="Add your fund size")
    assert sent.json()["status"] == "info_requested"
    assert (
        decision(as_admin, submitted["id"], decision="request_info", reason="again").status_code
        == 409
    )
    answered = applicant_client.patch(
        f"{APPLY}/{submitted['id']}", {"availability_note": "Fund size 5M"}, format="json"
    )
    assert answered.json()["status"] == "pending"
    assert decision(as_admin, submitted["id"], decision="approve").status_code == 200


def test_a_decision_cannot_be_made_twice(as_admin, submitted):
    assert decision(as_admin, submitted["id"], decision="approve").status_code == 200
    assert decision(as_admin, submitted["id"], decision="decline", reason="x").status_code == 409


def test_an_unknown_decision_is_refused(as_admin, submitted):
    assert decision(as_admin, submitted["id"], decision="maybe").status_code == 400


def test_a_suspended_applicant_cannot_be_approved(applicant, as_admin, submitted):
    applicant.status = "suspended"
    applicant.save()
    assert decision(as_admin, submitted["id"], decision="approve").status_code == 409


def test_admins_are_told_of_a_new_application(admin, submitted, run_outbox):
    run_outbox()
    assert Notification.objects.filter(user=admin, type="mentor_application_received").count() == 1


def test_the_queue_lists_oldest_first_with_applicant_details(as_admin, submitted):
    page = as_admin.get(QUEUE, {"status": "pending"}).json()
    assert page["count"] == 1
    row = page["results"][0]
    assert row["applicant"]["email"] == "applicant@example.com"
    assert row["linkedin_url"].startswith("https://")
    assert as_admin.get(f"{QUEUE}/{submitted['id']}").json()["id"] == submitted["id"]
    assert as_admin.get(QUEUE, {"status": "approved"}).json()["count"] == 0


# --- who may decide ---


def test_only_admins_with_the_permission_can_use_the_queue(
    api_client, applicant_client, editor_client, make_user, client_for, submitted
):
    url = f"{QUEUE}/{submitted['id']}"
    for client, expected in ((api_client, 401), (applicant_client, 403), (editor_client, 403)):
        assert client.get(QUEUE).status_code == expected
        assert client.get(url).status_code == expected
        assert (
            client.post(f"{url}/decision", {"decision": "approve"}, format="json").status_code
            == expected
        )
    no_mfa = client_for(make_user(roles=("community_admin",), email="nomfa@example.com"))
    assert no_mfa.get(QUEUE).status_code == 403
    assert MentorApplication.objects.get().status == "pending"


def test_unknown_applications_are_404(as_admin):
    import uuid

    missing = uuid.uuid4()
    assert as_admin.get(f"{QUEUE}/{missing}").status_code == 404
    assert decision(as_admin, missing, decision="approve").status_code == 404
