"""A member's data: everything is in the export, and erasing a venture leaves nothing behind."""

import io
from datetime import timedelta

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone
from PIL import Image

from apps.audit.models import AuditLog
from apps.integrations.storage.base import PRIVATE
from apps.integrations.storage.fake import FakeStorage
from apps.toolkit.ai.models import AIRun
from apps.toolkit.ai.providers.fake import FakeLLMProvider
from apps.toolkit.ai.research.base import Page, SearchHit
from apps.toolkit.ai.research.fake import FakeResearchProvider
from apps.toolkit.testing import BASE
from apps.toolkit.ventures import services as ventures
from apps.toolkit.ventures.models import Venture

pytestmark = pytest.mark.django_db


def build_everything(client, venture, run_jobs):
    vid = venture["id"]
    page = Page(
        url="https://data.example.org/x",
        title="Report",
        text="The sector is growing 18 percent a year.",
        publisher="Example",
    )
    FakeResearchProvider.hits["growth"] = [SearchHit(page.url, page.title)]
    FakeResearchProvider.pages[page.url] = page
    FakeLLMProvider.canned["research.extract_facts"] = {"facts": []}
    FakeLLMProvider.canned["plan.section"] = {
        "blocks": [{"type": "paragraph", "text": "Plain words.", "cites": []}],
        "missing": [],
    }
    FakeLLMProvider.canned["plan.executive_summary"] = {"paragraphs": ["Summary."]}
    FakeLLMProvider.canned["partner.reply"] = {
        "reply": "Noted.",
        "changes": [],
        "next_steps": [],
        "mentor_topics": [],
    }
    client.post(f"{BASE}/ventures/{vid}/score")
    client.post(f"{BASE}/ventures/{vid}/plan/generate", {}, format="json")
    client.post(f"{BASE}/ventures/{vid}/forecast", {}, format="json")
    deck = client.post(f"{BASE}/ventures/{vid}/decks", {"template": "teaser"}, format="json").json()
    out = io.BytesIO()
    Image.new("RGB", (30, 20), (10, 90, 200)).save(out, format="PNG")
    client.post(
        f"{BASE}/ventures/{vid}/decks/{deck['id']}/assets",
        {"file": SimpleUploadedFile("a.png", out.getvalue(), content_type="image/png")},
        format="multipart",
    )
    client.post(f"{BASE}/ventures/{vid}/prototypes", {"template": "landing"}, format="json")
    client.post(
        f"{BASE}/ventures/{vid}/shares",
        {"subject_type": "deck", "subject_id": deck["id"]},
        format="json",
    )
    conv = client.post(f"{BASE}/ventures/{vid}/partner/conversations", {}, format="json").json()
    client.post(
        f"{BASE}/ventures/{vid}/partner/conversations/{conv['id']}/messages",
        {"text": "Hello partner"},
        format="json",
    )
    client.post(
        f"{BASE}/ventures/{vid}/partner/decisions", {"text": "Focus on Lagos first"}, format="json"
    )
    run_jobs()
    client.post(f"{BASE}/ventures/{vid}/plan/export", {"format": "pdf"}, format="json")
    run_jobs()


def test_the_export_holds_everything_the_venture_has(client, full_venture, run_jobs, settings):
    settings.AI_PARTNER_REPLY_TIMEOUT_SECONDS = 0
    build_everything(client, full_venture, run_jobs)
    body = client.get(f"{BASE}/ventures/{full_venture['id']}/export").json()
    expected = {
        "venture",
        "profile",
        "scores",
        "plan",
        "forecast",
        "decks",
        "prototypes",
        "partner",
        "shares",
        "generated_files",
    }
    assert expected <= set(body), expected - set(body)
    assert body["scores"] and body["plan"]["sections"] and body["forecast"]["assumptions"]
    assert body["decks"][0]["images"] and body["prototypes"][0]["spec"]["screens"]
    assert body["partner"]["conversations"][0]["messages"][0]["text"] == "Hello partner"
    assert body["partner"]["decisions"][0]["text"] == "Focus on Lagos first"
    assert body["shares"][0]["subject_type"] == "deck"
    assert "token" not in str(body["shares"]) and "hash" not in str(body["shares"])
    assert body["generated_files"][0]["kind"] == "plan.pdf"


def test_erasing_a_venture_removes_every_row_and_file(client, full_venture, run_jobs, settings):
    from django.apps import apps

    settings.AI_PARTNER_REPLY_TIMEOUT_SECONDS = 0
    build_everything(client, full_venture, run_jobs)
    assert [k for k in FakeStorage.objects if k[0] == PRIVATE]
    assert AIRun.objects.filter(venture_id=full_venture["id"]).exists()
    assert client.delete(f"{BASE}/ventures/{full_venture['id']}").status_code in (200, 204)

    erased = ventures.erase_due(
        timezone.now() + timedelta(days=settings.VENTURE_DELETE_GRACE_DAYS + 1)
    )
    assert erased == 1
    assert not Venture.objects.filter(pk=full_venture["id"]).exists()
    assert not [k for k in FakeStorage.objects if k[0] == PRIVATE]

    leftovers = {}
    for model in apps.get_models():
        if not model._meta.app_label.startswith("tk_"):
            continue
        fields = {f.name for f in model._meta.get_fields()}
        if "venture" in fields and model._meta.model_name != "airun":
            count = model.objects.filter(venture_id=full_venture["id"]).count()
            if count:
                leftovers[model.__name__] = count
    assert leftovers == {}
    # Model usage keeps only counts and sizes, and no longer points at the venture.
    assert not AIRun.objects.filter(venture_id=full_venture["id"]).exists()
    assert AuditLog.objects.filter(action="toolkit.venture_erased").exists()
