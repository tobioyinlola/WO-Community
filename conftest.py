import re
import time
from collections.abc import Callable
from unittest import mock

import pytest
from celery import current_app
from django.core.cache import cache
from django.db import connection
from rest_framework.test import APIClient

from apps.accounts import tokens
from apps.accounts.models import User
from apps.accounts.tests.factories import UserFactory, UserRoleFactory
from apps.core import outbox
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
def client_for() -> Callable[..., APIClient]:
    """A client holding an access token for ``user``.

    ``mfa_age`` is how many seconds ago the user passed an MFA check; leave it
    out to model a session that never did.
    """

    def build(user: User | None = None, *, mfa_age: float | None = None) -> APIClient:
        client = APIClient()
        if user is not None:
            mfa_at = None if mfa_age is None else time.time() - mfa_age
            token = tokens.issue_access_token(user, mfa_at=mfa_at)
            client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
        return client

    return build


@pytest.fixture
def api_client() -> APIClient:
    return APIClient()


@pytest.fixture
def run_outbox() -> Callable[[], int]:
    """Publish pending outbox events and run their handlers inline."""

    def run() -> int:
        def send_task(name: str, args: list[str], queue: str) -> None:
            current_app.tasks[name].apply(args=args, throw=True)

        with mock.patch("apps.core.outbox.current_app.send_task", side_effect=send_task):
            return outbox.dispatch_pending()

    return run


@pytest.fixture
def last_token() -> Callable[[], str]:
    """The token in the link of the most recent email."""

    def find() -> str:
        match = re.search(r"token=([\w-]+)", FakeEmailAdapter.sent[-1].text_body)
        assert match, "no token link in the last email"
        return match.group(1)

    return find


@pytest.fixture
def sent_emails() -> list:
    """Messages the fake email adapter has accepted in this test."""
    return FakeEmailAdapter.sent


@pytest.fixture
def truncate_audit(transactional_db: None):
    """Transactional tests commit audit rows, and the table refuses DELETE.

    Django's flush skips unmanaged tables, so empty it explicitly afterwards.
    """
    yield
    with connection.cursor() as cursor:
        cursor.execute("TRUNCATE audit_auditlog")
