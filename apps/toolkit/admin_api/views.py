from datetime import date
from typing import Any

from django.http import HttpResponse
from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core import policies
from apps.toolkit.admin_api import service
from apps.toolkit.admin_api.serializers import (
    TkAdminDeckTemplateSerializer,
    TkAdminDeckTemplateWriteSerializer,
    TkAdminPlanSectionSerializer,
    TkAdminPlanSectionWriteSerializer,
    TkAdminPrototypeTemplateSerializer,
    TkAdminPrototypeTemplateWriteSerializer,
    TkAdminQualitySerializer,
    TkAdminRubricSerializer,
    TkAdminRubricWriteSerializer,
    TkAdminSettingsSerializer,
    TkAdminUsageQuerySerializer,
    TkAdminUsageRowSerializer,
)
from apps.toolkit.decks import service as decks
from apps.toolkit.decks.models import DeckTemplate
from apps.toolkit.plans import service as plans
from apps.toolkit.plans.models import PlanSectionDef
from apps.toolkit.prototypes import service as prototypes
from apps.toolkit.prototypes.models import PrototypeTemplate
from apps.toolkit.scoring import service as scoring
from apps.toolkit.scoring.models import ScoreRubric

MANAGE = policies.admin_permission("toolkit.manage")
SETTINGS = policies.admin_permission("toolkit.settings")
SETTINGS_STEP_UP = policies.admin_permission("toolkit.settings", step_up=True)
ERRORS = {
    401: OpenApiResponse(description="Not authenticated"),
    403: OpenApiResponse(description="Not allowed, or MFA missing"),
    404: OpenApiResponse(description="Not found"),
}


def _private(response: Response) -> Response:
    response["Cache-Control"] = "private, no-store"
    return response


def _deck_template(row: DeckTemplate) -> dict[str, Any]:
    return {
        "slug": row.slug,
        "name": row.name,
        "description": row.description,
        "slides": row.slides,
        "position": row.position,
        "active": row.active,
    }


class DeckTemplatesView(APIView):
    policy = MANAGE

    @extend_schema(
        summary="Deck templates, including switched off ones",
        responses={200: TkAdminDeckTemplateSerializer(many=True), **ERRORS},
        tags=["toolkit-admin"],
    )
    def get(self, request: Request) -> Response:
        decks.ensure_templates()
        rows = [_deck_template(r) for r in DeckTemplate.objects.all()]
        return _private(Response(TkAdminDeckTemplateSerializer(rows, many=True).data))

    @extend_schema(
        summary="Create or replace a deck template",
        description="The template must build into a valid deck from an empty profile; the "
        "400 says why when it does not. Changes apply to decks made from now on.",
        request=TkAdminDeckTemplateWriteSerializer,
        responses={200: TkAdminDeckTemplateSerializer, **ERRORS},
        tags=["toolkit-admin"],
    )
    def put(self, request: Request) -> Response:
        body = TkAdminDeckTemplateWriteSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        data = body.validated_data
        row = service.save_deck_template(
            actor=request.user,
            slug=data["slug"],
            name=data["name"],
            description=data.get("description", ""),
            slides=data["slides"],
            active=data["active"],
            position=data.get("position"),
        )
        return _private(Response(TkAdminDeckTemplateSerializer(_deck_template(row)).data))


class PrototypeTemplatesView(APIView):
    policy = MANAGE

    @extend_schema(
        summary="Prototype templates, including switched off ones",
        responses={200: TkAdminPrototypeTemplateSerializer(many=True), **ERRORS},
        tags=["toolkit-admin"],
    )
    def get(self, request: Request) -> Response:
        prototypes.ensure_templates()
        rows = [
            {
                "slug": r.slug,
                "name": r.name,
                "description": r.description,
                "spec": r.spec,
                "active": r.active,
            }
            for r in PrototypeTemplate.objects.all()
        ]
        return _private(Response(TkAdminPrototypeTemplateSerializer(rows, many=True).data))

    @extend_schema(
        summary="Create or replace a prototype template",
        description="The specification is checked against the component registry and limits. "
        "`{name}` in text is replaced with the venture's name.",
        request=TkAdminPrototypeTemplateWriteSerializer,
        responses={200: TkAdminPrototypeTemplateSerializer, **ERRORS},
        tags=["toolkit-admin"],
    )
    def put(self, request: Request) -> Response:
        body = TkAdminPrototypeTemplateWriteSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        data = body.validated_data
        row = service.save_prototype_template(
            actor=request.user,
            slug=data["slug"],
            name=data["name"],
            description=data.get("description", ""),
            spec=data["spec"],
            active=data["active"],
        )
        out = {
            "slug": row.slug,
            "name": row.name,
            "description": row.description,
            "spec": row.spec,
            "active": row.active,
        }
        return _private(Response(TkAdminPrototypeTemplateSerializer(out).data))


def _section(row: PlanSectionDef) -> dict[str, Any]:
    return {
        "number": row.number,
        "chapter": row.chapter,
        "title": row.title,
        "guidance": row.guidance,
        "depends_on": row.depends_on,
        "required_inputs": row.required_inputs,
        "active": row.active,
    }


class PlanSectionsView(APIView):
    policy = MANAGE

    @extend_schema(
        summary="The business plan's sections",
        responses={200: TkAdminPlanSectionSerializer(many=True), **ERRORS},
        tags=["toolkit-admin"],
    )
    def get(self, request: Request) -> Response:
        plans.ensure_catalog()
        rows = [_section(r) for r in PlanSectionDef.objects.order_by("number")]
        return _private(Response(TkAdminPlanSectionSerializer(rows, many=True).data))


class PlanSectionView(APIView):
    policy = MANAGE

    @extend_schema(
        summary="Change a plan section's wording, inputs or whether it is used",
        description="Applies to plans generated from now on. The executive summary cannot be "
        "switched off. Fields and topics must exist.",
        request=TkAdminPlanSectionWriteSerializer,
        responses={200: TkAdminPlanSectionSerializer, **ERRORS},
        tags=["toolkit-admin"],
    )
    def patch(self, request: Request, number: int) -> Response:
        body = TkAdminPlanSectionWriteSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        row = service.save_plan_section(
            actor=request.user, number=number, changes=dict(body.validated_data)
        )
        return _private(Response(TkAdminPlanSectionSerializer(_section(row)).data))


def _rubric(row: ScoreRubric) -> dict[str, Any]:
    return {
        "version": row.version,
        "active": row.active,
        "notes": row.notes,
        "config": row.config,
        "created_at": row.created_at,
    }


class RubricsView(APIView):
    policy = SETTINGS

    @extend_schema(
        summary="Score rubric versions",
        responses={200: TkAdminRubricSerializer(many=True), **ERRORS},
        tags=["toolkit-admin"],
    )
    def get(self, request: Request) -> Response:
        scoring.ensure_default_rubric()
        rows = [_rubric(r) for r in ScoreRubric.objects.order_by("-version")]
        return _private(Response(TkAdminRubricSerializer(rows, many=True).data))

    @extend_schema(
        summary="Add a rubric version",
        description="Checked before it is stored: weights must add up to 100 and verdicts must "
        "cover every score. It is not used until it is activated.",
        request=TkAdminRubricWriteSerializer,
        responses={201: TkAdminRubricSerializer, **ERRORS},
        tags=["toolkit-admin"],
    )
    def post(self, request: Request) -> Response:
        body = TkAdminRubricWriteSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        row = service.create_rubric(
            actor=request.user,
            config=body.validated_data["config"],
            notes=body.validated_data.get("notes", ""),
        )
        return _private(Response(TkAdminRubricSerializer(_rubric(row)).data, status=201))


class RubricActivateView(APIView):
    policy = SETTINGS_STEP_UP

    @extend_schema(
        summary="Make a rubric version the one in use",
        description="Needs a recent multi-factor check. New scores use it at once; earlier "
        "scores keep the version they were made with.",
        request=None,
        responses={200: TkAdminRubricSerializer, **ERRORS},
        tags=["toolkit-admin"],
    )
    def post(self, request: Request, version: int) -> Response:
        row = service.activate_rubric(actor=request.user, version=version)
        return _private(Response(TkAdminRubricSerializer(_rubric(row)).data))


def _usage_params(request: Request) -> tuple[date | None, date | None, str]:
    raw = dict(request.query_params.items())
    renamed = {
        ("date_from" if k == "from" else "date_to" if k == "to" else k): v for k, v in raw.items()
    }
    query = TkAdminUsageQuerySerializer(data=renamed)
    query.is_valid(raise_exception=True)
    data = query.validated_data
    return data.get("start"), data.get("end"), data["group_by"]


class UsageView(APIView):
    policy = MANAGE

    @extend_schema(
        summary="AI use by day, prompt or agent",
        description="Counts, tokens and estimated cost only; no member content is held. Query "
        "`from`, `to` (dates, up to 366 days) and `group_by` (day, prompt, agent).",
        responses={200: TkAdminUsageRowSerializer(many=True), **ERRORS},
        tags=["toolkit-admin"],
    )
    def get(self, request: Request) -> Response:
        start, end, group = _usage_params(request)
        rows = service.usage(date_from=start, date_to=end, group_by=group)
        return _private(Response(TkAdminUsageRowSerializer(rows, many=True).data))


class UsageCsvView(APIView):
    policy = MANAGE

    @extend_schema(
        summary="The same usage as a CSV file",
        responses={200: OpenApiResponse(description="text/csv"), **ERRORS},
        tags=["toolkit-admin"],
    )
    def get(self, request: Request) -> HttpResponse:
        start, end, group = _usage_params(request)
        rows = service.usage(date_from=start, date_to=end, group_by=group)
        response = HttpResponse(service.usage_csv(rows), content_type="text/csv; charset=utf-8")
        response["Content-Disposition"] = 'attachment; filename="toolkit-usage.csv"'
        response["Cache-Control"] = "private, no-store"
        return response


class QualityView(APIView):
    policy = MANAGE

    @extend_schema(
        summary="Where outputs are failing",
        description="Refused model answers and failed jobs over the last seven days, by prompt "
        "and kind, with identifiers to investigate. No content is shown.",
        responses={200: TkAdminQualitySerializer, **ERRORS},
        tags=["toolkit-admin"],
    )
    def get(self, request: Request) -> Response:
        return _private(Response(TkAdminQualitySerializer(service.quality()).data))


class SettingsView(APIView):
    policy = SETTINGS

    @extend_schema(
        summary="The toolkit's configuration, without secrets",
        description="Read only. Feature flags and providers are changed by deployment.",
        responses={200: TkAdminSettingsSerializer, **ERRORS},
        tags=["toolkit-admin"],
    )
    def get(self, request: Request) -> Response:
        return _private(Response(TkAdminSettingsSerializer(service.settings_view()).data))
