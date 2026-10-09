import itertools
import json

import pytest
from django.utils import timezone

from apps.core.visibility import Audience, can_see
from apps.startups import domain, selectors
from apps.startups.tests.conftest import MARKERS, detail, etag_of, set_levels

pytestmark = pytest.mark.django_db

GROUPS = list(domain.GROUP_FIELDS)
LEVELS = ["private", "members", "public"]


def view(client, startup_id):
    return client.get(detail(startup_id))


# --- who can see what by default ---


def test_other_members_see_a_startup_at_the_default_levels(stranger_client, startup_id):
    body = view(stranger_client, startup_id).json()
    assert body["name"] == "ZZSTARTUP Pay"
    assert body["description"].startswith("ZZDESCRIPTION")
    assert body["website_url"] == "https://zzsite.example.com"


def test_other_members_never_see_owner_only_fields(stranger_client, startup_id):
    body = view(stranger_client, startup_id).json()
    for owner_only in ("owner_id", "directory_opt_in", "visibility", "completeness"):
        assert owner_only not in body


def test_the_owner_sees_the_settings(owner_client, startup_id):
    body = view(owner_client, startup_id).json()
    assert {"owner_id", "directory_opt_in", "visibility", "completeness"} <= set(body)


def test_unknown_startups_are_404(stranger_client):
    missing = "00000000-0000-0000-0000-000000000000"
    assert view(stranger_client, missing).status_code == 404


def test_pending_accounts_see_what_a_visitor_sees(owner_client, startup_id, make_user, client_for):
    pending = client_for(make_user(email="pending@example.com", status="pending"))
    assert view(pending, startup_id).status_code == 404  # basics are members-only by default
    set_levels(owner_client, startup_id, {"basics": "public"})
    body = view(pending, startup_id).json()
    assert body["name"] == "ZZSTARTUP Pay"
    assert "description" not in body


# --- hiding ---


def test_hiding_the_basics_hides_the_whole_startup(owner_client, stranger_client, startup_id):
    set_levels(owner_client, startup_id, {"basics": "private"})
    response = view(stranger_client, startup_id)
    assert response.status_code == 404
    assert "ZZ" not in response.content.decode()
    assert view(owner_client, startup_id).status_code == 200


def test_a_private_group_is_absent_not_blank(owner_client, stranger_client, startup_id):
    set_levels(owner_client, startup_id, {"description": "private", "website": "private"})
    body = view(stranger_client, startup_id).json()
    assert "description" not in body and "website_url" not in body
    assert "ZZDESCRIPTION" not in json.dumps(body)


def test_changes_apply_to_the_next_read(owner_client, stranger_client, startup_id):
    set_levels(owner_client, startup_id, {"description": "private"})
    assert "description" not in view(stranger_client, startup_id).json()
    set_levels(owner_client, startup_id, {"description": "members"})
    assert "description" in view(stranger_client, startup_id).json()


@pytest.mark.parametrize(
    "body", [{}, {"basics": "everyone"}, {"logo": "public"}, {"basics": 1}, []]
)
def test_invalid_visibility_changes_are_rejected(owner_client, startup_id, body):
    assert set_levels(owner_client, startup_id, body).status_code == 400


def test_only_editors_can_change_visibility(stranger_client, startup_id):
    response = stranger_client.patch(
        f"{detail(startup_id)}/visibility",
        {"basics": "public"},
        HTTP_IF_MATCH=etag_of(stranger_client, startup_id),
    )
    assert response.status_code == 404


def test_visibility_changes_need_the_etag(owner_client, startup_id):
    response = owner_client.patch(f"{detail(startup_id)}/visibility", {"description": "public"})
    assert response.status_code == 428


# --- the exhaustive check (AC-17) ---


@pytest.mark.parametrize(("group", "level"), itertools.product(GROUPS, LEVELS))
@pytest.mark.parametrize("audience", [Audience.PUBLIC, Audience.MEMBER, Audience.OWNER])
def test_every_group_obeys_its_level_for_every_audience(
    owner_client, startup_id, group, level, audience
):
    if group != "basics":
        set_levels(owner_client, startup_id, {"basics": "public"})
    set_levels(owner_client, startup_id, {group: level})
    startup = selectors.get_startup(startup_id)
    result = selectors.project_startup(startup, audience)
    visible = can_see(level, audience)
    if group == "basics" and not visible:
        assert result is None
        return
    assert result is not None
    if group in MARKERS:
        assert (MARKERS[group] in json.dumps(result, default=str)) is visible


@pytest.mark.parametrize("audience", [Audience.PUBLIC, Audience.MEMBER])
def test_a_private_startup_leaks_nothing_to_anyone_else(owner_client, startup_id, audience):
    set_levels(owner_client, startup_id, dict.fromkeys(GROUPS, "private"))
    startup = selectors.get_startup(startup_id)
    assert selectors.project_startup(startup, audience) is None


def test_a_startup_with_only_public_basics_shows_a_visitor_nothing_else(owner_client, startup_id):
    set_levels(owner_client, startup_id, {"basics": "public"})
    public = selectors.project_startup(selectors.get_startup(startup_id), Audience.PUBLIC)
    text = json.dumps(public, default=str)
    assert "ZZSTARTUP" in text
    assert "ZZDESCRIPTION" not in text and "zzsite" not in text
    assert public["traction"] == []
    assert "team" not in public


# --- the team list ---


def test_the_team_list_shows_only_linked_members_to_others(
    owner_client, startup_id, stranger, make_user, client_for
):
    watcher = client_for(
        make_user(email="watcher@example.com", approved_at=timezone.now())
    )  # an approved member who is not on the team
    owner_client.post(f"{detail(startup_id)}/team", {"email": stranger.email, "title": "CTO"})
    owner_client.post(f"{detail(startup_id)}/team", {"email": "not.joined@example.com"})
    body = view(watcher, startup_id).json()
    assert {m["title"] for m in body["team"]} == {"Founder", "CTO"}
    assert "not.joined@example.com" not in json.dumps(body)
    assert all("email" not in m for m in body["team"])


def test_a_private_team_group_hides_the_list(owner_client, stranger_client, startup_id):
    set_levels(owner_client, startup_id, {"team": "private"})
    assert "team" not in view(stranger_client, startup_id).json()


# --- cost ---


def test_viewing_a_startup_uses_a_fixed_number_of_queries(
    owner_client, stranger_client, startup_id, django_assert_max_num_queries
):
    for n in range(4):
        owner_client.post(f"{detail(startup_id)}/team", {"email": f"m{n}@example.com"})
    with django_assert_max_num_queries(8):
        assert view(stranger_client, startup_id).status_code == 200
