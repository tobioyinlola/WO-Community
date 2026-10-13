from typing import Any, cast
from uuid import UUID

from django.conf import settings
from django.http import HttpResponse
from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core import policies
from apps.core.public import PublicView
from apps.events import selectors, services
from apps.events.serializers import (
    EventPageSerializer,
    EventSerializer,
    ListQuerySerializer,
    PublicEventPageSerializer,
    PublicEventSerializer,
    PublicQuerySerializer,
    RegistrationResultSerializer,
)

ERRORS = {
    401: OpenApiResponse(description="Not authenticated"),
    403: OpenApiResponse(description="Not an active member"),
    404: OpenApiResponse(description="Not found, or not published"),
}


def _uid(request: Request) -> UUID:
    return cast(UUID, request.user.pk)


def _params(request: Request, serializer_class: Any) -> dict[str, Any]:
    serializer = serializer_class(data=request.query_params)
    serializer.is_valid(raise_exception=True)
    return dict(serializer.validated_data)


def _private(response: Response) -> Response:
    response["Cache-Control"] = "private, no-store"
    return response


class EventsView(APIView):
    policy = policies.active_member

    @extend_schema(
        operation_id="events_list",
        summary="Events, demo days, workshops and meetups",
        description="`when=upcoming` (default) soonest first, or `past` for the archive, latest "
        "first. `registered=true` shows only those you registered for.",
        parameters=[ListQuerySerializer],
        responses={200: EventPageSerializer, **ERRORS},
        tags=["events"],
    )
    def get(self, request: Request) -> Response:
        page = selectors.listing(request.user, **_params(request, ListQuerySerializer))
        return _private(Response(EventPageSerializer(page).data))


class EventView(APIView):
    policy = policies.active_member

    @extend_schema(
        summary="One event",
        description="Includes the join link, the demo day pitch order and, once it is over, the "
        "recording and summary. A cancelled event stays visible with its status.",
        responses={200: EventSerializer, **ERRORS},
        tags=["events"],
    )
    def get(self, request: Request, event_id: UUID) -> Response:
        _, view = selectors.get_event(request.user, event_id)
        return _private(Response(EventSerializer(view).data))


def _result(request: Request, event_id: UUID, registered: bool, status_code: int) -> Response:
    _, view = selectors.get_event(request.user, event_id)
    body = {
        "event_id": event_id,
        "registered": registered,
        "registered_count": view["registered_count"],
        "spots_left": view["spots_left"],
    }
    return Response(RegistrationResultSerializer(body).data, status=status_code)


class RegisterView(APIView):
    policy = policies.active_member

    @extend_schema(
        summary="Register for an event",
        description="Idempotent: registering again answers 200. Refused with 409 when "
        "registration is closed, the event is full or it has started. You get a confirmation "
        "and reminders 24 hours and 1 hour before.",
        request=None,
        responses={
            201: RegistrationResultSerializer,
            200: RegistrationResultSerializer,
            **ERRORS,
            409: OpenApiResponse(description="Closed, full or already started"),
        },
        tags=["events"],
    )
    def post(self, request: Request, event_id: UUID) -> Response:
        created = services.register(user_id=_uid(request), event_id=event_id)
        return _result(request, event_id, True, 201 if created else 200)

    @extend_schema(
        summary="Cancel your registration",
        description="Idempotent. Not possible once the event has started.",
        responses={
            200: RegistrationResultSerializer,
            **ERRORS,
            409: OpenApiResponse(description="Already started"),
        },
        tags=["events"],
    )
    def delete(self, request: Request, event_id: UUID) -> Response:
        services.unregister(user_id=_uid(request), event_id=event_id)
        return _result(request, event_id, False, status.HTTP_200_OK)


class CalendarView(APIView):
    policy = policies.active_member

    @extend_schema(
        summary="Add the event to your calendar",
        description="An iCalendar (.ics) file.",
        responses={(200, "text/calendar"): OpenApiResponse(description="iCalendar file"), **ERRORS},
        tags=["events"],
    )
    def get(self, request: Request, event_id: UUID) -> HttpResponse:
        event, _ = selectors.get_event(request.user, event_id)
        response = HttpResponse(
            services.calendar_file(event, settings.FRONTEND_BASE_URL),
            content_type="text/calendar; charset=utf-8",
        )
        response["Content-Disposition"] = f'attachment; filename="{event.slug}.ics"'
        response["Cache-Control"] = "private, no-store"
        return response


# --- public ---


class PublicEventsView(PublicView):
    @extend_schema(
        operation_id="public_events_list",
        summary="Public events",
        parameters=[PublicQuerySerializer],
        responses={200: PublicEventPageSerializer, 400: OpenApiResponse(description="Bad filter")},
        tags=["public"],
    )
    def get(self, request: Request) -> Response:
        page = selectors.public_listing(**_params(request, PublicQuerySerializer))
        return self.cached(request, PublicEventPageSerializer(page).data)


class PublicEventView(PublicView):
    @extend_schema(
        summary="One public event, with Open Graph data",
        responses={200: PublicEventSerializer, 404: OpenApiResponse(description="Not found")},
        tags=["public"],
    )
    def get(self, request: Request, slug: str) -> Response:
        return self.cached(request, PublicEventSerializer(selectors.public_detail(slug)).data)
