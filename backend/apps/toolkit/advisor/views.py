from collections.abc import Iterator
from typing import Any
from uuid import UUID

from django.core import signing
from django.core.cache import cache
from django.http import HttpResponse, StreamingHttpResponse
from django.http.response import HttpResponseBase
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, extend_schema
from rest_framework import exceptions
from rest_framework.parsers import MultiPartParser
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle, ScopedRateThrottle, UserRateThrottle
from rest_framework.views import APIView

from apps.core import policies
from apps.toolkit.advisor import service
from apps.toolkit.advisor.models import AdvisorMessage
from apps.toolkit.advisor.serializers import (
    TkAdvisorConversationSerializer,
    TkAdvisorReplySerializer,
    TkAdvisorSendSerializer,
    TkAdvisorSpeechLinkSerializer,
    TkAdvisorVoiceTurnSerializer,
)
from apps.toolkit.ai import errors as ai_errors
from apps.toolkit.ai import providers, voice
from apps.toolkit.jobs import services as jobs
from apps.toolkit.jobs.services import JobFailed, TransientError
from apps.toolkit.jobs.views import idempotency_key
from apps.toolkit.ventures.permissions import member_policy, uid

ERRORS = {
    401: OpenApiResponse(description="Not authenticated"),
    403: OpenApiResponse(description="Not an approved member"),
    404: OpenApiResponse(description="The advisor is switched off"),
}
KEY = OpenApiParameter("Idempotency-Key", str, OpenApiParameter.HEADER, required=False)


def _private(response: Response) -> Response:
    response["Cache-Control"] = "private, no-store"
    return response


def message_view(m: AdvisorMessage) -> dict[str, Any]:
    return {
        "id": m.pk,
        "author": m.role,
        "text": m.text,
        "next_steps": m.meta.get("next_steps", []),
        "frameworks": m.meta.get("frameworks", []),
        "declined": m.meta.get("declined"),
        "created_at": m.created_at,
    }


class MessagesView(APIView):
    policy = member_policy("advisor")
    throttle_classes = [UserRateThrottle, ScopedRateThrottle]
    throttle_scope = "toolkit_advisor"

    def get_throttles(self) -> list[Any]:
        # Reading the conversation is cheap; only sending is held to the tighter rate.
        throttles = super().get_throttles()
        if self.request.method != "POST":
            return [t for t in throttles if not isinstance(t, ScopedRateThrottle)]
        return throttles

    @extend_schema(
        operation_id="tk_advisor_conversation",
        summary="Your conversation with Onyeka",
        description="The latest messages with Onyeka, the community's AI founder advisor, oldest "
        "first, and whether Onyeka can answer right now.",
        responses={200: TkAdvisorConversationSerializer, **ERRORS},
        tags=["toolkit"],
    )
    def get(self, request: Request) -> Response:
        data = {
            "greeting": service.GREETING,
            "ai_enabled": providers.ai_enabled(),
            "messages": [message_view(m) for m in service.history(uid(request))],
        }
        return _private(Response(TkAdvisorConversationSerializer(data).data))

    @extend_schema(
        operation_id="tk_advisor_send",
        summary="Ask Onyeka something",
        description="Answers 201 with the reply when it is ready within a few seconds, otherwise "
        "202 with a `job` to poll; the reply then appears in the conversation. Requests for "
        "legal, tax or investment advice, or for made up proof, are declined without calling a "
        "model. Answers 503 `ai_off` when AI is not switched on.",
        parameters=[KEY],
        request=TkAdvisorSendSerializer,
        responses={201: TkAdvisorReplySerializer, 202: TkAdvisorReplySerializer, **ERRORS},
        tags=["toolkit"],
    )
    def post(self, request: Request) -> Response:
        body = TkAdvisorSendSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        try:
            result = service.post_message(
                owner_id=uid(request),
                text=body.validated_data["text"],
                key=idempotency_key(request),
            )
        except JobFailed as exc:
            raise ai_errors.translate(exc) from exc
        return reply_response(request, result)

    @extend_schema(
        operation_id="tk_advisor_clear",
        summary="Start over with Onyeka",
        description="Deletes every message in your conversation with Onyeka.",
        request=None,
        responses={204: None, **ERRORS},
        tags=["toolkit"],
    )
    def delete(self, request: Request) -> Response:
        service.clear(uid(request))
        return Response(status=204)


SPEECH_CACHE_SECONDS = 86400
SPEECH_LINK_SECONDS = 300
SPEECH_SALT = "toolkit.advisor.speech"
MAX_CACHED_SPEECH = 3 * 1024 * 1024
# A recording that cannot be used is the member's to fix, so it is a 400, not a failure of ours.
RECORDING_PROBLEMS = ("unsupported_audio", "audio_too_long")


def speech_url(owner_id: UUID, message_id: UUID) -> str:
    """A short lived address an audio player can stream an answer from without a sign in header.

    It names one answer of one member and stops working after a few minutes."""
    token = signing.dumps({"u": str(owner_id), "m": str(message_id)}, salt=SPEECH_SALT)
    return f"/api/v1/toolkit/advisor/speech/{token}"


def reply_response(request: Request, result: dict[str, Any], *, spoken: bool = False) -> Response:
    """The answer to a turn: the reply now (201), or a job to follow (202). A spoken turn also
    carries where to stream the reply from, so playback can start without another request."""
    assistant = result["assistant_message"]
    job = result["job"]
    data = {
        "user_message": message_view(result["user_message"]),
        "assistant_message": message_view(assistant) if assistant else None,
        "job": jobs.view(job) if job else None,
        "speech_url": speech_url(uid(request), assistant.pk) if spoken and assistant else None,
    }
    response = Response(TkAdvisorReplySerializer(data).data, status=202 if job else 201)
    if job:
        response["Location"] = f"/api/v1/toolkit/jobs/{job.pk}"
    return _private(response)


class VoiceTurnView(APIView):
    policy = member_policy("advisor")
    parser_classes = [MultiPartParser]
    throttle_classes = [UserRateThrottle, ScopedRateThrottle]
    throttle_scope = "toolkit_voice"

    @extend_schema(
        operation_id="tk_advisor_voice_turn",
        summary="Say something to Onyeka",
        description="Send a recording as `audio` (WebM, Ogg, MP4, M4A, MP3 or WAV, up to 4 MB). It "
        "is turned into words, sent to Onyeka as your message, and answered like a typed message "
        "(201 with the reply, or 202 with a job), with a short spoken answer and `speech_url` to "
        "stream it from. The recording itself is not kept.",
        request={"multipart/form-data": TkAdvisorVoiceTurnSerializer},
        responses={201: TkAdvisorReplySerializer, 202: TkAdvisorReplySerializer, **ERRORS},
        tags=["toolkit"],
    )
    def post(self, request: Request) -> Response:
        body = TkAdvisorVoiceTurnSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        upload = body.validated_data["audio"]
        if upload.size > voice.MAX_AUDIO_BYTES:
            raise exceptions.ValidationError(
                {"audio": ["That recording is too long. Keep it under two minutes."]}
            )
        try:
            text = voice.transcribe(
                owner_id=uid(request),
                audio=upload.read(),
                content_type=upload.content_type or "",
            )
            if not text:
                raise exceptions.ValidationError(
                    {
                        "audio": [
                            "We could not hear any words. Try again a little closer to the mic."
                        ]
                    }
                )
            result = service.post_message(owner_id=uid(request), text=text, voice=True)
        except JobFailed as exc:
            if exc.code in RECORDING_PROBLEMS:
                raise exceptions.ValidationError({"audio": [exc.detail]}) from exc
            raise ai_errors.translate(exc) from exc
        except TransientError as exc:
            raise ai_errors.translate(exc) from exc
        return reply_response(request, result, spoken=True)


def spoken_text(m: AdvisorMessage) -> str:
    """What Onyeka reads out: the answer, then any next steps. A spoken answer already carries its
    one next step in its words, so only written answers have them read after."""
    steps = [] if m.meta.get("voice") else (m.meta.get("next_steps") or [])
    if not steps:
        return m.text
    listed = " ".join(f"{n}. {step}" for n, step in enumerate(steps, start=1))
    return f"{m.text}\n\nNext steps. {listed}"


class SpeechLinkView(APIView):
    policy = member_policy("advisor")

    @extend_schema(
        operation_id="tk_advisor_speech_link",
        summary="Where to hear one of Onyeka's answers",
        description="A short lived address (a few minutes) that streams the answer read aloud in "
        "Onyeka's voice, for an audio player to start playing at once. Only Onyeka's own answers "
        "in your conversation.",
        request=None,
        responses={200: TkAdvisorSpeechLinkSerializer, **ERRORS},
        tags=["toolkit"],
    )
    def post(self, request: Request, message_id: UUID) -> Response:
        exists = AdvisorMessage.objects.filter(
            pk=message_id, owner_id=uid(request), role="assistant"
        ).exists()
        if not exists:
            raise exceptions.NotFound()
        data = {"url": speech_url(uid(request), message_id), "expires_in": SPEECH_LINK_SECONDS}
        return _private(Response(TkAdvisorSpeechLinkSerializer(data).data))


class SpeechStreamView(APIView):
    # The signed address is the permission: it names one answer of one member and expires soon.
    policy = policies.public
    throttle_classes = [AnonRateThrottle, UserRateThrottle, ScopedRateThrottle]
    throttle_scope = "toolkit_voice"

    @extend_schema(
        operation_id="tk_advisor_speech",
        summary="Stream one of Onyeka's answers",
        description="MP3 audio, sent as it is made so playback can start at once. The address "
        "comes from a voice turn or from asking for a speech link. Kept for a day so listening "
        "again is instant.",
        responses={(200, "audio/mpeg"): OpenApiTypes.BINARY, 404: ERRORS[404]},
        tags=["toolkit"],
    )
    def get(self, request: Request, token: str) -> HttpResponseBase:
        try:
            claims = signing.loads(token, salt=SPEECH_SALT, max_age=SPEECH_LINK_SECONDS)
        except signing.BadSignature as exc:
            raise exceptions.NotFound() from exc
        message = AdvisorMessage.objects.filter(
            pk=claims.get("m"), owner_id=claims.get("u"), role="assistant"
        ).first()
        if message is None:
            raise exceptions.NotFound()
        key = f"toolkit:advisor:speech:{message.pk}:{voice.speech_voice()}"
        cached = cache.get(key)
        if cached is not None:
            content_type, audio = cached
            response: HttpResponseBase = HttpResponse(audio, content_type=content_type)
        else:
            try:
                stream = voice.open_speech(owner_id=message.owner_id, text=spoken_text(message))
            except (JobFailed, TransientError) as exc:
                raise ai_errors.translate(exc) from exc
            response = StreamingHttpResponse(
                _keep(stream.chunks, key, stream.content_type), content_type=stream.content_type
            )
        response["Cache-Control"] = "private, max-age=300"
        response["X-Accel-Buffering"] = "no"  # pass each piece on at once
        return response


def _keep(chunks: Iterator[bytes], key: str, content_type: str) -> Iterator[bytes]:
    """Passes the audio through as it arrives, and keeps the whole of it for the next listen."""
    parts: list[bytes] = []
    size = 0
    complete = False
    try:
        for chunk in chunks:
            size += len(chunk)
            if size <= MAX_CACHED_SPEECH:
                parts.append(chunk)
            yield chunk
        complete = True
    finally:
        close = getattr(chunks, "close", None)
        if close is not None:
            close()
        if complete and size <= MAX_CACHED_SPEECH:
            cache.set(key, (content_type, b"".join(parts)), SPEECH_CACHE_SECONDS)
