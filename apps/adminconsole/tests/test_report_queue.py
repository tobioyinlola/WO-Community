import uuid

import pytest
from django.utils import timezone

from apps.audit.models import AuditLog
from apps.feed.models import Comment, Post, Report

pytestmark = pytest.mark.django_db

POSTS = "/api/v1/posts"
QUEUE = "/api/v1/admin/reports"


def make_member(make_user, email):
    return make_user(email=email, approved_at=timezone.now(), email_verified_at=timezone.now())


@pytest.fixture
def author(make_user):
    return make_member(make_user, "author@example.com")


@pytest.fixture
def author_client(author, client_for):
    return client_for(author)


@pytest.fixture
def reporter(make_user):
    return make_member(make_user, "reporter@example.com")


@pytest.fixture
def reporter_client(reporter, client_for):
    return client_for(reporter)


@pytest.fixture
def moderator(make_user):
    return make_user(roles=("community_admin",), email="admin@example.com")


@pytest.fixture
def as_moderator(moderator, client_for):
    return client_for(moderator, mfa_age=5)


@pytest.fixture
def post(author_client):
    return author_client.post(
        POSTS, {"category": "update", "body": "<p>Buy my thing now</p>"}, format="json"
    ).json()["id"]


@pytest.fixture
def comment(reporter_client, post):
    return reporter_client.post(
        f"{POSTS}/{post}/comments", {"body": "<p>rude words</p>"}, format="json"
    ).json()["id"]


def file_report(client, kind, target, reason="spam"):
    base = "posts" if kind == "post" else "comments"
    response = client.post(f"/api/v1/{base}/{target}/reports", {"reason": reason}, format="json")
    assert response.status_code in (200, 201), response.content
    return response.json()["id"]


# --- reading the queue ---


def test_the_queue_shows_open_reports_oldest_first_with_a_look_at_the_content(
    as_moderator, reporter_client, author_client, post, author, reporter
):
    first = file_report(reporter_client, "post", post, "spam")
    second_post = author_client.post(
        POSTS, {"category": "update", "body": "<p>second</p>"}, format="json"
    ).json()["id"]
    second = file_report(reporter_client, "post", second_post, "harassment")
    body = as_moderator.get(QUEUE).json()
    assert body["count"] == 2
    assert [r["id"] for r in body["results"]] == [first, second]
    item = body["results"][0]
    assert item["status"] == "open" and item["reason"] == "spam"
    assert item["reporter"]["id"] == str(reporter.pk)
    assert item["target"]["type"] == "post" and item["target"]["excerpt"] == "Buy my thing now"
    assert item["target"]["state"] == "visible" and item["target"]["author"]["id"] == str(author.pk)
    assert item["open_reports_on_target"] == 1


def test_open_reports_on_the_same_target_are_counted(
    as_moderator, reporter_client, make_user, client_for, post
):
    file_report(reporter_client, "post", post)
    file_report(client_for(make_member(make_user, "other@example.com")), "post", post, "illegal")
    assert {r["open_reports_on_target"] for r in as_moderator.get(QUEUE).json()["results"]} == {2}


def test_a_comment_report_points_at_its_post(as_moderator, author_client, comment, post):
    file_report(author_client, "comment", comment)
    item = as_moderator.get(QUEUE).json()["results"][0]
    assert item["target"]["type"] == "comment" and item["target"]["post_id"] == post
    assert item["target"]["excerpt"] == "rude words"


def test_the_queue_can_be_filtered(as_moderator, reporter_client, author_client, post, comment):
    file_report(reporter_client, "post", post, "spam")
    file_report(author_client, "comment", comment, "harassment")
    assert as_moderator.get(QUEUE, {"target_type": "comment"}).json()["count"] == 1
    assert as_moderator.get(QUEUE, {"reason": "spam"}).json()["count"] == 1
    assert as_moderator.get(QUEUE, {"status": "actioned"}).json()["count"] == 0


@pytest.mark.parametrize(
    "params",
    [{"status": "x"}, {"target_type": "user"}, {"reason": "boring"}, {"limit": 0}, {"z": 1}],
)
def test_bad_queue_queries_are_refused(as_moderator, params):
    assert as_moderator.get(QUEUE, params).status_code == 400


def test_one_report_can_be_read(as_moderator, reporter_client, post):
    rid = file_report(reporter_client, "post", post)
    assert as_moderator.get(f"{QUEUE}/{rid}").json()["id"] == rid
    assert as_moderator.get(f"{QUEUE}/{uuid.uuid4()}").status_code == 404


def test_the_queue_count_appears_with_the_other_queues(as_moderator, reporter_client, post):
    file_report(reporter_client, "post", post)
    counts = as_moderator.get("/api/v1/admin/queues").json()
    assert counts["open_reports"] == 1


# --- handling reports ---


def test_reviewing_closes_nothing_but_the_one_report(
    as_moderator, moderator, reporter_client, make_user, client_for, post
):
    mine = file_report(reporter_client, "post", post)
    other = file_report(client_for(make_member(make_user, "o@example.com")), "post", post)
    response = as_moderator.post(f"{QUEUE}/{mine}/review", {"note": "looks fine"})
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "reviewed" and body["note"] == "looks fine"
    assert body["handled_by"] == str(moderator.pk) and body["handled_at"]
    assert Report.objects.get(pk=other).status == "open"
    assert Post.objects.get(pk=post).hidden_at is None
    assert AuditLog.objects.filter(action="feed.report_reviewed").count() == 1


def test_actioning_hides_the_post_and_closes_every_open_report_about_it(
    as_moderator, moderator, reporter_client, make_user, client_for, post
):
    a = file_report(reporter_client, "post", post)
    b = file_report(client_for(make_member(make_user, "o@example.com")), "post", post, "illegal")
    response = as_moderator.post(f"{QUEUE}/{a}/action", {"action": "hide", "note": "spam"})
    assert response.status_code == 200 and response.json()["status"] == "actioned"
    assert {r.status for r in Report.objects.filter(pk__in=[a, b])} == {"actioned"}
    assert Report.objects.get(pk=b).handled_by_id == moderator.pk
    assert Post.objects.get(pk=post).hidden_at is not None
    assert response.json()["target"]["state"] == "hidden"
    assert AuditLog.objects.filter(action="feed.post_hide").exists()
    assert AuditLog.objects.filter(action="feed.report_actioned").count() == 1


def test_actioning_can_remove_a_post(as_moderator, reporter_client, author_client, post):
    rid = file_report(reporter_client, "post", post)
    as_moderator.post(f"{QUEUE}/{rid}/action", {"action": "remove"})
    assert Post.objects.get(pk=post).deleted_at is not None
    assert author_client.get(f"{POSTS}/{post}").status_code == 404
    assert as_moderator.get(f"{QUEUE}/{rid}").json()["target"]["state"] == "removed"


def test_actioning_a_comment_hides_it_and_fixes_the_post_count(
    as_moderator, author_client, reporter_client, post, comment
):
    reply = author_client.post(
        f"{POSTS}/{post}/comments", {"body": "<p>reply</p>", "parent_id": comment}, format="json"
    ).json()["id"]
    assert author_client.get(f"{POSTS}/{post}").json()["comment_count"] == 2
    rid = file_report(author_client, "comment", comment, "harassment")
    as_moderator.post(f"{QUEUE}/{rid}/action", {"action": "hide"})
    assert Comment.objects.get(pk=comment).hidden_at is not None
    assert author_client.get(f"{POSTS}/{post}").json()["comment_count"] == 0
    assert author_client.get(f"{POSTS}/{post}/comments").json()["results"] == []
    assert (
        reporter_client.post(f"/api/v1/comments/{reply}/reactions", {"kind": "like"}).status_code
        == 404
    )


def test_an_already_actioned_report_cannot_be_reviewed_again(as_moderator, reporter_client, post):
    rid = file_report(reporter_client, "post", post)
    as_moderator.post(f"{QUEUE}/{rid}/action", {"action": "hide"})
    assert as_moderator.post(f"{QUEUE}/{rid}/review").status_code == 409


def test_actioning_something_already_removed_still_closes_the_report(
    as_moderator, reporter_client, post
):
    rid = file_report(reporter_client, "post", post)
    as_moderator.post(f"/api/v1/admin/posts/{post}/remove")
    assert (
        as_moderator.post(f"{QUEUE}/{rid}/action", {"action": "hide"}).json()["status"]
        == "actioned"
    )


@pytest.mark.parametrize(
    "body",
    [{}, {"action": "ban"}, {"action": "hide", "note": "x" * 501}, {"action": "hide", "x": 1}],
)
def test_invalid_actions_are_refused(as_moderator, reporter_client, post, body):
    rid = file_report(reporter_client, "post", post)
    assert as_moderator.post(f"{QUEUE}/{rid}/action", body).status_code == 400
    assert Report.objects.get(pk=rid).status == "open"


def test_unknown_reports_are_404(as_moderator):
    rid = uuid.uuid4()
    assert as_moderator.post(f"{QUEUE}/{rid}/review").status_code == 404
    assert as_moderator.post(f"{QUEUE}/{rid}/action", {"action": "hide"}).status_code == 404


# --- direct comment moderation ---


def test_comments_can_be_hidden_unhidden_and_removed_directly(
    as_moderator, author_client, post, comment
):
    base = f"/api/v1/admin/comments/{comment}"
    assert as_moderator.post(f"{base}/hide", {"reason": "rude"}).status_code == 200
    assert author_client.get(f"{POSTS}/{post}").json()["comment_count"] == 0
    assert as_moderator.post(f"{base}/unhide").status_code == 200
    assert author_client.get(f"{POSTS}/{post}").json()["comment_count"] == 1
    assert as_moderator.post(f"{base}/remove").status_code == 200
    assert author_client.get(f"{POSTS}/{post}/comments").json()["results"] == []
    assert Comment.objects.get(pk=comment).deleted_at is not None
    assert AuditLog.objects.filter(action="feed.comment_hide", reason="rude").exists()
    assert as_moderator.post(f"{base}/hide").status_code == 404


def test_hiding_a_comment_hides_its_replies_too(as_moderator, author_client, post, comment):
    author_client.post(
        f"{POSTS}/{post}/comments", {"body": "<p>reply</p>", "parent_id": comment}, format="json"
    )
    as_moderator.post(f"/api/v1/admin/comments/{comment}/hide")
    assert author_client.get(f"{POSTS}/{post}").json()["comment_count"] == 0
    as_moderator.post(f"/api/v1/admin/comments/{comment}/unhide")
    page = author_client.get(f"{POSTS}/{post}/comments").json()["results"]
    assert len(page) == 1 and len(page[0]["replies"]) == 1
    assert author_client.get(f"{POSTS}/{post}").json()["comment_count"] == 2


# --- who may use the queue ---


ENDPOINTS = [
    ("get", QUEUE),
    ("get", f"{QUEUE}/{uuid.uuid4()}"),
    ("post", f"{QUEUE}/{uuid.uuid4()}/review"),
    ("post", f"{QUEUE}/{uuid.uuid4()}/action"),
    ("post", f"/api/v1/admin/comments/{uuid.uuid4()}/hide"),
]


@pytest.mark.parametrize("method, url", ENDPOINTS)
def test_visitors_and_members_cannot_use_the_queue(api_client, reporter_client, method, url):
    assert getattr(api_client, method)(url).status_code == 401
    assert getattr(reporter_client, method)(url).status_code == 403


@pytest.mark.parametrize("method, url", ENDPOINTS)
def test_an_editor_without_report_permission_is_refused(make_user, client_for, method, url):
    editor = client_for(make_user(roles=("content_editor",), email="e@example.com"), mfa_age=5)
    assert getattr(editor, method)(url).status_code == 403


@pytest.mark.parametrize("method, url", ENDPOINTS)
def test_an_admin_without_a_recent_mfa_check_is_refused(moderator, client_for, method, url):
    assert getattr(client_for(moderator), method)(url).status_code == 403
