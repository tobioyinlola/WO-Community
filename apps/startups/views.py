from typing import Any, cast
from uuid import UUID

from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, extend_schema
from rest_framework import exceptions, status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core import etag, policies
from apps.core.visibility import Audience
from apps.startups import selectors, services
from apps.startups.serializers import (
    StartupCreateSerializer,
    StartupSerializer,
    StartupUpdateSerializer,
    TeamAddSerializer,
    TeamMemberSerializer,
    TractionReplaceSerializer,
    VisibilityUpdateSerializer,
)


def _uid(request: Request) -> UUID:
    return cast(UUID, request.user.pk)


IF_MATCH = OpenApiParameter("If-Match", str, OpenApiParameter.HEADER, required=True)
ERRORS = {
    401: OpenApiResponse(description="Not authenticated"),
    403: OpenApiResponse(description="Not allowed to do this on this startup"),
    404: OpenApiResponse(description="No such startup, or not visible to you"),
    412: OpenApiResponse(description="The startup changed since the ETag was issued"),
    428: OpenApiResponse(description="If-Match header missing"),
}


def _owner_response(startup_id: UUID, user_id: UUID, *, created: bool = False) -> Response:
    """The startup as its owner sees it, with a fresh ETag."""
    found = selectors.get_startup(startup_id)
    view = selectors.project_startup(found, Audience.OWNER) if found else None
    if found is None or view is None:
        raise exceptions.NotFound()
    response = Response(StartupSerializer(view).data, status=201 if created else 200)
    return etag.add_etag(response, found)


class StartupCreateView(APIView):
    policy = policies.active_member

    @extend_schema(
        summary="Create a startup",
        description="You become its owner and first founder.",
        request=StartupCreateSerializer,
        responses={201: StartupSerializer, **ERRORS},
        tags=["startups"],
    )
    def post(self, request: Request) -> Response:
        serializer = StartupCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        startup = services.create_startup(
            owner_id=_uid(request), data=dict(serializer.validated_data)
        )
        return _owner_response(startup.pk, _uid(request), created=True)


class MyStartupsView(APIView):
    policy = policies.authenticated

    @extend_schema(
        summary="Startups you own or are on the team of",
        responses={200: StartupSerializer(many=True), **ERRORS},
        tags=["startups"],
    )
    def get(self, request: Request) -> Response:
        views = [view for _, view in selectors.my_startups(_uid(request))]
        return Response(StartupSerializer(views, many=True).data)


class StartupDetailView(APIView):
    policy = policies.authenticated

    @extend_schema(
        summary="One startup, as the viewer may see it",
        description="The team sees everything. Other members see only the field groups and "
        "traction items marked members or public. A startup whose basics are hidden from you "
        "answers 404.",
        responses={200: StartupSerializer, **ERRORS},
        tags=["startups"],
    )
    def get(self, request: Request, startup_id: UUID) -> Response:
        found = selectors.startup_for_viewer(request.user, startup_id)
        if found is None:
            raise exceptions.NotFound()
        startup, view = found
        return etag.add_etag(Response(StartupSerializer(view).data), startup)

    @extend_schema(
        summary="Update a startup",
        description="Owner or a founder on the team. Only the owner can change "
        "`directory_opt_in`. Send the ETag from the last read in If-Match.",
        parameters=[IF_MATCH],
        request=StartupUpdateSerializer,
        responses={200: StartupSerializer, **ERRORS},
        tags=["startups"],
    )
    def patch(self, request: Request, startup_id: UUID) -> Response:
        serializer = StartupUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        services.update_startup(
            user_id=_uid(request),
            startup_id=startup_id,
            data=dict(serializer.validated_data),
            if_match=request.headers.get("If-Match"),
        )
        return _owner_response(startup_id, _uid(request))


class StartupVisibilityView(APIView):
    policy = policies.authenticated

    @extend_schema(
        summary="Change visibility of startup field groups",
        description="Groups: basics, description, website, team. Levels: private, members, "
        "public. Traction items carry their own level.",
        parameters=[IF_MATCH],
        request={
            "application/json": {"type": "object", "additionalProperties": {"type": "string"}}
        },
        responses={200: StartupSerializer, **ERRORS},
        tags=["startups"],
    )
    def patch(self, request: Request, startup_id: UUID) -> Response:
        serializer = VisibilityUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        services.set_visibility(
            user_id=_uid(request),
            startup_id=startup_id,
            levels=dict(serializer.validated_data),
            if_match=request.headers.get("If-Match"),
        )
        return _owner_response(startup_id, _uid(request))


class StartupTractionView(APIView):
    policy = policies.authenticated

    @extend_schema(
        summary="Replace the traction list",
        description="Send the complete list; anything not sent is removed. `users`, "
        "`revenue_range` and `funding_range` may appear once each.",
        parameters=[IF_MATCH],
        request=TractionReplaceSerializer,
        responses={200: StartupSerializer, **ERRORS},
        tags=["startups"],
    )
    def put(self, request: Request, startup_id: UUID) -> Response:
        serializer = TractionReplaceSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        services.replace_traction(
            user_id=_uid(request),
            startup_id=startup_id,
            items=[dict(item) for item in serializer.validated_data["metrics"]],
            if_match=request.headers.get("If-Match"),
        )
        return _owner_response(startup_id, _uid(request))


class StartupTeamView(APIView):
    policy = policies.authenticated

    @extend_schema(
        summary="Add a person to the team by email",
        description="The answer is the same whether or not the address belongs to a member. "
        "Someone who is not an active member yet is attached when they are approved.",
        request=TeamAddSerializer,
        responses={201: TeamMemberSerializer, **ERRORS},
        tags=["startups"],
    )
    def post(self, request: Request, startup_id: UUID) -> Response:
        serializer = TeamAddSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        member = services.add_team_member(
            owner_id=_uid(request), startup_id=startup_id, **serializer.validated_data
        )
        body: dict[str, Any] = {
            "id": member.pk,
            "email": member.invited_email,
            "title": member.title,
            "is_founder": member.is_founder,
        }
        return Response(TeamMemberSerializer(body).data, status=status.HTTP_201_CREATED)


class StartupTeamMemberView(APIView):
    policy = policies.authenticated

    @extend_schema(
        summary="Remove a team member",
        description="The owner can remove anyone except themselves. Members can remove themselves.",
        responses={204: None, **ERRORS},
        tags=["startups"],
    )
    def delete(self, request: Request, startup_id: UUID, member_id: UUID) -> Response:
        services.remove_team_member(
            actor_id=_uid(request), startup_id=startup_id, member_id=member_id
        )
        return Response(status=status.HTTP_204_NO_CONTENT)
