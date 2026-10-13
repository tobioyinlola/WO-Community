from datetime import timedelta

import pytest
from django.utils import timezone

from apps.notifications.models import Notification
from apps.support.models import SupportTicket
from apps.support.tests.helpers import (
    MESSAGE,
    TICKETS,
    active,
    body,
    ready_attachment,
)

pytestmark = pytest.mark.django_db


@pytest.fixture
def ada(make_user):
    return active(make_user, "ada@example.com", "Adaeze Okafor")


@pytest.fixture
def tunde(make_user):
    return active(make_user, "tunde@example.com", "Tunde Bakare")


@pytest.fixture
def admin(make_user):
    return active(make_user, "admin@example.com", "Support Sam", roles=("community_admin",))


@pytest.fixture
def as_ada(ada, client_for):
    return client_for(ada)


@pytest.fixture
def as_tunde(tunde, client_for):
    return client_for(tunde)


def open_one(client, **overrides):
    response = client.post(TICKETS, body(**overrides), format="json")
    assert response.status_code == 201, response.content
    return response.json()


def url(ticket, tail=""):
    return f"{TICKETS}/{ticket['id']}" + (f"/{tail}" if tail else "")


# --- opening a request ---


def test_a_member_opens_a_request_and_sees_it_with_its_first_message(as_ada, ada):
    ticket = open_one(as_ada)
    assert ticket["reference"].startswith("SUP-") and ticket["number"] >= 1001
    assert ticket["status"] == "open" and ticket["status_label"] == "Open"
    assert ticket["category_label"] == "Profile and directory"
    assert [m["body"] for m in ticket["messages"]] == [f"<p>{MESSAGE}</p>"]
    assert ticket["messages"][0]["author"]["name"] == "Adaeze Okafor"
    stored = SupportTicket.objects.get(pk=ticket["id"])
    assert stored.member_id == ada.pk and stored.email == "ada@example.com"


def test_numbers_are_unique_and_rise(as_ada):
    first, second = open_one(as_ada), open_one(as_ada, subject="Another thing entirely")
    assert second["number"] == first["number"] + 1


def test_admins_are_told_in_the_app_about_a_new_request(as_ada, admin):
    ticket = open_one(as_ada)
    note = Notification.objects.get(user=admin, type="ticket_new")
    assert note.payload["ticket_id"] == ticket["id"]
    assert note.payload["reference"] == ticket["reference"]


def test_message_text_is_kept_as_text_not_markup(as_ada):
    ticket = open_one(
        as_ada, message="Please look at <script>alert(1)</script> this broken page.\n\nThanks"
    )
    html = ticket["messages"][0]["body"]
    assert "<script" not in html and html.count("<p>") == 2


@pytest.mark.parametrize(
    "overrides",
    [
        {"subject": "Four"},
        {"subject": "x" * 121},
        {"message": "Too short"},
        {"message": "x" * 4001},
        {"category": "billing"},
        {"category": ""},
        {"extra": "field"},
        {"attachments": ["00000000-0000-0000-0000-000000000000"] * 4},
    ],
)
def test_a_bad_request_is_refused_and_nothing_is_created(as_ada, overrides):
    response = as_ada.post(TICKETS, body(**overrides), format="json")
    assert response.status_code == 400
    assert SupportTicket.objects.count() == 0


def test_the_same_form_sent_twice_opens_one_request(as_ada):
    first = as_ada.post(TICKETS, body(), format="json", HTTP_IDEMPOTENCY_KEY="abc-123")
    second = as_ada.post(TICKETS, body(), format="json", HTTP_IDEMPOTENCY_KEY="abc-123")
    assert first.json()["id"] == second.json()["id"]
    assert SupportTicket.objects.count() == 1


def test_files_can_be_attached_once_each(as_ada, ada):
    upload = ready_attachment(ada)
    ticket = open_one(as_ada, attachments=[str(upload.pk)])
    files = ticket["messages"][0]["attachments"]
    assert [(f["filename"], f["content_type"]) for f in files] == [
        ("screenshot.pdf", "application/pdf")
    ]
    reuse = as_ada.post(TICKETS, body(attachments=[str(upload.pk)]), format="json")
    assert reuse.status_code == 400


def test_someone_elses_upload_cannot_be_attached(as_ada, tunde):
    theirs = ready_attachment(tunde)
    assert (
        as_ada.post(TICKETS, body(attachments=[str(theirs.pk)]), format="json").status_code == 400
    )


# --- reading ---


def test_a_member_sees_only_their_own_requests(as_ada, as_tunde):
    mine = open_one(as_ada)
    open_one(as_tunde, subject="Tunde's own problem")
    listing = as_ada.get(TICKETS).json()
    assert listing["count"] == 1 and [t["id"] for t in listing["results"]] == [mine["id"]]
    assert as_tunde.get(url(mine)).status_code == 404


def test_the_list_filters_by_status_newest_activity_first(as_ada):
    first = open_one(as_ada, subject="The first thing I asked")
    second = open_one(as_ada, subject="The second thing I asked")
    SupportTicket.objects.filter(pk=first["id"]).update(
        status="resolved", resolved_at=timezone.now()
    )
    assert [t["id"] for t in as_ada.get(TICKETS, {"status": "open"}).json()["results"]] == [
        second["id"]
    ]
    assert [t["id"] for t in as_ada.get(TICKETS, {"status": "resolved"}).json()["results"]] == [
        first["id"]
    ]
    assert as_ada.get(TICKETS, {"status": "bogus"}).status_code == 400


# --- the conversation ---


def reply(client, ticket, text="Here is a screenshot of what I see.", **extra):
    return client.post(url(ticket, "messages"), {"message": text, **extra}, format="json")


def test_a_reply_is_added_to_the_thread(as_ada):
    ticket = open_one(as_ada)
    assert reply(as_ada, ticket).status_code == 201
    thread = as_ada.get(url(ticket)).json()["messages"]
    assert len(thread) == 2 and thread[1]["body"] == "<p>Here is a screenshot of what I see.</p>"


def test_replying_after_support_answered_puts_it_back_in_progress(as_ada, admin, client_for):
    ticket = open_one(as_ada)
    support = client_for(admin, mfa_age=5)
    support.post(
        f"/api/v1/admin/support/tickets/{ticket['id']}/messages",
        {"body": "<p>Which page are you on?</p>"},
        format="json",
    )
    assert as_ada.get(url(ticket)).json()["status"] == "awaiting_member"
    reply(as_ada, ticket)
    assert as_ada.get(url(ticket)).json()["status"] == "in_progress"


def test_the_assignee_hears_about_a_reply(as_ada, admin, client_for):
    ticket = open_one(as_ada)
    client_for(admin, mfa_age=5).patch(
        f"/api/v1/admin/support/tickets/{ticket['id']}", {"assignee": str(admin.pk)}, format="json"
    )
    reply(as_ada, ticket)
    assert Notification.objects.filter(user=admin, type="ticket_member_reply").count() == 1


def test_a_resolved_request_needs_reopening_before_a_reply(as_ada):
    ticket = open_one(as_ada)
    SupportTicket.objects.filter(pk=ticket["id"]).update(
        status="resolved", resolved_at=timezone.now()
    )
    assert reply(as_ada, ticket).status_code == 409


def test_nobody_else_can_reply_on_my_request(as_ada, as_tunde):
    ticket = open_one(as_ada)
    assert reply(as_tunde, ticket).status_code == 404


@pytest.mark.parametrize("text", ["", "   ", "<b></b>", "x" * 4001])
def test_an_empty_or_huge_reply_is_refused(as_ada, text):
    ticket = open_one(as_ada)
    assert reply(as_ada, ticket, text).status_code == 400


def test_internal_notes_never_reach_the_member(as_ada, admin, client_for):
    ticket = open_one(as_ada)
    support = client_for(admin, mfa_age=5)
    support.post(
        f"/api/v1/admin/support/tickets/{ticket['id']}/messages",
        {"body": "<p>Looks like a duplicate account.</p>", "internal": True},
        format="json",
    )
    thread = as_ada.get(url(ticket)).json()["messages"]
    assert len(thread) == 1 and "duplicate" not in str(thread)


# --- reopening and feedback ---


def resolve(ticket, days_ago=0, **fields):
    SupportTicket.objects.filter(pk=ticket["id"]).update(
        status="resolved", resolved_at=timezone.now() - timedelta(days=days_ago), **fields
    )


def test_a_member_can_reopen_within_fourteen_days(as_ada):
    ticket = open_one(as_ada)
    resolve(ticket, days_ago=13)
    assert as_ada.get(url(ticket)).json()["can_reopen"] is True
    reopened = as_ada.post(url(ticket, "reopen")).json()
    assert reopened["status"] == "open" and reopened["resolved_at"] is None
    assert SupportTicket.objects.get(pk=ticket["id"]).reopened_count == 1


def test_it_cannot_be_reopened_after_fourteen_days_or_when_not_resolved(as_ada):
    ticket = open_one(as_ada)
    assert as_ada.post(url(ticket, "reopen")).status_code == 409
    resolve(ticket, days_ago=15)
    assert as_ada.get(url(ticket)).json()["can_reopen"] is False
    assert as_ada.post(url(ticket, "reopen")).status_code == 409


def test_only_the_owner_can_reopen(as_ada, as_tunde):
    ticket = open_one(as_ada)
    resolve(ticket)
    assert as_tunde.post(url(ticket, "reopen")).status_code == 404


def test_feedback_is_for_resolved_requests_and_can_be_changed(as_ada):
    ticket = open_one(as_ada)
    assert (
        as_ada.post(url(ticket, "feedback"), {"satisfaction": "up"}, format="json").status_code
        == 409
    )
    resolve(ticket)
    first = as_ada.post(url(ticket, "feedback"), {"satisfaction": "up"}, format="json")
    assert first.status_code == 200 and first.json()["satisfaction"] == "up"
    again = as_ada.post(
        url(ticket, "feedback"), {"satisfaction": "down", "comment": "Still broken"}, format="json"
    )
    assert (
        again.json()["satisfaction"] == "down"
        and again.json()["satisfaction_comment"] == "Still broken"
    )


@pytest.mark.parametrize(
    "payload", [{}, {"satisfaction": "meh"}, {"satisfaction": "up", "comment": "x" * 501}]
)
def test_bad_feedback_is_refused(as_ada, payload):
    ticket = open_one(as_ada)
    resolve(ticket)
    assert as_ada.post(url(ticket, "feedback"), payload, format="json").status_code == 400


# --- files ---


def test_an_attachment_downloads_through_a_short_lived_link_for_its_owner_only(
    as_ada, as_tunde, ada, monkeypatch
):
    monkeypatch.setattr(
        "apps.support.services.uploads.document_link", lambda **kw: ("https://files.test/x", 300)
    )
    ticket = open_one(as_ada, attachments=[str(ready_attachment(ada).pk)])
    file_id = ticket["messages"][0]["attachments"][0]["id"]
    link = as_ada.get(f"/api/v1/support/attachments/{file_id}/download")
    assert link.status_code == 200 and link.json() == {
        "url": "https://files.test/x",
        "expires_in": 300,
    }
    assert as_tunde.get(f"/api/v1/support/attachments/{file_id}/download").status_code == 404


# --- who may call what ---


@pytest.mark.parametrize(
    "method,path",
    [
        ("get", TICKETS),
        ("post", TICKETS),
        ("get", f"{TICKETS}/00000000-0000-0000-0000-000000000001"),
        ("post", f"{TICKETS}/00000000-0000-0000-0000-000000000001/messages"),
        ("post", f"{TICKETS}/00000000-0000-0000-0000-000000000001/reopen"),
        ("post", f"{TICKETS}/00000000-0000-0000-0000-000000000001/feedback"),
        ("get", "/api/v1/support/attachments/00000000-0000-0000-0000-000000000001/download"),
    ],
)
def test_signing_in_is_required(api_client, method, path):
    assert getattr(api_client, method)(path).status_code == 401


def test_an_unknown_request_is_not_found(as_ada):
    assert as_ada.get(f"{TICKETS}/00000000-0000-0000-0000-000000000001").status_code == 404


def test_a_member_waiting_for_approval_can_still_ask_for_help(make_user, client_for):
    waiting = make_user(roles=(), status="pending", email="w@example.com")
    ticket = client_for(waiting).post(TICKETS, body(category="approval"), format="json")
    assert ticket.status_code == 201
