import json

import pytest
from django.utils import timezone

from apps.accounts import services as accounts
from apps.core import etag
from apps.core.visibility import Audience
from apps.directory import services
from apps.directory.models import PublicFounder, PublicStartup
from apps.directory.tests.conftest import (
    FOUNDERS,
    SITEMAP,
    STARTUPS,
    edit_profile,
    edit_startup,
    make_member,
    set_startup_levels,
    slugs,
)
from apps.integrations.cdn.fake import FakePurger
from apps.profiles import services as profile_services
from apps.profiles.models import FounderProfile
from apps.startups import selectors as startup_selectors
from apps.startups import services as startup_services
from apps.startups.models import Startup
from apps.startups.tests.conftest import new_startup_body

pytestmark = pytest.mark.django_db


def startup_url(slug):
    return f"{STARTUPS}/{slug}"


def founder_url(slug):
    return f"{FOUNDERS}/{slug}"


def founder_slug_of(client, fixture):
    return client.get(startup_url(fixture.slug)).json()["founders"][0]["slug"]


# --- startup page ---


def test_the_startup_page_shows_what_the_owner_made_public(api_client, listed):
    fixture = listed("Acme Pay", description="ZZDESCRIPTION we move money")
    body = api_client.get(startup_url(fixture.slug)).json()
    assert body["name"] == "Acme Pay"
    assert body["description"] == "ZZDESCRIPTION we move money"
    assert body["website_url"] == "https://acme.example.com"
    assert body["year_founded"] == 2022
    assert body["url"].endswith(f"/startups/{fixture.slug}")
    assert body["founders"][0]["full_name"] == "Ada Obi"


def test_the_page_is_cacheable_and_conditional(api_client, listed):
    fixture = listed()
    first = api_client.get(startup_url(fixture.slug))
    assert "max-age=300" in first["Cache-Control"]
    assert (
        api_client.get(startup_url(fixture.slug), HTTP_IF_NONE_MATCH=first["ETag"]).status_code
        == 304
    )


def test_unknown_and_unlisted_startups_are_404(api_client, listed):
    hidden = listed("Hidden Co", listed=False)
    assert api_client.get(startup_url("no-such-startup")).status_code == 404
    assert api_client.get(startup_url(hidden.slug)).status_code == 404


def test_a_private_description_or_website_is_absent_from_the_page(api_client, listed):
    fixture = listed(description_public=False)
    set_startup_levels(fixture.id, website="members")
    from apps.core.models import OutboxEvent  # noqa: F401  (events are run by the fixture below)

    services.refresh_startup(fixture.id)
    body = api_client.get(startup_url(fixture.slug)).json()
    assert "description" not in body and "website_url" not in body
    assert "ZZDESCRIPTION" not in json.dumps(body)


def test_only_public_traction_is_shown_and_without_internal_fields(api_client, listed, run_outbox):
    fixture = listed()
    startup_services.replace_traction(
        user_id=fixture.user.pk,
        startup_id=fixture.id,
        items=[
            {"kind": "users", "value": 1200, "visibility": "public"},
            {"kind": "revenue_range", "value": "10k_50k", "visibility": "members"},
            {"kind": "funding_range", "value": "1m_5m", "visibility": "private"},
        ],
        if_match=etag.etag_for(Startup.objects.get(pk=fixture.id)),
    )
    run_outbox()
    traction = api_client.get(startup_url(fixture.slug)).json()["traction"]
    assert traction == [{"kind": "users", "value": 1200, "as_of_date": traction[0]["as_of_date"]}]


def test_the_page_carries_schema_org_data_built_from_public_fields_only(api_client, listed):
    fixture = listed("Acme Pay", pitch="Payments for small traders")
    data = api_client.get(startup_url(fixture.slug)).json()["structured_data"]
    assert data["@context"] == "https://schema.org" and data["@type"] == "Organization"
    assert data["name"] == "Acme Pay"
    assert data["description"] == "Payments for small traders"
    assert data["address"] == {
        "@type": "PostalAddress",
        "addressCountry": "NG",
        "addressLocality": "Lagos",
    }
    assert data["foundingDate"] == "2022"
    assert data["sameAs"] == ["https://acme.example.com"]
    assert data["url"].endswith(f"/startups/{fixture.slug}")


def test_structured_data_leaves_out_a_website_that_is_not_public(api_client, listed):
    fixture = listed()
    set_startup_levels(fixture.id, website="members")
    services.refresh_startup(fixture.id)
    data = api_client.get(startup_url(fixture.slug)).json()["structured_data"]
    assert "sameAs" not in data


# --- founder page ---


def test_the_founder_page_shows_only_the_groups_made_public(api_client, listed):
    fixture = listed(founder="Ada Obi", skills=("payments", "sales"))
    slug = founder_slug_of(api_client, fixture)
    body = api_client.get(founder_url(slug)).json()
    assert body["full_name"] == "Ada Obi"
    assert [s["slug"] for s in body["skills"]] == ["payments", "sales"] or {
        s["slug"] for s in body["skills"]
    } == {"payments", "sales"}
    assert "bio" not in body  # the bio group is still members-only
    assert "ZZBIO" not in json.dumps(body)
    assert "linkedin_url" not in body


def test_making_more_groups_public_widens_the_page(api_client, listed, run_outbox):
    fixture = listed()
    slug = founder_slug_of(api_client, fixture)
    profile_services.update_visibility(
        user_id=fixture.user.pk, levels={"bio": "public", "location": "public"}
    )
    run_outbox()
    body = api_client.get(founder_url(slug)).json()
    assert body["bio"] == "ZZBIO builds things"
    assert body["city"] == "Lagos" and body["country"] == "NG"


def test_the_founder_page_lists_their_listed_startups(api_client, listed):
    fixture = listed("Acme Pay")
    slug = founder_slug_of(api_client, fixture)
    startups = api_client.get(founder_url(slug)).json()["startups"]
    assert [s["name"] for s in startups] == ["Acme Pay"]
    assert startups[0]["slug"] == fixture.slug


def test_a_startup_with_a_private_team_is_not_linked_from_the_founder_page(
    api_client, listed, run_outbox
):
    fixture = listed("Acme Pay")
    slug = founder_slug_of(api_client, fixture)
    set_startup_levels(fixture.id, team="members")
    run_outbox()
    body = api_client.get(founder_url(slug)).json()
    assert body["startups"] == []
    assert api_client.get(startup_url(fixture.slug)).json()["founders"] == []


def test_founder_pages_carry_schema_org_person_data(api_client, listed, run_outbox):
    fixture = listed("Acme Pay")
    slug = founder_slug_of(api_client, fixture)
    profile_services.update_visibility(user_id=fixture.user.pk, levels={"links": "public"})
    edit_profile(fixture.user.pk, linkedin_url="https://www.linkedin.com/in/adaobi")
    edit_profile(fixture.user.pk, headline="CEO at Acme Pay")
    run_outbox()
    data = api_client.get(founder_url(slug)).json()["structured_data"]
    assert data["@type"] == "Person" and data["name"] == "Ada Obi"
    assert data["jobTitle"] == "CEO at Acme Pay"
    assert data["sameAs"] == ["https://www.linkedin.com/in/adaobi"]
    assert data["worksFor"][0]["name"] == "Acme Pay"


def test_a_founder_who_keeps_their_basics_members_only_has_no_page(api_client, listed):
    fixture = listed(founder_public=False)
    assert api_client.get(FOUNDERS).json()["results"] == []
    assert api_client.get(startup_url(fixture.slug)).json()["founders"] == []


def test_unknown_founders_are_404(api_client):
    assert api_client.get(founder_url("nobody-1a2b3c")).status_code == 404


# --- keeping the read model in step ---


def test_an_edit_reaches_the_page_after_the_refresh_and_purges_the_cdn(
    api_client, listed, run_outbox
):
    fixture = listed("Acme Pay")
    edit_startup(fixture.id, pitch="A brand new pitch")
    assert api_client.get(startup_url(fixture.slug)).json()["pitch"] != "A brand new pitch"
    FakePurger.reset()
    run_outbox()
    assert api_client.get(startup_url(fixture.slug)).json()["pitch"] == "A brand new pitch"
    assert f"/api/v1/public/startups/{fixture.slug}" in FakePurger.purged
    assert "/api/v1/public/startups" in FakePurger.purged


def test_opting_out_takes_the_page_down(api_client, listed, run_outbox):
    fixture = listed()
    edit_startup(fixture.id, directory_opt_in=False)
    run_outbox()
    assert api_client.get(startup_url(fixture.slug)).status_code == 404
    assert PublicStartup.objects.count() == 0


def test_a_founder_edit_updates_the_cards_of_their_startups(api_client, listed, run_outbox):
    fixture = listed("Acme Pay", founder="Ada Obi")
    edit_profile(fixture.user.pk, full_name="Adaeze Obi")
    run_outbox()
    card = api_client.get(STARTUPS).json()["results"][0]
    assert card["founders"][0]["full_name"] == "Adaeze Obi"


def test_a_founder_hiding_their_basics_leaves_the_startup_but_not_the_other_way_round(
    api_client, listed, run_outbox
):
    fixture = listed()
    profile_services.update_visibility(user_id=fixture.user.pk, levels={"basics": "members"})
    run_outbox()
    assert api_client.get(FOUNDERS).json()["results"] == []
    card = api_client.get(STARTUPS).json()["results"][0]
    assert card["founders"] == []
    assert api_client.get(startup_url(fixture.slug)).status_code == 200


def test_a_member_removed_from_the_team_loses_their_link(api_client, listed, make_user, run_outbox):
    fixture = listed("Acme Pay")
    cofounder = make_member(make_user, "co@example.com")
    profile_services.create_from_signup(
        cofounder.pk, {"full_name": "Chioma Eze", "country": "NG", "city": "Abuja"}
    )
    profile_services.update_visibility(user_id=cofounder.pk, levels={"basics": "public"})
    member = startup_services.add_team_member(
        owner_id=fixture.user.pk,
        startup_id=fixture.id,
        email="co@example.com",
        title="CTO",
        is_founder=True,
    )
    run_outbox()
    names = [f["full_name"] for f in api_client.get(startup_url(fixture.slug)).json()["founders"]]
    assert set(names) == {"Ada Obi", "Chioma Eze"}
    startup_services.remove_team_member(
        actor_id=fixture.user.pk, startup_id=fixture.id, member_id=member.pk
    )
    run_outbox()
    names = [f["full_name"] for f in api_client.get(startup_url(fixture.slug)).json()["founders"]]
    assert names == ["Ada Obi"]
    linked = PublicFounder.objects.get(user_id=cofounder.pk).detail["startups"]
    assert linked == []


def test_refreshing_twice_changes_nothing(listed):
    fixture = listed()
    before = PublicStartup.objects.get().detail
    services.refresh_startup(fixture.id)
    services.refresh_startup(fixture.id)
    assert PublicStartup.objects.count() == 1
    assert PublicStartup.objects.get().detail == before


# --- takedown ---


@pytest.mark.parametrize("status", ["suspended", "removed"])
def test_a_suspended_or_removed_owner_disappears_at_once(api_client, listed, status):
    fixture = listed()
    assert api_client.get(startup_url(fixture.slug)).status_code == 200
    slug = founder_slug_of(api_client, fixture)
    fixture.user.status = status
    fixture.user.save()  # nothing has been refreshed yet
    assert api_client.get(startup_url(fixture.slug)).status_code == 404
    assert api_client.get(founder_url(slug)).status_code == 404
    assert api_client.get(STARTUPS).json()["results"] == []
    assert api_client.get(FOUNDERS).json()["results"] == []
    assert api_client.get(SITEMAP).json() == {"startups": [], "founders": []}


def test_removal_by_an_admin_deletes_the_rows_and_purges_the_cdn(
    api_client, listed, run_outbox, make_user
):
    admin = make_user(roles=("community_admin",), email="admin@example.com")
    fixture = listed()
    FakePurger.reset()
    accounts.remove_member(actor=admin, user_id=fixture.user.pk, reason="breach of terms")
    run_outbox()
    assert PublicStartup.objects.count() == 0 and PublicFounder.objects.count() == 0
    assert f"/api/v1/public/startups/{fixture.slug}" in FakePurger.purged


def test_reinstating_brings_the_pages_back(api_client, listed, run_outbox, make_user):
    admin = make_user(roles=("community_admin",), email="admin@example.com")
    fixture = listed()
    accounts.suspend_member(actor=admin, user_id=fixture.user.pk, reason="review")
    run_outbox()
    assert api_client.get(startup_url(fixture.slug)).status_code == 404
    accounts.reinstate_member(actor=admin, user_id=fixture.user.pk)
    run_outbox()
    assert api_client.get(startup_url(fixture.slug)).status_code == 200


def test_pending_members_are_never_listed(api_client, listed, make_user, run_outbox):
    pending = make_user(email="pending@example.com", status="pending")
    profile_services.create_from_signup(
        pending.pk, {"full_name": "Not Yet", "country": "NG", "city": "Lagos"}
    )
    startup = startup_services.create_startup(
        owner_id=pending.pk, data={**new_startup_body(name="Pending Co"), "year_founded": 2020}
    )
    edit_startup(startup.pk, directory_opt_in=True)
    run_outbox()
    assert api_client.get(STARTUPS).json()["results"] == []


def test_a_member_removed_from_a_team_they_did_not_own_only_leaves_that_team(
    api_client, listed, make_user, run_outbox
):
    admin = make_user(roles=("community_admin",), email="admin@example.com")
    fixture = listed("Acme Pay")
    other = make_member(make_user, "other@example.com")
    profile_services.create_from_signup(
        other.pk, {"full_name": "Other Person", "country": "NG", "city": "Abuja"}
    )
    profile_services.update_visibility(user_id=other.pk, levels={"basics": "public"})
    startup_services.add_team_member(
        owner_id=fixture.user.pk,
        startup_id=fixture.id,
        email="other@example.com",
        title="CTO",
        is_founder=True,
    )
    run_outbox()
    accounts.remove_member(actor=admin, user_id=other.pk, reason="left")
    run_outbox()
    assert api_client.get(startup_url(fixture.slug)).status_code == 200
    names = [f["full_name"] for f in api_client.get(startup_url(fixture.slug)).json()["founders"]]
    assert names == ["Ada Obi"]


# --- consistency with the sources (AC-17) ---


def test_the_read_model_never_holds_more_than_the_public_projection(listed):
    fixture = listed(description_public=False)
    row = PublicStartup.objects.get()
    projection = startup_selectors.project_startup(
        startup_selectors.get_startup(fixture.id), Audience.PUBLIC
    )
    assert "description" not in projection
    assert "description" not in row.detail
    assert row.description == ""
    stored = json.dumps(row.detail) + json.dumps(row.card)
    assert "ZZDESCRIPTION" not in stored


def test_stored_text_columns_never_contain_private_values(listed):
    listed(description_public=False)
    row = PublicStartup.objects.get()
    everything = " ".join(
        str(getattr(row, f))
        for f in ("description", "founder_names", "skill_names", "city", "pitch", "name")
    )
    assert "ZZDESCRIPTION" not in everything
    founder = PublicFounder.objects.get()
    assert "ZZBIO" not in " ".join([founder.bio, founder.headline, founder.skill_names])


# --- sitemap ---


def test_the_sitemap_lists_every_public_page_with_a_last_change(api_client, listed):
    one = listed("One Co")
    listed("Two Co", listed=False)
    body = api_client.get(SITEMAP).json()
    assert [e["slug"] for e in body["startups"]] == [one.slug]
    assert body["startups"][0]["path"] == f"/startups/{one.slug}"
    assert body["startups"][0]["lastmod"]
    assert len(body["founders"]) == 2  # a founder's page does not depend on a listing
    response = api_client.get(SITEMAP)
    assert "max-age=3600" in response["Cache-Control"]


def test_the_sitemap_rejects_stray_parameters(api_client):
    assert api_client.get(SITEMAP, {"type": "all"}).status_code == 400


# --- rebuilding ---


def test_reconcile_repairs_missing_and_stale_rows(api_client, listed):
    fixture = listed("Acme Pay")
    PublicStartup.objects.all().delete()  # a lost row
    PublicStartup.objects.create(
        startup_id="00000000-0000-0000-0000-000000000001",
        owner_id=fixture.user.pk,
        slug="ghost",
        name="Ghost",
        country="NG",
        sector_slug="fintech",
        stage_slug="seed",
        newest_key=0,
        name_key="ghost",
        pitch="x",
        source_updated_at=timezone.now(),
    )  # a row whose source no longer exists
    result = services.reconcile()
    assert result["removed"] == 1
    assert [c["name"] for c in api_client.get(STARTUPS).json()["results"]] == ["Acme Pay"]


def test_the_rebuild_command_runs(listed, capsys):
    from django.core.management import call_command

    listed()
    PublicStartup.objects.all().delete()
    call_command("rebuild_directory")
    assert PublicStartup.objects.count() == 1
    assert "1 startups" in capsys.readouterr().out


def test_profile_rows_without_a_public_basics_group_are_not_built(listed):
    listed(founder_public=False)
    assert FounderProfile.objects.count() == 1
    assert PublicFounder.objects.count() == 0
    assert slugs is not None
