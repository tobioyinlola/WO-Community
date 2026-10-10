from typing import Any

from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import serializers, status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.adminconsole import dashboard, tasks
from apps.adminconsole.serializers import QueueCountsSerializer
from apps.adminconsole.views import _actor
from apps.core import policies
from apps.core.serializers import StrictSerializer

VIEW = policies.admin_permission("dashboard.view")
REFRESH = policies.admin_permission("settings.manage")
ERRORS = {
    401: OpenApiResponse(description="Not authenticated"),
    403: OpenApiResponse(description="Not allowed, or MFA missing"),
}


class RangeQuerySerializer(StrictSerializer):
    date_from = serializers.DateField(required=False, source="start")
    date_to = serializers.DateField(required=False, source="end")

    def to_internal_value(self, data: Any) -> Any:
        # The public names are `from` and `to`; `from` cannot be a Python attribute name.
        renamed = {
            ("date_from" if k == "from" else "date_to" if k == "to" else k): v
            for k, v in dict(data).items()
        }
        return super().to_internal_value(
            {k: (v[0] if isinstance(v, list) else v) for k, v in renamed.items()}
        )


class SeriesQuerySerializer(RangeQuerySerializer):
    metric = serializers.CharField(max_length=80)


class CountItemSerializer(serializers.Serializer):
    name = serializers.CharField()
    count = serializers.IntegerField()


class CommunitySerializer(serializers.Serializer):
    active_members = serializers.IntegerField(allow_null=True)
    pending_members = serializers.IntegerField(allow_null=True)
    registered_last_7_days = serializers.IntegerField(allow_null=True)
    registered_last_30_days = serializers.IntegerField()
    registered_previous_30_days = serializers.IntegerField()
    growth = serializers.FloatField(allow_null=True, help_text="Change on the previous 30 days")
    retention = serializers.DictField(child=serializers.FloatField(allow_null=True))
    by_country = CountItemSerializer(many=True)
    startups_by_sector = CountItemSerializer(many=True)
    startups_by_stage = CountItemSerializer(many=True)


class ActivitySerializer(serializers.Serializer):
    daily_active = serializers.IntegerField(allow_null=True)
    weekly_active = serializers.IntegerField(allow_null=True)
    monthly_active = serializers.IntegerField(allow_null=True)
    posts_last_7_days = serializers.IntegerField()
    comments_last_7_days = serializers.IntegerField()
    reactions_last_7_days = serializers.IntegerField()
    jobs_live = serializers.IntegerField(allow_null=True)
    jobs_posted_last_30_days = serializers.IntegerField()
    average_hours_to_approval = serializers.FloatField(allow_null=True)


class CampaignGlanceSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    name = serializers.CharField()
    started_at = serializers.DateTimeField(allow_null=True)
    sent = serializers.IntegerField()
    open_rate = serializers.FloatField()
    click_rate = serializers.FloatField()
    unsubscribed = serializers.IntegerField()


class EmailSnapshotSerializer(serializers.Serializer):
    recent_campaigns = CampaignGlanceSerializer(many=True)
    average_open_rate = serializers.FloatField(allow_null=True)
    average_click_rate = serializers.FloatField(allow_null=True)


class AvailabilitySerializer(serializers.Serializer):
    available = serializers.BooleanField(help_text="False until that part of the platform exists")


class DashboardSerializer(serializers.Serializer):
    refreshed_at = serializers.DateTimeField(allow_null=True)
    pending = QueueCountsSerializer()
    community = CommunitySerializer()
    activity = ActivitySerializer()
    email = EmailSnapshotSerializer()
    learning = AvailabilitySerializer()
    mentorship = AvailabilitySerializer()
    revenue = AvailabilitySerializer()


class PointSerializer(serializers.Serializer):
    date = serializers.DateField()
    value = serializers.FloatField(allow_null=True)


class SeriesSerializer(serializers.Serializer):
    metric = serializers.CharField()
    description = serializers.CharField()
    points = PointSerializer(many=True)
    total = serializers.FloatField(
        allow_null=True, help_text="Sum, or the average for averaged metrics"
    )


class MetricInfoSerializer(serializers.Serializer):
    metric = serializers.CharField()
    description = serializers.CharField()


class FunnelStepSerializer(serializers.Serializer):
    step = serializers.CharField()
    title = serializers.CharField()
    count = serializers.FloatField()
    from_previous = serializers.FloatField(allow_null=True)
    from_start = serializers.FloatField(allow_null=True)


class FunnelSerializer(serializers.Serializer):
    from_ = serializers.DateField(source="from")
    to = serializers.DateField()
    steps = FunnelStepSerializer(many=True)


class DashboardView(APIView):
    policy = VIEW

    @extend_schema(
        summary="The console home: queues, community, activity and email at a glance",
        description="Read from summary tables, never from raw events, so it is quick. "
        "`refreshed_at` says how fresh they are. The learning, mentorship and revenue "
        "sections report `available: false` until those parts of the platform exist.",
        responses={200: DashboardSerializer, **ERRORS},
        tags=["admin"],
    )
    def get(self, request: Request) -> Response:
        return Response(DashboardSerializer(dashboard.home(_actor(request))).data)


class MetricsView(APIView):
    policy = VIEW

    @extend_schema(
        summary="The metrics that can be charted",
        responses={200: MetricInfoSerializer(many=True), **ERRORS},
        tags=["admin"],
    )
    def get(self, request: Request) -> Response:
        data = [
            {"metric": m, "description": d} for m, d in sorted(dashboard.known_metrics().items())
        ]
        return Response(MetricInfoSerializer(data, many=True).data)


class SeriesView(APIView):
    policy = VIEW

    @extend_schema(
        summary="One metric, one value per day",
        description="`from` and `to` are dates (default: the last 30 days, at most 366 days).",
        parameters=[SeriesQuerySerializer],
        responses={
            200: SeriesSerializer,
            400: OpenApiResponse(description="Bad metric or range"),
            **ERRORS,
        },
        tags=["admin"],
    )
    def get(self, request: Request) -> Response:
        params = SeriesQuerySerializer(data=request.query_params.dict())
        params.is_valid(raise_exception=True)
        data = params.validated_data
        result = dashboard.series(data["metric"], data.get("start"), data.get("end"))
        return Response(SeriesSerializer(result).data)


class FunnelView(APIView):
    policy = VIEW

    @extend_schema(
        summary="The registration funnel, from directory visit to approval",
        description="Early steps come from visitors' browsers and only from people who agreed "
        "to analytics, so they understate traffic; the later steps are exact.",
        parameters=[RangeQuerySerializer],
        responses={200: FunnelSerializer, 400: OpenApiResponse(description="Bad range"), **ERRORS},
        tags=["admin"],
    )
    def get(self, request: Request) -> Response:
        params = RangeQuerySerializer(data=request.query_params.dict())
        params.is_valid(raise_exception=True)
        data = params.validated_data
        result = dashboard.funnel(data.get("start"), data.get("end"))
        return Response(
            {
                "from": result["from"],
                "to": result["to"],
                "steps": FunnelStepSerializer(result["steps"], many=True).data,
            }
        )


class RefreshView(APIView):
    policy = REFRESH

    @extend_schema(
        summary="Refresh the summary tables now",
        description="Normally a job does this every hour. Returns 202; the work runs in a worker.",
        request=None,
        responses={202: OpenApiResponse(description="Queued"), **ERRORS},
        tags=["admin"],
    )
    def post(self, request: Request) -> Response:
        tasks.refresh_dashboard.delay(2)
        return Response({"detail": "Refresh queued."}, status=status.HTTP_202_ACCEPTED)
