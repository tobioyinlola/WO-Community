from uuid import UUID

from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import exceptions
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.adminconsole.views import _actor, _ip
from apps.core import policies
from apps.core.pagination import AdminLimitOffsetPagination
from apps.mentorship import applications, booking, mentors, selectors, session_selectors
from apps.mentorship.models import MentorApplication, MentorProfile, MentorSession
from apps.mentorship.serializers import (
    AdminMentorApplicationSerializer,
    AdminMentorSerializer,
    AdminQuerySerializer,
    DecisionSerializer,
    MentorNoteSerializer,
    MentorReasonSerializer,
)
from apps.mentorship.session_serializers import (
    AdminMentoringSessionSerializer,
    AdminSessionQuerySerializer,
)

DECIDE = policies.admin_permission("mentors.decide")
ERRORS = {
    401: OpenApiResponse(description="Not authenticated"),
    403: OpenApiResponse(description="Not allowed, or MFA missing"),
    404: OpenApiResponse(description="Not found"),
}


def _filters(request: Request) -> dict[str, str]:
    params = AdminQuerySerializer(data=request.query_params.dict())
    params.is_valid(raise_exception=True)
    return {k: v for k, v in params.validated_data.items() if k in ("status", "q")}


class AdminMentorApplicationsView(APIView):
    policy = DECIDE
    pagination_class = AdminLimitOffsetPagination  # documents the page shape

    @extend_schema(
        summary="Mentor applications",
        description="Oldest first, so the queue is worked in order. Filter by `status` "
        "(`pending` is the queue, `info_requested` are waiting for the applicant) and applicant "
        "name.",
        parameters=[AdminQuerySerializer],
        responses={200: AdminMentorApplicationSerializer(many=True), **ERRORS},
        tags=["admin"],
    )
    def get(self, request: Request) -> Response:
        paginator = AdminLimitOffsetPagination()
        page = paginator.paginate_queryset(
            selectors.admin_applications(**_filters(request)), request, view=self
        )
        views = selectors.admin_application_views(_actor(request), page or [])
        return paginator.get_paginated_response(
            AdminMentorApplicationSerializer(views, many=True).data
        )


class AdminMentorApplicationView(APIView):
    policy = DECIDE

    @extend_schema(
        summary="One mentor application",
        responses={200: AdminMentorApplicationSerializer, **ERRORS},
        tags=["admin"],
    )
    def get(self, request: Request, application_id: UUID) -> Response:
        application = MentorApplication.objects.filter(pk=application_id).first()
        if application is None:
            raise exceptions.NotFound()
        view = selectors.admin_application_views(_actor(request), [application])[0]
        return Response(AdminMentorApplicationSerializer(view).data)


class AdminMentorDecisionView(APIView):
    policy = DECIDE

    @extend_schema(
        summary="Approve, decline or ask for more information",
        description="`decline` and `request_info` need a `reason`, which the applicant is "
        "shown. Approving gives the member the mentor role, badge and mentor section.",
        request=DecisionSerializer,
        responses={
            200: AdminMentorApplicationSerializer,
            **ERRORS,
            409: OpenApiResponse(description="Already decided"),
        },
        tags=["admin"],
    )
    def post(self, request: Request, application_id: UUID) -> Response:
        serializer = DecisionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        application = applications.decide(
            actor=_actor(request),
            application_id=application_id,
            ip=_ip(request),
            **serializer.validated_data,
        )
        view = selectors.admin_application_views(_actor(request), [application])[0]
        return Response(AdminMentorApplicationSerializer(view).data)


class AdminMentorsView(APIView):
    policy = DECIDE
    pagination_class = AdminLimitOffsetPagination  # documents the page shape

    @extend_schema(
        summary="Mentors",
        description="Filter by `status` (`active`, `pending` or `revoked`) and name.",
        parameters=[AdminQuerySerializer],
        responses={200: AdminMentorSerializer(many=True), **ERRORS},
        tags=["admin"],
    )
    def get(self, request: Request) -> Response:
        paginator = AdminLimitOffsetPagination()
        page = paginator.paginate_queryset(
            selectors.admin_mentors(**_filters(request)), request, view=self
        )
        views = selectors.admin_mentor_views(_actor(request), page or [])
        return paginator.get_paginated_response(AdminMentorSerializer(views, many=True).data)


class AdminMentorRevokeView(APIView):
    policy = policies.admin_permission("mentors.decide", step_up=True)

    @extend_schema(
        summary="Revoke mentor status",
        description="Removes the role, badge and listing. Needs a reason and a recent MFA check.",
        request=MentorReasonSerializer,
        responses={200: AdminMentorSerializer, **ERRORS},
        tags=["admin"],
    )
    def post(self, request: Request, user_id: UUID) -> Response:
        serializer = MentorReasonSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        profile = mentors.revoke(
            actor=_actor(request),
            user_id=user_id,
            reason=serializer.validated_data["reason"],
            ip=_ip(request),
        )
        return _mentor(request, profile)


class AdminMentorPendingView(APIView):
    policy = DECIDE

    @extend_schema(
        summary="Move an approved mentor to pending",
        description="Takes the mentor off the platform's mentor list and cancels open sessions. "
        "The note is optional. Approve them again with the restore action.",
        request=MentorNoteSerializer,
        responses={200: AdminMentorSerializer, **ERRORS},
        tags=["admin"],
    )
    def post(self, request: Request, user_id: UUID) -> Response:
        serializer = MentorNoteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        profile = mentors.set_pending(
            actor=_actor(request),
            user_id=user_id,
            reason=serializer.validated_data.get("reason", ""),
            ip=_ip(request),
        )
        return _mentor(request, profile)


class AdminMentorRestoreView(APIView):
    policy = DECIDE

    @extend_schema(
        summary="Approve a pending or revoked mentor again",
        request=None,
        responses={200: AdminMentorSerializer, **ERRORS},
        tags=["admin"],
    )
    def post(self, request: Request, user_id: UUID) -> Response:
        profile = mentors.restore(actor=_actor(request), user_id=user_id, ip=_ip(request))
        return _mentor(request, profile)


def _mentor(request: Request, profile: MentorProfile) -> Response:
    view = selectors.admin_mentor_views(_actor(request), [profile])[0]
    return Response(AdminMentorSerializer(view).data)


MANAGE_SESSIONS = policies.admin_permission("sessions.manage")


class AdminSessionsView(APIView):
    policy = MANAGE_SESSIONS
    pagination_class = AdminLimitOffsetPagination  # documents the page shape

    @extend_schema(
        summary="Mentoring sessions",
        description="Newest first. Filter by `status`, `mentor_id` and `mentee_id`. Shows both "
        "sides' feedback and each person's email, so it is for support and moderation.",
        parameters=[AdminSessionQuerySerializer],
        responses={200: AdminMentoringSessionSerializer(many=True), **ERRORS},
        tags=["admin"],
    )
    def get(self, request: Request) -> Response:
        params = AdminSessionQuerySerializer(data=request.query_params.dict())
        params.is_valid(raise_exception=True)
        keep = ("status", "mentor_id", "mentee_id")
        filters = {k: v for k, v in params.validated_data.items() if k in keep}
        paginator = AdminLimitOffsetPagination()
        page = paginator.paginate_queryset(
            session_selectors.admin_sessions(**filters), request, view=self
        )
        views = session_selectors.admin_views(_actor(request), page or [])
        return paginator.get_paginated_response(
            AdminMentoringSessionSerializer(views, many=True).data
        )


class AdminSessionView(APIView):
    policy = MANAGE_SESSIONS

    @extend_schema(
        summary="One mentoring session",
        responses={200: AdminMentoringSessionSerializer, **ERRORS},
        tags=["admin"],
    )
    def get(self, request: Request, session_id: UUID) -> Response:
        session = MentorSession.objects.filter(pk=session_id).first()
        if session is None:
            raise exceptions.NotFound()
        view = session_selectors.admin_views(_actor(request), [session])[0]
        return Response(AdminMentoringSessionSerializer(view).data)


class AdminSessionCancelView(APIView):
    policy = MANAGE_SESSIONS

    @extend_schema(
        summary="Cancel a session",
        description="For support cases. Both people are told, with the reason. Audited.",
        request=MentorReasonSerializer,
        responses={
            200: AdminMentoringSessionSerializer,
            **ERRORS,
            409: OpenApiResponse(description="Already closed"),
        },
        tags=["admin"],
    )
    def post(self, request: Request, session_id: UUID) -> Response:
        serializer = MentorReasonSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        session = booking.cancel_by_admin(
            actor=_actor(request),
            session_id=session_id,
            reason=serializer.validated_data["reason"],
            ip=_ip(request),
        )
        view = session_selectors.admin_views(_actor(request), [session])[0]
        return Response(AdminMentoringSessionSerializer(view).data)
