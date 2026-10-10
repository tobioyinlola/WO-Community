import uuid

import pytest
from django.db import IntegrityError, transaction
from django.db.models import ProtectedError

from apps.audit.models import AuditLog
from apps.core import etag
from apps.core.models import OutboxEvent
from apps.profiles import services as profile_services
from apps.profiles.models import FounderProfile
from apps.reference.models import Sector, Skill, Stage
from apps.startups import services as startup_services
from apps.startups.models import Startup

pytestmark = pytest.mark.django_db

ADMIN = "/api/v1/admin/reference"
SECTORS = f"{ADMIN}/sectors"
STAGES = f"{ADMIN}/stages"
SKILLS = f"{ADMIN}/skills"


@pytest.fixture
def admin(make_user):
    return make_user(roles=("community_admin",), email="admin@example.com")


@pytest.fixture
def as_admin(admin, client_for):
    return client_for(admin, mfa_age=5)


def item_url(kind, item):
    return f"{ADMIN}/{kind}/{item.pk}"


def entries(client, url=SECTORS):
    return {e["slug"]: e for e in client.get(url).json()}


# --- access ---


def calls(item):
    return [
        ("get", SECTORS, None),
        ("post", SECTORS, {"name": "Space"}),
        ("patch", item_url("sectors", item), {"name": "Renamed"}),
        ("delete", item_url("sectors", item), None),
        ("put", f"{SECTORS}/order", {"ids": [str(item.pk)]}),
    ]


@pytest.fixture
def some_sector():
    return Sector.objects.get(slug="gaming")


def run(client, call):
    method, url, body = call
    return getattr(client, method)(url, body) if body is not None else getattr(client, method)(url)


@pytest.mark.parametrize("index", range(5))
def test_anonymous_callers_are_rejected(api_client, some_sector, index):
    assert run(api_client, calls(some_sector)[index]).status_code == 401


@pytest.mark.parametrize("index", range(5))
def test_members_and_content_editors_are_forbidden(client_for, make_user, some_sector, index):
    for roles in (("member",), ("content_editor",)):
        user = make_user(roles=roles, email=f"{roles[0]}@example.com")
        response = run(client_for(user, mfa_age=5), calls(some_sector)[index])
        assert response.status_code == 403
        assert response.json()["code"] == "permission_denied"


@pytest.mark.parametrize("index", range(5))
def test_admins_without_mfa_are_refused(client_for, admin, some_sector, index):
    response = run(client_for(admin), calls(some_sector)[index])
    assert response.status_code == 403 and response.json()["code"] == "mfa_required"


def test_unknown_lists_are_404(as_admin):
    assert as_admin.get(f"{ADMIN}/countries").status_code == 404
    assert as_admin.get(f"{ADMIN}/colours").status_code == 404


# --- listing ---


def test_the_list_shows_every_entry_in_order(as_admin):
    result = as_admin.get(STAGES).json()
    assert [e["slug"] for e in result][:3] == ["idea", "pre-seed", "seed"]
    assert set(result[0]) == {"id", "slug", "name", "active", "sort_order", "usage"}


def test_retired_entries_are_listed_for_admins_but_not_for_the_public(
    as_admin, api_client, some_sector
):
    as_admin.patch(item_url("sectors", some_sector), {"active": False})
    assert entries(as_admin)["gaming"]["active"] is False
    public = {e["slug"] for e in api_client.get("/api/v1/reference/sectors").json()}
    assert "gaming" not in public


def test_usage_counts_the_records_that_use_each_entry(as_admin, make_user):
    owner = make_user(email="o@example.com", status="active")
    startup_services.create_startup(
        owner_id=owner.pk,
        data={
            "name": "A",
            "pitch": "p",
            "country": "NG",
            "city": "Lagos",
            "sector": "fintech",
            "stage": "seed",
        },
    )
    startup_services.create_startup(
        owner_id=owner.pk,
        data={
            "name": "B",
            "pitch": "p",
            "country": "NG",
            "city": "Lagos",
            "sector": "fintech",
            "stage": "idea",
        },
    )
    profile_services.get_or_create_profile(owner.pk)
    profile = FounderProfile.objects.get(user=owner)
    profile_services.update_profile(
        user_id=owner.pk, data={"skills": ["payments"]}, if_match=etag.etag_for(profile)
    )
    sectors, stages, skills = (
        entries(as_admin),
        entries(as_admin, STAGES),
        entries(as_admin, SKILLS),
    )
    assert (sectors["fintech"]["usage"], sectors["healthtech"]["usage"]) == (2, 0)
    assert (stages["seed"]["usage"], stages["idea"]["usage"], stages["series-a"]["usage"]) == (
        1,
        1,
        0,
    )
    assert (skills["payments"]["usage"], skills["sales"]["usage"]) == (1, 0)


def test_listing_uses_a_fixed_number_of_queries(as_admin, django_assert_max_num_queries):
    with django_assert_max_num_queries(8):
        assert as_admin.get(SKILLS).status_code == 200


# --- adding ---


def test_adding_an_entry_makes_a_slug_and_goes_to_the_end(as_admin, api_client):
    response = as_admin.post(SECTORS, {"name": "Space and aerospace"})
    assert response.status_code == 201
    body = response.json()
    assert body["slug"] == "space-and-aerospace"
    assert body["active"] is True and body["usage"] == 0
    assert body["sort_order"] == max(e["sort_order"] for e in as_admin.get(SECTORS).json())
    public = [e["slug"] for e in api_client.get("/api/v1/reference/sectors").json()]
    assert public[-1] == "space-and-aerospace"


def test_a_chosen_slug_and_position_are_respected(as_admin):
    body = as_admin.post(STAGES, {"name": "Acquired", "slug": "exit", "sort_order": 0}).json()
    assert (body["slug"], body["sort_order"]) == ("exit", 0)


def test_markup_in_a_name_is_stripped(as_admin):
    body = as_admin.post(SKILLS, {"name": "<b>Robotics</b>"}).json()
    assert body["name"] == "Robotics" and body["slug"] == "robotics"


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"name": ""},
        {"name": "A"},
        {"name": "x" * 201},
        {"name": "<i></i>"},
        {"name": "Fine", "slug": "Bad Slug"},
        {"name": "Fine", "slug": "-leading"},
        {"name": "Fine", "slug": "double--dash"},
        {"name": "Fine", "slug": "x" * 81},
        {"name": "Fine", "sort_order": -1},
        {"name": "Fine", "active": False},
        {"name": "Fine", "id": "x"},
    ],
)
def test_invalid_additions_are_refused(as_admin, body):
    before = Sector.objects.count()
    assert as_admin.post(SECTORS, body).status_code == 400
    assert Sector.objects.count() == before


def test_a_name_that_exists_is_a_conflict_whatever_its_case(as_admin):
    response = as_admin.post(SECTORS, {"name": "FINTECH"})
    assert response.status_code == 409 and response.json()["code"] == "name_taken"


def test_a_slug_that_exists_is_a_conflict(as_admin):
    response = as_admin.post(SECTORS, {"name": "Money tech", "slug": "fintech"})
    assert response.status_code == 409 and response.json()["code"] == "slug_taken"


def test_a_list_has_a_size_limit(as_admin, monkeypatch):
    from apps.reference import services

    monkeypatch.setattr(services, "MAX_ITEMS", Sector.objects.count())
    response = as_admin.post(SECTORS, {"name": "One too many"})
    assert response.status_code == 409 and response.json()["code"] == "list_full"


def test_the_database_itself_refuses_duplicate_names(db):
    with pytest.raises(IntegrityError), transaction.atomic():
        Sector.objects.create(name="FINTECH", slug="another-slug")


def test_additions_are_audited_and_announced(as_admin, admin):
    as_admin.post(SKILLS, {"name": "Robotics"})
    entry = AuditLog.objects.get(action="reference.created")
    assert entry.actor_id == admin.pk and entry.target_type == "reference.skills"
    assert entry.after["slug"] == "robotics"
    event = OutboxEvent.objects.get(topic="reference.changed")
    assert event.payload == {"kind": "skills", "slug": "robotics"}


# --- changing ---


def test_renaming_keeps_the_slug(as_admin, some_sector):
    body = as_admin.patch(item_url("sectors", some_sector), {"name": "Games and esports"}).json()
    assert (body["name"], body["slug"]) == ("Games and esports", "gaming")


def test_the_slug_cannot_be_changed(as_admin, some_sector):
    response = as_admin.patch(item_url("sectors", some_sector), {"slug": "other"})
    assert response.status_code == 400 and response.json()["errors"]["slug"] == "Unknown field."
    some_sector.refresh_from_db()
    assert some_sector.slug == "gaming"


def test_retiring_and_restoring(as_admin, some_sector):
    assert (
        as_admin.patch(item_url("sectors", some_sector), {"active": False}).json()["active"]
        is False
    )
    assert (
        as_admin.patch(item_url("sectors", some_sector), {"active": True}).json()["active"] is True
    )


def test_the_position_can_be_changed(as_admin, some_sector):
    body = as_admin.patch(item_url("sectors", some_sector), {"sort_order": 9999}).json()
    assert body["sort_order"] == 9999
    assert as_admin.get(SECTORS).json()[-1]["slug"] == "gaming"


def test_renaming_to_an_existing_name_is_a_conflict(as_admin, some_sector):
    response = as_admin.patch(item_url("sectors", some_sector), {"name": "fintech"})
    assert response.status_code == 409 and response.json()["code"] == "name_taken"


def test_an_entry_can_keep_its_own_name_when_other_fields_change(as_admin, some_sector):
    response = as_admin.patch(item_url("sectors", some_sector), {"name": "gaming", "sort_order": 3})
    assert response.status_code == 200


@pytest.mark.parametrize(
    "body", [{}, {"name": ""}, {"name": "x"}, {"active": "maybe"}, {"sort_order": -3}]
)
def test_invalid_changes_are_refused(as_admin, some_sector, body):
    assert as_admin.patch(item_url("sectors", some_sector), body).status_code == 400
    some_sector.refresh_from_db()
    assert some_sector.name == "Gaming" and some_sector.active


def test_unknown_entries_are_404(as_admin):
    missing = f"{SECTORS}/00000000-0000-0000-0000-000000000000"
    assert as_admin.patch(missing, {"name": "Nope"}).status_code == 404
    assert as_admin.delete(missing).status_code == 404


def test_changes_are_audited_with_before_and_after(as_admin, some_sector):
    as_admin.patch(item_url("sectors", some_sector), {"name": "Esports", "active": False})
    entry = AuditLog.objects.get(action="reference.updated")
    assert entry.before["name"] == "Gaming" and entry.before["active"] is True
    assert entry.after["name"] == "Esports" and entry.after["active"] is False


# --- what retiring means for existing and new records (the regression) ---


@pytest.fixture
def startup_in_gaming(make_user, client_for):
    owner = make_user(email="gamer@example.com", status="active")
    startup = startup_services.create_startup(
        owner_id=owner.pk,
        data={
            "name": "Pixel Co",
            "pitch": "Games",
            "country": "NG",
            "city": "Lagos",
            "sector": "gaming",
            "stage": "seed",
        },
    )
    return owner, startup, client_for(owner)


def test_nobody_can_choose_a_retired_entry(as_admin, some_sector, startup_in_gaming):
    owner, _, client = startup_in_gaming
    as_admin.patch(item_url("sectors", some_sector), {"active": False})
    body = {
        "name": "New",
        "pitch": "p",
        "country": "NG",
        "city": "Lagos",
        "sector": "gaming",
        "stage": "seed",
    }
    response = client.post("/api/v1/startups", body)
    assert response.status_code == 400 and "sector" in response.json()["errors"]


def test_a_startup_keeps_a_retired_sector_and_can_still_be_edited(
    as_admin, some_sector, startup_in_gaming
):
    _, startup, client = startup_in_gaming
    as_admin.patch(item_url("sectors", some_sector), {"active": False})
    detail = f"/api/v1/startups/{startup.pk}"
    current = client.get(detail)
    assert current.json()["sector"]["slug"] == "gaming"
    # Changing only the stage used to re-check the (now retired) sector and fail.
    response = client.patch(detail, {"stage": "series-a"}, HTTP_IF_MATCH=current["ETag"])
    assert response.status_code == 200
    assert response.json()["stage"]["slug"] == "series-a"
    assert Startup.objects.get().sector.slug == "gaming"


def test_moving_to_a_retired_sector_is_still_refused(as_admin, startup_in_gaming):
    _, startup, client = startup_in_gaming
    as_admin.patch(item_url("sectors", Sector.objects.get(slug="cybersecurity")), {"active": False})
    detail = f"/api/v1/startups/{startup.pk}"
    response = client.patch(
        detail, {"sector": "cybersecurity"}, HTTP_IF_MATCH=client.get(detail)["ETag"]
    )
    assert response.status_code == 400


def test_registration_rejects_a_retired_choice(as_admin, api_client, some_sector):
    from apps.accounts.tests.helpers import REGISTER_URL, registration_payload

    as_admin.patch(item_url("sectors", Sector.objects.get(slug="fintech")), {"active": False})
    response = api_client.post(REGISTER_URL, registration_payload())
    assert response.status_code == 400 and "sector" in response.json()["errors"]["startup"]


# --- deleting ---


def test_an_unused_entry_can_be_deleted(as_admin, some_sector, admin):
    assert as_admin.delete(item_url("sectors", some_sector)).status_code == 204
    assert not Sector.objects.filter(slug="gaming").exists()
    entry = AuditLog.objects.get(action="reference.deleted")
    assert entry.before["slug"] == "gaming" and entry.actor_id == admin.pk


@pytest.mark.parametrize(
    ("url_kind", "slug"), [("sectors", "gaming"), ("stages", "seed"), ("skills", "payments")]
)
def test_an_entry_in_use_cannot_be_deleted(as_admin, startup_in_gaming, url_kind, slug, make_user):
    owner, startup, _ = startup_in_gaming
    profile_services.get_or_create_profile(owner.pk)
    profile = FounderProfile.objects.get(user=owner)
    profile_services.update_profile(
        user_id=owner.pk, data={"skills": ["payments"]}, if_match=etag.etag_for(profile)
    )
    model = {"sectors": Sector, "stages": Stage, "skills": Skill}[url_kind]
    item = model.objects.get(slug=slug)
    response = as_admin.delete(item_url(url_kind, item))
    assert response.status_code == 409 and response.json()["code"] == "in_use"
    assert model.objects.filter(slug=slug).exists()


def test_the_database_protects_sectors_in_use_even_if_the_check_is_bypassed(startup_in_gaming):
    with pytest.raises(ProtectedError):
        Sector.objects.get(slug="gaming").delete()


# --- ordering ---


def test_reordering_sets_the_order_everywhere(as_admin, api_client):
    ids = [e["id"] for e in as_admin.get(STAGES).json()]
    reversed_ids = list(reversed(ids))
    response = as_admin.put(f"{STAGES}/order", {"ids": reversed_ids})
    assert response.status_code == 200
    assert [e["id"] for e in response.json()] == reversed_ids
    public = [e["slug"] for e in api_client.get("/api/v1/reference/stages").json()]
    assert public[0] == "bootstrapped-profitable" and public[-1] == "idea"
    assert AuditLog.objects.get(action="reference.reordered").after["order"][0] == public[0]


def test_an_order_must_name_every_entry_exactly_once(as_admin):
    ids = [e["id"] for e in as_admin.get(STAGES).json()]
    assert as_admin.put(f"{STAGES}/order", {"ids": ids[:-1]}).status_code == 409
    assert as_admin.put(f"{STAGES}/order", {"ids": [*ids, ids[0]]}).status_code == 400
    unknown = str(uuid.uuid4())  # a well-formed id that is not in the list
    assert as_admin.put(f"{STAGES}/order", {"ids": [*ids, unknown]}).status_code == 409
    assert as_admin.put(f"{STAGES}/order", {"ids": []}).status_code == 400
    assert as_admin.put(f"{STAGES}/order", {"ids": ["not-a-uuid"]}).status_code == 400


def test_an_order_for_another_list_is_refused(as_admin):
    sector_ids = [e["id"] for e in as_admin.get(SECTORS).json()]
    assert as_admin.put(f"{STAGES}/order", {"ids": sector_ids}).status_code == 409
