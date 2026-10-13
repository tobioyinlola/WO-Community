import pytest

from apps.feed.models import BlockedDomain, LinkPreview
from apps.feed.tests.conftest import post_url, write_post
from apps.integrations.linkpreview.fake import FakeFetcher

pytestmark = pytest.mark.django_db

BLOCKED = "/api/v1/admin/blocked-domains"
PREVIEWS = "/api/v1/admin/link-previews"


@pytest.fixture(autouse=True)
def _reset_fetcher():
    FakeFetcher.reset()


@pytest.fixture
def moderator(make_user, client_for):
    return client_for(make_user(roles=("community_admin",), email="mod@example.com"), mfa_age=5)


def post_with(client, *urls):
    body = "".join(f'<p><a href="{u}">link</a></p>' for u in urls)
    return write_post(client, body).json()["id"]


def cards(client, post_id):
    return client.get(post_url(post_id)).json()["previews"]


def test_moderators_find_cards_and_see_how_widely_they_are_used(
    moderator, author_client, run_outbox
):
    post_with(author_client, "https://news.example.com/a")
    post_with(author_client, "https://other.example.org/b")
    run_outbox()
    everything = moderator.get(PREVIEWS).json()
    assert everything["count"] == 2
    found = moderator.get(PREVIEWS, {"q": "news.example"}).json()["results"]
    assert [r["domain"] for r in found] == ["news.example.com"]
    row = found[0]
    assert row["status"] == "ready" and row["posts"] == 1 and row["blocked"] is False
    assert moderator.get(PREVIEWS, {"status": "failed"}).json()["count"] == 0


def test_a_card_can_be_fetched_again(moderator, author_client, run_outbox):
    post_with(author_client, "https://news.example.com/a")
    run_outbox()
    preview = LinkPreview.objects.get()
    FakeFetcher.fetched.clear()
    response = moderator.post(f"{PREVIEWS}/{preview.pk}/refresh")
    assert response.status_code == 200 and response.json()["status"] == "pending"
    run_outbox()
    assert FakeFetcher.fetched == ["https://news.example.com/a"]
    assert LinkPreview.objects.get().status == "ready"


def test_blocking_a_site_takes_down_its_cards_at_once(
    moderator, author_client, reader_client, run_outbox
):
    post = post_with(author_client, "https://shop.evil.com/x", "https://fine.example.com/y")
    run_outbox()
    assert len(cards(reader_client, post)) == 2
    created = moderator.post(
        BLOCKED, {"domain": "https://www.EVIL.com/anything", "reason": "scam"}, format="json"
    )
    assert created.status_code == 201 and created.json()["domain"] == "evil.com"
    shown = cards(reader_client, post)
    assert [c["url"] for c in shown] == ["https://fine.example.com/y"]
    blocked = LinkPreview.objects.get(url__contains="evil.com")
    assert blocked.status == "failed" and blocked.fail_code == "blocked_domain"
    assert blocked.title == ""


def test_a_blocked_site_is_never_fetched_again(moderator, author_client, run_outbox):
    moderator.post(BLOCKED, {"domain": "evil.com"}, format="json")
    post_with(author_client, "https://evil.com/a", "https://sub.evil.com/b")
    run_outbox()
    assert FakeFetcher.fetched == []
    assert set(LinkPreview.objects.values_list("fail_code", flat=True)) == {"blocked_domain"}
    # A site that only looks similar is not caught.
    post_with(author_client, "https://notevil.com/c")
    run_outbox()
    assert FakeFetcher.fetched == ["https://notevil.com/c"]


def test_refreshing_a_blocked_site_is_refused_and_unblocking_restores_it(
    moderator, author_client, run_outbox
):
    post_with(author_client, "https://evil.com/a")
    run_outbox()
    entry = moderator.post(BLOCKED, {"domain": "evil.com"}, format="json").json()
    preview = LinkPreview.objects.get()
    assert moderator.post(f"{PREVIEWS}/{preview.pk}/refresh").status_code == 400
    assert moderator.get(PREVIEWS).json()["results"][0]["blocked"] is True
    assert moderator.delete(f"{BLOCKED}/{entry['id']}").status_code == 204
    assert not BlockedDomain.objects.exists()
    assert moderator.post(f"{PREVIEWS}/{preview.pk}/refresh").status_code == 200


def test_domains_are_checked_and_not_blocked_twice(moderator):
    assert moderator.post(BLOCKED, {"domain": "not a domain"}, format="json").status_code == 400
    assert moderator.post(BLOCKED, {"domain": "localhost"}, format="json").status_code == 400
    assert moderator.post(BLOCKED, {"domain": "evil.com"}, format="json").status_code == 201
    assert moderator.post(BLOCKED, {"domain": "EVIL.com"}, format="json").status_code == 400
    assert [d["domain"] for d in moderator.get(BLOCKED).json()] == ["evil.com"]


def test_only_moderators_can_use_these_tools(author_client, api_client):
    assert author_client.get(PREVIEWS).status_code == 403
    assert author_client.post(BLOCKED, {"domain": "evil.com"}, format="json").status_code == 403
    assert api_client.get(BLOCKED).status_code == 401
