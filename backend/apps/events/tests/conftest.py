from datetime import timedelta

import pytest
from django.utils import timezone

from apps.events import services

EVENTS = "/api/v1/events"


def active(make_user, email, **fields):
    return make_user(
        email=email, approved_at=timezone.now(), email_verified_at=timezone.now(), **fields
    )


@pytest.fixture
def admin(make_user):
    return make_user(roles=("community_admin",), email="admin@example.com")


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


def event_data(**overrides):
    start = timezone.now() + timedelta(days=3)
    data = {
        "type": "workshop",
        "title": "Pitch practice workshop",
        "description": "<p>Practise your <strong>pitch</strong> with peers.</p>",
        "starts_at": start,
        "ends_at": start + timedelta(hours=2),
        "timezone": "Africa/Lagos",
        "location": "Yaba, Lagos",
        "link": "https://meet.example.com/pitch",
    }
    data.update(overrides)
    return data


def make_event(admin, *, publish=True, **overrides):
    event = services.create_event(actor=admin, data=event_data(**overrides))
    if publish:
        services.publish(actor=admin, event_id=event.pk)
        event.refresh_from_db()
    return event


@pytest.fixture
def event(admin):
    return make_event(admin)
