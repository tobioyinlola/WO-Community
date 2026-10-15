from typing import Any
from uuid import UUID

from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, extend_schema
from rest_framework import exceptions
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.toolkit.ai import errors as ai_errors
from apps.toolkit.ai import runner
from apps.toolkit.jobs import services as jobs
from apps.toolkit.jobs.serializers import TkJobSerializer
from apps.toolkit.jobs.services import JobFailed
from apps.toolkit.jobs.views import accepted, idempotency_key
from apps.toolkit.prototypes import registry, service
from apps.toolkit.prototypes.models import Prototype
from apps.toolkit.prototypes.serializers import (
    TkComponentSerializer,
    TkPrototypeBriefSerializer,
    TkPrototypeCreateSerializer,
    TkPrototypeGenerateSerializer,
    TkPrototypePatchSerializer,
    TkPrototypeRenameSerializer,
    TkPrototypeSerializer,
    TkPrototypeTemplateSerializer,
    TkPrototypeVersionSerializer,
)
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


def _private(response: Response) -> Response:
    response["Cache-Control"] = "private, no-store"
    return response


def _proto(venture: Venture, prototype_id: UUID) -> Prototype:
    prototype = service.get(venture, prototype_id)
    if prototype is None:
        raise exceptions.NotFound()
    return prototype


def _full(p: Prototype) -> dict[str, Any]:
    return {
        "id": p.pk,
        "title": p.title,
        "template_slug": p.template_slug,
        "version": p.version,
        "spec": p.spec,
        "updated_at": p.updated_at,
    }


class ComponentsView(APIView):
    policy = member_policy("prototypes")

    @extend_schema(
        summary="The components a prototype can use",
        responses={200: TkComponentSerializer(many=True), **ERRORS},
        tags=["toolkit"],
    )
    def get(self, request: Request) -> Response:
        return Response(TkComponentSerializer(registry.catalogue(), many=True).data)


class TemplatesView(APIView):
    policy = member_policy("prototypes")

    @extend_schema(
        summary="Prototype templates",
        responses={200: TkPrototypeTemplateSerializer(many=True), **ERRORS},
        tags=["toolkit"],
    )
    def get(self, request: Request) -> Response:
        rows = [
            {
                "slug": t.slug,
                "name": t.name,
                "description": t.description,
                "screen_count": len(t.spec.get("screens", [])),
                "kind": t.spec.get("kind", "web"),
            }
            for t in service.available_templates()
        ]
        return Response(TkPrototypeTemplateSerializer(rows, many=True).data)


class PrototypesView(APIView):
    policy = member_policy("prototypes")

    @extend_schema(
        summary="Prototypes of a venture",
        responses={200: TkPrototypeBriefSerializer(many=True), **ERRORS},
        tags=["toolkit"],
    )
    def get(self, request: Request, venture_id: UUID) -> Response:
        venture = readable_venture(request, venture_id)
        rows = [
            {
                "id": p.pk,
                "title": p.title,
                "template_slug": p.template_slug,
                "kind": p.spec.get("kind", "web"),
                "version": p.version,
                "screen_count": len(p.spec.get("screens", [])),
                "updated_at": p.updated_at,
            }
            for p in Prototype.objects.filter(venture=venture).order_by("-updated_at")
        ]
        return _private(Response(TkPrototypeBriefSerializer(rows, many=True).data))

    @extend_schema(
        summary="Create a prototype from a template",
        request=TkPrototypeCreateSerializer,
        responses={201: TkPrototypeSerializer, **ERRORS},
        tags=["toolkit"],
    )
    def post(self, request: Request, venture_id: UUID) -> Response:
        venture = owned_venture(request, venture_id)
        body = TkPrototypeCreateSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        made = service.create_from_template(
            venture,
            slug=body.validated_data["template"],
            title=body.validated_data.get("title", ""),
        )
        return _private(Response(TkPrototypeSerializer(_full(made)).data, status=201))


class GenerateView(APIView):
    policy = member_policy("prototypes")

    @extend_schema(
        summary="Draft a prototype from the venture",
        description="Starts a job and answers 202. When it succeeds `result.id` is the new "
        "prototype. The draft is checked against the component rules; if a valid design cannot "
        "be made you get a template instead (`result.fallback`). Nothing is written into your "
        "profile.",
        parameters=[KEY],
        request=TkPrototypeGenerateSerializer,
        responses={202: TkJobSerializer, 200: TkJobSerializer, **ERRORS},
        tags=["toolkit"],
    )
    def post(self, request: Request, venture_id: UUID) -> Response:
        venture = owned_venture(request, venture_id)
        body = TkPrototypeGenerateSerializer(data=request.data or {})
        body.is_valid(raise_exception=True)
        data = body.validated_data
        try:
            runner.require_ai()  # drafting is the model's job; templates work without it
        except JobFailed as exc:
            raise ai_errors.translate(exc) from exc
        job, created = jobs.start(
            owner_id=uid(request),
            kind="prototype.generate",
            venture=venture,
            payload={
                "kind": data["kind"],
                "brief": service.check_brief(data.get("brief", "")),
                "title": data.get("title", ""),
            },
            idempotency_key=idempotency_key(request),
        )
        return accepted(request, job, created)


class PrototypeView(APIView):
    policy = member_policy("prototypes")

    @extend_schema(
        summary="A prototype",
        responses={200: TkPrototypeSerializer, **ERRORS},
        tags=["toolkit"],
    )
    def get(self, request: Request, venture_id: UUID, prototype_id: UUID) -> Response:
        venture = readable_venture(request, venture_id)
        return _private(Response(TkPrototypeSerializer(_full(_proto(venture, prototype_id))).data))

    @extend_schema(
        summary="Change a prototype with patch operations",
        description="`add`, `remove`, `replace`, `move` on `/screens/...`, `/theme`, `/start` "
        "or `/kind`. All or nothing and validated as a whole; a stale `base_version` is 409.",
        request=TkPrototypePatchSerializer,
        responses={200: TkPrototypeSerializer, **ERRORS},
        tags=["toolkit"],
    )
    def patch(self, request: Request, venture_id: UUID, prototype_id: UUID) -> Response:
        venture = owned_venture(request, venture_id)
        prototype = _proto(venture, prototype_id)
        body = TkPrototypePatchSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        data = body.validated_data
        saved = service.apply_ops(
            prototype,
            ops=data["ops"],
            base_version=data["base_version"],
            label=data.get("label", ""),
        )
        return _private(Response(TkPrototypeSerializer(_full(saved)).data))

    @extend_schema(
        summary="Rename a prototype",
        request=TkPrototypeRenameSerializer,
        responses={200: TkPrototypeSerializer, **ERRORS},
        tags=["toolkit"],
    )
    def put(self, request: Request, venture_id: UUID, prototype_id: UUID) -> Response:
        venture = owned_venture(request, venture_id)
        prototype = _proto(venture, prototype_id)
        body = TkPrototypeRenameSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        saved = service.rename(prototype, body.validated_data["title"])
        return _private(Response(TkPrototypeSerializer(_full(saved)).data))

    @extend_schema(
        summary="Delete a prototype",
        request=None,
        responses={204: OpenApiResponse(description="Deleted"), **ERRORS},
        tags=["toolkit"],
    )
    def delete(self, request: Request, venture_id: UUID, prototype_id: UUID) -> Response:
        venture = owned_venture(request, venture_id)
        _proto(venture, prototype_id).delete()
        return Response(status=204)


class DuplicateView(APIView):
    policy = member_policy("prototypes")

    @extend_schema(
        summary="Copy a prototype",
        request=None,
        responses={201: TkPrototypeSerializer, **ERRORS},
        tags=["toolkit"],
    )
    def post(self, request: Request, venture_id: UUID, prototype_id: UUID) -> Response:
        venture = owned_venture(request, venture_id)
        made = service.duplicate(_proto(venture, prototype_id))
        return _private(Response(TkPrototypeSerializer(_full(made)).data, status=201))


class VersionsView(APIView):
    policy = member_policy("prototypes")

    @extend_schema(
        summary="Saved versions",
        responses={200: TkPrototypeVersionSerializer(many=True), **ERRORS},
        tags=["toolkit"],
    )
    def get(self, request: Request, venture_id: UUID, prototype_id: UUID) -> Response:
        venture = readable_venture(request, venture_id)
        rows = [
            {"version": v.version, "label": v.label, "created_at": v.created_at}
            for v in _proto(venture, prototype_id).versions.all()
        ]
        return _private(Response(TkPrototypeVersionSerializer(rows, many=True).data))


class RestoreView(APIView):
    policy = member_policy("prototypes")

    @extend_schema(
        summary="Go back to a saved version",
        request=None,
        responses={200: TkPrototypeSerializer, **ERRORS},
        tags=["toolkit"],
    )
    def post(
        self, request: Request, venture_id: UUID, prototype_id: UUID, version: int
    ) -> Response:
        venture = owned_venture(request, venture_id)
        prototype = _proto(venture, prototype_id)
        return _private(
            Response(TkPrototypeSerializer(_full(service.restore(prototype, version))).data)
        )
