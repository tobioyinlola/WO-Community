import pytest
from django.utils import timezone


def active(make_user, email, **fields):
    return make_user(
        email=email, approved_at=timezone.now(), email_verified_at=timezone.now(), **fields
    )


def application_body(**overrides):
    data = {
        "expertise": ["Fundraising", "Go-to-market"],
        "years_experience": 12,
        "current_role": "Partner",
        "company": "Savannah Capital",
        "linkedin_url": "https://www.linkedin.com/in/ada-obi",
        "industries": ["fintech"],
        "stages": ["pre-seed", "seed"],
        "languages": ["en", "fr"],
        "timezone": "Africa/Lagos",
        "weekly_hours": 4,
        "availability_note": "Evenings",
        "motivation": "I have raised three rounds and want to help founders.",
        "accept_conduct": True,
    }
    data.update(overrides)
    return data


@pytest.fixture
def applicant(make_user):
    return active(make_user, "applicant@example.com")


@pytest.fixture
def applicant_client(applicant, client_for):
    return client_for(applicant)


@pytest.fixture
def other(make_user):
    return active(make_user, "other@example.com")


@pytest.fixture
def other_client(other, client_for):
    return client_for(other)


@pytest.fixture
def admin(make_user):
    return make_user(roles=("community_admin",), email="admin@example.com")


@pytest.fixture
def as_admin(admin, client_for):
    return client_for(admin, mfa_age=5)


@pytest.fixture
def editor_client(make_user, client_for):
    return client_for(make_user(roles=("content_editor",), email="editor@example.com"), mfa_age=5)


@pytest.fixture
def mentor(applicant, applicant_client, as_admin):
    """The applicant, approved."""
    created = applicant_client.post(
        "/api/v1/mentor-applications", application_body(), format="json"
    )
    assert created.status_code == 201, created.content
    done = as_admin.post(
        f"/api/v1/admin/mentor-applications/{created.json()['id']}/decision",
        {"decision": "approve"},
        format="json",
    )
    assert done.status_code == 200, done.content
    return applicant
