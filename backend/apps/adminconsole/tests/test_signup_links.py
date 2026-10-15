import pytest

from apps.accounts.tests.helpers import REGISTER_URL, registration_payload
from apps.profiles.models import FounderProfile
from apps.startups.models import Startup

pytestmark = pytest.mark.django_db


def test_links_typed_without_https_are_completed(api_client, run_outbox):
    payload = registration_payload()
    payload["profile"]["linkedin_url"] = "linkedin.com/in/ada-founder"
    payload["startup"]["website_url"] = "http://adapay.example.com"
    assert api_client.post(REGISTER_URL, payload, format="json").status_code in (201, 202)
    run_outbox()
    profile = FounderProfile.objects.get(user__email=payload["email"])
    assert profile.linkedin_url == "https://linkedin.com/in/ada-founder"
    assert Startup.objects.get(owner__email=payload["email"]).website_url == (
        "https://adapay.example.com"
    )
