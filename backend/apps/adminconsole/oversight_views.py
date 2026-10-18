"""What admins see across the community: the feed, mentoring pairs and live analytics.

Everything here reads the database directly, so the numbers are current without waiting for a
background job to roll them up.
"""

from collections import Counter
from datetime import date, datetime, time, timedelta
from typing import Any, cast
from uuid import UUID

from django.db.models import Count, Max, Q, QuerySet
from django.db.models.functions import TruncDate
from django.utils import timezone
from django.utils.html import strip_tags
from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import exceptions, serializers
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.throttling import BaseThrottle
from rest_framework.views import APIView

from apps.accounts.models import User
from apps.adminconsole.dashboard_views import RangeQuerySerializer
from apps.adminconsole.people import people
from apps.core import policies
from apps.core.pagination import AdminLimitOffsetPagination
from apps.core.serializers import StrictSerializer
from apps.events.models import EventRegistration
from apps.feed import services as feed_services
from apps.feed.models import CATEGORIES, Comment, Post, Reaction, Report
from apps.feed.serializers import ImageInputSerializer, ShareInputSerializer
from apps.jobs.models import Job
from apps.learning.models import Enrolment
from apps.mentorship.models import MentorSession
from apps.profiles.models import FounderProfile
from apps.startups.models import Startup

MODERATE = policies.admin_permission("feed.moderate")
SESSIONS = policies.admin_permission("sessions.manage")
INSIGHTS = policies.admin_permission("dashboard.view")
ERRORS = {
    401: OpenApiResponse(description="Not authenticated"),
    403: OpenApiResponse(description="Not allowed, or MFA missing"),
}


class ConsolePersonSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    name = serializers.CharField()
    email = serializers.EmailField()


# --- the feed ---


class AdminPostQuerySerializer(StrictSerializer):
    q = serializers.CharField(required=False, allow_blank=True, max_length=100, default="")
    category = serializers.ChoiceField(choices=list(CATEGORIES), required=False, default="")
    state = serializers.ChoiceField(
        choices=["live", "hidden", "pinned", "featured", "reported", "scheduled", "team"],
        required=False,
        default="",
    )
    limit = serializers.IntegerField(required=False, min_value=1, max_value=100)
    offset = serializers.IntegerField(required=False, min_value=0)


class AdminPostSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    author = ConsolePersonSerializer()
    category = serializers.CharField()
    excerpt = serializers.CharField()
    created_at = serializers.DateTimeField()
    pinned = serializers.BooleanField()
    pinned_until = serializers.DateTimeField(allow_null=True)
    featured = serializers.BooleanField()
    hidden = serializers.BooleanField()
    official = serializers.BooleanField()
    comments_enabled = serializers.BooleanField()
    audience_roles = serializers.ListField(child=serializers.CharField())
    scheduled_for = serializers.DateTimeField(allow_null=True)
    comment_count = serializers.IntegerField()
    reaction_count = serializers.IntegerField()
    open_reports = serializers.IntegerField()


class AdminPostCommentSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    parent_id = serializers.UUIDField(allow_null=True)
    author = ConsolePersonSerializer()
    text = serializers.CharField()
    hidden = serializers.BooleanField()
    created_at = serializers.DateTimeField()


class AdminPostDetailSerializer(AdminPostSerializer):
    text = serializers.CharField()
    comments = AdminPostCommentSerializer(many=True)


def _post_queryset(*, q: str, category: str, state: str) -> QuerySet[Post]:
    queryset = Post.objects.filter(deleted_at__isnull=True)
    # Posts written ahead are listed only on their own tab, so they are not mistaken for live ones.
    if state == "scheduled":
        return queryset.filter(scheduled_for__isnull=False).order_by("scheduled_for", "id")
    queryset = queryset.filter(scheduled_for__isnull=True)
    if q:
        queryset = queryset.filter(
            Q(body_text__icontains=q)
            | Q(author__email__icontains=q)
            | Q(author__founder_profile__full_name__icontains=q)
        )
    if category:
        queryset = queryset.filter(category=category)
    if state == "hidden":
        queryset = queryset.filter(hidden_at__isnull=False)
    elif state == "live":
        queryset = queryset.filter(hidden_at__isnull=True)
    elif state == "pinned":
        queryset = queryset.filter(pinned_at__isnull=False)
    elif state == "featured":
        queryset = queryset.filter(featured_at__isnull=False)
    elif state == "team":
        queryset = queryset.filter(official=True)
    elif state == "reported":
        reported = Report.objects.filter(status="open", target_type="post").values("target_id")
        queryset = queryset.filter(pk__in=reported)
    return queryset.order_by("-created_at", "-id")


def _post_rows(posts: list[Post]) -> list[dict[str, Any]]:
    who = people(p.author_id for p in posts)
    reports = dict(
        Report.objects.filter(
            status="open", target_type="post", target_id__in=[p.pk for p in posts]
        )
        .values_list("target_id")
        .annotate(n=Count("id"))
        .order_by()
    )
    return [
        {
            "id": p.pk,
            "author": who[p.author_id],
            "category": p.category,
            "excerpt": p.body_text[:240],
            "created_at": p.created_at,
            "pinned": p.pinned_at is not None,
            "pinned_until": p.pinned_until,
            "featured": p.featured_at is not None,
            "hidden": p.hidden_at is not None,
            "official": p.official,
            "comments_enabled": p.comments_enabled,
            "audience_roles": p.audience_roles,
            "scheduled_for": p.scheduled_for,
            "comment_count": p.comment_count,
            "reaction_count": p.reaction_count,
            "open_reports": reports.get(p.pk, 0),
        }
        for p in posts
    ]


class TeamPostSerializer(StrictSerializer):
    """A post from the team: the same fields as a member's, plus the options only the team has."""

    category = serializers.ChoiceField(choices=list(CATEGORIES))
    body = serializers.CharField(
        max_length=20_000,
        trim_whitespace=False,
        allow_blank=True,
        help_text="Required, unless the post shares a course or event.",
    )
    images = serializers.ListField(
        child=ImageInputSerializer(), required=False, default=list, max_length=10
    )
    share = ShareInputSerializer(
        required=False, allow_null=True, default=None, help_text="A course or event to share"
    )
    official = serializers.BooleanField(
        required=False, default=False, help_text="Post as the WO Community team"
    )
    pin = serializers.BooleanField(required=False, default=False)
    pinned_until = serializers.DateTimeField(required=False, allow_null=True, default=None)
    comments_enabled = serializers.BooleanField(required=False, default=True)
    audience_roles = serializers.ListField(
        child=serializers.CharField(max_length=20),
        required=False,
        default=list,
        help_text="Empty means every member",
    )
    scheduled_for = serializers.DateTimeField(required=False, allow_null=True, default=None)


class TeamPostUpdateSerializer(StrictSerializer):
    category = serializers.ChoiceField(choices=list(CATEGORIES), required=False)
    body = serializers.CharField(max_length=20_000, trim_whitespace=False, required=False)
    official = serializers.BooleanField(required=False)
    comments_enabled = serializers.BooleanField(required=False)
    audience_roles = serializers.ListField(
        child=serializers.CharField(max_length=20), required=False
    )
    pinned_until = serializers.DateTimeField(required=False, allow_null=True)
    scheduled_for = serializers.DateTimeField(required=False, allow_null=True)


class AdminPostsView(APIView):
    policy = MODERATE
    pagination_class = AdminLimitOffsetPagination  # documents the page shape

    @extend_schema(
        summary="Post as the team or as yourself",
        description="Skips the daily allowance and is never held for review. Options: post as "
        "the WO Community team, pin (with an optional date it lapses), turn comments off, limit "
        "to members or mentors, and schedule for later. `share` attaches a published course or "
        "event as a card.",
        request=TeamPostSerializer,
        responses={201: AdminPostSerializer, **ERRORS},
        tags=["admin"],
    )
    def post(self, request: Request) -> Response:
        serializer = TeamPostSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        post = feed_services.create_post(
            user_id=cast(UUID, request.user.pk),
            category=data["category"],
            body=data["body"],
            images=data["images"],
            share=data["share"],
            team={
                "actor": request.user,
                "ip": BaseThrottle().get_ident(request) or "",
                "official": data["official"],
                "pin": data["pin"],
                "pinned_until": data["pinned_until"],
                "comments_enabled": data["comments_enabled"],
                "audience_roles": data["audience_roles"],
                "scheduled_for": data["scheduled_for"],
            },
        )
        return Response(AdminPostSerializer(_post_rows([post])[0]).data, status=201)

    @extend_schema(
        summary="Every post, for moderation",
        description="Newest first, hidden ones included. Filter by `category`, `state` "
        "(live, hidden, pinned, featured, reported, team, scheduled) and text.",
        parameters=[AdminPostQuerySerializer],
        responses={200: AdminPostSerializer(many=True), **ERRORS},
        tags=["admin"],
    )
    def get(self, request: Request) -> Response:
        params = AdminPostQuerySerializer(data=request.query_params.dict())
        params.is_valid(raise_exception=True)
        filters = {k: v for k, v in params.validated_data.items() if k not in ("limit", "offset")}
        paginator = AdminLimitOffsetPagination()
        page = paginator.paginate_queryset(_post_queryset(**filters), request, view=self)
        return paginator.get_paginated_response(
            AdminPostSerializer(_post_rows(list(page or [])), many=True).data
        )


class AdminPostView(APIView):
    policy = MODERATE

    @extend_schema(
        summary="Edit any post, or change how the team's post behaves",
        request=TeamPostUpdateSerializer,
        responses={200: AdminPostSerializer, 404: OpenApiResponse(description="No post")},
        tags=["admin"],
    )
    def patch(self, request: Request, post_id: UUID) -> Response:
        serializer = TeamPostUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        post = feed_services.update_team_post(
            actor=request.user,
            post_id=post_id,
            changes=dict(serializer.validated_data),
            ip=BaseThrottle().get_ident(request) or "",
        )
        return Response(AdminPostSerializer(_post_rows([post])[0]).data)

    @extend_schema(
        summary="One post with all of its comments",
        description="Hidden comments are included so they can be restored.",
        responses={200: AdminPostDetailSerializer, 404: OpenApiResponse(description="No post")},
        tags=["admin"],
    )
    def get(self, request: Request, post_id: UUID) -> Response:
        post = Post.objects.filter(pk=post_id, deleted_at__isnull=True).first()
        if post is None:
            raise exceptions.NotFound()
        comments = list(
            Comment.objects.filter(post_id=post_id, deleted_at__isnull=True).order_by(
                "created_at", "id"
            )
        )
        who = people(c.author_id for c in comments)
        view = _post_rows([post])[0]
        view["text"] = post.body_text
        view["comments"] = [
            {
                "id": c.pk,
                "parent_id": c.parent_id,
                "author": who[c.author_id],
                "text": strip_tags(c.body)[:1000],
                "hidden": c.hidden_at is not None,
                "created_at": c.created_at,
            }
            for c in comments
        ]
        return Response(AdminPostDetailSerializer(view).data)


class FeedStatsSerializer(serializers.Serializer):
    posts = serializers.IntegerField()
    posts_last_7_days = serializers.IntegerField()
    comments = serializers.IntegerField()
    reactions = serializers.IntegerField()
    hidden = serializers.IntegerField()
    pinned = serializers.IntegerField()
    open_reports = serializers.IntegerField()


class AdminFeedStatsView(APIView):
    policy = MODERATE

    @extend_schema(
        summary="Feed totals for the moderation page",
        responses={200: FeedStatsSerializer, **ERRORS},
        tags=["admin"],
    )
    def get(self, request: Request) -> Response:
        live = Post.objects.filter(deleted_at__isnull=True)
        week = timezone.now() - timedelta(days=7)
        return Response(
            FeedStatsSerializer(
                {
                    "posts": live.count(),
                    "posts_last_7_days": live.filter(created_at__gte=week).count(),
                    "comments": Comment.objects.filter(deleted_at__isnull=True).count(),
                    "reactions": Reaction.objects.count(),
                    "hidden": live.filter(hidden_at__isnull=False).count(),
                    "pinned": live.filter(pinned_at__isnull=False).count(),
                    "open_reports": Report.objects.filter(status="open").count(),
                }
            ).data
        )


# --- mentoring pairs ---


class AdminMatchQuerySerializer(StrictSerializer):
    q = serializers.CharField(required=False, allow_blank=True, max_length=100, default="")
    state = serializers.ChoiceField(
        choices=["active", "completed", "idle"], required=False, default=""
    )
    limit = serializers.IntegerField(required=False, min_value=1, max_value=100)
    offset = serializers.IntegerField(required=False, min_value=0)


class AdminMatchSerializer(serializers.Serializer):
    mentor = ConsolePersonSerializer()
    mentee = ConsolePersonSerializer()
    sessions = serializers.IntegerField()
    completed = serializers.IntegerField()
    upcoming = serializers.IntegerField()
    waiting = serializers.IntegerField()
    last_at = serializers.DateTimeField()
    next_at = serializers.DateTimeField(allow_null=True)
    state = serializers.ChoiceField(choices=["active", "completed", "idle"])


def _match_state(upcoming: int, waiting: int, completed: int) -> str:
    if upcoming or waiting:
        return "active"
    return "completed" if completed else "idle"


class AdminMatchesView(APIView):
    policy = SESSIONS
    pagination_class = AdminLimitOffsetPagination  # documents the page shape

    @extend_schema(
        summary="Mentor and founder pairs",
        description="Everyone who has asked a mentor for a session, one row per pair, with how "
        "many sessions they have had and whether they are still working together. `active` is a "
        "pair with a request waiting or a session coming up.",
        parameters=[AdminMatchQuerySerializer],
        responses={200: AdminMatchSerializer(many=True), **ERRORS},
        tags=["admin"],
    )
    def get(self, request: Request) -> Response:
        params = AdminMatchQuerySerializer(data=request.query_params.dict())
        params.is_valid(raise_exception=True)
        now = timezone.now()
        pairs = (
            MentorSession.objects.values("mentor_id", "mentee_id")
            .annotate(
                total=Count("id"),
                completed=Count("id", filter=Q(status="completed")),
                upcoming=Count("id", filter=Q(status="confirmed", starts_at__gt=now)),
                waiting=Count("id", filter=Q(status="requested")),
                last_at=Max("starts_at"),
                next_at=Max("starts_at", filter=Q(status="confirmed", starts_at__gt=now)),
            )
            .order_by()
        )
        who = people(
            [p["mentor_id"] for p in pairs] + [p["mentee_id"] for p in pairs],
        )
        rows = []
        for p in pairs:
            rows.append(
                {
                    "mentor": who[p["mentor_id"]],
                    "mentee": who[p["mentee_id"]],
                    "sessions": p["total"],
                    "completed": p["completed"],
                    "upcoming": p["upcoming"],
                    "waiting": p["waiting"],
                    "last_at": p["last_at"],
                    "next_at": p["next_at"],
                    "state": _match_state(p["upcoming"], p["waiting"], p["completed"]),
                }
            )
        text = params.validated_data["q"].lower()
        if text:
            rows = [
                r
                for r in rows
                if text in f"{r['mentor']['name']} {r['mentor']['email']} "
                f"{r['mentee']['name']} {r['mentee']['email']}".lower()
            ]
        if params.validated_data["state"]:
            rows = [r for r in rows if r["state"] == params.validated_data["state"]]
        rows.sort(key=lambda r: r["last_at"], reverse=True)
        paginator = AdminLimitOffsetPagination()
        page: Any = paginator.paginate_queryset(cast(Any, rows), request, view=self)
        return paginator.get_paginated_response(AdminMatchSerializer(page, many=True).data)


# --- analytics ---


class SeriesPointSerializer(serializers.Serializer):
    day = serializers.DateField()
    count = serializers.IntegerField()
    previous = serializers.IntegerField(help_text="The same day of the range before")


class StatSerializer(serializers.Serializer):
    key = serializers.CharField()
    title = serializers.CharField()
    value = serializers.IntegerField()
    previous = serializers.IntegerField()


class CountRowSerializer(serializers.Serializer):
    name = serializers.CharField()
    count = serializers.IntegerField()


class AnalyticsSeriesSerializer(serializers.Serializer):
    key = serializers.CharField()
    title = serializers.CharField()
    points = SeriesPointSerializer(many=True)


class BreakdownSerializer(serializers.Serializer):
    key = serializers.CharField()
    title = serializers.CharField()
    rows = CountRowSerializer(many=True)


class AnalyticsSerializer(serializers.Serializer):
    start = serializers.DateField()
    end = serializers.DateField()
    days = serializers.IntegerField()
    stats = StatSerializer(many=True)
    series = AnalyticsSeriesSerializer(many=True)
    breakdowns = BreakdownSerializer(many=True)
    funnel = CountRowSerializer(many=True)


def _bounds(start: date, end: date) -> tuple[datetime, datetime]:
    tz = timezone.get_current_timezone()
    return (
        datetime.combine(start, time.min, tzinfo=tz),
        datetime.combine(end + timedelta(days=1), time.min, tzinfo=tz),
    )


def _daily(queryset: QuerySet[Any], field: str, start: date, end: date) -> list[dict[str, Any]]:
    lo, hi = _bounds(start, end)
    rows = dict(
        queryset.filter(**{f"{field}__gte": lo, f"{field}__lt": hi})
        .annotate(day=TruncDate(field))
        .values_list("day")
        .annotate(n=Count("id"))
        .order_by("day")
    )
    out = []
    day = start
    while day <= end:
        out.append({"day": day, "count": rows.get(day, 0)})
        day += timedelta(days=1)
    return out


def _between(queryset: QuerySet[Any], field: str, start: date, end: date) -> int:
    lo, hi = _bounds(start, end)
    return queryset.filter(**{f"{field}__gte": lo, f"{field}__lt": hi}).count()


def _top(counter: Counter[str], limit: int = 8) -> list[dict[str, Any]]:
    return [{"name": name or "Not given", "count": n} for name, n in counter.most_common(limit)]


def build_analytics(start: date, end: date) -> dict[str, Any]:
    days = (end - start).days + 1
    prev_end = start - timedelta(days=1)
    prev_start = prev_end - timedelta(days=days - 1)

    sources: list[tuple[str, str, QuerySet[Any], str]] = [
        ("members", "New members", User.objects.all(), "created_at"),
        ("posts", "Posts", Post.objects.filter(deleted_at__isnull=True), "created_at"),
        ("comments", "Comments", Comment.objects.filter(deleted_at__isnull=True), "created_at"),
        ("sessions", "Mentoring requests", MentorSession.objects.all(), "created_at"),
        ("enrolments", "Course enrolments", Enrolment.objects.all(), "started_at"),
        ("rsvps", "Event sign ups", EventRegistration.objects.all(), "created_at"),
    ]
    stats = [
        {
            "key": key,
            "title": label,
            "value": _between(qs, field, start, end),
            "previous": _between(qs, field, prev_start, prev_end),
        }
        for key, label, qs, field in sources
    ]
    series = [
        {
            "key": key,
            "title": label,
            "points": [
                {**now, "previous": before["count"]}
                for now, before in zip(
                    _daily(qs, field, start, end),
                    _daily(qs, field, prev_start, prev_end),
                    strict=True,
                )
            ],
        }
        for key, label, qs, field in sources
    ]

    country = Counter(
        FounderProfile.objects.filter(user__status="active").values_list("country", flat=True)
    )
    sectors = Counter(Startup.objects.values_list("sector__name", flat=True))
    stages = Counter(Startup.objects.values_list("stage__name", flat=True))
    post_cats = Counter(
        Post.objects.filter(deleted_at__isnull=True).values_list("category", flat=True)
    )
    job_types = Counter(Job.objects.filter(status="published").values_list("type", flat=True))
    session_states = Counter(MentorSession.objects.values_list("status", flat=True))
    breakdowns = [
        {"key": "country", "title": "Members by country", "rows": _top(country)},
        {"key": "sector", "title": "Startups by sector", "rows": _top(sectors)},
        {"key": "stage", "title": "Startups by stage", "rows": _top(stages)},
        {"key": "category", "title": "Posts by category", "rows": _top(post_cats)},
        {"key": "job_type", "title": "Live jobs by type", "rows": _top(job_types)},
        {"key": "session_status", "title": "Mentoring by status", "rows": _top(session_states)},
    ]

    lo, hi = _bounds(start, end)
    cohort = User.objects.filter(created_at__gte=lo, created_at__lt=hi)
    ids = cohort.values("pk")
    funnel = [
        {"name": "Signed up", "count": cohort.count()},
        {
            "name": "Confirmed their email",
            "count": cohort.filter(email_verified_at__isnull=False).count(),
        },
        {"name": "Approved", "count": cohort.filter(approved_at__isnull=False).count()},
        {
            "name": "Took part (posted, commented or enrolled)",
            "count": cohort.filter(
                Q(feed_posts__isnull=False)
                | Q(feed_comments__isnull=False)
                | Q(enrolments__isnull=False)
            )
            .distinct()
            .count(),
        },
        {
            "name": "Asked a mentor for a session",
            "count": MentorSession.objects.filter(mentee_id__in=ids)
            .values("mentee_id")
            .distinct()
            .count(),
        },
    ]
    return {
        "start": start,
        "end": end,
        "days": days,
        "stats": stats,
        "series": series,
        "breakdowns": breakdowns,
        "funnel": funnel,
    }


class AdminAnalyticsView(APIView):
    policy = INSIGHTS

    @extend_schema(
        summary="Community analytics, counted live",
        description="Totals for the range and the range before it, a count per day, "
        "breakdowns of who is here and what they do, and a funnel for people who signed up in "
        "the range. Defaults to the last 30 days; the range is at most 366 days.",
        parameters=[RangeQuerySerializer],
        responses={200: AnalyticsSerializer, **ERRORS},
        tags=["admin"],
    )
    def get(self, request: Request) -> Response:
        params = RangeQuerySerializer(data=request.query_params)
        params.is_valid(raise_exception=True)
        today = timezone.localdate()
        end = params.validated_data.get("end") or today
        start = params.validated_data.get("start") or end - timedelta(days=29)
        if start > end:
            raise exceptions.ValidationError({"from": ["The start must be before the end."]})
        if (end - start).days > 365:
            raise exceptions.ValidationError({"from": ["Choose a range of a year or less."]})
        return Response(AnalyticsSerializer(build_analytics(start, end)).data)
