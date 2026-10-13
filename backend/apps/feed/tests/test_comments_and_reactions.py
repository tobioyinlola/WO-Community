import uuid

import pytest

from apps.analytics.models import AnalyticsEvent
from apps.core.models import OutboxEvent
from apps.feed.models import Comment, Post, Reaction
from apps.feed.tests.conftest import POSTS, active, comments_url, post_url, write_post

pytestmark = pytest.mark.django_db


def comment(client, post, body="<p>Nice one</p>", **extra):
    return client.post(comments_url(post), {"body": body, **extra}, format="json")


def post_of(client, post):
    return client.get(post_url(post)).json()


# --- commenting ---


def test_a_member_can_comment_and_it_counts(reader_client, author_client, post_id, reader):
    response = comment(reader_client, post_id)
    assert response.status_code == 201
    body = response.json()
    assert body["body"] == "<p>Nice one</p>" and body["mine"] is True
    assert body["author"]["id"] == str(reader.pk) and body["replies"] == []
    assert post_of(author_client, post_id)["comment_count"] == 1
    assert AnalyticsEvent.objects.filter(name="comment_created", actor_id=reader.pk).exists()


def test_comments_are_listed_oldest_first_with_their_replies(reader_client, author_client, post_id):
    first = comment(reader_client, post_id, "<p>first</p>").json()["id"]
    second = comment(author_client, post_id, "<p>second</p>").json()["id"]
    reply = comment(author_client, post_id, "<p>reply</p>", parent_id=first).json()["id"]
    page = reader_client.get(comments_url(post_id)).json()
    assert [c["id"] for c in page["results"]] == [first, second]
    assert [r["id"] for r in page["results"][0]["replies"]] == [reply]
    assert page["results"][1]["replies"] == []
    assert post_of(reader_client, post_id)["comment_count"] == 3


def test_comment_pages_walk_every_comment_once(reader_client, post_id):
    ids = [comment(reader_client, post_id, f"<p>{i}</p>").json()["id"] for i in range(5)]
    seen, cursor = [], ""
    while True:
        page = reader_client.get(comments_url(post_id), {"limit": 2, "cursor": cursor}).json()
        seen += [c["id"] for c in page["results"]]
        cursor = page["next_cursor"]
        if not cursor:
            break
    assert seen == ids


def test_replies_go_one_level_deep(reader_client, post_id):
    top = comment(reader_client, post_id).json()["id"]
    reply = comment(reader_client, post_id, parent_id=top).json()["id"]
    assert comment(reader_client, post_id, parent_id=reply).status_code == 400


def test_a_reply_must_belong_to_the_same_post(reader_client, author_client, post_id):
    other_post = write_post(author_client).json()["id"]
    elsewhere = comment(reader_client, other_post).json()["id"]
    assert comment(reader_client, post_id, parent_id=elsewhere).status_code == 400
    assert comment(reader_client, post_id, parent_id=str(uuid.uuid4())).status_code == 400


@pytest.mark.parametrize(
    "body",
    [{}, {"body": ""}, {"body": "<p></p>"}, {"body": "x" * 1501}, {"body": "ok", "post": "x"}],
)
def test_invalid_comments_are_refused(reader_client, post_id, body):
    assert reader_client.post(comments_url(post_id), body, format="json").status_code == 400
    assert Comment.objects.count() == 0


def test_comment_markup_is_limited_to_inline_formatting(reader_client, post_id):
    body = comment(
        reader_client,
        post_id,
        '<h2>big</h2><p onclick="x()">hi <strong>there</strong></p><script>x</script>',
    ).json()["body"]
    assert "<h2" not in body and "onclick" not in body and "<script" not in body
    assert "<strong>there</strong>" in body


def test_commenting_on_a_missing_or_hidden_post_is_404(reader_client, post_id):
    assert comment(reader_client, str(uuid.uuid4())).status_code == 404
    Post.objects.filter(pk=post_id).update(hidden_at="2026-01-01T00:00:00Z")
    assert comment(reader_client, post_id).status_code == 404


def test_comments_need_an_active_member(api_client, make_user, client_for, post_id):
    assert api_client.post(comments_url(post_id), {"body": "x"}).status_code == 401
    pending = client_for(make_user(email="p@example.com", status="pending"))
    assert pending.post(comments_url(post_id), {"body": "x"}).status_code == 403
    assert pending.get(comments_url(post_id)).status_code == 403


def test_comments_have_a_daily_allowance(reader_client, post_id, settings):
    settings.FEED_COMMENTS_PER_DAY = 2
    assert [comment(reader_client, post_id).status_code for _ in range(3)] == [201, 201, 429]


def test_comments_by_removed_members_vanish(reader_client, author_client, post_id, reader):
    from apps.accounts.models import User

    comment(reader_client, post_id)
    User.objects.filter(pk=reader.pk).update(status="removed")
    assert author_client.get(comments_url(post_id)).json()["results"] == []


# --- editing and deleting comments ---


def test_the_author_can_edit_their_comment(reader_client, post_id):
    cid = comment(reader_client, post_id).json()["id"]
    response = reader_client.patch(
        f"/api/v1/comments/{cid}", {"body": "<p>Better</p>"}, format="json"
    )
    assert response.status_code == 200
    assert response.json()["body"] == "<p>Better</p>" and response.json()["edited_at"]


def test_others_cannot_edit_or_delete_a_comment(reader_client, author_client, post_id):
    cid = comment(reader_client, post_id).json()["id"]
    url = f"/api/v1/comments/{cid}"
    assert author_client.patch(url, {"body": "x"}, format="json").status_code == 404
    assert author_client.delete(url).status_code == 404
    assert Comment.objects.get(pk=cid).deleted_at is None


def test_deleting_a_comment_removes_its_replies_and_fixes_the_count(
    reader_client, author_client, post_id
):
    top = comment(reader_client, post_id).json()["id"]
    comment(author_client, post_id, parent_id=top)
    comment(author_client, post_id)
    assert post_of(reader_client, post_id)["comment_count"] == 3
    assert reader_client.delete(f"/api/v1/comments/{top}").status_code == 204
    after = reader_client.get(comments_url(post_id)).json()["results"]
    assert len(after) == 1
    assert post_of(reader_client, post_id)["comment_count"] == 1
    assert reader_client.delete(f"/api/v1/comments/{top}").status_code == 404


# --- reactions ---


def react(client, post, kind="like", target="posts"):
    return client.post(f"/api/v1/{target}/{post}/reactions", {"kind": kind}, format="json")


def test_a_member_can_react_and_the_counts_follow(reader_client, author_client, post_id, reader):
    response = react(reader_client, post_id, "celebrate")
    assert response.status_code == 201
    assert response.json() == {"created": True, "reactions": {"celebrate": 1}, "reaction_count": 1}
    seen = post_of(author_client, post_id)
    assert seen["reactions"] == {"celebrate": 1} and seen["my_reactions"] == []
    assert post_of(reader_client, post_id)["my_reactions"] == ["celebrate"]
    assert AnalyticsEvent.objects.filter(name="post_reacted", actor_id=reader.pk).exists()


def test_reacting_twice_the_same_way_is_harmless(reader_client, post_id):
    react(reader_client, post_id)
    again = react(reader_client, post_id)
    assert again.status_code == 200 and again.json()["reaction_count"] == 1
    assert Reaction.objects.count() == 1


def test_different_kinds_and_different_members_add_up(reader_client, author_client, post_id):
    react(reader_client, post_id, "like")
    react(reader_client, post_id, "insightful")
    react(author_client, post_id, "like")
    counts = post_of(reader_client, post_id)
    assert counts["reactions"] == {"like": 2, "insightful": 1} and counts["reaction_count"] == 3


def test_a_reaction_can_be_taken_back(reader_client, post_id):
    react(reader_client, post_id, "like")
    react(reader_client, post_id, "insightful")
    response = reader_client.delete(f"{POSTS}/{post_id}/reactions/like")
    assert response.status_code == 200
    assert response.json()["reactions"] == {"insightful": 1}
    again = reader_client.delete(f"{POSTS}/{post_id}/reactions/like")
    assert again.json()["reaction_count"] == 1  # nothing to take back, nothing changes
    assert Reaction.objects.count() == 1


def test_only_the_three_reactions_exist(reader_client, post_id):
    assert react(reader_client, post_id, "angry").status_code == 400
    assert reader_client.post(f"{POSTS}/{post_id}/reactions", {}, format="json").status_code == 400
    assert reader_client.delete(f"{POSTS}/{post_id}/reactions/angry").status_code == 400


def test_reactions_to_missing_or_hidden_posts_are_404(reader_client, post_id):
    assert react(reader_client, str(uuid.uuid4())).status_code == 404
    Post.objects.filter(pk=post_id).update(hidden_at="2026-01-01T00:00:00Z")
    assert react(reader_client, post_id).status_code == 404


def test_reactions_need_an_active_member(api_client, make_user, client_for, post_id):
    assert react(api_client, post_id).status_code == 401
    assert (
        react(client_for(make_user(email="p@example.com", status="pending")), post_id).status_code
        == 403
    )


def test_comments_take_reactions_too(reader_client, author_client, post_id):
    cid = comment(reader_client, post_id).json()["id"]
    response = react(author_client, cid, "like", target="comments")
    assert response.status_code == 201 and response.json()["reactions"] == {"like": 1}
    listed = author_client.get(comments_url(post_id)).json()["results"][0]
    assert listed["reactions"] == {"like": 1} and listed["my_reactions"] == ["like"]
    assert (
        author_client.delete(f"/api/v1/comments/{cid}/reactions/like").json()["reaction_count"] == 0
    )
    # a comment's reactions do not count towards the post's
    assert post_of(author_client, post_id)["reaction_count"] == 0


def test_reacting_to_a_comment_on_a_removed_post_is_404(reader_client, author_client, post_id):
    cid = comment(reader_client, post_id).json()["id"]
    author_client.delete(post_url(post_id))
    assert react(reader_client, cid, "like", target="comments").status_code == 404


@pytest.mark.django_db(transaction=True, serialized_rollback=True)
@pytest.mark.usefixtures("truncate_audit")
def test_counters_stay_exact_under_concurrent_reactions(post_id, make_user, client_for):
    """Several members react at once; the stored count must equal the rows."""
    from concurrent.futures import ThreadPoolExecutor

    from django.db import connections

    from apps.feed import services

    members = [active(make_user, f"m{i}@example.com") for i in range(6)]

    def go(member):
        try:
            return services.react(
                user_id=member.pk, target_type="post", target_id=uuid.UUID(post_id), kind="like"
            )
        finally:
            connections.close_all()

    with ThreadPoolExecutor(6) as pool:
        list(pool.map(go, members))
    post = Post.objects.get(pk=post_id)
    assert post.reaction_count == Reaction.objects.filter(target_id=post.pk).count() == 6
    assert post.engagement == 6


# --- mentions and notices ---


def topics():
    return list(OutboxEvent.objects.values_list("topic", flat=True))


def test_mentioning_active_members_queues_a_notice_for_each(
    author_client, reader, make_user, author
):
    other = active(make_user, "other@example.com")
    pending = make_user(email="pending@example.com", status="pending")
    write_post(
        author_client,
        mentions=[str(reader.pk), str(other.pk), str(pending.pk), str(author.pk), str(reader.pk)],
    )
    mentioned = [
        e.payload["user_id"] for e in OutboxEvent.objects.filter(topic="feed.member_mentioned")
    ]
    assert sorted(mentioned) == sorted([str(reader.pk), str(other.pk)])


def test_a_comment_tells_the_post_author_and_the_parent_author(
    reader_client, author_client, post_id, author, reader
):
    top = comment(reader_client, post_id).json()["id"]
    comment(author_client, post_id, parent_id=top)
    events = [e.payload for e in OutboxEvent.objects.filter(topic="feed.comment_added")]
    assert events[0]["post_author_id"] == str(author.pk) and events[0]["parent_author_id"] == ""
    assert events[1]["parent_author_id"] == str(reader.pk)


def test_comment_mentions_are_queued_too(reader_client, post_id, author):
    comment(reader_client, post_id, mentions=[str(author.pk)])
    assert "feed.member_mentioned" in topics()
