from typing import Any
from uuid import UUID

from django.utils import timezone
from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, extend_schema
from rest_framework import exceptions
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.toolkit.ai import errors as ai_errors
from apps.toolkit.jobs import services as jobs
from apps.toolkit.jobs.services import JobFailed
from apps.toolkit.jobs.views import idempotency_key
from apps.toolkit.partner import service
from apps.toolkit.partner.models import ChangeSet, Conversation, Decision, Message, Nudge
from apps.toolkit.partner.serializers import (
    TkChangeApplySerializer,
    TkChangeSetSerializer,
    TkChangeUndoSerializer,
    TkConversationCreateSerializer,
    TkConversationDetailSerializer,
    TkConversationSerializer,
    TkDecisionCreateSerializer,
    TkDecisionSerializer,
    TkMentorSuggestionSerializer,
    TkNudgeSerializer,
    TkPartnerReplySerializer,
    TkSendMessageSerializer,
)
from apps.toolkit.ventures.models import Venture
from apps.toolkit.ventures.permissions import member_policy, owned_venture, uid

ERRORS = {
    401: OpenApiResponse(description="Not authenticated"),
    403: OpenApiResponse(description="Not an approved member"),
    404: OpenApiResponse(description="Not found, or not yours, or the tool is off"),
}
KEY = OpenApiParameter("Idempotency-Key", str, OpenApiParameter.HEADER, required=False)
policy = member_policy("partner")


def _private(response: Response) -> Response:
    response["Cache-Control"] = "private, no-store"
    return response


def _conversation(request: Request, venture: Venture, conversation_id: UUID) -> Conversation:
    row = service.get(venture, uid(request), conversation_id)
    if row is None:
        raise exceptions.NotFound()
    return row


def _change_set_view(row: ChangeSet | None) -> dict[str, Any] | None:
    if row is None:
        return None
    return {
        "id": row.pk,
        "status": row.status,
        "changes": row.changes,
        "applied_at": row.applied_at,
        "undone_at": row.undone_at,
    }


def _message_view(message: Message) -> dict[str, Any]:
    change = ChangeSet.objects.filter(message=message).first()
    return {
        "id": message.pk,
        "author": message.role,
        "text": message.text,
        "next_steps": message.meta.get("next_steps", []),
        "mentor_topics": message.meta.get("mentor_topics", []),
        "declined": message.meta.get("declined"),
        "change_set": _change_set_view(change),
        "created_at": message.created_at,
    }


def _conversation_view(row: Conversation, *, messages: bool = False) -> dict[str, Any]:
    data: dict[str, Any] = {
        "id": row.pk,
        "title": row.title,
        "message_count": row.messages.count(),
        "updated_at": row.updated_at,
    }
    if messages:
        data["messages"] = [_message_view(m) for m in row.messages.all()]
    return data


class ConversationsView(APIView):
    policy = policy

    @extend_schema(
        summary="Conversations with the venture partner",
        responses={200: TkConversationSerializer(many=True), **ERRORS},
        tags=["toolkit"],
    )
    def get(self, request: Request, venture_id: UUID) -> Response:
        venture = owned_venture(request, venture_id)
        rows = Conversation.objects.filter(venture=venture, owner_id=uid(request)).order_by(
            "-updated_at"
        )
        return _private(
            Response(
                TkConversationSerializer([_conversation_view(r) for r in rows], many=True).data
            )
        )

    @extend_schema(
        summary="Start a conversation",
        request=TkConversationCreateSerializer,
        responses={201: TkConversationSerializer, **ERRORS},
        tags=["toolkit"],
    )
    def post(self, request: Request, venture_id: UUID) -> Response:
        venture = owned_venture(request, venture_id)
        body = TkConversationCreateSerializer(data=request.data or {})
        body.is_valid(raise_exception=True)
        row = service.start(venture, uid(request), body.validated_data.get("title", ""))
        return _private(
            Response(TkConversationSerializer(_conversation_view(row)).data, status=201)
        )


class ConversationView(APIView):
    policy = policy

    @extend_schema(
        summary="A conversation with its messages",
        responses={200: TkConversationDetailSerializer, **ERRORS},
        tags=["toolkit"],
    )
    def get(self, request: Request, venture_id: UUID, conversation_id: UUID) -> Response:
        venture = owned_venture(request, venture_id)
        row = _conversation(request, venture, conversation_id)
        return _private(
            Response(TkConversationDetailSerializer(_conversation_view(row, messages=True)).data)
        )

    @extend_schema(
        summary="Delete a conversation",
        request=None,
        responses={204: OpenApiResponse(description="Deleted"), **ERRORS},
        tags=["toolkit"],
    )
    def delete(self, request: Request, venture_id: UUID, conversation_id: UUID) -> Response:
        venture = owned_venture(request, venture_id)
        _conversation(request, venture, conversation_id).delete()
        return Response(status=204)


class MessagesView(APIView):
    policy = policy

    @extend_schema(
        summary="Say something to the partner",
        description="Answers 201 with the reply when it is ready within a few seconds, "
        "otherwise 202 with a `job` to poll; the reply then appears in the conversation. "
        "Requests for legal, tax or investment advice, or for made up proof, are declined "
        "without calling a model. Anything the partner proposes to change in your profile comes "
        "back as a change set that you apply or dismiss.",
        parameters=[KEY],
        request=TkSendMessageSerializer,
        responses={201: TkPartnerReplySerializer, 202: TkPartnerReplySerializer, **ERRORS},
        tags=["toolkit"],
    )
    def post(self, request: Request, venture_id: UUID, conversation_id: UUID) -> Response:
        venture = owned_venture(request, venture_id)
        conversation = _conversation(request, venture, conversation_id)
        body = TkSendMessageSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        try:
            result = service.post_message(
                venture=venture,
                owner_id=uid(request),
                conversation=conversation,
                text=body.validated_data["text"],
                key=idempotency_key(request),
            )
        except JobFailed as exc:
            raise ai_errors.translate(exc) from exc
        assistant = result["assistant_message"]
        job = result["job"]
        data = {
            "user_message": _message_view(result["user_message"]),
            "assistant_message": _message_view(assistant) if assistant else None,
            "job": jobs.view(job) if job else None,
        }
        response = Response(TkPartnerReplySerializer(data).data, status=202 if job else 201)
        if job:
            response["Location"] = f"/api/v1/toolkit/jobs/{job.pk}"
        return _private(response)


class ChangeApplyView(APIView):
    policy = policy

    @extend_schema(
        summary="Apply proposed changes to the profile",
        description="Writes the chosen changes (or all of them). Each field is recorded as an "
        "accepted suggestion. Outputs made from those fields are marked out of date.",
        request=TkChangeApplySerializer,
        responses={200: TkChangeSetSerializer, **ERRORS},
        tags=["toolkit"],
    )
    def post(self, request: Request, venture_id: UUID, change_set_id: UUID) -> Response:
        venture = owned_venture(request, venture_id)
        body = TkChangeApplySerializer(data=request.data or {})
        body.is_valid(raise_exception=True)
        row = service.apply_changes(
            venture, change_set_id, fields=body.validated_data.get("accept")
        )
        return _private(Response(TkChangeSetSerializer(_change_set_view(row)).data))


class ChangeUndoView(APIView):
    policy = policy

    @extend_schema(
        summary="Undo applied changes",
        description="Puts the previous values back, except any field you have edited since.",
        request=None,
        responses={200: TkChangeUndoSerializer, **ERRORS},
        tags=["toolkit"],
    )
    def post(self, request: Request, venture_id: UUID, change_set_id: UUID) -> Response:
        venture = owned_venture(request, venture_id)
        row, skipped = service.undo_changes(venture, change_set_id)
        return _private(
            Response(
                TkChangeUndoSerializer(
                    {"change_set": _change_set_view(row), "skipped": skipped}
                ).data
            )
        )


class ChangeDismissView(APIView):
    policy = policy

    @extend_schema(
        summary="Dismiss proposed changes",
        request=None,
        responses={200: TkChangeSetSerializer, **ERRORS},
        tags=["toolkit"],
    )
    def post(self, request: Request, venture_id: UUID, change_set_id: UUID) -> Response:
        venture = owned_venture(request, venture_id)
        row = service.dismiss_changes(venture, change_set_id)
        return _private(Response(TkChangeSetSerializer(_change_set_view(row)).data))


class DecisionsView(APIView):
    policy = policy

    @extend_schema(
        summary="The decision log",
        responses={200: TkDecisionSerializer(many=True), **ERRORS},
        tags=["toolkit"],
    )
    def get(self, request: Request, venture_id: UUID) -> Response:
        venture = owned_venture(request, venture_id)
        rows = [
            {
                "id": d.pk,
                "text": d.text,
                "rationale": d.rationale,
                "decided_on": d.decided_on,
                "created_at": d.created_at,
            }
            for d in Decision.objects.filter(venture=venture)
        ]
        return _private(Response(TkDecisionSerializer(rows, many=True).data))

    @extend_schema(
        summary="Record a decision",
        description="The partner reads the latest decisions, so it stops suggesting what you "
        "already ruled out.",
        request=TkDecisionCreateSerializer,
        responses={201: TkDecisionSerializer, **ERRORS},
        tags=["toolkit"],
    )
    def post(self, request: Request, venture_id: UUID) -> Response:
        venture = owned_venture(request, venture_id)
        body = TkDecisionCreateSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        d = service.record_decision(venture, **body.validated_data)
        out = {
            "id": d.pk,
            "text": d.text,
            "rationale": d.rationale,
            "decided_on": d.decided_on,
            "created_at": d.created_at,
        }
        return _private(Response(TkDecisionSerializer(out).data, status=201))


class DecisionView(APIView):
    policy = policy

    @extend_schema(
        summary="Remove a decision",
        request=None,
        responses={204: OpenApiResponse(description="Removed"), **ERRORS},
        tags=["toolkit"],
    )
    def delete(self, request: Request, venture_id: UUID, decision_id: UUID) -> Response:
        venture = owned_venture(request, venture_id)
        deleted, _ = Decision.objects.filter(pk=decision_id, venture=venture).delete()
        if not deleted:
            raise exceptions.NotFound()
        return Response(status=204)


class NudgesView(APIView):
    policy = policy

    @extend_schema(
        summary="Weekly next steps",
        responses={200: TkNudgeSerializer(many=True), **ERRORS},
        tags=["toolkit"],
    )
    def get(self, request: Request, venture_id: UUID) -> Response:
        venture = owned_venture(request, venture_id)
        rows = [
            {
                "id": n.pk,
                "week_key": n.week_key,
                "code": n.code,
                "text": n.text,
                "action": n.action,
                "read_at": n.read_at,
                "created_at": n.created_at,
            }
            for n in Nudge.objects.filter(venture=venture)[:12]
        ]
        return _private(Response(TkNudgeSerializer(rows, many=True).data))


class NudgeReadView(APIView):
    policy = policy

    @extend_schema(
        summary="Mark a next step as seen",
        request=None,
        responses={204: OpenApiResponse(description="Marked"), **ERRORS},
        tags=["toolkit"],
    )
    def post(self, request: Request, venture_id: UUID, nudge_id: UUID) -> Response:
        venture = owned_venture(request, venture_id)
        updated = Nudge.objects.filter(pk=nudge_id, venture=venture, read_at__isnull=True).update(
            read_at=timezone.now()
        )
        if not updated and not Nudge.objects.filter(pk=nudge_id, venture=venture).exists():
            raise exceptions.NotFound()
        return Response(status=204)


class MentorSuggestionsView(APIView):
    policy = policy

    @extend_schema(
        summary="Mentors who could help with what this venture needs",
        description="Ranked from the weakest areas of the latest score and the topics the "
        "partner has raised. Nobody is contacted; book from the mentor's page.",
        responses={200: TkMentorSuggestionSerializer, **ERRORS},
        tags=["toolkit"],
    )
    def get(self, request: Request, venture_id: UUID) -> Response:
        venture = owned_venture(request, venture_id)
        data = service.suggest_mentors(request.user, venture)
        return _private(Response(TkMentorSuggestionSerializer(data).data))
