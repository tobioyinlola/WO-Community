"""Sharing a course, an event or a post: in the feed, and as a link outside the platform."""

import pytest
from django.test import Client
from django.utils import timezone

from apps.events.tests.conftest import make_event
from apps.feed.models import Post
from apps.learning.models import Course
from apps.learning.tests.conftest import build_course
from apps.profiles.models import FounderProfile

pytestmark = pytest.mark.django_db

POSTS = "/api/v1/posts"
CARD = "/api/v1/public/share"


def active(make_user, email, **fields):
    return make_user(
        email=email, approved_at=timezone.now(), email_verified_at=timezone.now(), **fields
    )


@pytest.fixture
def editor(make_user):
    return make_user(roles=("content_editor",), email="editor@example.com")


@pytest.fixture
def admin(make_user):
    return make_user(roles=("community_admin",), email="admin@example.com")


@pytest.fixture
def member(make_user):
    user = active(make_user, "kofi@example.com")
    FounderProfile.objects.update_or_create(
        user=user, defaults={"full_name": "Kofi Mensah", "slug": "kofi-mensah"}
    )
    return user


@pytest.fixture
def member_client(member, client_for):
    return client_for(member)


@pytest.fixture
def course(editor):
    return build_course(
        editor, title="Raising your first round", subtitle="From first call to close."
    )


# --- the brief anyone may see ---


def test_a_published_course_has_a_brief_and_a_draft_has_none(api_client, editor, course):
    card = api_client.get(f"{CARD}/course/{course.slug}").json()
    assert card["title"] == "Raising your first round"
    assert card["excerpt"] == "From first call to close."
    assert card["url"] == f"/app/learn/courses/{course.slug}"
    assert card["action"] == "View course" and "3 lectures" in card["facts"]
    assert "lessons" not in card and "modules" not in card  # the brief, not the course
    draft = build_course(editor, title="Not ready", publish=False)
    assert api_client.get(f"{CARD}/course/{draft.slug}").status_code == 404


def test_an_event_brief_says_when_and_where_but_never_how_to_join(api_client, admin):
    event = make_event(admin)
    card = api_client.get(f"{CARD}/event/{event.pk}").json()
    assert card["title"] == "Pitch practice workshop" and card["badge"] == "Workshop"
    assert "Yaba, Lagos" in card["facts"] and any("WAT" in f for f in card["facts"])
    assert "meet.example.com" not in str(card)
    draft = make_event(admin, publish=False, title="Later")
    assert api_client.get(f"{CARD}/event/{draft.pk}").status_code == 404


def test_a_post_for_every_member_can_be_shared_and_one_for_some_cannot(
    api_client, member, member_client
):
    post_id = member_client.post(
        POSTS, {"category": "win", "body": "<p>We closed our seed round!</p>"}, format="json"
    ).json()["id"]
    card = api_client.get(f"{CARD}/post/{post_id}").json()
    assert card["title"] == "Kofi Mensah shared a win" and card["badge"] == "Celebration"
    assert card["excerpt"] == "We closed our seed round!"
    Post.objects.filter(pk=post_id).update(audience_roles=["mentor"])
    assert api_client.get(f"{CARD}/post/{post_id}").status_code == 404
    Post.objects.filter(pk=post_id).update(audience_roles=[], hidden_at=timezone.now())
    assert api_client.get(f"{CARD}/post/{post_id}").status_code == 404


def test_an_author_who_keeps_their_name_private_is_not_named(api_client, member, member_client):
    FounderProfile.objects.filter(user=member).update(visibility={"basics": "members"})
    post_id = member_client.post(
        POSTS, {"category": "update", "body": "<p>Hiring soon.</p>"}, format="json"
    ).json()["id"]
    card = api_client.get(f"{CARD}/post/{post_id}").json()
    assert "Kofi" not in str(card) and card["title"] == "Community member shared an update"


# --- in the feed ---


def test_a_course_is_shared_to_the_feed_as_a_card(member_client, course):
    response = member_client.post(
        POSTS,
        {"category": "resource", "body": "", "share": {"kind": "course", "ref": course.slug}},
        format="json",
    )
    assert response.status_code == 201, response.content
    post = response.json()
    assert post["shared"]["title"] == "Raising your first round"
    assert post["shared"]["url"] == f"/app/learn/courses/{course.slug}"
    assert "Sharing this course" in post["body"] and post["shareable"] is True
    feed = member_client.get(POSTS).json()["results"]
    assert feed[0]["shared"]["kind"] == "course"


def test_a_draft_cannot_be_shared_and_one_taken_down_later_says_so(member_client, editor, course):
    draft = build_course(editor, title="Not ready", publish=False)
    refused = member_client.post(
        POSTS,
        {"category": "resource", "body": "", "share": {"kind": "course", "ref": draft.slug}},
        format="json",
    )
    assert refused.status_code == 400 and "share" in refused.json()["errors"]
    post_id = member_client.post(
        POSTS,
        {
            "category": "resource",
            "body": "<p>Take this</p>",
            "share": {"kind": "course", "ref": course.slug},
        },
        format="json",
    ).json()["id"]
    Course.objects.filter(pk=course.pk).update(status=Course.Status.DRAFT)
    post = member_client.get(f"{POSTS}/{post_id}").json()
    assert post["shared"] is None and post["shared_gone"] is True


# --- the link shared outside ---


def test_the_shared_link_gives_a_preview_and_sends_people_to_the_teaser(course, settings):
    settings.FRONTEND_BASE_URL = "https://community.example"
    page = Client().get(f"/s/course/{course.slug}")
    html = page.content.decode()
    assert page.status_code == 200 and page["Content-Type"].startswith("text/html")
    assert '<meta property="og:title" content="Raising your first round">' in html
    assert f'content="https://community.example/s/course/{course.slug}"' in html
    assert f"url=https://community.example/p/course/{course.slug}" in html
    assert "script-src 'nonce-" in page["Content-Security-Policy"]


def test_words_in_a_shared_title_cannot_break_the_page(editor):
    sneaky = build_course(editor, title='Sales & "growth" "><b>')
    html = Client().get(f"/s/course/{sneaky.slug}").content.decode()
    assert '<meta property="og:title" content="Sales &amp; &quot;growth&quot; &quot;&gt;">' in html


def test_a_link_to_nothing_goes_home(settings):
    settings.FRONTEND_BASE_URL = "https://community.example"
    page = Client().get("/s/course/no-such-course")
    assert page.status_code == 404 and "url=https://community.example/" in page.content.decode()


def test_an_admin_shares_a_course_as_the_team_pinned(client_for, admin, course):
    response = client_for(admin, mfa_age=5).post(
        "/api/v1/admin/posts",
        {
            "category": "resource",
            "body": "",
            "share": {"kind": "course", "ref": course.slug},
            "official": True,
            "pin": True,
        },
        format="json",
    )
    assert response.status_code == 201, response.content
    post = Post.objects.get(pk=response.json()["id"])
    assert post.official and post.pinned_at is not None
    assert (post.shared_kind, post.shared_ref) == ("course", course.slug)
