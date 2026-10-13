from typing import Any, cast
from uuid import UUID

from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core import policies
from apps.core.errors import PROBLEM_CONTENT_TYPE
from apps.mentorship import selectors, setup
from apps.mentorship.models import MentorProfile
from apps.mentorship.setup_serializers import (
    AcknowledgeSerializer,
    ExceptionCreateSerializer,
    MentorSetupSerializer,
    MentorSetupUpdateSerializer,
    ScheduleConflictSerializer,
    SlotsQuerySerializer,
    SlotsSerializer,
    WeeklySerializer,
    WeeklyUpdateSerializer,
)

ERRORS = {
    401: OpenApiResponse(description="Not authenticated"),
    403: OpenApiResponse(description="Not an approved mentor"),
    404: OpenApiResponse(description="Not found"),
}
CONFLICT = {
    409: OpenApiResponse(
        response=ScheduleConflictSerializer,
        description="Agreed sessions would fall outside the schedule. They are listed in "
        "`sessions`; send `acknowledge: true` to keep them and apply the change anyway.",
    )
}


def _uid(request: Request) -> UUID:
    return cast(UUID, request.user.pk)


def _private(response: Response) -> Response:
    response["Cache-Control"] = "private, no-store"
    return response


def _conflict(exc: setup.ScheduleConflict) -> Response:
    body = ScheduleConflictSerializer(
        {
            "status": status.HTTP_409_CONFLICT,
            "code": "schedule_conflict",
            "title": "Conflict",
            "detail": str(exc.detail),
            "sessions": exc.sessions,
        }
    ).data
    response = Response(body, status=status.HTTP_409_CONFLICT)
    response.content_type = PROBLEM_CONTENT_TYPE
    return response


def _own_setup(request: Request) -> Response:
    return _private(Response(MentorSetupSerializer(setup.settings_view(_uid(request))).data))


class MyMentorSettingsView(APIView):
    policy = policies.active_member

    @extend_schema(
        summary="Your mentoring settings",
        description="Everything the Mentorship section of Settings edits: the weekly schedule, "
        "days off, session lengths, buffer, notice, weekly limit, booking window, pricing, "
        "meeting provider and mentoring profile. Only approved mentors.",
        responses={200: MentorSetupSerializer, **ERRORS},
        tags=["mentorship"],
    )
    def get(self, request: Request) -> Response:
        return _own_setup(request)

    @extend_schema(
        summary="Change your mentoring settings",
        description="Send only what changed. Prices are in the smallest unit. While online "
        "payment is off a paid session is a request you confirm and payment is arranged "
        "directly. Accepting mentees needs at least one weekly time range.",
        request=MentorSetupUpdateSerializer,
        responses={200: MentorSetupSerializer, **CONFLICT, **ERRORS},
        tags=["mentorship"],
    )
    def put(self, request: Request) -> Response:
        serializer = MentorSetupUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = dict(serializer.validated_data)
        acknowledge = data.pop("acknowledge", False)
        try:
            setup.save_settings(user_id=_uid(request), data=data, acknowledge=acknowledge)
        except setup.ScheduleConflict as exc:
            return _conflict(exc)
        return _own_setup(request)


def _weekly_body(user_id: UUID) -> dict[str, Any]:
    view = setup.settings_view(user_id)
    return {k: view[k] for k in ("timezone", "weekly", "exceptions")}


class MyMentorAvailabilityView(APIView):
    policy = policies.active_member

    @extend_schema(
        summary="Your weekly availability and days off",
        responses={200: WeeklySerializer, **ERRORS},
        tags=["mentorship"],
    )
    def get(self, request: Request) -> Response:
        return _private(Response(WeeklySerializer(_weekly_body(_uid(request))).data))

    @extend_schema(
        summary="Replace your weekly availability",
        description="Sends every weekly range (weekday 0 is Monday, HH:MM in your time zone). "
        "Days off and extra one off time are kept. Ranges must not overlap, each must fit one "
        "session, and accepting mentees needs at least one.",
        request=WeeklyUpdateSerializer,
        responses={200: WeeklySerializer, **CONFLICT, **ERRORS},
        tags=["mentorship"],
    )
    def put(self, request: Request) -> Response:
        serializer = WeeklyUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        try:
            setup.save_weekly(
                user_id=_uid(request),
                weekly=[dict(w) for w in data["weekly"]],
                tz=data.get("timezone"),
                acknowledge=data["acknowledge"],
            )
        except setup.ScheduleConflict as exc:
            return _conflict(exc)
        return _private(Response(WeeklySerializer(_weekly_body(_uid(request))).data))


class MyMentorExceptionsView(APIView):
    policy = policies.active_member

    @extend_schema(
        summary="Block days off, or add extra time on one date",
        description="`type` `blocked` takes `starts_on` and `ends_on` (dates in your time zone). "
        "`type` `extra` takes `date`, `start` and `end`. Existing bookings are never removed.",
        request=ExceptionCreateSerializer,
        responses={201: WeeklySerializer, **CONFLICT, **ERRORS},
        tags=["mentorship"],
    )
    def post(self, request: Request) -> Response:
        serializer = ExceptionCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = dict(serializer.validated_data)
        acknowledge = data.pop("acknowledge", False)
        try:
            setup.add_exception(user_id=_uid(request), data=data, acknowledge=acknowledge)
        except setup.ScheduleConflict as exc:
            return _conflict(exc)
        return _private(
            Response(
                WeeklySerializer(_weekly_body(_uid(request))).data, status=status.HTTP_201_CREATED
            )
        )


class MyMentorExceptionView(APIView):
    policy = policies.active_member

    @extend_schema(
        summary="Remove a day off or extra time",
        description="Removing extra time can leave agreed sessions outside your schedule: send "
        "`acknowledge=true` to keep them and remove it anyway.",
        parameters=[AcknowledgeSerializer],
        responses={200: WeeklySerializer, **CONFLICT, **ERRORS},
        tags=["mentorship"],
    )
    def delete(self, request: Request, item_id: UUID) -> Response:
        serializer = AcknowledgeSerializer(data=request.query_params.dict())
        serializer.is_valid(raise_exception=True)
        try:
            setup.remove_exception(
                user_id=_uid(request),
                item_id=item_id,
                acknowledge=serializer.validated_data["acknowledge"],
            )
        except setup.ScheduleConflict as exc:
            return _conflict(exc)
        return _private(Response(WeeklySerializer(_weekly_body(_uid(request))).data))


def _slots(request: Request, profile: MentorProfile) -> Response:
    query = SlotsQuerySerializer(data=request.query_params.dict())
    query.is_valid(raise_exception=True)
    data = query.validated_data
    body = setup.slots_for(
        profile,
        start=data.get("from"),
        end=data.get("to"),
        length=data.get("length"),
        tz=data["tz"],
    )
    return _private(Response(SlotsSerializer(body).data))


class MentorSlotsView(APIView):
    policy = policies.active_member

    @extend_schema(
        summary="Times a mentor can be booked, in your time zone",
        description="Slots for one session length between `from` and `to` (dates, at most 31 "
        "days), computed from the weekly schedule less days off, the buffer, minimum notice, "
        "booking window, the weekly limit, existing sessions and the mentor's calendar. `tz` is "
        "an IANA zone for the local date and time of each slot. Includes the price, if any.",
        parameters=[SlotsQuerySerializer],
        responses={200: SlotsSerializer, **ERRORS},
        tags=["mentorship"],
    )
    def get(self, request: Request, user_id: UUID) -> Response:
        selectors.detail(request.user, user_id)  # 404 unless listed (or your own)
        return _slots(request, MentorProfile.objects.get(user_id=user_id))


class MyMentorPreviewView(APIView):
    policy = policies.active_member

    @extend_schema(
        summary="Preview your booking calendar as a mentee sees it",
        description="The same slots a mentee gets, even while you are not accepting mentees, "
        "so you can check the schedule before turning it on. `accepting_new` says whether "
        "mentees can book now.",
        parameters=[SlotsQuerySerializer],
        responses={200: SlotsSerializer, **ERRORS},
        tags=["mentorship"],
    )
    def get(self, request: Request) -> Response:
        profile = setup.profile_of(_uid(request))
        if not profile.paused:
            return _slots(request, profile)
        # While paused, a mentee sees nothing; the preview shows what they would see once on.
        profile.paused = False
        response = _slots(request, profile)
        response.data["accepting_new"] = False
        return response
