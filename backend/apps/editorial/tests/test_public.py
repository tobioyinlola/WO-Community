from datetime import timedelta

import pytest
from django.utils import timezone

from apps.editorial import services
from apps.editorial.models import EditorialItem
from apps.editorial.tests.conftest import story
from apps.integrations.cdn.fake import FakePurger

pytestmark = pytest.mark.django_db

PUBLIC = "/api/v1/public/news"


@pytest.fixture(autouse=True)
def _reset_purger():
    FakePurger.reset()


def public_story(editor, **overrides):
    item = story(editor, **overrides)
    EditorialItem.objects.filter(pk=item.pk).update(public=True)
    return item


def test_only_public_published_items_are_on_the_website(api_client, editor):
    shown = public_story(editor, title="Shown")
    story(editor, title="Members only")
    story(editor, title="Public draft", _draft=True)
    EditorialItem.objects.filter(title="Public draft").update(public=True)
    page = api_client.get(PUBLIC)
    assert [i["slug"] for i in page.json()["results"]] == [shown.slug]
    assert set(page.json()["results"][0]) == {
        "slug",
        "type",
        "title",
        "excerpt",
        "cover",
        "published_at",
    }
    assert "public" in page["Cache-Control"] and page["ETag"]
    assert api_client.get(PUBLIC, HTTP_IF_NONE_MATCH=page["ETag"]).status_code == 304


def test_the_public_list_filters_and_pages(api_client, editor):
    for i in range(3):
        public_story(editor, title=f"News {i}", type="news")
    public_story(editor, title="An award", type="award")
    assert [i["title"] for i in api_client.get(PUBLIC, {"type": "award"}).json()["results"]] == [
        "An award"
    ]
    page = api_client.get(PUBLIC, {"limit": 3}).json()
    assert len(page["results"]) == 3 and page["next_cursor"]
    rest = api_client.get(PUBLIC, {"limit": 3, "cursor": page["next_cursor"]}).json()
    assert len(rest["results"]) == 1


@pytest.mark.parametrize("params", [{"type": "x"}, {"limit": 0}, {"cursor": "x"}, {"q": "x"}])
def test_bad_public_queries_are_refused(api_client, params):
    assert api_client.get(PUBLIC, params).status_code == 400


def test_a_public_item_has_open_graph_data(api_client, editor, settings):
    item = public_story(editor, body="<p>" + "word " * 100 + "</p>")
    body = api_client.get(f"{PUBLIC}/{item.slug}").json()
    assert body["title"] == "Community raises a milestone" and "word" in body["body"]
    assert body["share_url"] == f"{settings.FRONTEND_BASE_URL}/news/{item.slug}"
    graph = body["open_graph"]
    assert (
        graph["url"] == body["share_url"] and graph["type"] == "article" and graph["image"] is None
    )
    assert len(graph["description"]) <= 200


def test_members_only_drafts_and_removed_items_are_404(api_client, editor):
    members_only = story(editor)
    draft = story(editor, _draft=True)
    EditorialItem.objects.filter(pk=draft.pk).update(public=True)
    gone = public_story(editor)
    services.remove_item(actor=editor, item_id=gone.pk)
    for item in (members_only, draft, gone):
        assert api_client.get(f"{PUBLIC}/{item.slug}").status_code == 404
    assert api_client.get(f"{PUBLIC}/no-such-item").status_code == 404


def test_no_member_details_or_comments_are_public(api_client, editor, member_client):
    item = public_story(editor)
    member_client.post(
        f"/api/v1/editorial/{item.pk}/comments", {"body": "<p>secret thought</p>"}, format="json"
    )
    text = (
        api_client.get(PUBLIC).content.decode()
        + api_client.get(f"{PUBLIC}/{item.slug}").content.decode()
    )
    assert "secret thought" not in text and "member@example.com" not in text
    assert "comment_count" not in text and "reactions" not in text


def test_public_pages_ignore_credentials(api_client, editor):
    public_story(editor)
    assert api_client.get(PUBLIC, HTTP_AUTHORIZATION="Bearer garbage").status_code == 200


def test_publishing_editing_and_taking_down_purge_the_public_pages(
    editor, django_capture_on_commit_callbacks
):
    with django_capture_on_commit_callbacks(execute=True):
        item = public_story(editor)
    assert PUBLIC in FakePurger.purged and f"{PUBLIC}/{item.slug}" in FakePurger.purged
    FakePurger.reset()
    with django_capture_on_commit_callbacks(execute=True):
        services.unpublish(actor=editor, item_id=item.pk)
    assert f"{PUBLIC}/{item.slug}" in FakePurger.purged


def test_a_scheduled_item_appears_publicly_only_after_it_goes_live(api_client, editor):
    item = story(editor, _draft=True)
    EditorialItem.objects.filter(pk=item.pk).update(public=True)
    services.schedule(actor=editor, item_id=item.pk, publish_at=timezone.now() + timedelta(hours=1))
    assert api_client.get(PUBLIC).json()["results"] == []
    EditorialItem.objects.filter(pk=item.pk).update(
        publish_at=timezone.now() - timedelta(minutes=1)
    )
    assert services.publish_due() == 1
    assert [i["slug"] for i in api_client.get(PUBLIC).json()["results"]] == [item.slug]
