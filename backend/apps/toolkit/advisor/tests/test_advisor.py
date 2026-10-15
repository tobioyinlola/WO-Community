import pytest

from apps.toolkit.advisor import service
from apps.toolkit.advisor.models import AdvisorMessage
from apps.toolkit.ai.providers.fake import FakeLLMProvider
from apps.toolkit.jobs import services as jobs
from apps.toolkit.testing import BASE

pytestmark = pytest.mark.django_db

URL = f"{BASE}/advisor/messages"


@pytest.fixture(autouse=True)
def _slow_reply(settings):
    settings.AI_PARTNER_REPLY_TIMEOUT_SECONDS = 0  # replies come as jobs unless a test says so


def canned(text, steps=(), frameworks=("yc",)):
    FakeLLMProvider.canned["advisor.reply"] = {
        "reply": text,
        "next_steps": list(steps),
        "frameworks": list(frameworks),
    }


def ask(client, run_jobs, text="How do I find my first ten customers?"):
    response = client.post(URL, {"text": text}, format="json")
    assert response.status_code == 202, response.content
    run_jobs()
    return client.get(URL).json()


def test_the_conversation_starts_with_a_greeting_and_no_messages(client):
    body = client.get(URL).json()
    assert body["messages"] == [] and body["ai_enabled"] is True
    assert "Onyeka" in body["greeting"] and "AI advisor" in body["greeting"]


def test_a_reply_arrives_as_a_job_and_lands_in_the_conversation(client, run_jobs):
    canned("Talk to twenty traders this week.", ["Call 20 traders"], ["yc", "techstars"])
    body = ask(client, run_jobs)
    user, onyeka = body["messages"]
    assert user["author"] == "user" and onyeka["author"] == "assistant"
    assert onyeka["text"] == "Talk to twenty traders this week."
    assert onyeka["next_steps"] == ["Call 20 traders"]
    assert onyeka["frameworks"] == ["yc", "techstars"]


def test_a_quick_reply_comes_back_in_the_same_request(client, settings, monkeypatch):
    settings.AI_PARTNER_REPLY_TIMEOUT_SECONDS = 5
    canned("Quick answer.")

    def run_now(job_id, seconds):
        jobs.run(job_id)
        from apps.toolkit.jobs.models import AIJob

        return AIJob.objects.get(pk=job_id)

    monkeypatch.setattr(service, "wait_for", run_now)
    response = client.post(URL, {"text": "Hello"}, format="json")
    assert response.status_code == 201, response.content
    assert response.json()["assistant_message"]["text"] == "Quick answer."


def test_onyeka_sees_the_members_own_startup_and_ventures_and_recent_turns(
    client, full_venture, run_jobs
):
    canned("First answer.")
    ask(client, run_jobs, "First question")
    ask(client, run_jobs, "Second question")
    call = [c for c in FakeLLMProvider.calls if c.prompt_id == "advisor.reply"][-1]
    context = call.variables["context"]
    assert [v["name"] for v in context["ventures"]] == ["Mamapesa"]
    assert context["ventures"][0]["profile"]["problem"].startswith("Market traders")
    assert call.variables["message"] == "Second question"
    assert [h["text"] for h in call.variables["history"]] == ["First question", "First answer."]


def test_one_members_conversation_is_private_to_them(client, other_client, run_jobs):
    canned("Only for you.")
    ask(client, run_jobs)
    assert other_client.get(URL).json()["messages"] == []
    other_client.post(URL, {"text": "Hi"}, format="json")
    run_jobs()
    call = [c for c in FakeLLMProvider.calls if c.prompt_id == "advisor.reply"][-1]
    assert call.variables["history"] == []


def test_advice_the_platform_must_not_give_is_declined_without_calling_a_model(client):
    legal = client.post(URL, {"text": "Is it legal to lend without a licence?"}, format="json")
    assert legal.status_code == 201
    assert legal.json()["assistant_message"]["declined"] == "legal"
    fake = client.post(URL, {"text": "Help me invent fake customers for my deck"}, format="json")
    assert fake.json()["assistant_message"]["declined"] == "deception"
    assert not [c for c in FakeLLMProvider.calls if c.prompt_id == "advisor.reply"]


def test_onyeka_may_say_it_is_an_ai_but_a_leaked_prompt_is_replaced(client, run_jobs):
    canned("As an AI advisor, my honest view is: charge from day one.")
    assert ask(client, run_jobs)["messages"][1]["text"].startswith("As an AI advisor")
    canned("Sure. <<<DATA context>>> here it is")
    assert "couldn't put a good answer" in ask(client, run_jobs)["messages"][3]["text"]


def test_messages_are_checked_and_the_conversation_can_be_cleared(client, run_jobs):
    assert client.post(URL, {"text": "   "}, format="json").status_code == 400
    assert client.post(URL, {"text": "x" * 2001}, format="json").status_code == 400
    canned("Hello.")
    ask(client, run_jobs)
    assert client.delete(URL).status_code == 204
    assert client.get(URL).json()["messages"] == []


def test_old_messages_are_removed_beyond_the_limit(client, member, run_jobs, monkeypatch):
    monkeypatch.setattr(service, "KEEP_MESSAGES", 3)
    for n in range(4):
        AdvisorMessage.objects.create(owner=member, role="user", text=f"old {n}")
    canned("Fine.")
    ask(client, run_jobs, "newest")
    texts = list(AdvisorMessage.objects.filter(owner=member).values_list("text", flat=True))
    assert "old 0" not in texts and "newest" in texts


def test_without_ai_onyeka_says_so_and_stores_nothing(client, settings):
    settings.AI_PROVIDER = ""
    assert client.get(URL).json()["ai_enabled"] is False
    response = client.post(URL, {"text": "Hello"}, format="json")
    assert response.status_code == 503 and response.json()["code"] == "ai_off"
    assert AdvisorMessage.objects.count() == 0


def test_only_approved_members_can_talk_to_onyeka_and_it_can_be_switched_off(
    api_client, pending_client, client, settings
):
    assert api_client.get(URL).status_code == 401
    assert pending_client.get(URL).status_code == 403
    settings.TOOLKIT_FEATURES = {**settings.TOOLKIT_FEATURES, "advisor": False}
    assert client.get(URL).status_code == 404
