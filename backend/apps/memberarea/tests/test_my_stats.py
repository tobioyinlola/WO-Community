import pytest
from django.utils import timezone

from apps.feed.models import Comment, Follow, Post, Reaction

pytestmark = pytest.mark.django_db

URL = "/api/v1/me/stats"


def active(make_user, email):
    return make_user(email=email, approved_at=timezone.now(), email_verified_at=timezone.now())


def test_a_member_sees_their_reach_and_not_their_own_reactions(make_user, client_for):
    me = active(make_user, "me@example.com")
    fan = active(make_user, "fan@example.com")
    post = Post.objects.create(author=me, category="update", body="<p>Hi</p>", body_text="Hi")
    Reaction.objects.create(target_type="post", target_id=post.pk, user=fan, kind="like")
    Reaction.objects.create(target_type="post", target_id=post.pk, user=me, kind="like")
    Comment.objects.create(post=post, author=fan, body="<p>Nice</p>")
    Follow.objects.create(follower=fan, followee_type="member", followee_id=me.pk)

    body = client_for(me).get(URL).json()
    assert body["posts"] == 1
    assert body["reactions_received"] == 1 and body["reactions_recent"] == 1
    assert body["comments_received"] == 1
    assert body["followers"] == 1 and body["followers_recent"] == 1
    assert body["courses_completed"] == 0 and body["sessions_upcoming"] == 0


def test_stats_need_sign_in(api_client):
    assert api_client.get(URL).status_code == 401
