from typing import Any
from uuid import UUID

from django.db import transaction
from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, extend_schema
from rest_framework import serializers, status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.adminconsole.views import _actor, _ip
from apps.audit import services as audit
from apps.core import policies
from apps.core.serializers import StrictSerializer
from apps.reference import services

MANAGE = policies.admin_permission("reference.manage")
KIND = OpenApiParameter("kind", str, OpenApiParameter.PATH, enum=list(services.KINDS))
ERRORS = {
    401: OpenApiResponse(description="Not authenticated"),
    403: OpenApiResponse(description="Not allowed, or MFA missing"),
    404: OpenApiResponse(description="Unknown list or entry"),
    409: OpenApiResponse(description="Name or slug taken, entry in use, or the list changed"),
}


class ReferenceItemSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    slug = serializers.CharField()
    name = serializers.CharField()
    active = serializers.BooleanField()
    sort_order = serializers.IntegerField()
    usage = serializers.IntegerField(help_text="Records that use this entry")


class ReferenceCreateSerializer(StrictSerializer):
    name = serializers.CharField(max_length=200)
    slug = serializers.CharField(max_length=80, required=False, default="")
    sort_order = serializers.IntegerField(min_value=0, max_value=10_000, required=False)


class ReferenceUpdateSerializer(StrictSerializer):
    """The slug cannot change: it is used in URLs, filters and stored records."""

    name = serializers.CharField(max_length=200, required=False)
    active = serializers.BooleanField(required=False)
    sort_order = serializers.IntegerField(min_value=0, max_value=10_000, required=False)

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        if not attrs:
            raise serializers.ValidationError("Send at least one field to change.")
        return attrs


class ReferenceOrderSerializer(StrictSerializer):
    ids = serializers.ListField(child=serializers.UUIDField(), allow_empty=False, max_length=500)


def _target(kind: str) -> str:
    return f"reference.{kind}"


def _one(kind: str, item_id: Any) -> dict[str, Any]:
    return next(entry for entry in services.list_items(kind) if entry["id"] == item_id)


class ReferenceListView(APIView):
    policy = MANAGE

    @extend_schema(
        summary="Every entry of a list, retired ones included, with how many records use it",
        parameters=[KIND],
        responses={200: ReferenceItemSerializer(many=True), **ERRORS},
        tags=["admin"],
    )
    def get(self, request: Request, kind: str) -> Response:
        return Response(ReferenceItemSerializer(services.list_items(kind), many=True).data)

    @extend_schema(
        summary="Add an entry",
        description="The slug defaults to one made from the name and can never be changed.",
        parameters=[KIND],
        request=ReferenceCreateSerializer,
        responses={201: ReferenceItemSerializer, **ERRORS},
        tags=["admin"],
    )
    def post(self, request: Request, kind: str) -> Response:
        serializer = ReferenceCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        with transaction.atomic():
            item = services.create_item(kind=kind, **serializer.validated_data)
            audit.record(
                actor=_actor(request),
                action="reference.created",
                target_type=_target(kind),
                target_id=item.pk,
                after=services.snapshot(item),
                ip=_ip(request),
            )
        return Response(
            ReferenceItemSerializer(_one(kind, item.pk)).data, status=status.HTTP_201_CREATED
        )


class ReferenceItemView(APIView):
    policy = MANAGE

    @extend_schema(
        summary="Rename, retire, restore or reposition an entry",
        description="Retiring hides an entry from new choices; records that already use it keep "
        "it. Renaming updates the public pages that show it.",
        parameters=[KIND],
        request=ReferenceUpdateSerializer,
        responses={200: ReferenceItemSerializer, **ERRORS},
        tags=["admin"],
    )
    def patch(self, request: Request, kind: str, item_id: UUID) -> Response:
        serializer = ReferenceUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        with transaction.atomic():
            item, before = services.update_item(
                kind=kind, item_id=item_id, **serializer.validated_data
            )
            audit.record(
                actor=_actor(request),
                action="reference.updated",
                target_type=_target(kind),
                target_id=item.pk,
                before=before,
                after=services.snapshot(item),
                ip=_ip(request),
            )
        return Response(ReferenceItemSerializer(_one(kind, item.pk)).data)

    @extend_schema(
        summary="Delete an entry nobody uses",
        description="An entry in use cannot be deleted (409); retire it instead.",
        parameters=[KIND],
        responses={204: None, **ERRORS},
        tags=["admin"],
    )
    def delete(self, request: Request, kind: str, item_id: UUID) -> Response:
        with transaction.atomic():
            before = services.delete_item(kind=kind, item_id=item_id)
            audit.record(
                actor=_actor(request),
                action="reference.deleted",
                target_type=_target(kind),
                target_id=item_id,
                before=before,
                ip=_ip(request),
            )
        return Response(status=status.HTTP_204_NO_CONTENT)


class ReferenceOrderView(APIView):
    policy = MANAGE

    @extend_schema(
        summary="Set the display order of a list",
        description="Send every entry's id exactly once, in the order wanted.",
        parameters=[KIND],
        request=ReferenceOrderSerializer,
        responses={200: ReferenceItemSerializer(many=True), **ERRORS},
        tags=["admin"],
    )
    def put(self, request: Request, kind: str) -> Response:
        serializer = ReferenceOrderSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        with transaction.atomic():
            items = services.reorder(kind=kind, ids=serializer.validated_data["ids"])
            audit.record(
                actor=_actor(request),
                action="reference.reordered",
                target_type=_target(kind),
                after={"order": [entry["slug"] for entry in items]},
                ip=_ip(request),
            )
        return Response(ReferenceItemSerializer(items, many=True).data)
