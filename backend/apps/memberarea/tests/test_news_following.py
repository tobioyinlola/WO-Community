from datetime import timedelta

import pytest
from django.utils import timezone

from apps.editorial import services as editorial
from apps.memberarea import news
from apps.notifications.models import Notification
from apps.startups.models import Startup

pytestmark = pytest.mark.django_db

FEED = "/api/v1/me/news/following"
FOLLOWS = "/api/v1/follows"


def member(make_user, email):
    return make_user(email=email, approved_at=timezone.now(), email_verified_at=timezone.now())


@pytest.fixture
def editor(make_user):
    return make_user(roles=("content_editor",), email="editor@example.com")


@pytest.fixture
def founder(make_user):
    return member(make_user, "founder@example.com")


@pytest.fixture
def fan(make_user):
    return member(make_user, "fan@example.com")


@pytest.fixture
def startup(founder, client_for):
    response = client_for(founder).post(
        "/api/v1/startups",
        {
            "name": "Acme Pay",
            "pitch": "Payments for traders",
            "country": "NG",
            "city": "Lagos",
            "sector": "fintech",
            "stage": "seed",
            "year_founded": 2023,
            "description": "Pay",
            "website_url": "https://acme.example.com",
        },
    )
    assert response.status_code == 201, response.content
    return Startup.objects.get(pk=response.json()["id"])


def publish(editor, title, startups=()):
    item = editorial.create_item(
        actor=editor,
        data={
            "type": "news",
            "title": title,
            "body": f"<p>{title}</p>",
            "startup_ids": [s.pk for s in startups],
        },
    )
    return editorial.publish_now(actor=editor, item_id=item.pk)


def follow(client, kind, target_id):
    return client.post(FOLLOWS, {"type": kind, "id": str(target_id)}, format="json")


# --- the following view ---


def test_a_member_sees_news_about_startups_they_follow(editor, startup, fan, client_for):
    about = publish(editor, "Acme Pay raises a seed round", [startup])
    publish(editor, "Unrelated community news")
    client = client_for(fan)
    assert client.get(FEED).json() == {"results": [], "next_cursor": None}  # follows nothing yet
    assert follow(client, "startup", startup.pk).status_code == 201
    body = client.get(FEED).json()
    assert [r["id"] for r in body["results"]] == [str(about.pk)]
    assert client.get(FEED)["Cache-Control"] == "private, no-store"


def test_news_about_a_followed_members_startup_counts_too(
    editor, startup, founder, fan, client_for
):
    from apps.profiles.models import FounderProfile

    FounderProfile.objects.update_or_create(
        user=founder, defaults={"full_name": "Ada Founder", "slug": "ada-founder"}
    )
    about = publish(editor, "Acme Pay hires its first engineer", [startup])
    client = client_for(fan)
    assert follow(client, "member", founder.pk).status_code == 201
    assert [r["id"] for r in client.get(FEED).json()["results"]] == [str(about.pk)]


def test_the_following_view_pages_and_filters(editor, startup, fan, client_for):
    for n in range(3):
        publish(editor, f"Acme story {n}", [startup])
    client = client_for(fan)
    follow(client, "startup", startup.pk)
    first = client.get(FEED, {"limit": 2}).json()
    assert len(first["results"]) == 2 and first["next_cursor"]
    rest = client.get(FEED, {"limit": 2, "cursor": first["next_cursor"]}).json()
    assert len(rest["results"]) == 1
    assert client.get(FEED, {"limit": 99}).status_code == 400


# --- notices ---


def test_followers_of_a_featured_startup_are_told_when_it_is_in_the_news(
    editor, startup, fan, client_for, run_outbox
):
    follow(client_for(fan), "startup", startup.pk)
    item = publish(editor, "Acme Pay wins an award", [startup])
    run_outbox()
    note = Notification.objects.get(user=fan, type="news_featuring_followed")
    assert note.payload["slug"] == item.slug
    titles = [n["title"] for n in client_for(fan).get("/api/v1/notifications").json()["results"]]
    assert "In the news: Acme Pay wins an award" in titles
    # Running it again (a retried event) tells nobody twice.
    assert news.notify_followers_of_item(item.pk) == 0


def test_nobody_is_told_about_stories_that_feature_no_one_they_follow(
    editor, startup, fan, client_for, run_outbox
):
    publish(editor, "Community update")
    run_outbox()
    assert not Notification.objects.filter(type="news_featuring_followed").exists()


# --- the digest ---


def opt_in(client):
    return client.put(
        "/api/v1/me/notification-preferences",
        {"preferences": {"news_digest": {"email": True}}},
        format="json",
    )


def opt_out(client):
    return client.put(
        "/api/v1/me/notification-preferences",
        {"preferences": {"news_digest": {"email": False}}},
        format="json",
    )


def test_the_digest_goes_to_members_who_did_not_switch_it_off_and_once_a_week(
    editor, fan, make_user, client_for, sent_emails
):
    publish(editor, "Big funding round")
    quiet = member(make_user, "quiet@example.com")
    assert opt_out(client_for(quiet)).status_code == 200
    assert news.send_digest() >= 1
    to = {m.to for m in sent_emails if m.subject == "This week on WO Community"}
    assert "fan@example.com" in to and "quiet@example.com" not in to
    mail = [m for m in sent_emails if m.to == "fan@example.com"]
    assert "Big funding round" in mail[0].text_body and "/news/" in mail[0].text_body
    assert news.send_digest() == 0  # already sent this week


def test_the_digest_skips_weeks_with_no_stories(editor, fan, client_for, sent_emails):
    opt_in(client_for(fan))
    old = publish(editor, "Old story")
    from apps.editorial.models import EditorialItem

    EditorialItem.objects.filter(pk=old.pk).update(published_at=timezone.now() - timedelta(days=30))
    assert news.send_digest() == 0 and not sent_emails
