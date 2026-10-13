import pytest


@pytest.fixture
def policy_urls(settings):
    """Route requests to the throwaway views used to test the policy framework."""
    settings.ROOT_URLCONF = "apps.core.tests.urls"
