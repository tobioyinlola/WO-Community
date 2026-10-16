import pytest

from apps.audit.models import AuditLog
from apps.editorial.models import Testimonial as Quote

pytestmark = pytest.mark.django_db

ADMIN = "/api/v1/admin/testimonials"
PUBLIC = "/api/v1/public/testimonials"
QUOTE = "WO Community introduced me to my first investor within a month."


@pytest.fixture(autouse=True)
def _start_empty():
    """The first testimonials come with a data migration; these tests start from none."""
    Quote.objects.all().delete()


@pytest.fixture
def as_editor(make_user, client_for):
    return client_for(make_user(roles=("content_editor",), email="ed@example.com"), mfa_age=5)


def add(client, **overrides):
    response = client.post(
        ADMIN, {"quote": QUOTE, "name": "Amaka Obi", "role": "Founder, Kuda Foods", **overrides}
    )
    assert response.status_code == 201, response.content
    return response.json()


def test_a_testimonial_is_drafted_then_published_once_consent_is_confirmed(as_editor, api_client):
    made = add(as_editor)
    assert made["published"] is False and api_client.get(PUBLIC).json() == []
    refused = as_editor.patch(f"{ADMIN}/{made['id']}", {"published": True})
    assert refused.status_code == 400 and "consent_confirmed" in refused.json()["errors"]
    shown = as_editor.patch(f"{ADMIN}/{made['id']}", {"published": True, "consent_confirmed": True})
    assert shown.status_code == 200 and shown.json()["published"] is True
    public = api_client.get(PUBLIC).json()
    assert public == [
        {"id": made["id"], "quote": QUOTE, "name": "Amaka Obi", "role": "Founder, Kuda Foods"}
    ]
    assert AuditLog.objects.filter(action="testimonial.updated").exists()


def test_withdrawing_consent_takes_it_off_the_website(as_editor, api_client):
    made = add(as_editor, published=True, consent_confirmed=True)
    assert len(api_client.get(PUBLIC).json()) == 1
    as_editor.patch(f"{ADMIN}/{made['id']}", {"consent_confirmed": False})
    assert Quote.objects.get().published is False
    assert api_client.get(PUBLIC).json() == []


def test_testimonials_are_ordered_and_can_be_deleted(as_editor, api_client):
    second = add(as_editor, name="Second", position=2, published=True, consent_confirmed=True)
    add(as_editor, name="First", position=1, published=True, consent_confirmed=True)
    assert [t["name"] for t in api_client.get(PUBLIC).json()] == ["First", "Second"]
    assert as_editor.delete(f"{ADMIN}/{second['id']}").status_code == 204
    assert [t["name"] for t in as_editor.get(ADMIN).json()] == ["First"]
    assert as_editor.delete(f"{ADMIN}/{second['id']}").status_code == 404


def test_markup_is_stripped_and_short_quotes_are_refused(as_editor):
    made = add(as_editor, quote="<b>Great</b> community for any founder.")
    assert made["quote"] == "Great community for any founder."
    assert as_editor.post(ADMIN, {"quote": "Ok", "name": "A B"}).status_code == 400


def test_only_editorial_admins_manage_testimonials(client_for, make_user, api_client):
    member = client_for(make_user(email="m@example.com"))
    assert api_client.get(ADMIN).status_code == 401
    assert member.get(ADMIN).status_code == 403
    assert member.post(ADMIN, {"quote": QUOTE, "name": "X Y"}).status_code == 403
