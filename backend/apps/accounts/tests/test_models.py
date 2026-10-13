import pytest
from django.db import IntegrityError, transaction

from apps.accounts.models import User
from apps.accounts.tests.factories import UserFactory, UserRoleFactory

pytestmark = pytest.mark.django_db


def test_email_is_unique_ignoring_case():
    UserFactory(email="Person@Example.com")
    with pytest.raises(IntegrityError), transaction.atomic():
        UserFactory(email="person@example.com")


def test_role_assignment_is_unique_per_user():
    user = UserFactory()
    UserRoleFactory(user=user, role="member")
    with pytest.raises(IntegrityError), transaction.atomic():
        UserRoleFactory(user=user, role="member")


def test_new_users_start_pending():
    user = User.objects.create_user("new@example.com", "a-long-test-passphrase")
    assert user.status == "pending"
    assert user.email == "new@example.com"


def test_primary_keys_are_time_ordered_uuids():
    first, second = UserFactory(), UserFactory()
    assert first.pk.version == 7
    assert first.pk < second.pk
