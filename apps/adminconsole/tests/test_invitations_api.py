from datetime import timedelta

import pytest
from django.utils import timezone

from apps.accounts.models import Invitation
from apps.audit.models import AuditLog

pytestmark = pytest.mark.django_db

INVITES = "/api/v1/admin/invitations"
BULK = f"{INVITES}/bulk"
INSPECT = "/api/v1/auth/invitations/inspect"


@pytest.fixture
def admin(make_user):
    return make_user(roles=("community_admin",), email="admin@example.com")


@pytest.fixture
def as_admin(admin, client_for):
    return client_for(admin, mfa_age=5)


def invite(client, email="guest@example.com", **extra):
    return client.post(INVITES, {"email": email, **extra})


@pytest.fixture
def invitation(as_admin):
    return Invitation.objects.get(pk=invite(as_admin).json()["id"])


# --- access control ---

ENDPOINTS = [
    ("get", INVITES, None),
    ("post", INVITES, {"email": "x@example.com"}),
    ("post", BULK, {"csv": "email\nx@example.com"}),
    ("get", "{i}", None),
    ("post", "{i}/resend", None),
    ("post", "{i}/revoke", None),
]


def call(client, method, path, body, invitation):
    path = path.replace("{i}", f"{INVITES}/{invitation.pk}")
    return getattr(client, method)(path, body) if body else getattr(client, method)(path)


@pytest.mark.parametrize(("method", "path", "body"), ENDPOINTS)
def test_anonymous_callers_are_rejected(api_client, invitation, method, path, body):
    assert call(api_client, method, path, body, invitation).status_code == 401


@pytest.mark.parametrize(("method", "path", "body"), ENDPOINTS)
def test_members_and_editors_are_forbidden(client_for, make_user, invitation, method, path, body):
    for roles in (("member",), ("content_editor",)):
        user = make_user(roles=roles, email=f"{roles[0]}@example.com")
        response = call(client_for(user, mfa_age=5), method, path, body, invitation)
        assert response.status_code == 403
        assert response.json()["code"] == "permission_denied"


@pytest.mark.parametrize(("method", "path", "body"), ENDPOINTS)
def test_admins_without_mfa_are_refused(client_for, admin, invitation, method, path, body):
    response = call(client_for(admin), method, path, body, invitation)
    assert response.status_code == 403
    assert response.json()["code"] == "mfa_required"


# --- create ---


def test_creating_an_invitation_returns_it_without_any_token(as_admin, admin):
    response = invite(as_admin, "Guest@Example.com", message="Welcome!")
    assert response.status_code == 201
    body = response.json()
    assert body["email"] == "guest@example.com"
    assert body["status"] == "sent"
    assert body["role"] == "member"
    assert body["invited_by"] == str(admin.pk)
    assert not {"token", "token_hash", "link"} & set(body)


def test_the_invitee_is_emailed_a_link_with_the_personal_message(
    as_admin, run_outbox, sent_emails, last_invitation_token
):
    invite(as_admin, message="We loved your demo day pitch.")
    run_outbox()
    assert [m.to for m in sent_emails] == ["guest@example.com"]
    body = sent_emails[0].text_body
    assert "We loved your demo day pitch." in body
    assert "https://app.test/register?invitation=" in body
    assert "expires on" in body
    assert len(last_invitation_token()) >= 40


def test_only_the_hash_of_the_link_is_stored(as_admin, run_outbox, last_invitation_token):
    invite(as_admin)
    run_outbox()
    token = last_invitation_token()
    stored = Invitation.objects.get()
    assert stored.token_hash and stored.token_hash != token and len(stored.token_hash) == 64
    assert stored.last_sent_at is not None


def test_creation_is_audited(as_admin, admin):
    invite(as_admin)
    entry = AuditLog.objects.get(action="invitation.created")
    assert entry.actor_id == admin.pk
    assert entry.after == {"role": "member"}


def test_mentor_is_an_allowed_role(as_admin):
    assert invite(as_admin, role="mentor").json()["role"] == "mentor"


@pytest.mark.parametrize("role", ["super_admin", "community_admin", "content_editor", "nonsense"])
def test_admin_and_unknown_roles_cannot_be_invited(as_admin, role):
    response = invite(as_admin, role=role)
    assert response.status_code == 400
    assert "role" in response.json()["errors"]
    assert Invitation.objects.count() == 0


@pytest.mark.parametrize("email", ["", "not-an-email", "a@b", "x" * 300 + "@example.com"])
def test_invalid_addresses_are_rejected(as_admin, email):
    assert invite(as_admin, email=email).status_code == 400


def test_overlong_messages_are_rejected(as_admin):
    response = invite(as_admin, message="x" * 501)
    assert response.status_code == 400
    assert "message" in response.json()["errors"]


def test_control_characters_are_stripped_from_messages(as_admin):
    invite(as_admin, message="Hello\x07 there!\nSecond line")
    assert Invitation.objects.get().message == "Hello there!\nSecond line"


def test_null_characters_are_rejected(as_admin):
    assert invite(as_admin, message="bad\x00message").status_code == 400


def test_unknown_fields_are_rejected(as_admin):
    assert invite(as_admin, status="registered").status_code == 400


def test_a_live_invitation_blocks_a_second_one(as_admin):
    invite(as_admin)
    again = invite(as_admin, "GUEST@example.com")
    assert again.status_code == 409
    assert again.json()["code"] == "already_invited"
    assert Invitation.objects.count() == 1


def test_people_who_already_have_an_account_cannot_be_invited(as_admin, make_user):
    make_user(email="guest@example.com")
    response = invite(as_admin)
    assert response.status_code == 409
    assert response.json()["code"] == "already_registered"


def test_an_expired_invitation_is_replaced_by_a_new_one(as_admin):
    old = Invitation.objects.get(pk=invite(as_admin).json()["id"])
    Invitation.objects.filter(pk=old.pk).update(expires_at=timezone.now() - timedelta(days=1))
    assert invite(as_admin).status_code == 201
    old.refresh_from_db()
    assert old.status == "revoked"
    assert Invitation.objects.filter(status="sent").count() == 1


@pytest.mark.django_db(transaction=True, serialized_rollback=True)
@pytest.mark.usefixtures("truncate_audit")
def test_simultaneous_invitations_for_one_address_create_only_one(make_user, client_for):
    import threading

    from django.db import connections

    admins = [make_user(roles=("community_admin",), email=f"a{n}@example.com") for n in range(2)]
    clients = [client_for(a, mfa_age=5) for a in admins]
    results: list[int] = []

    def send(client):
        try:
            results.append(invite(client, "race@example.com").status_code)
        finally:
            connections.close_all()

    threads = [threading.Thread(target=send, args=(c,)) for c in clients]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert sorted(results) == [201, 409]
    assert Invitation.objects.count() == 1


# --- list and detail ---


def test_list_shows_status_including_computed_expiry(as_admin, make_user):
    for n in range(3):
        invite(as_admin, f"p{n}@example.com")
    ids = list(Invitation.objects.order_by("created_at").values_list("pk", flat=True))
    Invitation.objects.filter(pk=ids[1]).update(expires_at=timezone.now() - timedelta(minutes=1))
    Invitation.objects.filter(pk=ids[2]).update(status="registered")
    statuses = {r["email"]: r["status"] for r in as_admin.get(INVITES).json()["results"]}
    assert statuses == {
        "p0@example.com": "sent",
        "p1@example.com": "expired",
        "p2@example.com": "registered",
    }


def test_list_filters_by_status_and_search(as_admin):
    for name in ("ann", "bob", "cat"):
        invite(as_admin, f"{name}@example.com")
    Invitation.objects.filter(email="bob@example.com").update(
        expires_at=timezone.now() - timedelta(minutes=1)
    )
    Invitation.objects.filter(email="cat@example.com").update(status="revoked")
    assert as_admin.get(INVITES, {"status": "sent"}).json()["count"] == 1
    assert as_admin.get(INVITES, {"status": "expired"}).json()["count"] == 1
    assert as_admin.get(INVITES, {"status": "revoked"}).json()["count"] == 1
    assert as_admin.get(INVITES, {"q": "ANN"}).json()["count"] == 1


@pytest.mark.parametrize("params", [{"status": "bogus"}, {"limit": 500}, {"order": "email"}])
def test_list_rejects_bad_parameters(as_admin, params):
    assert as_admin.get(INVITES, params).status_code == 400


def test_list_does_not_query_per_row(as_admin, django_assert_max_num_queries):
    for n in range(8):
        invite(as_admin, f"q{n}@example.com")
    with django_assert_max_num_queries(6):
        assert as_admin.get(INVITES).status_code == 200


def test_detail_and_unknown_invitation(as_admin, invitation):
    assert as_admin.get(f"{INVITES}/{invitation.pk}").json()["email"] == "guest@example.com"
    assert as_admin.get(f"{INVITES}/00000000-0000-0000-0000-000000000000").status_code == 404


# --- opened ---


def test_opening_the_link_marks_the_invitation_opened(
    as_admin, api_client, run_outbox, last_invitation_token
):
    invite(as_admin, message="Hi")
    run_outbox()
    response = api_client.post(INSPECT, {"token": last_invitation_token()})
    assert response.status_code == 200
    body = response.json()
    assert body["email"] == "guest@example.com"
    assert body["role"] == "member"
    assert body["message"] == "Hi"
    assert response["Cache-Control"] == "no-store"
    row = as_admin.get(INVITES).json()["results"][0]
    assert row["status"] == "opened"
    assert row["opened_at"]


def test_inspecting_does_not_consume_the_link(
    as_admin, api_client, run_outbox, last_invitation_token
):
    invite(as_admin)
    run_outbox()
    token = last_invitation_token()
    assert api_client.post(INSPECT, {"token": token}).status_code == 200
    assert api_client.post(INSPECT, {"token": token}).status_code == 200


@pytest.mark.parametrize("token", ["nope", "x" * 100])
def test_unknown_links_are_rejected(api_client, token):
    response = api_client.post(INSPECT, {"token": token})
    assert response.status_code == 400
    assert response.json()["errors"]["token"]


def test_expired_links_are_rejected(as_admin, api_client, run_outbox, last_invitation_token):
    invite(as_admin)
    run_outbox()
    Invitation.objects.update(expires_at=timezone.now() - timedelta(seconds=1))
    assert api_client.post(INSPECT, {"token": last_invitation_token()}).status_code == 400


# --- resend and revoke ---


def test_resending_replaces_the_link_and_extends_the_expiry(
    as_admin, api_client, run_outbox, sent_emails, last_invitation_token
):
    invite(as_admin)
    run_outbox()
    first = last_invitation_token()
    api_client.post(INSPECT, {"token": first})
    Invitation.objects.update(expires_at=timezone.now() + timedelta(hours=1))
    pk = Invitation.objects.get().pk

    response = as_admin.post(f"{INVITES}/{pk}/resend")
    assert response.status_code == 200
    assert response.json()["status"] == "sent"
    run_outbox()
    second = last_invitation_token()

    assert len(sent_emails) == 2
    assert second != first
    assert api_client.post(INSPECT, {"token": first}).status_code == 400
    assert api_client.post(INSPECT, {"token": second}).status_code == 200
    assert Invitation.objects.get().expires_at > timezone.now() + timedelta(days=6)
    assert AuditLog.objects.filter(action="invitation.resent").exists()


def test_an_expired_invitation_can_be_resent(as_admin, run_outbox, sent_emails):
    invite(as_admin)
    Invitation.objects.update(expires_at=timezone.now() - timedelta(days=1))
    pk = Invitation.objects.get().pk
    assert as_admin.post(f"{INVITES}/{pk}/resend").status_code == 200
    run_outbox()
    assert len(sent_emails) == 1


def test_revoking_kills_the_link(as_admin, api_client, run_outbox, last_invitation_token):
    invite(as_admin)
    run_outbox()
    token = last_invitation_token()
    pk = Invitation.objects.get().pk
    response = as_admin.post(f"{INVITES}/{pk}/revoke")
    assert response.status_code == 200
    assert response.json()["status"] == "revoked"
    assert api_client.post(INSPECT, {"token": token}).status_code == 400
    assert Invitation.objects.get().token_hash is None
    assert AuditLog.objects.filter(action="invitation.revoked_by_admin").exists()


def test_a_revoked_invitation_sends_nothing_and_allows_a_new_one(as_admin, run_outbox, sent_emails):
    invite(as_admin)
    pk = Invitation.objects.get().pk
    as_admin.post(f"{INVITES}/{pk}/revoke")
    run_outbox()  # the queued email must not go out for a revoked invitation
    assert sent_emails == []
    assert invite(as_admin).status_code == 201


@pytest.mark.parametrize("final", ["registered", "revoked"])
def test_finished_invitations_cannot_be_resent_or_revoked(as_admin, invitation, final):
    Invitation.objects.filter(pk=invitation.pk).update(status=final)
    for action in ("resend", "revoke"):
        response = as_admin.post(f"{INVITES}/{invitation.pk}/{action}")
        assert response.status_code == 409
        assert response.json()["code"] == "invalid_transition"


def test_resend_is_refused_once_the_person_has_an_account(as_admin, invitation, make_user):
    make_user(email="guest@example.com")
    response = as_admin.post(f"{INVITES}/{invitation.pk}/resend")
    assert response.status_code == 409
    assert response.json()["code"] == "already_registered"


def test_unknown_invitation_returns_404(as_admin):
    missing = f"{INVITES}/00000000-0000-0000-0000-000000000000"
    assert as_admin.post(f"{missing}/resend").status_code == 404
    assert as_admin.post(f"{missing}/revoke").status_code == 404


# --- bulk import ---


def bulk(client, csv_text):
    return client.post(BULK, {"csv": csv_text})


def test_bulk_import_invites_everyone_and_emails_them(as_admin, run_outbox, sent_emails):
    csv_text = (
        "email,role,message\n"
        "a@example.com,member,Hi A\n"
        "b@example.com,mentor,Hi B\n"
        "c@example.com,,\n"
    )
    response = bulk(as_admin, csv_text)
    assert response.status_code == 200
    body = response.json()
    assert (body["created"], body["skipped"]) == (3, 0)
    assert [r["row"] for r in body["rows"]] == [2, 3, 4]
    assert {i.email: i.role for i in Invitation.objects.all()} == {
        "a@example.com": "member",
        "b@example.com": "mentor",
        "c@example.com": "member",
    }
    run_outbox()
    assert sorted(m.to for m in sent_emails) == ["a@example.com", "b@example.com", "c@example.com"]
    assert AuditLog.objects.get(action="invitation.bulk_imported").after == {
        "created": 3,
        "skipped": 0,
    }


def test_bad_rows_are_reported_and_do_not_stop_the_rest(as_admin, make_user):
    make_user(email="member@example.com")
    as_admin.post(INVITES, {"email": "live@example.com"})
    csv_text = "\n".join(
        [
            "email,role,message",
            "good@example.com,member,",
            "not-an-email,member,",
            "member@example.com,member,",
            "live@example.com,member,",
            "good@example.com,member,",
            "boss@example.com,super_admin,",
            "ok@example.com,member,fine",
        ]
    )
    body = bulk(as_admin, csv_text).json()
    assert (body["created"], body["skipped"]) == (2, 5)
    reasons = {r["row"]: r["reason"] for r in body["rows"] if r["result"] == "skipped"}
    assert set(reasons) == {3, 4, 5, 6, 7}
    assert "already has an account" in reasons[4]
    assert "live invitation" in reasons[5]
    assert "Duplicate" in reasons[6]
    assert Invitation.objects.filter(email="boss@example.com").count() == 0


def test_csv_with_quotes_commas_and_a_byte_order_mark_is_parsed(as_admin):
    csv_text = '﻿Email,Message\nq@example.com,"Hello, world\nsecond line"\n'
    assert bulk(as_admin, csv_text).json()["created"] == 1
    assert Invitation.objects.get().message == "Hello, world\nsecond line"


def test_spreadsheet_formulas_are_stored_as_plain_text(as_admin):
    bulk(as_admin, 'email,message\nf@example.com,"=HYPERLINK(""http://evil"")"\n')
    assert Invitation.objects.get().message == '=HYPERLINK("http://evil")'


@pytest.mark.parametrize(
    ("csv_text", "field"),
    [
        ("", "csv"),
        ("name\nx\n", "csv"),
        ("email,colour\na@example.com,red\n", "csv"),
        ("email\n", "csv"),
    ],
)
def test_malformed_files_are_rejected_whole(as_admin, csv_text, field):
    response = bulk(as_admin, csv_text) if csv_text else as_admin.post(BULK, {"csv": ""})
    assert response.status_code == 400
    assert field in response.json()["errors"]
    assert Invitation.objects.count() == 0


def test_too_many_rows_are_rejected(as_admin, settings):
    settings.INVITATION_BULK_MAX_ROWS = 3
    rows = "\n".join(f"r{n}@example.com" for n in range(4))
    response = bulk(as_admin, f"email\n{rows}\n")
    assert response.status_code == 400
    assert Invitation.objects.count() == 0


def test_oversized_files_are_rejected(as_admin, settings):
    settings.INVITATION_BULK_MAX_BYTES = 50
    response = bulk(as_admin, "email\n" + "\n".join(f"person{n}@example.com" for n in range(10)))
    assert response.status_code == 400


def test_bulk_import_is_rate_limited(as_admin, monkeypatch):
    from rest_framework.throttling import ScopedRateThrottle

    monkeypatch.setattr(
        ScopedRateThrottle,
        "THROTTLE_RATES",
        {**ScopedRateThrottle.THROTTLE_RATES, "admin_bulk": "2/hour"},
    )
    statuses = [bulk(as_admin, f"email\nn{n}@example.com\n").status_code for n in range(3)]
    assert statuses == [200, 200, 429]


def test_resending_before_the_first_email_goes_out_sends_exactly_one(
    as_admin, run_outbox, sent_emails, last_invitation_token, api_client
):
    invite(as_admin)  # the first email is still queued
    pk = Invitation.objects.get().pk
    as_admin.post(f"{INVITES}/{pk}/resend")
    run_outbox()
    assert len(sent_emails) == 1
    assert api_client.post(INSPECT, {"token": last_invitation_token()}).status_code == 200


def test_a_failed_send_leaves_no_link_behind_and_a_retry_succeeds(
    as_admin, sent_emails, monkeypatch
):
    from celery.exceptions import Retry

    from apps.core.models import OutboxEvent
    from apps.notifications import emails
    from apps.notifications.tasks import send_invitation_email

    invite(as_admin)
    event_id = str(OutboxEvent.objects.get().pk)
    real = emails.send_invitation

    def broken(*args, **kwargs):
        raise OSError("smtp down")

    monkeypatch.setattr(emails, "send_invitation", broken)
    with pytest.raises((OSError, Retry)):  # the base task schedules a retry on failure
        send_invitation_email.apply(args=[event_id], throw=True)
    assert Invitation.objects.get().token_hash is None

    monkeypatch.setattr(emails, "send_invitation", real)
    send_invitation_email.apply(args=[event_id], throw=True)
    assert len(sent_emails) == 1
    assert Invitation.objects.get().token_hash is not None


def test_a_retried_event_does_not_send_a_second_email(as_admin, run_outbox, sent_emails):
    from apps.core.models import OutboxEvent
    from apps.notifications.tasks import send_invitation_email

    invite(as_admin)
    run_outbox()
    send_invitation_email.apply(args=[str(OutboxEvent.objects.get().pk)], throw=True)
    assert len(sent_emails) == 1
