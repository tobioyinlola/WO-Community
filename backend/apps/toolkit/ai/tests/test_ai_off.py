"""With no AI service, every tool still works and says plainly where AI would help."""

import pytest

from apps.toolkit.ai import providers

pytestmark = pytest.mark.django_db

BASE = "/api/v1/toolkit"


@pytest.fixture
def ai_off(settings):
    settings.AI_PROVIDER = ""
    settings.RESEARCH_PROVIDER = ""


def test_ai_is_on_only_with_a_provider_and_for_an_api_its_address_and_key(settings):
    settings.AI_PROVIDER = ""
    assert providers.ai_enabled() is False
    settings.AI_PROVIDER, settings.AI_BASE_URL, settings.AI_API_KEY = "http", "", ""
    assert providers.ai_enabled() is False
    settings.AI_BASE_URL, settings.AI_API_KEY = "https://api.openai.com/v1", "sk-test"
    assert providers.ai_enabled() is True


def test_the_workspace_is_told_what_is_on(client, ai_off, settings):
    settings.TOOLKIT_FEATURES = {**settings.TOOLKIT_FEATURES, "partner": False}
    body = client.get(f"{BASE}/config").json()
    assert body["ai_enabled"] is False and body["research_enabled"] is False
    assert body["features"]["partner"] is False and body["features"]["score"] is True


def test_the_score_is_worked_out_without_ai(client, full_venture, ai_off, run_jobs):
    venture = full_venture
    started = client.post(f"{BASE}/ventures/{venture['id']}/score")
    assert started.status_code == 202
    run_jobs()
    report = client.get(f"{BASE}/ventures/{venture['id']}/score/latest")
    assert report.status_code == 200
    assert report.json()["dimensions"]
    assert all(d["explanation"] for d in report.json()["dimensions"])


def test_without_ai_the_plan_is_laid_out_for_the_founder_to_write(
    client, full_venture, ai_off, run_jobs
):
    venture = full_venture
    assert client.post(f"{BASE}/ventures/{venture['id']}/plan/generate").status_code == 202
    run_jobs()
    plan = client.get(f"{BASE}/ventures/{venture['id']}/plan").json()
    assert plan["status"] == "ready" and len(plan["sections"]) > 10
    first = plan["sections"][0]
    assert first["word_count"] == 0 and first["status"] == "needs_input"
    assert first["prompts"][0]["message"]  # what the section should say


@pytest.mark.parametrize(
    "path",
    ["forecast/suggest", "profile/suggest"],
)
def test_ai_buttons_say_ai_is_off_instead_of_failing(client, full_venture, ai_off, path):
    venture = full_venture
    if path == "forecast/suggest":
        client.post(f"{BASE}/ventures/{venture['id']}/forecast", {"template": "subscription"})
    body = {"field": "problem"} if path == "profile/suggest" else {}
    response = client.post(f"{BASE}/ventures/{venture['id']}/{path}", body, format="json")
    assert response.status_code == 503 and response.json()["code"] == "ai_off"
    assert "not switched on" in response.json()["detail"]


def test_the_partner_says_ai_is_off_and_stores_nothing(client, venture, ai_off):
    conversation = client.post(f"{BASE}/ventures/{venture['id']}/partner/conversations").json()
    response = client.post(
        f"{BASE}/ventures/{venture['id']}/partner/conversations/{conversation['id']}/messages",
        {"text": "How should I price this?"},
        format="json",
    )
    assert response.status_code == 503 and response.json()["code"] == "ai_off"
    again = client.get(
        f"{BASE}/ventures/{venture['id']}/partner/conversations/{conversation['id']}"
    ).json()
    assert again.get("messages", []) == []


def test_the_cost_estimate_knows_dated_model_names(settings):
    from apps.toolkit.ai.runner import _cost

    settings.AI_PRICE_PER_MILLION_TOKENS = {"gpt-4.1-mini": (40, 160), "gpt-4.1": (200, 800)}
    assert _cost("gpt-4.1-mini", 1_000_000, 1_000_000) == 200
    assert _cost("gpt-4.1-mini-2025-04-14", 1_000_000, 0) == 40  # not the gpt-4.1 price
    assert _cost("gpt-4.1-2025-04-14", 0, 1_000_000) == 800
    assert _cost("unknown-model", 1_000_000, 1_000_000) == 0
