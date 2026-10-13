import pytest

from apps.reference import selectors
from apps.reference.models import Sector

pytestmark = pytest.mark.django_db


@pytest.mark.parametrize("name", ["sectors", "stages", "skills", "countries"])
def test_lists_are_public_and_cacheable(api_client, name):
    response = api_client.get(f"/api/v1/reference/{name}")
    assert response.status_code == 200
    assert response["Cache-Control"] == "public, max-age=3600"
    assert len(response.json()) > 5


def test_seeded_sectors_and_stages_cover_the_registration_form(api_client):
    sectors = {i["slug"] for i in api_client.get("/api/v1/reference/sectors").json()}
    stages = [i["slug"] for i in api_client.get("/api/v1/reference/stages").json()]
    assert {"fintech", "healthtech", "agritech", "other"} <= sectors
    assert stages[:3] == ["idea", "pre-seed", "seed"]  # kept in life-cycle order


def test_countries_use_iso_codes_sorted_by_name(api_client):
    countries = api_client.get("/api/v1/reference/countries").json()
    codes = {c["code"] for c in countries}
    assert {"NG", "GB", "KE", "ZA", "GH", "US"} <= codes
    names = [c["name"] for c in countries]
    assert names == sorted(names)
    assert len(codes) == len(countries) >= 240


def test_inactive_entries_are_hidden_from_the_lists_and_lookups(api_client):
    Sector.objects.filter(slug="gaming").update(active=False)
    slugs = {i["slug"] for i in api_client.get("/api/v1/reference/sectors").json()}
    assert "gaming" not in slugs
    assert selectors.get_sector("gaming") is None
    assert selectors.get_sector("fintech") is not None


def test_country_helpers():
    assert selectors.is_country("NG") and not selectors.is_country("XX")
    assert not selectors.is_country("ng")  # codes are stored upper case
    assert selectors.country_name("NG") == "Nigeria"


def test_skill_lookup_ignores_unknown_slugs():
    found = selectors.skills_by_slug(["payments", "no-such-skill"])
    assert [s.slug for s in found] == ["payments"]
