import httpx
import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework.test import APIClient

from apps.toolkit.advisor.models import AdvisorMessage
from apps.toolkit.ai import voice
from apps.toolkit.ai.models import AIRun
from apps.toolkit.ai.providers.fake import FakeLLMProvider
from apps.toolkit.testing import BASE

pytestmark = pytest.mark.django_db

VOICE = f"{BASE}/advisor/voice"


def link_url(message_id):
    return f"{BASE}/advisor/messages/{message_id}/speech"


def recording(content=b"\x1aE\xdf\xa3fake-webm", content_type="audio/webm"):
    return SimpleUploadedFile("speech.webm", content, content_type=content_type)


def answer(member, text="Charge from day one.", **meta):
    return AdvisorMessage.objects.create(owner=member, role="assistant", text=text, meta=meta)


def hear(client, message_id):
    """Asks for the answer's address, then streams it like an audio player would: no sign in."""
    link = client.post(link_url(message_id))
    assert link.status_code == 200, link.content
    response = APIClient().get(link.json()["url"])
    body = b"".join(response.streaming_content) if response.streaming else response.content
    return response, body


@pytest.fixture
def quick(settings, monkeypatch):
    """Replies come back in the same request, as they do when the model is quick."""
    from apps.toolkit.advisor import service
    from apps.toolkit.jobs import services as jobs
    from apps.toolkit.jobs.models import AIJob

    settings.AI_PARTNER_REPLY_TIMEOUT_SECONDS = 5

    def run_now(job_id, seconds):
        jobs.run(job_id)
        return AIJob.objects.get(pk=job_id)

    monkeypatch.setattr(service, "wait_for", run_now)


def test_a_spoken_turn_is_heard_answered_briefly_and_ready_to_play(client, member, quick):
    FakeLLMProvider.canned["advisor.reply"] = {
        "reply": "Start with ten calls.",
        "next_steps": ["Call ten traders"],
        "frameworks": ["yc"],
    }
    response = client.post(VOICE, {"audio": recording()}, format="multipart")
    assert response.status_code == 201, response.content
    body = response.json()
    assert body["user_message"]["text"] == voice.FAKE_TRANSCRIPT
    assert body["assistant_message"]["text"] == "Start with ten calls."
    assert body["speech_url"].startswith("/api/v1/toolkit/advisor/speech/")
    call = [c for c in FakeLLMProvider.calls if c.prompt_id == "advisor.reply"][-1]
    assert "spoken aloud" in call.variables["style"]
    played = APIClient().get(body["speech_url"])
    assert played.status_code == 200
    assert {r.prompt_id for r in AIRun.objects.all()} >= {"voice.transcribe", "voice.speak"}


def test_a_typed_turn_gets_the_full_written_style(client, quick):
    FakeLLMProvider.canned["advisor.reply"] = {"reply": "Ok.", "next_steps": [], "frameworks": []}
    response = client.post(f"{BASE}/advisor/messages", {"text": "Hello"}, format="json")
    assert response.json()["speech_url"] is None
    call = [c for c in FakeLLMProvider.calls if c.prompt_id == "advisor.reply"][-1]
    assert call.variables["style"].startswith("written")


def test_unsupported_or_oversized_recordings_are_refused(client, monkeypatch):
    bad = client.post(
        VOICE, {"audio": recording(content_type="video/quicktime")}, format="multipart"
    )
    assert bad.status_code == 400 and "audio" in str(bad.json())
    monkeypatch.setattr(voice, "MAX_AUDIO_BYTES", 4)
    big = client.post(VOICE, {"audio": recording()}, format="multipart")
    assert big.status_code == 400 and "too long" in str(big.json())
    assert AIRun.objects.count() == 0 and AdvisorMessage.objects.count() == 0


def test_an_answer_streams_and_is_kept_for_a_second_listen(client, member):
    message = answer(member, next_steps=["Call ten traders"])
    first, audio = hear(client, message.pk)
    assert first.status_code == 200 and first["Content-Type"] == "audio/wav"
    assert audio.startswith(b"RIFF")
    again, audio_again = hear(client, message.pk)
    assert again.status_code == 200 and audio_again == audio
    assert AIRun.objects.filter(prompt_id="voice.speak").count() == 1  # the second came from cache


def test_a_speech_address_is_for_one_answer_and_expires(client, member, other, monkeypatch):
    from apps.toolkit.advisor import views

    mine = AdvisorMessage.objects.create(owner=member, role="user", text="Hi")
    theirs = answer(other)
    assert client.post(link_url(mine.pk)).status_code == 404
    assert client.post(link_url(theirs.pk)).status_code == 404
    assert APIClient().get(f"{BASE}/advisor/speech/not-a-token").status_code == 404
    url = client.post(link_url(answer(member).pk)).json()["url"]
    monkeypatch.setattr(views, "SPEECH_LINK_SECONDS", -1)
    assert APIClient().get(url).status_code == 404


def test_without_ai_there_is_no_voice(client, member, settings):
    message = answer(member)
    settings.AI_PROVIDER = ""
    response = client.post(VOICE, {"audio": recording()}, format="multipart")
    assert response.status_code == 503 and response.json()["code"] == "ai_off"
    url = client.post(link_url(message.pk)).json()["url"]
    assert APIClient().get(url).status_code == 503


def test_voice_counts_towards_the_daily_allowance(client, settings, quick):
    settings.AI_DAILY_RUN_CEILING = 0
    capped = client.post(VOICE, {"audio": recording()}, format="multipart")
    assert capped.status_code == 429 and capped.json()["code"] == "ai_daily_limit"


def test_a_spoken_answer_is_read_without_its_steps_and_a_written_one_with_them(member):
    from apps.toolkit.advisor.views import spoken_text

    written = answer(member, "Do this.", next_steps=["Call", "Price"])
    assert spoken_text(written) == "Do this.\n\nNext steps. 1. Call 2. Price"
    spoken = answer(member, "Do this.", next_steps=["Call"], voice=True)
    assert spoken_text(spoken) == "Do this."


@pytest.fixture
def openai(settings, monkeypatch):
    """The real HTTP path, against a stand-in for the service."""
    settings.AI_PROVIDER = "http"
    settings.AI_BASE_URL = "https://llm.test/v1"
    settings.AI_API_KEY = "sk-test"
    seen: dict = {}
    replies: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["path"] = request.url.path
        seen["auth"] = request.headers["authorization"]
        seen["body"] = request.content
        return replies.get("next") or httpx.Response(404)

    def client():
        return httpx.Client(
            base_url="https://llm.test/v1",
            headers={"Authorization": "Bearer sk-test"},
            transport=httpx.MockTransport(handler),
        )

    monkeypatch.setattr(voice, "_client", client)
    return seen, replies


def test_transcription_calls_the_service_with_the_recording(member, openai):
    seen, replies = openai
    replies["next"] = httpx.Response(
        200, json={"text": " Hello there ", "usage": {"input_tokens": 9}}
    )
    text = voice.transcribe(owner_id=member.pk, audio=b"abc", content_type="audio/webm;codecs=opus")
    assert text == "Hello there" and seen["path"] == "/v1/audio/transcriptions"
    assert b'filename="speech.webm"' in seen["body"] and b"gpt-4o-mini-transcribe" in seen["body"]
    assert AIRun.objects.get().input_tokens == 9


def test_speech_asks_for_mp3_in_the_configured_voice(member, openai, settings):
    seen, replies = openai
    settings.AI_TTS_VOICE = "sage"
    replies["next"] = httpx.Response(200, content=b"ID3mp3", headers={"content-type": "audio/mpeg"})
    speech = voice.speak(owner_id=member.pk, text="Hello")
    assert speech.audio == b"ID3mp3" and speech.content_type == "audio/mpeg"
    assert seen["path"] == "/v1/audio/speech"
    assert b'"voice":"sage"' in seen["body"].replace(b" ", b"") and b'"mp3"' in seen["body"]


def test_a_voice_the_model_refuses_falls_back_to_one_it_has(member, openai, settings, monkeypatch):
    settings.AI_TTS_VOICE = "cedar"
    voices: list[bytes] = []

    def handler(request: httpx.Request) -> httpx.Response:
        voices.append(request.content)
        if b'"cedar"' in request.content.replace(b" ", b""):
            return httpx.Response(400, json={"error": {"message": "Invalid voice"}})
        return httpx.Response(200, content=b"ID3ash", headers={"content-type": "audio/mpeg"})

    monkeypatch.setattr(
        voice,
        "_client",
        lambda: httpx.Client(
            base_url="https://llm.test/v1", transport=httpx.MockTransport(handler)
        ),
    )
    assert voice.speak(owner_id=member.pk, text="Hello").audio == b"ID3ash"
    assert len(voices) == 2 and b'"voice":"ash"' in voices[1].replace(b" ", b"")


@pytest.mark.parametrize(("status", "error"), [(429, "TransientError"), (401, "JobFailed")])
def test_service_failures_become_clear_errors(member, openai, status, error):
    from apps.toolkit.jobs import services as jobs

    _, replies = openai
    replies["next"] = httpx.Response(status, json={})
    with pytest.raises(getattr(jobs, error)):
        voice.speak(owner_id=member.pk, text="Hello")


def test_with_onyekas_own_voice_speech_comes_from_elevenlabs(member, settings, monkeypatch):
    settings.AI_PROVIDER = "http"
    settings.AI_BASE_URL = "https://llm.test/v1"
    settings.AI_API_KEY = "sk-test"
    settings.ELEVENLABS_API_KEY = "xi-test"
    settings.ELEVENLABS_VOICE_ID = "onyeka123"
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["path"] = request.url.path
        seen["query"] = str(request.url.query)
        seen["key"] = request.headers.get("xi-api-key")
        seen["body"] = request.content
        return httpx.Response(200, content=b"ID3cloned", headers={"content-type": "audio/mpeg"})

    monkeypatch.setattr(
        voice,
        "_eleven_client",
        lambda: httpx.Client(base_url="https://xi.test/v1", transport=httpx.MockTransport(handler)),
    )
    stream = voice.open_speech(owner_id=member.pk, text="Hello founder")
    assert b"".join(stream.chunks) == b"ID3cloned" and stream.content_type == "audio/mpeg"
    assert seen["path"] == "/v1/text-to-speech/onyeka123/stream"
    assert "mp3" in seen["query"] and b"eleven_flash_v2_5" in seen["body"]
    assert AIRun.objects.get().provider == "elevenlabs"
    assert voice.speech_voice().startswith("elevenlabs:onyeka123")


def test_the_website_on_another_site_may_play_the_audio(client, member):
    # The site (vercel.app) and the API (railway.app) are different sites, so the audio must not
    # carry the API's default same-site resource policy, or the browser blocks it.
    response, _ = hear(client, answer(member).pk)
    assert response["Cross-Origin-Resource-Policy"] == "cross-origin"
    again, _ = hear(client, answer(member, "Second.").pk)
    assert again["Cross-Origin-Resource-Policy"] == "cross-origin"
