import datetime
import json

import pytest

from apps.core.visibility import Audience
from apps.startups import selectors
from apps.startups.models import TractionMetric
from apps.startups.tests.conftest import detail, etag_of

pytestmark = pytest.mark.django_db


def put(client, startup_id, metrics, etag=None):
    return client.put(
        f"{detail(startup_id)}/traction",
        {"metrics": metrics},
        HTTP_IF_MATCH=etag or etag_of(client, startup_id),
        format="json",
    )


GOOD = [
    {"kind": "users", "value": 1200, "visibility": "members"},
    {"kind": "revenue_range", "value": "10k_50k", "visibility": "private"},
    {"kind": "funding_range", "value": "250k_1m", "visibility": "public"},
    {"kind": "milestone", "value": "ZZMILESTONE launched in Kano", "as_of_date": "2025-03-01"},
    {"kind": "award", "value": "ZZAWARD best newcomer", "visibility": "members"},
    {"kind": "partner", "value": "ZZPARTNER Bank", "visibility": "public"},
]


def test_the_traction_list_is_saved_and_returned(owner_client, startup_id):
    response = put(owner_client, startup_id, GOOD)
    assert response.status_code == 200
    by_kind = {m["kind"]: m for m in response.json()["traction"]}
    assert by_kind["users"]["value"] == 1200
    assert by_kind["revenue_range"]["value"] == "10k_50k"
    assert by_kind["milestone"]["as_of_date"] == "2025-03-01"
    assert by_kind["milestone"]["visibility"] == "private"  # the default
    assert by_kind["award"]["value"] == "ZZAWARD best newcomer"


def test_an_entry_without_a_date_is_dated_today(owner_client, startup_id):
    put(owner_client, startup_id, [{"kind": "users", "value": 5}])
    assert TractionMetric.objects.get().as_of_date == datetime.date.today()


def test_putting_replaces_the_whole_list(owner_client, startup_id):
    put(owner_client, startup_id, GOOD)
    response = put(owner_client, startup_id, [{"kind": "users", "value": 7}])
    assert [m["kind"] for m in response.json()["traction"]] == ["users"]
    assert TractionMetric.objects.count() == 1
    assert put(owner_client, startup_id, []).json()["traction"] == []


def test_the_etag_is_required_and_checked(owner_client, startup_id):
    missing = owner_client.put(f"{detail(startup_id)}/traction", {"metrics": []}, format="json")
    assert missing.status_code == 428
    stale = etag_of(owner_client, startup_id)
    put(owner_client, startup_id, [{"kind": "users", "value": 1}], etag=stale)
    assert put(owner_client, startup_id, [], etag=stale).status_code == 412
    assert TractionMetric.objects.count() == 1


@pytest.mark.parametrize(
    "metric",
    [
        {"kind": "users", "value": -1},
        {"kind": "users", "value": "many"},
        {"kind": "users", "value": 1.5},
        {"kind": "users", "value": True},
        {"kind": "users", "value": 10**10},
        {"kind": "revenue_range", "value": "a lot"},
        {"kind": "revenue_range", "value": 5},
        {"kind": "funding_range", "value": "10k_50k"},
        {"kind": "milestone", "value": ""},
        {"kind": "milestone", "value": "<b></b>"},
        {"kind": "milestone", "value": "x" * 301},
        {"kind": "milestone", "value": 5},
        {"kind": "award", "value": "ok", "as_of_date": "2999-01-01"},
        {"kind": "award", "value": "ok", "as_of_date": "not a date"},
        {"kind": "award", "value": "ok", "visibility": "everyone"},
        {"kind": "invented", "value": "x"},
        {"kind": "users"},
        {"kind": "users", "value": 1, "startup": "other"},
    ],
)
def test_invalid_entries_reject_the_whole_request(owner_client, startup_id, metric):
    put(owner_client, startup_id, [{"kind": "users", "value": 3}])
    response = put(owner_client, startup_id, [metric])
    assert response.status_code == 400
    assert TractionMetric.objects.count() == 1  # the previous list is untouched


def test_single_value_kinds_may_appear_only_once(owner_client, startup_id):
    response = put(
        owner_client,
        startup_id,
        [{"kind": "users", "value": 1}, {"kind": "users", "value": 2}],
    )
    assert response.status_code == 400
    assert "metrics" in response.json()["errors"]


def test_free_text_kinds_may_repeat(owner_client, startup_id):
    response = put(
        owner_client,
        startup_id,
        [{"kind": "award", "value": "One"}, {"kind": "award", "value": "Two"}],
    )
    assert response.status_code == 200


def test_there_is_a_cap_on_the_number_of_entries(owner_client, startup_id):
    many = [{"kind": "milestone", "value": f"m{n}"} for n in range(51)]
    assert put(owner_client, startup_id, many).status_code == 400


def test_markup_in_text_entries_is_stripped(owner_client, startup_id):
    put(owner_client, startup_id, [{"kind": "partner", "value": "<b>Acme</b><script>x</script>"}])
    assert TractionMetric.objects.get().value_text == "Acme"


def test_the_body_must_use_the_metrics_key_only(owner_client, startup_id):
    response = owner_client.put(
        f"{detail(startup_id)}/traction",
        {"metrics": [], "extra": 1},
        HTTP_IF_MATCH=etag_of(owner_client, startup_id),
        format="json",
    )
    assert response.status_code == 400


# --- who may change it ---


def test_outsiders_get_404_and_nothing_changes(stranger_client, startup_id):
    response = put(stranger_client, startup_id, [{"kind": "users", "value": 1}], etag='"x"')
    assert response.status_code == 404
    assert TractionMetric.objects.count() == 0


def test_anonymous_callers_get_401(api_client, startup_id):
    response = api_client.put(f"{detail(startup_id)}/traction", {"metrics": []}, format="json")
    assert response.status_code == 401


def test_a_founder_on_the_team_can_edit_traction(
    owner_client, stranger_client, startup_id, stranger
):
    owner_client.post(f"{detail(startup_id)}/team", {"email": stranger.email, "is_founder": True})
    assert put(stranger_client, startup_id, [{"kind": "users", "value": 2}]).status_code == 200


def test_an_ordinary_team_member_cannot(owner_client, stranger_client, startup_id, stranger):
    owner_client.post(f"{detail(startup_id)}/team", {"email": stranger.email})
    response = put(stranger_client, startup_id, [{"kind": "users", "value": 2}])
    assert response.status_code == 403


# --- visibility of each entry (AC-17) ---


def test_every_entry_obeys_its_own_level(owner_client, stranger_client, startup_id):
    put(owner_client, startup_id, GOOD)
    seen_by_member = {m["kind"] for m in stranger_client.get(detail(startup_id)).json()["traction"]}
    assert seen_by_member == {"users", "funding_range", "award", "partner"}  # not private ones
    seen_by_owner = {m["kind"] for m in owner_client.get(detail(startup_id)).json()["traction"]}
    assert seen_by_owner == {m["kind"] for m in GOOD}


def test_private_entries_never_appear_in_a_members_response(
    owner_client, stranger_client, startup_id
):
    put(owner_client, startup_id, GOOD)
    text = stranger_client.get(detail(startup_id)).content.decode()
    assert "10k_50k" not in text and "ZZMILESTONE" not in text
    assert "ZZAWARD" in text and "ZZPARTNER" in text


@pytest.mark.parametrize(
    ("audience", "kinds"),
    [
        (Audience.PUBLIC, {"funding_range", "partner"}),
        (Audience.MEMBER, {"users", "funding_range", "award", "partner"}),
        (
            Audience.OWNER,
            {"users", "revenue_range", "funding_range", "milestone", "award", "partner"},
        ),
    ],
)
def test_traction_shown_to_each_audience(owner_client, startup_id, audience, kinds):
    from apps.startups.tests.conftest import set_levels

    set_levels(owner_client, startup_id, {"basics": "public"})
    put(owner_client, startup_id, GOOD)
    result = selectors.project_startup(selectors.get_startup(startup_id), audience)
    assert {m["kind"] for m in result["traction"]} == kinds


def test_a_hidden_startup_shows_no_traction_either(owner_client, stranger_client, startup_id):
    from apps.startups.tests.conftest import set_levels

    put(
        owner_client,
        startup_id,
        [{"kind": "partner", "value": "ZZPARTNER", "visibility": "public"}],
    )
    set_levels(owner_client, startup_id, {"basics": "private"})
    response = stranger_client.get(detail(startup_id))
    assert response.status_code == 404
    assert "ZZPARTNER" not in json.dumps(response.json())
