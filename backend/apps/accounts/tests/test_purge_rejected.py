from datetime import timedelta

import pytest
from django.utils import timezone

from apps.accounts import membership
from apps.accounts.models import User, UserStatus
from apps.audit.models import AuditLog

pytestmark = pytest.mark.django_db


def test_rejected_registrations_are_erased_after_the_retention_period(make_user, settings):
    old = make_user(email="old@example.com", status=UserStatus.REJECTED)
    recent = make_user(email="recent@example.com", status=UserStatus.REJECTED)
    suspended = make_user(email="susp@example.com", status=UserStatus.SUSPENDED)
    long_ago = timezone.now() - timedelta(days=settings.REJECTED_REGISTRATION_RETENTION_DAYS + 1)
    User.objects.filter(pk__in=[old.pk, suspended.pk]).update(status_changed_at=long_ago)
    User.objects.filter(pk=recent.pk).update(status_changed_at=timezone.now() - timedelta(days=5))
    assert membership.purge_rejected_registrations() == 1
    assert not User.objects.filter(pk=old.pk).exists()
    assert User.objects.filter(pk__in=[recent.pk, suspended.pk]).count() == 2  # only rejected
    assert membership.purge_rejected_registrations() == 0
    assert AuditLog.objects.filter(action="members.purged", target_id=str(old.pk)).exists()
