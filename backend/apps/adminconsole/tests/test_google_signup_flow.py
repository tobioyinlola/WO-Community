import pytest

from apps.accounts.models import User
from apps.accounts.tests.helpers import registration_payload

pytestmark = pytest.mark.django_db

URL = "/api/v1/auth/google"
EMAIL = "ada@example.com"


def test_the_sign_up_details_reach_the_profile_and_startup(api_client, run_outbox):
    from apps.profiles.models import FounderProfile
    from apps.startups.models import Startup

    api_client.post(
        URL,
        {
            "id_token": f"fake|g-1|{EMAIL}|1|Ada Founder",
            "registration": {
                "accepted_terms": True,
                "accepted_privacy": True,
                "accepted_conduct": True,
                "profile": registration_payload()["profile"],
                "startup": registration_payload()["startup"],
            },
        },
    )
    run_outbox()
    user = User.objects.get(email=EMAIL)
    assert FounderProfile.objects.get(user_id=user.pk).full_name == "Ada Founder"
    assert Startup.objects.filter(owner_id=user.pk, name="Ada Pay").exists()
