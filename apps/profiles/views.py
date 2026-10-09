from typing import cast
from uuid import UUID

from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, extend_schema
from rest_framework import exceptions
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core import etag, policies
from apps.profiles import selectors, services
from apps.profiles.serializers import (
    ProfileSerializer,
    ProfileUpdateSerializer,
    VisibilityUpdateSerializer,
)


def _uid(request: Request) -> UUID:
    return cast(UUID, request.user.pk)


IF_MATCH = OpenApiParameter("If-Match", str, OpenApiParameter.HEADER, required=True)
ERRORS = {
    401: OpenApiResponse(description="Not authenticated"),
    412: OpenApiResponse(description="The profile changed since the ETag was issued"),
    428: OpenApiResponse(description="If-Match header missing"),
}


class MyProfileView(APIView):
    policy = policies.authenticated

    @extend_schema(
        summary="Your own profile, with visibility settings and completeness",
        responses={200: ProfileSerializer, **ERRORS},
        tags=["profile"],
    )
    def get(self, request: Request) -> Response:
        profile, view = selectors.own_profile(_uid(request))
        return etag.add_etag(Response(ProfileSerializer(view).data), profile)

    @extend_schema(
        summary="Update your profile",
        description="Partial update. Send the ETag from the last read in If-Match.",
        parameters=[IF_MATCH],
        request=ProfileUpdateSerializer,
        responses={200: ProfileSerializer, **ERRORS},
        tags=["profile"],
    )
    def patch(self, request: Request) -> Response:
        serializer = ProfileUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        services.update_profile(
            user_id=_uid(request),
            data=dict(serializer.validated_data),
            if_match=request.headers.get("If-Match"),
        )
        profile, view = selectors.own_profile(_uid(request))
        return etag.add_etag(Response(ProfileSerializer(view).data), profile)


class MyVisibilityView(APIView):
    policy = policies.authenticated

    @extend_schema(
        summary="Visibility level of each profile field group",
        responses={200: {"type": "object", "additionalProperties": {"type": "string"}}, **ERRORS},
        tags=["profile"],
    )
    def get(self, request: Request) -> Response:
        profile, view = selectors.own_profile(_uid(request))
        return Response(view["visibility"])

    @extend_schema(
        summary="Change visibility of one or more field groups",
        description="Body maps group names (basics, bio, location, skills, links, open_to) "
        "to private, members or public.",
        request={
            "application/json": {"type": "object", "additionalProperties": {"type": "string"}}
        },
        responses={200: {"type": "object", "additionalProperties": {"type": "string"}}, **ERRORS},
        tags=["profile"],
    )
    def patch(self, request: Request) -> Response:
        serializer = VisibilityUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        services.update_visibility(user_id=_uid(request), levels=dict(serializer.validated_data))
        _, view = selectors.own_profile(_uid(request))
        return Response(view["visibility"])


class MemberProfileView(APIView):
    policy = policies.active_member

    @extend_schema(
        summary="Another member's profile, as members may see it",
        description="Fields the member keeps private are never included. If they hide even the "
        "basics, the profile answers 404.",
        responses={
            200: ProfileSerializer,
            403: OpenApiResponse(description="Not an approved member"),
            404: OpenApiResponse(description="No such profile, or not visible to you"),
        },
        tags=["profile"],
    )
    def get(self, request: Request, user_id: UUID) -> Response:
        view = selectors.profile_for_viewer(request.user, user_id)
        if view is None:
            raise exceptions.NotFound()
        return Response(ProfileSerializer(view).data)
