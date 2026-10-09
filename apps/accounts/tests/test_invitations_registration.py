import threading
from datetime import timedelta

import pytest
from django.db import connections
from django.utils import timezone

from apps.accounts import services
from apps.accounts.models import ConsentRecord, Invitation, User
from apps.accounts.tests.helpers import LOGIN_URL, PASSWORD, REGISTER_URL, registration_payload
from apps.audit.models import AuditLog

pytestmark = pytest.mark.django_db

EMAIL = "guest@example.com"


@pytest.fixture
def inviter(make_user):
    return make_user(roles=("community_admin",), email="admin@example.com")


@pytest.fixture
def invite(inviter, run_outbox, last_invitation_token):
    """Create and 'send' an invitation; returns its raw token."""

    def build(email=EMAIL, role="member", message=""):
        services.create_invitation(actor=inviter, email=email, role=role, message=message)
        run_outbox()
        return last_invitation_token()

    return build


def register(client, token, email=EMAIL, **overrides):
    return client.post(
        REGISTER_URL,
        registration_payload(email=email, invitation_token=token, **overrides),
    )


def test_registering_through_an_invitation_approves_the_account_at_once(
    api_client, invite, inviter
):
    token = invite()
    response = register(api_client, token)
    assert response.status_code == 201
    assert response.json()["approved"] is True
    user = User.objects.get(email=EMAIL)
    assert user.status == "active"
    assert user.email_verified_at is not None
    assert user.approval_source == "invitation"
    assert user.approved_by == inviter
    assert user.approved_at is not None
    assert sorted(user.role_names()) == ["member"]
    invitation = Invitation.objects.get()
    assert invitation.status == "registered"
    assert invitation.accepted_by == user
    assert invitation.registered_at is not None
    assert invitation.token_hash is None


def test_the_new_member_can_log_in_straight_away(api_client, invite):
    register(api_client, invite())
    login = api_client.post(LOGIN_URL, {"email": EMAIL, "password": PASSWORD})
    assert login.status_code == 200
    assert login.json()["user"]["status"] == "active"
    me = api_client.get("/api/v1/me", HTTP_AUTHORIZATION=f"Bearer {login.json()['access_token']}")
    assert me.json()["roles"] == ["member"]


def test_a_welcome_email_follows_and_no_verification_email_is_sent(
    api_client, invite, run_outbox, sent_emails
):
    register(api_client, invite())
    sent_emails.clear()
    run_outbox()
    assert len(sent_emails) == 1
    assert "approved" in sent_emails[0].subject.lower()


def test_a_mentor_invitation_grants_mentor_and_member_roles(api_client, invite):
    register(api_client, invite(role="mentor"))
    assert sorted(User.objects.get(email=EMAIL).role_names()) == ["member", "mentor"]


def test_registration_through_an_invitation_is_audited(api_client, invite):
    register(api_client, invite())
    entry = AuditLog.objects.get(action="auth.registered")
    assert entry.after == {"approval_source": "invitation"}


def test_consents_are_still_required_and_recorded(api_client, invite):
    token = invite()
    refused = register(api_client, token, accepted_terms=False)
    assert refused.status_code == 400
    assert User.objects.count() == 1  # only the inviter
    assert register(api_client, token).status_code == 201
    assert ConsentRecord.objects.filter(user__email=EMAIL).count() == 4


def test_password_rules_still_apply(api_client, invite):
    token = invite()
    assert register(api_client, token, password="short").status_code == 400
    assert register(api_client, token, password="Password123!456").status_code == 400
    assert Invitation.objects.get().status == "sent"


def test_the_address_may_differ_in_case(api_client, invite):
    assert register(api_client, invite(), email="GUEST@Example.com").status_code == 201


def test_a_token_for_another_address_is_ignored_like_no_token(api_client, invite):
    token = invite()
    response = register(api_client, token, email="someone.else@example.com")
    assert response.status_code == 202
    assert User.objects.get(email="someone.else@example.com").status == "pending"
    assert Invitation.objects.get().status == "sent"


@pytest.mark.parametrize("fault", ["expired", "revoked", "garbage", "empty"])
def test_unusable_tokens_fall_back_to_the_normal_pending_flow(api_client, invite, fault):
    token = invite()
    if fault == "expired":
        Invitation.objects.update(expires_at=timezone.now() - timedelta(seconds=1))
    elif fault == "revoked":
        Invitation.objects.update(status="revoked", token_hash=None)
    elif fault == "garbage":
        token = "not-a-real-token"
    else:
        token = ""
    response = register(api_client, token)
    assert response.status_code == 202
    assert response.json() == {"detail": "Check your email to confirm your address."}
    assert User.objects.get(email=EMAIL).status == "pending"


def test_a_link_works_only_once(api_client, invite):
    token = invite()
    assert register(api_client, token).status_code == 201
    again = register(api_client, token, email="another@example.com")
    assert again.status_code == 202
    assert User.objects.get(email="another@example.com").status == "pending"


def test_an_existing_account_is_not_revealed_even_with_a_valid_token(api_client, invite, make_user):
    token = invite()
    make_user(email=EMAIL)  # registered between the invitation and the click
    response = register(api_client, token)
    assert response.status_code == 202
    assert User.objects.filter(email__iexact=EMAIL).count() == 1
    assert Invitation.objects.get().status == "sent"


def test_the_invitation_token_field_is_optional_and_strictly_typed(api_client):
    assert api_client.post(REGISTER_URL, registration_payload()).status_code == 202
    bad = registration_payload(email="x@example.com", invitation_token=["a"])
    assert api_client.post(REGISTER_URL, bad).status_code == 400


@pytest.mark.django_db(transaction=True)
@pytest.mark.usefixtures("truncate_audit")
def test_two_simultaneous_registrations_with_one_link_create_one_account(
    api_client, invite, inviter
):
    token = invite()
    results: list[int] = []

    def go():
        from rest_framework.test import APIClient

        try:
            results.append(register(APIClient(), token).status_code)
        finally:
            connections.close_all()

    threads = [threading.Thread(target=go) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert sorted(results) in ([201, 202], [202, 202])
    assert User.objects.filter(email=EMAIL).count() == 1
    assert Invitation.objects.get().status in ("registered", "sent")
