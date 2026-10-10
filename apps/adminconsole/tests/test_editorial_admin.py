import uuid
from datetime import timedelta

import pytest
from django.utils import timezone

from apps.audit.models import AuditLog
from apps.editorial import services
from apps.editorial.models import EditorialItem, ItemComment, WinSubmission

pytestmark = pytest.mark.django_db

ADMIN = "/api/v1/admin/editorial"
WINS = "/api/v1/admin/win-submissions"
ITEMS = "/api/v1/editorial"


def body(**overrides):
    base = {
        "type": "award",
        "title": "Founder of the year",
        "body": "<p>Congratulations to our winner.</p>",
    }
    base.update(overrides)
    return base


@pytest.fixture
def editor(make_user):
    return make_user(roles=("content_editor",), email="editor@example.com")


@pytest.fixture
def as_editor(editor, client_for):
    return client_for(editor, mfa_age=5)


@pytest.fixture
def member(make_user):
    return make_user(
        email="member@example.com", approved_at=timezone.now(), email_verified_at=timezone.now()
    )


@pytest.fixture
def member_client(member, client_for):
    return client_for(member)


def create(client, **overrides):
    response = client.post(ADMIN, body(**overrides), format="json")
    assert response.status_code == 201, response.content
    return response.json()


def when(minutes):
    return (timezone.now() + timedelta(minutes=minutes)).isoformat()


# --- writing ---


def test_an_editor_writes_a_draft_that_members_cannot_see(as_editor, member_client, editor):
    item = create(as_editor)
    assert item["status"] == "draft" and item["created_by"] == str(editor.pk)
    assert member_client.get(f"{ITEMS}/{item['id']}").status_code == 404
    assert as_editor.get(f"{ADMIN}/{item['id']}").json()["title"] == "Founder of the year"
    assert AuditLog.objects.filter(action="editorial.created").exists()


def test_rich_text_is_cleaned_and_external_links_must_be_https(as_editor):
    cleaned = create(as_editor, body="<h2>Hi</h2><script>x()</script><p onclick='y()'>t</p>")[
        "body"
    ]
    assert "<script" not in cleaned and "onclick" not in cleaned
    assert (
        as_editor.post(
            ADMIN, body(external_url="http://insecure.example.com"), format="json"
        ).status_code
        == 400
    )
    assert (
        create(as_editor, external_url="https://example.com/story")["external_url"]
        == "https://example.com/story"
    )


@pytest.mark.parametrize(
    "overrides",
    [
        {"type": "gossip"},
        {"title": ""},
        {"title": "x" * 161},
        {"body": ""},
        {"body": "<p></p>"},
        {"external_url": "javascript:alert(1)"},
        {"startup_ids": [str(uuid.uuid4())]},
        {"startup_ids": [str(uuid.uuid4())] * 11},
        {"banner_ends_at": when(60)},  # banners are for announcements only
        {"status": "published"},
        {"slug": "mine"},
    ],
)
def test_invalid_items_are_refused(as_editor, overrides):
    assert as_editor.post(ADMIN, body(**overrides), format="json").status_code == 400
    assert EditorialItem.objects.count() == 0


def test_items_can_link_startups(as_editor, make_user, client_for):
    from apps.startups.tests.conftest import STARTUPS, new_startup_body

    owner = client_for(make_user(email="o@example.com", approved_at=timezone.now()))
    startup = owner.post(STARTUPS, new_startup_body(name="Kola Pay")).json()["id"]
    item = create(as_editor, startup_ids=[startup])
    assert [s["name"] for s in item["startups"]] == ["Kola Pay"]


# --- banners ---


def test_announcements_can_have_a_banner_window_of_up_to_ninety_days(as_editor):
    ok = create(
        as_editor, type="announcement", banner_starts_at=when(0), banner_ends_at=when(60 * 24 * 30)
    )
    assert ok["banner_ends_at"]
    for bad in (
        {"banner_ends_at": when(-60)},
        {"banner_starts_at": when(120), "banner_ends_at": when(60)},
        {"banner_starts_at": when(0), "banner_ends_at": when(60 * 24 * 91)},
        {"banner_starts_at": when(0)},
    ):
        assert (
            as_editor.post(ADMIN, body(type="announcement", **bad), format="json").status_code
            == 400
        )


# --- editing ---


def test_editing_needs_the_current_etag(as_editor):
    item = create(as_editor)
    url = f"{ADMIN}/{item['id']}"
    etag = as_editor.get(url)["ETag"]
    changed = as_editor.patch(url, {"title": "Renamed"}, format="json", HTTP_IF_MATCH=etag)
    assert changed.status_code == 200 and changed.json()["title"] == "Renamed"
    assert changed.json()["edited_at"] is not None
    assert as_editor.patch(url, {"title": "x"}, format="json").status_code == 428
    assert (
        as_editor.patch(url, {"title": "x"}, format="json", HTTP_IF_MATCH=etag).status_code == 412
    )


def test_reactions_and_comments_do_not_change_the_etag(as_editor, member_client):
    item = create(as_editor)
    as_editor.post(f"{ADMIN}/{item['id']}/publish")
    etag = as_editor.get(f"{ADMIN}/{item['id']}")["ETag"]
    member_client.post(f"{ITEMS}/{item['id']}/reactions", {"kind": "like"}, format="json")
    member_client.post(f"{ITEMS}/{item['id']}/comments", {"body": "<p>hi</p>"}, format="json")
    ok = as_editor.patch(
        f"{ADMIN}/{item['id']}", {"title": "Still editable"}, format="json", HTTP_IF_MATCH=etag
    )
    assert ok.status_code == 200


def test_the_listing_filters_by_status_type_and_text(as_editor):
    create(as_editor, title="Alpha award", type="award")
    published = create(as_editor, title="Beta news", type="news")
    as_editor.post(f"{ADMIN}/{published['id']}/publish")
    assert as_editor.get(ADMIN, {"status": "published"}).json()["count"] == 1
    assert as_editor.get(ADMIN, {"type": "award"}).json()["count"] == 1
    assert as_editor.get(ADMIN, {"q": "beta"}).json()["count"] == 1
    assert as_editor.get(ADMIN).json()["count"] == 2


@pytest.mark.parametrize("params", [{"status": "removed"}, {"type": "x"}, {"limit": 0}, {"z": 1}])
def test_bad_admin_queries_are_refused(as_editor, params):
    assert as_editor.get(ADMIN, params).status_code == 400


# --- publishing, scheduling, taking down ---


def test_publishing_makes_an_item_visible_and_unpublishing_hides_it_again(as_editor, member_client):
    item = create(as_editor)
    live = as_editor.post(f"{ADMIN}/{item['id']}/publish")
    assert live.status_code == 200 and live.json()["status"] == "published"
    assert member_client.get(f"{ITEMS}/{item['id']}").status_code == 200
    assert as_editor.post(f"{ADMIN}/{item['id']}/publish").status_code == 409
    down = as_editor.post(f"{ADMIN}/{item['id']}/unpublish")
    assert down.json()["status"] == "draft"
    assert member_client.get(f"{ITEMS}/{item['id']}").status_code == 404
    assert as_editor.post(f"{ADMIN}/{item['id']}/unpublish").status_code == 409


def test_a_scheduled_item_goes_live_by_itself_stamped_with_its_time(as_editor, member_client):
    item = create(as_editor)
    due = timezone.now() + timedelta(minutes=10)
    scheduled = as_editor.post(
        f"{ADMIN}/{item['id']}/schedule", {"publish_at": due.isoformat()}, format="json"
    )
    assert scheduled.status_code == 200 and scheduled.json()["status"] == "scheduled"
    assert services.publish_due() == 0
    assert member_client.get(f"{ITEMS}/{item['id']}").status_code == 404
    EditorialItem.objects.filter(pk=item["id"]).update(publish_at=due - timedelta(minutes=20))
    assert services.publish_due() == 1
    row = EditorialItem.objects.get(pk=item["id"])
    assert row.status == "published" and row.publish_at is None
    assert row.published_at == due - timedelta(minutes=20)
    assert member_client.get(f"{ITEMS}/{item['id']}").status_code == 200
    assert services.publish_due() == 0


def test_a_schedule_can_be_cancelled_or_replaced(as_editor):
    item = create(as_editor)
    as_editor.post(f"{ADMIN}/{item['id']}/schedule", {"publish_at": when(60)}, format="json")
    assert as_editor.post(f"{ADMIN}/{item['id']}/unpublish").json()["status"] == "draft"
    again = as_editor.post(
        f"{ADMIN}/{item['id']}/schedule", {"publish_at": when(120)}, format="json"
    )
    assert again.json()["status"] == "scheduled"


@pytest.mark.parametrize(
    "payload", [{}, {"publish_at": "soon"}, {"publish_at": "2000-01-01T00:00:00Z"}]
)
def test_invalid_schedules_are_refused(as_editor, payload):
    item = create(as_editor)
    assert (
        as_editor.post(f"{ADMIN}/{item['id']}/schedule", payload, format="json").status_code == 400
    )
    assert EditorialItem.objects.get(pk=item["id"]).status == "draft"


def test_a_published_item_cannot_be_scheduled(as_editor):
    item = create(as_editor)
    as_editor.post(f"{ADMIN}/{item['id']}/publish")
    assert (
        as_editor.post(
            f"{ADMIN}/{item['id']}/schedule", {"publish_at": when(60)}, format="json"
        ).status_code
        == 409
    )


def test_a_removed_item_disappears_everywhere(as_editor, member_client):
    item = create(as_editor)
    as_editor.post(f"{ADMIN}/{item['id']}/publish")
    assert as_editor.delete(f"{ADMIN}/{item['id']}").status_code == 204
    assert member_client.get(f"{ITEMS}/{item['id']}").status_code == 404
    assert as_editor.get(f"{ADMIN}/{item['id']}").status_code == 404
    assert as_editor.delete(f"{ADMIN}/{item['id']}").status_code == 404
    assert AuditLog.objects.filter(action="editorial.removed").count() == 1


def test_publishing_is_audited_and_unknown_items_are_404(as_editor):
    item = create(as_editor)
    as_editor.post(f"{ADMIN}/{item['id']}/publish")
    assert AuditLog.objects.filter(action="editorial.published").count() == 1
    assert as_editor.post(f"{ADMIN}/{uuid.uuid4()}/publish").status_code == 404


# --- covers ---


def test_a_cover_image_can_be_set_and_cleared(as_editor, editor, ready_upload, member_client):
    item = create(as_editor)
    as_editor.post(f"{ADMIN}/{item['id']}/publish")
    upload = ready_upload(editor, "editorial_cover")
    with_cover = as_editor.put(
        f"{ADMIN}/{item['id']}/cover", {"upload_id": str(upload.pk)}, format="json"
    )
    assert with_cover.status_code == 200 and with_cover.json()["cover"]["large"].endswith(
        "/large.webp"
    )
    assert member_client.get(f"{ITEMS}/{item['id']}").json()["cover"] is not None
    assert as_editor.delete(f"{ADMIN}/{item['id']}/cover").json()["cover"] is None


def test_a_cover_must_be_the_right_kind_of_upload_and_used_once(as_editor, editor, ready_upload):
    item = create(as_editor)
    wrong = ready_upload(editor, "profile_photo")
    assert (
        as_editor.put(
            f"{ADMIN}/{item['id']}/cover", {"upload_id": str(wrong.pk)}, format="json"
        ).status_code
        == 400
    )
    right = ready_upload(editor, "editorial_cover")
    assert (
        as_editor.put(
            f"{ADMIN}/{item['id']}/cover", {"upload_id": str(right.pk)}, format="json"
        ).status_code
        == 200
    )
    other = create(as_editor, title="Other")
    assert (
        as_editor.put(
            f"{ADMIN}/{other['id']}/cover", {"upload_id": str(right.pk)}, format="json"
        ).status_code
        == 400
    )


# --- moderating comments ---


def test_comments_can_be_hidden_unhidden_and_removed(as_editor, member_client):
    item = create(as_editor)
    as_editor.post(f"{ADMIN}/{item['id']}/publish")
    cid = member_client.post(
        f"{ITEMS}/{item['id']}/comments", {"body": "<p>rude</p>"}, format="json"
    ).json()["id"]
    base = f"/api/v1/admin/editorial-comments/{cid}"
    assert as_editor.post(f"{base}/hide", {"reason": "rude"}, format="json").status_code == 200
    assert member_client.get(f"{ITEMS}/{item['id']}/comments").json()["results"] == []
    assert member_client.get(f"{ITEMS}/{item['id']}").json()["comment_count"] == 0
    assert (
        member_client.patch(
            f"/api/v1/editorial-comments/{cid}", {"body": "<p>x</p>"}, format="json"
        ).status_code
        == 409  # the author is told a moderator hid it
    )
    as_editor.post(f"{base}/unhide")
    assert member_client.get(f"{ITEMS}/{item['id']}").json()["comment_count"] == 1
    assert as_editor.post(f"{base}/remove").status_code == 200
    assert ItemComment.objects.get(pk=cid).deleted_at is not None
    assert as_editor.post(f"{base}/hide").status_code == 404
    assert AuditLog.objects.filter(action="editorial.comment_hide", reason="rude").exists()


# --- win submissions ---


@pytest.fixture
def submitted(member_client):
    response = member_client.post(
        "/api/v1/win-submissions",
        {
            "kind": "funding",
            "title": "Seed round closed",
            "evidence_url": "https://news.example.com/seed",
            "details": "Closed a 500k seed.",
        },
        format="json",
    )
    return response.json()["id"]


def test_pending_wins_are_queued_and_counted(as_editor, submitted, make_user, client_for):
    queue = as_editor.get(WINS).json()
    assert queue["count"] == 1 and queue["results"][0]["id"] == submitted
    assert queue["results"][0]["submitter_id"]
    admin = client_for(make_user(roles=("community_admin",), email="ca@example.com"), mfa_age=5)
    assert admin.get("/api/v1/admin/queues").json()["wins_awaiting_review"] == 1
    assert as_editor.get(WINS, {"status": "approved"}).json()["count"] == 0


def test_approving_creates_a_draft_story_for_an_editor(
    as_editor, member_client, submitted, run_outbox
):
    done = as_editor.post(f"{WINS}/{submitted}/approve", {"reason": "great news"}, format="json")
    assert done.status_code == 200 and done.json()["status"] == "approved"
    item = EditorialItem.objects.get(pk=done.json()["item_id"])
    assert item.status == "draft" and item.type == "funding" and item.title == "Seed round closed"
    assert item.external_url == "https://news.example.com/seed" and "500k seed" in item.body
    assert (
        member_client.get(f"{ITEMS}/{item.pk}").status_code == 404
    )  # nothing is public until an editor publishes
    run_outbox()
    assert member_client.get("/api/v1/notifications").json()["results"][0]["type"] == "win_approved"
    assert AuditLog.objects.filter(action="editorial.win_approve").exists()


def test_rejecting_needs_a_reason_and_tells_the_member_why(
    as_editor, member_client, submitted, run_outbox
):
    assert as_editor.post(f"{WINS}/{submitted}/reject", {}, format="json").status_code == 400
    done = as_editor.post(
        f"{WINS}/{submitted}/reject", {"reason": "Cannot verify the source"}, format="json"
    )
    assert done.json()["status"] == "rejected" and done.json()["item_id"] is None
    run_outbox()
    [notice] = member_client.get("/api/v1/notifications").json()["results"]
    assert notice["type"] == "win_rejected" and "Cannot verify the source" in notice["title"]
    mine = member_client.get("/api/v1/win-submissions").json()["results"][0]
    assert mine["review_note"] == "Cannot verify the source"


def test_a_submission_can_only_be_reviewed_once(as_editor, submitted):
    as_editor.post(f"{WINS}/{submitted}/approve", {}, format="json")
    assert as_editor.post(f"{WINS}/{submitted}/approve", {}, format="json").status_code == 409
    assert (
        as_editor.post(f"{WINS}/{submitted}/reject", {"reason": "late"}, format="json").status_code
        == 409
    )
    assert WinSubmission.objects.get(pk=submitted).status == "approved"


def test_unknown_submissions_are_404(as_editor):
    assert as_editor.post(f"{WINS}/{uuid.uuid4()}/approve", {}, format="json").status_code == 404


# --- access control ---


ENDPOINTS = [
    ("get", ADMIN),
    ("post", ADMIN),
    ("get", f"{ADMIN}/{uuid.uuid4()}"),
    ("patch", f"{ADMIN}/{uuid.uuid4()}"),
    ("delete", f"{ADMIN}/{uuid.uuid4()}"),
    ("post", f"{ADMIN}/{uuid.uuid4()}/publish"),
    ("post", f"{ADMIN}/{uuid.uuid4()}/unpublish"),
    ("post", f"{ADMIN}/{uuid.uuid4()}/schedule"),
    ("put", f"{ADMIN}/{uuid.uuid4()}/cover"),
    ("delete", f"{ADMIN}/{uuid.uuid4()}/cover"),
    ("post", f"/api/v1/admin/editorial-comments/{uuid.uuid4()}/hide"),
    ("get", WINS),
    ("post", f"{WINS}/{uuid.uuid4()}/approve"),
    ("post", f"{WINS}/{uuid.uuid4()}/reject"),
]


@pytest.mark.parametrize("method, url", ENDPOINTS)
def test_visitors_and_members_cannot_use_the_editorial_tools(
    api_client, member_client, method, url
):
    assert getattr(api_client, method)(url).status_code == 401
    assert getattr(member_client, method)(url).status_code == 403


@pytest.mark.parametrize("method, url", ENDPOINTS)
def test_editors_without_a_recent_mfa_check_are_refused(editor, client_for, method, url):
    assert getattr(client_for(editor), method)(url).status_code == 403
