import pytest
from django.utils import timezone

from apps.accounts import services as accounts
from apps.campaigns import render, services
from apps.campaigns.models import Segment


def subscriber(make_user, email, *, consent=True, **fields):
    user = make_user(
        email=email, approved_at=timezone.now(), email_verified_at=timezone.now(), **fields
    )
    accounts.set_marketing_consent(user.pk, consent)
    return user


def set_profile(user, **fields):
    from apps.profiles.models import FounderProfile
    from apps.profiles.services import get_or_create_profile

    profile = get_or_create_profile(user.pk)
    FounderProfile.objects.filter(pk=profile.pk).update(**fields)


BLOCKS = [
    {"type": "heading", "text": "Hello {{first_name}}", "level": 1},
    {"type": "paragraph", "html": "<p>News for <strong>founders</strong>, {{first_name}}.</p>"},
    {"type": "button", "label": "Read more", "url": "https://wocommunity.example.com/news"},
    {"type": "divider"},
]


@pytest.fixture
def admin(make_user):
    return make_user(roles=("community_admin",), email="admin@example.com")


@pytest.fixture
def everyone(db):
    return Segment.objects.create(name="Everyone", definition={})


def make_campaign(admin, segment, **overrides):
    data = {"name": "October news", "subject": "News for you, {{first_name}}", "blocks": BLOCKS}
    data.update(overrides)
    campaign = services.create_campaign(actor=admin, data=data)
    campaign.segment = segment
    campaign.save()
    return campaign


def blocks_for(admin):
    return render.clean_blocks(BLOCKS, owner_id=admin.pk)
