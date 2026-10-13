import pytest
from django.utils import timezone

from apps.editorial import services as editorial
from apps.editorial.models import CommentReport, ItemComment
from apps.notifications.models import Notification

pytestmark = pytest.mark.django_db

QUEUE = "/api/v1/admin/reports"


def active(make_user, email):
    return make_user(email=email, approved_at=timezone.now(), email_verified_at=timezone.now())


@pytest.fixture
def story(make_user):
    editor = make_user(roles=("content_editor",), email="editor@example.com")
    item = editorial.create_item(
        actor=editor, data={"type": "news", "title": "A milestone", "body": "<p>Big day.</p>"}
    )
    return editorial.publish_now(actor=editor, item_id=item.pk)


@pytest.fixture
def author(make_user):
    return active(make_user, "author@example.com")


@pytest.fixture
def reporter(make_user):
    return active(make_user, "reporter@example.com")


@pytest.fixture
def comment(story, author):
    return editorial.add_comment(user_id=author.pk, item_id=story.pk, body="<p>Buy my coins!</p>")


@pytest.fixture
def admin_client(make_user, client_for):
    admin = make_user(roles=("community_admin",), email="admin@example.com")
    return client_for(admin, mfa_age=5)


def file_report(client, comment, reason="spam", **extra):
    return client.post(
        f"/api/v1/editorial-comments/{comment.pk}/reports",
        {"reason": reason, **extra},
        format="json",
    )


# --- members report ---


def test_a_member_reports_a_comment_once(reporter, comment, client_for):
    client = client_for(reporter)
    first = file_report(client, comment, details="Crypto scam")
    assert first.status_code == 201 and first.json()["created"] is True
    again = file_report(client, comment)
    assert again.status_code == 200 and again.json()["created"] is False
    assert again.json()["id"] == first.json()["id"]
    assert CommentReport.objects.count() == 1


def test_you_cannot_report_your_own_comment_or_one_you_cannot_see(
    author, reporter, comment, client_for
):
    assert file_report(client_for(author), comment).status_code == 400
    ItemComment.objects.filter(pk=comment.pk).update(hidden_at=timezone.now())
    assert file_report(client_for(reporter), comment).status_code == 404


def test_bad_reasons_are_refused_and_visitors_cannot_report(
    reporter, comment, client_for, api_client
):
    assert file_report(client_for(reporter), comment, reason="dislike").status_code == 400
    assert file_report(api_client, comment).status_code == 401


def test_reports_are_limited_per_day(reporter, story, make_user, client_for, settings):
    settings.FEED_REPORTS_PER_DAY = 2
    client = client_for(reporter)
    statuses = []
    for n in range(3):
        writer = active(make_user, f"writer{n}@example.com")
        c = editorial.add_comment(user_id=writer.pk, item_id=story.pk, body="<p>Hello</p>")
        statuses.append(file_report(client, c).status_code)
    assert statuses == [201, 201, 429]


# --- moderators ---


def test_the_queue_shows_news_comments_beside_feed_reports(
    admin_client, reporter, comment, client_for
):
    file_report(client_for(reporter), comment)
    queue = admin_client.get(QUEUE).json()
    assert queue["count"] == 1
    row = queue["results"][0]
    assert row["target"]["type"] == "news_comment" and row["target"]["state"] == "visible"
    assert "Buy my coins" in row["target"]["excerpt"]
    assert row["target"]["author"]["id"] == str(comment.author_id)
    assert row["reason"] == "spam" and row["open_reports_on_target"] == 1

    only = admin_client.get(QUEUE, {"target_type": "news_comment"}).json()
    assert only["count"] == 1
    assert admin_client.get(QUEUE, {"target_type": "post"}).json()["count"] == 0
    assert admin_client.get("/api/v1/admin/queues").json()["open_reports"] == 1


def test_reviewing_a_report_tells_the_reporter(
    admin_client, reporter, comment, client_for, run_outbox
):
    report = file_report(client_for(reporter), comment).json()
    done = admin_client.post(
        f"{QUEUE}/{report['id']}/review", {"note": "Fine as it is"}, format="json"
    )
    assert done.status_code == 200 and done.json()["status"] == "reviewed"
    run_outbox()
    note = Notification.objects.get(user=reporter, type="report_outcome")
    assert note.payload["outcome"] == "reviewed"


def test_acting_hides_the_comment_and_closes_every_report_on_it(
    admin_client, reporter, comment, client_for, make_user, run_outbox
):
    second = active(make_user, "second@example.com")
    first = file_report(client_for(reporter), comment).json()
    file_report(client_for(second), comment, reason="harassment")
    done = admin_client.post(
        f"{QUEUE}/{first['id']}/action", {"action": "hide", "note": "Scam"}, format="json"
    )
    assert done.status_code == 200
    assert done.json()["status"] == "actioned" and done.json()["target"]["state"] == "hidden"
    assert CommentReport.objects.filter(status="actioned").count() == 2
    assert ItemComment.objects.get(pk=comment.pk).hidden_at is not None
    again = admin_client.post(f"{QUEUE}/{first['id']}/review", {}, format="json")
    assert again.status_code == 409  # already actioned
    run_outbox()
    assert Notification.objects.filter(type="report_outcome").count() == 2
    title = Notification.objects.filter(user=reporter).first().payload
    assert title["target_type"] == "news_comment"


def test_one_report_detail_and_unknown_ids(admin_client, reporter, comment, client_for):
    report = file_report(client_for(reporter), comment).json()
    detail = admin_client.get(f"{QUEUE}/{report['id']}")
    assert detail.status_code == 200 and detail.json()["target"]["type"] == "news_comment"
    missing = admin_client.get(f"{QUEUE}/00000000-0000-0000-0000-000000000000")
    assert missing.status_code == 404


def test_only_moderators_see_the_queue(reporter, client_for):
    assert client_for(reporter, mfa_age=5).get(QUEUE).status_code == 403
