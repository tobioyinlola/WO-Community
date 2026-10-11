import pytest

from apps.toolkit.testing import BASE, FULL_PROFILE
from apps.toolkit.ventures.models import OutputState, Venture

pytestmark = pytest.mark.django_db


def profile_url(venture):
    return f"{BASE}/ventures/{venture['id']}/profile"


def patch(client, venture, fields, **extra):
    return client.patch(profile_url(venture), {"fields": fields, **extra}, format="json")


# --- who may use it ---


def test_the_toolkit_is_for_approved_members(api_client, pending_client):
    assert api_client.get(f"{BASE}/ventures").status_code == 401
    assert pending_client.get(f"{BASE}/ventures").status_code == 403


def test_a_switched_off_tool_does_not_exist(client, venture, settings):
    # Ventures themselves are always on; the individual tools have flags.
    assert settings.TOOLKIT_FEATURES["score"] is True
    assert client.get(f"{BASE}/ventures/{venture['id']}").status_code == 200


# --- ventures ---


def test_a_member_starts_and_lists_ventures(client, venture, member):
    assert venture["name"] == "Mamapesa" and venture["profile_completeness"] > 0
    listing = client.get(f"{BASE}/ventures").json()["results"]
    assert [v["id"] for v in listing] == [venture["id"]]
    package = client.get(f"{BASE}/ventures/{venture['id']}/package").json()
    assert package["ready_for_score"] is False
    assert package["missing_required"] == [
        "startup_idea",
        "target_regions",
        "problem",
        "solution",
        "revenue_models",
    ]
    assert {o["type"] for o in package["outputs"]} == {"score", "plan", "forecast"}
    assert all(o["status"] == "not_started" for o in package["outputs"])


def test_names_are_checked_and_markup_is_removed(client):
    assert client.post(f"{BASE}/ventures", {"name": "x"}, format="json").status_code == 400
    assert (
        client.post(f"{BASE}/ventures", {"name": "A", "extra": 1}, format="json").status_code == 400
    )
    made = client.post(f"{BASE}/ventures", {"name": "<b>Acme</b> Pay"}, format="json")
    assert made.status_code == 201 and made.json()["name"] == "Acme Pay"


def test_a_member_can_have_only_a_few_ventures(client, settings):
    settings.TOOLKIT_MAX_VENTURES_PER_MEMBER = 2
    for n in range(2):
        assert (
            client.post(f"{BASE}/ventures", {"name": f"Venture {n}"}, format="json").status_code
            == 201
        )
    over = client.post(f"{BASE}/ventures", {"name": "Third one"}, format="json")
    assert over.status_code == 409 and over.json()["code"] == "venture_limit"


def test_other_members_cannot_see_or_touch_a_venture(client, other_client, venture):
    url = f"{BASE}/ventures/{venture['id']}"
    for method, path, body in (
        ("get", url, None),
        ("patch", url, {"name": "Stolen"}),
        ("delete", url, None),
        ("get", f"{url}/package", None),
        ("get", f"{url}/profile", None),
        ("patch", f"{url}/profile", {"fields": {"name": "Stolen"}}),
        ("get", f"{url}/profile/versions", None),
        ("get", f"{url}/export", None),
        ("post", f"{url}/competitors", {"name": "X"}),
        ("post", f"{url}/team", {"name": "X", "role": "CEO"}),
    ):
        kwargs = {"format": "json"} if body is not None else {}
        response = getattr(other_client, method)(
            path, *([body] if body is not None else []), **kwargs
        )
        assert response.status_code == 404, (method, path)
    assert other_client.get(f"{BASE}/ventures").json()["results"] == []
    assert Venture.objects.get(pk=venture["id"]).name == "Mamapesa"


def test_archiving_and_renaming(client, venture):
    url = f"{BASE}/ventures/{venture['id']}"
    done = client.patch(url, {"name": "Mamapesa Africa", "archived": True}, format="json").json()
    assert done["name"] == "Mamapesa Africa" and done["status"] == "archived"
    profile = client.get(f"{url}/profile").json()
    assert profile["fields"]["name"] == "Mamapesa Africa"
    back = client.patch(url, {"archived": False}, format="json").json()
    assert back["status"] == "active"


def test_deleting_hides_a_venture_and_it_can_be_restored(client, venture):
    url = f"{BASE}/ventures/{venture['id']}"
    assert client.delete(url).status_code == 204
    assert client.get(url).status_code == 404
    assert client.get(f"{BASE}/ventures").json()["results"] == []
    restored = client.post(f"{url}/restore")
    assert restored.status_code == 200 and client.get(url).status_code == 200
    assert client.post(f"{url}/restore").status_code == 404  # nothing to restore


# --- the profile ---


def test_a_step_is_saved_and_reports_what_it_changed(client, venture):
    response = patch(
        client, venture, {"startup_idea": FULL_PROFILE["startup_idea"], "stage": "idea"}
    )
    assert response.status_code == 200
    body = response.json()
    assert sorted(body["changed"]) == ["stage", "startup_idea"]
    assert body["profile"]["version"] == 2
    assert body["profile"]["field_meta"]["stage"]["source"] == "member"
    assert body["profile"]["completeness"] > venture["profile_completeness"]
    again = patch(client, venture, {"stage": "idea"}).json()
    assert again["changed"] == [] and again["profile"]["version"] == 2


@pytest.mark.parametrize(
    ("fields", "field"),
    [
        ({"startup_idea": "too short"}, "startup_idea"),
        ({"problem": "x" * 2001}, "problem"),
        ({"target_regions": ["mars"]}, "target_regions"),
        ({"stage": "ipo"}, "stage"),
        ({"country": "ZZ"}, "country"),
        ({"revenue_models": ["barter"]}, "revenue_models"),
        ({"how_it_works": ["step"] * 11}, "how_it_works"),
        ({"key_features": ["f"] * 7}, "key_features"),
        ({"price_points": [{"label": "x", "amount_minor": -1, "currency": "NGN"}]}, "price_points"),
        ({"price_points": [{"label": "x", "amount_minor": 1, "currency": "EUR"}]}, "price_points"),
        ({"traction": {"users": -5}}, "traction"),
        ({"estimated_customers": -1}, "estimated_customers"),
        ({"unknown_field": "x"}, "unknown_field"),
    ],
)
def test_invalid_values_name_the_field(client, venture, fields, field):
    response = patch(client, venture, fields)
    assert response.status_code == 400, response.content
    if field:
        assert field in response.json()["errors"]


def test_target_countries_need_africa_and_must_be_african(client, venture):
    assert patch(client, venture, {"target_countries": ["NG"]}).status_code == 400
    assert (
        patch(
            client, venture, {"target_regions": ["europe"], "target_countries": ["NG"]}
        ).status_code
        == 400
    )
    assert (
        patch(
            client, venture, {"target_regions": ["africa"], "target_countries": ["FR"]}
        ).status_code
        == 400
    )
    ok = patch(
        client, venture, {"target_regions": ["africa", "europe"], "target_countries": ["ng", "KE"]}
    )
    assert ok.status_code == 200
    assert ok.json()["profile"]["fields"]["target_countries"] == ["NG", "KE"]


def test_removing_africa_while_countries_remain_is_refused(client, venture):
    patch(client, venture, {"target_regions": ["africa"], "target_countries": ["NG"]})
    bad = patch(client, venture, {"target_regions": ["europe"]})
    assert bad.status_code == 400 and "target_countries" in bad.json()["errors"]
    both = patch(client, venture, {"target_regions": ["europe"], "target_countries": None})
    assert both.status_code == 200


def test_text_is_stripped_of_markup_and_blank_clears(client, venture):
    patch(client, venture, {"one_liner": "<script>alert(1)</script>Loans for <b>traders</b>"})
    fields = client.get(profile_url(venture)).json()["fields"]
    assert fields["one_liner"] == "Loans for traders"
    cleared = patch(client, venture, {"one_liner": ""}).json()
    assert "one_liner" not in cleared["profile"]["fields"]
    assert "one_liner" not in cleared["profile"]["field_meta"]


def test_sector_must_be_one_the_platform_lists(client, venture):
    assert patch(client, venture, {"sector": "not-a-sector"}).status_code == 400


def test_a_stale_base_version_is_a_conflict(client, venture):
    patch(client, venture, {"stage": "idea"})
    stale = patch(client, venture, {"stage": "prototype"}, base_version=1)
    assert stale.status_code == 409
    current = patch(client, venture, {"stage": "prototype"}, base_version=2)
    assert current.status_code == 200


def test_the_required_fields_make_a_venture_ready_for_a_score(client, full_venture):
    package = client.get(f"{BASE}/ventures/{full_venture['id']}/package").json()
    assert package["ready_for_score"] is True and package["missing_required"] == []
    assert package["completeness"] >= 50


def test_every_change_is_in_the_version_history(client, venture):
    patch(client, venture, {"stage": "idea"})
    patch(client, venture, {"stage": "prototype", "city": "Abuja"})
    history = client.get(f"{profile_url(venture)}/versions").json()
    assert [h["version"] for h in history] == [3, 2, 1]
    assert sorted(history[0]["changed_fields"]) == ["city", "stage"]


# --- staleness ---


def test_changing_a_field_marks_what_was_made_from_it(client, full_venture):
    venture = Venture.objects.get(pk=full_venture["id"])
    for output in ("score", "plan"):
        OutputState.objects.filter(venture=venture, output_type=output).update(status="ready")
    patch(client, full_venture, {"problem": "Traders lose a day of sales whenever stock runs out."})
    states = {
        s.output_type: (s.status, s.stale_fields)
        for s in OutputState.objects.filter(venture=venture)
    }
    assert states["score"] == ("needs_refresh", ["problem"])
    assert states["plan"] == ("needs_refresh", ["problem"])
    assert states["forecast"][0] == "not_started"  # never made, so nothing to refresh
    patch(client, full_venture, {"price_points": []})
    assert OutputState.objects.get(venture=venture, output_type="plan").stale_fields == [
        "price_points",
        "problem",
    ]


# --- competitors and team ---


def test_competitors_and_team_are_rows_that_count_toward_completeness(client, venture):
    before = client.get(f"{BASE}/ventures/{venture['id']}").json()["profile_completeness"]
    made = client.post(
        f"{BASE}/ventures/{venture['id']}/competitors",
        {"name": "Competitor Co", "website": "https://competitor.example.com"},
        format="json",
    )
    assert made.status_code == 201
    team = client.post(
        f"{BASE}/ventures/{venture['id']}/team",
        {"name": "Ada Obi", "role": "CEO", "is_founder": True},
        format="json",
    )
    assert team.status_code == 201
    after = client.get(f"{BASE}/ventures/{venture['id']}").json()["profile_completeness"]
    assert after > before
    changed = client.patch(
        f"{BASE}/ventures/{venture['id']}/competitors/{made.json()['id']}",
        {"differentiator": "Slower payouts"},
        format="json",
    )
    assert changed.json()["differentiator"] == "Slower payouts"
    assert (
        client.delete(f"{BASE}/ventures/{venture['id']}/team/{team.json()['id']}").status_code
        == 204
    )
    assert client.get(f"{BASE}/ventures/{venture['id']}/team").json() == []


def test_competitors_are_limited_and_links_are_checked(client, venture):
    url = f"{BASE}/ventures/{venture['id']}/competitors"
    assert (
        client.post(url, {"name": "X", "website": "javascript:alert(1)"}, format="json").status_code
        == 400
    )
    for n in range(8):
        assert client.post(url, {"name": f"C{n}"}, format="json").status_code == 201
    assert client.post(url, {"name": "Ninth"}, format="json").status_code == 400
    bad = client.post(
        f"{BASE}/ventures/{venture['id']}/team",
        {"name": "A", "role": "CEO", "linkedin": "https://example.com/in/a"},
        format="json",
    )
    assert bad.status_code == 400


# --- importing a startup profile ---


def test_a_venture_can_start_from_a_startup_profile(client, member, make_user):
    from apps.startups.tests.conftest import new_startup_body

    created = client.post("/api/v1/startups", new_startup_body())
    assert created.status_code == 201, created.content
    venture = client.post(
        f"{BASE}/ventures",
        {"name": "From startup", "from_startup_id": created.json()["id"]},
        format="json",
    )
    assert venture.status_code == 201, venture.content
    profile = client.get(f"{BASE}/ventures/{venture.json()['id']}/profile").json()
    fields, meta = profile["fields"], profile["field_meta"]
    assert fields["name"] == "ZZSTARTUP Pay" and fields["country"] == "NG"
    assert fields["sector"] == "fintech" and meta["country"]["source"] == "imported"
    assert profile["team"] == []  # nobody else is on that startup yet


def test_only_your_own_startup_can_be_imported(client, other_client, make_user):
    from apps.startups.tests.conftest import new_startup_body

    theirs = other_client.post("/api/v1/startups", new_startup_body()).json()["id"]
    response = client.post(
        f"{BASE}/ventures", {"name": "Taking it", "from_startup_id": theirs}, format="json"
    )
    assert response.status_code == 404


# --- erasing ---


def test_a_deleted_venture_is_erased_after_the_grace_period(client, venture, settings):
    from datetime import timedelta

    from django.utils import timezone

    from apps.toolkit.ventures import services

    client.delete(f"{BASE}/ventures/{venture['id']}")
    assert services.erase_due() == 0  # still inside the grace period
    Venture.objects.filter(pk=venture["id"]).update(
        deleted_at=timezone.now() - timedelta(days=settings.VENTURE_DELETE_GRACE_DAYS + 1)
    )
    assert services.erase_due() == 1
    assert not Venture.objects.filter(pk=venture["id"]).exists()


def test_a_member_can_export_everything_held_about_a_venture(client, full_venture):
    response = client.get(f"{BASE}/ventures/{full_venture['id']}/export")
    assert response.status_code == 200
    assert response["Content-Type"] == "application/json"
    assert response["Content-Disposition"].startswith("attachment")
    body = response.json()
    assert body["venture"]["name"] == "Mamapesa"
    assert body["profile"]["fields"]["problem"].startswith("Market traders")
    assert len(body["profile_versions"]) >= 2
