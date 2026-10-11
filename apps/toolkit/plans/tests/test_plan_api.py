import pytest

from apps.toolkit.ai.models import AIRun
from apps.toolkit.ai.providers.fake import FakeLLMProvider
from apps.toolkit.ai.research.base import Page, SearchHit
from apps.toolkit.ai.research.fake import FakeResearchProvider
from apps.toolkit.jobs.models import AIJob
from apps.toolkit.plans.models import BusinessPlan, PlanSection
from apps.toolkit.testing import BASE
from apps.toolkit.ventures.models import OutputState

pytestmark = pytest.mark.django_db

PAGE = Page(
    url="https://data.example.org/fintech",
    title="Fintech report",
    text="The sector is growing 18 percent a year across the region.",
    publisher="Example Data",
)


def research():
    for key in ("market", "growth", "competitors", "regulation", "benchmarks"):
        FakeResearchProvider.hits[key] = [SearchHit(PAGE.url, PAGE.title)]
    FakeResearchProvider.pages[PAGE.url] = PAGE
    FakeLLMProvider.canned["research.extract_facts"] = lambda v, m: {
        "facts": (
            [
                {
                    "statement": "The sector grows 18 percent a year",
                    "quote": "The sector is growing 18 percent a year",
                    "value": 18,
                    "unit": "percent",
                    "region": "africa",
                    "confidence": 0.9,
                }
            ]
            if v["topic"] == "growth"
            else []
        )
    }


def writer(text="Traders lose sales every week.", extra=None):
    def answer(variables, messages):
        blocks = [{"type": "paragraph", "text": text, "cites": list(extra or [])}]
        return {"blocks": blocks, "missing": []}

    FakeLLMProvider.canned["plan.section"] = answer
    FakeLLMProvider.canned["plan.executive_summary"] = {
        "paragraphs": ["Mamapesa gives market traders instant stock loans."]
    }


def generate(client, venture, run_jobs, body=None):
    started = client.post(
        f"{BASE}/ventures/{venture['id']}/plan/generate", body or {}, format="json"
    )
    assert started.status_code == 202, started.content
    run_jobs()
    return client.get(f"{BASE}/jobs/{started.json()['id']}").json()


def url(venture, tail=""):
    return f"{BASE}/ventures/{venture['id']}/plan{tail}"


def test_the_plan_has_44_sections_and_only_what_the_data_supports(client, full_venture, run_jobs):
    research()
    writer()
    job = generate(client, full_venture, run_jobs)
    assert job["status"] == "succeeded", job
    plan = client.get(url(full_venture)).json()
    assert plan["status"] == "ready" and len(plan["sections"]) == 44
    by_number = {s["number"]: s for s in plan["sections"]}
    # The team section needs a team that was never entered: no text is made up for it.
    assert by_number[33]["status"] == "needs_input" and by_number[33]["prompts"]
    assert by_number[33]["word_count"] == 0
    assert by_number[5]["status"] == "drafted" and by_number[1]["status"] == "drafted"
    state = OutputState.objects.get(venture_id=full_venture["id"], output_type="plan")
    assert state.status == "ready"


def test_figures_that_are_not_in_the_data_are_removed(client, full_venture, run_jobs):
    research()
    writer("Traders lose sales. The market is worth 9,000,000 dollars.")
    generate(client, full_venture, run_jobs)
    section = client.get(url(full_venture, "/sections/5")).json()
    text = str(section["content"])
    assert "9,000,000" not in text and "Traders lose sales." in text
    # The first answer was refused and the section was asked for again with a note.
    assert AIRun.objects.filter(prompt_id="plan.section").count() > 44 - 8
    notes = [c.variables["notes"] for c in FakeLLMProvider.calls if c.prompt_id == "plan.section"]
    assert any("9000000" in n for n in notes)


def test_cited_facts_become_numbered_citations_with_their_source(client, full_venture, run_jobs):
    research()
    from apps.toolkit.ventures.models import VentureProfile

    client.patch(
        url(full_venture).replace("/plan", "/profile"),
        {"fields": {"sector": "fintech"}},
        format="json",
    )
    assert VentureProfile.objects.get().fields["sector"] == "fintech"
    writer("The sector grows 18 percent a year.", extra=[1, 9])
    generate(client, full_venture, run_jobs)
    section = client.get(url(full_venture, "/sections/17")).json()
    assert [c["number"] for c in section["citations"]] == [1]
    assert section["citations"][0]["url"] == PAGE.url
    assert section["content"]["blocks"][0]["cites"] == [1]  # the invented position 9 is dropped


def test_a_section_you_edited_is_kept_unless_you_ask_for_a_rewrite(client, full_venture, run_jobs):
    research()
    writer()
    generate(client, full_venture, run_jobs)
    current = client.get(url(full_venture, "/sections/5")).json()
    saved = client.patch(
        url(full_venture, "/sections/5"),
        {
            "content": {"blocks": [{"type": "paragraph", "text": "My own words."}]},
            "base_version": current["version"],
        },
        format="json",
    )
    assert saved.status_code == 200 and saved.json()["status"] == "edited"
    writer("Rewritten by the tool.")
    generate(client, full_venture, run_jobs)
    kept = client.get(url(full_venture, "/sections/5")).json()
    assert "My own words." in str(kept["content"]) and kept["edited_by_member"] is True
    generate(client, full_venture, run_jobs, {"overwrite_edited": True})
    again = client.get(url(full_venture, "/sections/5")).json()
    assert "Rewritten by the tool." in str(again["content"])
    assert BusinessPlan.objects.count() == 3


def test_saving_a_stale_version_is_refused_and_markup_is_stripped(client, full_venture, run_jobs):
    research()
    writer()
    generate(client, full_venture, run_jobs)
    section = client.get(url(full_venture, "/sections/9")).json()
    body = {
        "content": {"blocks": [{"type": "paragraph", "text": "<b>Bold</b><script>x()</script>"}]},
        "base_version": section["version"],
    }
    first = client.patch(url(full_venture, "/sections/9"), body, format="json")
    assert first.status_code == 200
    assert "<" not in str(first.json()["content"])
    second = client.patch(url(full_venture, "/sections/9"), body, format="json")
    assert second.status_code == 409
    bad = client.patch(
        url(full_venture, "/sections/9"),
        {
            "content": {"blocks": [{"type": "html", "text": "x"}]},
            "base_version": first.json()["version"],
        },
        format="json",
    )
    assert bad.status_code == 400


def test_an_assist_action_proposes_and_saves_nothing(client, full_venture, run_jobs):
    research()
    writer("Traders lose sales every week and buy stock late.")
    generate(client, full_venture, run_jobs)
    before = client.get(url(full_venture, "/sections/5")).json()
    FakeLLMProvider.canned["plan.rewrite"] = {
        "blocks": [{"type": "paragraph", "text": "Traders lose sales weekly. Up to 400 percent."}],
        "missing": [],
    }
    response = client.post(
        url(full_venture, "/sections/5/assist"), {"action": "shorten"}, format="json"
    )
    assert response.status_code == 200, response.content
    proposal = response.json()
    assert proposal["removed_figures"] == ["400"]
    assert "400" not in str(proposal["content"])
    after = client.get(url(full_venture, "/sections/5")).json()
    assert after["content"] == before["content"] and after["version"] == before["version"]
    unknown = client.post(
        url(full_venture, "/sections/5/assist"), {"action": "poetry"}, format="json"
    )
    assert unknown.status_code == 400


def test_a_changed_profile_field_marks_only_the_sections_that_use_it(
    client, full_venture, run_jobs
):
    research()
    writer()
    generate(client, full_venture, run_jobs)
    client.patch(
        f"{BASE}/ventures/{full_venture['id']}/profile",
        {"fields": {"differentiator": "We lend against daily sales, not collateral."}},
        format="json",
    )
    plan = client.get(url(full_venture)).json()
    stale = {s["number"] for s in plan["sections"] if s["stale"]}
    assert 14 in stale and 21 in stale
    assert 5 not in stale and 16 not in stale
    ready = client.get(url(full_venture, "/readiness")).json()
    assert ready["ready"] is False and ready["blockers"]


def test_a_version_can_be_restored_and_the_current_text_is_kept(client, full_venture, run_jobs):
    research()
    writer()
    generate(client, full_venture, run_jobs)
    versions = client.get(url(full_venture, "/versions")).json()
    assert versions and versions[0]["label"] == "Generated"
    section = client.get(url(full_venture, "/sections/5")).json()
    client.patch(
        url(full_venture, "/sections/5"),
        {
            "content": {"blocks": [{"type": "paragraph", "text": "Different."}]},
            "base_version": section["version"],
        },
        format="json",
    )
    restored = client.post(url(full_venture, f"/versions/{versions[0]['version']}/restore"))
    assert restored.status_code == 200
    back = client.get(url(full_venture, "/sections/5")).json()
    assert back["content"] == section["content"]
    assert len(client.get(url(full_venture, "/versions")).json()) == 2


def test_it_will_not_start_without_the_required_fields(client, venture):
    response = client.post(url(venture, "/generate"), {}, format="json")
    assert response.status_code == 400 and AIJob.objects.count() == 0


def test_only_the_owner_can_read_or_change_a_plan(client, other_client, full_venture, run_jobs):
    research()
    writer()
    generate(client, full_venture, run_jobs)
    for tail in ("", "/readiness", "/versions", "/sections/5"):
        assert other_client.get(url(full_venture, tail)).status_code == 404
    assert other_client.post(url(full_venture, "/generate"), {}, format="json").status_code == 404
    assert (
        other_client.patch(
            url(full_venture, "/sections/5"),
            {"content": {"blocks": []}, "base_version": 1},
            format="json",
        ).status_code
        == 404
    )


def test_anonymous_and_unapproved_members_are_turned_away(api_client, pending_client, full_venture):
    assert api_client.get(url(full_venture)).status_code == 401
    assert pending_client.get(url(full_venture)).status_code == 403


def test_the_flag_switches_the_tool_off(client, full_venture, settings):
    settings.TOOLKIT_FEATURES = {**settings.TOOLKIT_FEATURES, "plan": False}
    assert client.get(url(full_venture)).status_code == 404
    assert client.post(url(full_venture, "/generate"), {}, format="json").status_code == 404


def test_partial_rewrite_touches_only_the_chosen_sections(client, full_venture, run_jobs):
    research()
    writer("First draft.")
    generate(client, full_venture, run_jobs)
    writer("Second draft.")
    generate(client, full_venture, run_jobs, {"sections": [5]})
    assert BusinessPlan.objects.count() == 1
    five = client.get(url(full_venture, "/sections/5")).json()
    nine = client.get(url(full_venture, "/sections/9")).json()
    assert "Second draft." in str(five["content"]) and "First draft." in str(nine["content"])
    assert PlanSection.objects.filter(number=5).get().version == 2


def export(client, venture, run_jobs, fmt="docx"):
    started = client.post(url(venture, "/export"), {"format": fmt}, format="json")
    assert started.status_code == 202, started.content
    run_jobs()
    return client.get(f"{BASE}/jobs/{started.json()['id']}").json()


def test_the_plan_exports_to_word_and_pdf_with_a_signed_link(client, full_venture, run_jobs):
    import io

    from docx import Document

    from apps.integrations.storage.base import PRIVATE
    from apps.integrations.storage.fake import FakeStorage

    research()
    writer("Traders lose sales every week.")
    generate(client, full_venture, run_jobs)
    job = export(client, full_venture, run_jobs, "docx")
    assert job["status"] == "succeeded", job
    file = client.get(f"{BASE}/exports/{job['result']['id']}").json()
    assert file["filename"].endswith(".docx") and file["url"] and file["size"] > 1000
    stored = next(v for (b, k), v in FakeStorage.objects.items() if b == PRIVATE)
    text = "\n".join(p.text for p in Document(io.BytesIO(stored[0])).paragraphs)
    assert "Mamapesa" in text and "Traders lose sales every week." in text
    assert "not audited" in text

    pdf = export(client, full_venture, run_jobs, "pdf")
    assert pdf["status"] == "succeeded"
    again = client.get(f"{BASE}/exports/{pdf['result']['id']}").json()
    from apps.toolkit.jobs.models import ExportFile

    key = ExportFile.objects.get(pk=again["id"]).storage_key
    assert again["content_type"] == "application/pdf"
    assert FakeStorage.objects[(PRIVATE, key)][0].startswith(b"%PDF")


def test_an_export_belongs_to_its_owner_and_expires(client, other_client, full_venture, run_jobs):
    from datetime import timedelta

    from django.utils import timezone

    from apps.toolkit.jobs import exports
    from apps.toolkit.jobs.models import ExportFile

    research()
    writer()
    generate(client, full_venture, run_jobs)
    job = export(client, full_venture, run_jobs, "pdf")
    path = f"{BASE}/exports/{job['result']['id']}"
    assert other_client.get(path).status_code == 404
    assert client.get(path).status_code == 200
    ExportFile.objects.update(expires_at=timezone.now() - timedelta(minutes=1))
    assert client.get(path).status_code == 404
    assert exports.purge_expired() == 1
    assert ExportFile.objects.count() == 0


def test_exporting_needs_a_plan_and_a_known_format(client, full_venture, run_jobs):
    assert client.post(url(full_venture, "/export"), {}, format="json").status_code == 404
    research()
    writer()
    generate(client, full_venture, run_jobs)
    bad = client.post(url(full_venture, "/export"), {"format": "exe"}, format="json")
    assert bad.status_code == 400
