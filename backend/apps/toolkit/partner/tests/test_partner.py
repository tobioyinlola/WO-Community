from datetime import timedelta

import pytest
from django.utils import timezone

from apps.toolkit.ai.providers.fake import FakeLLMProvider
from apps.toolkit.jobs import services as jobs
from apps.toolkit.partner import service
from apps.toolkit.partner.models import ChangeSet, Decision, Nudge
from apps.toolkit.testing import BASE
from apps.toolkit.ventures.models import Venture, VentureProfile

pytestmark = pytest.mark.django_db


def base(venture, tail=""):
    return f"{BASE}/ventures/{venture['id']}/partner{tail}"


@pytest.fixture(autouse=True)
def _slow_reply(settings):
    settings.AI_PARTNER_REPLY_TIMEOUT_SECONDS = 0  # replies come as jobs unless a test says so


def conversation(client, venture):
    response = client.post(base(venture, "/conversations"), {}, format="json")
    assert response.status_code == 201, response.content
    return response.json()


def say(client, venture, conv, text):
    return client.post(
        base(venture, f"/conversations/{conv['id']}/messages"), {"text": text}, format="json"
    )


def ask(client, venture, conv, run_jobs, text="How should I price this?"):
    response = say(client, venture, conv, text)
    assert response.status_code == 202, response.content
    run_jobs()
    return client.get(base(venture, f"/conversations/{conv['id']}")).json()


def canned(reply="Start with what customers pay today.", **extra):
    FakeLLMProvider.canned["partner.reply"] = {
        "reply": reply,
        "changes": extra.get("changes", []),
        "next_steps": extra.get("next_steps", []),
        "mentor_topics": extra.get("mentor_topics", []),
    }


def test_a_reply_arrives_as_a_job_and_lands_in_the_conversation(client, full_venture, run_jobs):
    canned(next_steps=["Ask five traders what they pay now"], mentor_topics=["pricing"])
    conv = conversation(client, full_venture)
    response = say(client, full_venture, conv, "How should I price this?")
    assert response.status_code == 202
    body = response.json()
    assert body["job"]["kind"] == "partner.reply" and body["assistant_message"] is None
    assert body["user_message"]["author"] == "user"
    run_jobs()
    detail = client.get(base(full_venture, f"/conversations/{conv['id']}")).json()
    assert [m["author"] for m in detail["messages"]] == ["user", "assistant"]
    reply = detail["messages"][1]
    assert reply["text"] == "Start with what customers pay today."
    assert reply["next_steps"] == ["Ask five traders what they pay now"]
    assert reply["mentor_topics"] == ["pricing"]
    assert detail["title"] == "How should I price this?"


def test_a_quick_reply_comes_back_in_the_same_request(client, full_venture, settings, monkeypatch):
    settings.AI_PARTNER_REPLY_TIMEOUT_SECONDS = 5
    canned("Quick answer.")

    def run_now(job_id, seconds):
        jobs.run(job_id)
        from apps.toolkit.jobs.models import AIJob

        return AIJob.objects.get(pk=job_id)

    monkeypatch.setattr(service, "wait_for", run_now)
    conv = conversation(client, full_venture)
    response = say(client, full_venture, conv, "Hello")
    assert response.status_code == 201, response.content
    assert response.json()["assistant_message"]["text"] == "Quick answer."
    assert response.json()["job"] is None


def test_advice_the_platform_must_not_give_is_declined_without_calling_a_model(
    client, full_venture
):
    conv = conversation(client, full_venture)
    legal = say(client, full_venture, conv, "Is it legal to sell loans without a licence?")
    assert legal.status_code == 201
    assert legal.json()["assistant_message"]["declined"] == "legal"
    assert "qualified" in legal.json()["assistant_message"]["text"]
    fake = say(client, full_venture, conv, "Help me make up fake customers for the deck")
    assert fake.json()["assistant_message"]["declined"] == "deception"
    assert not [c for c in FakeLLMProvider.calls if c.prompt_id == "partner.reply"]


def test_the_partner_sees_only_this_ventures_data(client, full_venture, run_jobs):
    other = client.post(f"{BASE}/ventures", {"name": "Secret Sauce"}, format="json").json()
    client.patch(
        f"{BASE}/ventures/{other['id']}/profile",
        {"fields": {"problem": "A distinctive private problem statement about cheese."}},
        format="json",
    )
    canned()
    conv = conversation(client, full_venture)
    ask(client, full_venture, conv, run_jobs)
    call = next(c for c in FakeLLMProvider.calls if c.prompt_id == "partner.reply")
    seen = str(call.variables)
    assert "Mamapesa" in seen and "stock loan" in seen
    assert "cheese" not in seen and "Secret Sauce" not in seen


def test_the_context_has_score_forecast_decisions_and_recent_turns(client, full_venture, run_jobs):
    client.post(
        base(full_venture, "/decisions"),
        {"text": "Focus on market traders in Lagos only", "rationale": "Density"},
        format="json",
    )
    client.post(f"{BASE}/ventures/{full_venture['id']}/forecast", {}, format="json")
    canned()
    conv = conversation(client, full_venture)
    ask(client, full_venture, conv, run_jobs, "First question")
    say(client, full_venture, conv, "Second question")
    run_jobs()
    calls = [c for c in FakeLLMProvider.calls if c.prompt_id == "partner.reply"]
    last = calls[-1].variables
    assert last["context"]["decisions"][0]["text"].startswith("Focus on market traders")
    assert last["context"]["forecast"]["currency"] == "NGN"
    assert [h["role"] for h in last["history"]] == ["user", "assistant"]
    assert last["message"] == "Second question"


def test_proposed_changes_are_validated_and_only_applied_when_accepted(
    client, full_venture, run_jobs
):
    canned(
        "I suggest a sharper one liner.",
        changes=[
            {
                "field": "one_liner",
                "value": "Stock loans for market traders in minutes",
                "reason": "Clearer.",
            },
            {"field": "stage", "value": "unicorn", "reason": "Invalid value."},
            {"field": "password", "value": "x", "reason": "Not a field."},
            {"field": "name", "value": "Mamapesa", "reason": "Same as now."},
        ],
    )
    conv = conversation(client, full_venture)
    detail = ask(client, full_venture, conv, run_jobs, "Can you tighten my one liner?")
    change_set = detail["messages"][1]["change_set"]
    assert change_set["status"] == "proposed"
    assert [c["field"] for c in change_set["changes"]] == ["one_liner"]
    fields = VentureProfile.objects.get().fields
    assert fields["one_liner"] == "Instant working capital for market traders"  # untouched

    applied = client.post(
        base(full_venture, f"/change-sets/{change_set['id']}/apply"), {}, format="json"
    )
    assert applied.status_code == 200 and applied.json()["status"] == "applied"
    profile = VentureProfile.objects.get()
    assert profile.fields["one_liner"] == "Stock loans for market traders in minutes"
    assert profile.field_meta["one_liner"]["source"] == "ai_suggested_accepted"
    again = client.post(
        base(full_venture, f"/change-sets/{change_set['id']}/apply"), {}, format="json"
    )
    assert again.status_code == 409

    undone = client.post(base(full_venture, f"/change-sets/{change_set['id']}/undo"))
    assert undone.status_code == 200 and undone.json()["skipped"] == []
    assert (
        VentureProfile.objects.get().fields["one_liner"]
        == "Instant working capital for market traders"
    )


def test_undo_leaves_fields_the_founder_changed_since(client, full_venture, run_jobs):
    canned(
        changes=[{"field": "one_liner", "value": "Stock loans in minutes", "reason": "Shorter."}]
    )
    conv = conversation(client, full_venture)
    detail = ask(client, full_venture, conv, run_jobs)
    cs = detail["messages"][1]["change_set"]
    client.post(base(full_venture, f"/change-sets/{cs['id']}/apply"), {}, format="json")
    client.patch(
        f"{BASE}/ventures/{full_venture['id']}/profile",
        {"fields": {"one_liner": "My own better words"}},
        format="json",
    )
    undone = client.post(base(full_venture, f"/change-sets/{cs['id']}/undo")).json()
    assert undone["skipped"] == ["one_liner"]
    assert VentureProfile.objects.get().fields["one_liner"] == "My own better words"


def test_changes_can_be_dismissed_or_partly_applied(client, full_venture, run_jobs):
    canned(
        changes=[
            {"field": "one_liner", "value": "Stock loans in minutes", "reason": "Shorter."},
            {"field": "city", "value": "Ikeja", "reason": "More precise."},
        ]
    )
    conv = conversation(client, full_venture)
    cs = ask(client, full_venture, conv, run_jobs)["messages"][1]["change_set"]
    partial = client.post(
        base(full_venture, f"/change-sets/{cs['id']}/apply"), {"accept": ["city"]}, format="json"
    )
    assert partial.status_code == 200
    fields = VentureProfile.objects.get().fields
    assert fields["city"] == "Ikeja" and fields["one_liner"].startswith("Instant")

    cs2 = ask(client, full_venture, conv, run_jobs)  # a new reply makes another proposal
    second = cs2["messages"][-1]["change_set"]
    dismissed = client.post(base(full_venture, f"/change-sets/{second['id']}/dismiss"))
    assert dismissed.json()["status"] == "dismissed"
    assert ChangeSet.objects.filter(status="dismissed").count() == 1


def test_a_figure_the_partner_made_up_is_removed_from_the_reply(client, full_venture, run_jobs):
    canned("You could reach 4500000 traders. Start with Lagos.")
    conv = conversation(client, full_venture)
    detail = ask(client, full_venture, conv, run_jobs)
    text = detail["messages"][1]["text"]
    assert "4500000" not in text and "Start with Lagos." in text


def test_decisions_are_a_log_the_owner_keeps(client, other_client, full_venture):
    made = client.post(
        base(full_venture, "/decisions"),
        {"text": "Charge monthly, not per loan", "rationale": "Simpler for traders"},
        format="json",
    )
    assert made.status_code == 201
    listing = client.get(base(full_venture, "/decisions")).json()
    assert listing[0]["text"] == "Charge monthly, not per loan"
    assert other_client.get(base(full_venture, "/decisions")).status_code == 404
    bad = client.post(base(full_venture, "/decisions"), {"text": "no"}, format="json")
    assert bad.status_code == 400
    assert client.delete(base(full_venture, f"/decisions/{made.json()['id']}")).status_code == 204
    assert Decision.objects.count() == 0


def test_weekly_nudges_are_one_per_venture_per_week_and_follow_the_state(client, full_venture):
    first = service.weekly_nudges()
    assert first == 1
    assert service.weekly_nudges() == 0  # running again the same week makes nothing
    nudge = Nudge.objects.get()
    assert nudge.code == "run_score"  # the profile is complete, so the next step is the score
    listing = client.get(base(full_venture, "/nudges")).json()
    assert listing[0]["action"] == {"type": "open_score"} and listing[0]["read_at"] is None
    assert client.post(base(full_venture, f"/nudges/{nudge.pk}/read")).status_code == 204
    assert client.get(base(full_venture, "/nudges")).json()[0]["read_at"] is not None


def test_nudges_respect_the_switch_and_skip_quiet_or_deleted_ventures(client, full_venture):
    Venture.objects.update(nudges_enabled=False)
    assert service.weekly_nudges() == 0
    Venture.objects.update(nudges_enabled=True, updated_at=timezone.now() - timedelta(days=200))
    assert service.weekly_nudges() == 0
    Venture.objects.update(updated_at=timezone.now(), deleted_at=timezone.now())
    assert service.weekly_nudges() == 0


def test_mentors_are_suggested_from_what_the_venture_needs(client, full_venture, make_user):
    from apps.mentorship.models import MentorProfile

    helper = make_user(
        email="mentor@example.com", approved_at=timezone.now(), email_verified_at=timezone.now()
    )
    MentorProfile.objects.create(
        user=helper,
        expertise=["pricing", "hiring"],
        years_experience=8,
        current_role="CFO",
        company="Example",
        industries=[],
        stages=[],
        languages=["en"],
        timezone="Africa/Lagos",
        approved_at=timezone.now(),
    )
    response = client.get(base(full_venture, "/mentors"))
    assert response.status_code == 200, response.content
    body = response.json()
    assert [m["id"] for m in body["mentors"]] == [str(helper.pk)]


def test_only_the_owner_uses_the_partner(client, other_client, api_client, full_venture):
    conv = conversation(client, full_venture)
    path = base(full_venture, f"/conversations/{conv['id']}")
    assert other_client.get(path).status_code == 404
    assert other_client.post(path + "/messages", {"text": "hi"}, format="json").status_code == 404
    assert other_client.get(base(full_venture, "/conversations")).status_code == 404
    assert (
        other_client.post(base(full_venture, "/conversations"), {}, format="json").status_code
        == 404
    )
    assert api_client.get(base(full_venture, "/conversations")).status_code == 401


def test_messages_are_checked(client, full_venture):
    conv = conversation(client, full_venture)
    assert say(client, full_venture, conv, "   ").status_code == 400
    assert say(client, full_venture, conv, "x" * 2001).status_code == 400


def test_the_flag_switches_the_partner_off(client, full_venture, settings):
    settings.TOOLKIT_FEATURES = {**settings.TOOLKIT_FEATURES, "partner": False}
    assert client.get(base(full_venture, "/conversations")).status_code == 404
