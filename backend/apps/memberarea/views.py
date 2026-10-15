from typing import cast
from uuid import UUID

from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, extend_schema
from rest_framework import serializers
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle, UserRateThrottle
from rest_framework.views import APIView

from apps.core import policies
from apps.core.public import PublicView
from apps.core.serializers import StrictSerializer
from apps.editorial.serializers import EditorialItemPageSerializer
from apps.memberarea import browse, news, onboarding, search, sitemap, stats


class ChecklistItemSerializer(serializers.Serializer):
    key = serializers.CharField()
    done = serializers.BooleanField()


class CompletenessSerializer(serializers.Serializer):
    score = serializers.IntegerField()
    next_missing_field = serializers.CharField(allow_null=True)


class OnboardingSerializer(serializers.Serializer):
    items = ChecklistItemSerializer(many=True)
    complete = serializers.BooleanField()
    profile_completeness = CompletenessSerializer()


class OnboardingView(APIView):
    policy = policies.authenticated

    @extend_schema(
        summary="Your onboarding checklist",
        description="Complete the profile (score of 80 or more), add a startup, add traction, "
        "and save your notification preferences. Calculated from your data on each call.",
        responses={200: OnboardingSerializer, 401: OpenApiResponse(description="Not logged in")},
        tags=["member area"],
    )
    def get(self, request: Request) -> Response:
        return Response(OnboardingSerializer(onboarding.checklist(request.user)).data)


class MyStatsSerializer(serializers.Serializer):
    trend_days = serializers.IntegerField(help_text="The window of the *_recent counts.")
    followers = serializers.IntegerField()
    followers_recent = serializers.IntegerField()
    posts = serializers.IntegerField()
    reactions_received = serializers.IntegerField()
    reactions_recent = serializers.IntegerField()
    comments_received = serializers.IntegerField()
    comments_recent = serializers.IntegerField()
    courses_in_progress = serializers.IntegerField()
    courses_completed = serializers.IntegerField()
    certificates = serializers.IntegerField()
    sessions_completed = serializers.IntegerField()
    sessions_upcoming = serializers.IntegerField()
    events_attended = serializers.IntegerField()
    events_upcoming = serializers.IntegerField()


class MyStatsView(APIView):
    policy = policies.authenticated

    @extend_schema(
        summary="Your numbers for the dashboard",
        description="Followers, reactions and comments on your posts, learning, mentoring and "
        "events. The *_recent counts cover the last `trend_days` days.",
        responses={200: MyStatsSerializer, 401: OpenApiResponse(description="Not logged in")},
        tags=["member area"],
    )
    def get(self, request: Request) -> Response:
        return Response(MyStatsSerializer(stats.for_member(cast(UUID, request.user.pk))).data)


class SearchQuerySerializer(StrictSerializer):
    q = serializers.CharField(min_length=2, max_length=100, trim_whitespace=True)
    types = serializers.CharField(required=False, allow_blank=True, default="", max_length=100)
    limit = serializers.IntegerField(required=False, min_value=1, max_value=20, default=10)

    def validate_types(self, value: str) -> list[str]:
        kinds = [part.strip() for part in value.split(",") if part.strip()]
        unknown = sorted(set(kinds) - set(search.SEARCHERS))
        if unknown:
            raise serializers.ValidationError(f"Unknown type: {', '.join(unknown)}.")
        return kinds or list(search.SEARCHERS)


class SearchHitSerializer(serializers.Serializer):
    type = serializers.CharField()
    id = serializers.UUIDField()
    slug = serializers.CharField()
    title = serializers.CharField()
    subtitle = serializers.CharField(allow_blank=True)
    image = serializers.DictField(allow_null=True)


class SearchResultSerializer(serializers.Serializer):
    members = SearchHitSerializer(many=True, required=False)
    startups = SearchHitSerializer(many=True, required=False)
    jobs = SearchHitSerializer(many=True, required=False)
    mentors = SearchHitSerializer(many=True, required=False)
    events = SearchHitSerializer(many=True, required=False)
    news = SearchHitSerializer(many=True, required=False)
    courses = SearchHitSerializer(many=True, required=False)


class SearchView(APIView):
    policy = policies.active_member
    throttle_classes = [UserRateThrottle, ScopedRateThrottle]
    throttle_scope = "search"

    @extend_schema(
        summary="Search members, startups, jobs, mentors, events, news and courses",
        description="Results are what you may see of each item: someone who hides their basics "
        "from members cannot be found. People and startups tolerate small typos; events, news "
        "and courses match words in their title and text.",
        parameters=[
            OpenApiParameter("q", str, required=True, description="2 to 100 characters"),
            OpenApiParameter(
                "types",
                str,
                description="Comma list: members, startups, jobs, mentors, events, news, courses",
            ),
            OpenApiParameter("limit", int, description="Per type, 1 to 20 (default 10)"),
        ],
        responses={
            200: SearchResultSerializer,
            400: OpenApiResponse(description="Invalid query"),
            401: OpenApiResponse(description="Not logged in"),
            403: OpenApiResponse(description="Not an active member"),
            429: OpenApiResponse(description="Too many searches"),
        },
        tags=["member area"],
    )
    def get(self, request: Request) -> Response:
        params = SearchQuerySerializer(data=request.query_params)
        params.is_valid(raise_exception=True)
        data = params.validated_data
        found = search.search(request.user, data["q"], data["types"], data["limit"])
        response = Response(SearchResultSerializer(found).data)
        response["Cache-Control"] = "private, no-store"
        return response


class SitemapPageSerializer(serializers.Serializer):
    path = serializers.CharField(help_text="Front end path, for example /jobs/senior-engineer.")
    lastmod = serializers.DateTimeField(allow_null=True)


class PublicStatsCountrySerializer(serializers.Serializer):
    code = serializers.CharField()
    founders = serializers.IntegerField()


class PublicStatsSerializer(serializers.Serializer):
    startups = serializers.IntegerField()
    founders = serializers.IntegerField()
    courses = serializers.IntegerField()
    jobs = serializers.IntegerField()
    countries = PublicStatsCountrySerializer(many=True)


class PublicStatsView(PublicView):
    cache_control = "public, max-age=600, stale-while-revalidate=600"

    @extend_schema(
        summary="How much is on the public site",
        description="Counts of what a visitor can see: startups and founders listed, courses "
        "open to visitors and open roles, and up to ten countries listed founders are in (code and "
        "founder count only). Counted from the same lists as the sitemap, so every "
        "number is something a visitor can click through to. Nothing about individual members.",
        responses={200: PublicStatsSerializer},
        tags=["public"],
    )
    def get(self, request: Request) -> Response:
        if request.query_params:
            raise serializers.ValidationError({"detail": "No parameters are accepted."})
        return self.cached(request, PublicStatsSerializer(sitemap.counts()).data)


class FullSitemapSerializer(serializers.Serializer):
    startups = SitemapPageSerializer(many=True)
    founders = SitemapPageSerializer(many=True)
    jobs = SitemapPageSerializer(many=True)
    news = SitemapPageSerializer(many=True)
    events = SitemapPageSerializer(many=True)
    courses = SitemapPageSerializer(many=True)


class FullSitemapView(PublicView):
    cache_control = "public, max-age=3600, stale-while-revalidate=3600"

    @extend_schema(
        summary="Every public page of every kind, with its last change",
        description="Startups, founders, jobs, news and wins, events and courses open to "
        "visitors in one response, so the front end builds a single sitemap from it. Each list "
        "is capped at 5,000 entries (50,000 for startups and founders), newest first.",
        responses={200: FullSitemapSerializer},
        tags=["public"],
    )
    def get(self, request: Request) -> Response:
        if request.query_params:
            raise serializers.ValidationError({"detail": "No parameters are accepted."})
        return self.cached(request, FullSitemapSerializer(sitemap.build()).data)


class FollowingNewsQuerySerializer(serializers.Serializer):
    type = serializers.CharField(required=False, allow_blank=True, max_length=12, default="")
    cursor = serializers.CharField(required=False, allow_blank=True, max_length=400, default="")
    limit = serializers.IntegerField(required=False, min_value=1, max_value=50, default=20)


class FollowingNewsView(APIView):
    policy = policies.active_member

    @extend_schema(
        summary="News about people and startups you follow",
        description="Published news and wins that feature a startup you follow, or a startup of "
        "someone you follow. Same shape as `GET /editorial`.",
        parameters=[FollowingNewsQuerySerializer],
        responses={
            200: EditorialItemPageSerializer,
            401: OpenApiResponse(description="Not logged in"),
        },
        tags=["member area"],
    )
    def get(self, request: Request) -> Response:
        params = FollowingNewsQuerySerializer(data=request.query_params.dict())
        params.is_valid(raise_exception=True)
        data = params.validated_data
        page = news.following_feed(
            request.user, type=data["type"], cursor=data["cursor"], limit=data["limit"]
        )
        response = Response(EditorialItemPageSerializer(page).data)
        response["Cache-Control"] = "private, no-store"
        return response


class BrowseQuerySerializer(StrictSerializer):
    q = serializers.CharField(required=False, allow_blank=True, default="", max_length=100)
    country = serializers.CharField(required=False, allow_blank=True, default="", max_length=2)
    sort = serializers.ChoiceField(choices=["newest", "name"], required=False, default="newest")
    page = serializers.IntegerField(required=False, min_value=1, default=1)
    page_size = serializers.IntegerField(required=False, min_value=1, max_value=48, default=12)


class StartupBrowseQuerySerializer(BrowseQuerySerializer):
    city = serializers.CharField(required=False, allow_blank=True, default="", max_length=100)
    sector = serializers.CharField(required=False, allow_blank=True, default="", max_length=80)
    stage = serializers.CharField(required=False, allow_blank=True, default="", max_length=80)
    hiring = serializers.BooleanField(required=False, default=False)


class PeopleBrowseQuerySerializer(BrowseQuerySerializer):
    skill = serializers.CharField(required=False, allow_blank=True, default="", max_length=80)


class PageMetaSerializer(serializers.Serializer):
    count = serializers.IntegerField()
    page = serializers.IntegerField()
    page_size = serializers.IntegerField()
    pages = serializers.IntegerField()


class BrowseJobSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    title = serializers.CharField()


class BrowseTractionSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    kind = serializers.CharField()
    value = serializers.JSONField(allow_null=True)
    as_of_date = serializers.DateField()


class BrowseNamedSerializer(serializers.Serializer):
    slug = serializers.CharField()
    name = serializers.CharField()


class BrowseStartupSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    slug = serializers.CharField()
    name = serializers.CharField()
    pitch = serializers.CharField(allow_blank=True)
    logo = serializers.DictField(allow_null=True)
    sector = BrowseNamedSerializer(allow_null=True)
    stage = BrowseNamedSerializer(allow_null=True)
    country = serializers.CharField(allow_blank=True)
    city = serializers.CharField(allow_blank=True)
    year_founded = serializers.IntegerField(allow_null=True)
    description = serializers.CharField(allow_blank=True)
    website_url = serializers.CharField(allow_blank=True)
    pitch_deck_url = serializers.CharField(allow_blank=True)
    featured = serializers.BooleanField()
    traction = BrowseTractionSerializer(many=True)
    open_jobs_count = serializers.IntegerField()
    open_jobs = BrowseJobSerializer(many=True)


class BrowseStartupPageSerializer(PageMetaSerializer):
    results = BrowseStartupSerializer(many=True)


class BrowsePersonSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    slug = serializers.CharField()
    name = serializers.CharField()
    headline = serializers.CharField(allow_blank=True)
    photo = serializers.DictField(allow_null=True)
    city = serializers.CharField(allow_blank=True)
    country = serializers.CharField(allow_blank=True)
    skills = BrowseNamedSerializer(many=True)


class BrowsePeoplePageSerializer(PageMetaSerializer):
    results = BrowsePersonSerializer(many=True)


BROWSE_ERRORS = {
    400: OpenApiResponse(description="Invalid filter"),
    401: OpenApiResponse(description="Not logged in"),
    403: OpenApiResponse(description="Not an active member"),
}


class BrowseStartupsView(APIView):
    policy = policies.active_member
    throttle_classes = [UserRateThrottle, ScopedRateThrottle]
    throttle_scope = "search"

    @extend_schema(
        operation_id="directory_startups",
        summary="Browse startups with filters",
        description="Page by page, featured first. Filter by country, city, sector, stage and "
        "whether the startup has open jobs. Each card shows only what its owner shares "
        "with members.",
        parameters=[StartupBrowseQuerySerializer],
        responses={200: BrowseStartupPageSerializer, **BROWSE_ERRORS},
        tags=["member area"],
    )
    def get(self, request: Request) -> Response:
        params = StartupBrowseQuerySerializer(data=request.query_params)
        params.is_valid(raise_exception=True)
        response = Response(
            BrowseStartupPageSerializer(
                browse.browse_startups(request.user, **params.validated_data)
            ).data
        )
        response["Cache-Control"] = "private, no-store"
        return response


class BrowsePeopleView(APIView):
    policy = policies.active_member
    throttle_classes = [UserRateThrottle, ScopedRateThrottle]
    throttle_scope = "search"

    @extend_schema(
        operation_id="directory_people",
        summary="Browse members with filters",
        description="Page by page. Filter by country and skill. Members who hide their basics "
        "from members do not appear.",
        parameters=[PeopleBrowseQuerySerializer],
        responses={200: BrowsePeoplePageSerializer, **BROWSE_ERRORS},
        tags=["member area"],
    )
    def get(self, request: Request) -> Response:
        params = PeopleBrowseQuerySerializer(data=request.query_params)
        params.is_valid(raise_exception=True)
        response = Response(
            BrowsePeoplePageSerializer(
                browse.browse_people(request.user, **params.validated_data)
            ).data
        )
        response["Cache-Control"] = "private, no-store"
        return response
