import uuid
from datetime import timedelta

import pytest
from django.utils import timezone

from apps.accounts import services as accounts
from apps.audit.models import AuditLog
from apps.campaigns.models import Campaign

pytestmark = pytest.mark.django_db

ADMIN = "/api/v1/admin"
BLOCKS = [
    {"type": "heading", "text": "Hi {{first_name}}", "level": 1},
    {"type": "paragraph", "html": "<p>Big news.</p>"},
    {"type": "button", "label": "Read", "url": "https://wocommunity.example.com/news"},
]


@pytest.fixture
def admin(make_user):
    return make_user(roles=("community_admin",), email="admin@example.com")


@pytest.fixture
def as_admin(admin, client_for):
    return client_for(admin, mfa_age=5)


@pytest.fixture
def as_admin_stale(admin, client_for):
    return client_for(admin, mfa_age=3600)


@pytest.fixture
def member(make_user):
    user = make_user(
        email="member@example.com", approved_at=timezone.now(), email_verified_at=timezone.now()
    )
    accounts.set_marketing_consent(user.pk, True)
    return user


def segment(client, **definition):
    response = client.post(
        f"{ADMIN}/segments", {"name": "Everyone", "definition": definition}, format="json"
    )
    assert response.status_code == 201, response.content
    return response.json()


def campaign(client, segment_id=None, **overrides):
    body = {"name": "October", "subject": "News {{first_name}}", "blocks": BLOCKS}
    if segment_id:
        body["segment_id"] = segment_id
    body.update(overrides)
    response = client.post(f"{ADMIN}/campaigns", body, format="json")
    assert response.status_code == 201, response.content
    return response.json()


# --- segments ---


def test_a_segment_is_saved_validated_and_previewed(as_admin, member):
    saved = segment(as_admin, tags=["registered_incomplete"])
    assert saved["definition"] == {"tags": ["registered_incomplete"]}
    preview = as_admin.get(f"{ADMIN}/segments/{saved['id']}/preview").json()
    assert preview == {"matching": 1, "eligible": 1}
    adhoc = as_admin.post(
        f"{ADMIN}/segments/preview", {"definition": {"country": ["KE"]}}, format="json"
    )
    assert adhoc.json() == {"matching": 0, "eligible": 0}


def test_a_segment_can_be_changed_and_deleted(as_admin):
    saved = segment(as_admin)
    url = f"{ADMIN}/segments/{saved['id']}"
    changed = as_admin.patch(
        url, {"name": "Kenya", "definition": {"country": ["ke"]}}, format="json"
    )
    assert changed.json()["name"] == "Kenya" and changed.json()["definition"] == {"country": ["KE"]}
    assert as_admin.get(ADMIN + "/segments").json()["count"] == 1
    assert as_admin.delete(url).status_code == 204
    assert as_admin.get(url).status_code == 404 and as_admin.delete(url).status_code == 404


@pytest.mark.parametrize(
    "body",
    [
        {"name": "x"},
        {"name": "", "definition": {}},
        {"name": "x", "definition": {"bogus": 1}},
        {"name": "x", "definition": {"country": ["ZZ"]}},
        {"name": "x", "definition": {"tags": ["vip"]}},
        {"name": "x", "definition": {}, "extra": 1},
    ],
)
def test_bad_segments_are_refused(as_admin, body):
    assert as_admin.post(f"{ADMIN}/segments", body, format="json").status_code == 400


def test_deleting_a_segment_keeps_the_campaigns_that_used_it(as_admin):
    saved = segment(as_admin)
    made = campaign(as_admin, saved["id"])
    as_admin.delete(f"{ADMIN}/segments/{saved['id']}")
    assert as_admin.get(f"{ADMIN}/campaigns/{made['id']}").json()["segment_id"] is None


# --- templates ---


def test_templates_can_be_saved_listed_used_and_deleted(as_admin):
    template = as_admin.post(
        f"{ADMIN}/campaign-templates", {"name": "Monthly", "blocks": BLOCKS}, format="json"
    )
    assert template.status_code == 201
    tid = template.json()["id"]
    assert [t["name"] for t in as_admin.get(f"{ADMIN}/campaign-templates").json()] == ["Monthly"]
    made = as_admin.post(
        f"{ADMIN}/campaigns",
        {"name": "From template", "subject": "Hi", "template_id": tid},
        format="json",
    ).json()
    assert [b["type"] for b in made["blocks"]] == ["heading", "paragraph", "button"]
    assert as_admin.delete(f"{ADMIN}/campaign-templates/{tid}").status_code == 204
    assert as_admin.delete(f"{ADMIN}/campaign-templates/{tid}").status_code == 404


def test_a_campaign_takes_blocks_or_a_template_not_both(as_admin):
    response = as_admin.post(
        f"{ADMIN}/campaigns",
        {"name": "x", "subject": "s", "blocks": BLOCKS, "template_id": str(uuid.uuid4())},
        format="json",
    )
    assert response.status_code == 400


# --- writing campaigns ---


def test_a_campaign_is_a_draft_with_cleaned_content(as_admin):
    saved = segment(as_admin)
    made = campaign(
        as_admin,
        saved["id"],
        blocks=[{"type": "paragraph", "html": "<p onclick='x()'>hi</p><script>bad()</script>"}],
    )
    assert made["status"] == "draft" and made["segment_id"] == saved["id"]
    assert "<script" not in made["blocks"][0]["html"] and "onclick" not in made["blocks"][0]["html"]
    assert AuditLog.objects.filter(action="campaigns.created").exists()


@pytest.mark.parametrize(
    "overrides",
    [
        {"subject": ""},
        {"subject": "Hi {{password}}"},
        {"blocks": [{"type": "video"}]},
        {"blocks": [{"type": "button", "label": "x", "url": "http://insecure.example.com"}]},
        {"segment_id": str(uuid.uuid4())},
        {"status": "sent"},
    ],
)
def test_invalid_campaigns_are_refused(as_admin, overrides):
    body = {"name": "x", "subject": "s", "blocks": BLOCKS, **overrides}
    assert as_admin.post(f"{ADMIN}/campaigns", body, format="json").status_code == 400
    assert Campaign.objects.count() == 0


def test_editing_a_draft_needs_the_etag(as_admin):
    made = campaign(as_admin)
    url = f"{ADMIN}/campaigns/{made['id']}"
    etag = as_admin.get(url)["ETag"]
    edited = as_admin.patch(url, {"subject": "New subject"}, format="json", HTTP_IF_MATCH=etag)
    assert edited.status_code == 200 and edited.json()["subject"] == "New subject"
    assert as_admin.patch(url, {"subject": "x"}, format="json").status_code == 428
    assert (
        as_admin.patch(url, {"subject": "x"}, format="json", HTTP_IF_MATCH=etag).status_code == 412
    )


def test_the_campaign_list_filters_by_status(as_admin):
    campaign(as_admin)
    assert as_admin.get(f"{ADMIN}/campaigns").json()["count"] == 1
    assert as_admin.get(f"{ADMIN}/campaigns", {"status": "sent"}).json()["count"] == 0
    assert as_admin.get(f"{ADMIN}/campaigns", {"status": "bogus"}).status_code == 400


def test_a_draft_can_be_deleted(as_admin):
    made = campaign(as_admin)
    assert as_admin.delete(f"{ADMIN}/campaigns/{made['id']}").status_code == 204
    assert as_admin.get(f"{ADMIN}/campaigns/{made['id']}").status_code == 404


# --- the whole journey ---


def test_build_a_segment_send_a_test_schedule_and_see_delivery(as_admin, member, sent_emails):
    saved = segment(as_admin)
    made = campaign(as_admin, saved["id"])
    base = f"{ADMIN}/campaigns/{made['id']}"
    assert as_admin.post(f"{base}/test").status_code == 204
    assert sent_emails[-1].to == "admin@example.com" and sent_emails[-1].subject.startswith(
        "[Test]"
    )
    soon = (timezone.now() + timedelta(hours=2)).isoformat()
    scheduled = as_admin.post(f"{base}/schedule", {"scheduled_at": soon}, format="json")
    assert scheduled.status_code == 200 and scheduled.json()["status"] == "scheduled"
    Campaign.objects.filter(pk=made["id"]).update(
        scheduled_at=timezone.now() - timedelta(minutes=1)
    )
    from apps.campaigns.tasks import start_due

    start_due()
    report = as_admin.get(f"{base}/report").json()
    assert report["recipients"] == 1 and report["sent"] == 1 and report["opened"] == 0
    recipient = Campaign.objects.get(pk=made["id"]).recipients.get()
    from apps.campaigns.services import record_delivery

    record_delivery("delivered", recipient.provider_message_id)
    record_delivery("opened", recipient.provider_message_id)
    assert as_admin.get(f"{base}/report").json()["opened"] == 1
    assert [m.to for m in sent_emails if m.stream == "marketing"] == ["member@example.com"]


def test_actions_enforce_state_and_the_kill_switch_works_over_the_api(as_admin, member):
    made = campaign(as_admin, segment(as_admin)["id"])
    base = f"{ADMIN}/campaigns/{made['id']}"
    assert as_admin.post(f"{base}/pause").status_code == 409
    assert as_admin.post(f"{base}/send").json()["status"] == "sending"
    assert as_admin.post(f"{base}/send").status_code == 409
    assert as_admin.post(f"{base}/pause").json()["status"] == "paused"
    assert as_admin.post(f"{base}/resume").json()["status"] == "sending"
    assert as_admin.post(f"{base}/cancel").json()["status"] == "cancelled"
    assert (
        AuditLog.objects.filter(
            action__in=[
                "campaigns.sent",
                "campaigns.paused",
                "campaigns.resumed",
                "campaigns.cancelled",
            ]
        ).count()
        == 4
    )


def test_scheduling_needs_a_future_time_content_and_an_audience(as_admin):
    made = campaign(as_admin)  # no segment
    base = f"{ADMIN}/campaigns/{made['id']}"
    soon = (timezone.now() + timedelta(hours=1)).isoformat()
    assert (
        as_admin.post(f"{base}/schedule", {"scheduled_at": soon}, format="json").status_code == 400
    )
    assert (
        as_admin.post(
            f"{base}/schedule", {"scheduled_at": "2000-01-01T00:00:00Z"}, format="json"
        ).status_code
        == 400
    )
    assert as_admin.post(f"{base}/schedule", {}, format="json").status_code == 400
    assert as_admin.post(f"{base}/send").status_code == 400


# --- access control ---


def test_sending_scheduling_and_resuming_need_a_fresh_mfa_check(as_admin, as_admin_stale):
    made = campaign(as_admin, segment(as_admin)["id"])
    base = f"{ADMIN}/campaigns/{made['id']}"
    for action, body in (
        ("send", {}),
        ("schedule", {"scheduled_at": (timezone.now() + timedelta(hours=1)).isoformat()}),
        ("resume", {}),
    ):
        response = as_admin_stale.post(f"{base}/{action}", body, format="json")
        assert response.status_code == 403 and response.json()["code"] == "step_up_required"
    assert Campaign.objects.get(pk=made["id"]).status == "draft"
    # stopping a send must never be slower than starting one
    as_admin.post(f"{base}/send")
    assert as_admin_stale.post(f"{base}/pause").status_code == 200
    assert as_admin_stale.post(f"{base}/cancel").status_code == 200


ENDPOINTS = [
    ("get", f"{ADMIN}/segments"),
    ("post", f"{ADMIN}/segments"),
    ("post", f"{ADMIN}/segments/preview"),
    ("get", f"{ADMIN}/segments/{uuid.uuid4()}"),
    ("get", f"{ADMIN}/segments/{uuid.uuid4()}/preview"),
    ("get", f"{ADMIN}/campaign-templates"),
    ("post", f"{ADMIN}/campaign-templates"),
    ("get", f"{ADMIN}/campaigns"),
    ("post", f"{ADMIN}/campaigns"),
    ("get", f"{ADMIN}/campaigns/{uuid.uuid4()}"),
    ("patch", f"{ADMIN}/campaigns/{uuid.uuid4()}"),
    ("delete", f"{ADMIN}/campaigns/{uuid.uuid4()}"),
    ("get", f"{ADMIN}/campaigns/{uuid.uuid4()}/report"),
    ("post", f"{ADMIN}/campaigns/{uuid.uuid4()}/send"),
    ("post", f"{ADMIN}/campaigns/{uuid.uuid4()}/schedule"),
    ("post", f"{ADMIN}/campaigns/{uuid.uuid4()}/pause"),
    ("post", f"{ADMIN}/campaigns/{uuid.uuid4()}/test"),
]


@pytest.mark.parametrize("method, url", ENDPOINTS)
def test_visitors_and_members_cannot_use_the_newsletter_tools(
    api_client, member, client_for, method, url
):
    assert getattr(api_client, method)(url).status_code == 401
    assert getattr(client_for(member), method)(url).status_code == 403


@pytest.mark.parametrize("method, url", ENDPOINTS)
def test_content_editors_cannot_send_newsletters(make_user, client_for, method, url):
    editor = client_for(make_user(roles=("content_editor",), email="e@example.com"), mfa_age=5)
    assert getattr(editor, method)(url).status_code == 403


@pytest.mark.parametrize("method, url", ENDPOINTS)
def test_admins_without_an_mfa_check_are_refused(admin, client_for, method, url):
    assert getattr(client_for(admin), method)(url).status_code == 403
