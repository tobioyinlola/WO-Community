import csv
import io

import pytest
from django.utils import timezone

from apps.toolkit.ai.models import AIRun
from apps.toolkit.jobs.models import AIJob
from apps.toolkit.plans.models import PlanSectionDef
from apps.toolkit.scoring import rubric
from apps.toolkit.scoring.models import ScoreRubric
from apps.toolkit.testing import BASE

pytestmark = pytest.mark.django_db

ADMIN = f"{BASE}/admin"


@pytest.fixture
def staff(make_user):
    return make_user(
        roles=("community_admin",),
        email="staff@example.com",
        approved_at=timezone.now(),
        email_verified_at=timezone.now(),
    )


@pytest.fixture
def staff_client(staff, client_for):
    return client_for(staff, mfa_age=10)


@pytest.fixture
def boss_client(make_user, client_for):
    user = make_user(
        roles=("super_admin",),
        email="boss@example.com",
        approved_at=timezone.now(),
        email_verified_at=timezone.now(),
    )
    return client_for(user, mfa_age=10)


def test_members_and_anonymous_callers_are_turned_away(client, api_client, staff_client):
    for path in (
        "/deck-templates",
        "/prototype-templates",
        "/plan-sections",
        "/score-rubrics",
        "/usage",
        "/quality",
        "/settings",
    ):
        assert api_client.get(ADMIN + path).status_code == 401, path
        assert client.get(ADMIN + path).status_code == 403, path
    # Community admins manage content and read usage; settings and rubrics are super admin.
    assert staff_client.get(ADMIN + "/usage").status_code == 200
    assert staff_client.get(ADMIN + "/settings").status_code == 403
    assert staff_client.get(ADMIN + "/score-rubrics").status_code == 403


def test_staff_without_a_recent_mfa_check_cannot_use_admin(staff, client_for):
    no_mfa = client_for(staff)
    assert no_mfa.get(ADMIN + "/usage").status_code == 403


def test_a_deck_template_is_validated_and_listed(staff_client, client):
    listed = staff_client.get(ADMIN + "/deck-templates").json()
    assert {t["slug"] for t in listed} >= {"investor_pitch", "teaser"}
    body = {
        "slug": "one_slide",
        "name": "One slide",
        "slides": [
            {
                "layout": "statement",
                "title": "Why us",
                "elements": [{"type": "text", "fill": "solution"}],
            }
        ],
    }
    saved = staff_client.put(ADMIN + "/deck-templates", body, format="json")
    assert saved.status_code == 200, saved.content
    assert "one_slide" in [t["slug"] for t in client.get(f"{BASE}/deck-templates").json()]

    broken = {**body, "slug": "broken", "slides": [{"layout": "hologram", "elements": []}]}
    bad = staff_client.put(ADMIN + "/deck-templates", broken, format="json")
    assert bad.status_code == 400 and "slides" in str(bad.json())
    off = staff_client.put(ADMIN + "/deck-templates", {**body, "active": False}, format="json")
    assert off.status_code == 200
    assert "one_slide" not in [t["slug"] for t in client.get(f"{BASE}/deck-templates").json()]


def test_a_prototype_template_must_satisfy_the_registry(staff_client):
    good = {
        "slug": "tiny",
        "name": "Tiny",
        "spec": {
            "kind": "web",
            "screens": [
                {"id": "a", "name": "A", "root": {"component": "container", "children": []}}
            ],
        },
    }
    assert staff_client.put(ADMIN + "/prototype-templates", good, format="json").status_code == 200
    bad = {
        **good,
        "slug": "evil",
        "spec": {
            "kind": "web",
            "screens": [{"id": "a", "name": "A", "root": {"component": "iframe"}}],
        },
    }
    refused = staff_client.put(ADMIN + "/prototype-templates", bad, format="json")
    assert refused.status_code == 400


def test_plan_sections_can_be_edited_within_limits(staff_client):
    sections = staff_client.get(ADMIN + "/plan-sections").json()
    assert len(sections) == 44
    ok = staff_client.patch(
        ADMIN + "/plan-sections/9",
        {"title": "The solution we offer", "required_inputs": ["solution"]},
        format="json",
    )
    assert ok.status_code == 200 and ok.json()["title"] == "The solution we offer"
    assert PlanSectionDef.objects.get(number=9).title == "The solution we offer"
    for body in (
        {"depends_on": {"fields": ["not_a_field"]}},
        {"depends_on": {"facts": ["horoscope"]}},
        {"depends_on": {"outputs": ["rocket"]}},
        {"nonsense": 1},
    ):
        assert (
            staff_client.patch(ADMIN + "/plan-sections/9", body, format="json").status_code == 400
        )
    assert (
        staff_client.patch(ADMIN + "/plan-sections/1", {"active": False}, format="json").status_code
        == 400
    )
    assert (
        staff_client.patch(
            ADMIN + "/plan-sections/99", {"active": False}, format="json"
        ).status_code
        == 404
    )


def test_a_switched_off_section_is_left_out_of_new_plans(
    staff_client, client, full_venture, run_jobs
):
    from apps.toolkit.ai.providers.fake import FakeLLMProvider

    staff_client.patch(ADMIN + "/plan-sections/13", {"active": False}, format="json")
    FakeLLMProvider.canned["plan.section"] = {
        "blocks": [{"type": "paragraph", "text": "Words.", "cites": []}],
        "missing": [],
    }
    FakeLLMProvider.canned["plan.executive_summary"] = {"paragraphs": ["Summary."]}
    started = client.post(f"{BASE}/ventures/{full_venture['id']}/plan/generate", {}, format="json")
    assert started.status_code == 202
    run_jobs()
    plan = client.get(f"{BASE}/ventures/{full_venture['id']}/plan").json()
    numbers = [s["number"] for s in plan["sections"]]
    assert len(numbers) == 43 and 13 not in numbers


def test_rubrics_are_validated_versioned_and_activated_with_step_up(
    boss_client, client_for, make_user
):
    listed = boss_client.get(ADMIN + "/score-rubrics").json()
    assert listed[0]["version"] == 1 and listed[0]["active"] is True

    broken = {**rubric.DEFAULT, "dimensions": rubric.DEFAULT["dimensions"][:2]}
    bad = boss_client.post(ADMIN + "/score-rubrics", {"config": broken}, format="json")
    assert bad.status_code == 400 and "add up to 100" in str(bad.json())

    config = {**rubric.DEFAULT, "verdicts": [{"min": 0, "label": "Custom"}]}
    made = boss_client.post(
        ADMIN + "/score-rubrics", {"config": config, "notes": "Simpler labels"}, format="json"
    )
    assert (
        made.status_code == 201 and made.json()["version"] == 2 and made.json()["active"] is False
    )
    assert ScoreRubric.objects.get(version=1).active is True

    activated = boss_client.post(ADMIN + "/score-rubrics/2/activate")
    assert activated.status_code == 200 and activated.json()["active"] is True
    assert ScoreRubric.objects.filter(active=True).count() == 1
    assert boss_client.post(ADMIN + "/score-rubrics/9/activate").status_code == 404

    stale = make_user(
        roles=("super_admin",),
        email="old@example.com",
        approved_at=timezone.now(),
        email_verified_at=timezone.now(),
    )
    old_mfa = client_for(stale, mfa_age=60 * 60 * 5)
    assert old_mfa.post(ADMIN + "/score-rubrics/1/activate").status_code == 403


def test_usage_is_aggregated_without_content_and_exports_to_csv(staff_client, member):
    for prompt, outcome, cost in (
        ("plan.section", "ok", 5),
        ("plan.section", "invalid_output", 5),
        ("score.explain", "ok", 2),
    ):
        AIRun.objects.create(
            owner=member,
            agent="writer",
            provider="fake",
            model="m",
            prompt_id=prompt,
            input_tokens=100,
            output_tokens=50,
            estimated_cost_minor=cost,
            outcome=outcome,
        )
    by_prompt = staff_client.get(ADMIN + "/usage", {"group_by": "prompt"}).json()
    section = next(r for r in by_prompt if r["key"] == "plan.section")
    assert section["runs"] == 2 and section["input_tokens"] == 200
    assert section["estimated_cost_minor"] == 10
    assert section["outcomes"] == {"ok": 1, "invalid_output": 1}
    by_day = staff_client.get(ADMIN + "/usage").json()
    assert len(by_day) == 1 and by_day[0]["runs"] == 3

    response = staff_client.get(ADMIN + "/usage.csv", {"group_by": "prompt"})
    assert response.status_code == 200 and response["Content-Type"].startswith("text/csv")
    rows = list(csv.reader(io.StringIO(response.content.decode())))
    assert rows[0][:3] == ["key", "runs", "input_tokens"] and len(rows) == 3
    assert staff_client.get(ADMIN + "/usage", {"group_by": "member"}).status_code == 400
    assert (
        staff_client.get(ADMIN + "/usage", {"from": "2026-05-01", "to": "2025-01-01"}).status_code
        == 400
    )
    assert (
        staff_client.get(ADMIN + "/usage", {"from": "2020-01-01", "to": "2026-01-01"}).status_code
        == 400
    )


def test_the_quality_queue_lists_failures_without_content(staff_client, member):
    AIRun.objects.create(
        owner=member,
        agent="writer",
        provider="fake",
        model="m",
        prompt_id="plan.section",
        outcome="invalid_output",
    )
    AIJob.objects.create(
        owner=member, kind="plan.generate", status="failed", error_code="generation_failed"
    )
    body = staff_client.get(ADMIN + "/quality").json()
    assert body["not_ok"] == 1 and body["runs"] == 1
    assert body["by_prompt"][0] == {
        "prompt_id": "plan.section",
        "outcome": "invalid_output",
        "count": 1,
    }
    assert body["failed_jobs"][0]["error_code"] == "generation_failed"
    assert set(body["recent"][0]) == {
        "id",
        "created_at",
        "prompt_id",
        "prompt_version",
        "outcome",
        "model",
        "job_id",
    }


def test_settings_show_no_secrets(boss_client, settings):
    settings.AI_API_KEY = "sk-very-secret"
    body = boss_client.get(ADMIN + "/settings").json()
    assert "sk-very-secret" not in str(body)
    assert body["features"]["plan"] is True and body["ai_daily_run_ceiling"] > 0


def test_ventures_are_listed_with_progress_but_no_content(
    staff_client, client, other_client, full_venture, run_jobs
):
    other_client.post(f"{BASE}/ventures", {"name": "Grainstore"}, format="json")
    client.post(f"{BASE}/ventures/{full_venture['id']}/score", format="json")
    run_jobs()
    body = staff_client.get(ADMIN + "/ventures").json()
    assert body["count"] == 2
    assert body["totals"]["ventures"] == 2 and body["totals"]["founders"] == 2
    row = next(r for r in body["results"] if r["id"] == full_venture["id"])
    assert row["name"] == "Mamapesa" and row["owner_email"]
    assert row["profile_completeness"] > 0 and row["latest_score"] is not None
    assert body["totals"]["scored"] == 1
    assert "fields" not in row and "Market traders" not in str(body)


def test_ventures_can_be_searched_by_name_or_owner(staff_client, other_client, full_venture):
    other_client.post(f"{BASE}/ventures", {"name": "Grainstore"}, format="json")
    names = [r["name"] for r in staff_client.get(ADMIN + "/ventures?q=grain").json()["results"]]
    assert names == ["Grainstore"]


def test_deleted_ventures_are_hidden_unless_asked_for(staff_client, client, venture):
    assert client.delete(f"{BASE}/ventures/{venture['id']}").status_code == 204
    assert staff_client.get(ADMIN + "/ventures").json()["count"] == 0
    rows = staff_client.get(ADMIN + "/ventures?include_deleted=true").json()["results"]
    assert [r["status"] for r in rows] == ["deleted"]


def test_only_staff_see_the_ventures_list(client, api_client, staff, client_for):
    assert api_client.get(ADMIN + "/ventures").status_code == 401
    assert client.get(ADMIN + "/ventures").status_code == 403
    assert client_for(staff).get(ADMIN + "/ventures").status_code == 403
