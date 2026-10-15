import httpx
import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from apps.toolkit.advisor.models import AdvisorMessage
from apps.toolkit.ai import voice
from apps.toolkit.ai.models import AIRun
from apps.toolkit.testing import BASE

pytestmark = pytest.mark.django_db

TRANSCRIBE = f"{BASE}/advisor/transcribe"


def speech_url(message_id):
    return f"{BASE}/advisor/messages/{message_id}/speech"


def recording(content=b"\x1aE\xdf\xa3fake-webm", content_type="audio/webm"):
    return SimpleUploadedFile("speech.webm", content, content_type=content_type)


def answer(member, text="Charge from day one.", **meta):
    return AdvisorMessage.objects.create(owner=member, role="assistant", text=text, meta=meta)


def test_a_recording_becomes_text_and_is_counted_as_ai_use(client):
    response = client.post(TRANSCRIBE, {"audio": recording()}, format="multipart")
    assert response.status_code == 200, response.content
    assert response.json() == {"text": voice.FAKE_TRANSCRIPT}
    run = AIRun.objects.get()
    assert run.prompt_id == "voice.transcribe" and run.agent == "voice"


def test_unsupported_or_oversized_recordings_are_refused(client, monkeypatch):
    bad = client.post(
        TRANSCRIBE, {"audio": recording(content_type="video/quicktime")}, format="multipart"
    )
    assert bad.status_code == 400 and "audio" in str(bad.json())
    monkeypatch.setattr(voice, "MAX_AUDIO_BYTES", 4)
    big = client.post(TRANSCRIBE, {"audio": recording()}, format="multipart")
    assert big.status_code == 400 and "too long" in str(big.json())
    assert AIRun.objects.count() == 0


def test_an_answer_can_be_heard_and_is_kept_for_a_second_listen(client, member):
    message = answer(member, next_steps=["Call ten traders"])
    first = client.get(speech_url(message.pk))
    assert first.status_code == 200 and first["Content-Type"] == "audio/wav"
    assert first.content.startswith(b"RIFF")
    assert client.get(speech_url(message.pk)).status_code == 200
    assert AIRun.objects.filter(prompt_id="voice.speak").count() == 1  # the second came from cache


def test_only_onyekas_own_answers_in_your_conversation_can_be_heard(client, member, other):
    mine = AdvisorMessage.objects.create(owner=member, role="user", text="Hi")
    theirs = answer(other)
    assert client.get(speech_url(mine.pk)).status_code == 404
    assert client.get(speech_url(theirs.pk)).status_code == 404


def test_without_ai_there_is_no_voice(client, member, settings):
    settings.AI_PROVIDER = ""
    message = answer(member)
    assert client.get(speech_url(message.pk)).status_code == 503
    response = client.post(TRANSCRIBE, {"audio": recording()}, format="multipart")
    assert response.status_code == 503 and response.json()["code"] == "ai_off"


def test_voice_counts_towards_the_daily_allowance(client, settings):
    settings.AI_DAILY_RUN_CEILING = 1
    assert client.post(TRANSCRIBE, {"audio": recording()}, format="multipart").status_code == 200
    capped = client.post(TRANSCRIBE, {"audio": recording()}, format="multipart")
    assert capped.status_code == 429 and capped.json()["code"] == "ai_daily_limit"


def test_the_spoken_text_reads_the_next_steps_too(member):
    from apps.toolkit.advisor.views import spoken_text

    message = answer(member, "Do this.", next_steps=["Call", "Price"])
    assert spoken_text(message) == "Do this.\n\nNext steps. 1. Call 2. Price"


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


@pytest.mark.parametrize(("status", "error"), [(429, "TransientError"), (401, "JobFailed")])
def test_service_failures_become_clear_errors(member, openai, status, error):
    from apps.toolkit.jobs import services as jobs

    _, replies = openai
    replies["next"] = httpx.Response(status, json={})
    with pytest.raises(getattr(jobs, error)):
        voice.speak(owner_id=member.pk, text="Hello")
