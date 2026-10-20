import importlib

import pytest
from django.apps import apps as django_apps
from django.utils import timezone

from apps.core.models import OutboxEvent
from apps.feed.models import Comment, LinkPreview, Post, PostLink

pytestmark = pytest.mark.django_db

backfill = importlib.import_module("apps.feed.migrations.0009_link_existing_posts")


@pytest.fixture
def author(make_user):
    return make_user(
        email="old@example.com", approved_at=timezone.now(), email_verified_at=timezone.now()
    )


def old_post(author, body):
    return Post.objects.create(author=author, category="update", body=body, body_text=body)


def test_old_posts_and_comments_get_links_and_cards(author):
    post = old_post(author, "<p>Read https://example.com/a and https://example.org/b now</p>")
    plain = old_post(author, "<p>No address here</p>")
    comment = Comment.objects.create(
        post=plain, author=author, body="<p>Also https://example.com/c</p>"
    )
    backfill.link_up(django_apps, None)

    post.refresh_from_db()
    assert post.body.count("<a ") == 2 and 'href="https://example.com/a"' in post.body
    assert PostLink.objects.filter(post=post).count() == 2
    assert LinkPreview.objects.filter(status="pending").count() == 2
    assert OutboxEvent.objects.filter(topic="feed.link_preview_requested").count() == 2
    comment.refresh_from_db()
    assert 'href="https://example.com/c"' in comment.body
    assert PostLink.objects.filter(post=plain).count() == 0


def test_running_it_again_changes_nothing(author):
    old_post(author, "<p>https://example.com/a</p>")
    backfill.link_up(django_apps, None)
    before = (PostLink.objects.count(), LinkPreview.objects.count(), OutboxEvent.objects.count())
    backfill.link_up(django_apps, None)
    assert (
        PostLink.objects.count(),
        LinkPreview.objects.count(),
        OutboxEvent.objects.count(),
    ) == before


def test_a_shared_address_is_asked_for_once(author):
    old_post(author, "<p>https://example.com/same</p>")
    old_post(author, "<p>https://example.com/same</p>")
    backfill.link_up(django_apps, None)
    assert LinkPreview.objects.count() == 1
    assert OutboxEvent.objects.filter(topic="feed.link_preview_requested").count() == 1
    assert PostLink.objects.count() == 2
