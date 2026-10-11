from uuid import UUID

from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import exceptions
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.adminconsole.views import _actor, _ip
from apps.core import policies
from apps.core.pagination import AdminLimitOffsetPagination
from apps.mentorship import applications, mentors, selectors
from apps.mentorship.models import MentorApplication, MentorProfile
from apps.mentorship.serializers import (
    AdminMentorApplicationSerializer,
    AdminMentorSerializer,
    AdminQuerySerializer,
    DecisionSerializer,
    MentorReasonSerializer,
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

    @extend_schema(
        summary="Mentors",
        description="Filter by `status` (`active` or `revoked`) and name.",
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


class AdminMentorRestoreView(APIView):
    policy = DECIDE

    @extend_schema(
        summary="Restore a revoked mentor",
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
