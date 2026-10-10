import pytest
from django.utils import timezone

POSTS = "/api/v1/posts"


def post_url(post_id):
    return f"{POSTS}/{post_id}"


def comments_url(post_id):
    return f"{POSTS}/{post_id}/comments"


def active(make_user, email, **fields):
    return make_user(
        email=email, approved_at=timezone.now(), email_verified_at=timezone.now(), **fields
    )


@pytest.fixture
def author(make_user):
    return active(make_user, "author@example.com")


@pytest.fixture
def reader(make_user):
    return active(make_user, "reader@example.com")


@pytest.fixture
def author_client(author, client_for):
    return client_for(author)


@pytest.fixture
def reader_client(reader, client_for):
    return client_for(reader)


def write_post(client, body="<p>Hello <strong>community</strong></p>", category="update", **extra):
    return client.post(POSTS, {"category": category, "body": body, **extra}, format="json")


@pytest.fixture
def post_id(author_client):
    response = write_post(author_client)
    assert response.status_code == 201, response.content
    return response.json()["id"]
