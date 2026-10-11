import pytest

from apps.accounts.models import User
from apps.accounts.tests.helpers import REGISTER_URL, registration_payload
from apps.mentorship.models import MentorInterest
from apps.mentorship.tests.conftest import active, application_body

pytestmark = pytest.mark.django_db

MINE = "/api/v1/me/mentoring"
APPLY = "/api/v1/mentor-applications"
SEARCH = "/api/v1/search"


def set_profile(user, name, headline=""):
    from apps.profiles.models import FounderProfile
    from apps.profiles.services import get_or_create_profile

    FounderProfile.objects.filter(pk=get_or_create_profile(user.pk).pk).update(
        full_name=name, headline=headline
    )


# --- "I am also a mentor" at registration ---


def test_ticking_the_option_records_interest_but_grants_nothing(api_client, run_outbox):
    response = api_client.post(REGISTER_URL, registration_payload(also_mentor=True))
    assert response.status_code == 202
    run_outbox()
    user = User.objects.get(email="new.member@example.com")
    assert MentorInterest.objects.filter(user=user).exists()
    assert "mentor" not in user.role_names()


def test_leaving_it_unticked_records_nothing(api_client, run_outbox):
    api_client.post(REGISTER_URL, registration_payload())
    api_client.post(REGISTER_URL, registration_payload(email="b@example.com", also_mentor=False))
    run_outbox()
    assert not MentorInterest.objects.exists()


def test_the_option_must_be_a_boolean(api_client):
    response = api_client.post(REGISTER_URL, registration_payload(also_mentor="maybe"))
    assert response.status_code == 400


def test_an_interested_member_is_prompted_to_apply_until_they_do(
    make_user, client_for, applicant_client, applicant
):
    MentorInterest.objects.create(user=applicant)
    body = applicant_client.get(MINE).json()
    assert body["interested"] is True and body["prompt_to_apply"] is True
    assert body["can_apply"] is True and body["application_status"] is None
    applicant_client.post(APPLY, application_body(), format="json")
    after = applicant_client.get(MINE).json()
    assert after["prompt_to_apply"] is False and after["application_status"] == "pending"
    assert after["can_apply"] is False


def test_a_member_who_did_not_tick_is_not_prompted(applicant_client):
    body = applicant_client.get(MINE).json()
    assert body == {
        "is_mentor": False,
        "application_id": None,
        "application_status": None,
        "interested": False,
        "can_apply": True,
        "can_apply_after": None,
        "prompt_to_apply": False,
    }


def test_the_summary_shows_mentors_and_the_decline_wait(mentor, applicant_client, as_admin):
    assert applicant_client.get(MINE).json()["is_mentor"] is True
    assert applicant_client.get(MINE).json()["can_apply"] is False


def test_the_summary_shows_when_a_declined_member_may_apply_again(
    applicant_client, as_admin, applicant
):
    created = applicant_client.post(APPLY, application_body(), format="json").json()
    as_admin.post(
        f"/api/v1/admin/mentor-applications/{created['id']}/decision",
        {"decision": "decline", "reason": "Not yet"},
        format="json",
    )
    body = applicant_client.get(MINE).json()
    assert body["can_apply"] is False and body["can_apply_after"] is not None
    assert body["application_status"] == "declined"


def test_the_summary_needs_login(api_client):
    assert api_client.get(MINE).status_code == 401


# --- searching for mentors ---


@pytest.fixture
def searcher(make_user, client_for):
    return client_for(active(make_user, "searcher@example.com"))


def test_search_finds_listed_mentors_by_name_role_company_and_expertise(mentor, searcher):
    set_profile(mentor, "Ada Obi")
    for query in ("Ada Obi", "savannah", "partner", "fundraising"):
        hits = searcher.get(SEARCH, {"q": query, "types": "mentors"}).json()["mentors"]
        assert [h["id"] for h in hits] == [str(mentor.pk)], query
    hit = searcher.get(SEARCH, {"q": "savannah", "types": "mentors"}).json()["mentors"][0]
    assert hit["type"] == "mentor" and hit["title"] == "Ada Obi"
    assert hit["subtitle"] == "Partner, Savannah Capital"


def test_search_leaves_out_paused_and_revoked_mentors(mentor, applicant_client, as_admin, searcher):
    applicant_client.put("/api/v1/me/mentor-profile", {"paused": True}, format="json")
    assert searcher.get(SEARCH, {"q": "savannah", "types": "mentors"}).json()["mentors"] == []
    applicant_client.put("/api/v1/me/mentor-profile", {"paused": False}, format="json")
    as_admin.post(f"/api/v1/admin/mentors/{mentor.pk}/revoke", {"reason": "x"}, format="json")
    assert searcher.get(SEARCH, {"q": "savannah", "types": "mentors"}).json()["mentors"] == []


def test_a_mentor_who_hides_their_name_is_not_found_by_it(mentor, searcher):
    set_profile(mentor, "Hidden Person")
    from apps.profiles.models import FounderProfile

    FounderProfile.objects.filter(user=mentor).update(visibility={"basics": "private"})
    by_name = searcher.get(SEARCH, {"q": "Hidden Person", "types": "mentors"}).json()["mentors"]
    assert by_name == []
    by_work = searcher.get(SEARCH, {"q": "savannah", "types": "mentors"}).json()["mentors"]
    assert by_work and by_work[0]["title"] == "Community member"
    assert "Hidden" not in str(by_work)


def test_mentors_are_part_of_the_default_search(mentor, searcher):
    set_profile(mentor, "Ada Obi")
    body = searcher.get(SEARCH, {"q": "savannah"}).json()
    assert len(body["mentors"]) == 1


def test_mentor_search_needs_an_active_member(api_client):
    assert api_client.get(SEARCH, {"q": "savannah", "types": "mentors"}).status_code == 401
