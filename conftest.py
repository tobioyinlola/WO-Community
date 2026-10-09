from collections.abc import Callable

import pytest
from django.core.cache import cache
from rest_framework.test import APIClient

from apps.accounts import tokens
from apps.accounts.models import User
from apps.accounts.tests.factories import UserFactory, UserRoleFactory
from apps.integrations.email.fake import FakeEmailAdapter


@pytest.fixture(autouse=True)
def _clean_state() -> None:
    cache.clear()
    FakeEmailAdapter.reset()


@pytest.fixture
def make_user(db: None) -> Callable[..., User]:
    def build(roles: tuple[str, ...] = ("member",), **fields: object) -> User:
        user = UserFactory(**fields)
        for role in roles:
            UserRoleFactory(user=user, role=role)
        return user

    return build


@pytest.fixture
def client_for() -> Callable[[User | None], APIClient]:
    def build(user: User | None = None) -> APIClient:
        client = APIClient()
        if user is not None:
            client.credentials(HTTP_AUTHORIZATION=f"Bearer {tokens.issue_access_token(user)}")
        return client

    return build


@pytest.fixture
def api_client() -> APIClient:
    return APIClient()
