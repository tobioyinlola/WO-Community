from datetime import timedelta

import pytest
from django.utils import timezone

from apps.feed import links
from apps.feed.models import LinkPreview, PostLink
from apps.feed.tests.conftest import POSTS, post_url, write_post
from apps.integrations.linkpreview import FetchFailed, FetchRejected, Preview
from apps.integrations.linkpreview.fake import FakeFetcher
from apps.integrations.malware.fake import EICAR
from apps.uploads.tests.helpers import image_bytes

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _reset_fetcher():
    FakeFetcher.reset()


def link(url, text="read this"):
    return f'<p><a href="{url}">{text}</a></p>'


def previews(client, post_id):
    return client.get(post_url(post_id)).json()["previews"]


def create(client, *urls):
    return write_post(client, "".join(link(u) for u in urls)).json()["id"]


# --- finding the links ---


def test_a_post_with_a_link_gets_a_preview_after_a_worker_runs(
    author_client, reader_client, run_outbox
):
    post = create(author_client, "https://example.com/story")
    assert previews(reader_client, post) == []  # nothing until the worker has fetched it
    assert LinkPreview.objects.get().status == "pending"
    run_outbox()
    [card] = previews(reader_client, post)
    assert card["url"] == "https://example.com/story"
    assert card["title"] == "Title of https://example.com/story"
    assert card["description"] == "A description" and card["site_name"] == "Example"
    assert card["image"] is None
    assert FakeFetcher.fetched == ["https://example.com/story"]


def test_only_the_first_two_distinct_links_are_used(author_client, run_outbox):
    post = create(
        author_client,
        "https://a.example.com/1",
        "https://a.example.com/1",
        "https://b.example.com/2",
        "https://c.example.com/3",
    )
    run_outbox()
    assert [p.preview.url for p in PostLink.objects.filter(post_id=post).order_by("position")] == [
        "https://a.example.com/1",
        "https://b.example.com/2",
    ]
    assert len(FakeFetcher.fetched) == 2


def test_fragments_are_dropped_and_other_schemes_ignored(author_client, run_outbox):
    html = (
        link("https://example.com/p#section")
        + link("mailto:someone@example.com")
        + link("javascript:alert(1)")
        + link("ftp://example.com/file")
    )
    write_post(author_client, html)
    run_outbox()
    assert FakeFetcher.fetched == ["https://example.com/p"]


@pytest.mark.parametrize(
    "url",
    [
        "http://localhost/admin",
        "http://127.0.0.1:8080/",
        "http://169.254.169.254/latest/meta-data/",
        "http://10.0.0.5/",
        "http://[::1]/",
        "http://intranet/",
        "http://db.internal/",
        "http://example.com:22/",
        "http://user:pw@example.com/",
    ],
)
def test_internal_addresses_are_never_even_queued(author_client, run_outbox, url):
    post = create(author_client, url)
    run_outbox()
    assert FakeFetcher.fetched == [] and LinkPreview.objects.count() == 0
    assert PostLink.objects.filter(post_id=post).count() == 0


def test_a_link_to_a_name_that_resolves_inside_is_stopped_by_the_fetcher(author_client, run_outbox):
    FakeFetcher.results["https://sneaky.example.com/"] = FetchRejected("blocked_address")
    post = create(author_client, "https://sneaky.example.com/")
    run_outbox()
    preview = LinkPreview.objects.get()
    assert preview.status == "failed" and preview.fail_code == "blocked_address"
    assert previews(author_client, post) == []


# --- sharing and refreshing ---


def test_the_same_address_in_two_posts_is_fetched_once(author_client, reader_client, run_outbox):
    first = create(author_client, "https://example.com/shared")
    second = create(reader_client, "https://example.com/shared")
    run_outbox()
    assert FakeFetcher.fetched == ["https://example.com/shared"]
    assert LinkPreview.objects.count() == 1
    assert len(previews(author_client, first)) == len(previews(author_client, second)) == 1


def test_a_failed_fetch_leaves_the_post_fine_and_is_tried_again_after_an_hour(
    author_client, run_outbox
):
    post = create(author_client, "https://unreachable.example.com/")
    run_outbox()
    preview = LinkPreview.objects.get()
    assert preview.status == "failed" and preview.fail_code == "unreachable"
    assert previews(author_client, post) == []
    create(author_client, "https://unreachable.example.com/")
    run_outbox()
    assert len(FakeFetcher.fetched) == 1  # too soon to try again
    LinkPreview.objects.update(fetched_at=timezone.now() - timedelta(hours=2))
    FakeFetcher.results["https://unreachable.example.com/"] = Preview(title="Back up")
    create(author_client, "https://unreachable.example.com/")
    run_outbox()
    assert LinkPreview.objects.get().status == "ready"
    assert previews(author_client, post)[0]["title"] == "Back up"


def test_a_ready_preview_is_refreshed_after_a_week_and_keeps_its_content_if_that_fails(
    author_client, run_outbox
):
    post = create(author_client, "https://example.com/news")
    run_outbox()
    LinkPreview.objects.update(fetched_at=timezone.now() - timedelta(days=8))
    FakeFetcher.results["https://example.com/news"] = FetchFailed("timeout")
    create(author_client, "https://example.com/news")
    run_outbox()
    stored = LinkPreview.objects.get()
    assert stored.status == "ready" and stored.fail_code == "timeout"
    assert previews(author_client, post)[0]["title"] == "Title of https://example.com/news"


# --- editing ---


def test_editing_the_body_replaces_the_links(author_client, run_outbox):
    post = create(author_client, "https://example.com/old")
    run_outbox()
    etag = author_client.get(post_url(post))["ETag"]
    response = author_client.patch(
        post_url(post),
        {"body": link("https://example.com/new")},
        format="json",
        HTTP_IF_MATCH=etag,
    )
    assert response.status_code == 200
    run_outbox()
    assert [c["url"] for c in previews(author_client, post)] == ["https://example.com/new"]


def test_removing_the_links_removes_the_cards(author_client, run_outbox):
    post = create(author_client, "https://example.com/old")
    run_outbox()
    etag = author_client.get(post_url(post))["ETag"]
    author_client.patch(
        post_url(post), {"body": "<p>no links now</p>"}, format="json", HTTP_IF_MATCH=etag
    )
    assert previews(author_client, post) == []


def test_the_feed_list_carries_the_cards_too(author_client, reader_client, run_outbox):
    create(author_client, "https://example.com/in-feed")
    run_outbox()
    [post] = reader_client.get(POSTS).json()["results"]
    assert post["previews"][0]["title"].endswith("in-feed")


# --- the picture ---


def test_a_picture_is_checked_and_stored_like_any_other_image(author_client, run_outbox):
    FakeFetcher.results["https://example.com/pic"] = Preview(
        title="With picture", image=image_bytes("PNG", (800, 600)), image_type="image/png"
    )
    post = create(author_client, "https://example.com/pic")
    run_outbox()
    card = previews(author_client, post)[0]
    assert card["image"]["large"].endswith("/large.webp")
    assert "link_preview" in card["image"]["large"]
    assert LinkPreview.objects.get().image_key.startswith("media/link_preview/")


@pytest.mark.parametrize(
    "bad",
    [b"not an image at all", b"<svg onload=alert(1)></svg>", b"\x89PNG\r\n\x1a\ntruncated"],
)
def test_a_bad_picture_only_costs_the_card_its_picture(author_client, run_outbox, bad):
    FakeFetcher.results["https://example.com/pic"] = Preview(
        title="Still a card", image=bad, image_type="image/png"
    )
    post = create(author_client, "https://example.com/pic")
    run_outbox()
    card = previews(author_client, post)[0]
    assert card["title"] == "Still a card" and card["image"] is None


def test_a_picture_that_the_scanner_flags_is_not_kept(author_client, run_outbox):
    FakeFetcher.results["https://example.com/pic"] = Preview(
        title="Flagged", image=image_bytes("PNG", (50, 50)) + EICAR, image_type="image/png"
    )
    post = create(author_client, "https://example.com/pic")
    run_outbox()
    assert previews(author_client, post)[0]["image"] is None


# --- housekeeping ---


def test_previews_nobody_links_to_any_more_are_purged_with_their_pictures(
    author_client, run_outbox
):
    FakeFetcher.results["https://example.com/pic"] = Preview(
        title="x", image=image_bytes("PNG", (50, 50)), image_type="image/png"
    )
    post = create(author_client, "https://example.com/pic")
    other = create(author_client, "https://example.com/kept")
    run_outbox()
    PostLink.objects.filter(post_id=post).delete()
    LinkPreview.objects.update(created_at=timezone.now() - timedelta(days=8))
    assert links.purge_unused() == 1
    assert list(LinkPreview.objects.values_list("url", flat=True)) == ["https://example.com/kept"]
    assert PostLink.objects.filter(post_id=other).count() == 1


def test_recent_unlinked_previews_are_kept(author_client, run_outbox):
    post = create(author_client, "https://example.com/new")
    run_outbox()
    PostLink.objects.filter(post_id=post).delete()
    assert links.purge_unused() == 0
