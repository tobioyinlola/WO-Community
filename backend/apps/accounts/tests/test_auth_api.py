import jwt
import pytest
from django.conf import settings

from apps.accounts import tokens
from apps.accounts.models import UserStatus

pytestmark = pytest.mark.django_db

ME = "/api/v1/me"


def test_me_returns_account_for_valid_token(make_user, client_for):
    user = make_user(roles=("member", "mentor"))
    response = client_for(user).get(ME)
    assert response.status_code == 200
    assert response.json() == {
        "id": str(user.pk),
        "email": user.email,
        "status": "active",
        "roles": ["member", "mentor"],
        "community_invite_url": settings.WHATSAPP_COMMUNITY_URL,
    }


def test_me_requires_authentication(api_client):
    response = api_client.get(ME)
    assert response.status_code == 401
    body = response.json()
    assert body["code"] == "not_authenticated"
    assert response["Content-Type"] == "application/problem+json"


def test_me_rejects_wrong_scheme(api_client):
    response = api_client.get(ME, HTTP_AUTHORIZATION="Basic abc")
    assert response.status_code == 401


def test_me_rejects_garbage_token(api_client):
    response = api_client.get(ME, HTTP_AUTHORIZATION="Bearer not-a-token")
    assert response.status_code == 401


def test_me_rejects_token_signed_with_another_key(make_user, api_client):
    from config.settings.keys import ephemeral_jwt_keys

    user = make_user()
    other_private, _ = ephemeral_jwt_keys()
    forged = jwt.encode(
        {"iss": settings.JWT_ISSUER, "sub": str(user.pk), "iat": 1, "exp": 4102444800, "tv": 1},
        other_private,
        algorithm="EdDSA",
    )
    response = api_client.get(ME, HTTP_AUTHORIZATION=f"Bearer {forged}")
    assert response.status_code == 401


def test_me_rejects_unsigned_token(make_user, api_client):
    user = make_user()
    unsigned = jwt.encode(
        {"iss": settings.JWT_ISSUER, "sub": str(user.pk), "iat": 1, "exp": 4102444800, "tv": 1},
        key=None,
        algorithm="none",
    )
    response = api_client.get(ME, HTTP_AUTHORIZATION=f"Bearer {unsigned}")
    assert response.status_code == 401


@pytest.mark.parametrize("status", [UserStatus.SUSPENDED, UserStatus.REMOVED])
def test_me_rejects_suspended_and_removed_accounts(make_user, client_for, status):
    user = make_user(status=status)
    assert client_for(user).get(ME).status_code == 401


def test_pending_account_can_read_itself_but_is_not_active_member(make_user, client_for):
    user = make_user(status=UserStatus.PENDING)
    response = client_for(user).get(ME)
    assert response.status_code == 200
    assert response.json()["status"] == "pending"


def test_token_version_bump_revokes_existing_tokens(make_user, client_for):
    user = make_user()
    client = client_for(user)
    assert client.get(ME).status_code == 200
    user.bump_token_version()
    tokens.revoke_older_tokens(user)
    assert client.get(ME).status_code == 401


def test_new_token_works_after_version_bump(make_user, client_for):
    user = make_user()
    user.bump_token_version()
    tokens.revoke_older_tokens(user)
    assert client_for(user).get(ME).status_code == 200


# --- the WhatsApp community invitation ---

SHOWN = "/api/v1/me/community-invite/shown"
JOINED = "/api/v1/me/community-invite/joined"


def test_the_community_invitation_is_offered_three_times_then_stops(make_user, client_for):
    client = client_for(make_user())
    for _ in range(3):
        assert client.get(ME).json()["community_invite_url"] == settings.WHATSAPP_COMMUNITY_URL
        assert client.post(SHOWN).status_code == 204
    assert client.get(ME).json()["community_invite_url"] is None
    assert client.post(SHOWN).status_code == 204  # never counts past three
    assert client.get(ME).json()["community_invite_url"] is None


def test_following_the_community_link_stops_the_invitation(make_user, client_for):
    client = client_for(make_user())
    assert client.post(JOINED).status_code == 204
    assert client.get(ME).json()["community_invite_url"] is None


def test_the_invitation_needs_a_signed_in_member(api_client):
    assert api_client.post(SHOWN).status_code == 401
    assert api_client.post(JOINED).status_code == 401
