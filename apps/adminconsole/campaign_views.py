from uuid import UUID

from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, extend_schema
from rest_framework import exceptions, status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.adminconsole.views import _actor, _ip
from apps.campaigns import segments, services
from apps.campaigns.models import Campaign, CampaignTemplate, Segment
from apps.campaigns.serializers import (
    CampaignCreateSerializer,
    CampaignQuerySerializer,
    CampaignScheduleSerializer,
    CampaignSerializer,
    CampaignUpdateSerializer,
    PreviewResultSerializer,
    ReportSerializer,
    SegmentPreviewSerializer,
    SegmentSerializer,
    SegmentUpdateSerializer,
    SegmentWriteSerializer,
    TemplateSerializer,
    TemplateWriteSerializer,
)
from apps.core import etag, policies
from apps.core.pagination import AdminLimitOffsetPagination

MANAGE = policies.admin_permission("campaigns.send")
# Starting a send reaches many people and cannot be recalled, so it needs a fresh MFA check.
SEND = policies.admin_permission("campaigns.send", step_up=True)
IF_MATCH = OpenApiParameter("If-Match", str, OpenApiParameter.HEADER, required=True)
ERRORS = {
    401: OpenApiResponse(description="Not authenticated"),
    403: OpenApiResponse(description="Not allowed, or MFA missing"),
    404: OpenApiResponse(description="Not found"),
}


def _campaign_view(campaign: Campaign) -> dict[str, object]:
    return {
        "id": campaign.pk,
        "name": campaign.name,
        "subject": campaign.subject,
        "preheader": campaign.preheader,
        "blocks": campaign.blocks,
        "segment_id": campaign.segment_id,
        "status": campaign.status,
        "scheduled_at": campaign.scheduled_at,
        "started_at": campaign.started_at,
        "finished_at": campaign.finished_at,
        "recipient_count": campaign.recipient_count,
        "created_at": campaign.created_at,
    }


def _one(campaign: Campaign, status_code: int = 200) -> Response:
    fresh = Campaign.objects.get(pk=campaign.pk)
    return etag.add_etag(
        Response(CampaignSerializer(_campaign_view(fresh)).data, status=status_code), fresh
    )


def _campaign(campaign_id: UUID) -> Campaign:
    found = Campaign.objects.filter(pk=campaign_id).first()
    if found is None:
        raise exceptions.NotFound()
    return found


# --- segments ---


class SegmentsView(APIView):
    policy = MANAGE

    @extend_schema(
        summary="Saved segments",
        responses={200: SegmentSerializer(many=True), **ERRORS},
        tags=["admin"],
    )
    def get(self, request: Request) -> Response:
        paginator = AdminLimitOffsetPagination()
        page = paginator.paginate_queryset(
            Segment.objects.order_by("-created_at"), request, view=self
        )
        return paginator.get_paginated_response(SegmentSerializer(page, many=True).data)

    @extend_schema(
        summary="Save a segment",
        description="Choose from: `country`, `sector`, `stage`, `skills`, `roles`, `joined_after`, "
        "`joined_before`, `last_active_after`, `last_active_before`, `completeness_min`, "
        "`completeness_max` and `tags` (profile_complete, registered_incomplete, directory_listed, "
        "founder_active, founder_dormant, job_poster). Everything given must match; several "
        "values in one list match any of them. Course enrolment arrives with the learning hub.",
        request=SegmentWriteSerializer,
        responses={201: SegmentSerializer, **ERRORS},
        tags=["admin"],
    )
    def post(self, request: Request) -> Response:
        serializer = SegmentWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        segment = services.create_segment(
            actor=_actor(request),
            name=serializer.validated_data["name"],
            definition=dict(request.data["definition"]),
        )
        return Response(SegmentSerializer(segment).data, status=status.HTTP_201_CREATED)


class SegmentView(APIView):
    policy = MANAGE

    @extend_schema(
        summary="One segment", responses={200: SegmentSerializer, **ERRORS}, tags=["admin"]
    )
    def get(self, request: Request, segment_id: UUID) -> Response:
        segment = Segment.objects.filter(pk=segment_id).first()
        if segment is None:
            raise exceptions.NotFound()
        return Response(SegmentSerializer(segment).data)

    @extend_schema(
        summary="Change a segment",
        request=SegmentUpdateSerializer,
        responses={200: SegmentSerializer, **ERRORS},
        tags=["admin"],
    )
    def patch(self, request: Request, segment_id: UUID) -> Response:
        serializer = SegmentUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        segment = services.update_segment(
            segment_id=segment_id,
            name=serializer.validated_data.get("name"),
            definition=dict(request.data["definition"]) if "definition" in request.data else None,
        )
        return Response(SegmentSerializer(segment).data)

    @extend_schema(summary="Delete a segment", responses={204: None, **ERRORS}, tags=["admin"])
    def delete(self, request: Request, segment_id: UUID) -> Response:
        services.delete_segment(segment_id=segment_id)
        return Response(status=status.HTTP_204_NO_CONTENT)


class SegmentPreviewView(APIView):
    policy = MANAGE

    @extend_schema(
        summary="How many people a segment would reach",
        request=SegmentPreviewSerializer,
        responses={200: PreviewResultSerializer, **ERRORS},
        tags=["admin"],
    )
    def post(self, request: Request) -> Response:
        serializer = SegmentPreviewSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        definition = segments.clean(dict(request.data["definition"]))
        return Response(PreviewResultSerializer(segments.preview(definition)).data)


class SavedSegmentPreviewView(APIView):
    policy = MANAGE

    @extend_schema(
        summary="How many people a saved segment would reach now",
        responses={200: PreviewResultSerializer, **ERRORS},
        tags=["admin"],
    )
    def get(self, request: Request, segment_id: UUID) -> Response:
        segment = Segment.objects.filter(pk=segment_id).first()
        if segment is None:
            raise exceptions.NotFound()
        return Response(PreviewResultSerializer(segments.preview(segment.definition)).data)


# --- templates ---


class TemplatesView(APIView):
    policy = MANAGE

    @extend_schema(
        summary="Newsletter templates",
        responses={200: TemplateSerializer(many=True), **ERRORS},
        tags=["admin"],
    )
    def get(self, request: Request) -> Response:
        rows = CampaignTemplate.objects.order_by("name")
        return Response(TemplateSerializer(rows, many=True).data)

    @extend_schema(
        summary="Save a template",
        description="Blocks: heading, paragraph, button, image and divider. Merge field: "
        "`{{first_name}}`.",
        request=TemplateWriteSerializer,
        responses={201: TemplateSerializer, **ERRORS},
        tags=["admin"],
    )
    def post(self, request: Request) -> Response:
        serializer = TemplateWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        template = services.create_template(
            actor=_actor(request),
            name=serializer.validated_data["name"],
            blocks=serializer.validated_data["blocks"],
        )
        return Response(TemplateSerializer(template).data, status=status.HTTP_201_CREATED)


class TemplateView(APIView):
    policy = MANAGE

    @extend_schema(summary="Delete a template", responses={204: None, **ERRORS}, tags=["admin"])
    def delete(self, request: Request, template_id: UUID) -> Response:
        services.delete_template(template_id=template_id)
        return Response(status=status.HTTP_204_NO_CONTENT)


# --- campaigns ---


class CampaignsView(APIView):
    policy = MANAGE

    @extend_schema(
        summary="Newsletters",
        parameters=[CampaignQuerySerializer],
        responses={200: CampaignSerializer(many=True), **ERRORS},
        tags=["admin"],
    )
    def get(self, request: Request) -> Response:
        params = CampaignQuerySerializer(data=request.query_params.dict())
        params.is_valid(raise_exception=True)
        queryset = Campaign.objects.order_by("-created_at", "-id")
        if params.validated_data["status"]:
            queryset = queryset.filter(status=params.validated_data["status"])
        paginator = AdminLimitOffsetPagination()
        page = paginator.paginate_queryset(queryset, request, view=self)
        data = CampaignSerializer([_campaign_view(c) for c in page or []], many=True).data
        return paginator.get_paginated_response(data)

    @extend_schema(
        summary="Write a newsletter",
        description="Starts as a draft. Content is a list of blocks (or `template_id`). The "
        "audience is a saved segment (`segment_id`).",
        request=CampaignCreateSerializer,
        responses={201: CampaignSerializer, **ERRORS},
        tags=["admin"],
    )
    def post(self, request: Request) -> Response:
        serializer = CampaignCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        campaign = services.create_campaign(
            actor=_actor(request), data=dict(serializer.validated_data), ip=_ip(request)
        )
        return _one(campaign, 201)


class CampaignView(APIView):
    policy = MANAGE

    @extend_schema(
        summary="One newsletter", responses={200: CampaignSerializer, **ERRORS}, tags=["admin"]
    )
    def get(self, request: Request, campaign_id: UUID) -> Response:
        return _one(_campaign(campaign_id))

    @extend_schema(
        summary="Edit a draft or scheduled newsletter",
        parameters=[IF_MATCH],
        request=CampaignUpdateSerializer,
        responses={
            200: CampaignSerializer,
            **ERRORS,
            409: OpenApiResponse(description="Already sending or sent"),
            412: OpenApiResponse(description="Changed since the ETag was issued"),
            428: OpenApiResponse(description="If-Match header missing"),
        },
        tags=["admin"],
    )
    def patch(self, request: Request, campaign_id: UUID) -> Response:
        serializer = CampaignUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        campaign = services.update_campaign(
            actor=_actor(request),
            campaign_id=campaign_id,
            data=dict(serializer.validated_data),
            if_match=request.headers.get("If-Match"),
        )
        return _one(campaign)

    @extend_schema(summary="Delete a draft", responses={204: None, **ERRORS}, tags=["admin"])
    def delete(self, request: Request, campaign_id: UUID) -> Response:
        services.delete_campaign(actor=_actor(request), campaign_id=campaign_id, ip=_ip(request))
        return Response(status=status.HTTP_204_NO_CONTENT)


class CampaignReportView(APIView):
    policy = MANAGE

    @extend_schema(
        summary="Delivery and engagement so far",
        description="Counts of people: sent, delivered, opened, clicked, bounced, unsubscribed "
        "and complained, with open and click rates of those sent. Updated as the email provider "
        "reports.",
        responses={200: ReportSerializer, **ERRORS},
        tags=["admin"],
    )
    def get(self, request: Request, campaign_id: UUID) -> Response:
        return Response(ReportSerializer(services.report(_campaign(campaign_id))).data)


class CampaignActionView(APIView):
    """Schedule, send, pause, resume, cancel or test (the URL names the action)."""

    policy = MANAGE
    action = ""

    @extend_schema(
        summary="Run an action on a newsletter",
        description="Actions: `send` (now), `schedule` (needs `scheduled_at`), `unschedule`, "
        "`pause` (the kill switch), `resume`, `cancel` and `test` (sends to you alone, 204). "
        "Send, schedule and resume need a fresh MFA step-up. Sending freezes the audience, "
        "leaves out anyone who has unsubscribed, and rechecks each person just before their "
        "message goes.",
        request=CampaignScheduleSerializer,
        responses={
            200: CampaignSerializer,
            204: None,
            **ERRORS,
            409: OpenApiResponse(description="Not in a state that allows this"),
        },
        tags=["admin"],
    )
    def post(self, request: Request, campaign_id: UUID) -> Response:
        actor, ip = _actor(request), _ip(request)
        if self.action == "test":
            services.send_test(actor=actor, campaign_id=campaign_id)
            return Response(status=status.HTTP_204_NO_CONTENT)
        if self.action == "schedule":
            serializer = CampaignScheduleSerializer(data=request.data)
            serializer.is_valid(raise_exception=True)
            campaign = services.schedule(
                actor=actor,
                campaign_id=campaign_id,
                at=serializer.validated_data["scheduled_at"],
                ip=ip,
            )
        else:
            call = {
                "send": services.send_now,
                "unschedule": services.unschedule,
                "pause": services.pause,
                "resume": services.resume,
                "cancel": services.cancel,
            }[self.action]
            campaign = call(actor=actor, campaign_id=campaign_id, ip=ip)
        return _one(campaign)


class StepUpCampaignActionView(CampaignActionView):
    policy = SEND


def action_view(action: str) -> type[CampaignActionView]:
    base = (
        StepUpCampaignActionView if action in ("send", "schedule", "resume") else CampaignActionView
    )
    return type(f"{action.title()}CampaignView", (base,), {"action": action})
