from uuid import UUID

from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.toolkit.ai import errors
from apps.toolkit.ai.agents import writer
from apps.toolkit.ai.runner import CeilingReached
from apps.toolkit.ai.serializers import (
    TkFillFromTextSerializer,
    TkProposedFieldsSerializer,
    TkSuggestionsSerializer,
    TkSuggestSerializer,
)
from apps.toolkit.jobs.services import JobFailed, TransientError
from apps.toolkit.ventures.permissions import member_policy, owned_venture, uid

ERRORS = {
    401: OpenApiResponse(description="Not authenticated"),
    403: OpenApiResponse(description="Not an approved member"),
    404: OpenApiResponse(description="Not found, or not yours"),
    429: OpenApiResponse(description="Daily limit of assistant requests reached"),
    502: OpenApiResponse(description="The assistant could not produce an answer"),
    503: OpenApiResponse(description="The assistant is busy; try again"),
}


class SuggestView(APIView):
    policy = member_policy()

    @extend_schema(
        summary="Suggest wording for a profile field",
        description="Up to three alternatives, grounded in what the profile already says. "
        "Nothing is saved. To use one, send it with `PATCH .../profile`. Requests for legal, tax "
        "or investment advice, or for made up results, are declined with 400.",
        request=TkSuggestSerializer,
        responses={200: TkSuggestionsSerializer, **ERRORS},
        tags=["toolkit"],
    )
    def post(self, request: Request, venture_id: UUID) -> Response:
        venture = owned_venture(request, venture_id)
        serializer = TkSuggestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        try:
            suggestions = writer.suggest_field(
                venture=venture, owner_id=uid(request), field=data["field"], intent=data["intent"]
            )
        except (JobFailed, TransientError, CeilingReached) as exc:
            raise errors.translate(exc) from exc
        return Response(
            TkSuggestionsSerializer({"field": data["field"], "suggestions": suggestions}).data
        )


class FillFromTextView(APIView):
    policy = member_policy()

    @extend_schema(
        summary="Propose profile fields from a paragraph",
        description="Reads free text and returns the fields it clearly supports, already "
        "validated. Nothing is saved; the member reviews the proposal and saves what they want.",
        request=TkFillFromTextSerializer,
        responses={200: TkProposedFieldsSerializer, **ERRORS},
        tags=["toolkit"],
    )
    def post(self, request: Request, venture_id: UUID) -> Response:
        venture = owned_venture(request, venture_id)
        serializer = TkFillFromTextSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            proposed, rejected = writer.fill_from_text(
                venture=venture, owner_id=uid(request), text=serializer.validated_data["text"]
            )
        except (JobFailed, TransientError, CeilingReached) as exc:
            raise errors.translate(exc) from exc
        return Response(
            TkProposedFieldsSerializer({"proposed": proposed, "rejected": rejected}).data
        )
