import json
import uuid
from datetime import timedelta

import pytest
from django.utils import timezone

from apps.accounts import services as accounts
from apps.accounts.models import User
from apps.accounts.tests.helpers import REGISTER_URL, VERIFY_URL, registration_payload
from apps.analytics import services as analytics
from apps.analytics.models import AnalyticsEvent, IdentityLink

pytestmark = pytest.mark.django_db

MEMBERS = "/api/v1/admin/members"
INVITES = "/api/v1/admin/invitations"


def events(name=None):
    queryset = AnalyticsEvent.objects.order_by("seq")
    return list(queryset.filter(name=name) if name else queryset)


@pytest.fixture
def admin(make_user):
    return make_user(roles=("community_admin",), email="admin@example.com")


@pytest.fixture
def as_admin(admin, client_for):
    return client_for(admin, mfa_age=5)


@pytest.fixture
def pending(make_user):
    return make_user(
        roles=(), status="pending", email="pending@example.com", email_verified_at=timezone.now()
    )


# --- the registration funnel ---


def test_verifying_an_email_is_recorded(api_client, run_outbox, last_token):
    api_client.post(REGISTER_URL, registration_payload())
    run_outbox()
    api_client.post(VERIFY_URL, {"token": last_token()})
    [event] = events("email_verified")
    assert event.actor_id == User.objects.get(email="new.member@example.com").pk
    assert event.properties == {} and event.source == "server"


def test_registering_with_a_visitor_id_joins_the_funnel_to_the_member(api_client):
    anon = uuid.uuid4()
    api_client.post(
        "/api/v1/events",
        {
            "anonymous_id": str(anon),
            "events": [{"name": "registration_started", "properties": {"source": "organic"}}],
        },
    )
    api_client.post(REGISTER_URL, registration_payload(anonymous_id=str(anon)))
    member = User.objects.get(email="new.member@example.com")
    assert IdentityLink.objects.get().user_id == member.pk
    # the pre-registration event and the member share the visitor id, so the funnel is continuous
    assert events("registration_started")[0].anonymous_id == IdentityLink.objects.get().anonymous_id


def test_a_repeat_registration_for_an_existing_address_links_nothing(api_client, make_user):
    make_user(email="taken@example.com")
    api_client.post(
        REGISTER_URL,
        registration_payload(email="taken@example.com", anonymous_id=str(uuid.uuid4())),
    )
    assert IdentityLink.objects.count() == 0


def test_registering_without_a_visitor_id_still_works(api_client):
    assert api_client.post(REGISTER_URL, registration_payload()).status_code == 202
    assert IdentityLink.objects.count() == 0


def test_a_malformed_visitor_id_is_refused(api_client):
    response = api_client.post(REGISTER_URL, registration_payload(anonymous_id="not-a-uuid"))
    assert response.status_code == 400


# --- approval and its aftermath ---


def test_approval_records_how_long_the_member_waited(as_admin, pending):
    User.objects.filter(pk=pending.pk).update(
        created_at=timezone.now() - timedelta(hours=50, minutes=30)
    )
    as_admin.post(f"{MEMBERS}/{pending.pk}/approve")
    [event] = events("member_approved")
    assert event.actor_id == pending.pk
    assert event.properties == {"approval_source": "admin", "time_to_decision_hours": 50}


def test_rejection_records_the_wait_but_never_the_reason(as_admin, pending):
    as_admin.post(f"{MEMBERS}/{pending.pk}/reject", {"reason": "ZZPRIVATEREASON not a founder"})
    [event] = events("member_rejected")
    assert set(event.properties) == {"time_to_decision_hours"}
    assert "ZZPRIVATEREASON" not in json.dumps(event.properties)


def test_suspension_and_removal_are_recorded_against_the_member(as_admin, make_user):
    member = make_user(email="m@example.com", email_verified_at=timezone.now())
    as_admin.post(f"{MEMBERS}/{member.pk}/suspend", {"reason": "ZZREASON"})
    as_admin.post(f"{MEMBERS}/{member.pk}/reinstate")
    as_admin.post(f"{MEMBERS}/{member.pk}/remove", {"reason": "ZZREASON"})
    assert [e.name for e in events()] == ["member_suspended", "member_removed"]
    assert {e.actor_id for e in events()} == {member.pk}


def test_a_failed_action_records_nothing(as_admin, make_user):
    active = make_user(email="active@example.com")
    as_admin.post(f"{MEMBERS}/{active.pk}/approve")  # not pending: a conflict
    assert events() == []


# --- invitations ---


def test_invitations_are_recorded_singly_and_in_bulk(as_admin, admin):
    as_admin.post(INVITES, {"email": "one@example.com", "role": "mentor"})
    as_admin.post(
        f"{INVITES}/bulk", {"csv": "email\ntwo@example.com\nthree@example.com\nnot-an-email\n"}
    )
    sent = events("invitation_sent")
    assert [e.properties for e in sent] == [
        {"role": "mentor", "bulk": False},
        {"role": "member", "bulk": True},
        {"role": "member", "bulk": True},
    ]
    assert {e.actor_id for e in sent} == {admin.pk}


def test_registering_through_an_invitation_records_both_events(api_client, admin, run_outbox):
    import hashlib

    from apps.accounts.models import Invitation

    accounts.create_invitation(actor=admin, email="new.member@example.com", role="mentor")
    Invitation.objects.update(token_hash=hashlib.sha256(b"known-token").hexdigest())
    api_client.post(REGISTER_URL, registration_payload(invitation_token="known-token"))
    member = User.objects.get(email="new.member@example.com")
    [registered] = events("invitation_registered")
    [approved] = events("member_approved")
    assert registered.actor_id == approved.actor_id == member.pk
    assert registered.properties == {"role": "mentor"}
    assert approved.properties == {"approval_source": "invitation", "time_to_decision_hours": 0}


# --- profiles ---


def test_profile_changes_are_recorded_with_the_new_score(make_user, client_for):
    member = make_user(email="m@example.com")
    client = client_for(member)
    etag = client.get("/api/v1/me/profile")["ETag"]
    client.patch(
        "/api/v1/me/profile", {"full_name": "Ada Obi", "bio": "ZZBIO text"}, HTTP_IF_MATCH=etag
    )
    client.patch("/api/v1/me/visibility", {"bio": "public"})
    updates = events("profile_updated")
    assert len(updates) == 2
    assert updates[0].properties["completeness"] > 0
    assert "ZZBIO" not in json.dumps([e.properties for e in updates])


# --- privacy and safety ---


def test_a_member_who_opted_out_leaves_no_trace_but_everything_still_works(as_admin, pending):
    analytics.set_opt_out(pending.pk, True)
    response = as_admin.post(f"{MEMBERS}/{pending.pk}/approve")
    assert response.status_code == 200
    pending.refresh_from_db()
    assert pending.status == "active"
    assert events() == []


def test_a_fault_in_analytics_never_breaks_an_admin_action(
    as_admin, pending, settings, monkeypatch
):
    settings.ANALYTICS_STRICT = False  # as in production

    def broken(*args, **kwargs):
        raise RuntimeError("analytics database unavailable")

    monkeypatch.setattr(AnalyticsEvent.objects, "create", broken)
    response = as_admin.post(f"{MEMBERS}/{pending.pk}/approve")
    assert response.status_code == 200
    pending.refresh_from_db()
    assert pending.status == "active"


def test_no_stored_property_anywhere_contains_personal_text(as_admin, make_user, api_client):
    """Run a busy scenario, then look at everything that was stored."""
    member = make_user(
        roles=(),
        status="pending",
        email="secret.person@example.com",
        email_verified_at=timezone.now(),
    )
    as_admin.post(f"{INVITES}", {"email": "guest@example.com", "message": "ZZINVITENOTE hello"})
    as_admin.post(f"{MEMBERS}/{member.pk}/reject", {"reason": "ZZREASON private detail"})
    api_client.post(REGISTER_URL, registration_payload())
    stored = json.dumps([[e.name, e.properties] for e in events()])
    for secret in (
        "secret.person",
        "guest@example.com",
        "ZZINVITENOTE",
        "ZZREASON",
        "Ada Founder",
        "Lagos",
    ):
        assert secret not in stored
