import pytest

from apps.core import policies
from apps.core.rbac import Role, permissions_for

pytestmark = [pytest.mark.django_db, pytest.mark.usefixtures("policy_urls")]


def test_view_without_policy_is_denied_even_to_authenticated_users(make_user, client_for):
    assert client_for(make_user()).get("/nopolicy").status_code == 403


def test_view_without_policy_is_denied_to_anonymous(api_client):
    assert api_client.get("/nopolicy").status_code in (401, 403)


def test_public_policy_allows_anonymous(api_client):
    assert api_client.get("/public").status_code == 200


def test_member_policy_rejects_anonymous(api_client):
    assert api_client.get("/member").status_code == 401


def test_member_policy_rejects_pending_account(make_user, client_for):
    user = make_user(status="pending")
    assert client_for(user).get("/member").status_code == 403


def test_member_policy_accepts_active_account(make_user, client_for):
    assert client_for(make_user()).get("/member").status_code == 200


def test_permission_policy_rejects_wrong_role(make_user, client_for):
    assert client_for(make_user(roles=("member",))).get("/editor").status_code == 403


def test_permission_policy_accepts_role_with_permission(make_user, client_for):
    user = make_user(roles=("content_editor",))
    assert client_for(user).get("/editor").status_code == 200


def test_permission_policy_rejects_suspended_admin(make_user, client_for):
    user = make_user(roles=("super_admin",), status="suspended")
    assert client_for(user).get("/editor").status_code == 401


def test_owns_compares_owner_to_user(make_user):
    user = make_user()
    other = make_user()

    class Thing:
        owner_id = user.pk

    check = policies.owns(lambda obj: obj.owner_id)
    assert check(user, Thing()) is True
    assert check(other, Thing()) is False


def test_permission_matrix_is_cumulative():
    assert permissions_for({Role.MEMBER}) < permissions_for({Role.MENTOR})
    assert permissions_for({Role.COMMUNITY_ADMIN}) < permissions_for({Role.SUPER_ADMIN})
    assert "audit.read" not in permissions_for({Role.COMMUNITY_ADMIN})
    assert "audit.read" in permissions_for({Role.SUPER_ADMIN})


def test_unknown_role_grants_nothing():
    assert permissions_for({"visitor", "made_up"}) == frozenset()
