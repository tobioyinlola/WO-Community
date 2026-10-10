import pytest

from apps.audit.models import AuditLog
from apps.directory.tests.conftest import STARTUPS, edit_startup

pytestmark = pytest.mark.django_db


@pytest.fixture
def admin(make_user):
    return make_user(roles=("community_admin",), email="admin@example.com")


@pytest.fixture
def as_admin(admin, client_for):
    return client_for(admin, mfa_age=5)


def feature(client, startup_id):
    return client.post(f"/api/v1/admin/startups/{startup_id}/feature")


def unfeature(client, startup_id):
    return client.post(f"/api/v1/admin/startups/{startup_id}/unfeature")


ENDPOINTS = ["feature", "unfeature"]


@pytest.mark.parametrize("action", ENDPOINTS)
def test_anonymous_callers_are_rejected(api_client, listed, action):
    fixture = listed()
    assert api_client.post(f"/api/v1/admin/startups/{fixture.id}/{action}").status_code == 401


@pytest.mark.parametrize("action", ENDPOINTS)
def test_members_and_editors_are_forbidden(client_for, make_user, listed, action):
    fixture = listed()
    for roles in (("member",), ("content_editor",)):
        user = make_user(roles=roles, email=f"{roles[0]}@example.com")
        response = client_for(user, mfa_age=5).post(f"/api/v1/admin/startups/{fixture.id}/{action}")
        assert response.status_code == 403
        assert response.json()["code"] == "permission_denied"


@pytest.mark.parametrize("action", ENDPOINTS)
def test_admins_without_mfa_are_refused(client_for, admin, listed, action):
    fixture = listed()
    response = client_for(admin).post(f"/api/v1/admin/startups/{fixture.id}/{action}")
    assert response.status_code == 403
    assert response.json()["code"] == "mfa_required"


def test_featuring_pins_a_startup_to_the_top_of_the_directory(
    as_admin, api_client, listed, run_outbox
):
    listed("Older Co")
    star = listed("Newest Co")
    listed("Newer Co")
    response = feature(as_admin, star.id)
    assert response.status_code == 200
    assert response.json() == {"id": str(star.id), "slug": star.slug, "featured": True}
    run_outbox()
    results = api_client.get(STARTUPS).json()["results"]
    assert results[0]["name"] == "Newest Co" and results[0]["featured"] is True
    assert [c["name"] for c in results[1:]] == ["Newer Co", "Older Co"]


def test_unfeaturing_restores_the_normal_order(as_admin, api_client, listed, run_outbox):
    listed("Older Co")
    star = listed("Newer Co")
    feature(as_admin, star.id)
    unfeature(as_admin, star.id)
    run_outbox()
    results = api_client.get(STARTUPS).json()["results"]
    assert [c["featured"] for c in results] == [False, False]


def test_featuring_is_audited(as_admin, admin, listed):
    star = listed()
    feature(as_admin, star.id)
    unfeature(as_admin, star.id)
    actions = list(AuditLog.objects.filter(target_id=str(star.id)).values_list("action", flat=True))
    assert actions == ["startup.featured", "startup.unfeatured"]
    assert AuditLog.objects.filter(action="startup.featured").get().actor_id == admin.pk


def test_only_listed_startups_can_be_featured(as_admin, listed):
    unlisted = listed("Hidden Co", listed=False)
    response = feature(as_admin, unlisted.id)
    assert response.status_code == 409
    assert response.json()["code"] == "not_listed"


def test_a_startup_that_leaves_the_directory_can_still_be_unpinned(as_admin, listed):
    star = listed()
    feature(as_admin, star.id)
    edit_startup(star.id, directory_opt_in=False)
    assert unfeature(as_admin, star.id).status_code == 200


def test_unknown_startups_are_404(as_admin):
    missing = "00000000-0000-0000-0000-000000000000"
    assert feature(as_admin, missing).status_code == 404
    assert unfeature(as_admin, missing).status_code == 404


def test_featuring_twice_is_harmless(as_admin, listed):
    star = listed()
    assert feature(as_admin, star.id).status_code == 200
    assert feature(as_admin, star.id).status_code == 200
