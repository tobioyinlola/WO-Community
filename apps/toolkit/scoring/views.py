from uuid import UUID

from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, extend_schema
from rest_framework import exceptions
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.toolkit.jobs import services as jobs
from apps.toolkit.jobs.serializers import TkJobSerializer
from apps.toolkit.jobs.views import accepted, idempotency_key
from apps.toolkit.scoring import selectors
from apps.toolkit.scoring.serializers import (
    TkAssessmentSerializer,
    TkScoreHistoryItemSerializer,
    TkScoreSummarySerializer,
)
from apps.toolkit.ventures import schema
from apps.toolkit.ventures.permissions import (
    member_policy,
    owned_venture,
    readable_venture,
    uid,
)
from apps.toolkit.ventures.selectors import profile_of

ERRORS = {
    401: OpenApiResponse(description="Not authenticated"),
    403: OpenApiResponse(description="Not an approved member"),
    404: OpenApiResponse(description="Not found, or not yours, or the tool is off"),
}
KEY = OpenApiParameter("Idempotency-Key", str, OpenApiParameter.HEADER, required=False)


class ScoreStartView(APIView):
    policy = member_policy("score")

    @extend_schema(
        summary="Run the validation score",
        description="Needs the six required profile fields (400 names what is missing). Starts "
        "a job and answers 202; poll the job, then read `score/latest`. A repeated "
        "`Idempotency-Key` returns the same job. The score is calculated from a rubric in code "
        "and sourced facts; a model only writes the explanations.",
        parameters=[KEY],
        request=None,
        responses={202: TkJobSerializer, 200: TkJobSerializer, **ERRORS},
        tags=["toolkit"],
    )
    def post(self, request: Request, venture_id: UUID) -> Response:
        venture = owned_venture(request, venture_id)
        missing = schema.missing_required(profile_of(venture).fields)
        if missing:
            raise exceptions.ValidationError(
                {"profile": ["Complete these fields first: " + ", ".join(missing)]}
            )
        job, created = jobs.start(
            owner_id=uid(request),
            kind="score.generate",
            venture=venture,
            idempotency_key=idempotency_key(request),
        )
        return accepted(request, job, created)


class ScoreLatestView(APIView):
    policy = member_policy("score")

    @extend_schema(
        summary="The latest score report",
        responses={200: TkAssessmentSerializer, **ERRORS},
        tags=["toolkit"],
    )
    def get(self, request: Request, venture_id: UUID) -> Response:
        venture = readable_venture(request, venture_id)
        assessment = selectors.latest(venture)
        if assessment is None:
            raise exceptions.NotFound()
        response = Response(TkAssessmentSerializer(selectors.view(assessment)).data)
        response["Cache-Control"] = "private, no-store"
        return response


class ScoreHistoryView(APIView):
    policy = member_policy("score")

    @extend_schema(
        summary="Score history, oldest first, for a chart",
        responses={200: TkScoreHistoryItemSerializer(many=True), **ERRORS},
        tags=["toolkit"],
    )
    def get(self, request: Request, venture_id: UUID) -> Response:
        venture = readable_venture(request, venture_id)
        response = Response(
            TkScoreHistoryItemSerializer(selectors.history(venture), many=True).data
        )
        response["Cache-Control"] = "private, no-store"
        return response


class ScoreSummaryView(APIView):
    policy = member_policy("score")

    @extend_schema(
        summary="A one page summary of the latest score",
        description="The scores and the top strengths and gaps, without evidence detail, in a "
        "form that is safe to share.",
        responses={200: TkScoreSummarySerializer, **ERRORS},
        tags=["toolkit"],
    )
    def get(self, request: Request, venture_id: UUID) -> Response:
        venture = readable_venture(request, venture_id)
        assessment = selectors.latest(venture)
        if assessment is None:
            raise exceptions.NotFound()
        response = Response(TkScoreSummarySerializer(selectors.summary(venture, assessment)).data)
        response["Cache-Control"] = "private, no-store"
        return response
