from typing import Any
from uuid import UUID

from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, extend_schema
from rest_framework import exceptions
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.toolkit.ai import errors as ai_errors
from apps.toolkit.forecasts import catalog, engine, service
from apps.toolkit.forecasts.models import Forecast
from apps.toolkit.forecasts.serializers import (
    TkForecastCreateSerializer,
    TkForecastExportSerializer,
    TkForecastResultSerializer,
    TkForecastSaveSerializer,
    TkForecastScenariosSerializer,
    TkForecastSensitivitySerializer,
    TkForecastSerializer,
    TkForecastSuggestionSerializer,
    TkForecastTemplateSerializer,
    TkForecastVersionSerializer,
)
from apps.toolkit.jobs import services as jobs
from apps.toolkit.jobs.serializers import TkJobSerializer
from apps.toolkit.jobs.services import JobFailed, TransientError
from apps.toolkit.jobs.views import accepted, idempotency_key
from apps.toolkit.ventures.models import Venture
from apps.toolkit.ventures.permissions import (
    member_policy,
    owned_venture,
    readable_venture,
    uid,
)

ERRORS = {
    401: OpenApiResponse(description="Not authenticated"),
    403: OpenApiResponse(description="Not an approved member"),
    404: OpenApiResponse(description="Not found, or not yours, or the tool is off"),
}
KEY = OpenApiParameter("Idempotency-Key", str, OpenApiParameter.HEADER, required=False)
SCENARIO = OpenApiParameter(
    "scenario", str, OpenApiParameter.QUERY, enum=list(engine.SCENARIOS), required=False
)


def _private(response: Response) -> Response:
    response["Cache-Control"] = "private, no-store"
    return response


def _forecast(venture: Venture) -> Forecast:
    forecast = service.get(venture)
    if forecast is None:
        raise exceptions.NotFound()
    return forecast


def _scenario(request: Request) -> str:
    name = request.query_params.get("scenario", "base")
    if name not in engine.SCENARIOS:
        raise exceptions.ValidationError({"scenario": ["Choose conservative, base or optimistic."]})
    return name


def _view(forecast: Forecast) -> dict[str, Any]:
    return {
        "version": forecast.version,
        "template": forecast.template,
        "currency": forecast.currency,
        "assumptions": forecast.assumptions,
        "updated_at": forecast.updated_at,
    }


class TemplatesView(APIView):
    policy = member_policy("forecast")

    @extend_schema(
        summary="The revenue templates and what each asks for",
        responses={200: TkForecastTemplateSerializer(many=True), **ERRORS},
        tags=["toolkit"],
    )
    def get(self, request: Request) -> Response:
        return Response(TkForecastTemplateSerializer(catalog.templates(), many=True).data)


class ForecastView(APIView):
    policy = member_policy("forecast")

    @extend_schema(
        summary="The forecast assumptions",
        responses={200: TkForecastSerializer, **ERRORS},
        tags=["toolkit"],
    )
    def get(self, request: Request, venture_id: UUID) -> Response:
        venture = readable_venture(request, venture_id)
        return _private(Response(TkForecastSerializer(_view(_forecast(venture))).data))

    @extend_schema(
        summary="Start the forecast",
        description="Starts from the venture profile (template, currency, price, planned "
        "funding) unless you send assumptions. 409 if one exists already.",
        request=TkForecastCreateSerializer,
        responses={201: TkForecastSerializer, **ERRORS},
        tags=["toolkit"],
    )
    def post(self, request: Request, venture_id: UUID) -> Response:
        venture = owned_venture(request, venture_id)
        body = TkForecastCreateSerializer(data=request.data or {})
        body.is_valid(raise_exception=True)
        forecast = service.create(venture, body.validated_data.get("assumptions"))
        return _private(Response(TkForecastSerializer(_view(forecast)).data, status=201))

    @extend_schema(
        summary="Save the assumptions",
        description="`base_version` must be the version you loaded (409 otherwise). Every "
        "value is checked and named in the 400 when it is out of range.",
        request=TkForecastSaveSerializer,
        responses={200: TkForecastSerializer, **ERRORS},
        tags=["toolkit"],
    )
    def put(self, request: Request, venture_id: UUID) -> Response:
        venture = owned_venture(request, venture_id)
        _forecast(venture)
        body = TkForecastSaveSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        data = body.validated_data
        forecast = service.save(
            venture,
            dict(data["assumptions"]),
            base_version=data["base_version"],
            note=data.get("note", ""),
        )
        return _private(Response(TkForecastSerializer(_view(forecast)).data))


class ResultView(APIView):
    policy = member_policy("forecast")

    @extend_schema(
        summary="The 24 month forecast",
        description="Calculated from the saved assumptions. Money is whole minor units.",
        parameters=[SCENARIO],
        responses={200: TkForecastResultSerializer, **ERRORS},
        tags=["toolkit"],
    )
    def get(self, request: Request, venture_id: UUID) -> Response:
        venture = readable_venture(request, venture_id)
        forecast = _forecast(venture)
        result = engine.to_dict(service.compute(forecast, _scenario(request)))
        result["version"] = forecast.version
        return _private(Response(TkForecastResultSerializer(result).data))


class ScenariosView(APIView):
    policy = member_policy("forecast")

    @extend_schema(
        summary="The three scenarios side by side",
        responses={200: TkForecastScenariosSerializer, **ERRORS},
        tags=["toolkit"],
    )
    def get(self, request: Request, venture_id: UUID) -> Response:
        venture = readable_venture(request, venture_id)
        forecast = _forecast(venture)
        body = {
            "currency": forecast.currency,
            "version": forecast.version,
            **service.all_scenarios(forecast),
        }
        return _private(Response(TkForecastScenariosSerializer(body).data))


class SensitivityView(APIView):
    policy = member_policy("forecast")

    @extend_schema(
        summary="Which assumptions move the result most",
        description="Each main assumption is moved 20 percent down and up; the effect on year "
        "two revenue and the lowest cash is listed, largest first.",
        responses={200: TkForecastSensitivitySerializer(many=True), **ERRORS},
        tags=["toolkit"],
    )
    def get(self, request: Request, venture_id: UUID) -> Response:
        venture = readable_venture(request, venture_id)
        rows = engine.sensitivity(_forecast(venture).assumptions)
        return _private(Response(TkForecastSensitivitySerializer(rows, many=True).data))


class SuggestView(APIView):
    policy = member_policy("forecast")

    @extend_schema(
        summary="Proposed assumptions from sourced benchmarks",
        description="Proposals only, each with the source it rests on. Nothing is saved: copy "
        "the ones you accept into the assumptions and save. Prices and volumes are never "
        "proposed.",
        request=None,
        responses={200: TkForecastSuggestionSerializer, **ERRORS},
        tags=["toolkit"],
    )
    def post(self, request: Request, venture_id: UUID) -> Response:
        venture = owned_venture(request, venture_id)
        try:
            body = service.suggest(
                venture=venture, owner_id=uid(request), forecast=_forecast(venture)
            )
        except (JobFailed, TransientError) as exc:
            raise ai_errors.translate(exc) from exc
        return _private(Response(TkForecastSuggestionSerializer(body).data))


class ExportView(APIView):
    policy = member_policy("forecast")

    @extend_schema(
        summary="Export the forecast as a spreadsheet or a PDF",
        description="Starts a job and answers 202. The spreadsheet keeps its working: derived "
        "lines are formulas. When the job succeeds `result.id` is an export for "
        "`GET /exports/{id}`.",
        parameters=[KEY],
        request=TkForecastExportSerializer,
        responses={202: TkJobSerializer, 200: TkJobSerializer, **ERRORS},
        tags=["toolkit"],
    )
    def post(self, request: Request, venture_id: UUID) -> Response:
        venture = owned_venture(request, venture_id)
        _forecast(venture)
        body = TkForecastExportSerializer(data=request.data or {})
        body.is_valid(raise_exception=True)
        job, created = jobs.start(
            owner_id=uid(request),
            kind="exports.forecast",
            venture=venture,
            payload={"format": body.validated_data["format"]},
            idempotency_key=idempotency_key(request),
        )
        return accepted(request, job, created)


class VersionsView(APIView):
    policy = member_policy("forecast")

    @extend_schema(
        summary="Saved versions of the assumptions",
        responses={200: TkForecastVersionSerializer(many=True), **ERRORS},
        tags=["toolkit"],
    )
    def get(self, request: Request, venture_id: UUID) -> Response:
        venture = readable_venture(request, venture_id)
        rows = [
            {"version": v.version, "note": v.note, "created_at": v.created_at}
            for v in _forecast(venture).versions.all()
        ]
        return _private(Response(TkForecastVersionSerializer(rows, many=True).data))


class RestoreView(APIView):
    policy = member_policy("forecast")

    @extend_schema(
        summary="Go back to a saved version",
        description="Saved as a new version, so it can be undone.",
        request=None,
        responses={200: TkForecastSerializer, **ERRORS},
        tags=["toolkit"],
    )
    def post(self, request: Request, venture_id: UUID, version: int) -> Response:
        venture = owned_venture(request, venture_id)
        _forecast(venture)
        return _private(
            Response(TkForecastSerializer(_view(service.restore(venture, version))).data)
        )
