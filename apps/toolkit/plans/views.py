from uuid import UUID

from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, extend_schema
from rest_framework import exceptions
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.toolkit.jobs import services as jobs
from apps.toolkit.jobs.serializers import TkJobSerializer
from apps.toolkit.jobs.views import accepted, idempotency_key
from apps.toolkit.plans import selectors, service
from apps.toolkit.plans.models import PlanSection
from apps.toolkit.plans.serializers import (
    TkPlanAssistSerializer,
    TkPlanGenerateSerializer,
    TkPlanProposalSerializer,
    TkPlanReadinessSerializer,
    TkPlanSectionSaveSerializer,
    TkPlanSectionSerializer,
    TkPlanSerializer,
    TkPlanVersionSerializer,
)
from apps.toolkit.ventures import schema
from apps.toolkit.ventures.models import Venture
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


def _private(response: Response) -> Response:
    response["Cache-Control"] = "private, no-store"
    return response


def _section(venture: Venture, number: int) -> PlanSection:
    section = service.section_of(venture, number)
    if section is None:
        raise exceptions.NotFound()
    return section


class PlanStartView(APIView):
    policy = member_policy("plan")

    @extend_schema(
        summary="Write the business plan",
        description="Needs the six required profile fields (400 names what is missing). Starts a "
        "job and answers 202; poll it, then read `plan`. Sections you edited yourself are kept "
        "unless `overwrite_edited` is true. Pass `sections` to rewrite only some. A repeated "
        "`Idempotency-Key` returns the same job.",
        parameters=[KEY],
        request=TkPlanGenerateSerializer,
        responses={202: TkJobSerializer, 200: TkJobSerializer, **ERRORS},
        tags=["toolkit"],
    )
    def post(self, request: Request, venture_id: UUID) -> Response:
        venture = owned_venture(request, venture_id)
        body = TkPlanGenerateSerializer(data=request.data or {})
        body.is_valid(raise_exception=True)
        missing = schema.missing_required(profile_of(venture).fields)
        if missing:
            raise exceptions.ValidationError(
                {"profile": ["Complete these fields first: " + ", ".join(missing)]}
            )
        job, created = jobs.start(
            owner_id=uid(request),
            kind="plan.generate",
            venture=venture,
            payload={
                "sections": body.validated_data.get("sections", []),
                "overwrite_edited": body.validated_data.get("overwrite_edited", False),
            },
            idempotency_key=idempotency_key(request),
        )
        return accepted(request, job, created)


class PlanView(APIView):
    policy = member_policy("plan")

    @extend_schema(
        summary="The latest plan and where each section stands",
        responses={200: TkPlanSerializer, **ERRORS},
        tags=["toolkit"],
    )
    def get(self, request: Request, venture_id: UUID) -> Response:
        venture = readable_venture(request, venture_id)
        plan = service.latest(venture)
        if plan is None:
            raise exceptions.NotFound()
        return _private(Response(TkPlanSerializer(selectors.plan_view(venture, plan)).data))


class PlanSectionView(APIView):
    policy = member_policy("plan")

    @extend_schema(
        summary="One section with its text and citations",
        responses={200: TkPlanSectionSerializer, **ERRORS},
        tags=["toolkit"],
    )
    def get(self, request: Request, venture_id: UUID, number: int) -> Response:
        venture = readable_venture(request, venture_id)
        section = _section(venture, number)
        return _private(
            Response(TkPlanSectionSerializer(selectors.section_view(venture, section)).data)
        )

    @extend_schema(
        summary="Save your edit of a section",
        description="`base_version` must be the version you loaded; otherwise 409 so two tabs "
        "cannot overwrite each other. Text is plain: markup is stripped.",
        request=TkPlanSectionSaveSerializer,
        responses={
            200: TkPlanSectionSerializer,
            409: OpenApiResponse(description="The section changed elsewhere"),
            **ERRORS,
        },
        tags=["toolkit"],
    )
    def patch(self, request: Request, venture_id: UUID, number: int) -> Response:
        venture = owned_venture(request, venture_id)
        section = _section(venture, number)
        body = TkPlanSectionSaveSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        data = body.validated_data
        if data.get("citations"):
            saved = service.accept_proposal(
                section,
                proposal=data["content"],
                citations=data["citations"],
                base_version=data["base_version"],
            )
        else:
            saved = service.save_section(
                section, new_content=data["content"], base_version=data["base_version"]
            )
        saved.definition = section.definition
        return _private(
            Response(TkPlanSectionSerializer(selectors.section_view(venture, saved)).data)
        )


class PlanSectionAssistView(APIView):
    policy = member_policy("plan")

    @extend_schema(
        summary="Ask for a rewrite of a section",
        description="Answers with a proposal and saves nothing. Accept it by saving it with "
        "`PATCH` (send its `citations` too). A figure that is not in your data or the sources "
        "is removed and listed in `removed_figures`.",
        request=TkPlanAssistSerializer,
        responses={200: TkPlanProposalSerializer, **ERRORS},
        tags=["toolkit"],
    )
    def post(self, request: Request, venture_id: UUID, number: int) -> Response:
        venture = owned_venture(request, venture_id)
        section = _section(venture, number)
        body = TkPlanAssistSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        proposal = service.propose(
            venture=venture,
            owner_id=uid(request),
            section=section,
            action=body.validated_data["action"],
            country=body.validated_data.get("country", ""),
        )
        return _private(Response(TkPlanProposalSerializer(proposal).data))


class PlanReadinessView(APIView):
    policy = member_policy("plan")

    @extend_schema(
        summary="What is still missing before the plan can be shared",
        responses={200: TkPlanReadinessSerializer, **ERRORS},
        tags=["toolkit"],
    )
    def get(self, request: Request, venture_id: UUID) -> Response:
        venture = readable_venture(request, venture_id)
        return _private(Response(TkPlanReadinessSerializer(service.readiness(venture)).data))


class PlanVersionsView(APIView):
    policy = member_policy("plan")

    @extend_schema(
        summary="Saved versions of the plan",
        responses={200: TkPlanVersionSerializer(many=True), **ERRORS},
        tags=["toolkit"],
    )
    def get(self, request: Request, venture_id: UUID) -> Response:
        venture = readable_venture(request, venture_id)
        plan = service.latest(venture)
        if plan is None:
            raise exceptions.NotFound()
        return _private(Response(TkPlanVersionSerializer(selectors.versions(plan), many=True).data))


class PlanVersionRestoreView(APIView):
    policy = member_policy("plan")

    @extend_schema(
        summary="Go back to a saved version",
        description="The current text is saved as a version first, so this can be undone.",
        request=None,
        responses={200: TkPlanSerializer, **ERRORS},
        tags=["toolkit"],
    )
    def post(self, request: Request, venture_id: UUID, version: int) -> Response:
        venture = owned_venture(request, venture_id)
        plan = service.latest(venture)
        if plan is None:
            raise exceptions.NotFound()
        service.restore_version(plan, version)
        return _private(Response(TkPlanSerializer(selectors.plan_view(venture, plan)).data))
