from uuid import UUID

from django.http import HttpResponse
from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, extend_schema
from rest_framework import exceptions, status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.adminconsole.views import _actor, _ip
from apps.audit import services as audit
from apps.core import etag, policies
from apps.core.pagination import AdminLimitOffsetPagination
from apps.events import selectors, services
from apps.events.models import Event
from apps.events.serializers import (
    AdminEventSerializer,
    AdminQuerySerializer,
    AttendeeQuerySerializer,
    AttendeeSerializer,
    CheckInSerializer,
    EventCreateSerializer,
    EventReasonSerializer,
    EventUpdateSerializer,
    SlotsSerializer,
)

MANAGE = policies.admin_permission("events.manage")
# The attendee list holds names and email addresses, so reading it needs a fresh MFA check.
ATTENDEES = policies.admin_permission("events.manage", step_up=True)
IF_MATCH = OpenApiParameter("If-Match", str, OpenApiParameter.HEADER, required=True)
ERRORS = {
    401: OpenApiResponse(description="Not authenticated"),
    403: OpenApiResponse(description="Not allowed, or MFA missing"),
    404: OpenApiResponse(description="Not found"),
}


def _one(request: Request, event: Event, status_code: int = 200) -> Response:
    fresh = Event.objects.prefetch_related("slots").get(pk=event.pk)
    view = selectors.admin_views(_actor(request), [fresh], detail=True)[0]
    return etag.add_etag(Response(AdminEventSerializer(view).data, status=status_code), fresh)


class AdminEventsView(APIView):
    policy = MANAGE

    @extend_schema(
        summary="All events, any state",
        parameters=[AdminQuerySerializer],
        responses={200: AdminEventSerializer(many=True), **ERRORS},
        tags=["admin"],
    )
    def get(self, request: Request) -> Response:
        params = AdminQuerySerializer(data=request.query_params.dict())
        params.is_valid(raise_exception=True)
        filters = {k: v for k, v in params.validated_data.items() if k not in ("limit", "offset")}
        paginator = AdminLimitOffsetPagination()
        queryset = selectors.admin_queryset(**filters).prefetch_related("slots")
        page = paginator.paginate_queryset(queryset, request, view=self)
        views = selectors.admin_views(_actor(request), page or [], detail=True)
        return paginator.get_paginated_response(AdminEventSerializer(views, many=True).data)

    @extend_schema(
        summary="Create an event",
        description="Starts as a draft. Times are sent with an offset and stored in UTC; "
        "`timezone` is the place's zone name (default UTC). `capacity` blank means unlimited.",
        request=EventCreateSerializer,
        responses={201: AdminEventSerializer, **ERRORS},
        tags=["admin"],
    )
    def post(self, request: Request) -> Response:
        serializer = EventCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        event = services.create_event(
            actor=_actor(request), data=dict(serializer.validated_data), ip=_ip(request)
        )
        return _one(request, event, 201)


class AdminEventView(APIView):
    policy = MANAGE

    @extend_schema(
        summary="One event", responses={200: AdminEventSerializer, **ERRORS}, tags=["admin"]
    )
    def get(self, request: Request, event_id: UUID) -> Response:
        event = Event.objects.exclude(status=Event.Status.REMOVED).filter(pk=event_id).first()
        if event is None:
            raise exceptions.NotFound()
        return _one(request, event)

    @extend_schema(
        summary="Edit an event",
        description="Changing the times of a published event tells everyone registered and "
        "resets their reminders. Capacity cannot drop below the number registered. After the "
        "event, add `recording_url` and `summary` for the archive.",
        parameters=[IF_MATCH],
        request=EventUpdateSerializer,
        responses={
            200: AdminEventSerializer,
            **ERRORS,
            409: OpenApiResponse(description="Cancelled"),
            412: OpenApiResponse(description="Changed since the ETag was issued"),
            428: OpenApiResponse(description="If-Match header missing"),
        },
        tags=["admin"],
    )
    def patch(self, request: Request, event_id: UUID) -> Response:
        serializer = EventUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        event = services.update_event(
            actor=_actor(request),
            event_id=event_id,
            data=dict(serializer.validated_data),
            if_match=request.headers.get("If-Match"),
            ip=_ip(request),
        )
        return _one(request, event)

    @extend_schema(summary="Remove an event", responses={204: None, **ERRORS}, tags=["admin"])
    def delete(self, request: Request, event_id: UUID) -> Response:
        services.remove(actor=_actor(request), event_id=event_id, ip=_ip(request))
        return Response(status=status.HTTP_204_NO_CONTENT)


class EventStateView(APIView):
    """Publish, unpublish or cancel an event (the URL names the action)."""

    policy = MANAGE
    action = ""

    @extend_schema(
        summary="Publish, unpublish or cancel an event",
        description="Publish needs a start in the future. Unpublish only while nobody has "
        "registered. Cancel tells everyone registered and closes registration.",
        request=EventReasonSerializer,
        responses={
            200: AdminEventSerializer,
            **ERRORS,
            409: OpenApiResponse(description="Not in a state that allows this"),
        },
        tags=["admin"],
    )
    def post(self, request: Request, event_id: UUID) -> Response:
        serializer = EventReasonSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        actor, ip = _actor(request), _ip(request)
        if self.action == "cancel":
            event = services.cancel(
                actor=actor, event_id=event_id, reason=serializer.validated_data["reason"], ip=ip
            )
        elif self.action == "publish":
            event = services.publish(actor=actor, event_id=event_id, ip=ip)
        else:
            event = services.unpublish(actor=actor, event_id=event_id, ip=ip)
        return _one(request, event)


def state_view(action: str) -> type[EventStateView]:
    return type(f"{action.title()}EventView", (EventStateView,), {"action": action})


class EventSlotsView(APIView):
    policy = MANAGE

    @extend_schema(
        summary="Set the demo day's presenting startups and pitch order",
        description="Replaces the whole list; the order sent is the pitch order. Demo days only.",
        request=SlotsSerializer,
        responses={
            200: AdminEventSerializer,
            **ERRORS,
            409: OpenApiResponse(description="Not a demo day"),
        },
        tags=["admin"],
    )
    def put(self, request: Request, event_id: UUID) -> Response:
        serializer = SlotsSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        event = services.set_slots(
            actor=_actor(request),
            event_id=event_id,
            slots=[dict(s) for s in serializer.validated_data["slots"]],
            ip=_ip(request),
        )
        return _one(request, event)


class AttendeesView(APIView):
    policy = ATTENDEES

    @extend_schema(
        summary="Who registered",
        description="Names and email addresses, so it needs a recent MFA check. Reading is logged.",
        parameters=[AttendeeQuerySerializer],
        responses={200: AttendeeSerializer(many=True), **ERRORS},
        tags=["admin"],
    )
    def get(self, request: Request, event_id: UUID) -> Response:
        if not Event.objects.exclude(status=Event.Status.REMOVED).filter(pk=event_id).exists():
            raise exceptions.NotFound()
        params = AttendeeQuerySerializer(data=request.query_params.dict())
        params.is_valid(raise_exception=True)
        paginator = AdminLimitOffsetPagination()
        page = paginator.paginate_queryset(selectors.attendees(event_id), request, view=self)
        audit.record(
            actor=_actor(request),
            action="events.attendees_viewed",
            target_type="event",
            target_id=event_id,
            ip=_ip(request),
        )
        data = AttendeeSerializer(
            selectors.attendee_views(_actor(request), page or []), many=True
        ).data
        return paginator.get_paginated_response(data)


class AttendeesExportView(APIView):
    policy = ATTENDEES

    @extend_schema(
        summary="Export the attendee list as CSV",
        responses={(200, "text/csv"): OpenApiResponse(description="CSV file"), **ERRORS},
        tags=["admin"],
    )
    def get(self, request: Request, event_id: UUID) -> HttpResponse:
        event = Event.objects.exclude(status=Event.Status.REMOVED).filter(pk=event_id).first()
        if event is None:
            raise exceptions.NotFound()
        audit.record(
            actor=_actor(request),
            action="events.attendees_exported",
            target_type="event",
            target_id=event_id,
            ip=_ip(request),
        )
        response = HttpResponse(
            selectors.attendees_csv(_actor(request), event_id),
            content_type="text/csv; charset=utf-8",
        )
        response["Content-Disposition"] = f'attachment; filename="{event.slug}-attendees.csv"'
        response["Cache-Control"] = "private, no-store"
        return response


class CheckInView(APIView):
    policy = MANAGE

    @extend_schema(
        summary="Mark an attendee as present (or not)",
        request=CheckInSerializer,
        responses={204: None, **ERRORS},
        tags=["admin"],
    )
    def post(self, request: Request, event_id: UUID, user_id: UUID) -> Response:
        serializer = CheckInSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        services.check_in(
            actor=_actor(request),
            event_id=event_id,
            user_id=user_id,
            present=serializer.validated_data["present"],
            ip=_ip(request),
        )
        return Response(status=status.HTTP_204_NO_CONTENT)
