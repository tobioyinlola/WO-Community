from typing import Any

from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, extend_schema
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
)
from apps.toolkit.ai import errors as ai_errors
from apps.toolkit.ai import providers
from apps.toolkit.jobs import services as jobs
from apps.toolkit.jobs.services import JobFailed
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
