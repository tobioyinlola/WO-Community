from typing import Any
from uuid import UUID

from django.conf import settings
from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, extend_schema
from rest_framework import exceptions
from rest_framework.parsers import MultiPartParser
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.integrations.storage import get_storage
from apps.integrations.storage.base import PRIVATE
from apps.toolkit.ai import errors as ai_errors
from apps.toolkit.decks import service
from apps.toolkit.decks.models import Deck, DeckAsset
from apps.toolkit.decks.serializers import (
    TkDeckAssetSerializer,
    TkDeckAssetUploadSerializer,
    TkDeckAssistResultSerializer,
    TkDeckAssistSerializer,
    TkDeckBriefSerializer,
    TkDeckCreateSerializer,
    TkDeckExportSerializer,
    TkDeckFindingSerializer,
    TkDeckPatchSerializer,
    TkDeckSerializer,
    TkDeckShownSerializer,
    TkDeckTemplateSerializer,
    TkDeckUpdateSerializer,
    TkDeckVersionSerializer,
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


def _private(response: Response) -> Response:
    response["Cache-Control"] = "private, no-store"
    return response


def _deck(venture: Venture, deck_id: UUID) -> Deck:
    deck = service.get(venture, deck_id)
    if deck is None:
        raise exceptions.NotFound()
    return deck


def _full(deck: Deck) -> dict[str, Any]:
    return {
        "id": deck.pk,
        "title": deck.title,
        "template_slug": deck.template_slug,
        "status": deck.status,
        "version": deck.version,
        "content": deck.content,
        "updated_at": deck.updated_at,
    }


def _asset_view(asset: DeckAsset) -> dict[str, Any]:
    url = get_storage().presign_get(
        bucket=PRIVATE,
        key=asset.storage_key,
        expires_in=settings.EXPORT_URL_TTL,
        filename="image.webp",
        content_type=asset.content_type,
    )
    return {
        "id": asset.pk,
        "filename": asset.filename,
        "width": asset.width,
        "height": asset.height,
        "size": asset.size,
        "url": url,
    }


class TemplatesView(APIView):
    policy = member_policy("decks")

    @extend_schema(
        summary="Deck templates",
        responses={200: TkDeckTemplateSerializer(many=True), **ERRORS},
        tags=["toolkit"],
    )
    def get(self, request: Request) -> Response:
        rows = [
            {
                "slug": t.slug,
                "name": t.name,
                "description": t.description,
                "slide_count": len(t.slides),
            }
            for t in service.templates()
        ]
        return Response(TkDeckTemplateSerializer(rows, many=True).data)


class DecksView(APIView):
    policy = member_policy("decks")

    @extend_schema(
        summary="Decks of a venture",
        responses={200: TkDeckBriefSerializer(many=True), **ERRORS},
        tags=["toolkit"],
    )
    def get(self, request: Request, venture_id: UUID) -> Response:
        venture = readable_venture(request, venture_id)
        rows = [
            {
                "id": d.pk,
                "title": d.title,
                "template_slug": d.template_slug,
                "status": d.status,
                "version": d.version,
                "slide_count": len(d.content.get("slides", [])),
                "updated_at": d.updated_at,
            }
            for d in Deck.objects.filter(venture=venture, deleted_at__isnull=True).order_by(
                "-updated_at"
            )
        ]
        return _private(Response(TkDeckBriefSerializer(rows, many=True).data))

    @extend_schema(
        summary="Create a deck from a template",
        description="The slides are filled from the venture profile in the founder's own words; "
        "figures are linked to the forecast and stay current. Nothing is written by a model.",
        request=TkDeckCreateSerializer,
        responses={201: TkDeckSerializer, **ERRORS},
        tags=["toolkit"],
    )
    def post(self, request: Request, venture_id: UUID) -> Response:
        venture = owned_venture(request, venture_id)
        body = TkDeckCreateSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        deck = service.create(
            venture,
            template_slug=body.validated_data["template"],
            title=body.validated_data.get("title", ""),
        )
        return _private(Response(TkDeckSerializer(_full(deck)).data, status=201))


class DeckView(APIView):
    policy = member_policy("decks")

    @extend_schema(
        summary="A deck's content, as saved",
        responses={200: TkDeckSerializer, **ERRORS},
        tags=["toolkit"],
    )
    def get(self, request: Request, venture_id: UUID, deck_id: UUID) -> Response:
        venture = readable_venture(request, venture_id)
        return _private(Response(TkDeckSerializer(_full(_deck(venture, deck_id))).data))

    @extend_schema(
        summary="Change the slides with patch operations",
        description="`ops` are add, remove, replace and move on `/slides/...` or `/theme/...`. "
        "All or nothing; the result is validated as a whole. A stale `base_version` is 409.",
        request=TkDeckPatchSerializer,
        responses={
            200: TkDeckSerializer,
            409: OpenApiResponse(description="The deck changed elsewhere"),
            **ERRORS,
        },
        tags=["toolkit"],
    )
    def patch(self, request: Request, venture_id: UUID, deck_id: UUID) -> Response:
        venture = owned_venture(request, venture_id)
        deck = _deck(venture, deck_id)
        body = TkDeckPatchSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        data = body.validated_data
        saved = service.apply_ops(
            deck, ops=data["ops"], base_version=data["base_version"], label=data.get("label", "")
        )
        return _private(Response(TkDeckSerializer(_full(saved)).data))

    @extend_schema(
        summary="Rename a deck or mark it ready",
        request=TkDeckUpdateSerializer,
        responses={200: TkDeckSerializer, **ERRORS},
        tags=["toolkit"],
    )
    def put(self, request: Request, venture_id: UUID, deck_id: UUID) -> Response:
        venture = owned_venture(request, venture_id)
        deck = _deck(venture, deck_id)
        body = TkDeckUpdateSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        saved = service.rename(
            deck,
            title=body.validated_data.get("title"),
            status=body.validated_data.get("status"),
        )
        return _private(Response(TkDeckSerializer(_full(saved)).data))

    @extend_schema(
        summary="Delete a deck and its images",
        request=None,
        responses={204: OpenApiResponse(description="Deleted"), **ERRORS},
        tags=["toolkit"],
    )
    def delete(self, request: Request, venture_id: UUID, deck_id: UUID) -> Response:
        venture = owned_venture(request, venture_id)
        service.delete(_deck(venture, deck_id))
        return Response(status=204)


class ShownView(APIView):
    policy = member_policy("decks")

    @extend_schema(
        summary="The deck as it should be shown",
        description="Linked figures are looked up now from the forecast and profile, and image "
        "addresses are signed and short lived. Use this for preview and presenting.",
        responses={200: TkDeckShownSerializer, **ERRORS},
        tags=["toolkit"],
    )
    def get(self, request: Request, venture_id: UUID, deck_id: UUID) -> Response:
        venture = readable_venture(request, venture_id)
        deck = _deck(venture, deck_id)
        shown = service.resolve(venture, deck)
        body = {
            "id": deck.pk,
            "title": deck.title,
            "version": deck.version,
            "slides": shown["slides"],
            "theme": shown["theme"],
        }
        return _private(Response(TkDeckShownSerializer(body).data))


class CheckView(APIView):
    policy = member_policy("decks")

    @extend_schema(
        summary="Check a deck before showing it",
        description="Gaps to fill, dense slides, missing notes and figures that are not in the "
        "profile or forecast. Advice only; nothing is blocked.",
        responses={200: TkDeckFindingSerializer(many=True), **ERRORS},
        tags=["toolkit"],
    )
    def get(self, request: Request, venture_id: UUID, deck_id: UUID) -> Response:
        venture = readable_venture(request, venture_id)
        findings = service.check(venture, _deck(venture, deck_id))
        return _private(Response(TkDeckFindingSerializer(findings, many=True).data))


class AssistView(APIView):
    policy = member_policy("decks")

    @extend_schema(
        summary="Ask for reworded text on one slide",
        description="A proposal only. Apply what you accept with a `replace` operation. A "
        "rewrite that adds a figure is dropped.",
        request=TkDeckAssistSerializer,
        responses={200: TkDeckAssistResultSerializer, **ERRORS},
        tags=["toolkit"],
    )
    def post(self, request: Request, venture_id: UUID, deck_id: UUID) -> Response:
        venture = owned_venture(request, venture_id)
        deck = _deck(venture, deck_id)
        body = TkDeckAssistSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        try:
            result = service.assist(
                venture=venture,
                owner_id=uid(request),
                deck=deck,
                slide_id=body.validated_data["slide_id"],
                action=body.validated_data["action"],
            )
        except (JobFailed, TransientError) as exc:
            raise ai_errors.translate(exc) from exc
        return _private(Response(TkDeckAssistResultSerializer(result).data))


class ExportView(APIView):
    policy = member_policy("decks")

    @extend_schema(
        summary="Export a deck as PowerPoint or PDF",
        description="Starts a job and answers 202. On success `result.id` is an export for "
        "`GET /exports/{id}`.",
        parameters=[KEY],
        request=TkDeckExportSerializer,
        responses={202: TkJobSerializer, 200: TkJobSerializer, **ERRORS},
        tags=["toolkit"],
    )
    def post(self, request: Request, venture_id: UUID, deck_id: UUID) -> Response:
        venture = owned_venture(request, venture_id)
        deck = _deck(venture, deck_id)
        body = TkDeckExportSerializer(data=request.data or {})
        body.is_valid(raise_exception=True)
        job, created = jobs.start(
            owner_id=uid(request),
            kind="exports.deck",
            venture=venture,
            payload={"deck_id": str(deck.pk), "format": body.validated_data["format"]},
            idempotency_key=idempotency_key(request),
        )
        return accepted(request, job, created)


class VersionsView(APIView):
    policy = member_policy("decks")

    @extend_schema(
        summary="Saved versions of a deck",
        responses={200: TkDeckVersionSerializer(many=True), **ERRORS},
        tags=["toolkit"],
    )
    def get(self, request: Request, venture_id: UUID, deck_id: UUID) -> Response:
        venture = readable_venture(request, venture_id)
        rows = [
            {"version": v.version, "label": v.label, "created_at": v.created_at}
            for v in _deck(venture, deck_id).versions.all()
        ]
        return _private(Response(TkDeckVersionSerializer(rows, many=True).data))


class RestoreView(APIView):
    policy = member_policy("decks")

    @extend_schema(
        summary="Go back to a saved version",
        description="The current deck is saved first, so this can be undone.",
        request=None,
        responses={200: TkDeckSerializer, **ERRORS},
        tags=["toolkit"],
    )
    def post(self, request: Request, venture_id: UUID, deck_id: UUID, version: int) -> Response:
        venture = owned_venture(request, venture_id)
        deck = _deck(venture, deck_id)
        return _private(Response(TkDeckSerializer(_full(service.restore(deck, version))).data))


class AssetsView(APIView):
    policy = member_policy("decks")
    parser_classes = [MultiPartParser]

    @extend_schema(
        summary="Images added to a deck",
        responses={200: TkDeckAssetSerializer(many=True), **ERRORS},
        tags=["toolkit"],
    )
    def get(self, request: Request, venture_id: UUID, deck_id: UUID) -> Response:
        venture = readable_venture(request, venture_id)
        deck = _deck(venture, deck_id)
        return _private(
            Response(
                TkDeckAssetSerializer([_asset_view(a) for a in deck.assets.all()], many=True).data
            )
        )

    @extend_schema(
        summary="Add an image to a deck",
        description="PNG, JPEG or WebP up to 5 MB. It is checked, scanned and re-encoded; "
        "reference the returned id from an `image` element with a description.",
        request={"multipart/form-data": TkDeckAssetUploadSerializer},
        responses={201: TkDeckAssetSerializer, **ERRORS},
        tags=["toolkit"],
    )
    def post(self, request: Request, venture_id: UUID, deck_id: UUID) -> Response:
        venture = owned_venture(request, venture_id)
        deck = _deck(venture, deck_id)
        body = TkDeckAssetUploadSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        upload = body.validated_data["file"]
        if upload.size > service.MAX_ASSET_BYTES:
            raise exceptions.ValidationError({"file": ["Images can be up to 5 MB."]})
        asset = service.add_asset(
            deck, owner_id=uid(request), data=upload.read(), filename=upload.name or ""
        )
        return _private(Response(TkDeckAssetSerializer(_asset_view(asset)).data, status=201))


class AssetView(APIView):
    policy = member_policy("decks")

    @extend_schema(
        summary="Remove an image from a deck",
        description="409 while a slide still uses it.",
        request=None,
        responses={204: OpenApiResponse(description="Removed"), **ERRORS},
        tags=["toolkit"],
    )
    def delete(self, request: Request, venture_id: UUID, deck_id: UUID, asset_id: UUID) -> Response:
        venture = owned_venture(request, venture_id)
        deck = _deck(venture, deck_id)
        asset = deck.assets.filter(pk=asset_id).first()
        if asset is None:
            raise exceptions.NotFound()
        service.remove_asset(deck, asset)
        return Response(status=204)
