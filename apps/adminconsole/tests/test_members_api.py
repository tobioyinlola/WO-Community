from datetime import timedelta

import pytest
from django.utils import timezone

from apps.accounts.tests.helpers import AJAX, LOGIN_URL, PASSWORD, REFRESH_URL
from apps.audit.models import AuditLog
from apps.core.models import OutboxEvent

pytestmark = pytest.mark.django_db

MEMBERS = "/api/v1/admin/members"
QUEUES = "/api/v1/admin/queues"


def url(member, action=""):
    return f"{MEMBERS}/{member.pk}" + (f"/{action}" if action else "")


@pytest.fixture
def admin(make_user):
    return make_user(roles=("community_admin",), email="admin@example.com")


@pytest.fixture
def pending(make_user):
    return make_user(
        roles=(), status="pending", email="pending@example.com", email_verified_at=timezone.now()
    )


@pytest.fixture
def active(make_user):
    return make_user(email="active@example.com", email_verified_at=timezone.now())


@pytest.fixture
def as_admin(admin, client_for):
    return client_for(admin, mfa_age=5)


# --- access control, shared by every endpoint ---

ENDPOINTS = [
    ("get", MEMBERS, None),
    ("get", "{m}", None),
    ("get", QUEUES, None),
    ("post", "{m}/approve", None),
    ("post", "{m}/reject", {"reason": "spam"}),
    ("post", "{m}/suspend", {"reason": "spam"}),
    ("post", "{m}/reinstate", None),
    ("post", "{m}/remove", {"reason": "spam"}),
]


def call(client, method, path, body, member):
    path = path.replace("{m}", f"{MEMBERS}/{member.pk}")
    return getattr(client, method)(path, body) if body else getattr(client, method)(path)


@pytest.mark.parametrize(("method", "path", "body"), ENDPOINTS)
def test_anonymous_callers_are_rejected(api_client, active, method, path, body):
    assert call(api_client, method, path, body, active).status_code == 401


@pytest.mark.parametrize(("method", "path", "body"), ENDPOINTS)
def test_ordinary_members_are_forbidden(client_for, active, method, path, body):
    response = call(client_for(active, mfa_age=5), method, path, body, active)
    assert response.status_code == 403
    assert response.json()["code"] == "permission_denied"


@pytest.mark.parametrize(("method", "path", "body"), ENDPOINTS)
def test_content_editors_cannot_manage_members(client_for, make_user, active, method, path, body):
    editor = make_user(roles=("content_editor",), email="editor@example.com")
    assert call(client_for(editor, mfa_age=5), method, path, body, active).status_code == 403


@pytest.mark.parametrize(("method", "path", "body"), ENDPOINTS)
def test_admins_without_mfa_are_refused(client_for, admin, active, method, path, body):
    response = call(client_for(admin), method, path, body, active)
    assert response.status_code == 403
    assert response.json()["code"] == "mfa_required"


@pytest.mark.parametrize(
    ("path", "body"),
    [
        ("{m}/suspend", {"reason": "spam"}),
        ("{m}/reinstate", None),
        ("{m}/remove", {"reason": "spam"}),
    ],
)
def test_destructive_actions_need_a_recent_mfa_check(client_for, admin, active, path, body):
    stale = client_for(admin, mfa_age=3600)
    response = call(stale, "post", path, body, active)
    assert response.status_code == 403
    assert response.json()["code"] == "step_up_required"
    active.refresh_from_db()
    assert active.status == "active"


def test_viewing_and_approving_do_not_need_a_recent_check(client_for, admin, pending):
    stale = client_for(admin, mfa_age=3600)
    assert stale.get(MEMBERS).status_code == 200
    assert stale.post(url(pending, "approve")).status_code == 200


def test_a_suspended_admin_loses_access(client_for, admin):
    admin.status = "suspended"
    admin.save()
    assert client_for(admin, mfa_age=5).get(MEMBERS).status_code == 401


# --- listing and filtering ---


def test_list_returns_members_with_roles_and_paging(as_admin, active, pending):
    response = as_admin.get(MEMBERS)
    assert response.status_code == 200
    body = response.json()
    assert body["count"] == 3
    row = next(r for r in body["results"] if r["email"] == "active@example.com")
    assert row["roles"] == ["member"]
    assert row["status"] == "active"
    assert "password" not in row


def test_list_filters_by_status_role_search_and_verification(as_admin, make_user, active, pending):
    make_user(roles=(), status="pending", email="unverified@example.com")
    assert as_admin.get(MEMBERS, {"status": "pending"}).json()["count"] == 2
    assert (
        as_admin.get(MEMBERS, {"status": "pending", "email_verified": "true"}).json()["count"] == 1
    )
    assert (
        as_admin.get(MEMBERS, {"status": "pending", "email_verified": "false"}).json()["count"] == 1
    )
    assert as_admin.get(MEMBERS, {"role": "community_admin"}).json()["count"] == 1
    assert as_admin.get(MEMBERS, {"q": "ACTIVE@"}).json()["count"] == 1
    assert as_admin.get(MEMBERS, {"q": "nobody"}).json()["count"] == 0


def test_list_filters_by_join_date(as_admin, active):
    tomorrow = (timezone.now() + timedelta(days=1)).date().isoformat()
    assert as_admin.get(MEMBERS, {"joined_after": tomorrow}).json()["count"] == 0
    assert as_admin.get(MEMBERS, {"joined_before": tomorrow}).json()["count"] >= 1


def test_list_pagination_respects_limit_and_caps_it(as_admin, make_user):
    for n in range(5):
        make_user(email=f"extra{n}@example.com")
    page = as_admin.get(MEMBERS, {"limit": 2}).json()
    assert len(page["results"]) == 2
    assert page["next"]
    assert as_admin.get(MEMBERS, {"limit": 500}).status_code == 400


@pytest.mark.parametrize(
    "params", [{"status": "bogus"}, {"sort": "password"}, {"joined_after": "yesterday"}]
)
def test_list_rejects_unknown_or_invalid_parameters(as_admin, params):
    assert as_admin.get(MEMBERS, params).status_code == 400


def test_list_does_not_query_per_row(as_admin, make_user, django_assert_max_num_queries):
    for n in range(10):
        make_user(email=f"bulk{n}@example.com")
    with django_assert_max_num_queries(8):
        assert as_admin.get(MEMBERS).status_code == 200


def test_detail_and_unknown_member(as_admin, active):
    assert as_admin.get(url(active)).json()["email"] == "active@example.com"
    missing = "/api/v1/admin/members/00000000-0000-0000-0000-000000000000"
    assert as_admin.get(missing).status_code == 404


def test_queue_counts_split_verified_and_unverified(as_admin, make_user, pending):
    make_user(roles=(), status="pending", email="unverified@example.com")
    assert as_admin.get(QUEUES).json() == {
        "registrations_awaiting_approval": 1,
        "registrations_unverified": 1,
        "open_reports": 0,
        "jobs_awaiting_review": 0,
        "wins_awaiting_review": 0,
    }


# --- approve ---


def test_approving_activates_the_member_and_grants_the_member_role(
    as_admin, admin, pending, client_for
):
    response = as_admin.post(url(pending, "approve"))
    assert response.status_code == 200
    pending.refresh_from_db()
    assert pending.status == "active"
    assert pending.approved_by == admin
    assert pending.approval_source == "admin"
    assert pending.approved_at is not None
    assert response.json()["roles"] == ["member"]
    assert client_for(pending).get("/api/v1/me").json()["status"] == "active"


def test_approval_is_audited_with_before_and_after(as_admin, admin, pending):
    as_admin.post(url(pending, "approve"))
    entry = AuditLog.objects.get(action="member.approve")
    assert entry.actor_id == admin.pk
    assert entry.target_id == str(pending.pk)
    assert entry.before == {"status": "pending"}
    assert entry.after == {"status": "active"}
    assert entry.actor_roles == ["community_admin"]


def test_approved_member_is_emailed(as_admin, pending, run_outbox, sent_emails):
    as_admin.post(url(pending, "approve"))
    run_outbox()
    assert [m.to for m in sent_emails] == ["pending@example.com"]
    assert "approved" in sent_emails[0].subject.lower()


def test_unverified_registration_cannot_be_approved(as_admin, make_user):
    unverified = make_user(roles=(), status="pending", email="u@example.com")
    response = as_admin.post(url(unverified, "approve"))
    assert response.status_code == 409
    assert response.json()["code"] == "email_not_verified"
    unverified.refresh_from_db()
    assert unverified.status == "pending"


def test_approving_twice_is_a_conflict(as_admin, pending):
    as_admin.post(url(pending, "approve"))
    again = as_admin.post(url(pending, "approve"))
    assert again.status_code == 409
    assert again.json()["code"] == "invalid_transition"


def test_unknown_member_returns_404(as_admin):
    missing = "/api/v1/admin/members/00000000-0000-0000-0000-000000000000/approve"
    assert as_admin.post(missing).status_code == 404


def test_admins_cannot_act_on_themselves(as_admin, admin):
    assert as_admin.post(url(admin, "suspend"), {"reason": "x"}).status_code == 403
    assert as_admin.post(url(admin, "remove"), {"reason": "x"}).status_code == 403


def test_community_admin_cannot_change_another_admin_but_super_admin_can(
    make_user, client_for, as_admin
):
    other_admin = make_user(roles=("community_admin",), email="other@example.com")
    assert as_admin.post(url(other_admin, "suspend"), {"reason": "x"}).status_code == 403
    other_admin.refresh_from_db()
    assert other_admin.status == "active"
    boss = make_user(roles=("super_admin",), email="boss@example.com")
    response = client_for(boss, mfa_age=5).post(url(other_admin, "suspend"), {"reason": "x"})
    assert response.status_code == 200


# --- reject ---


def test_rejection_records_the_reason_and_emails_it(
    as_admin, pending, run_outbox, sent_emails, api_client
):
    response = as_admin.post(url(pending, "reject"), {"reason": "Not a founder"})
    assert response.status_code == 200
    pending.refresh_from_db()
    assert pending.status == "rejected"
    assert pending.status_reason == "Not a founder"
    run_outbox()
    assert "Not a founder" in sent_emails[0].text_body
    login = api_client.post(LOGIN_URL, {"email": "pending@example.com", "password": PASSWORD})
    assert login.status_code == 401


@pytest.mark.parametrize("body", [{}, {"reason": ""}, {"reason": "   "}])
def test_rejection_requires_a_reason(as_admin, pending, body):
    response = as_admin.post(url(pending, "reject"), body)
    assert response.status_code == 400
    assert "reason" in response.json()["errors"]
    pending.refresh_from_db()
    assert pending.status == "pending"


def test_rejection_rejects_unknown_fields(as_admin, pending):
    response = as_admin.post(url(pending, "reject"), {"reason": "no", "status": "active"})
    assert response.status_code == 400


def test_only_pending_registrations_can_be_rejected(as_admin, active):
    response = as_admin.post(url(active, "reject"), {"reason": "no"})
    assert response.status_code == 409


def test_rejected_person_gets_no_password_reset_email(
    as_admin, pending, api_client, run_outbox, sent_emails
):
    as_admin.post(url(pending, "reject"), {"reason": "no"})
    run_outbox()
    sent_emails.clear()
    api_client.post("/api/v1/auth/password/forgot", {"email": "pending@example.com"})
    run_outbox()
    assert sent_emails == []


# --- suspend and reinstate ---


def test_suspending_ends_sessions_and_access_tokens_immediately(as_admin, api_client, make_user):
    member = make_user(email="live@example.com", email_verified_at=timezone.now())
    login = api_client.post(LOGIN_URL, {"email": "live@example.com", "password": PASSWORD})
    access = login.json()["access_token"]
    refresh = login.cookies["wo_refresh"].value
    assert api_client.get("/api/v1/me", HTTP_AUTHORIZATION=f"Bearer {access}").status_code == 200

    assert as_admin.post(url(member, "suspend"), {"reason": "abuse"}).status_code == 200

    assert api_client.get("/api/v1/me", HTTP_AUTHORIZATION=f"Bearer {access}").status_code == 401
    api_client.cookies["wo_refresh"] = refresh
    assert api_client.post(REFRESH_URL, **AJAX).status_code == 401
    assert (
        api_client.post(LOGIN_URL, {"email": "live@example.com", "password": PASSWORD}).status_code
        == 401
    )


def test_suspension_needs_a_reason_and_an_active_member(as_admin, active, pending):
    assert as_admin.post(url(active, "suspend"), {}).status_code == 400
    assert as_admin.post(url(pending, "suspend"), {"reason": "x"}).status_code == 409


def test_reinstating_restores_access(as_admin, active, api_client):
    as_admin.post(url(active, "suspend"), {"reason": "cooling off"})
    assert as_admin.post(url(active, "reinstate")).status_code == 200
    active.refresh_from_db()
    assert active.status == "active"
    login = api_client.post(LOGIN_URL, {"email": "active@example.com", "password": PASSWORD})
    assert login.status_code == 200


def test_only_suspended_members_can_be_reinstated(as_admin, active):
    assert as_admin.post(url(active, "reinstate")).status_code == 409


def test_suspension_is_audited_with_its_reason(as_admin, active):
    as_admin.post(url(active, "suspend"), {"reason": "harassment report 42"})
    entry = AuditLog.objects.get(action="member.suspend")
    assert entry.reason == "harassment report 42"
    assert entry.before == {"status": "active"}
    assert entry.after == {"status": "suspended"}


# --- remove ---


def test_removal_ends_access_and_announces_the_takedown(as_admin, active, api_client):
    login = api_client.post(LOGIN_URL, {"email": "active@example.com", "password": PASSWORD})
    access = login.json()["access_token"]
    response = as_admin.post(url(active, "remove"), {"reason": "Terms violation"})
    assert response.status_code == 200
    active.refresh_from_db()
    assert active.status == "removed"
    assert active.status_reason == "Terms violation"
    assert api_client.get("/api/v1/me", HTTP_AUTHORIZATION=f"Bearer {access}").status_code == 401
    topics = list(OutboxEvent.objects.values_list("topic", flat=True))
    assert "accounts.member_removed" in topics
    assert AuditLog.objects.filter(action="member.remove", reason="Terms violation").exists()


@pytest.mark.parametrize("state", ["pending", "suspended", "rejected"])
def test_members_in_other_states_can_be_removed(as_admin, make_user, state):
    member = make_user(roles=(), status=state, email=f"{state}@example.com")
    assert as_admin.post(url(member, "remove"), {"reason": "cleanup"}).status_code == 200


def test_removal_requires_a_reason_and_cannot_repeat(as_admin, active):
    assert as_admin.post(url(active, "remove"), {}).status_code == 400
    as_admin.post(url(active, "remove"), {"reason": "gone"})
    assert as_admin.post(url(active, "remove"), {"reason": "again"}).status_code == 409


# --- concurrency ---


@pytest.mark.django_db(transaction=True, serialized_rollback=True)
@pytest.mark.usefixtures("truncate_audit")
def test_simultaneous_approvals_succeed_exactly_once(make_user, client_for):
    import threading

    from django.db import connections

    admins = [make_user(roles=("community_admin",), email=f"a{n}@example.com") for n in range(2)]
    target = make_user(
        roles=(), status="pending", email="race@example.com", email_verified_at=timezone.now()
    )
    clients = [client_for(a, mfa_age=5) for a in admins]
    results: list[int] = []

    def approve(client):
        try:
            results.append(client.post(url(target, "approve")).status_code)
        finally:
            connections.close_all()

    threads = [threading.Thread(target=approve, args=(c,)) for c in clients]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert sorted(results) == [200, 409]
    assert AuditLog.objects.filter(action="member.approve").count() == 1
