from datetime import timedelta

import pytest
from django.utils import timezone

from apps.audit.models import AuditLog
from apps.feed import services
from apps.feed.models import Post
from apps.feed.tests.conftest import POSTS, active, comments_url, write_post
from apps.notifications.models import Notification

pytestmark = pytest.mark.django_db

ADMIN = "/api/v1/admin/posts"


@pytest.fixture
def admin(make_user):
    return active(make_user, "admin@example.com", roles=("community_admin", "member"))


@pytest.fixture
def admin_client(admin, client_for):
    return client_for(admin, mfa_age=5)


def team_post(client, **fields):
    body = {"category": "update", "body": "<p>Welcome to the community</p>", **fields}
    return client.post(ADMIN, body, format="json")


def in_feed(client):
    page = client.get(POSTS).json()
    return [p["id"] for p in page.get("pinned", []) + page["results"]]


def soon(**delta):
    return (timezone.now() + timedelta(**delta)).isoformat()


# --- posting as the team ---


def test_a_team_post_goes_live_at_once_with_the_team_as_author(admin_client, reader_client):
    made = team_post(admin_client, official=True).json()
    assert made["official"] is True
    seen = reader_client.get(f"{POSTS}/{made['id']}").json()
    assert seen["official"] is True
    assert seen["author"]["name"] == "WO Community team" and seen["author"]["slug"] is None
    assert made["id"] in in_feed(reader_client)


def test_posting_as_yourself_shows_your_own_name(admin_client, reader_client, admin):
    made = team_post(admin_client).json()
    seen = reader_client.get(f"{POSTS}/{made['id']}").json()
    assert seen["official"] is False and seen["author"]["name"] != "WO Community team"


def test_a_team_post_is_not_limited_by_the_daily_allowance(admin_client, settings):
    settings.FEED_POSTS_PER_DAY = 1
    assert team_post(admin_client).status_code == 201
    assert team_post(admin_client).status_code == 201


def test_a_member_cannot_use_the_team_options_or_endpoint(reader_client):
    assert team_post(reader_client).status_code == 403
    extra = write_post(reader_client, official=True, pin=True)
    assert extra.status_code == 400  # unknown fields are refused


# --- pinning ---


def test_a_pinned_post_leads_the_feed_until_the_pin_lapses(admin_client, reader_client):
    older = team_post(admin_client, body="<p>Older</p>").json()["id"]
    pinned = team_post(
        admin_client, body="<p>Pinned</p>", pin=True, pinned_until=soon(days=2)
    ).json()
    team_post(admin_client, body="<p>Newest</p>")
    page = reader_client.get(POSTS).json()
    assert [p["id"] for p in page["pinned"]] == [pinned["id"]]
    assert pinned["id"] not in [p["id"] for p in page["results"]]
    Post.objects.filter(pk=pinned["id"]).update(pinned_until=timezone.now() - timedelta(minutes=1))
    page = reader_client.get(POSTS).json()
    assert page["pinned"] == [] and pinned["id"] in [p["id"] for p in page["results"]]
    assert older in [p["id"] for p in page["results"]]


def test_a_pin_in_the_past_or_without_a_pin_is_refused(admin_client):
    assert team_post(admin_client, pin=True, pinned_until=soon(days=-1)).status_code == 400
    assert team_post(admin_client, pinned_until=soon(days=1)).status_code == 400


# --- comments ---


def test_comments_can_be_turned_off(admin_client, reader_client):
    post = team_post(admin_client, comments_enabled=False).json()
    assert reader_client.get(f"{POSTS}/{post['id']}").json()["comments_enabled"] is False
    refused = reader_client.post(comments_url(post["id"]), {"body": "<p>hi</p>"}, format="json")
    assert refused.status_code == 403
    admin_client.patch(f"{ADMIN}/{post['id']}", {"comments_enabled": True}, format="json")
    ok = reader_client.post(comments_url(post["id"]), {"body": "<p>hi</p>"}, format="json")
    assert ok.status_code == 201


# --- audience ---


def test_a_post_for_mentors_is_seen_only_by_mentors_and_the_team(
    admin_client, make_user, client_for
):
    mentor = client_for(active(make_user, "mentor@example.com", roles=("mentor", "member")))
    plain = client_for(active(make_user, "plain@example.com"))
    post = team_post(admin_client, audience_roles=["mentor"]).json()["id"]
    assert post in in_feed(mentor) and post in in_feed(admin_client)
    assert post not in in_feed(plain)
    assert plain.get(f"{POSTS}/{post}").status_code == 404
    assert team_post(admin_client, audience_roles=["wizard"]).status_code == 400


# --- scheduling ---


def test_a_scheduled_post_waits_and_then_appears_when_due(admin_client, reader_client):
    made = team_post(admin_client, scheduled_for=soon(hours=2)).json()
    assert made["scheduled_for"] is not None
    assert made["id"] not in in_feed(reader_client)
    assert reader_client.get(f"{POSTS}/{made['id']}").status_code == 404
    listed = admin_client.get(ADMIN, {"state": "scheduled"}).json()
    assert [r["id"] for r in listed["results"]] == [made["id"]]
    assert made["id"] not in [r["id"] for r in admin_client.get(ADMIN).json()["results"]]
    assert services.publish_due() == 0
    assert services.publish_due(now=timezone.now() + timedelta(hours=3)) == 1
    assert made["id"] in in_feed(reader_client)
    assert admin_client.get(ADMIN, {"state": "scheduled"}).json()["results"] == []


def test_a_scheduled_post_can_be_moved_but_not_into_the_past(admin_client):
    made = team_post(admin_client, scheduled_for=soon(hours=2)).json()
    moved = admin_client.patch(
        f"{ADMIN}/{made['id']}", {"scheduled_for": soon(hours=5)}, format="json"
    )
    assert moved.status_code == 200
    past = admin_client.patch(
        f"{ADMIN}/{made['id']}", {"scheduled_for": soon(hours=-1)}, format="json"
    )
    assert past.status_code == 400


def test_a_past_schedule_is_refused(admin_client):
    assert team_post(admin_client, scheduled_for=soon(hours=-1)).status_code == 400


# --- moderating members' posts ---


def test_hiding_and_removing_a_members_post_tells_the_author_and_is_audited(
    admin_client, author_client, author, post_id, run_outbox
):
    admin_client.post(f"{ADMIN}/{post_id}/hide", {"reason": "Off topic"}, format="json")
    admin_client.post(f"{ADMIN}/{post_id}/remove", {"reason": "Spam"}, format="json")
    run_outbox()
    notes = list(Notification.objects.filter(user=author, type="post_moderated"))
    assert {n.payload["what"] for n in notes} == {"hidden", "removed"}
    assert AuditLog.objects.filter(action="feed.post_hide", target_id=post_id).exists()
    assert AuditLog.objects.filter(action="feed.post_remove", target_id=post_id).exists()


def test_the_team_can_edit_any_post_and_it_is_audited(
    admin_client, author_client, author, post_id, run_outbox
):
    done = admin_client.patch(
        f"{ADMIN}/{post_id}", {"body": "<p>Tidied by the team</p>"}, format="json"
    )
    assert done.status_code == 200
    assert "Tidied" in Post.objects.get(pk=post_id).body_text
    entry = AuditLog.objects.get(action="feed.post_edited_by_team")
    assert entry.target_id == post_id and entry.before["body"]
    run_outbox()
    assert Notification.objects.filter(user=author, type="post_moderated").exists()


def test_team_posts_are_audited(admin_client):
    made = team_post(admin_client, official=True, pin=True).json()
    entry = AuditLog.objects.get(action="feed.post_created_by_team")
    assert entry.target_id == made["id"] and entry.after["official"] == "True"


def test_only_the_team_can_use_the_admin_post_tools(reader_client, post_id):
    assert (
        reader_client.patch(f"{ADMIN}/{post_id}", {"body": "<p>x</p>"}, format="json").status_code
        == 403
    )
    assert reader_client.get(ADMIN, {"state": "scheduled"}).status_code == 403


def test_the_team_list_filter_finds_official_posts(admin_client):
    team_post(admin_client, official=True)
    team_post(admin_client)
    assert admin_client.get(ADMIN, {"state": "team"}).json()["count"] == 1
