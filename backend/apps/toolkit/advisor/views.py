from typing import Any
from uuid import UUID

from django.core.cache import cache
from django.http import HttpResponse
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, extend_schema
from rest_framework import exceptions
from rest_framework.parsers import MultiPartParser
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle, UserRateThrottle
from rest_framework.views import APIView

from apps.toolkit.advisor import service
from apps.toolkit.advisor.models import AdvisorMessage
from apps.toolkit.advisor.serializers import (
    TkAdvisorConversationSerializer,
    TkAdvisorReplySerializer,
    TkAdvisorSendSerializer,
    TkAdvisorTranscribeSerializer,
    TkAdvisorTranscriptSerializer,
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
        assistant = result["assistant_message"]
        job = result["job"]
        data = {
            "user_message": message_view(result["user_message"]),
            "assistant_message": message_view(assistant) if assistant else None,
            "job": jobs.view(job) if job else None,
        }
        response = Response(TkAdvisorReplySerializer(data).data, status=202 if job else 201)
        if job:
            response["Location"] = f"/api/v1/toolkit/jobs/{job.pk}"
        return _private(response)

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
# A recording that cannot be used is the member's to fix, so it is a 400, not a failure of ours.
RECORDING_PROBLEMS = ("unsupported_audio", "audio_too_long")


class TranscribeView(APIView):
    policy = member_policy("advisor")
    parser_classes = [MultiPartParser]
    throttle_classes = [UserRateThrottle, ScopedRateThrottle]
    throttle_scope = "toolkit_voice"

    @extend_schema(
        operation_id="tk_advisor_transcribe",
        summary="Turn a voice recording into text",
        description="Send the recording as `audio` (WebM, Ogg, MP4, M4A, MP3 or WAV, up to 4 MB). "
        "Answers with the words, which you then send to Onyeka as a message. Nothing is kept: "
        "neither the recording nor the words.",
        request={"multipart/form-data": TkAdvisorTranscribeSerializer},
        responses={200: TkAdvisorTranscriptSerializer, **ERRORS},
        tags=["toolkit"],
    )
    def post(self, request: Request) -> Response:
        body = TkAdvisorTranscribeSerializer(data=request.data)
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
        except JobFailed as exc:
            if exc.code in RECORDING_PROBLEMS:
                raise exceptions.ValidationError({"audio": [exc.detail]}) from exc
            raise ai_errors.translate(exc) from exc
        except TransientError as exc:
            raise ai_errors.translate(exc) from exc
        if not text:
            raise exceptions.ValidationError(
                {"audio": ["We could not hear any words. Try again a little closer to the mic."]}
            )
        return _private(Response(TkAdvisorTranscriptSerializer({"text": text}).data))


def spoken_text(m: AdvisorMessage) -> str:
    """What Onyeka reads out: the answer, then the next steps."""
    steps = m.meta.get("next_steps") or []
    if not steps:
        return m.text
    listed = " ".join(f"{n}. {step}" for n, step in enumerate(steps, start=1))
    return f"{m.text}\n\nNext steps. {listed}"


class SpeechView(APIView):
    policy = member_policy("advisor")
    throttle_classes = [UserRateThrottle, ScopedRateThrottle]
    throttle_scope = "toolkit_voice"

    @extend_schema(
        operation_id="tk_advisor_speech",
        summary="Hear one of Onyeka's answers",
        description="The answer read aloud in Onyeka's voice, as MP3 audio. Only Onyeka's own "
        "answers in your conversation can be heard. Kept for a day so listening again is quick.",
        responses={
            (200, "audio/mpeg"): OpenApiTypes.BINARY,
            **ERRORS,
        },
        tags=["toolkit"],
    )
    def get(self, request: Request, message_id: UUID) -> HttpResponse:
        message = AdvisorMessage.objects.filter(
            pk=message_id, owner_id=uid(request), role="assistant"
        ).first()
        if message is None:
            raise exceptions.NotFound()
        key = f"toolkit:advisor:speech:{message.pk}"
        cached = cache.get(key)
        if cached is None:
            try:
                speech = voice.speak(owner_id=uid(request), text=spoken_text(message))
            except (JobFailed, TransientError) as exc:
                raise ai_errors.translate(exc) from exc
            cached = (speech.content_type, speech.audio)
            cache.set(key, cached, SPEECH_CACHE_SECONDS)
        content_type, audio = cached
        response = HttpResponse(audio, content_type=content_type)
        response["Cache-Control"] = "private, max-age=86400"
        return response
