"""Admin dashboards: summary tables refreshed by a job, and the figures read from them.

The console never scans raw events. A job turns the last couple of days of activity into one
number per metric per day (``DailyMetric``) and takes snapshots of the community's current shape.
Every dashboard request reads those small tables.
"""

from datetime import UTC, date, datetime, time, timedelta
from typing import Any

import structlog
from django.db import transaction
from django.utils import timezone
from rest_framework import exceptions

from apps.accounts import services as accounts
from apps.adminconsole import selectors as queues
from apps.adminconsole.models import DailyMetric, DashboardState
from apps.analytics import registry
from apps.analytics import services as analytics
from apps.audit import services as audit
from apps.campaigns import services as campaigns
from apps.jobs import selectors as jobs
from apps.learning import selectors as learning
from apps.mentorship import selectors as mentorship
from apps.profiles import selectors as profiles
from apps.reference import selectors as reference
from apps.startups import selectors as startups

logger = structlog.get_logger(__name__)

MAX_RANGE_DAYS = 366
RETENTION_WINDOWS = (30, 60, 90)

# Metrics stored once per day, with what they mean. ``events.<name>`` metrics (one per analytics
# event) are added to this list below.
DAILY_METRICS: dict[str, str] = {
    "registrations": "New accounts created",
    "active_members": "Different members who logged in that day",
    "wau": "Different members who logged in during the 7 days up to that day",
    "mau": "Different members who logged in during the 30 days up to that day",
    "approval_time_hours": "Average hours from registration to an admin's decision",
}
# Current-shape snapshots, one set of rows per refresh day.
SNAPSHOT_METRICS = (
    "members_active",
    "members_pending",
    "registered_7d",
    "registered_30d",
    "retention_30",
    "retention_60",
    "retention_90",
    "jobs_live",
    "members_by_country",
    "startups_by_sector",
    "startups_by_stage",
)
FUNNEL_STEPS = (
    ("directory_viewed", "Viewed the directory"),
    ("registration_started", "Started registering"),
    ("registration_step_completed", "Completed a registration step"),
    ("email_verified", "Verified their email"),
    ("member_approved", "Were approved"),
)


def event_metric(name: str) -> str:
    return f"events.{name}"


def known_metrics() -> dict[str, str]:
    metrics = dict(DAILY_METRICS)
    for name in registry.EVENTS:
        metrics[event_metric(name)] = f"Times the '{name}' event was recorded"
    return metrics


def _start_of(day: date) -> datetime:
    return datetime.combine(day, time.min, tzinfo=UTC)


def _put(day: date, metric: str, value: float, dimension: str = "") -> None:
    DailyMetric.objects.update_or_create(
        day=day, metric=metric, dimension=dimension, defaults={"value": float(value)}
    )


# --- refreshing ---


def refresh(days: int = 2) -> int:
    """Recompute the last ``days`` days of daily metrics and today's snapshots.

    Safe to run any time and as often as wanted: each number is overwritten with the current truth,
    so a late event or a re-run never double counts.
    """
    now = timezone.now()
    today = now.date()
    first = today - timedelta(days=days - 1)
    start, end = _start_of(first), _start_of(today + timedelta(days=1))
    written = 0
    with transaction.atomic():
        registrations = accounts.registrations_by_day(start, end)
        logins = audit.distinct_actors_by_day("auth.login", start, end)
        counts = analytics.daily_event_counts(start, end)
        approval_hours = analytics.daily_property_average(
            ["member_approved", "member_rejected"], "time_to_decision_hours", start, end
        )
        names = list(registry.EVENTS)
        for offset in range(days):
            day = first + timedelta(days=offset)
            _put(day, "registrations", registrations.get(day, 0))
            _put(day, "active_members", logins.get(day, 0))
            window_end = _start_of(day + timedelta(days=1))
            _put(
                day,
                "wau",
                audit.distinct_actors_between(
                    "auth.login", window_end - timedelta(days=7), window_end
                ),
            )
            _put(
                day,
                "mau",
                audit.distinct_actors_between(
                    "auth.login", window_end - timedelta(days=30), window_end
                ),
            )
            if day in approval_hours:
                _put(day, "approval_time_hours", round(approval_hours[day], 2))
            for name in names:
                _put(day, event_metric(name), counts.get((day, name), 0))
            written += 5 + len(names)
        written += _snapshot(now)
        state, _ = DashboardState.objects.get_or_create(id=1)
        state.refreshed_at = now
        state.save()
    return written


def _snapshot(now: datetime) -> int:
    today = now.date()
    DailyMetric.objects.filter(day=today, metric__in=SNAPSHOT_METRICS).delete()
    rows: list[DailyMetric] = []

    def add(metric: str, value: float, dimension: str = "") -> None:
        rows.append(DailyMetric(day=today, metric=metric, dimension=dimension, value=float(value)))

    numbers = accounts.member_numbers(now)
    add("members_active", numbers["active"])
    add("members_pending", numbers["pending"])
    add("registered_7d", numbers["registered_7d"])
    add("registered_30d", numbers["registered_30d"])
    for window in RETENTION_WINDOWS:
        value = accounts.retention(now, window)
        if value is not None:
            add(f"retention_{window}", value)
    add("jobs_live", jobs.live_count())
    for country, count in profiles.active_member_counts_by_country().items():
        add("members_by_country", count, country)
    sector_slugs = [s.slug for s in reference.sectors()]
    for slug, count in startups.count_by_sector(sector_slugs).items():
        add("startups_by_sector", count, slug)
    stage_slugs = [s.slug for s in reference.stages()]
    for slug, count in startups.count_by_stage(stage_slugs).items():
        add("startups_by_stage", count, slug)
    DailyMetric.objects.bulk_create(rows)
    return len(rows)


def backfill(days: int) -> int:
    """Rebuild a longer stretch of history, for a fresh install or after a fix."""
    return refresh(days=min(days, MAX_RANGE_DAYS))


# --- reading ---


def _range(start: date | None, end: date | None, default_days: int = 30) -> tuple[date, date]:
    end = end or timezone.now().date()
    start = start or end - timedelta(days=default_days - 1)
    if start > end:
        raise exceptions.ValidationError({"from": ["Must not be after the end date."]})
    if (end - start).days >= MAX_RANGE_DAYS:
        raise exceptions.ValidationError({"from": [f"At most {MAX_RANGE_DAYS} days at a time."]})
    return start, end


def series(metric: str, start: date | None, end: date | None) -> dict[str, Any]:
    """One value per day. Counts are 0 on quiet days; averages are null when there is no data."""
    description = known_metrics().get(metric)
    if description is None:
        raise exceptions.ValidationError({"metric": ["Unknown metric."]})
    first, last = _range(start, end)
    stored = {
        row.day: row.value
        for row in DailyMetric.objects.filter(
            metric=metric, dimension="", day__gte=first, day__lte=last
        )
    }
    is_average = metric == "approval_time_hours"
    points = []
    day = first
    while day <= last:
        value = stored.get(day)
        points.append({"date": day, "value": value if value is not None or is_average else 0.0})
        day += timedelta(days=1)
    return {
        "metric": metric,
        "description": description,
        "points": points,
        "total": _total(metric, points),
    }


def _total(metric: str, points: list[dict[str, Any]]) -> float | None:
    values = [p["value"] for p in points if p["value"] is not None]
    if metric in ("wau", "mau", "approval_time_hours"):
        return round(sum(values) / len(values), 2) if values else None
    return float(sum(values))


def _sum(metric: str, first: date, last: date) -> float:
    rows = DailyMetric.objects.filter(metric=metric, dimension="", day__gte=first, day__lte=last)
    return float(sum(r.value for r in rows))


def funnel(start: date | None, end: date | None) -> dict[str, Any]:
    """Visitor to member, step by step, with how many carried on from the step before.

    Early steps are reported by visitors' browsers and only for people who agreed to analytics,
    so they understate real traffic; the later, server-side steps are exact.
    """
    first, last = _range(start, end)
    steps = []
    previous: float | None = None
    top: float | None = None
    for name, label in FUNNEL_STEPS:
        count = _sum(event_metric(name), first, last)
        top = count if top is None else top
        steps.append(
            {
                "step": name,
                "title": label,
                "count": count,
                "from_previous": round(count / previous, 4) if previous else None,
                "from_start": round(count / top, 4) if top else None,
            }
        )
        previous = count
    return {"from": first, "to": last, "steps": steps}


def _latest_snapshot(metric: str) -> tuple[date | None, dict[str, float]]:
    day = (
        DailyMetric.objects.filter(metric=metric)
        .order_by("-day")
        .values_list("day", flat=True)
        .first()
    )
    if day is None:
        return None, {}
    rows = DailyMetric.objects.filter(metric=metric, day=day)
    return day, {r.dimension: r.value for r in rows}


def _single(metric: str) -> float | None:
    _, values = _latest_snapshot(metric)
    return values.get("")


def _top(metric: str, limit: int = 10) -> list[dict[str, Any]]:
    _, values = _latest_snapshot(metric)
    ranked = sorted(values.items(), key=lambda item: (-item[1], item[0]))[:limit]
    return [{"name": name, "count": int(count)} for name, count in ranked]


def home(actor: Any) -> dict[str, Any]:
    """Everything the console's home page shows."""
    today = timezone.now().date()
    last30, previous30 = today - timedelta(days=29), today - timedelta(days=59)
    now_registered = _sum("registrations", last30, today)
    before_registered = _sum("registrations", previous30, last30 - timedelta(days=1))
    state = DashboardState.objects.filter(id=1).first()
    newsletters = campaigns.recent_reports(5)
    sent = sum(c["sent"] for c in newsletters)
    return {
        "refreshed_at": state.refreshed_at if state else None,
        "pending": queues.queue_counts(),
        "community": {
            "active_members": _int(_single("members_active")),
            "pending_members": _int(_single("members_pending")),
            "registered_last_7_days": _int(_single("registered_7d")),
            "registered_last_30_days": int(now_registered),
            "registered_previous_30_days": int(before_registered),
            "growth": (
                round((now_registered - before_registered) / before_registered, 4)
                if before_registered
                else None
            ),
            "retention": {f"day_{w}": _single(f"retention_{w}") for w in RETENTION_WINDOWS},
            "by_country": _top("members_by_country"),
            "startups_by_sector": _top("startups_by_sector"),
            "startups_by_stage": _top("startups_by_stage"),
        },
        "activity": {
            "daily_active": _latest_value("active_members"),
            "weekly_active": _latest_value("wau"),
            "monthly_active": _latest_value("mau"),
            "posts_last_7_days": int(
                _sum(event_metric("post_created"), today - timedelta(days=6), today)
            ),
            "comments_last_7_days": int(
                _sum(event_metric("comment_created"), today - timedelta(days=6), today)
            ),
            "reactions_last_7_days": int(
                _sum(event_metric("post_reacted"), today - timedelta(days=6), today)
            ),
            "jobs_live": _int(_single("jobs_live")),
            "jobs_posted_last_30_days": int(_sum(event_metric("job_created"), last30, today)),
            "average_hours_to_approval": series("approval_time_hours", last30, today)["total"],
        },
        "email": {
            "recent_campaigns": [
                {
                    "id": c["id"],
                    "name": c["name"],
                    "started_at": c["started_at"],
                    "sent": c["sent"],
                    "open_rate": c["open_rate"],
                    "click_rate": c["click_rate"],
                    "unsubscribed": c["unsubscribed"],
                }
                for c in newsletters
            ],
            "average_open_rate": (
                round(sum(c["opened"] for c in newsletters) / sent, 4) if sent else None
            ),
            "average_click_rate": (
                round(sum(c["clicked"] for c in newsletters) / sent, 4) if sent else None
            ),
        },
        # Arrive with their modules in later stages.
        "learning": _learning(today),
        "mentorship": {"available": True, **mentorship.snapshot()},
        "revenue": {"available": False},
    }


def _learning(today: date) -> dict[str, Any]:
    figures = learning.snapshot()
    last30 = today - timedelta(days=29)
    return {
        "available": True,
        "published_courses": figures["published_courses"],
        "enrolments": figures["enrolments"],
        "completed": figures["completed"],
        "completion_rate": (
            round(figures["completed"] / figures["enrolments"], 4)
            if figures["enrolments"]
            else None
        ),
        "certificates": figures["certificates"],
        "enrolments_last_30_days": int(_sum(event_metric("course_enrolled"), last30, today)),
        "lessons_completed_last_30_days": int(
            _sum(event_metric("lesson_completed"), last30, today)
        ),
    }


def _int(value: float | None) -> int | None:
    return None if value is None else int(value)


def _latest_value(metric: str) -> int | None:
    row = DailyMetric.objects.filter(metric=metric, dimension="").order_by("-day").first()
    return None if row is None else int(row.value)
