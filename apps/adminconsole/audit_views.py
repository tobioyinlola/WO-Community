"""The audit log for admins: read, filter, open one entry and export. Nothing here can change it."""

import csv
import json
from datetime import UTC, datetime, time, timedelta
from typing import Any
from uuid import UUID

from django.http import StreamingHttpResponse
from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import exceptions, serializers
from rest_framework.pagination import CursorPagination
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.adminconsole.people import people
from apps.adminconsole.views import _actor, _ip
from apps.audit import selectors, services
from apps.audit.models import AuditLog
from apps.core import policies
from apps.core.serializers import StrictSerializer

VIEW = policies.admin_permission("audit.read")
EXPORT_LIMIT = 50_000
ERRORS = {
    401: OpenApiResponse(description="Not authenticated"),
    403: OpenApiResponse(description="Not allowed, or MFA missing"),
}


class AuditPagination(CursorPagination):
    """Newest first; the sequence number breaks ties so the order is stable."""

    page_size = 25
    page_size_query_param = "limit"
    max_page_size = 100
    ordering = ("-created_at", "-seq")


class AuditQuerySerializer(StrictSerializer):
    date_from = serializers.DateField(required=False)
    date_to = serializers.DateField(required=False)
    actor = serializers.CharField(required=False, allow_blank=True, max_length=120, default="")
    group = serializers.CharField(
        required=False,
        allow_blank=True,
        max_length=200,
        default="",
        help_text="Comma separated: members, content, jobs, events, courses, certificates, "
        "settings, security.",
    )
    action = serializers.CharField(required=False, allow_blank=True, max_length=300, default="")
    outcome = serializers.ChoiceField(
        choices=["success", "failure"], required=False, allow_blank=True, default=""
    )
    q = serializers.CharField(required=False, allow_blank=True, max_length=120, default="")
    target_type = serializers.CharField(required=False, allow_blank=True, max_length=100)
    target_id = serializers.CharField(required=False, allow_blank=True, max_length=64)
    limit = serializers.IntegerField(required=False, min_value=1, max_value=100)
    cursor = serializers.CharField(required=False, allow_blank=True)


class AuditActorSerializer(serializers.Serializer):
    id = serializers.UUIDField(allow_null=True)
    name = serializers.CharField()
    email = serializers.CharField(allow_blank=True)
    roles = serializers.ListField(child=serializers.CharField())


class AuditTargetSerializer(serializers.Serializer):
    type = serializers.CharField(allow_blank=True)
    id = serializers.CharField(allow_blank=True)
    title = serializers.CharField(allow_blank=True)


class AuditChangeSerializer(serializers.Serializer):
    field = serializers.CharField()
    before = serializers.JSONField(allow_null=True)
    after = serializers.JSONField(allow_null=True)


class AuditEntrySerializer(serializers.Serializer):
    id = serializers.UUIDField()
    created_at = serializers.DateTimeField()
    actor = AuditActorSerializer()
    action = serializers.CharField()
    target = AuditTargetSerializer()
    outcome = serializers.CharField()
    ip_ref = serializers.CharField(allow_blank=True)
    request_id = serializers.CharField(allow_blank=True)
    reason = serializers.CharField(allow_blank=True)
    changes = AuditChangeSerializer(many=True)


class AuditEntryDetailSerializer(AuditEntrySerializer):
    before = serializers.JSONField(allow_null=True)
    after = serializers.JSONField(allow_null=True)


def _filters(request: Request) -> dict[str, Any]:
    params = AuditQuerySerializer(data=request.query_params.dict())
    params.is_valid(raise_exception=True)
    data = params.validated_data
    start, end = data.get("date_from"), data.get("date_to")
    return {
        "date_from": datetime.combine(start, time.min, tzinfo=UTC) if start else None,
        # The end day is included, so the bound is the start of the day after.
        "date_to": datetime.combine(end + timedelta(days=1), time.min, tzinfo=UTC) if end else None,
        "actor": data["actor"],
        "groups": [g for g in data["group"].split(",") if g],
        "actions": [a for a in data["action"].split(",") if a],
        "outcome": data["outcome"],
        "q": data["q"],
        "target_type": data.get("target_type", ""),
        "target_id": data.get("target_id", ""),
    }


def _rows(entries: list[AuditLog], detail: bool = False) -> list[dict[str, Any]]:
    who = people(e.actor_id for e in entries)
    out = []
    for e in entries:
        person = who.get(e.actor_id) if e.actor_id else None
        actor: dict[str, Any]
        if e.actor_id is None:
            actor = {"id": None, "name": "System", "email": "", "roles": []}
        elif person is None:
            actor = {
                "id": e.actor_id,
                "name": "Deleted account",
                "email": "",
                "roles": e.actor_roles,
            }
        else:
            actor = {**person, "roles": e.actor_roles}
        row: dict[str, Any] = {
            "id": e.id,
            "created_at": e.created_at,
            "actor": actor,
            "action": e.action,
            "target": {
                "type": e.target_type,
                "id": e.target_id,
                "title": e.target_label or e.target_id,
            },
            "outcome": e.outcome,
            "ip_ref": e.ip_hash[:8],
            "request_id": e.request_id,
            "reason": e.reason,
            "changes": selectors.changes(e.before, e.after),
        }
        if detail:
            row.update(before=e.before, after=e.after)
        out.append(row)
    return out


class AuditListView(APIView):
    policy = VIEW
    pagination_class = AuditPagination

    @extend_schema(
        summary="The audit log, newest first",
        description="Filters combine. The log starts at deployment and cannot be edited.",
        parameters=[AuditQuerySerializer],
        responses={200: AuditEntrySerializer(many=True), **ERRORS},
        tags=["admin"],
    )
    def get(self, request: Request) -> Response:
        paginator = AuditPagination()
        found = selectors.entries(**_filters(request))
        page = paginator.paginate_queryset(found, request, view=self)
        return paginator.get_paginated_response(_rows(list(page or [])))


class AuditEntryView(APIView):
    policy = VIEW

    @extend_schema(
        summary="One audit entry with its before and after",
        responses={
            200: AuditEntryDetailSerializer,
            **ERRORS,
            404: OpenApiResponse(description="No such entry"),
        },
        tags=["admin"],
    )
    def get(self, request: Request, entry_id: UUID) -> Response:
        entry = AuditLog.objects.filter(pk=entry_id).first()
        if entry is None:
            raise exceptions.NotFound()
        return Response(_rows([entry], detail=True)[0])


class _Echo:
    def write(self, value: str) -> str:
        return value


class AuditExportView(APIView):
    policy = VIEW

    @extend_schema(
        summary="Download the filtered audit log as CSV",
        description=f"Up to {EXPORT_LIMIT} rows, newest first. The export is itself recorded.",
        parameters=[AuditQuerySerializer],
        responses={(200, "text/csv"): OpenApiResponse(description="CSV file"), **ERRORS},
        tags=["admin"],
    )
    def get(self, request: Request) -> StreamingHttpResponse:
        found = selectors.entries(**_filters(request)).order_by("-created_at", "-seq")
        entries = list(found[:EXPORT_LIMIT])
        services.record(
            actor=_actor(request),
            action="audit.exported",
            target_type="audit",
            after={"rows": len(entries), "filters": request.query_params.dict()},
            ip=_ip(request),
        )
        data = _rows(entries)
        writer = csv.writer(_Echo())

        def lines() -> Any:
            yield writer.writerow(
                [
                    "time_utc",
                    "actor",
                    "actor_email",
                    "action",
                    "target",
                    "outcome",
                    "reason",
                    "changes",
                ]
            )
            for r in data:
                target = f"{r['target']['type']} {r['target']['title']}".strip()
                yield writer.writerow(
                    [
                        r["created_at"].isoformat(),
                        r["actor"]["name"],
                        r["actor"]["email"],
                        r["action"],
                        target,
                        r["outcome"],
                        r["reason"],
                        json.dumps(r["changes"], default=str),
                    ]
                )

        response = StreamingHttpResponse(lines(), content_type="text/csv")
        response["Content-Disposition"] = 'attachment; filename="audit-log.csv"'
        return response
