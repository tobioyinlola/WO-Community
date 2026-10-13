import uuid

import pytest

from apps.accounts.models import User
from apps.feed import follows
from apps.feed.models import Follow
from apps.feed.tests.conftest import POSTS, active, write_post
from apps.startups.tests.conftest import STARTUPS, new_startup_body

pytestmark = pytest.mark.django_db

FOLLOWS = "/api/v1/follows"
FOLLOWING = "/api/v1/me/following"


def follow(client, kind, target):
    return client.post(FOLLOWS, {"type": kind, "id": str(target)}, format="json")


def unfollow(client, kind, target):
    return client.delete(f"{FOLLOWS}/{kind}/{target}")


def feed_ids(client, **params):
    return [p["id"] for p in client.get(POSTS, {"scope": "following", **params}).json()["results"]]


@pytest.fixture
def third(make_user, client_for):
    user = active(make_user, "third@example.com")
    return user, client_for(user)


# --- following and unfollowing ---


def test_a_member_can_follow_another_member(reader_client, author, author_client):
    response = follow(reader_client, "member", author.pk)
    assert response.status_code == 201
    assert response.json() == {"type": "member", "id": str(author.pk), "following": True}
    assert Follow.objects.get().followee_id == author.pk


def test_following_twice_is_harmless(reader_client, author):
    follow(reader_client, "member", author.pk)
    assert follow(reader_client, "member", author.pk).status_code == 200
    assert Follow.objects.count() == 1


def test_unfollowing_removes_it_and_is_repeatable(reader_client, author):
    follow(reader_client, "member", author.pk)
    assert unfollow(reader_client, "member", author.pk).status_code == 204
    assert Follow.objects.count() == 0
    assert unfollow(reader_client, "member", author.pk).status_code == 204


def test_you_cannot_follow_yourself(author_client, author):
    assert follow(author_client, "member", author.pk).status_code == 400
    assert Follow.objects.count() == 0


def test_you_cannot_follow_someone_who_does_not_exist_or_is_not_active(reader_client, make_user):
    assert follow(reader_client, "member", uuid.uuid4()).status_code == 404
    pending = make_user(email="p@example.com", status="pending")
    assert follow(reader_client, "member", pending.pk).status_code == 404
    suspended = active(make_user, "s@example.com", status="suspended")
    assert follow(reader_client, "member", suspended.pk).status_code == 404


def test_you_cannot_follow_someone_who_hides_their_profile_from_you(
    reader_client, author, author_client
):
    author_client.patch("/api/v1/me/visibility", {"basics": "private"})
    assert follow(reader_client, "member", author.pk).status_code == 404


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"type": "member"},
        {"type": "group", "id": str(uuid.uuid4())},
        {"type": "member", "id": "x"},
    ],
)
def test_invalid_follow_requests_are_refused(reader_client, body):
    assert reader_client.post(FOLLOWS, body, format="json").status_code == 400


def test_the_unfollow_url_rejects_unknown_kinds(reader_client):
    assert unfollow(reader_client, "group", uuid.uuid4()).status_code == 404


def test_following_needs_an_active_member(api_client, make_user, client_for, author):
    assert follow(api_client, "member", author.pk).status_code == 401
    assert unfollow(api_client, "member", author.pk).status_code == 401
    assert api_client.get(FOLLOWING).status_code == 401
    pending = client_for(make_user(email="p@example.com", status="pending"))
    assert follow(pending, "member", author.pk).status_code == 403
    assert pending.get(FOLLOWING).status_code == 403


def test_there_is_a_limit_on_how_many_you_can_follow(reader_client, make_user, monkeypatch):
    monkeypatch.setattr(follows, "MAX_FOLLOWS", 2)
    people = [active(make_user, f"p{i}@example.com") for i in range(3)]
    assert [follow(reader_client, "member", p.pk).status_code for p in people] == [201, 201, 400]


# --- startups ---


@pytest.fixture
def startup(author_client):
    response = author_client.post(STARTUPS, new_startup_body(name="Kola Pay"))
    assert response.status_code == 201
    return response.json()["id"]


def test_a_startup_can_be_followed(reader_client, startup):
    assert follow(reader_client, "startup", startup).status_code == 201
    assert follow(reader_client, "startup", uuid.uuid4()).status_code == 404


def test_a_startup_that_hides_its_basics_cannot_be_followed(reader_client, author_client, startup):
    etag = author_client.get(f"{STARTUPS}/{startup}")["ETag"]
    author_client.patch(
        f"{STARTUPS}/{startup}/visibility", {"basics": "private"}, HTTP_IF_MATCH=etag
    )
    assert follow(reader_client, "startup", startup).status_code == 404


def test_a_startup_of_an_inactive_owner_cannot_be_followed(reader_client, author, startup):
    User.objects.filter(pk=author.pk).update(status="suspended")
    assert follow(reader_client, "startup", startup).status_code == 404


# --- who you follow ---


def test_the_following_list_shows_people_and_startups_newest_first(reader_client, author, startup):
    follow(reader_client, "member", author.pk)
    follow(reader_client, "startup", startup)
    items = reader_client.get(FOLLOWING).json()["results"]
    assert [i["type"] for i in items] == ["startup", "member"]
    assert items[0]["name"] == "Kola Pay" and items[0]["id"] == startup
    assert items[1]["id"] == str(author.pk)
    only = reader_client.get(FOLLOWING, {"type": "member"}).json()["results"]
    assert [i["type"] for i in only] == ["member"]


def test_the_following_list_paginates(reader_client, make_user):
    people = [active(make_user, f"p{i}@example.com") for i in range(5)]
    for person in people:
        follow(reader_client, "member", person.pk)
    seen, cursor = [], ""
    while True:
        page = reader_client.get(FOLLOWING, {"limit": 2, "cursor": cursor}).json()
        seen += [i["id"] for i in page["results"]]
        cursor = page["next_cursor"]
        if not cursor:
            break
    assert seen == [str(p.pk) for p in reversed(people)]


def test_people_you_can_no_longer_see_drop_off_the_list(reader_client, author, author_client):
    follow(reader_client, "member", author.pk)
    author_client.patch("/api/v1/me/visibility", {"basics": "private"})
    assert reader_client.get(FOLLOWING).json()["results"] == []
    author_client.patch("/api/v1/me/visibility", {"basics": "members"})
    assert len(reader_client.get(FOLLOWING).json()["results"]) == 1
    User.objects.filter(pk=author.pk).update(status="suspended")
    assert reader_client.get(FOLLOWING).json()["results"] == []


def test_the_following_list_is_private_to_each_member(reader_client, third, author):
    follow(reader_client, "member", author.pk)
    assert third[1].get(FOLLOWING).json()["results"] == []


@pytest.mark.parametrize(
    "params", [{"type": "group"}, {"limit": 0}, {"limit": 101}, {"cursor": "x"}, {"x": 1}]
)
def test_bad_following_queries_are_refused(reader_client, params):
    assert reader_client.get(FOLLOWING, params).status_code == 400


# --- the Following feed ---


def test_the_following_feed_has_only_posts_from_people_you_follow(
    reader_client, author, author_client, third
):
    wanted = write_post(author_client, "<p>from author</p>").json()["id"]
    write_post(third[1], "<p>from third</p>")
    assert feed_ids(reader_client) == []  # following nobody yet
    follow(reader_client, "member", author.pk)
    assert feed_ids(reader_client) == [wanted]
    assert len(reader_client.get(POSTS).json()["results"]) == 2  # the shared feed is unchanged


def test_posts_for_a_followed_startup_appear_even_from_other_team_members(
    reader_client, author_client, startup, third
):
    from apps.startups.models import Startup, StartupMember

    colleague, colleague_client = third
    StartupMember.objects.create(
        startup=Startup.objects.get(pk=startup), user=colleague, title="CTO"
    )
    posted = write_post(colleague_client, "<p>for the startup</p>", startup_id=startup).json()["id"]
    unrelated = write_post(colleague_client, "<p>personal</p>").json()["id"]
    follow(reader_client, "startup", startup)
    assert feed_ids(reader_client) == [posted]
    assert unrelated not in feed_ids(reader_client)


def test_unfollowing_removes_their_posts_from_the_following_feed(
    reader_client, author, author_client
):
    write_post(author_client)
    follow(reader_client, "member", author.pk)
    assert len(feed_ids(reader_client)) == 1
    unfollow(reader_client, "member", author.pk)
    assert feed_ids(reader_client) == []


def test_the_following_feed_honours_filters_sorting_and_pages(reader_client, author, author_client):
    follow(reader_client, "member", author.pk)
    ids = [write_post(author_client, f"<p>{i}</p>", "win").json()["id"] for i in range(4)]
    write_post(author_client, "<p>other</p>", "question")
    assert feed_ids(reader_client, category="win") == ids[::-1]
    assert feed_ids(reader_client, category="win", sort="engaged") == ids[::-1]
    page = reader_client.get(POSTS, {"scope": "following", "limit": 2, "category": "win"}).json()
    assert len(page["results"]) == 2 and page["next_cursor"]
    assert "pinned" not in page


def test_hidden_removed_and_suspended_posts_stay_out_of_the_following_feed(
    reader_client, author, author_client
):
    from apps.feed.models import Post

    follow(reader_client, "member", author.pk)
    hidden = write_post(author_client).json()["id"]
    removed = write_post(author_client).json()["id"]
    kept = write_post(author_client).json()["id"]
    Post.objects.filter(pk=hidden).update(hidden_at="2026-01-01T00:00:00Z")
    author_client.delete(f"{POSTS}/{removed}")
    assert feed_ids(reader_client) == [kept]
    User.objects.filter(pk=author.pk).update(status="suspended")
    assert feed_ids(reader_client) == []


def test_each_members_following_feed_is_their_own(reader_client, third, author, author_client):
    write_post(author_client)
    follow(reader_client, "member", author.pk)
    assert len(feed_ids(reader_client)) == 1
    assert feed_ids(third[1]) == []


# --- the follow flag on cards ---


def test_posts_and_comments_say_whether_you_follow_the_author(reader_client, author, author_client):
    post = write_post(author_client).json()["id"]
    before = reader_client.get(f"{POSTS}/{post}").json()
    assert before["author"]["following"] is False
    follow(reader_client, "member", author.pk)
    assert reader_client.get(f"{POSTS}/{post}").json()["author"]["following"] is True
    reader_client.post(f"{POSTS}/{post}/comments", {"body": "hi"}, format="json")
    author_client.post(f"{POSTS}/{post}/comments", {"body": "mine"}, format="json")
    comments = reader_client.get(f"{POSTS}/{post}/comments").json()["results"]
    flags = {c["author"]["id"]: c["author"]["following"] for c in comments}
    assert flags[str(author.pk)] is True


def test_a_startup_card_says_whether_you_follow_it(reader_client, author_client, startup):
    post = write_post(author_client, startup_id=startup).json()["id"]
    assert reader_client.get(f"{POSTS}/{post}").json()["startup"]["following"] is False
    follow(reader_client, "startup", startup)
    assert reader_client.get(f"{POSTS}/{post}").json()["startup"]["following"] is True
