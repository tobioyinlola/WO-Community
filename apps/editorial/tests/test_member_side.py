import uuid
from datetime import timedelta

import pytest
from django.utils import timezone

from apps.analytics.models import AnalyticsEvent
from apps.editorial import services
from apps.editorial.models import EditorialItem, WinSubmission
from apps.editorial.tests.conftest import ITEMS, story
from apps.notifications.models import Notification

pytestmark = pytest.mark.django_db

WINS = "/api/v1/win-submissions"
BANNERS = "/api/v1/banners"


def item_url(item):
    return f"{ITEMS}/{item.pk}"


# --- reading ---


def test_members_see_published_items_newest_first(editor, member_client):
    first = story(editor, title="First")
    second = story(editor, title="Second")
    page = member_client.get(ITEMS).json()
    assert [i["id"] for i in page["results"]] == [str(second.pk), str(first.pk)]
    item = page["results"][0]
    assert item["excerpt"] == "A big day for the community."
    assert item["body"] == "<p>A <strong>big</strong> day for the community.</p>"
    assert (
        item["comments_enabled"] is True and item["reactions"] == {} and item["my_reactions"] == []
    )


def test_drafts_scheduled_and_removed_items_are_invisible(editor, member_client):
    draft = story(editor, _draft=True, title="Draft")
    scheduled = story(editor, _draft=True, title="Later")
    services.schedule(
        actor=editor, item_id=scheduled.pk, publish_at=timezone.now() + timedelta(hours=1)
    )
    gone = story(editor, title="Gone")
    services.remove_item(actor=editor, item_id=gone.pk)
    assert member_client.get(ITEMS).json()["results"] == []
    for item in (draft, scheduled, gone):
        assert member_client.get(item_url(item)).status_code == 404


def test_items_can_be_filtered_by_type_and_paged(editor, member_client):
    for i in range(3):
        story(editor, title=f"News {i}", type="news")
    story(editor, title="An award", type="award")
    assert [i["title"] for i in member_client.get(ITEMS, {"type": "award"}).json()["results"]] == [
        "An award"
    ]
    seen, cursor = [], ""
    while True:
        page = member_client.get(ITEMS, {"limit": 3, "cursor": cursor}).json()
        seen += [i["title"] for i in page["results"]]
        cursor = page["next_cursor"]
        if not cursor:
            break
    assert seen == ["An award", "News 2", "News 1", "News 0"]


@pytest.mark.parametrize(
    "params", [{"type": "gossip"}, {"limit": 0}, {"limit": 51}, {"cursor": "x"}, {"x": 1}]
)
def test_bad_queries_are_refused(member_client, params):
    assert member_client.get(ITEMS, params).status_code == 400


def test_linked_startups_are_shown_if_their_basics_are_visible(editor, member_client, other_client):
    from apps.startups.tests.conftest import STARTUPS, new_startup_body

    visible = other_client.post(STARTUPS, new_startup_body(name="Visible Co")).json()["id"]
    hidden = other_client.post(STARTUPS, new_startup_body(name="Hidden Co")).json()["id"]
    etag = other_client.get(f"{STARTUPS}/{hidden}")["ETag"]
    other_client.patch(f"{STARTUPS}/{hidden}/visibility", {"basics": "private"}, HTTP_IF_MATCH=etag)
    item = story(editor, startup_ids=[uuid.UUID(visible), uuid.UUID(hidden)])
    names = [s["name"] for s in member_client.get(item_url(item)).json()["startups"]]
    assert names == ["Visible Co"]


def test_the_news_page_is_for_active_members_only(api_client, make_user, client_for, published):
    assert api_client.get(ITEMS).status_code == 401
    pending = client_for(make_user(email="p@example.com", status="pending"))
    assert pending.get(ITEMS).status_code == 403
    assert pending.get(item_url(published)).status_code == 403


def test_unknown_items_are_404(member_client):
    assert member_client.get(f"{ITEMS}/{uuid.uuid4()}").status_code == 404


# --- comments ---


def comments_url(item):
    return f"{item_url(item)}/comments"


def comment(client, item, body="<p>Great news</p>"):
    return client.post(comments_url(item), {"body": body}, format="json")


def test_a_member_can_comment_and_it_counts(member_client, other_client, published, member):
    response = comment(member_client, published)
    assert response.status_code == 201
    body = response.json()
    assert body["body"] == "<p>Great news</p>" and body["mine"] is True
    assert body["author"]["id"] == str(member.pk)
    assert other_client.get(item_url(published)).json()["comment_count"] == 1
    assert AnalyticsEvent.objects.filter(name="comment_created", actor_id=member.pk).exists()


def test_comments_are_listed_oldest_first_and_paged(member_client, other_client, published):
    ids = [comment(member_client, published, f"<p>{i}</p>").json()["id"] for i in range(4)]
    seen, cursor = [], ""
    while True:
        page = other_client.get(comments_url(published), {"limit": 3, "cursor": cursor}).json()
        seen += [c["id"] for c in page["results"]]
        cursor = page["next_cursor"]
        if not cursor:
            break
    assert seen == ids


def test_comment_text_is_cleaned_and_limited(member_client, published):
    body = comment(member_client, published, "<h1>x</h1><script>bad()</script><p>ok</p>").json()[
        "body"
    ]
    assert "<script" not in body and "<h1" not in body
    for bad in ("", "<p></p>", "x" * 1501):
        assert comment(member_client, published, bad).status_code == 400
    assert (
        member_client.post(
            comments_url(published), {"body": "x", "extra": 1}, format="json"
        ).status_code
        == 400
    )


def test_comments_can_be_switched_off_per_item(editor, member_client, other_client):
    item = story(editor, comments_enabled=False)
    assert comment(member_client, item).status_code == 409
    assert other_client.get(comments_url(item)).json()["results"] == []


def test_existing_comments_stay_when_comments_are_switched_off(member_client, published):
    comment(member_client, published)
    EditorialItem.objects.filter(pk=published.pk).update(comments_enabled=False)
    assert len(member_client.get(comments_url(published)).json()["results"]) == 1
    assert comment(member_client, published).status_code == 409


def test_comments_need_a_published_item_and_an_active_member(
    editor, api_client, member_client, make_user, client_for
):
    draft = story(editor, _draft=True)
    assert comment(member_client, draft).status_code == 404
    published = story(editor)
    assert comment(api_client, published).status_code == 401
    assert (
        comment(
            client_for(make_user(email="p@example.com", status="pending")), published
        ).status_code
        == 403
    )


def test_comments_have_a_daily_allowance(member_client, published, monkeypatch):
    monkeypatch.setattr(services, "COMMENTS_PER_DAY", 2)
    assert [comment(member_client, published).status_code for _ in range(3)] == [201, 201, 429]


def test_the_author_can_edit_and_delete_their_comment_and_others_cannot(
    member_client, other_client, published
):
    cid = comment(member_client, published).json()["id"]
    url = f"/api/v1/editorial-comments/{cid}"
    assert other_client.patch(url, {"body": "<p>x</p>"}, format="json").status_code == 404
    assert other_client.delete(url).status_code == 404
    edited = member_client.patch(url, {"body": "<p>Better</p>"}, format="json")
    assert edited.status_code == 200 and edited.json()["edited_at"]
    assert member_client.delete(url).status_code == 204
    assert member_client.delete(url).status_code == 404
    assert member_client.get(item_url(published)).json()["comment_count"] == 0


def test_comments_of_suspended_members_vanish(member_client, other_client, published, member):
    from apps.accounts.models import User

    comment(member_client, published)
    User.objects.filter(pk=member.pk).update(status="suspended")
    assert other_client.get(comments_url(published)).json()["results"] == []


# --- reactions ---


def react(client, item, kind="like"):
    return client.post(f"{item_url(item)}/reactions", {"kind": kind}, format="json")


def test_reacting_counts_is_idempotent_and_reversible(member_client, other_client, published):
    assert react(member_client, published, "celebrate").status_code == 201
    assert react(member_client, published, "celebrate").status_code == 200
    react(other_client, published, "celebrate")
    react(other_client, published, "like")
    seen = member_client.get(item_url(published)).json()
    assert seen["reactions"] == {"celebrate": 2, "like": 1} and seen["reaction_count"] == 3
    assert seen["my_reactions"] == ["celebrate"]
    gone = member_client.delete(f"{item_url(published)}/reactions/celebrate")
    assert gone.status_code == 200 and gone.json()["reactions"] == {"celebrate": 1, "like": 1}
    assert (
        member_client.delete(f"{item_url(published)}/reactions/celebrate").json()["reaction_count"]
        == 2
    )


def test_only_the_three_reactions_exist_and_only_on_published_items(
    editor, member_client, published
):
    assert react(member_client, published, "angry").status_code == 400
    draft = story(editor, _draft=True)
    assert react(member_client, draft).status_code == 404


# --- banners ---


def test_announcements_show_as_banners_only_during_their_window(editor, member_client):
    now = timezone.now()
    live = story(
        editor,
        type="announcement",
        title="Maintenance tonight",
        banner_starts_at=now - timedelta(hours=1),
        banner_ends_at=now + timedelta(days=1),
    )
    story(
        editor,
        type="announcement",
        title="Not yet",
        banner_starts_at=now + timedelta(days=1),
        banner_ends_at=now + timedelta(days=2),
    )
    story(editor, type="announcement", title="No banner")
    story(
        editor,
        type="announcement",
        title="Draft banner",
        _draft=True,
        banner_ends_at=now + timedelta(days=1),
    )
    banners = member_client.get(BANNERS).json()
    assert [b["id"] for b in banners] == [str(live.pk)]
    assert set(banners[0]) == {"id", "slug", "title", "excerpt", "external_url", "ends_at"}
    EditorialItem.objects.filter(pk=live.pk).update(banner_ends_at=now - timedelta(minutes=1))
    assert member_client.get(BANNERS).json() == []


def test_banners_need_an_active_member(api_client):
    assert api_client.get(BANNERS).status_code == 401


# --- win submissions ---


def win(**overrides):
    body = {
        "kind": "award",
        "title": "Won the Lagos Founder Award",
        "evidence_url": "https://awards.example.com/winners/2026",
        "details": "We were picked from 400 entries.",
    }
    body.update(overrides)
    return body


def test_a_member_can_submit_a_win_and_see_it(member_client, member):
    response = member_client.post(WINS, win(), format="json")
    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "pending" and body["kind"] == "award"
    assert member_client.get(WINS).json()["results"][0]["id"] == body["id"]
    [event] = AnalyticsEvent.objects.filter(name="win_submitted")
    assert event.actor_id == member.pk and event.properties == {"kind": "award"}


@pytest.mark.parametrize(
    "overrides",
    [
        {"kind": "birthday"},
        {"title": ""},
        {"title": "x" * 161},
        {"evidence_url": ""},
        {"evidence_url": "http://insecure.example.com"},
        {"evidence_url": "javascript:alert(1)"},
        {"evidence_url": "https://127.0.0.1/proof"},
        {"details": "x" * 1001},
        {"status": "approved"},
        {"startup_id": str(uuid.uuid4())},
    ],
)
def test_invalid_submissions_are_refused(member_client, overrides):
    assert member_client.post(WINS, win(**overrides), format="json").status_code == 400
    assert WinSubmission.objects.count() == 0


def test_a_win_can_name_ones_own_startup_only(member_client, other_client):
    from apps.startups.tests.conftest import STARTUPS, new_startup_body

    mine = member_client.post(STARTUPS, new_startup_body()).json()["id"]
    assert member_client.post(WINS, win(startup_id=mine), format="json").status_code == 201
    assert other_client.post(WINS, win(startup_id=mine), format="json").status_code == 400


def test_only_three_submissions_can_wait_at_once(member_client):
    assert [member_client.post(WINS, win(), format="json").status_code for _ in range(4)] == [
        201,
        201,
        201,
        400,
    ]


def test_submissions_have_a_daily_allowance(member_client, monkeypatch):
    monkeypatch.setattr(services, "MAX_PENDING_WINS", 100)
    monkeypatch.setattr(services, "WINS_PER_DAY", 2)
    assert [member_client.post(WINS, win(), format="json").status_code for _ in range(3)] == [
        201,
        201,
        429,
    ]


def test_you_only_see_your_own_submissions(member_client, other_client):
    member_client.post(WINS, win(), format="json")
    assert other_client.get(WINS).json()["results"] == []


def test_submitting_needs_an_active_member(api_client, make_user, client_for):
    assert api_client.post(WINS, win(), format="json").status_code == 401
    assert (
        client_for(make_user(email="p@example.com", status="pending"))
        .post(WINS, win(), format="json")
        .status_code
        == 403
    )


def test_a_reviewed_submission_notifies_the_member(editor, member_client, member, run_outbox):
    submitted = member_client.post(WINS, win(), format="json").json()["id"]
    win_row = WinSubmission.objects.get(pk=submitted)
    services.review_win(actor=editor, win_id=win_row.pk, decision="approve")
    run_outbox()
    [notice] = Notification.objects.filter(user=member)
    assert notice.type == "win_approved"
    assert "accepted" in member_client.get("/api/v1/notifications").json()["results"][0]["title"]
