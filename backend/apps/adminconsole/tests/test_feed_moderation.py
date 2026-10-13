import uuid

import pytest
from django.utils import timezone

from apps.audit.models import AuditLog
from apps.feed.models import Post

pytestmark = pytest.mark.django_db

POSTS = "/api/v1/posts"


def admin_url(post, action):
    return f"/api/v1/admin/posts/{post}/{action}"


@pytest.fixture
def member(make_user):
    return make_user(
        email="member@example.com", approved_at=timezone.now(), email_verified_at=timezone.now()
    )


@pytest.fixture
def member_client(member, client_for):
    return client_for(member)


@pytest.fixture
def moderator(make_user):
    return make_user(roles=("community_admin",), email="admin@example.com")


@pytest.fixture
def as_moderator(moderator, client_for):
    return client_for(moderator, mfa_age=5)


@pytest.fixture
def post(member_client):
    return member_client.post(
        POSTS, {"category": "update", "body": "<p>hello</p>"}, format="json"
    ).json()["id"]


@pytest.fixture
def reader_client(make_user, client_for):
    return client_for(
        make_user(
            email="reader@example.com",
            approved_at=timezone.now(),
            email_verified_at=timezone.now(),
        )
    )


# --- the actions ---


def test_pinning_puts_a_post_in_the_pinned_list_on_the_first_page(
    as_moderator, reader_client, member_client, post
):
    newer = member_client.post(
        POSTS, {"category": "update", "body": "<p>newer</p>"}, format="json"
    ).json()["id"]
    assert as_moderator.post(admin_url(post, "pin")).status_code == 200
    page = reader_client.get(POSTS).json()
    assert [p["id"] for p in page["pinned"]] == [post]
    assert [p["id"] for p in page["results"]] == [newer]  # not listed twice
    assert page["pinned"][0]["pinned"] is True
    as_moderator.post(admin_url(post, "unpin"))
    page = reader_client.get(POSTS).json()
    assert page["pinned"] == [] and len(page["results"]) == 2


def test_featuring_marks_a_post(as_moderator, reader_client, post):
    as_moderator.post(admin_url(post, "feature"))
    assert reader_client.get(f"{POSTS}/{post}").json()["featured"] is True
    as_moderator.post(admin_url(post, "unfeature"))
    assert reader_client.get(f"{POSTS}/{post}").json()["featured"] is False


def test_hiding_removes_a_post_for_everyone_but_its_author(
    as_moderator, reader_client, member_client, post
):
    as_moderator.post(admin_url(post, "hide"))
    assert reader_client.get(f"{POSTS}/{post}").status_code == 404
    assert reader_client.get(POSTS).json()["results"] == []
    own = member_client.get(f"{POSTS}/{post}").json()
    assert own["hidden"] is True
    assert [p["id"] for p in member_client.get(POSTS, {"scope": "mine"}).json()["results"]] == [
        post
    ]
    assert member_client.get(POSTS).json()["results"] == []
    etag = member_client.get(f"{POSTS}/{post}")["ETag"]
    edited = member_client.patch(
        f"{POSTS}/{post}", {"body": "<p>sneaky</p>"}, format="json", HTTP_IF_MATCH=etag
    )
    assert edited.status_code == 403
    as_moderator.post(admin_url(post, "unhide"))
    assert reader_client.get(f"{POSTS}/{post}").status_code == 200


def test_removing_deletes_a_post_for_everyone(as_moderator, reader_client, member_client, post):
    assert as_moderator.post(admin_url(post, "remove"), {"reason": "spam"}).status_code == 200
    for client in (reader_client, member_client):
        assert client.get(f"{POSTS}/{post}").status_code == 404
    assert Post.objects.get(pk=post).deleted_at is not None
    assert as_moderator.post(admin_url(post, "remove")).status_code == 404


def test_every_action_is_written_to_the_audit_log(as_moderator, moderator, post):
    as_moderator.post(admin_url(post, "hide"), {"reason": "off topic"})
    entry = AuditLog.objects.get(action="feed.post_hide")
    assert entry.actor_id == moderator.pk and str(entry.target_id) == post
    assert entry.reason == "off topic"


def test_actions_on_missing_posts_are_404(as_moderator):
    assert as_moderator.post(admin_url(uuid.uuid4(), "pin")).status_code == 404


def test_the_reason_is_optional_and_bounded(as_moderator, post):
    assert as_moderator.post(admin_url(post, "feature"), {"reason": "x" * 501}).status_code == 400
    assert as_moderator.post(admin_url(post, "feature"), {"extra": 1}).status_code == 400


# --- who may moderate ---


@pytest.mark.parametrize(
    "action", ["pin", "unpin", "feature", "unfeature", "hide", "unhide", "remove"]
)
def test_members_and_visitors_cannot_moderate(api_client, member_client, post, action):
    assert api_client.post(admin_url(post, action)).status_code == 401
    assert member_client.post(admin_url(post, action)).status_code == 403


def test_a_content_editor_without_the_permission_cannot_moderate(make_user, client_for, post):
    editor = make_user(roles=("content_editor",), email="editor@example.com")
    assert client_for(editor, mfa_age=5).post(admin_url(post, "hide")).status_code == 403


def test_an_admin_without_a_recent_mfa_check_is_refused(moderator, client_for, post):
    assert client_for(moderator).post(admin_url(post, "hide")).status_code == 403
    assert Post.objects.get(pk=post).hidden_at is None
