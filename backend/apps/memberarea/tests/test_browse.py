from uuid import UUID

import pytest
from django.utils import timezone

from apps.feed import services as feed
from apps.jobs import services as jobs
from apps.jobs.models import JobSettings
from apps.profiles.models import FounderProfile
from apps.profiles.services import get_or_create_profile
from apps.startups.models import Startup
from apps.startups.tests.conftest import STARTUPS, new_startup_body

pytestmark = pytest.mark.django_db

BROWSE_STARTUPS = "/api/v1/directory/startups"
BROWSE_PEOPLE = "/api/v1/directory/members"
ACTIVITY = "/api/v1/feed/activity"


def member(make_user, email, name="", country="NG", **fields):
    user = make_user(
        email=email, approved_at=timezone.now(), email_verified_at=timezone.now(), **fields
    )
    profile = get_or_create_profile(user.pk)
    FounderProfile.objects.filter(pk=profile.pk).update(full_name=name, country=country)
    return user


@pytest.fixture
def viewer(make_user, client_for):
    return client_for(member(make_user, "viewer@example.com", "Vera Viewer"))


@pytest.fixture
def founders(make_user, client_for):
    ada = member(make_user, "ada@example.com", "Ada Founder")
    kofi = member(make_user, "kofi@example.com", "Kofi Founder", country="GH")
    return {
        "ada": ada,
        "kofi": kofi,
        "ada_client": client_for(ada),
        "kofi_client": client_for(kofi),
    }


def add_startup(client, **overrides):
    response = client.post(STARTUPS, new_startup_body(**overrides), format="json")
    assert response.status_code == 201, response.content
    return response.json()["id"]


def names(response):
    return [row["name"] for row in response.json()["results"]]


# --- startups ---


def test_a_startup_card_has_what_a_browser_needs(viewer, founders):
    add_startup(
        founders["ada_client"],
        name="Kuda Foods",
        pitch_deck_url="https://decks.example.com/kuda",
    )
    [card] = viewer.get(BROWSE_STARTUPS).json()["results"]
    assert card["name"] == "Kuda Foods"
    assert card["website_url"] == "https://zzsite.example.com"
    assert card["pitch_deck_url"] == "https://decks.example.com/kuda"
    assert card["sector"]["slug"] == "fintech" and card["stage"]["slug"] == "seed"
    assert card["open_jobs_count"] == 0 and card["open_jobs"] == []


def test_filters_narrow_the_list_and_combine(viewer, founders):
    add_startup(founders["ada_client"], name="Alpha", country="NG", sector="fintech", stage="seed")
    add_startup(
        founders["kofi_client"], name="Bravo", country="GH", sector="agritech", stage="idea"
    )
    assert sorted(names(viewer.get(BROWSE_STARTUPS))) == ["Alpha", "Bravo"]
    assert names(viewer.get(BROWSE_STARTUPS, {"country": "GH"})) == ["Bravo"]
    assert names(viewer.get(BROWSE_STARTUPS, {"sector": "fintech"})) == ["Alpha"]
    assert names(viewer.get(BROWSE_STARTUPS, {"stage": "idea"})) == ["Bravo"]
    assert names(viewer.get(BROWSE_STARTUPS, {"sector": "fintech", "country": "GH"})) == []
    assert names(viewer.get(BROWSE_STARTUPS, {"q": "alph"})) == ["Alpha"]


def test_results_are_paged_with_a_count(viewer, founders):
    for i in range(3):
        add_startup(founders["ada_client"], name=f"Startup {i}")
    first = viewer.get(BROWSE_STARTUPS, {"page_size": 2, "sort": "name"}).json()
    assert (first["count"], first["pages"], first["page"]) == (3, 2, 1)
    assert [r["name"] for r in first["results"]] == ["Startup 0", "Startup 1"]
    second = viewer.get(BROWSE_STARTUPS, {"page_size": 2, "sort": "name", "page": 2}).json()
    assert [r["name"] for r in second["results"]] == ["Startup 2"]


def test_a_startup_that_hides_its_basics_is_only_shown_to_its_owner(viewer, founders):
    startup_id = add_startup(founders["ada_client"], name="Hidden Co")
    Startup.objects.filter(pk=startup_id).update(visibility={"basics": "private"})
    assert names(viewer.get(BROWSE_STARTUPS)) == []
    assert names(founders["ada_client"].get(BROWSE_STARTUPS)) == ["Hidden Co"]


def test_hiring_lists_startups_with_a_live_job(viewer, founders):
    board = JobSettings.load()
    board.require_approval = False
    board.save()
    hiring = add_startup(founders["ada_client"], name="Hiring Co")
    add_startup(founders["kofi_client"], name="Quiet Co")
    jobs.create_job(
        user_id=founders["ada"].pk,
        data={
            "title": "Backend engineer",
            "type": "full_time",
            "location": "Lagos",
            "remote": True,
            "startup_id": UUID(hiring),
            "description": "<p>Join us and build with us from day one.</p>",
            "apply_method": "email",
            "apply_target": "jobs@example.com",
        },
    )
    rows = viewer.get(BROWSE_STARTUPS, {"hiring": "true"}).json()["results"]
    assert [r["name"] for r in rows] == ["Hiring Co"]
    assert (
        rows[0]["open_jobs_count"] == 1 and rows[0]["open_jobs"][0]["title"] == "Backend engineer"
    )


def test_browsing_needs_an_active_member(api_client):
    assert api_client.get(BROWSE_STARTUPS).status_code in (401, 403)
    assert api_client.get(BROWSE_PEOPLE).status_code in (401, 403)


# --- people ---


def test_people_are_filtered_by_country_and_paged(viewer, founders):
    rows = viewer.get(BROWSE_PEOPLE, {"country": "GH"}).json()
    assert rows["count"] == 1 and rows["results"][0]["name"] == "Kofi Founder"
    page = viewer.get(BROWSE_PEOPLE, {"page_size": 1, "sort": "name"}).json()
    assert page["pages"] == 3 and page["results"][0]["name"] == "Ada Founder"


# --- activity on the dashboard ---


def test_comments_and_reactions_show_in_the_activity_list(viewer, founders, make_user):
    author = founders["ada"]
    post = feed.create_post(user_id=author.pk, category="update", body="<p>News</p>", images=[])
    feed.add_comment(user_id=founders["kofi"].pk, post_id=post.pk, body="<p>Well done</p>")
    feed.react(user_id=founders["kofi"].pk, target_type="post", target_id=post.pk, kind="like")
    items = viewer.get(ACTIVITY).json()
    assert {i["kind"] for i in items} == {"comment", "reaction"}
    comment = next(i for i in items if i["kind"] == "comment")
    assert comment["detail"] == "Well done" and comment["actor"]["name"] == "Kofi Founder"
    assert comment["post_author"] == "Ada Founder" and comment["mine"] is False
    assert items == sorted(items, key=lambda i: i["created_at"], reverse=True)


def test_activity_on_a_hidden_post_is_not_shown(viewer, founders):
    post = feed.create_post(
        user_id=founders["ada"].pk, category="update", body="<p>Hush</p>", images=[]
    )
    feed.add_comment(user_id=founders["kofi"].pk, post_id=post.pk, body="<p>Secret</p>")
    post.hidden_at = timezone.now()
    post.save(update_fields=["hidden_at"])
    assert viewer.get(ACTIVITY).json() == []


def test_every_member_is_listed_except_those_who_hid_themselves(viewer, founders, make_user):
    hidden = member(make_user, "hidden@example.com", "Hana Hidden")
    FounderProfile.objects.filter(user_id=hidden.pk).update(visibility={"basics": "private"})
    member(make_user, "noname@example.com", "")
    shown = member(make_user, "members@example.com", "Mo Members")
    FounderProfile.objects.filter(user_id=shown.pk).update(visibility={"basics": "members"})
    page = viewer.get(BROWSE_PEOPLE, {"page_size": 2, "sort": "name"}).json()
    assert page["count"] == 4 and page["pages"] == 2 and len(page["results"]) == 2
    everyone = names(viewer.get(BROWSE_PEOPLE, {"page_size": 10, "sort": "name"}))
    assert everyone == ["Ada Founder", "Kofi Founder", "Mo Members", "Vera Viewer"]
