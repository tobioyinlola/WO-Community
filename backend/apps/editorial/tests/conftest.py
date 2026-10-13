from datetime import timedelta

import pytest
from django.utils import timezone

from apps.editorial import services
from apps.editorial.models import EditorialItem

ITEMS = "/api/v1/editorial"


def active(make_user, email, **fields):
    return make_user(
        email=email, approved_at=timezone.now(), email_verified_at=timezone.now(), **fields
    )


@pytest.fixture
def editor(make_user):
    return make_user(roles=("content_editor",), email="editor@example.com")


@pytest.fixture
def member(make_user):
    return active(make_user, "member@example.com")


@pytest.fixture
def member_client(member, client_for):
    return client_for(member)


@pytest.fixture
def other(make_user):
    return active(make_user, "other@example.com")


@pytest.fixture
def other_client(other, client_for):
    return client_for(other)


def story(editor, **overrides):
    data = {
        "type": "news",
        "title": "Community raises a milestone",
        "body": "<p>A <strong>big</strong> day for the community.</p>",
    }
    data.update(overrides)
    item = services.create_item(actor=editor, data=data)
    if data.get("_draft"):
        return item
    return services.publish_now(actor=editor, item_id=item.pk)


@pytest.fixture
def published(editor) -> EditorialItem:
    return story(editor)


def later(minutes=30):
    return timezone.now() + timedelta(minutes=minutes)
