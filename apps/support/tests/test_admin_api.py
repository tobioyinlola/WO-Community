from datetime import timedelta

import pytest
from django.utils import timezone

from apps.audit.models import AuditLog
from apps.notifications.models import Notification
from apps.support.models import SupportCannedReply, SupportTicket
from apps.support.tests.helpers import ADMIN_TICKETS, TICKETS, active, body, ready_attachment

pytestmark = pytest.mark.django_db

ADMIN = "/api/v1/admin/support"


@pytest.fixture
def ada(make_user):
    return active(make_user, "ada@example.com", "Adaeze Okafor")


@pytest.fixture
def sam(make_user):
    return active(make_user, "sam@example.com", "Support Sam", roles=("community_admin",))


@pytest.fixture
def editor(make_user):
    return active(make_user, "editor@example.com", "Edie Editor", roles=("content_editor",))


@pytest.fixture
def as_ada(ada, client_for):
    return client_for(ada)


@pytest.fixture
def as_sam(sam, client_for):
    return client_for(sam, mfa_age=5)


def open_one(client, **overrides):
    response = client.post(TICKETS, body(**overrides), format="json")
    assert response.status_code == 201, response.content
    return response.json()


def one(ticket, tail=""):
    return f"{ADMIN_TICKETS}/{ticket['id']}" + (f"/{tail}" if tail else "")


def say(client, ticket, text="<p>Try the pencil icon on the startup page.</p>", **extra):
    return client.post(one(ticket, "messages"), {"body": text, **extra}, format="json")


# --- who may call what ---

NIL = "00000000-0000-0000-0000-000000000001"
ENDPOINTS = [
    ("get", f"{ADMIN}/tickets", None),
    ("get", f"{ADMIN}/tickets/{NIL}", None),
    ("patch", f"{ADMIN}/tickets/{NIL}", {"priority": "high"}),
    ("post", f"{ADMIN}/tickets/{NIL}/messages", {"body": "<p>x</p>"}),
    ("post", f"{ADMIN}/tickets/{NIL}/resolve", None),
    ("post", f"{ADMIN}/tickets/{NIL}/reopen", None),
    ("get", f"{ADMIN}/stats", None),
    ("get", f"{ADMIN}/agents", None),
    ("get", f"{ADMIN}/canned-replies", None),
    ("post", f"{ADMIN}/canned-replies", {"title": "Hello", "body": "Hi there"}),
    ("put", f"{ADMIN}/canned-replies/{NIL}", {"title": "Hello", "body": "Hi there"}),
    ("delete", f"{ADMIN}/canned-replies/{NIL}", None),
    ("get", f"{ADMIN}/attachments/{NIL}/download", None),
]


def call(client, method, path, payload):
    send = getattr(client, method)
    return send(path, payload, format="json") if payload is not None else send(path)


@pytest.mark.parametrize("method,path,payload", ENDPOINTS)
def test_signing_in_is_required(api_client, method, path, payload):
    assert call(api_client, method, path, payload).status_code == 401


@pytest.mark.parametrize("method,path,payload", ENDPOINTS)
def test_an_ordinary_member_is_refused(ada, client_for, method, path, payload):
    assert call(client_for(ada, mfa_age=5), method, path, payload).status_code == 403


@pytest.mark.parametrize("method,path,payload", ENDPOINTS)
def test_an_editor_without_the_support_permission_is_refused(
    editor, client_for, method, path, payload
):
    assert call(client_for(editor, mfa_age=5), method, path, payload).status_code == 403


@pytest.mark.parametrize("method,path,payload", ENDPOINTS)
def test_an_admin_who_has_not_passed_the_second_step_is_refused(
    sam, client_for, method, path, payload
):
    assert call(client_for(sam), method, path, payload).status_code == 403


@pytest.mark.parametrize(
    "method,path,payload",
    [e for e in ENDPOINTS if NIL in e[1]],
)
def test_an_unknown_item_is_not_found(as_sam, method, path, payload):
    assert call(as_sam, method, path, payload).status_code == 404


# --- the inbox ---


def test_the_inbox_lists_requests_with_who_asked(as_ada, as_sam):
    ticket = open_one(as_ada)
    page = as_sam.get(f"{ADMIN}/tickets").json()
    assert page["count"] == 1
    row = page["results"][0]
    assert row["id"] == ticket["id"] and row["member"]["name"] == "Adaeze Okafor"
    assert row["member"]["email"] == "ada@example.com" and row["assignee"] is None
    assert row["priority"] == "normal" and row["is_overdue"] is False


def test_filters_and_search(as_ada, as_sam, sam):
    a = open_one(as_ada, subject="Cannot sign in on my phone", category="account")
    b = open_one(as_ada, subject="Question about the course", category="learning")
    as_sam.patch(one(a), {"assignee": str(sam.pk)}, format="json")

    def get(**q):
        return [t["id"] for t in as_sam.get(f"{ADMIN}/tickets", q).json()["results"]]

    assert get(category="learning") == [b["id"]]
    assert get(assignee="me") == [a["id"]]
    assert get(assignee="unassigned") == [b["id"]]
    assert get(assignee=str(sam.pk)) == [a["id"]]
    assert get(q="phone") == [a["id"]]
    assert get(q=a["reference"]) == [a["id"]] and get(q=f"#{a['number']}") == [a["id"]]
    assert set(get(status="open")) == {a["id"], b["id"]}
    assert get(status="resolved") == []
    assert get(created_after=(timezone.now() + timedelta(days=1)).date().isoformat()) == []


def test_sorting_and_paging(as_ada, as_sam):
    ids = [open_one(as_ada, subject=f"Request number {n} for sorting")["id"] for n in range(3)]
    asc = [
        t["id"] for t in as_sam.get(f"{ADMIN}/tickets", {"ordering": "number"}).json()["results"]
    ]
    assert asc == ids
    page = as_sam.get(f"{ADMIN}/tickets", {"ordering": "-number", "limit": 2}).json()
    assert page["count"] == 3 and len(page["results"]) == 2 and page["next"]


@pytest.mark.parametrize(
    "query",
    [
        {"ordering": "subject"},
        {"status": "nope"},
        {"limit": 500},
        {"assignee": "someone"},
        {"x": 1},
    ],
)
def test_bad_filters_are_refused(as_sam, query):
    assert as_sam.get(f"{ADMIN}/tickets", query).status_code == 400


def test_the_detail_includes_internal_notes_and_the_members_history(as_ada, as_sam):
    first = open_one(as_ada)
    second = open_one(as_ada, subject="A second request later")
    say(as_sam, first, "<p>Duplicate account suspected.</p>", internal=True)
    detail = as_sam.get(one(first)).json()
    assert [m["is_internal"] for m in detail["messages"]] == [False, True]
    assert detail["previous_tickets"] == 1 and detail["member_joined_at"]
    assert second["id"] != first["id"]


# --- replying ---


def test_a_reply_answers_the_member_and_moves_the_request(as_ada, as_sam, ada, sam, sent_emails):
    ticket = open_one(as_ada)
    response = say(as_sam, ticket)
    assert response.status_code == 201
    detail = as_sam.get(one(ticket)).json()
    assert detail["status"] == "awaiting_member"
    assert detail["first_response_at"] and detail["assignee"]["id"] == str(sam.pk)
    note = Notification.objects.get(user=ada, type="ticket_reply")
    assert note.payload["reference"] == ticket["reference"]
    mail = sent_emails[-1]
    assert mail.to == "ada@example.com" and "pencil icon" in mail.text_body
    assert f"/support/{ticket['id']}" in mail.text_body
    assert mail.no_reply is True and "support@" not in mail.text_body


def test_the_member_sees_the_reply_with_the_senders_name_and_a_support_flag(as_ada, as_sam):
    ticket = open_one(as_ada)
    say(as_sam, ticket)
    last = as_ada.get(f"{TICKETS}/{ticket['id']}").json()["messages"][-1]
    assert last["author"]["name"] == "Support Sam" and last["author"]["is_support"] is True


def test_script_in_a_reply_is_removed(as_ada, as_sam):
    ticket = open_one(as_ada)
    say(as_sam, ticket, "<p>Hello</p><script>alert(1)</script><img src=x onerror=alert(1)>")
    html = as_sam.get(one(ticket)).json()["messages"][-1]["body"]
    assert "<script" not in html and "onerror" not in html and "Hello" in html


def test_an_internal_note_changes_nothing_and_tells_nobody(as_ada, as_sam, ada, sent_emails):
    ticket = open_one(as_ada)
    before = len(sent_emails)
    assert say(as_sam, ticket, "<p>Note to self.</p>", internal=True).status_code == 201
    detail = as_sam.get(one(ticket)).json()
    assert detail["status"] == "open" and detail["first_response_at"] is None
    assert not Notification.objects.filter(user=ada, type="ticket_reply").exists()
    assert len(sent_emails) == before


def test_send_and_resolve_records_who_and_when_and_tells_the_member(as_ada, as_sam, ada, sam):
    ticket = open_one(as_ada)
    say(as_sam, ticket, "<p>All fixed now.</p>", status="resolved")
    detail = as_sam.get(one(ticket)).json()
    assert detail["status"] == "resolved" and detail["resolved_at"]
    assert SupportTicket.objects.get(pk=ticket["id"]).resolved_by_id == sam.pk
    assert Notification.objects.filter(user=ada, type="ticket_resolved").count() == 1


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"body": ""},
        {"body": "<p> </p>"},
        {"body": "<p>x</p>", "status": "open"},
        {"body": "<p>x</p>", "x": 1},
    ],
)
def test_a_bad_reply_is_refused(as_ada, as_sam, payload):
    ticket = open_one(as_ada)
    assert as_sam.post(one(ticket, "messages"), payload, format="json").status_code == 400


def test_a_reply_can_carry_a_file_and_the_admin_can_download_it(as_ada, as_sam, sam, monkeypatch):
    monkeypatch.setattr(
        "apps.support.services.uploads.document_link", lambda **kw: ("https://files.test/y", 300)
    )
    ticket = open_one(as_ada)
    say(as_sam, ticket, attachments=[str(ready_attachment(sam, "guide.pdf").pk)])
    file_id = as_sam.get(one(ticket)).json()["messages"][-1]["attachments"][0]["id"]
    assert (
        as_sam.get(f"{ADMIN}/attachments/{file_id}/download").json()["url"]
        == "https://files.test/y"
    )


def test_a_reply_to_someone_without_an_account_goes_by_email(api_client, as_sam, sent_emails):
    api_client.post(
        "/api/v1/support/contact",
        {
            "name": "Kemi",
            "email": "kemi@example.com",
            "subject": "Cannot sign in",
            "message": "I forgot which email I used.",
        },
        format="json",
    )
    ticket = SupportTicket.objects.get()
    say(as_sam, {"id": str(ticket.pk)}, "<p>Try the address you registered with.</p>")
    assert [m.to for m in sent_emails] == ["kemi@example.com", "kemi@example.com"]
    assert "registered with" in sent_emails[-1].text_body and sent_emails[-1].no_reply is True


# --- changing a request ---


def test_status_assignee_priority_and_category_can_be_changed_and_are_audited(
    as_ada, as_sam, sam, truncate_audit
):
    ticket = open_one(as_ada)
    changed = as_sam.patch(
        one(ticket),
        {
            "status": "in_progress",
            "assignee": str(sam.pk),
            "priority": "high",
            "category": "account",
        },
        format="json",
    ).json()
    assert changed["status"] == "in_progress" and changed["priority"] == "high"
    assert changed["category"] == "account" and changed["assignee"]["id"] == str(sam.pk)
    entry = AuditLog.objects.filter(action="support.ticket.updated").get()
    assert entry.before["status"] == "open" and entry.after["status"] == "in_progress"
    assert entry.after["assignee"] == str(sam.pk)


def test_a_request_can_only_go_to_someone_who_handles_support(as_ada, as_sam, editor, ada):
    ticket = open_one(as_ada)
    for who in (editor, ada):
        refused = as_sam.patch(one(ticket), {"assignee": str(who.pk)}, format="json")
        assert refused.status_code == 400
    assert as_sam.patch(one(ticket), {"assignee": None}, format="json").status_code == 200


@pytest.mark.parametrize(
    "payload",
    [{"status": "nope"}, {"priority": "urgent"}, {"category": "x"}, {"assignee": "abc"}, {"x": 1}],
)
def test_bad_changes_are_refused(as_ada, as_sam, payload):
    ticket = open_one(as_ada)
    assert as_sam.patch(one(ticket), payload, format="json").status_code == 400


def test_resolve_and_reopen(as_ada, as_sam, ada):
    ticket = open_one(as_ada)
    assert as_sam.post(one(ticket, "reopen")).status_code == 409
    done = as_sam.post(one(ticket, "resolve")).json()
    assert done["status"] == "resolved"
    assert Notification.objects.filter(user=ada, type="ticket_resolved").count() == 1
    again = as_sam.post(one(ticket, "resolve")).json()
    assert again["status"] == "resolved"
    assert Notification.objects.filter(user=ada, type="ticket_resolved").count() == 1
    back = as_sam.post(one(ticket, "reopen")).json()
    assert back["status"] == "open" and back["reopened_count"] == 1


def test_an_admin_may_reopen_after_the_members_window(as_ada, as_sam):
    ticket = open_one(as_ada)
    SupportTicket.objects.filter(pk=ticket["id"]).update(
        status="resolved", resolved_at=timezone.now() - timedelta(days=40)
    )
    assert as_sam.post(one(ticket, "reopen")).status_code == 200


# --- numbers for the top of the inbox ---


def test_stats(as_ada, as_sam):
    a, b = open_one(as_ada), open_one(as_ada, subject="Another request here")
    say(as_sam, a)
    as_sam.post(one(b, "resolve"))
    SupportTicket.objects.filter(pk=a["id"]).update(created_at=timezone.now() - timedelta(hours=3))
    stats = as_sam.get(f"{ADMIN}/stats").json()
    assert stats["counts"]["awaiting_member"] == 1 and stats["counts"]["resolved_this_week"] == 1
    assert stats["counts"]["working"] == 1 and stats["counts"]["total"] == 2
    assert stats["median_first_response_seconds"] >= 3 * 3600 - 60 and stats["sla_hours"] == 24


def test_a_request_nobody_answered_after_the_service_level_is_overdue(as_ada, as_sam):
    ticket = open_one(as_ada)
    assert as_sam.get(f"{ADMIN}/stats").json()["overdue"] == 0
    SupportTicket.objects.filter(pk=ticket["id"]).update(
        created_at=timezone.now() - timedelta(hours=25)
    )
    assert as_sam.get(f"{ADMIN}/stats").json()["overdue"] == 1
    assert as_sam.get(one(ticket)).json()["is_overdue"] is True
    queues = as_sam.get("/api/v1/admin/queues").json()
    assert queues["support_overdue"] == 1 and queues["support_unanswered"] == 1


def test_the_people_a_request_can_be_assigned_to(as_sam, sam, editor):
    agents = as_sam.get(f"{ADMIN}/agents").json()
    assert [a["id"] for a in agents] == [str(sam.pk)]


# --- saved replies ---


def test_saved_replies_can_be_made_changed_filtered_and_deleted(as_sam):
    made = as_sam.post(
        f"{ADMIN}/canned-replies",
        {
            "title": "Reset steps",
            "body": "<p>Use <b>Forgot password</b>.</p>",
            "category": "account",
        },
        format="json",
    )
    assert made.status_code == 201
    reply_id = made.json()["id"]
    as_sam.post(
        f"{ADMIN}/canned-replies",
        {"title": "Thanks", "body": "<p>Thanks for writing.</p>"},
        format="json",
    )
    assert {r["title"] for r in as_sam.get(f"{ADMIN}/canned-replies").json()} == {
        "Reset steps",
        "Thanks",
    }
    assert [
        r["title"] for r in as_sam.get(f"{ADMIN}/canned-replies", {"category": "learning"}).json()
    ] == ["Thanks"]
    changed = as_sam.put(
        f"{ADMIN}/canned-replies/{reply_id}",
        {"title": "Reset steps", "body": "<p>Updated.</p>", "active": False},
        format="json",
    ).json()
    assert changed["active"] is False
    assert [r["title"] for r in as_sam.get(f"{ADMIN}/canned-replies").json()] == ["Thanks"]
    assert len(as_sam.get(f"{ADMIN}/canned-replies", {"all": "true"}).json()) == 2
    assert as_sam.delete(f"{ADMIN}/canned-replies/{reply_id}").status_code == 204
    assert SupportCannedReply.objects.count() == 1


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"title": "x", "body": "ok"},
        {"title": "Fine", "body": "<p> </p>"},
        {"title": "Fine", "body": "ok", "category": "zzz"},
    ],
)
def test_bad_saved_replies_are_refused(as_sam, payload):
    assert as_sam.post(f"{ADMIN}/canned-replies", payload, format="json").status_code == 400
