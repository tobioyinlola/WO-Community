import pytest
from django.utils import timezone
from rest_framework.throttling import ScopedRateThrottle

from apps.profiles.models import FounderProfile
from apps.profiles.services import get_or_create_profile
from apps.startups.models import Startup
from apps.startups.tests.conftest import STARTUPS, new_startup_body

pytestmark = pytest.mark.django_db

SEARCH = "/api/v1/search"


def member(make_user, email, name="", headline="", **fields):
    user = make_user(
        email=email, approved_at=timezone.now(), email_verified_at=timezone.now(), **fields
    )
    profile = get_or_create_profile(user.pk)
    FounderProfile.objects.filter(pk=profile.pk).update(full_name=name, headline=headline)
    return user


@pytest.fixture
def searcher(make_user, client_for):
    return client_for(member(make_user, "me@example.com", "Searcher One"))


@pytest.fixture
def people(make_user):
    return {
        "ada": member(make_user, "ada@example.com", "Adaeze Okafor", "Fintech founder in Lagos"),
        "tunde": member(make_user, "tunde@example.com", "Tunde Bakare", "Logistics builder"),
    }


def find(client, q, **params):
    return client.get(SEARCH, {"q": q, **params})


def titles(response, kind="members"):
    return [hit["title"] for hit in response.json()[kind]]


# --- finding people ---


def test_a_member_is_found_by_name_and_by_headline(searcher, people):
    assert titles(find(searcher, "Adaeze")) == ["Adaeze Okafor"]
    assert titles(find(searcher, "logistics")) == ["Tunde Bakare"]


def test_a_hit_has_what_a_results_list_needs(searcher, people):
    [hit] = find(searcher, "Tunde").json()["members"]
    assert set(hit) == {"type", "id", "slug", "title", "subtitle", "image"}
    assert hit["type"] == "member" and hit["id"] == str(people["tunde"].pk)
    assert hit["subtitle"] == "Logistics builder"


def test_small_typos_still_find_the_person(searcher, people):
    assert titles(find(searcher, "Adaeez")) == ["Adaeze Okafor"]
    assert titles(find(searcher, "bakkare")) == ["Tunde Bakare"]


def test_matching_ignores_case(searcher, people):
    assert titles(find(searcher, "TUNDE")) == ["Tunde Bakare"]


def test_unrelated_words_find_nothing(searcher, people):
    assert find(searcher, "zzqx").json() == {
        "members": [],
        "startups": [],
        "jobs": [],
        "mentors": [],
    }


def test_a_member_can_find_themselves(searcher):
    assert titles(find(searcher, "Searcher")) == ["Searcher One"]


# --- who must never appear ---


def test_someone_who_hides_their_basics_from_members_cannot_be_found(searcher, people, client_for):
    client = client_for(people["ada"])
    assert client.patch("/api/v1/me/visibility", {"basics": "private"}).status_code == 200
    assert titles(find(searcher, "Adaeze")) == []
    assert titles(find(searcher, "fintech founder")) == []


def test_hiding_other_groups_does_not_hide_the_person(searcher, people, client_for):
    client_for(people["ada"]).patch("/api/v1/me/visibility", {"bio": "private"})
    assert titles(find(searcher, "Adaeze")) == ["Adaeze Okafor"]


def test_the_owner_still_finds_themselves_when_hidden_from_others(people, client_for):
    client = client_for(people["ada"])
    client.patch("/api/v1/me/visibility", {"basics": "private"})
    assert titles(find(client, "Adaeze")) == ["Adaeze Okafor"]


@pytest.mark.parametrize("status", ["pending", "suspended", "removed", "rejected"])
def test_accounts_that_are_not_active_are_never_listed(searcher, make_user, status):
    member(make_user, "x@example.com", "Zanele Hidden", status=status)
    assert titles(find(searcher, "Zanele")) == []


def test_private_fields_are_never_matched(searcher, people, client_for):
    """Searching a word that only appears in a hidden bio finds nothing."""
    from apps.profiles.tests.conftest import FULL, patch

    client = client_for(people["ada"])
    patch(client, {**FULL, "bio": "ZZSECRETBIO"})
    client.patch("/api/v1/me/visibility", {"bio": "private"})
    assert titles(find(searcher, "ZZSECRETBIO")) == []


# --- startups ---


@pytest.fixture
def startup(people, client_for):
    client = client_for(people["ada"])
    response = client.post(
        STARTUPS, new_startup_body(name="Kola Pay", pitch="Payments for small traders")
    )
    assert response.status_code == 201
    return response.json()["id"], client


def test_a_startup_is_found_by_name_and_pitch(searcher, startup):
    assert titles(find(searcher, "Kola"), "startups") == ["Kola Pay"]
    assert titles(find(searcher, "traders"), "startups") == ["Kola Pay"]
    [hit] = find(searcher, "Kola").json()["startups"]
    assert hit["type"] == "startup" and hit["id"] == startup[0]


def test_startups_tolerate_typos_too(searcher, startup):
    assert titles(find(searcher, "Kolaa Pey"), "startups") == ["Kola Pay"]


def test_a_startup_hiding_its_basics_is_not_found(searcher, startup):
    startup_id, client = startup
    etag = client.get(f"{STARTUPS}/{startup_id}")["ETag"]
    client.patch(f"{STARTUPS}/{startup_id}/visibility", {"basics": "private"}, HTTP_IF_MATCH=etag)
    assert titles(find(searcher, "Kola"), "startups") == []


def test_a_startup_of_an_inactive_owner_disappears(searcher, startup, people):
    from apps.accounts.models import User

    User.objects.filter(pk=people["ada"].pk).update(status="suspended")
    assert titles(find(searcher, "Kola"), "startups") == []


def test_the_team_can_find_their_own_hidden_startup(startup):
    startup_id, client = startup
    etag = client.get(f"{STARTUPS}/{startup_id}")["ETag"]
    client.patch(f"{STARTUPS}/{startup_id}/visibility", {"basics": "private"}, HTTP_IF_MATCH=etag)
    assert titles(find(client, "Kola"), "startups") == ["Kola Pay"]
    assert Startup.objects.count() == 1


# --- the endpoint ---


def test_types_narrow_the_search(searcher, startup, people):
    only = find(searcher, "Kola", types="startups").json()
    assert list(only) == ["startups"]
    both = find(searcher, "Kola", types="members,startups").json()
    assert set(both) == {"members", "startups"}


def test_limit_is_applied_per_type(searcher, make_user):
    for i in range(5):
        member(make_user, f"p{i}@example.com", f"Chidi Person{i}")
    assert len(titles(find(searcher, "Chidi", limit=3))) == 3
    assert len(titles(find(searcher, "Chidi"))) == 5


@pytest.mark.parametrize(
    "params",
    [
        {},
        {"q": ""},
        {"q": "a"},
        {"q": "x" * 101},
        {"q": "ok", "types": "courses"},
        {"q": "ok", "limit": 0},
        {"q": "ok", "limit": 21},
        {"q": "ok", "limit": "many"},
        {"q": "ok", "extra": "1"},
    ],
)
def test_bad_queries_are_refused(searcher, params):
    assert searcher.get(SEARCH, params).status_code == 400


def test_search_terms_are_treated_as_text_not_patterns(searcher, people):
    for hostile in ("%", "_", "' OR 1=1 --", "Ada%", "\\"):
        assert searcher.get(SEARCH, {"q": hostile + "x"}).status_code == 200


def test_results_are_not_cached(searcher):
    assert find(searcher, "Searcher")["Cache-Control"] == "private, no-store"


def test_search_is_for_active_members_only(api_client, make_user, client_for):
    assert api_client.get(SEARCH, {"q": "ada"}).status_code == 401
    pending = make_user(email="p@example.com", status="pending")
    assert client_for(pending).get(SEARCH, {"q": "ada"}).status_code == 403


def test_searches_are_rate_limited(searcher, monkeypatch):
    monkeypatch.setattr(
        ScopedRateThrottle,
        "THROTTLE_RATES",
        {**ScopedRateThrottle.THROTTLE_RATES, "search": "2/min"},
    )
    statuses = [find(searcher, "ada").status_code for _ in range(3)]
    assert statuses == [200, 200, 429]
