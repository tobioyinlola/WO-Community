import pytest

from apps.toolkit.ai.models import AIRun, Fact
from apps.toolkit.ai.providers.fake import FakeLLMProvider
from apps.toolkit.ai.research.base import Page, SearchHit
from apps.toolkit.ai.research.fake import FakeResearchProvider
from apps.toolkit.jobs.models import AIJob
from apps.toolkit.scoring.models import Assessment, ScoreRubric
from apps.toolkit.testing import BASE
from apps.toolkit.ventures.models import OutputState

pytestmark = pytest.mark.django_db

PAGE = Page(
    url="https://data.example.org/fintech",
    title="Fintech report",
    text="The sector is growing 18 percent a year. A central bank licence is required to lend.",
    publisher="Example Data",
)


def prepare_research():
    FakeResearchProvider.hits["market"] = [SearchHit(PAGE.url, PAGE.title)]
    FakeResearchProvider.hits["growth"] = [SearchHit(PAGE.url, PAGE.title)]
    FakeResearchProvider.hits["regulation"] = [SearchHit(PAGE.url, PAGE.title)]
    FakeResearchProvider.pages[PAGE.url] = PAGE

    def facts(variables, messages):
        topic = variables["topic"]
        if topic == "growth":
            return {
                "facts": [
                    {
                        "statement": "The sector grows 18 percent a year",
                        "quote": "The sector is growing 18 percent a year",
                        "value": 18,
                        "unit": "percent",
                        "region": "africa",
                        "confidence": 0.9,
                    }
                ]
            }
        if topic == "regulation":
            return {
                "facts": [
                    {
                        "statement": "A central bank licence is required to lend",
                        "quote": "A central bank licence is required to lend",
                        "value": None,
                        "unit": "",
                        "region": "africa",
                        "confidence": 0.8,
                    }
                ]
            }
        return {"facts": []}

    FakeLLMProvider.canned["research.extract_facts"] = facts


def run_score(client, venture, run_jobs):
    started = client.post(f"{BASE}/ventures/{venture['id']}/score")
    assert started.status_code == 202, started.content
    run_jobs()
    job = client.get(f"{BASE}/jobs/{started.json()['id']}").json()
    return started, job


def state(venture):
    return OutputState.objects.get(venture_id=venture["id"], output_type="score").status


def test_a_complete_venture_gets_a_sourced_report(client, full_venture, run_jobs):
    prepare_research()
    started, job = run_score(client, full_venture, run_jobs)
    assert job["status"] == "succeeded", job
    report = client.get(f"{BASE}/ventures/{full_venture['id']}/score/latest").json()
    assert report["overall_score"] is not None and report["verdict"]
    dims = {d["key"]: d for d in report["dimensions"]}
    assert dims["market"]["status"] == "scored" and dims["market"]["score"] == 80  # 18% growth
    assert dims["market"]["evidence"][0]["url"] == PAGE.url
    assert dims["risk"]["score"] == 75 - 8  # one licence requirement found
    assert dims["team"]["status"] == "insufficient_data"
    assert "not financial, legal or investment advice" in report["disclaimer"]
    assert report["strengths"] and report["gaps"] and report["next_actions"]
    top = report["next_actions"][0]
    assert top["estimated_points"] >= 1
    assert top["action"]["type"] in {"edit_profile", "open_forecast", "find_mentor"}
    assert state(full_venture) == "ready"


def test_the_numbers_do_not_depend_on_what_the_model_wrote(client, full_venture, run_jobs):
    prepare_research()
    FakeLLMProvider.canned["score.explain"] = {
        "dimensions": [
            {
                "key": "market",
                "explanation": "Scored 100 out of 100, a perfect market.",
                "next_step": "Nothing.",
            }
        ]
    }
    run_score(client, full_venture, run_jobs)
    report = client.get(f"{BASE}/ventures/{full_venture['id']}/score/latest").json()
    market = next(d for d in report["dimensions"] if d["key"] == "market")
    assert market["score"] == 80  # the words say 100; the number comes from the rubric
    assert Assessment.objects.get().rubric_version == 1


def test_running_it_again_gives_the_same_score_and_builds_history(client, full_venture, run_jobs):
    prepare_research()
    run_score(client, full_venture, run_jobs)
    run_score(client, full_venture, run_jobs)
    history = client.get(f"{BASE}/ventures/{full_venture['id']}/score/history").json()
    assert len(history) == 2
    assert history[0]["overall_score"] == history[1]["overall_score"]
    assert history[0]["created_at"] <= history[1]["created_at"]


def test_it_will_not_start_without_the_required_fields(client, venture):
    response = client.post(f"{BASE}/ventures/{venture['id']}/score")
    assert response.status_code == 400
    assert "startup_idea" in str(response.json()["errors"])
    assert AIJob.objects.count() == 0


def test_a_repeated_key_returns_the_same_job(client, full_venture):
    url = f"{BASE}/ventures/{full_venture['id']}/score"
    first = client.post(url, HTTP_IDEMPOTENCY_KEY="abc-123")
    again = client.post(url, HTTP_IDEMPOTENCY_KEY="abc-123")
    assert first.status_code == 202 and again.status_code == 200
    assert first.json()["id"] == again.json()["id"] and AIJob.objects.count() == 1
    assert first["Location"].endswith(first.json()["id"])


def test_a_profile_that_became_incomplete_fails_the_job_with_a_clear_reason(
    client, full_venture, run_jobs
):
    started = client.post(f"{BASE}/ventures/{full_venture['id']}/score")
    client.patch(
        f"{BASE}/ventures/{full_venture['id']}/profile",
        {"fields": {"problem": None}},
        format="json",
    )
    run_jobs()
    job = client.get(f"{BASE}/jobs/{started.json()['id']}").json()
    assert job["status"] == "failed" and job["error_code"] == "profile_incomplete"
    assert "problem" in job["error_detail"]
    assert state(full_venture) == "failed"


def test_research_never_sends_what_the_member_wrote(client, full_venture, run_jobs):
    prepare_research()
    run_score(client, full_venture, run_jobs)
    queries = " ".join(FakeResearchProvider.searched).lower()
    assert "mobile wallet" not in queries and "traders" not in queries
    assert "market size" in queries and "africa" in queries


def test_a_changed_profile_marks_the_score_out_of_date(client, full_venture, run_jobs):
    prepare_research()
    run_score(client, full_venture, run_jobs)
    client.patch(
        f"{BASE}/ventures/{full_venture['id']}/profile",
        {"fields": {"solution": "Traders get stock loans in minutes, repaid from daily sales."}},
        format="json",
    )
    package = client.get(f"{BASE}/ventures/{full_venture['id']}/package").json()
    score = next(o for o in package["outputs"] if o["type"] == "score")
    assert score["status"] == "needs_refresh" and score["stale_fields"] == ["solution"]


def test_only_the_owner_reads_or_runs_a_score(client, other_client, full_venture, run_jobs):
    prepare_research()
    run_score(client, full_venture, run_jobs)
    base = f"{BASE}/ventures/{full_venture['id']}/score"
    assert other_client.post(base).status_code == 404
    for tail in ("/latest", "/history", "/summary"):
        assert other_client.get(base + tail).status_code == 404


def test_the_summary_is_short_and_has_no_evidence(client, full_venture, run_jobs):
    prepare_research()
    run_score(client, full_venture, run_jobs)
    body = client.get(f"{BASE}/ventures/{full_venture['id']}/score/summary").json()
    assert body["venture_name"] == "Mamapesa" and body["overall_score"] is not None
    assert all(set(d) == {"label", "score", "status"} for d in body["dimensions"])
    assert "evidence" not in body


def test_a_new_rubric_version_is_used_and_recorded(client, full_venture, run_jobs):
    from apps.toolkit.scoring import rubric

    ScoreRubric.objects.create(version=1, active=False, config=rubric.DEFAULT)
    config = {**rubric.DEFAULT, "verdicts": [{"min": 0, "label": "Custom verdict"}]}
    ScoreRubric.objects.create(version=2, active=True, config=config)
    prepare_research()
    run_score(client, full_venture, run_jobs)
    report = client.get(f"{BASE}/ventures/{full_venture['id']}/score/latest").json()
    assert report["rubric_version"] == 2 and report["verdict"] == "Custom verdict"


def test_the_flag_switches_the_tool_off(client, full_venture, settings):
    settings.TOOLKIT_FEATURES = {**settings.TOOLKIT_FEATURES, "score": False}
    assert client.post(f"{BASE}/ventures/{full_venture['id']}/score").status_code == 404
    assert client.get(f"{BASE}/ventures/{full_venture['id']}").status_code == 200


def test_usage_is_recorded_without_content(client, full_venture, run_jobs):
    prepare_research()
    run_score(client, full_venture, run_jobs)
    prompts = set(AIRun.objects.values_list("prompt_id", flat=True))
    assert {"score.explain", "research.extract_facts"} <= prompts
    assert Fact.objects.exists()
    run = AIRun.objects.filter(prompt_id="score.explain").get()
    assert run.input_tokens > 0 and run.job_id is not None
