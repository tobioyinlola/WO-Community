import pytest

from apps.analytics.models import AnalyticsEvent
from apps.mentorship import matching, scheduling
from apps.mentorship.models import MentorProfile
from apps.mentorship.tests.conftest import active, application_body

pytestmark = pytest.mark.django_db

REC = "/api/v1/mentors/recommended"
NEEDS = "/api/v1/me/mentorship-needs"
AVAILABILITY = "/api/v1/me/availability"
EVERY_DAY = [{"weekday": d, "start": "09:00", "end": "12:00"} for d in range(7)]


def make_mentor(make_user, client_for, as_admin, email, name, **overrides):
    user = active(make_user, email)
    client = client_for(user)
    created = client.post(
        "/api/v1/mentor-applications", application_body(**overrides), format="json"
    )
    assert created.status_code == 201, created.content
    as_admin.post(
        f"/api/v1/admin/mentor-applications/{created.json()['id']}/decision",
        {"decision": "approve"},
        format="json",
    )
    from apps.profiles.models import FounderProfile
    from apps.profiles.services import get_or_create_profile

    FounderProfile.objects.filter(pk=get_or_create_profile(user.pk).pk).update(full_name=name)
    return user, client


@pytest.fixture
def mentors(make_user, client_for, as_admin):
    ada = make_mentor(
        make_user,
        client_for,
        as_admin,
        "ada@example.com",
        "Ada Obi",
        expertise=["Fundraising", "Pitching"],
        industries=["fintech"],
        stages=["seed"],
        languages=["en", "fr"],
    )
    kofi = make_mentor(
        make_user,
        client_for,
        as_admin,
        "kofi@example.com",
        "Kofi Mensah",
        expertise=["Product design"],
        industries=["healthtech"],
        stages=["idea"],
        languages=["en"],
    )
    return ada, kofi


@pytest.fixture
def founder(make_user, client_for):
    user = active(make_user, "founder@example.com")
    return user, client_for(user)


def ids(response):
    return [m["id"] for m in response.json()]


def test_the_best_match_for_a_stated_need_comes_first(mentors, founder):
    (ada, _), (kofi, _) = mentors
    _, client = founder
    body = client.get(REC, {"needs": "fundraising"}).json()
    assert [m["id"] for m in body] == [str(ada.pk), str(kofi.pk)]
    assert body[0]["score"] > body[1]["score"]
    top = {r["key"]: r for r in body[0]["reasons"]}
    assert top["expertise"]["text"] == "Covers fundraising"
    assert body[0]["name"] == "Ada Obi" and "email" not in body[0]


def test_synonyms_and_partial_words_count(mentors, founder):
    (ada, _), (kofi, _) = mentors
    _, client = founder
    assert ids(client.get(REC, {"needs": "investors"}))[0] == str(ada.pk)  # synonym of fundraising
    assert ids(client.get(REC, {"needs": "design"}))[0] == str(kofi.pk)  # inside "product design"
    assert ids(client.get(REC, {"needs": "pitch"}))[0] == str(ada.pk)


def test_startup_sector_and_stage_add_a_fit_reason(mentors, founder):
    (ada, _), _ = mentors
    user, client = founder
    created = client.post(
        "/api/v1/startups",
        {
            "name": "Ada Pay",
            "pitch": "Payments",
            "country": "NG",
            "city": "Lagos",
            "sector": "fintech",
            "stage": "seed",
            "year_founded": 2024,
        },
        format="json",
    )
    assert created.status_code == 201, created.content
    first = client.get(REC).json()[0]
    assert first["id"] == str(ada.pk)
    fit = next(r for r in first["reasons"] if r["key"] == "fit")
    assert fit["score"] == 100 and fit["text"] == "Advises Fintech startups and Seed stage"


def test_a_founder_with_no_details_still_gets_scored_mentors(mentors, founder):
    _, client = founder
    body = client.get(REC).json()
    assert len(body) == 2
    assert all(0 <= m["score"] <= 100 for m in body)
    assert "expertise" not in body[0]["components"] and "fit" not in body[0]["components"]


def test_saved_needs_and_languages_are_used_and_can_be_overridden(mentors, founder):
    (ada, _), (kofi, _) = mentors
    _, client = founder
    saved = client.put(
        NEEDS, {"needs": ["Product Design", "product design"], "languages": ["en"]}, format="json"
    )
    assert saved.json() == {"needs": ["product design"], "languages": ["en"]}
    assert client.get(NEEDS).json()["needs"] == ["product design"]
    assert ids(client.get(REC))[0] == str(kofi.pk)
    assert ids(client.get(REC, {"needs": "fundraising"}))[0] == str(ada.pk)


@pytest.mark.parametrize(
    "body",
    [
        {"needs": ["x"]},
        {"needs": ["a topic"] * 6},
        {"needs": ["ok topic"], "languages": ["xx"]},
        {"needs": ["ok topic"], "extra": 1},
        {},
    ],
)
def test_saving_needs_is_validated(founder, body):
    _, client = founder
    assert client.put(NEEDS, body, format="json").status_code == 400


def test_shared_language_raises_the_score(mentors, founder):
    (ada, _), _ = mentors
    _, client = founder
    client.put(NEEDS, {"needs": ["fundraising"], "languages": ["fr"]}, format="json")
    first = client.get(REC).json()[0]
    assert first["id"] == str(ada.pk)
    assert next(r for r in first["reasons"] if r["key"] == "language")["text"] == "Speaks French"


def test_paused_revoked_full_and_own_profiles_are_left_out(mentors, founder, as_admin, monkeypatch):
    (ada, ada_client), (kofi, _) = mentors
    _, client = founder
    assert len(client.get(REC).json()) == 2
    ada_client.put("/api/v1/me/mentor-profile", {"paused": True}, format="json")
    assert ids(client.get(REC)) == [str(kofi.pk)]  # the cache is refreshed by the change
    as_admin.post(f"/api/v1/admin/mentors/{kofi.pk}/revoke", {"reason": "x"}, format="json")
    assert client.get(REC).json() == []
    ada_client.put("/api/v1/me/mentor-profile", {"paused": False}, format="json")
    assert ids(ada_client.get(REC)) == []  # a mentor is never recommended to themselves
    monkeypatch.setattr(scheduling, "sessions_in_week", lambda *a: 3)
    matching.cache.clear()
    assert client.get(REC).json() == []  # fully booked


def test_a_high_rating_beats_an_unrated_mentor_but_few_ratings_are_smoothed(mentors, founder):
    (ada, _), (kofi, _) = mentors
    _, client = founder
    MentorProfile.objects.filter(user=kofi).update(rating_count=40, rating_total=200)
    MentorProfile.objects.filter(user=ada).update(rating_count=1, rating_total=1)
    body = {m["id"]: m for m in client.get(REC).json()}
    assert body[str(kofi.pk)]["components"]["quality"] > body[str(ada.pk)]["components"]["quality"]
    assert body[str(ada.pk)]["components"]["quality"] > 0.4  # one bad rating cannot sink a mentor
    assert any(r["key"] == "quality" for r in body[str(kofi.pk)]["reasons"])


def test_availability_adds_to_the_score(mentors, founder):
    (ada, ada_client), (kofi, _) = mentors
    _, client = founder
    before = {m["id"]: m for m in client.get(REC).json()}
    ada_client.put(AVAILABILITY, {"weekly": EVERY_DAY}, format="json")
    after = {m["id"]: m for m in client.get(REC).json()}
    assert before[str(ada.pk)]["components"]["availability"] == 0
    assert after[str(ada.pk)]["components"]["availability"] == 1.0
    assert after[str(ada.pk)]["score"] > before[str(ada.pk)]["score"]
    assert after[str(kofi.pk)]["score"] == before[str(kofi.pk)]["score"]


def test_results_are_cached_and_dropped_when_mentor_data_changes(
    mentors, founder, monkeypatch, django_capture_on_commit_callbacks
):
    (_, ada_client), _ = mentors
    _, client = founder
    calls = []
    real = matching.score_mentor

    def counting(*args, **kwargs):
        calls.append(1)
        return real(*args, **kwargs)

    monkeypatch.setattr(matching, "score_mentor", counting)
    client.get(REC)
    first = len(calls)
    client.get(REC)
    assert len(calls) == first  # served from the cache
    with django_capture_on_commit_callbacks(execute=True):
        ada_client.put("/api/v1/me/mentor-profile", {"about": "New text"}, format="json")
    client.get(REC)
    assert len(calls) > first
    again = len(calls)
    client.put(NEEDS, {"needs": ["hiring"]}, format="json")
    client.get(REC)
    assert len(calls) > again


def test_the_limit_applies_and_the_event_is_recorded(mentors, founder):
    _, client = founder
    assert len(client.get(REC, {"limit": 1}).json()) == 1
    assert client.get(REC, {"limit": 0}).status_code == 400
    assert client.get(REC, {"limit": 21}).status_code == 400
    event = AnalyticsEvent.objects.filter(name="mentor_recommendation_shown").first()
    assert event is not None and event.properties == {"count": 1}


def test_weights_can_be_tuned_by_configuration(mentors, founder, settings):
    (ada, _), (kofi, _) = mentors
    _, client = founder
    settings.MENTORSHIP_MATCH_WEIGHTS = {
        "expertise": 0.0,
        "fit": 0.0,
        "availability": 0.0,
        "language": 0.0,
        "capacity": 0.0,
        "quality": 1.0,
    }
    MentorProfile.objects.filter(user=kofi).update(rating_count=10, rating_total=50)
    matching.cache.clear()
    assert ids(client.get(REC, {"needs": "fundraising"}))[0] == str(kofi.pk)


def test_only_members_can_ask_for_recommendations(api_client, make_user, client_for):
    assert api_client.get(REC).status_code == 401
    assert api_client.get(NEEDS).status_code == 401
    assert api_client.put(NEEDS, {"needs": ["hiring"]}, format="json").status_code == 401
    pending = make_user(email="pending@example.com", status="pending")
    assert client_for(pending).get(REC).status_code == 403


def test_needs_belong_to_their_owner(founder, make_user, client_for):
    _, client = founder
    client.put(NEEDS, {"needs": ["hiring"]}, format="json")
    other = client_for(active(make_user, "someone@example.com"))
    assert other.get(NEEDS).json() == {"needs": [], "languages": []}
