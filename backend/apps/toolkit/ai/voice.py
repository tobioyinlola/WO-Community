"""Speech in and out: turning a member's recording into text, and an answer into audio.

Both use the same OpenAI compatible service as the text models (``AI_BASE_URL``, ``AI_API_KEY``):
``/audio/transcriptions`` and ``/audio/speech``. Like every model call they count towards the
member's daily allowance and are recorded as an ``AIRun`` with sizes only, never the words or the
audio. With the offline stand-in (``AI_PROVIDER=fake``) they answer without any network call.
"""

import io
import struct
import time
import wave
from dataclasses import dataclass
from uuid import UUID

import httpx
import structlog
from django.conf import settings

from apps.core import metrics
from apps.toolkit.ai import runner
from apps.toolkit.ai.models import AIRun
from apps.toolkit.jobs.services import JobFailed, TransientError

logger = structlog.get_logger(__name__)

MAX_AUDIO_BYTES = 4 * 1024 * 1024  # about four minutes of compressed speech
MAX_SPEECH_CHARS = 4000
AUDIO_TYPES = {
    "audio/webm": "webm",
    "audio/ogg": "ogg",
    "audio/mp4": "mp4",
    "audio/mpeg": "mp3",
    "audio/mp3": "mp3",
    "audio/wav": "wav",
    "audio/x-wav": "wav",
    "audio/m4a": "m4a",
    "audio/x-m4a": "m4a",
    "audio/aac": "m4a",
}
FAKE_TRANSCRIPT = "How do I find my first ten paying customers?"


@dataclass(frozen=True)
class Speech:
    audio: bytes
    content_type: str


def extension_for(content_type: str) -> str | None:
    """The file extension the service expects for a recording's type, or None if unsupported."""
    return AUDIO_TYPES.get(content_type.split(";")[0].strip().lower())


def _fake() -> bool:
    return str(settings.AI_PROVIDER).strip() == "fake"


def _client() -> httpx.Client:
    return httpx.Client(
        base_url=settings.AI_BASE_URL.rstrip("/"),
        headers={"Authorization": f"Bearer {settings.AI_API_KEY}"},
        timeout=httpx.Timeout(settings.AI_REQUEST_TIMEOUT_SECONDS, connect=5.0),
    )


def _record(
    owner_id: UUID, what: str, model: str, started: float, outcome: str, **sizes: int
) -> None:
    AIRun.objects.create(
        owner_id=owner_id,
        agent="voice",
        provider="fake" if _fake() else "http",
        model=model,
        prompt_id=f"voice.{what}",
        input_tokens=sizes.get("input_tokens", 0),
        output_tokens=sizes.get("output_tokens", 0),
        duration_ms=int((time.monotonic() - started) * 1000),
        currency=settings.AI_COST_CURRENCY,
        outcome=outcome,
    )
    metrics.observe_ai_run(
        f"voice.{what}", outcome, sizes.get("input_tokens", 0), sizes.get("output_tokens", 0)
    )


def _check(response: httpx.Response) -> None:
    status = response.status_code
    if status in (401, 403):
        logger.error("toolkit_voice_misconfigured", status=status)
        raise JobFailed("ai_unavailable", "The assistant is not available right now.")
    if status in (408, 409, 425, 429) or status >= 500:
        raise TransientError(f"status {status}")
    if status >= 400:
        raise JobFailed("request_rejected", "That recording could not be processed.")


def transcribe(*, owner_id: UUID, audio: bytes, content_type: str) -> str:
    """The words in a recording. ``JobFailed`` or ``TransientError`` when it cannot be done."""
    runner.require_ai()
    extension = extension_for(content_type)
    if extension is None:
        raise JobFailed("unsupported_audio", "That kind of recording is not supported.")
    if not audio or len(audio) > MAX_AUDIO_BYTES:
        raise JobFailed("audio_too_long", "That recording is too long. Keep it under two minutes.")
    runner.check_ceiling(owner_id)
    model = settings.AI_TRANSCRIBE_MODEL
    started = time.monotonic()
    if _fake():
        _record(owner_id, "transcribe", model, started, "ok")
        return FAKE_TRANSCRIPT
    try:
        with _client() as client:
            response = client.post(
                "/audio/transcriptions",
                data={"model": model, "response_format": "json"},
                files={"file": (f"speech.{extension}", audio, content_type.split(";")[0])},
            )
    except httpx.HTTPError as exc:
        _record(owner_id, "transcribe", model, started, "timeout")
        raise TransientError("voice network error") from exc
    try:
        _check(response)
    except (JobFailed, TransientError):
        _record(owner_id, "transcribe", model, started, "rejected")
        raise
    try:
        body = response.json()
    except ValueError as exc:
        raise TransientError("unreadable transcription") from exc
    usage = body.get("usage") or {}
    _record(
        owner_id,
        "transcribe",
        model,
        started,
        "ok",
        input_tokens=int(usage.get("input_tokens") or 0),
        output_tokens=int(usage.get("output_tokens") or 0),
    )
    return str(body.get("text", "")).strip()


def _silence() -> bytes:
    """A short silent WAV, so the stand-in has real audio to play."""
    out = io.BytesIO()
    with wave.open(out, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(8000)
        w.writeframes(struct.pack("<h", 0) * 2400)
    return out.getvalue()


def speak(*, owner_id: UUID, text: str) -> Speech:
    """Spoken audio for ``text``, in Onyeka's voice. Raises like ``transcribe``."""
    runner.require_ai()
    words = text.strip()[:MAX_SPEECH_CHARS]
    if not words:
        raise JobFailed("nothing_to_say", "There is nothing to read out.")
    runner.check_ceiling(owner_id)
    model = settings.AI_TTS_MODEL
    started = time.monotonic()
    if _fake():
        _record(owner_id, "speak", model, started, "ok")
        return Speech(_silence(), "audio/wav")
    try:
        with _client() as client:
            response = client.post(
                "/audio/speech",
                json={
                    "model": model,
                    "voice": settings.AI_TTS_VOICE,
                    "input": words,
                    "instructions": settings.AI_TTS_INSTRUCTIONS,
                    "response_format": "mp3",
                },
            )
    except httpx.HTTPError as exc:
        _record(owner_id, "speak", model, started, "timeout")
        raise TransientError("voice network error") from exc
    try:
        _check(response)
    except (JobFailed, TransientError):
        _record(owner_id, "speak", model, started, "rejected")
        raise
    _record(owner_id, "speak", model, started, "ok")
    return Speech(response.content, "audio/mpeg")
