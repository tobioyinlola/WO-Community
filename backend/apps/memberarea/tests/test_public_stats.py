import pytest

from apps.learning.tests.conftest import build_course

pytestmark = pytest.mark.django_db

URL = "/api/v1/public/stats"


def test_counts_what_a_visitor_can_see_and_nothing_else(api_client, make_user):
    editor = make_user(roles=("content_editor",), email="editor@example.com")
    build_course(editor, open_to_visitors=True)
    build_course(editor, title="Members only course")
    response = api_client.get(URL)
    assert response.status_code == 200
    assert response.json() == {"startups": 0, "founders": 0, "courses": 1, "jobs": 0}


def test_it_is_public_cacheable_and_sets_no_cookie(api_client):
    first = api_client.get(URL)
    assert first["Cache-Control"].startswith("public")
    assert "set-cookie" not in {k.lower() for k in first.headers}
    assert api_client.get(URL, HTTP_IF_NONE_MATCH=first["ETag"]).status_code == 304


def test_it_takes_no_parameters(api_client):
    assert api_client.get(URL, {"x": "1"}).status_code == 400


def test_a_signed_in_member_sees_the_same_numbers(make_user, client_for, api_client):
    member = make_user(email="member@example.com")
    assert client_for(member).get(URL).json() == api_client.get(URL).json()
