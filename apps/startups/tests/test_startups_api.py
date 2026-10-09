import pytest

from apps.core.models import OutboxEvent
from apps.startups.models import Startup, StartupMember
from apps.startups.tests.conftest import (
    MINE,
    STARTUPS,
    detail,
    etag_of,
    new_startup_body,
    patch,
)

pytestmark = pytest.mark.django_db


# --- creating ---


def test_an_approved_member_can_create_a_startup(owner_client, owner):
    response = owner_client.post(STARTUPS, new_startup_body())
    assert response.status_code == 201
    body = response.json()
    assert body["name"] == "ZZSTARTUP Pay"
    assert body["sector"] == {"slug": "fintech", "name": "Fintech"}
    assert body["stage"]["slug"] == "seed"
    assert body["owner_id"] == str(owner.pk)
    assert body["directory_opt_in"] is False
    assert body["featured"] is False
    assert response["ETag"]
    assert body["slug"].startswith("zzstartup-pay-")


def test_the_creator_becomes_the_first_founder_on_the_team(owner_client, owner):
    owner_client.post(STARTUPS, new_startup_body())
    member = StartupMember.objects.get()
    assert (member.user, member.is_founder, member.title) == (owner, True, "Founder")


def test_only_the_required_fields_are_needed(owner_client):
    body = new_startup_body()
    for optional in ("year_founded", "description", "website_url"):
        del body[optional]
    assert owner_client.post(STARTUPS, body).status_code == 201


def test_two_startups_with_one_name_get_different_slugs(owner_client):
    one = owner_client.post(STARTUPS, new_startup_body()).json()["slug"]
    two = owner_client.post(STARTUPS, new_startup_body()).json()["slug"]
    assert one != two


def test_anonymous_callers_are_rejected(api_client, startup_id):
    assert api_client.post(STARTUPS, new_startup_body()).status_code == 401
    assert api_client.get(MINE).status_code == 401
    assert api_client.get(detail(startup_id)).status_code == 401


def test_pending_accounts_cannot_create_more_startups(make_user, client_for):
    pending = make_user(email="p@example.com", status="pending")
    assert client_for(pending).post(STARTUPS, new_startup_body()).status_code == 403


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("name", ""),
        ("name", "<i></i>"),
        ("name", "x" * 121),
        ("pitch", ""),
        ("pitch", "x" * 161),
        ("country", "XX"),
        ("city", ""),
        ("sector", "no-such-sector"),
        ("stage", "no-such-stage"),
        ("year_founded", 1899),
        ("year_founded", 2999),
        ("year_founded", "soon"),
        ("description", "x" * 5001),
        ("website_url", "http://example.com"),
        ("website_url", "javascript:alert(1)"),
    ],
)
def test_invalid_values_are_rejected(owner_client, field, value):
    response = owner_client.post(STARTUPS, new_startup_body(**{field: value}))
    assert response.status_code == 400
    assert field in response.json()["errors"]
    assert Startup.objects.count() == 0


@pytest.mark.parametrize(
    "field", ["owner", "owner_id", "slug", "directory_opt_in", "featured_at", "visibility", "id"]
)
def test_fields_the_member_must_not_control_are_refused_on_create(owner_client, field):
    response = owner_client.post(STARTUPS, new_startup_body(**{field: "x"}))
    assert response.status_code == 400
    assert response.json()["errors"][field] == "Unknown field."


def test_markup_is_stripped(owner_client):
    response = owner_client.post(
        STARTUPS, new_startup_body(name="<b>Acme</b>", description="Hi<script>x</script>")
    )
    body = response.json()
    assert body["name"] == "Acme"
    assert body["description"] == "Hi"


def test_creation_announces_itself_for_the_directory(owner_client):
    owner_client.post(STARTUPS, new_startup_body())
    assert OutboxEvent.objects.filter(topic="startups.startup_updated").exists()


# --- listing yours ---


def test_my_startups_lists_owned_and_team_startups_only(
    owner_client, stranger_client, startup_id, stranger, owner
):
    stranger_client.post(STARTUPS, new_startup_body(name="Stranger Co"))
    mine = owner_client.get(MINE).json()
    assert [s["id"] for s in mine] == [startup_id]
    owner_client.post(f"{detail(startup_id)}/team", {"email": stranger.email, "title": "CTO"})
    theirs = {s["name"] for s in stranger_client.get(MINE).json()}
    assert theirs == {"Stranger Co", "ZZSTARTUP Pay"}


def test_my_startups_does_not_query_per_startup(owner_client, django_assert_max_num_queries):
    for n in range(5):
        owner_client.post(STARTUPS, new_startup_body(name=f"Co {n}"))
    with django_assert_max_num_queries(10):
        assert len(owner_client.get(MINE).json()) == 5


# --- updating ---


def test_the_owner_can_update_a_startup(owner_client, startup_id):
    response = patch(
        owner_client,
        startup_id,
        {"pitch": "New pitch", "stage": "series-a", "sector": "healthtech", "year_founded": 2021},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["pitch"] == "New pitch"
    assert body["stage"]["slug"] == "series-a"
    assert body["sector"]["slug"] == "healthtech"
    assert body["year_founded"] == 2021


def test_each_save_changes_the_etag(owner_client, startup_id):
    first = etag_of(owner_client, startup_id)
    response = patch(owner_client, startup_id, {"pitch": "x"}, etag=first)
    assert response["ETag"] != first


def test_a_missing_if_match_is_428_and_a_stale_one_412(owner_client, startup_id):
    assert owner_client.patch(detail(startup_id), {"pitch": "x"}).status_code == 428
    stale = etag_of(owner_client, startup_id)
    patch(owner_client, startup_id, {"pitch": "first"}, etag=stale)
    response = patch(owner_client, startup_id, {"pitch": "second"}, etag=stale)
    assert response.status_code == 412
    assert owner_client.get(detail(startup_id)).json()["pitch"] == "first"


@pytest.mark.django_db(transaction=True, serialized_rollback=True)
@pytest.mark.usefixtures("truncate_audit")
def test_two_edits_from_one_version_cannot_both_win(owner, client_for):
    import threading

    from django.db import connections

    client = client_for(owner)
    sid = client.post(STARTUPS, new_startup_body()).json()["id"]
    etag = etag_of(client, sid)
    results: list[int] = []

    def go(text):
        try:
            results.append(patch(client_for(owner), sid, {"pitch": text}, etag=etag).status_code)
        finally:
            connections.close_all()

    threads = [threading.Thread(target=go, args=(t,)) for t in ("a", "b")]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert sorted(results) == [200, 412]


def test_strangers_cannot_edit_and_cannot_tell_the_startup_exists(stranger_client, startup_id):
    response = stranger_client.patch(
        detail(startup_id), {"pitch": "hijack"}, HTTP_IF_MATCH='"anything"'
    )
    assert response.status_code == 404
    assert Startup.objects.get().pitch.startswith("ZZPITCH")


def test_a_founder_on_the_team_can_edit_but_not_toggle_the_directory(
    owner_client, stranger_client, startup_id, stranger
):
    owner_client.post(f"{detail(startup_id)}/team", {"email": stranger.email, "is_founder": True})
    assert patch(stranger_client, startup_id, {"pitch": "co-founder edit"}).status_code == 200
    denied = patch(stranger_client, startup_id, {"directory_opt_in": True})
    assert denied.status_code == 403
    assert Startup.objects.get().directory_opt_in is False


def test_an_ordinary_team_member_can_read_everything_but_not_edit(
    owner_client, stranger_client, startup_id, stranger
):
    owner_client.post(f"{detail(startup_id)}/team", {"email": stranger.email, "title": "Dev"})
    assert stranger_client.get(detail(startup_id)).json()["visibility"]
    response = stranger_client.patch(
        detail(startup_id), {"pitch": "x"}, HTTP_IF_MATCH=etag_of(stranger_client, startup_id)
    )
    assert response.status_code == 403


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("name", ""),
        ("country", "XX"),
        ("sector", "nope"),
        ("year_founded", 1800),
        ("website_url", "http://example.com"),
        ("description", "x" * 5001),
    ],
)
def test_invalid_updates_change_nothing(owner_client, startup_id, field, value):
    response = patch(owner_client, startup_id, {field: value})
    assert response.status_code == 400
    assert owner_client.get(detail(startup_id)).json()["name"] == "ZZSTARTUP Pay"


@pytest.mark.parametrize("field", ["slug", "owner", "owner_id", "visibility", "featured_at", "id"])
def test_protected_fields_cannot_be_changed(owner_client, startup_id, field):
    response = patch(owner_client, startup_id, {field: "x"})
    assert response.status_code == 400
    assert response.json()["errors"][field] == "Unknown field."


def test_the_year_can_be_cleared(owner_client, startup_id):
    patch(owner_client, startup_id, {"year_founded": None})
    assert owner_client.get(detail(startup_id)).json()["year_founded"] is None


# --- the directory switch ---


def test_listing_in_the_directory_makes_the_basics_public(owner_client, startup_id):
    body = patch(owner_client, startup_id, {"directory_opt_in": True}).json()
    assert body["directory_opt_in"] is True
    assert body["visibility"]["basics"] == "public"
    assert body["visibility"]["description"] == "members"  # nothing else changes


def test_a_listed_startup_cannot_hide_its_basics(owner_client, startup_id):
    patch(owner_client, startup_id, {"directory_opt_in": True})
    response = owner_client.patch(
        f"{detail(startup_id)}/visibility",
        {"basics": "private"},
        HTTP_IF_MATCH=etag_of(owner_client, startup_id),
    )
    assert response.status_code == 409
    assert response.json()["code"] == "listed_in_directory"


def test_unlisting_lets_the_basics_be_hidden_again(owner_client, startup_id):
    patch(owner_client, startup_id, {"directory_opt_in": True})
    patch(owner_client, startup_id, {"directory_opt_in": False})
    response = owner_client.patch(
        f"{detail(startup_id)}/visibility",
        {"basics": "members"},
        HTTP_IF_MATCH=etag_of(owner_client, startup_id),
    )
    assert response.status_code == 200


# --- completeness ---


def test_completeness_names_the_next_gap(owner_client):
    body = new_startup_body()
    for optional in ("year_founded", "description", "website_url"):
        del body[optional]
    created = owner_client.post(STARTUPS, body).json()
    assert created["completeness"] == {"score": 15, "next_missing_field": "description"}
    patched = patch(owner_client, created["id"], {"description": "Details"}).json()
    assert patched["completeness"] == {"score": 35, "next_missing_field": "year_founded"}


def test_a_complete_startup_scores_100(owner_client, startup_id, make_user):
    owner_client.post(f"{detail(startup_id)}/team", {"email": "mate@example.com"})
    owner_client.put(
        f"{detail(startup_id)}/traction",
        {"metrics": [{"kind": "users", "value": 10}]},
        HTTP_IF_MATCH=etag_of(owner_client, startup_id),
        format="json",
    )
    body = owner_client.get(detail(startup_id)).json()
    assert body["completeness"] == {"score": 100, "next_missing_field": None}
    assert Startup.objects.get().completeness_score == 100
