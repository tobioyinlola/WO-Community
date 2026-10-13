import pytest
from django.utils import timezone

from apps.learning.tests.conftest import build_course

pytestmark = pytest.mark.django_db

URL = "/api/v1/public/sitemaps"


def test_every_kind_of_public_page_is_listed(api_client, make_user):
    editor = make_user(roles=("content_editor",), email="editor@example.com")
    course = build_course(editor, open_to_visitors=True)
    hidden = build_course(editor, title="Members only course")
    response = api_client.get(URL)
    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"startups", "founders", "jobs", "news", "events", "courses"}
    assert [e["path"] for e in body["courses"]] == [f"/courses/{course.slug}"]
    assert hidden.slug not in str(body)
    assert body["courses"][0]["lastmod"]
    assert response["Cache-Control"].startswith("public")
    assert "set-cookie" not in {k.lower() for k in response.headers}


def test_the_sitemap_is_cacheable_and_takes_no_parameters(api_client):
    first = api_client.get(URL)
    again = api_client.get(URL, HTTP_IF_NONE_MATCH=first["ETag"])
    assert again.status_code == 304
    assert api_client.get(URL, {"x": "1"}).status_code == 400
    assert timezone.now()
