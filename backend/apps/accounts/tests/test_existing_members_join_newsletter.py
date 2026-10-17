import importlib

import pytest
from django.apps import apps as django_apps
from django.utils import timezone

from apps.accounts import services as accounts
from apps.accounts.models import ConsentRecord
from apps.notifications import services as notifications

pytestmark = pytest.mark.django_db

migration = importlib.import_module(
    "apps.accounts.migrations.0011_existing_members_join_newsletter"
)


def active(make_user, email, **fields):
    return make_user(email=email, status="active", email_verified_at=timezone.now(), **fields)


def said(user, granted):
    ConsentRecord.objects.create(user=user, document="marketing", version="1", granted=granted)


def test_existing_members_join_unless_they_chose_otherwise(make_user):
    left_it_unticked = active(make_user, "unticked@example.com")
    said(left_it_unticked, False)
    never_asked = active(make_user, "never@example.com")
    already_in = active(make_user, "already@example.com")
    said(already_in, True)
    changed_their_mind = active(make_user, "withdrew@example.com")
    said(changed_their_mind, True)
    said(changed_their_mind, False)
    unsubscribed = active(make_user, "unsubscribed@example.com")
    said(unsubscribed, False)
    notifications.suppress("Unsubscribed@example.com", "unsubscribed")
    rejected = make_user(email="rejected@example.com", status="rejected")
    said(rejected, False)

    migration.join(django_apps, None)

    assert accounts.has_marketing_consent(left_it_unticked.pk)
    assert accounts.has_marketing_consent(never_asked.pk)
    assert ConsentRecord.objects.filter(user=already_in, granted=True).count() == 1
    assert not accounts.has_marketing_consent(changed_their_mind.pk)
    assert not accounts.has_marketing_consent(unsubscribed.pk)
    assert not ConsentRecord.objects.filter(user=rejected, granted=True).exists()


def test_running_it_again_adds_nothing(make_user):
    member = active(make_user, "once@example.com")
    said(member, False)
    migration.join(django_apps, None)
    migration.join(django_apps, None)
    assert ConsentRecord.objects.filter(user=member, granted=True).count() == 1
