from typing import Any, cast
from uuid import UUID

from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import exceptions
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core import policies
from apps.mentorship import applications, availability, matching, mentors, scheduling, selectors
from apps.mentorship.models import MentorProfile
from apps.mentorship.serializers import (
    ApplicationCreateSerializer,
    ApplicationUpdateSerializer,
    BookableQuerySerializer,
    BookableTimesSerializer,
    MentorApplicationSerializer,
    MentoringSummarySerializer,
    MentorPageSerializer,
    MentorProfileUpdateSerializer,
    MentorQuerySerializer,
    MentorScheduleSerializer,
    MentorScheduleUpdateSerializer,
    MentorSerializer,
    NeedsSerializer,
    NeedsUpdateSerializer,
    RecommendationQuerySerializer,
    RecommendedMentorSerializer,
)

ERRORS = {
    401: OpenApiResponse(description="Not authenticated"),
    403: OpenApiResponse(description="Not an active member"),
    404: OpenApiResponse(description="Not found"),
}


def _uid(request: Request) -> UUID:
    return cast(UUID, request.user.pk)


def _private(response: Response) -> Response:
    response["Cache-Control"] = "private, no-store"
    return response


def _application(application: Any, status_code: int = 200) -> Response:
    return _private(
        Response(
            MentorApplicationSerializer(selectors.application_view(application)).data,
            status=status_code,
        )
    )


class MentorApplicationsView(APIView):
    policy = policies.active_member

    @extend_schema(
        summary="Apply to become a mentor",
        description="Needs acceptance of the mentor conduct policy (`accept_conduct`). One "
        "application can be open at a time; after a decline you can apply again 30 days later. "
        "Applying does not grant mentor status: an admin approves, declines with a reason, or "
        "asks for more information.",
        request=ApplicationCreateSerializer,
        responses={
            201: MentorApplicationSerializer,
            **ERRORS,
            409: OpenApiResponse(
                description="Already a mentor, already applied, or declined recently"
            ),
        },
        tags=["mentorship"],
    )
    def post(self, request: Request) -> Response:
        serializer = ApplicationCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        application = applications.apply(
            user_id=_uid(request), data=dict(serializer.validated_data)
        )
        return _application(application, 201)


class MyMentorApplicationView(APIView):
    policy = policies.active_member

    @extend_schema(
        summary="Your latest mentor application",
        description="Includes the decision and its reason, or what the admin asked you to add.",
        responses={200: MentorApplicationSerializer, **ERRORS},
        tags=["mentorship"],
    )
    def get(self, request: Request) -> Response:
        application = applications.latest_for(_uid(request))
        if application is None:
            raise exceptions.NotFound()
        return _application(application)


class MentorApplicationView(APIView):
    policy = policies.active_member

    @extend_schema(
        summary="Answer questions or change an open application",
        description="Changing an application that is waiting for information sends it back to "
        "review.",
        request=ApplicationUpdateSerializer,
        responses={200: MentorApplicationSerializer, **ERRORS},
        tags=["mentorship"],
    )
    def patch(self, request: Request, application_id: UUID) -> Response:
        serializer = ApplicationUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        application = applications.update(
            user_id=_uid(request),
            application_id=application_id,
            data=dict(serializer.validated_data),
        )
        return _application(application)

    @extend_schema(
        summary="Withdraw an open application",
        responses={200: MentorApplicationSerializer, **ERRORS},
        tags=["mentorship"],
    )
    def delete(self, request: Request, application_id: UUID) -> Response:
        return _application(
            applications.withdraw(user_id=_uid(request), application_id=application_id)
        )


class MentorsView(APIView):
    policy = policies.active_member

    @extend_schema(
        operation_id="mentors_list",
        summary="The mentor directory",
        description="Approved mentors who are not paused. Filter by text (name, role, company or "
        "an expertise tag), expertise, industry, stage, country and language. Contact details "
        "are never shown.",
        parameters=[MentorQuerySerializer],
        responses={200: MentorPageSerializer, **ERRORS},
        tags=["mentorship"],
    )
    def get(self, request: Request) -> Response:
        query = MentorQuerySerializer(data=request.query_params.dict())
        query.is_valid(raise_exception=True)
        return _private(
            Response(
                MentorPageSerializer(selectors.directory(request.user, **query.validated_data)).data
            )
        )


class MentorView(APIView):
    policy = policies.active_member

    @extend_schema(
        summary="One mentor",
        description="The mentor section of a member profile. 404 if the member is not a listed "
        "mentor.",
        responses={200: MentorSerializer, **ERRORS},
        tags=["mentorship"],
    )
    def get(self, request: Request, user_id: UUID) -> Response:
        data = selectors.detail(request.user, user_id)
        return _private(Response(MentorSerializer(data).data))


class MyMentorProfileView(APIView):
    policy = policies.active_member

    @extend_schema(
        summary="Your mentor section",
        responses={200: MentorSerializer, **ERRORS},
        tags=["mentorship"],
    )
    def get(self, request: Request) -> Response:
        data = selectors.own_view(request.user)
        if data is None:
            raise exceptions.NotFound()
        return _private(Response(MentorSerializer(data).data))

    @extend_schema(
        summary="Change your mentor section, or pause mentoring",
        description="`paused` hides you from the directory and recommendations without ending "
        "anything already agreed. A mentor who joined by invitation creates the section with "
        "their first save, which then needs every descriptive field.",
        request=MentorProfileUpdateSerializer,
        responses={200: MentorSerializer, **ERRORS},
        tags=["mentorship"],
    )
    def put(self, request: Request) -> Response:
        serializer = MentorProfileUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        mentors.save_profile(user_id=_uid(request), data=dict(serializer.validated_data))
        data = selectors.own_view(request.user)
        return _private(Response(MentorSerializer(data).data))


class MyMentoringView(APIView):
    policy = policies.active_member

    @extend_schema(
        summary="Your mentoring status",
        description="Whether you are a mentor, where your application stands, whether you can "
        "apply now, and whether to prompt you to apply because you ticked the mentor option "
        "when registering.",
        responses={200: MentoringSummarySerializer, **ERRORS},
        tags=["mentorship"],
    )
    def get(self, request: Request) -> Response:
        return _private(
            Response(MentoringSummarySerializer(selectors.mentoring_summary(_uid(request))).data)
        )


def _own_active_profile(request: Request) -> MentorProfile:
    profile = MentorProfile.objects.filter(
        user_id=_uid(request), status=MentorProfile.Status.ACTIVE
    ).first()
    if profile is None:
        raise exceptions.NotFound()
    return profile


class MyAvailabilityView(APIView):
    policy = policies.active_member

    @extend_schema(
        summary="Your availability",
        description="Weekly windows (in your time zone) and upcoming one off windows.",
        responses={200: MentorScheduleSerializer, **ERRORS},
        tags=["mentorship"],
    )
    def get(self, request: Request) -> Response:
        profile = _own_active_profile(request)
        return _private(Response(MentorScheduleSerializer(availability.schedule(profile)).data))

    @extend_schema(
        summary="Replace your availability",
        description="Sends the whole schedule: `weekly` windows (weekday 0 is Monday, HH:MM in "
        "your time zone) and `one_off` windows (future instants). Omitted lists are emptied. "
        "Windows must be at least one session long, at most 12 hours, and must not overlap.",
        request=MentorScheduleUpdateSerializer,
        responses={200: MentorScheduleSerializer, **ERRORS},
        tags=["mentorship"],
    )
    def put(self, request: Request) -> Response:
        serializer = MentorScheduleUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        profile = availability.replace(user_id=_uid(request), data=dict(serializer.validated_data))
        return _private(Response(MentorScheduleSerializer(availability.schedule(profile)).data))


class MentorAvailabilityView(APIView):
    policy = policies.active_member

    @extend_schema(
        summary="Times a mentor can be booked",
        description="Start times (UTC) for the next `days` (default 14, at most 30), soonest "
        "first, with already booked time and the minimum notice removed. Empty for a paused "
        "mentor or one with no sessions left this week.",
        parameters=[BookableQuerySerializer],
        responses={200: BookableTimesSerializer, **ERRORS},
        tags=["mentorship"],
    )
    def get(self, request: Request, user_id: UUID) -> Response:
        query = BookableQuerySerializer(data=request.query_params.dict())
        query.is_valid(raise_exception=True)
        selectors.detail(request.user, user_id)  # 404 unless listed (or your own)
        profile = MentorProfile.objects.get(user_id=user_id)
        left = scheduling.capacity_left(profile)
        times = (
            scheduling.bookable_starts(profile, days=query.validated_data["days"])
            if left and not profile.paused
            else []
        )
        body = {
            "timezone": profile.timezone,
            "session_minutes": profile.session_minutes,
            "times": times,
            "sessions_left_this_week": left,
        }
        return _private(Response(BookableTimesSerializer(body).data))


class RecommendedMentorsView(APIView):
    policy = policies.active_member

    @extend_schema(
        summary="Mentors recommended for you",
        description="Scored from what you need help with (saved needs, or `needs` here), your "
        "startup sector and stage, mentor availability, shared languages, mentor capacity and "
        "ratings. Each mentor carries a 0 to 100 `score` and the `reasons` behind it. Paused, "
        "revoked and fully booked mentors are left out. Results are cached for 15 minutes and "
        "refresh when mentor data changes.",
        parameters=[RecommendationQuerySerializer],
        responses={200: RecommendedMentorSerializer(many=True), **ERRORS},
        tags=["mentorship"],
    )
    def get(self, request: Request) -> Response:
        query = RecommendationQuerySerializer(data=request.query_params.dict())
        query.is_valid(raise_exception=True)
        raw = query.validated_data.get("needs", "")
        needs = [part for part in raw.split(",") if part.strip()] or None
        results = matching.recommend(request.user, needs=needs, limit=query.validated_data["limit"])
        return _private(Response(RecommendedMentorSerializer(results, many=True).data))


class MyNeedsView(APIView):
    policy = policies.active_member

    @extend_schema(
        summary="What you want mentoring on",
        responses={200: NeedsSerializer, **ERRORS},
        tags=["mentorship"],
    )
    def get(self, request: Request) -> Response:
        return _private(Response(NeedsSerializer(matching.saved(_uid(request))).data))

    @extend_schema(
        summary="Save what you want mentoring on",
        description="Up to 5 topics and the languages you can be mentored in. Recommendations "
        "use these unless you pass `needs`.",
        request=NeedsUpdateSerializer,
        responses={200: NeedsSerializer, **ERRORS},
        tags=["mentorship"],
    )
    def put(self, request: Request) -> Response:
        serializer = NeedsUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        saved = matching.save(_uid(request), data["needs"], data.get("languages", []))
        from apps.mentorship import cache

        cache.bump()
        return _private(Response(NeedsSerializer(saved).data))
