import json
import uuid

import pytest

from apps.analytics.models import AnalyticsEvent
from apps.feed.models import Post, PostImage
from apps.feed.tests.conftest import POSTS, post_url, write_post
from apps.startups.tests.conftest import STARTUPS, new_startup_body

pytestmark = pytest.mark.django_db


# --- writing a post ---


def test_a_member_can_post_and_read_it_back(author_client, author):
    response = write_post(author_client, "<p>Launching <em>today</em></p>", "win")
    assert response.status_code == 201
    body = response.json()
    assert body["category"] == "win" and body["body"] == "<p>Launching <em>today</em></p>"
    assert body["mine"] is True and body["author"]["id"] == str(author.pk)
    assert body["comment_count"] == 0 and body["reactions"] == {}
    assert response["ETag"]
    assert author_client.get(post_url(body["id"])).json()["id"] == body["id"]


def test_creating_a_post_records_an_analytics_event(author_client, author):
    write_post(author_client, category="question")
    [event] = AnalyticsEvent.objects.filter(name="post_created")
    assert event.actor_id == author.pk and event.properties == {"category": "question"}


def test_the_post_remembers_the_authors_country(author_client):
    from apps.profiles.tests.conftest import FULL

    author_client.patch(
        "/api/v1/me/profile", FULL, HTTP_IF_MATCH=author_client.get("/api/v1/me/profile")["ETag"]
    )
    assert write_post(author_client).json()["country"] == "NG"


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"category": "update"},
        {"category": "gossip", "body": "x"},
        {"category": "update", "body": ""},
        {"category": "update", "body": "   "},
        {"category": "update", "body": "<p></p>"},
        {"category": "update", "body": "<script>alert(1)</script>"},
        {"category": "update", "body": "x" * 3001},
        {"category": "update", "body": "x" * 20_001},
        {"category": "update", "body": "ok", "extra": 1},
        {"category": "update", "body": "ok", "images": [{}]},
        {"category": "update", "body": "ok", "images": [{"upload_id": str(uuid.uuid4())}] * 11},
        {"category": "update", "body": "ok", "mentions": [str(uuid.uuid4())] * 21},
    ],
)
def test_invalid_posts_are_refused(author_client, body):
    assert author_client.post(POSTS, body, format="json").status_code == 400
    assert Post.objects.count() == 0


# --- rich text is cleaned, not trusted ---


@pytest.mark.parametrize(
    "dirty, expected_absent",
    [
        ("<p>hi</p><script>alert(1)</script>", "<script"),
        ('<p onclick="x()">hi</p>', "onclick"),
        ('<a href="javascript:alert(1)">click</a>', "javascript:"),
        ('<img src=x onerror="alert(1)">hi', "<img"),
        ('<iframe src="https://evil.example"></iframe>hi', "<iframe"),
        ('<p style="color:red">hi</p>', "style="),
        ("<h1>big</h1>hi", "<h1"),
        ('<a href="data:text/html;base64,AAAA">x</a>hi', "data:"),
        ("<svg onload=alert(1)>hi", "<svg"),
    ],
)
def test_dangerous_markup_is_removed(author_client, dirty, expected_absent):
    response = write_post(author_client, dirty)
    assert response.status_code == 201, dirty
    assert expected_absent not in response.json()["body"]


def test_allowed_formatting_survives_and_links_get_safe_attributes(author_client):
    html = (
        "<h2>Title</h2><p>a <strong>b</strong> <em>c</em></p><ul><li>one</li></ul>"
        '<blockquote>q</blockquote><a href="https://example.com/x">link</a>'
    )
    body = write_post(author_client, html).json()["body"]
    for part in (
        "<h2>Title</h2>",
        "<strong>b</strong>",
        "<li>one</li>",
        "<blockquote>q</blockquote>",
    ):
        assert part in body
    assert 'href="https://example.com/x"' in body
    assert "noopener" in body and "nofollow" in body


# --- reading the feed ---


def test_the_feed_shows_newest_first(author_client, reader_client):
    ids = [write_post(author_client, f"<p>post {i}</p>").json()["id"] for i in range(3)]
    results = reader_client.get(POSTS).json()["results"]
    assert [p["id"] for p in results] == ids[::-1]


def test_pagination_walks_every_post_once(author_client, reader_client):
    ids = [write_post(author_client, f"<p>post {i}</p>").json()["id"] for i in range(7)]
    seen, cursor = [], ""
    while True:
        page = reader_client.get(POSTS, {"limit": 3, "cursor": cursor}).json()
        seen += [p["id"] for p in page["results"]]
        cursor = page["next_cursor"]
        if not cursor:
            break
    assert seen == ids[::-1]


def test_filtering_by_category_and_country(author_client, reader_client):
    write_post(author_client, "<p>a</p>", "win")
    write_post(author_client, "<p>b</p>", "question")
    wins = reader_client.get(POSTS, {"category": "win"}).json()["results"]
    assert [p["category"] for p in wins] == ["win"]
    assert reader_client.get(POSTS, {"country": "ke"}).json()["results"] == []
    Post.objects.update(country="KE")
    assert len(reader_client.get(POSTS, {"country": "ke"}).json()["results"]) == 2


def test_most_engaged_comes_first_when_asked(author_client, reader_client):
    quiet = write_post(author_client, "<p>quiet</p>").json()["id"]
    busy = write_post(author_client, "<p>busy</p>").json()["id"]
    newest = write_post(author_client, "<p>newest</p>").json()["id"]
    reader_client.post(f"{POSTS}/{busy}/reactions", {"kind": "like"})
    ids = [p["id"] for p in reader_client.get(POSTS, {"sort": "engaged"}).json()["results"]]
    assert ids == [busy, newest, quiet]


def test_mine_lists_only_my_posts(author_client, reader_client):
    write_post(author_client, "<p>mine</p>")
    write_post(reader_client, "<p>theirs</p>")
    mine = author_client.get(POSTS, {"scope": "mine"}).json()["results"]
    assert [p["mine"] for p in mine] == [True]
    assert "pinned" not in author_client.get(POSTS, {"scope": "mine"}).json()


@pytest.mark.parametrize(
    "params",
    [
        {"sort": "random"},
        {"scope": "everyone"},
        {"category": "gossip"},
        {"country": "NGA"},
        {"limit": 0},
        {"limit": 51},
        {"cursor": "garbage"},
        {"extra": 1},
    ],
)
def test_bad_feed_queries_are_refused(reader_client, params):
    assert reader_client.get(POSTS, params).status_code == 400


def test_a_cursor_from_another_sort_is_refused(author_client, reader_client):
    for i in range(3):
        write_post(author_client, f"<p>{i}</p>")
    cursor = reader_client.get(POSTS, {"limit": 1}).json()["next_cursor"]
    assert (
        reader_client.get(POSTS, {"limit": 1, "sort": "engaged", "cursor": cursor}).status_code
        == 400
    )


def test_feed_responses_are_not_cached(reader_client):
    assert reader_client.get(POSTS)["Cache-Control"] == "private, no-store"


# --- who the feed hides ---


def test_posts_of_suspended_or_removed_authors_disappear_at_once(
    author_client, reader_client, author
):
    from apps.accounts.models import User

    post = write_post(author_client).json()["id"]
    User.objects.filter(pk=author.pk).update(status="suspended")
    assert reader_client.get(POSTS).json()["results"] == []
    assert reader_client.get(post_url(post)).status_code == 404


def test_an_author_who_hides_their_basics_appears_anonymously(author_client, reader_client):
    write_post(author_client)
    author_client.patch("/api/v1/me/visibility", {"basics": "private"})
    author_card = reader_client.get(POSTS).json()["results"][0]["author"]
    assert author_card["name"] == "Community member" and author_card["slug"] is None
    own_card = author_client.get(POSTS).json()["results"][0]["author"]
    assert own_card["name"] != "Community member"


def test_the_author_card_shows_name_and_headline(author_client, reader_client):
    author_client.patch(
        "/api/v1/me/profile",
        {"full_name": "Ada Obi", "headline": "Builds things"},
        HTTP_IF_MATCH=author_client.get("/api/v1/me/profile")["ETag"],
    )
    write_post(author_client)
    card = reader_client.get(POSTS).json()["results"][0]["author"]
    assert (card["name"], card["headline"]) == ("Ada Obi", "Builds things")


# --- access control ---


def test_the_feed_is_for_active_members_only(api_client, make_user, client_for):
    assert api_client.get(POSTS).status_code == 401
    assert api_client.post(POSTS, {"category": "update", "body": "x"}).status_code == 401
    pending = make_user(email="p@example.com", status="pending")
    pending_client = client_for(pending)
    assert pending_client.get(POSTS).status_code == 403
    assert write_post(pending_client).status_code == 403


def test_a_missing_post_is_404(reader_client):
    assert reader_client.get(post_url(uuid.uuid4())).status_code == 404


# --- editing and deleting ---


def edit(client, post, body, etag=None):
    return client.patch(
        post_url(post),
        body,
        format="json",
        HTTP_IF_MATCH=etag or client.get(post_url(post))["ETag"],
    )


def test_the_author_can_edit_and_it_is_marked_edited(author_client, post_id):
    response = edit(author_client, post_id, {"body": "<p>Changed</p>", "category": "resource"})
    assert response.status_code == 200
    body = response.json()
    assert body["body"] == "<p>Changed</p>" and body["category"] == "resource"
    assert body["edited_at"] is not None


def test_editing_needs_the_current_etag(author_client, post_id):
    url = post_url(post_id)
    assert author_client.patch(url, {"body": "x"}, format="json").status_code == 428
    stale = author_client.get(url)["ETag"]
    edit(author_client, post_id, {"body": "first"})
    assert (
        author_client.patch(url, {"body": "second"}, format="json", HTTP_IF_MATCH=stale).status_code
        == 412
    )


def test_reactions_do_not_invalidate_the_etag(author_client, reader_client, post_id):
    etag = author_client.get(post_url(post_id))["ETag"]
    reader_client.post(f"{POSTS}/{post_id}/reactions", {"kind": "like"})
    assert edit(author_client, post_id, {"body": "still fine"}, etag=etag).status_code == 200


def test_edits_are_cleaned_and_validated_like_new_posts(author_client, post_id):
    assert (
        "script"
        not in edit(author_client, post_id, {"body": "<script>x</script>hi"}).json()["body"]
    )
    assert edit(author_client, post_id, {"body": "<p></p>"}).status_code == 400
    assert edit(author_client, post_id, {"category": "gossip"}).status_code == 400
    assert edit(author_client, post_id, {"author": "x"}).status_code == 400


def test_nobody_else_can_edit_or_delete_a_post(reader_client, post_id):
    etag = reader_client.get(post_url(post_id))["ETag"]
    assert (
        reader_client.patch(
            post_url(post_id), {"body": "hijack"}, format="json", HTTP_IF_MATCH=etag
        ).status_code
        == 404
    )
    assert reader_client.delete(post_url(post_id)).status_code == 404
    assert Post.objects.get(pk=post_id).deleted_at is None


def test_deleting_removes_the_post_from_everything(author_client, reader_client, post_id):
    assert author_client.delete(post_url(post_id)).status_code == 204
    assert reader_client.get(post_url(post_id)).status_code == 404
    assert author_client.get(post_url(post_id)).status_code == 404
    assert reader_client.get(POSTS).json()["results"] == []
    assert Post.objects.get(pk=post_id).deleted_at is not None  # kept for moderation recovery
    assert author_client.delete(post_url(post_id)).status_code == 404


# --- images ---


def test_a_post_can_carry_images_in_order(author_client, author, ready_upload):
    first = ready_upload(author, "post_image")
    second = ready_upload(author, "post_image")
    response = write_post(
        author_client,
        images=[
            {"upload_id": str(second.pk), "alt": "second shot"},
            {"upload_id": str(first.pk)},
        ],
    )
    assert response.status_code == 201, response.content
    images = response.json()["images"]
    assert [i["alt"] for i in images] == ["second shot", ""]
    assert images[0]["urls"]["large"].endswith("/large.webp")


def test_images_can_be_kept_reordered_added_and_removed(author_client, author, ready_upload):
    a, b = ready_upload(author, "post_image"), ready_upload(author, "post_image")
    created = write_post(
        author_client, images=[{"upload_id": str(a.pk)}, {"upload_id": str(b.pk)}]
    ).json()
    first, second = (i["id"] for i in created["images"])
    c = ready_upload(author, "post_image")
    changed = edit(
        author_client,
        created["id"],
        {"images": [{"upload_id": str(c.pk)}, {"image_id": second, "alt": "kept"}]},
    ).json()
    assert [i["alt"] for i in changed["images"]] == ["", "kept"]
    assert changed["images"][1]["id"] == second
    assert not PostImage.objects.filter(pk=first).exists()
    cleared = edit(author_client, created["id"], {"images": []}).json()
    assert cleared["images"] == []


def test_an_upload_for_something_else_or_someone_elses_cannot_be_used(
    author_client, reader, ready_upload, author
):
    wrong_purpose = ready_upload(author, "profile_photo")
    assert (
        write_post(author_client, images=[{"upload_id": str(wrong_purpose.pk)}]).status_code == 400
    )
    theirs = ready_upload(reader, "post_image")
    assert write_post(author_client, images=[{"upload_id": str(theirs.pk)}]).status_code == 400
    assert Post.objects.count() == 0


def test_an_upload_cannot_be_used_twice(author_client, author, ready_upload):
    upload = ready_upload(author, "post_image")
    assert write_post(author_client, images=[{"upload_id": str(upload.pk)}]).status_code == 201
    assert write_post(author_client, images=[{"upload_id": str(upload.pk)}]).status_code == 400
    twice = ready_upload(author, "post_image")
    both = [{"upload_id": str(twice.pk)}] * 2
    assert write_post(author_client, images=both).status_code == 400


def test_a_bad_image_leaves_no_post_behind(author_client, author, ready_upload):
    good = ready_upload(author, "post_image")
    response = write_post(
        author_client,
        images=[{"upload_id": str(good.pk)}, {"upload_id": str(uuid.uuid4())}],
    )
    assert response.status_code == 400
    assert Post.objects.count() == 0
    good.refresh_from_db()
    assert good.claimed_at is None  # the failed attempt did not use up the upload


def test_unknown_image_ids_are_refused(author_client, post_id):
    unknown = str(uuid.uuid4())
    assert edit(author_client, post_id, {"images": [{"image_id": unknown}]}).status_code == 400


# --- posting for a startup ---


def test_a_member_can_post_for_their_startup_but_not_someone_elses(author_client, reader_client):
    startup = author_client.post(STARTUPS, new_startup_body()).json()["id"]
    posted = write_post(author_client, startup_id=startup)
    assert posted.status_code == 201
    assert posted.json()["startup"]["id"] == startup
    assert write_post(reader_client, startup_id=startup).status_code == 400


# --- limits ---


def test_a_member_has_a_daily_post_allowance(author_client, settings):
    settings.FEED_POSTS_PER_DAY = 2
    assert [write_post(author_client).status_code for _ in range(3)] == [201, 201, 429]


def test_the_allowance_is_per_member(author_client, reader_client, settings):
    settings.FEED_POSTS_PER_DAY = 1
    write_post(author_client)
    assert write_post(reader_client).status_code == 201


def test_the_stored_text_matches_the_markup(author_client):
    write_post(author_client, "<p>Hello <strong>world</strong></p><p>again</p>")
    assert Post.objects.get().body_text == "Hello world again"
    assert json.dumps(Post.objects.get().reaction_counts) == "{}"


def test_member_only_content_never_reaches_visitors(api_client, post_id):
    assert api_client.get(post_url(post_id)).status_code == 401
