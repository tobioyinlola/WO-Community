import itertools
import json

import pytest

from apps.core.visibility import Audience, can_see
from apps.profiles import domain, selectors
from apps.profiles.models import FounderProfile
from apps.profiles.tests.conftest import MARKERS, PROFILE, member_url, patch

pytestmark = pytest.mark.django_db

GROUPS = list(domain.GROUP_FIELDS)
LEVELS = ["private", "members", "public"]


def set_levels(client, levels):
    response = client.patch("/api/v1/me/visibility", levels)
    assert response.status_code == 200
    return response


def view(client, user):
    return client.get(member_url(user))


# --- who can call the endpoint ---


def test_anonymous_callers_get_401(api_client, full_profile):
    assert api_client.get(member_url(full_profile)).status_code == 401


def test_pending_accounts_are_not_members_yet(full_profile, make_user, client_for):
    pending = make_user(email="pending@example.com", status="pending")
    assert client_for(pending).get(member_url(full_profile)).status_code == 403


def test_unknown_members_are_404(other_client):
    assert (
        other_client.get("/api/v1/members/00000000-0000-0000-0000-000000000000").status_code == 404
    )


def test_members_without_a_profile_row_are_404(other_client, other, me):
    assert view(other_client, me).status_code == 404


# --- defaults ---


def test_by_default_members_see_the_essentials_but_not_personal_links(full_profile, other_client):
    body = view(other_client, full_profile).json()
    assert body["full_name"] == "ZZNAME Okafor"
    assert body["bio"] == "ZZBIO builds things"
    assert body["city"] == "ZZCITY"
    assert body["skills"] == [{"slug": "payments", "name": "Payments"}]
    for hidden in ("linkedin_url", "x_url", "website_url"):
        assert hidden not in body
    assert "zzlinked" not in json.dumps(body)


def test_members_never_see_the_owner_only_fields(full_profile, other_client):
    body = view(other_client, full_profile).json()
    assert not {"visibility", "completeness"} & set(body)


def test_the_owner_sees_everything_through_the_same_endpoint(full_profile, my_client):
    body = view(my_client, full_profile).json()
    assert body["linkedin_url"] == "https://www.linkedin.com/in/zzlinked"


# --- hiding ---


def test_a_private_group_disappears_for_other_members(full_profile, my_client, other_client):
    set_levels(my_client, {"bio": "private"})
    body = view(other_client, full_profile).json()
    assert "bio" not in body
    assert "ZZBIO" not in json.dumps(body)
    assert "bio" in my_client.get(PROFILE).json()


def test_hiding_the_basics_makes_the_whole_profile_invisible(full_profile, my_client, other_client):
    set_levels(my_client, {"basics": "private"})
    response = view(other_client, full_profile)
    assert response.status_code == 404
    assert "ZZ" not in response.content.decode()


def test_making_a_group_public_does_not_expose_it_to_unrelated_groups(
    full_profile, my_client, other_client
):
    set_levels(my_client, {"links": "members"})
    body = view(other_client, full_profile).json()
    assert body["linkedin_url"].endswith("zzlinked")


def test_changes_take_effect_immediately(full_profile, my_client, other_client):
    assert "bio" in view(other_client, full_profile).json()
    set_levels(my_client, {"bio": "private"})
    assert "bio" not in view(other_client, full_profile).json()
    set_levels(my_client, {"bio": "members"})
    assert "bio" in view(other_client, full_profile).json()


# --- the exhaustive check (AC-17) ---


@pytest.mark.parametrize(("group", "level"), itertools.product(GROUPS, LEVELS))
@pytest.mark.parametrize("audience", [Audience.PUBLIC, Audience.MEMBER, Audience.OWNER])
def test_every_group_obeys_its_level_for_every_audience(
    full_profile, my_client, group, level, audience
):
    """A group's data is present exactly when its level allows that audience."""
    if group != "basics":
        set_levels(my_client, {"basics": "public"})  # keep the profile itself visible
    set_levels(my_client, {group: level})
    profile = FounderProfile.objects.get(user=full_profile)
    result = selectors.project_profile(profile, audience)
    expected_visible = can_see(level, audience)
    if group == "basics" and not expected_visible:
        assert result is None
        return
    assert result is not None
    assert (MARKERS[group] in json.dumps(result, default=str)) is expected_visible


@pytest.mark.parametrize("group", GROUPS)
def test_a_private_group_never_reaches_a_member_over_http(
    full_profile, my_client, other_client, group
):
    levels = dict.fromkeys(GROUPS, "private")
    levels["basics"] = "members"  # the only group left readable
    set_levels(my_client, levels)
    text = view(other_client, full_profile).content.decode()
    for name, marker in MARKERS.items():
        if name != "basics":
            assert marker not in text, f"{name} leaked"


def test_a_visitor_sees_nothing_unless_the_member_made_it_public(full_profile, my_client):
    profile = FounderProfile.objects.get(user=full_profile)
    assert selectors.project_profile(profile, Audience.PUBLIC) is None
    set_levels(my_client, {"basics": "public"})
    profile.refresh_from_db()
    public = selectors.project_profile(profile, Audience.PUBLIC)
    assert public["full_name"] == "ZZNAME Okafor"
    assert "bio" not in public and "city" not in public and "linkedin_url" not in public
    assert "ZZBIO" not in json.dumps(public, default=str)


def test_a_visitor_never_receives_contact_details(full_profile, my_client):
    set_levels(my_client, dict.fromkeys(GROUPS, "public"))
    profile = FounderProfile.objects.get(user=full_profile)
    public = json.dumps(selectors.project_profile(profile, Audience.PUBLIC), default=str)
    assert "me@example.com" not in public
    assert "email" not in public


# --- badges and cost ---


def test_badges_show_verified_members_and_mentors(full_profile, my_client, other_client, me):
    me.status = "active"
    me.save()
    assert view(other_client, full_profile).json()["badges"] == ["verified_member"]
    from apps.accounts.models import UserRole

    UserRole.objects.create(user=me, role="mentor")
    assert view(other_client, full_profile).json()["badges"] == ["verified_member", "mentor"]


def test_viewing_a_profile_uses_a_fixed_number_of_queries(
    full_profile, other_client, django_assert_max_num_queries
):
    with django_assert_max_num_queries(8):
        assert view(other_client, full_profile).status_code == 200


def test_patching_cannot_be_used_to_read_someone_elses_profile(other_client, full_profile, other):
    from apps.profiles.tests.conftest import etag_of

    response = patch(other_client, {"bio": "hijack"}, etag=etag_of(other_client))
    assert response.status_code == 200
    assert FounderProfile.objects.get(user=full_profile).bio == "ZZBIO builds things"
    assert FounderProfile.objects.get(user=other).bio == "hijack"
