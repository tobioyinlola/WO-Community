import pytest
from django.utils import timezone

pytestmark = pytest.mark.django_db

URL = "/api/v1/search/recents"


def active(make_user, email):
    return make_user(email=email, approved_at=timezone.now(), email_verified_at=timezone.now())


@pytest.fixture
def me(make_user, client_for):
    return client_for(active(make_user, "me@example.com"))


def remember(client, term, scope="member"):
    return client.post(URL, {"term": term, "scope": scope}, format="json")


def test_a_term_is_remembered_and_listed_newest_first(me):
    remember(me, "fintech")
    remember(me, "agritech")
    assert me.get(URL).json() == {"terms": ["agritech", "fintech"]}


def test_a_repeated_term_moves_to_the_top_without_a_copy(me):
    remember(me, "fintech")
    remember(me, "agritech")
    remember(me, "  FinTech ")
    assert me.get(URL).json() == {"terms": ["FinTech", "agritech"]}


def test_only_the_latest_eight_are_kept(me):
    for n in range(10):
        remember(me, f"term {n}")
    terms = me.get(URL).json()["terms"]
    assert len(terms) == 8 and terms[0] == "term 9" and "term 0" not in terms


def test_member_and_admin_lists_are_separate_and_clearable(me):
    remember(me, "members only")
    remember(me, "admin only", "admin")
    assert me.get(URL, {"scope": "admin"}).json() == {"terms": ["admin only"]}
    assert me.delete(URL).status_code == 204
    assert me.get(URL).json() == {"terms": []}
    assert me.get(URL, {"scope": "admin"}).json() == {"terms": ["admin only"]}


def test_recents_belong_to_one_person(me, make_user, client_for):
    remember(me, "private idea")
    other = client_for(active(make_user, "o@example.com"))
    assert other.get(URL).json() == {"terms": []}


@pytest.mark.parametrize(
    "body",
    [
        {"term": "a"},
        {"term": "x" * 101},
        {"term": "ok", "scope": "staff"},
        {"term": "ok", "extra": 1},
    ],
)
def test_bad_terms_are_refused(me, body):
    assert me.post(URL, body, format="json").status_code == 400


def test_signing_in_is_required(api_client):
    assert api_client.get(URL).status_code == 401
    assert api_client.post(URL, {"term": "ok"}, format="json").status_code == 401
    assert api_client.delete(URL).status_code == 401
