import pytest
from django.utils import timezone

from apps.learning.models import Course
from apps.profiles.models import FounderProfile
from apps.profiles.services import get_or_create_profile

pytestmark = pytest.mark.django_db

SEARCH = "/api/v1/admin/search"


def person(make_user, email, name, **fields):
    user = make_user(email=email, **fields)
    profile = get_or_create_profile(user.pk)
    FounderProfile.objects.filter(pk=profile.pk).update(full_name=name)
    return user


@pytest.fixture
def admin(make_user, client_for):
    return client_for(make_user(roles=("community_admin",), email="admin@example.com"), mfa_age=5)


@pytest.fixture
def editor(make_user, client_for):
    return client_for(make_user(roles=("content_editor",), email="editor@example.com"), mfa_age=5)


@pytest.fixture
def data(make_user):
    person(make_user, "ada@example.com", "Adaeze Okafor", email_verified_at=timezone.now())
    person(
        make_user,
        "adam@example.com",
        "Adam Waiting",
        roles=(),
        status="pending",
        email_verified_at=timezone.now(),
    )
    Course.objects.create(
        slug="adaptive-selling",
        title="Adaptive selling",
        description="<p>x</p>",
        description_text="x",
        instructor="Someone",
        category="Sales",
        level="beginner",
        status="published",
    )


def test_an_admin_finds_members_by_name_including_pending_ones(admin, data):
    body = admin.get(SEARCH, {"q": "ada"}).json()
    names = [hit["title"] for hit in body["members"]]
    assert "Adaeze Okafor" in names and "Adam Waiting" in names
    assert [hit["title"] for hit in body["approvals"]] == ["Adam Waiting"]
    assert body["approvals"][0]["url"].startswith("/admin/approvals?request=")
    assert [hit["title"] for hit in body["courses"]] == ["Adaptive selling"]


def test_a_group_is_left_out_when_the_role_lacks_its_permission(editor, data):
    body = editor.get(SEARCH, {"q": "ada"}).json()
    assert "members" not in body and "approvals" not in body
    assert [hit["title"] for hit in body["courses"]] == ["Adaptive selling"]


def test_types_narrows_the_groups(admin, data):
    body = admin.get(SEARCH, {"q": "ada", "types": "courses"}).json()
    assert list(body) == ["courses"]


@pytest.mark.parametrize(
    "params",
    [
        {},
        {"q": "a"},
        {"q": "x" * 101},
        {"q": "ada", "types": "nonsense"},
        {"q": "ada", "limit": 99},
        {"q": "ada", "x": 1},
    ],
)
def test_bad_queries_are_refused(admin, params):
    assert admin.get(SEARCH, params).status_code == 400


def test_nothing_matching_gives_empty_groups(admin, data):
    body = admin.get(SEARCH, {"q": "zzzzzz"}).json()
    assert all(hits == [] for hits in body.values())


def test_a_member_without_an_admin_role_is_refused(make_user, client_for):
    member = client_for(make_user(email="m@example.com"), mfa_age=5)
    assert member.get(SEARCH, {"q": "ada"}).status_code == 403


def test_an_admin_without_a_second_step_is_refused(make_user, client_for):
    admin = client_for(make_user(roles=("community_admin",), email="a2@example.com"))
    assert admin.get(SEARCH, {"q": "ada"}).status_code == 403


def test_signing_in_is_required(api_client):
    assert api_client.get(SEARCH, {"q": "ada"}).status_code == 401
