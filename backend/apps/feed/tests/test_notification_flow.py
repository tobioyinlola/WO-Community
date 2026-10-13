"""The feed's events arriving as notifications, end to end through the outbox."""

import pytest

from apps.feed.tests.conftest import POSTS, active, comments_url, write_post
from apps.notifications.models import Notification

pytestmark = pytest.mark.django_db

LIST = "/api/v1/notifications"


def titles(client):
    return [n["title"] for n in client.get(LIST).json()["results"]]


def test_a_comment_notifies_the_post_author(author_client, reader_client, post_id, run_outbox):
    reader_client.post(comments_url(post_id), {"body": "<p>great</p>"}, format="json")
    run_outbox()
    [item] = author_client.get(LIST).json()["results"]
    assert item["type"] == "comment" and item["link"] == f"/posts/{post_id}"
    assert reader_client.get(LIST).json()["results"] == []  # not the commenter


def test_commenting_on_your_own_post_notifies_nobody(author_client, post_id, run_outbox):
    author_client.post(comments_url(post_id), {"body": "<p>note to self</p>"}, format="json")
    run_outbox()
    assert Notification.objects.count() == 0


def test_a_reply_notifies_the_comment_author_not_also_the_post_author_twice(
    author_client, reader_client, make_user, client_for, post_id, run_outbox
):
    third = client_for(active(make_user, "third@example.com"))
    top = third.post(comments_url(post_id), {"body": "<p>first</p>"}, format="json").json()["id"]
    run_outbox()
    reader_client.post(
        comments_url(post_id), {"body": "<p>reply</p>", "parent_id": top}, format="json"
    )
    run_outbox()
    assert [n.split(" ", 2)[-1] for n in titles(third)] == ["replied to your comment"]
    assert len(titles(author_client)) == 2  # the first comment, and the reply under it


def test_replying_to_the_post_authors_own_comment_notifies_them_once(
    author_client, reader_client, post_id, run_outbox
):
    top = author_client.post(comments_url(post_id), {"body": "<p>mine</p>"}, format="json").json()[
        "id"
    ]
    reader_client.post(
        comments_url(post_id), {"body": "<p>reply</p>", "parent_id": top}, format="json"
    )
    run_outbox()
    assert [n["type"] for n in author_client.get(LIST).json()["results"]] == ["reply"]


def test_mentions_notify_each_mentioned_member_once(
    author_client, reader, reader_client, make_user, run_outbox
):
    write_post(author_client, mentions=[str(reader.pk)])
    run_outbox()
    run_outbox()
    [item] = reader_client.get(LIST).json()["results"]
    assert item["type"] == "mention" and item["title"].endswith("mentioned you in a post")


def test_a_comment_mention_says_comment(author_client, reader_client, author, post_id, run_outbox):
    reader_client.post(
        comments_url(post_id), {"body": "<p>hey</p>", "mentions": [str(author.pk)]}, format="json"
    )
    run_outbox()
    assert any(t.endswith("mentioned you in a comment") for t in titles(author_client))


def test_a_mention_can_be_switched_off(author_client, reader, reader_client, run_outbox):
    reader_client.put(
        "/api/v1/me/notification-preferences",
        {"preferences": {"mentions": {"in_app": False}}},
        format="json",
    )
    write_post(author_client, mentions=[str(reader.pk)])
    run_outbox()
    assert reader_client.get(LIST).json()["results"] == []


def test_an_event_delivered_twice_notifies_once(author_client, reader_client, post_id, run_outbox):
    from apps.core.models import OutboxEvent

    reader_client.post(comments_url(post_id), {"body": "<p>x</p>"}, format="json")
    run_outbox()
    OutboxEvent.objects.update(status="pending")  # the publisher redelivers everything
    run_outbox()
    assert Notification.objects.count() == 1


def test_reporters_are_told_what_happened(
    reader_client, post_id, run_outbox, make_user, client_for
):
    reader_client.post(f"{POSTS}/{post_id}/reports", {"reason": "spam"}, format="json")
    admin = client_for(make_user(roles=("community_admin",), email="admin@example.com"), mfa_age=5)
    rid = admin.get("/api/v1/admin/reports").json()["results"][0]["id"]
    admin.post(f"/api/v1/admin/reports/{rid}/action", {"action": "hide"}, format="json")
    run_outbox()
    [item] = reader_client.get(LIST).json()["results"]
    assert item["type"] == "report_outcome"
    assert item["title"] == "A moderator removed or hid the post you reported"
    assert item["meta"] == {"outcome": "actioned", "target_type": "post"}


def test_every_reporter_of_an_actioned_item_is_told_and_a_review_tells_only_one(
    reader_client, post_id, run_outbox, make_user, client_for
):
    other = client_for(active(make_user, "other@example.com"))
    reader_client.post(f"{POSTS}/{post_id}/reports", {"reason": "spam"}, format="json")
    other.post(f"{POSTS}/{post_id}/reports", {"reason": "illegal"}, format="json")
    admin = client_for(make_user(roles=("community_admin",), email="admin@example.com"), mfa_age=5)
    reports = admin.get("/api/v1/admin/reports").json()["results"]
    admin.post(f"/api/v1/admin/reports/{reports[0]['id']}/review", {}, format="json")
    run_outbox()
    assert len(reader_client.get(LIST).json()["results"]) == 1
    assert other.get(LIST).json()["results"] == []
    admin.post(
        f"/api/v1/admin/reports/{reports[1]['id']}/action", {"action": "remove"}, format="json"
    )
    run_outbox()
    assert len(other.get(LIST).json()["results"]) == 1
    assert "removed or hid" in titles(other)[0]


def test_an_approved_member_gets_a_welcome_notice(make_user, client_for, run_outbox):
    pending = make_user(
        roles=(),
        status="pending",
        email="new@example.com",
        email_verified_at="2026-01-01T00:00:00Z",
    )
    admin = client_for(make_user(roles=("community_admin",), email="admin@example.com"), mfa_age=5)
    admin.post(f"/api/v1/admin/members/{pending.pk}/approve")
    run_outbox()
    [item] = client_for(pending).get(LIST).json()["results"]
    assert item["type"] == "member_approved"
