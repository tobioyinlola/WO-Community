from uuid import UUID

from django.http import HttpResponse
from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.toolkit.ventures import selectors, services
from apps.toolkit.ventures.permissions import (
    member_policy,
    owned_venture,
    readable_venture,
    uid,
)
from apps.toolkit.ventures.serializers import (
    TkCompetitorPatchSerializer,
    TkCompetitorSerializer,
    TkCompetitorWriteSerializer,
    TkImportStartupSerializer,
    TkPackageSerializer,
    TkProfileSerializer,
    TkProfileUpdateResultSerializer,
    TkProfileUpdateSerializer,
    TkProfileVersionSerializer,
    TkTeamMemberSerializer,
    TkTeamPatchSerializer,
    TkTeamWriteSerializer,
    TkVentureCreateSerializer,
    TkVenturePageSerializer,
    TkVentureSerializer,
    TkVentureUpdateSerializer,
)

ERRORS = {
    401: OpenApiResponse(description="Not authenticated"),
    403: OpenApiResponse(description="Not an approved member"),
    404: OpenApiResponse(description="Not found, or not yours"),
}
TAG = ["toolkit"]


def _private(response: Response) -> Response:
    response["Cache-Control"] = "private, no-store"
    return response


class VenturesView(APIView):
    policy = member_policy()

    @extend_schema(
        operation_id="toolkit_ventures_list",
        summary="Your ventures",
        responses={200: TkVenturePageSerializer, **ERRORS},
        tags=TAG,
    )
    def get(self, request: Request) -> Response:
        rows = [
            selectors.venture_view(v) for v in selectors.mine(uid(request)).order_by("-created_at")
        ]
        return _private(Response(TkVenturePageSerializer({"results": rows}).data))

    @extend_schema(
        summary="Start a venture",
        description="A member can have a few ventures at a time (409 beyond that). With "
        "`from_startup_id` the profile is filled from a startup you own or are on the team of.",
        request=TkVentureCreateSerializer,
        responses={201: TkVentureSerializer, **ERRORS, 409: OpenApiResponse(description="Limit")},
        tags=TAG,
    )
    def post(self, request: Request) -> Response:
        serializer = TkVentureCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        venture = services.create_venture(
            owner_id=uid(request),
            name=serializer.validated_data["name"],
            from_startup_id=serializer.validated_data.get("from_startup_id"),
        )
        return _private(
            Response(TkVentureSerializer(selectors.venture_view(venture)).data, status=201)
        )


class VentureView(APIView):
    policy = member_policy()

    @extend_schema(
        summary="One venture",
        responses={200: TkVentureSerializer, **ERRORS},
        tags=TAG,
    )
    def get(self, request: Request, venture_id: UUID) -> Response:
        venture = readable_venture(request, venture_id)
        return _private(Response(TkVentureSerializer(selectors.venture_view(venture)).data))

    @extend_schema(
        summary="Rename, archive or change nudges",
        request=TkVentureUpdateSerializer,
        responses={200: TkVentureSerializer, **ERRORS},
        tags=TAG,
    )
    def patch(self, request: Request, venture_id: UUID) -> Response:
        venture = owned_venture(request, venture_id)
        serializer = TkVentureUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        if "nudges_enabled" in data:
            venture.nudges_enabled = data["nudges_enabled"]
            venture.save(update_fields=["nudges_enabled", "updated_at"])
        venture = services.update_venture(
            venture=venture, name=data.get("name"), archived=data.get("archived")
        )
        return _private(Response(TkVentureSerializer(selectors.venture_view(venture)).data))

    @extend_schema(
        summary="Delete a venture",
        description="It disappears now and everything made from it is erased for good after the "
        "grace period (14 days by default). Restore it before then with `POST .../restore`.",
        responses={204: None, **ERRORS},
        tags=TAG,
    )
    def delete(self, request: Request, venture_id: UUID) -> Response:
        services.delete_venture(venture=owned_venture(request, venture_id))
        return Response(status=status.HTTP_204_NO_CONTENT)


class VentureRestoreView(APIView):
    policy = member_policy()

    @extend_schema(
        summary="Undo a delete during the grace period",
        request=None,
        responses={200: TkVentureSerializer, **ERRORS},
        tags=TAG,
    )
    def post(self, request: Request, venture_id: UUID) -> Response:
        venture = selectors.owned(uid(request), venture_id, include_deleted=True)
        if venture is None or venture.deleted_at is None:
            from rest_framework import exceptions

            raise exceptions.NotFound()
        venture = services.restore_venture(venture=venture)
        return Response(TkVentureSerializer(selectors.venture_view(venture)).data)


class VentureExportView(APIView):
    policy = member_policy()

    @extend_schema(
        summary="Download everything held about a venture",
        description="One JSON document: the profile, its history and every output.",
        responses={(200, "application/json"): OpenApiResponse(description="JSON"), **ERRORS},
        tags=TAG,
    )
    def get(self, request: Request, venture_id: UUID) -> HttpResponse:
        import json

        venture = owned_venture(request, venture_id)
        body = json.dumps(services.export_data(venture), default=str, indent=2)
        response = HttpResponse(body, content_type="application/json")
        response["Content-Disposition"] = f'attachment; filename="venture-{venture.pk}.json"'
        response["Cache-Control"] = "private, no-store"
        return response


class PackageView(APIView):
    policy = member_policy()

    @extend_schema(
        summary="The venture board",
        description="Completeness, what is missing before a score can run, and where each output "
        "(score, plan, forecast, decks, prototypes) stands.",
        responses={200: TkPackageSerializer, **ERRORS},
        tags=TAG,
    )
    def get(self, request: Request, venture_id: UUID) -> Response:
        venture = readable_venture(request, venture_id)
        return _private(Response(TkPackageSerializer(selectors.package(venture)).data))


class ProfileView(APIView):
    policy = member_policy()

    @extend_schema(
        summary="The venture profile",
        responses={200: TkProfileSerializer, **ERRORS},
        tags=TAG,
    )
    def get(self, request: Request, venture_id: UUID) -> Response:
        venture = readable_venture(request, venture_id)
        return _private(Response(TkProfileSerializer(selectors.profile_view(venture)).data))

    @extend_schema(
        summary="Save some profile fields",
        description="Send only what changed, a wizard step at a time. Every field is checked; "
        "a null or blank clears it. Changing a field marks the outputs made from it as needing "
        "a refresh. Anything that came from a suggestion is recorded as such only because you "
        "saved it here.",
        request=TkProfileUpdateSerializer,
        responses={
            200: TkProfileUpdateResultSerializer,
            **ERRORS,
            400: OpenApiResponse(description="A field is invalid (errors name each one)"),
            409: OpenApiResponse(description="`base_version` is stale"),
        },
        tags=TAG,
    )
    def patch(self, request: Request, venture_id: UUID) -> Response:
        venture = owned_venture(request, venture_id)
        serializer = TkProfileUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        _, changed = services.update_profile(
            venture=venture,
            patch=dict(data["fields"]),
            base_version=data.get("base_version"),
            source="member",
        )
        venture.refresh_from_db()
        body = {
            "profile": selectors.profile_view(venture),
            "changed": changed,
            "outputs": selectors.outputs(venture),
        }
        return _private(Response(TkProfileUpdateResultSerializer(body).data))


class ImportStartupView(APIView):
    policy = member_policy()

    @extend_schema(
        summary="Fill the profile from your startup profile",
        description="Copies name, pitch, country, city, sector, stage, description and team. "
        "Each copied field is marked as imported; nothing else changes.",
        request=TkImportStartupSerializer,
        responses={200: TkProfileUpdateResultSerializer, **ERRORS},
        tags=TAG,
    )
    def post(self, request: Request, venture_id: UUID) -> Response:
        venture = owned_venture(request, venture_id)
        serializer = TkImportStartupSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        services.import_startup(
            venture=venture,
            user_id=uid(request),
            startup_id=serializer.validated_data["startup_id"],
        )
        venture.refresh_from_db()
        body = {
            "profile": selectors.profile_view(venture),
            "changed": [],
            "outputs": selectors.outputs(venture),
        }
        return _private(Response(TkProfileUpdateResultSerializer(body).data))


class ProfileVersionsView(APIView):
    policy = member_policy()

    @extend_schema(
        summary="Profile history",
        responses={200: TkProfileVersionSerializer(many=True), **ERRORS},
        tags=TAG,
    )
    def get(self, request: Request, venture_id: UUID) -> Response:
        venture = owned_venture(request, venture_id)
        return _private(
            Response(TkProfileVersionSerializer(selectors.versions(venture), many=True).data)
        )


class CompetitorsView(APIView):
    policy = member_policy()

    @extend_schema(
        summary="Competitors",
        responses={200: TkCompetitorSerializer(many=True), **ERRORS},
        tags=TAG,
    )
    def get(self, request: Request, venture_id: UUID) -> Response:
        venture = readable_venture(request, venture_id)
        rows = selectors.profile_view(venture)["competitors"]
        return _private(Response(TkCompetitorSerializer(rows, many=True).data))

    @extend_schema(
        summary="Add a competitor",
        description="Up to 8.",
        request=TkCompetitorWriteSerializer,
        responses={201: TkCompetitorSerializer, **ERRORS},
        tags=TAG,
    )
    def post(self, request: Request, venture_id: UUID) -> Response:
        venture = owned_venture(request, venture_id)
        serializer = TkCompetitorWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        row = services.add_competitor(venture=venture, data=dict(serializer.validated_data))
        return Response(TkCompetitorSerializer(row).data, status=201)


class CompetitorView(APIView):
    policy = member_policy()

    @extend_schema(
        summary="Change a competitor",
        request=TkCompetitorPatchSerializer,
        responses={200: TkCompetitorSerializer, **ERRORS},
        tags=TAG,
    )
    def patch(self, request: Request, venture_id: UUID, competitor_id: UUID) -> Response:
        venture = owned_venture(request, venture_id)
        serializer = TkCompetitorPatchSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        row = services.change_competitor(
            venture=venture, competitor_id=competitor_id, data=dict(serializer.validated_data)
        )
        return Response(TkCompetitorSerializer(row).data)

    @extend_schema(summary="Remove a competitor", responses={204: None, **ERRORS}, tags=TAG)
    def delete(self, request: Request, venture_id: UUID, competitor_id: UUID) -> Response:
        services.remove_competitor(
            venture=owned_venture(request, venture_id), competitor_id=competitor_id
        )
        return Response(status=204)


class TeamView(APIView):
    policy = member_policy()

    @extend_schema(
        summary="Team",
        responses={200: TkTeamMemberSerializer(many=True), **ERRORS},
        tags=TAG,
    )
    def get(self, request: Request, venture_id: UUID) -> Response:
        venture = readable_venture(request, venture_id)
        rows = selectors.profile_view(venture)["team"]
        return _private(Response(TkTeamMemberSerializer(rows, many=True).data))

    @extend_schema(
        summary="Add a team member",
        description="Up to 20.",
        request=TkTeamWriteSerializer,
        responses={201: TkTeamMemberSerializer, **ERRORS},
        tags=TAG,
    )
    def post(self, request: Request, venture_id: UUID) -> Response:
        venture = owned_venture(request, venture_id)
        serializer = TkTeamWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        row = services.add_team_member(venture=venture, data=dict(serializer.validated_data))
        return Response(TkTeamMemberSerializer(row).data, status=201)


class TeamMemberView(APIView):
    policy = member_policy()

    @extend_schema(
        summary="Change a team member",
        request=TkTeamPatchSerializer,
        responses={200: TkTeamMemberSerializer, **ERRORS},
        tags=TAG,
    )
    def patch(self, request: Request, venture_id: UUID, member_id: UUID) -> Response:
        venture = owned_venture(request, venture_id)
        serializer = TkTeamPatchSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        row = services.change_team_member(
            venture=venture, member_id=member_id, data=dict(serializer.validated_data)
        )
        return Response(TkTeamMemberSerializer(row).data)

    @extend_schema(summary="Remove a team member", responses={204: None, **ERRORS}, tags=TAG)
    def delete(self, request: Request, venture_id: UUID, member_id: UUID) -> Response:
        services.remove_team_member(venture=owned_venture(request, venture_id), member_id=member_id)
        return Response(status=204)
