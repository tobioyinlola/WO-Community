from datetime import timedelta

import pytest
from django.core.cache import cache
from django.utils import timezone

from apps.audit import services as audit
from apps.feed.models import Comment, Post, Reaction
from apps.memberarea import leaderboard

pytestmark = pytest.mark.django_db

URL = "/api/v1/leaderboard"


@pytest.fixture(autouse=True)
def _fresh():
    cache.clear()


def active(make_user, email, **fields):
    return make_user(
        email=email, approved_at=timezone.now(), email_verified_at=timezone.now(), **fields
    )


def post_by(user, **fields):
    return Post.objects.create(
        author=user, category="update", body="<p>Hi</p>", body_text="Hi", **fields
    )


def signed_in(user):
    audit.record(actor=user, action="auth.login", target_type="session")


def test_members_are_ranked_by_points_from_what_they_did(make_user, client_for):
    ada = active(make_user, "ada@example.com")
    kofi = active(make_user, "kofi@example.com")
    post = post_by(ada)  # 10
    Comment.objects.create(post=post, author=kofi, body="<p>Nice</p>")  # kofi 5
    Reaction.objects.create(target_type="post", target_id=post.pk, user=kofi, kind="like")
    # kofi +1 for giving it, ada +2 for receiving it

    body = client_for(ada).get(URL).json()
    assert [(e["name"] != "", e["points"], e["rank"]) for e in body["entries"]] == [
        (True, 12, 1),
        (True, 6, 2),
    ]
    first = body["entries"][0]
    assert first["user_id"] == str(ada.pk) and first["is_me"] is True
    assert first["breakdown"]["posts"] == 1 and first["breakdown"]["reactions_received"] == 1
    assert body["me"] == {
        "rank": 1,
        "points": 12,
        "breakdown": first["breakdown"],
        "ranked_members": 2,
    }
    assert body["points"]["posts"] == 10 and body["period_days"] == 30


def test_days_signed_in_count_once_each(make_user, client_for):
    ada = active(make_user, "ada@example.com")
    signed_in(ada)
    signed_in(ada)  # the same day again
    entry = client_for(ada).get(URL).json()["entries"][0]
    assert entry["breakdown"]["login_days"] == 1 and entry["points"] == 3


def test_reacting_to_your_own_post_and_hidden_posts_earn_nothing(make_user, client_for):
    ada = active(make_user, "ada@example.com")
    post = post_by(ada, hidden_at=timezone.now())
    Reaction.objects.create(target_type="post", target_id=post.pk, user=ada, kind="like")
    entry = client_for(ada).get(URL).json()["me"]
    assert entry["breakdown"]["posts"] == 0 and entry["breakdown"]["reactions_received"] == 0
    assert entry["points"] == 1  # only the reaction given


def test_old_activity_and_people_who_are_not_members_are_left_out(make_user, client_for):
    ada = active(make_user, "ada@example.com")
    staff = active(make_user, "staff@example.com", roles=("community_admin",))
    suspended = active(make_user, "gone@example.com", status="suspended")
    old = post_by(ada)
    Post.objects.filter(pk=old.pk).update(created_at=timezone.now() - timedelta(days=40))
    post_by(staff)
    post_by(suspended)
    body = client_for(ada).get(URL).json()
    assert body["entries"] == [] and body["me"]["rank"] is None


def test_ties_share_a_rank_and_only_ten_are_shown(make_user, client_for):
    people = [active(make_user, f"m{n}@example.com") for n in range(12)]
    for person in people:
        post_by(person)
    body = client_for(people[0]).get(URL).json()
    assert len(body["entries"]) == 10
    assert {e["rank"] for e in body["entries"]} == {1}
    assert body["me"]["ranked_members"] == 12


def test_names_follow_profile_visibility(make_user, client_for):
    from apps.profiles.services import get_or_create_profile, update_visibility

    ada = active(make_user, "ada@example.com")
    viewer = active(make_user, "viewer@example.com")
    profile = get_or_create_profile(ada.pk)
    profile.full_name = "Ada Obi"
    profile.save()
    update_visibility(user_id=ada.pk, levels={"basics": "private"})
    post_by(ada)
    leader = client_for(viewer).get(URL).json()["entries"][0]
    assert leader["name"] == "Community member"


def test_the_leaderboard_is_for_signed_in_members(api_client):
    assert api_client.get(URL).status_code == 401


def test_admins_see_real_names_and_emails(make_user, client_for):
    ada = active(make_user, "ada@example.com")
    post_by(ada)
    admin = make_user(roles=("community_admin",), email="boss@example.com")
    body = client_for(admin, mfa_age=5).get("/api/v1/admin/leaderboard").json()
    assert body["entries"][0]["email"] == "ada@example.com"
    assert body["entries"][0]["points"] == 10


def test_standings_are_cached_for_a_few_minutes(make_user):
    ada = active(make_user, "ada@example.com")
    post_by(ada)
    assert leaderboard.standings()[0]["points"] == 10
    post_by(ada)
    assert leaderboard.standings()[0]["points"] == 10  # still the cached figure
    cache.clear()
    assert leaderboard.standings()[0]["points"] == 20
