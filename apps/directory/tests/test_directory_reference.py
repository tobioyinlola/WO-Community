import pytest

from apps.directory.models import PublicStartup
from apps.directory.tests.conftest import FOUNDERS, STARTUPS
from apps.integrations.cdn.fake import FakePurger
from apps.reference.models import Sector, Skill, Stage

pytestmark = pytest.mark.django_db

ADMIN = "/api/v1/admin/reference"


@pytest.fixture
def as_admin(make_user, client_for):
    admin = make_user(roles=("community_admin",), email="admin@example.com")
    return client_for(admin, mfa_age=5)


def rename(client, kind, model, slug, name):
    item = model.objects.get(slug=slug)
    response = client.patch(f"{ADMIN}/{kind}/{item.pk}", {"name": name})
    assert response.status_code == 200
    return response


def card(api_client):
    return api_client.get(STARTUPS).json()["results"][0]


def test_renaming_a_sector_updates_the_public_card_and_page(
    api_client, as_admin, listed, run_outbox
):
    fixture = listed("Acme Pay", sector="fintech")
    assert card(api_client)["sector"]["name"] == "Fintech"
    rename(as_admin, "sectors", Sector, "fintech", "Financial technology")
    run_outbox()
    assert card(api_client)["sector"] == {"slug": "fintech", "name": "Financial technology"}
    page = api_client.get(f"{STARTUPS}/{fixture.slug}").json()
    assert page["sector"]["name"] == "Financial technology"


def test_the_new_name_is_searchable_and_the_old_one_is_not(
    api_client, as_admin, listed, run_outbox
):
    listed("Acme Pay", sector="fintech")
    rename(as_admin, "sectors", Sector, "fintech", "Money systems")
    run_outbox()
    found = api_client.get(STARTUPS, {"q": "systems"}).json()["results"]
    assert [c["name"] for c in found] == ["Acme Pay"]
    assert api_client.get(STARTUPS, {"q": "fintech"}).json()["results"] == []


def test_renaming_a_stage_updates_the_public_pages(api_client, as_admin, listed, run_outbox):
    fixture = listed("Acme Pay", stage="seed")
    rename(as_admin, "stages", Stage, "seed", "Seed round")
    run_outbox()
    assert card(api_client)["stage"]["name"] == "Seed round"
    assert api_client.get(f"{STARTUPS}/{fixture.slug}").json()["stage"]["name"] == "Seed round"


def test_renaming_a_skill_updates_founder_pages_and_startup_search(
    api_client, as_admin, listed, run_outbox
):
    listed("Acme Pay", skills=("payments",))
    rename(as_admin, "skills", Skill, "payments", "Payment rails")
    run_outbox()
    founder = api_client.get(FOUNDERS).json()["results"][0]
    assert founder["skills"] == [{"slug": "payments", "name": "Payment rails"}]
    assert [c["name"] for c in api_client.get(STARTUPS, {"q": "rails"}).json()["results"]] == [
        "Acme Pay"
    ]


def test_only_the_pages_that_show_the_entry_are_rebuilt(api_client, as_admin, listed, run_outbox):
    listed("Money Co", sector="fintech")
    listed("Care Co", sector="healthtech")
    untouched = PublicStartup.objects.get(name="Care Co")
    before = untouched.source_updated_at
    rename(as_admin, "sectors", Sector, "fintech", "Finance")
    run_outbox()
    untouched.refresh_from_db()
    assert untouched.source_updated_at == before
    assert PublicStartup.objects.get(name="Money Co").card["sector"]["name"] == "Finance"


def test_retiring_an_entry_does_not_take_a_listed_startup_down(
    api_client, as_admin, listed, run_outbox
):
    fixture = listed("Acme Pay", sector="gaming")
    item = Sector.objects.get(slug="gaming")
    as_admin.patch(f"{ADMIN}/sectors/{item.pk}", {"active": False})
    run_outbox()
    assert api_client.get(f"{STARTUPS}/{fixture.slug}").status_code == 200
    assert card(api_client)["sector"]["slug"] == "gaming"
    public_list = {e["slug"] for e in api_client.get("/api/v1/reference/sectors").json()}
    assert "gaming" not in public_list


def test_every_change_purges_the_cached_public_list(api_client, as_admin, listed, run_outbox):
    FakePurger.reset()
    as_admin.post(f"{ADMIN}/sectors", {"name": "Space"})
    run_outbox()
    assert "/api/v1/reference/sectors" in FakePurger.purged

    FakePurger.reset()
    ids = [e["id"] for e in as_admin.get(f"{ADMIN}/stages").json()]
    as_admin.put(f"{ADMIN}/stages/order", {"ids": list(reversed(ids))})
    run_outbox()
    assert FakePurger.purged == ["/api/v1/reference/stages"]


def test_adding_an_entry_rebuilds_no_pages(api_client, as_admin, listed, run_outbox):
    listed("Acme Pay")
    before = PublicStartup.objects.get().source_updated_at
    as_admin.post(f"{ADMIN}/skills", {"name": "Robotics"})
    run_outbox()
    assert PublicStartup.objects.get().source_updated_at == before
