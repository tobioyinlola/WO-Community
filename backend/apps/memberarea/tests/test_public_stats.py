import pytest

from apps.directory.tests.conftest import listed  # noqa: F401
from apps.learning.tests.conftest import build_course

pytestmark = pytest.mark.django_db

URL = "/api/v1/public/stats"


def test_counts_what_a_visitor_can_see_and_nothing_else(api_client, make_user):
    editor = make_user(roles=("content_editor",), email="editor@example.com")
    build_course(editor, open_to_visitors=True)
    build_course(editor, title="Members only course")
    response = api_client.get(URL)
    assert response.status_code == 200
    assert response.json() == {
        "startups": 0,
        "founders": 0,
        "courses": 1,
        "jobs": 0,
        "countries": [],
    }


def test_countries_come_only_from_founders_who_made_their_location_public(api_client, listed):  # noqa: F811
    listed("Acme", country="NG", founder_location_public=True)
    listed("Beta", country="NG", founder_location_public=True)
    listed("Cedar", country="GH", founder_location_public=True)
    listed("Hidden", country="KE", founder_location_public=False)
    countries = api_client.get(URL).json()["countries"]
    assert countries == [{"code": "NG", "founders": 2}, {"code": "GH", "founders": 1}]


def test_at_most_ten_countries(api_client, listed):  # noqa: F811
    for code in ["NG", "GH", "KE", "ZA", "EG", "RW", "SN", "TZ", "UG", "ET", "MA", "CI"]:
        listed(f"Co {code}", country=code, founder_location_public=True)
    assert len(api_client.get(URL).json()["countries"]) == 10


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
