import uuid

import pytest

from apps.accounts.models import User
from apps.feed.models import Post, Report
from apps.feed.tests.conftest import POSTS, active, comments_url, write_post

pytestmark = pytest.mark.django_db


def report_post(client, post, reason="spam", **extra):
    return client.post(f"{POSTS}/{post}/reports", {"reason": reason, **extra}, format="json")


def report_comment(client, comment, reason="spam", **extra):
    return client.post(
        f"/api/v1/comments/{comment}/reports", {"reason": reason, **extra}, format="json"
    )


@pytest.fixture
def comment_id(author_client, reader_client, post_id):
    return reader_client.post(comments_url(post_id), {"body": "<p>hi</p>"}, format="json").json()[
        "id"
    ]


# --- reporting a post ---


def test_a_member_can_report_a_post(reader_client, reader, post_id):
    response = report_post(reader_client, post_id, "harassment", details="Targets me")
    assert response.status_code == 201
    assert response.json()["status"] == "open" and response.json()["created"] is True
    stored = Report.objects.get()
    assert (stored.reporter_id, str(stored.target_id), stored.reason) == (
        reader.pk,
        post_id,
        "harassment",
    )
    assert stored.target_type == "post" and stored.details == "Targets me"


def test_reporting_the_same_thing_twice_keeps_one_report(reader_client, post_id):
    first = report_post(reader_client, post_id).json()["id"]
    again = report_post(reader_client, post_id, "illegal")
    assert again.status_code == 200 and again.json()["id"] == first
    assert again.json()["created"] is False
    assert Report.objects.count() == 1 and Report.objects.get().reason == "spam"


def test_different_members_can_report_the_same_post(
    reader_client, author_client, make_user, client_for, post_id
):
    third = client_for(active(make_user, "third@example.com"))
    report_post(reader_client, post_id)
    report_post(third, post_id)
    assert Report.objects.count() == 2


def test_details_are_stripped_of_markup(reader_client, post_id):
    report_post(reader_client, post_id, details="<script>x</script>bad <b>stuff</b>")
    assert "<" not in Report.objects.get().details


def test_you_cannot_report_your_own_post_or_comment(author_client, reader_client, post_id):
    assert report_post(author_client, post_id).status_code == 400
    mine = reader_client.post(comments_url(post_id), {"body": "<p>x</p>"}, format="json").json()[
        "id"
    ]
    assert report_comment(reader_client, mine).status_code == 400
    assert Report.objects.count() == 0


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"reason": "boring"},
        {"reason": "spam", "details": "x" * 501},
        {"reason": "spam", "x": 1},
    ],
)
def test_invalid_reports_are_refused(reader_client, post_id, body):
    assert reader_client.post(f"{POSTS}/{post_id}/reports", body, format="json").status_code == 400
    assert Report.objects.count() == 0


def test_you_cannot_report_what_you_cannot_see(reader_client, post_id, author):
    assert report_post(reader_client, str(uuid.uuid4())).status_code == 404
    Post.objects.filter(pk=post_id).update(hidden_at="2026-01-01T00:00:00Z")
    assert report_post(reader_client, post_id).status_code == 404
    Post.objects.filter(pk=post_id).update(hidden_at=None)
    User.objects.filter(pk=author.pk).update(status="suspended")
    assert report_post(reader_client, post_id).status_code == 404


def test_reporting_needs_an_active_member(api_client, make_user, client_for, post_id):
    assert report_post(api_client, post_id).status_code == 401
    pending = client_for(make_user(email="p@example.com", status="pending"))
    assert report_post(pending, post_id).status_code == 403


def test_reports_have_a_daily_allowance(reader_client, author_client, settings):
    settings.FEED_REPORTS_PER_DAY = 2
    posts = [write_post(author_client).json()["id"] for _ in range(3)]
    assert [report_post(reader_client, p).status_code for p in posts] == [201, 201, 429]


# --- reporting a comment ---


def test_a_member_can_report_a_comment(author_client, comment_id):
    response = report_comment(author_client, comment_id, "inappropriate")
    assert response.status_code == 201
    stored = Report.objects.get()
    assert stored.target_type == "comment" and str(stored.target_id) == comment_id


def test_a_post_id_is_not_a_comment_id(reader_client, post_id):
    assert report_comment(reader_client, post_id).status_code == 404


def test_hidden_and_removed_comments_cannot_be_reported(author_client, reader_client, comment_id):
    from apps.feed.models import Comment

    Comment.objects.filter(pk=comment_id).update(hidden_at="2026-01-01T00:00:00Z")
    assert report_comment(author_client, comment_id).status_code == 404
    reader_client.delete(f"/api/v1/comments/{comment_id}")
    assert report_comment(author_client, comment_id).status_code == 404
