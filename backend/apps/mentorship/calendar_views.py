from typing import cast
from uuid import UUID

from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import serializers, status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core import policies
from apps.core.serializers import StrictSerializer
from apps.mentorship import calendar_sync

ERRORS = {
    401: OpenApiResponse(description="Not authenticated"),
    403: OpenApiResponse(description="Not an active mentor"),
    404: OpenApiResponse(description="No calendar is shared"),
    429: OpenApiResponse(description="Too many attempts"),
}


def _uid(request: Request) -> UUID:
    return cast(UUID, request.user.pk)


def _private(response: Response) -> Response:
    response["Cache-Control"] = "private, no-store"
    return response


class CalendarStatusSerializer(serializers.Serializer):
    connected = serializers.BooleanField()
    host = serializers.CharField(
        allow_blank=True, help_text="Where the calendar lives; never the address."
    )
    include_all_day = serializers.BooleanField()
    status = serializers.ChoiceField(choices=["active", "error"], allow_null=True)
    last_synced_at = serializers.DateTimeField(allow_null=True)
    last_error = serializers.CharField(allow_blank=True)
    stale = serializers.BooleanField(
        help_text="Not read recently; its busy time may be out of date."
    )
    busy_ranges = serializers.IntegerField(help_text="Busy ranges still ahead.")


class CalendarConnectSerializer(StrictSerializer):
    feed_url = serializers.CharField(
        max_length=calendar_sync.MAX_URL,
        required=False,
        help_text="The private iCal address of your calendar (https:// or webcal://).",
    )
    include_all_day = serializers.BooleanField(
        required=False, help_text="Also treat all-day events as busy. Off by default."
    )


class RangeSerializer(serializers.Serializer):
    starts_at = serializers.DateTimeField()
    ends_at = serializers.DateTimeField()


class AvailabilityPreviewSerializer(serializers.Serializer):
    timezone = serializers.CharField()
    session_minutes = serializers.IntegerField()
    windows = RangeSerializer(many=True, help_text="Your own availability windows.")
    calendar_busy = RangeSerializer(many=True, help_text="Busy time from your shared calendar.")
    booked = RangeSerializer(many=True, help_text="Requested and confirmed sessions.")
    free = RangeSerializer(many=True, help_text="Windows minus busy and booked time.")
    bookable_starts = serializers.ListField(
        child=serializers.DateTimeField(), help_text="The start times founders are offered."
    )
    calendar = CalendarStatusSerializer()


class PreviewQuerySerializer(serializers.Serializer):
    days = serializers.IntegerField(min_value=1, max_value=30, default=14)


class MyCalendarView(APIView):
    policy = policies.active_member

    @extend_schema(
        summary="Your shared calendar",
        description="Whether a calendar is shared, where it lives and when it was last read. "
        "The address itself is never returned.",
        responses={200: CalendarStatusSerializer, **ERRORS},
        tags=["mentorship"],
    )
    def get(self, request: Request) -> Response:
        calendar_sync.require_mentor(_uid(request))
        return _private(
            Response(CalendarStatusSerializer(calendar_sync.status_of(_uid(request))).data)
        )

    @extend_schema(
        summary="Share a calendar so busy time is not offered",
        description="Paste the private iCal address your calendar gives you (in Google Calendar: "
        "settings, your calendar, 'Secret address in iCal format'; Outlook and Apple have the "
        "same). It is read once now, so a wrong address is refused with the reason, then every "
        "15 minutes. Only the times you are busy are kept, never titles or guests. Events marked "
        "free, cancelled events and (by default) all-day events do not block time. Send only "
        "`include_all_day` to change that for the calendar already shared.",
        request=CalendarConnectSerializer,
        responses={200: CalendarStatusSerializer, **ERRORS},
        tags=["mentorship"],
    )
    def put(self, request: Request) -> Response:
        serializer = CalendarConnectSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        body = calendar_sync.connect(
            user_id=_uid(request),
            feed_url=data.get("feed_url"),
            include_all_day=data.get("include_all_day"),
        )
        return _private(Response(CalendarStatusSerializer(body).data))

    @extend_schema(
        summary="Stop sharing your calendar",
        description="Forgets the address and every stored busy range.",
        responses={204: None, **ERRORS},
        tags=["mentorship"],
    )
    def delete(self, request: Request) -> Response:
        calendar_sync.require_mentor(_uid(request))
        calendar_sync.disconnect(user_id=_uid(request))
        return Response(status=status.HTTP_204_NO_CONTENT)


class CalendarRefreshView(APIView):
    policy = policies.active_member

    @extend_schema(
        summary="Read your calendar now",
        description="Normally it is read every 15 minutes. At most once a minute.",
        request=None,
        responses={200: CalendarStatusSerializer, **ERRORS},
        tags=["mentorship"],
    )
    def post(self, request: Request) -> Response:
        body = calendar_sync.refresh(user_id=_uid(request))
        return _private(Response(CalendarStatusSerializer(body).data))


class AvailabilityPreviewView(APIView):
    policy = policies.active_member

    @extend_schema(
        summary="Preview the times you are offering",
        description="For the next `days` (default 14): your windows, the busy time and booked "
        "sessions that remove from them, what is left free and the start times founders see. "
        "Use it beside `PUT /me/availability` to choose your available time.",
        parameters=[PreviewQuerySerializer],
        responses={200: AvailabilityPreviewSerializer, **ERRORS},
        tags=["mentorship"],
    )
    def get(self, request: Request) -> Response:
        query = PreviewQuerySerializer(data=request.query_params.dict())
        query.is_valid(raise_exception=True)
        body = calendar_sync.preview(_uid(request), days=query.validated_data["days"])
        return _private(Response(AvailabilityPreviewSerializer(body).data))
