"""Fixtures shared by every toolkit test. Nothing here touches a real service."""

from collections.abc import Callable

import pytest
from django.utils import timezone

from apps.toolkit.ai.providers.fake import FakeLLMProvider
from apps.toolkit.ai.research.fake import FakeResearchProvider
from apps.toolkit.jobs import services as jobs
from apps.toolkit.jobs.models import AIJob
from apps.toolkit.testing import BASE, FULL_PROFILE  # noqa: F401


@pytest.fixture(autouse=True)
def _reset_ai():
    FakeLLMProvider.reset()
    FakeResearchProvider.reset()


@pytest.fixture
def member(make_user):
    return make_user(
        email="founder@example.com", approved_at=timezone.now(), email_verified_at=timezone.now()
    )


@pytest.fixture
def client(member, client_for):
    return client_for(member)


@pytest.fixture
def other(make_user):
    return make_user(
        email="rival@example.com", approved_at=timezone.now(), email_verified_at=timezone.now()
    )


@pytest.fixture
def other_client(other, client_for):
    return client_for(other)


@pytest.fixture
def pending_client(make_user, client_for):
    user = make_user(email="pending@example.com", status="pending")
    return client_for(user)


@pytest.fixture
def venture(client):
    response = client.post(f"{BASE}/ventures", {"name": "Mamapesa"}, format="json")
    if response.status_code != 201:
        pytest.fail(str(response.content))
    return response.json()


@pytest.fixture
def full_venture(client, venture):
    response = client.patch(
        f"{BASE}/ventures/{venture['id']}/profile", {"fields": FULL_PROFILE}, format="json"
    )
    if response.status_code != 200:
        pytest.fail(str(response.content))
    return venture


@pytest.fixture
def run_jobs(django_capture_on_commit_callbacks) -> Callable[[], None]:
    """Lets queued jobs run now, in the test's own process."""

    def run() -> None:
        with django_capture_on_commit_callbacks(execute=True):
            pass
        for job in AIJob.objects.filter(status="queued").order_by("created_at"):
            jobs.run(job.pk)

    return run
