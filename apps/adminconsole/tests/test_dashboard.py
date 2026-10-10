import uuid
from datetime import timedelta

import pytest
from django.conf import settings
from django.utils import timezone

from apps.accounts.models import User
from apps.adminconsole import dashboard
from apps.adminconsole.models import DailyMetric, DashboardState
from apps.analytics import services as analytics
from apps.analytics.models import AnalyticsEvent
from apps.audit import services as audit

pytestmark = pytest.mark.django_db

BASE = "/api/v1/admin/dashboard"


@pytest.fixture
def admin(make_user):
    return make_user(roles=("community_admin",), email="admin@example.com")


@pytest.fixture
def as_admin(admin, client_for):
    return client_for(admin, mfa_age=5)


def member(make_user, email, **fields):
    return make_user(
        email=email, approved_at=timezone.now(), email_verified_at=timezone.now(), **fields
    )


def login(user):
    audit.record(actor=user, action="auth.login", target_type="session", target_id=user.pk)
    return user


def metric(name, day=None, dimension=""):
    row = DailyMetric.objects.filter(
        metric=name, dimension=dimension, day=day or timezone.now().date()
    ).first()
    return None if row is None else row.value


# --- refreshing ---


def test_a_refresh_turns_todays_activity_into_numbers(make_user, admin):
    one, two = member(make_user, "a@example.com"), member(make_user, "b@example.com")
    login(one)
    login(one)  # logging in twice is still one person
    login(two)
    analytics.track("post_created", actor_id=one.pk, properties={"category": "update"})
    analytics.track("post_created", actor_id=two.pk, properties={"category": "win"})
    dashboard.refresh(days=1)
    assert metric("registrations") == 3  # admin and the two members
    assert metric("active_members") == 2 and metric("wau") == 2 and metric("mau") == 2
    assert metric("events.post_created") == 2
    assert metric("events.comment_created") == 0
    assert DashboardState.objects.get().refreshed_at is not None


def test_refreshing_again_overwrites_instead_of_double_counting(make_user):
    member(make_user, "a@example.com")
    dashboard.refresh(days=2)
    first = DailyMetric.objects.count()
    analytics.track(
        "post_created",
        actor_id=member(make_user, "b@example.com").pk,
        properties={"category": "update"},
    )
    dashboard.refresh(days=2)
    dashboard.refresh(days=2)
    assert DailyMetric.objects.count() == first  # same rows, updated in place
    assert metric("events.post_created") == 1 and metric("registrations") == 2


def test_each_day_is_counted_on_its_own_day(make_user):
    old = member(make_user, "old@example.com")
    User.objects.filter(pk=old.pk).update(created_at=timezone.now() - timedelta(days=1, hours=1))
    member(make_user, "new@example.com")
    dashboard.refresh(days=3)
    today = timezone.now().date()
    assert metric("registrations", today) == 1
    assert metric("registrations", today - timedelta(days=1)) == 1
    assert metric("registrations", today - timedelta(days=2)) == 0


def test_the_average_time_to_a_decision_comes_from_approval_and_rejection_events(make_user):
    user = member(make_user, "a@example.com")
    analytics.track(
        "member_approved",
        actor_id=user.pk,
        properties={"approval_source": "admin", "time_to_decision_hours": 10},
    )
    analytics.track("member_rejected", actor_id=user.pk, properties={"time_to_decision_hours": 30})
    dashboard.refresh(days=1)
    assert metric("approval_time_hours") == 20  # the average of 10 and 30 hours


def test_snapshots_describe_the_community_as_it_is(make_user, client_for):
    from apps.profiles.models import FounderProfile
    from apps.profiles.services import get_or_create_profile
    from apps.startups.tests.conftest import STARTUPS, new_startup_body

    ng = member(make_user, "ng@example.com")
    ke = member(make_user, "ke@example.com")
    member(make_user, "pending@example.com", status="pending")
    for user, country in ((ng, "NG"), (ke, "KE")):
        FounderProfile.objects.filter(pk=get_or_create_profile(user.pk).pk).update(country=country)
    client_for(ng).post(STARTUPS, new_startup_body(sector="fintech", stage="seed"))
    dashboard.refresh(days=1)
    assert metric("members_active") == 2 and metric("members_pending") == 1
    assert (
        metric("members_by_country", dimension="NG") == 1
        and metric("members_by_country", dimension="KE") == 1
    )
    assert metric("startups_by_sector", dimension="fintech") == 1
    assert metric("startups_by_stage", dimension="seed") == 1
    # a second refresh replaces today's snapshot rather than adding to it
    dashboard.refresh(days=1)
    assert DailyMetric.objects.filter(metric="members_by_country").count() == 2


def test_retention_measures_members_old_enough(make_user):
    now = timezone.now()
    stayed = member(make_user, "stayed@example.com")
    left = member(make_user, "left@example.com")
    for user in (stayed, left):
        User.objects.filter(pk=user.pk).update(approved_at=now - timedelta(days=40))
    User.objects.filter(pk=stayed.pk).update(last_login=now - timedelta(days=2))
    User.objects.filter(pk=left.pk).update(last_login=now - timedelta(days=35))
    dashboard.refresh(days=1)
    assert metric("retention_30") == 0.5
    assert metric("retention_60") is None  # nobody has been here 60 days yet


def test_a_late_event_is_picked_up_by_the_next_refresh(make_user):
    dashboard.refresh(days=2)
    yesterday = timezone.now() - timedelta(days=1)
    AnalyticsEvent.objects.create(
        seq=999_001,
        name="job_created",
        properties={"job_type": "contract"},
        source="server",
        occurred_at=yesterday,
        received_at=timezone.now(),
    )
    assert metric("events.job_created", yesterday.date()) == 0
    dashboard.refresh(days=2)
    assert metric("events.job_created", yesterday.date()) == 1


# --- reading series ---


def get_series(client, **params):
    return client.get(f"{BASE}/series", params)


def test_a_series_has_a_point_for_every_day_with_zeros_filled_in(as_admin, make_user):
    member(make_user, "a@example.com")
    dashboard.refresh(days=1)
    today = timezone.now().date()
    start = today - timedelta(days=4)
    body = get_series(
        as_admin, metric="registrations", **{"from": start.isoformat(), "to": today.isoformat()}
    ).json()
    assert len(body["points"]) == 5
    assert [p["value"] for p in body["points"]][-2:] == [0.0, 2.0]  # the admin and the member
    assert body["total"] == 2.0 and body["description"]


def test_averaged_metrics_leave_quiet_days_empty(as_admin):
    body = get_series(as_admin, metric="approval_time_hours").json()
    assert all(p["value"] is None for p in body["points"]) and body["total"] is None


def test_any_analytics_event_can_be_charted(as_admin, make_user):
    analytics.track("comment_created", actor_id=member(make_user, "a@example.com").pk)
    dashboard.refresh(days=1)
    body = get_series(as_admin, metric="events.comment_created").json()
    assert body["total"] == 1.0


def test_the_default_range_is_the_last_thirty_days(as_admin):
    assert len(get_series(as_admin, metric="registrations").json()["points"]) == 30


@pytest.mark.parametrize(
    "params",
    [
        {},
        {"metric": "nonsense"},
        {"metric": "events.nonsense"},
        {"metric": "registrations", "from": "2026-02-01", "to": "2026-01-01"},
        {"metric": "registrations", "from": "2024-01-01", "to": "2026-01-01"},
        {"metric": "registrations", "from": "yesterday"},
        {"metric": "registrations", "x": 1},
    ],
)
def test_bad_series_requests_are_refused(as_admin, params):
    assert get_series(as_admin, **params).status_code == 400


def test_the_list_of_metrics_covers_daily_figures_and_every_event(as_admin):
    names = {m["metric"] for m in as_admin.get(f"{BASE}/metrics").json()}
    assert {"registrations", "active_members", "wau", "mau", "events.post_created"} <= names


# --- the funnel ---


def test_the_funnel_counts_each_step_and_conversion(as_admin, make_user):
    user = member(make_user, "a@example.com")
    for _ in range(10):
        analytics.track("directory_viewed", anonymous_id=uuid.uuid4(), source="client")
    for _ in range(4):
        analytics.track(
            "registration_started",
            anonymous_id=uuid.uuid4(),
            properties={"source": "organic"},
            source="client",
        )
    analytics.track("email_verified", actor_id=user.pk)
    analytics.track(
        "member_approved",
        actor_id=user.pk,
        properties={"approval_source": "admin", "time_to_decision_hours": 5},
    )
    dashboard.refresh(days=1)
    body = as_admin.get(f"{BASE}/funnel").json()
    steps = {s["step"]: s for s in body["steps"]}
    assert [s["step"] for s in body["steps"]][0] == "directory_viewed"
    assert (
        steps["directory_viewed"]["count"] == 10
        and steps["directory_viewed"]["from_previous"] is None
    )
    assert (
        steps["registration_started"]["count"] == 4
        and steps["registration_started"]["from_previous"] == 0.4
    )
    assert steps["member_approved"]["from_start"] == 0.1
    assert steps["registration_step_completed"]["count"] == 0
    assert (
        steps["email_verified"]["from_previous"] is None
    )  # nothing in the step before to divide by


def test_the_funnel_takes_a_date_range_and_refuses_bad_ones(as_admin):
    ok = as_admin.get(f"{BASE}/funnel", {"from": "2026-01-01", "to": "2026-01-31"})
    assert ok.status_code == 200 and ok.json()["from"] == "2026-01-01"
    assert (
        as_admin.get(f"{BASE}/funnel", {"from": "2026-02-01", "to": "2026-01-01"}).status_code
        == 400
    )
    assert as_admin.get(f"{BASE}/funnel", {"foo": 1}).status_code == 400


# --- the home page ---


def test_home_shows_queues_community_activity_and_email(as_admin, make_user):
    pending = member(make_user, "p@example.com", status="pending", roles=())
    active = member(make_user, "a@example.com")
    login(active)
    analytics.track("post_created", actor_id=active.pk, properties={"category": "update"})
    dashboard.refresh(days=2)
    body = as_admin.get(BASE).json()
    assert (
        body["pending"]["registrations_awaiting_approval"] >= 0
        and "open_reports" in body["pending"]
    )
    assert body["community"]["active_members"] == 2  # admin and one member
    assert body["community"]["pending_members"] == 1
    assert body["community"]["registered_last_30_days"] == 3
    assert body["activity"]["daily_active"] == 1 and body["activity"]["posts_last_7_days"] == 1
    assert body["email"] == {
        "recent_campaigns": [],
        "average_open_rate": None,
        "average_click_rate": None,
    }
    assert body["refreshed_at"] is not None and pending


def test_unbuilt_areas_say_so(as_admin):
    body = as_admin.get(BASE).json()
    assert body["mentorship"] == body["revenue"] == {"available": False}
    assert body["learning"]["available"] is True and body["learning"]["enrolments"] == 0


def test_home_works_before_the_first_refresh(as_admin):
    body = as_admin.get(BASE).json()
    assert body["refreshed_at"] is None and body["community"]["active_members"] is None
    assert body["community"]["growth"] is None and body["community"]["by_country"] == []


def test_growth_compares_with_the_previous_thirty_days(as_admin, make_user):
    for i in range(3):
        user = member(make_user, f"old{i}@example.com")
        User.objects.filter(pk=user.pk).update(created_at=timezone.now() - timedelta(days=40))
    member(make_user, "new@example.com")
    dashboard.refresh(days=60)
    body = as_admin.get(BASE).json()["community"]
    assert body["registered_previous_30_days"] == 3
    assert body["registered_last_30_days"] == 2  # the admin and the new member
    assert body["growth"] == round((2 - 3) / 3, 4)


def test_the_email_snapshot_reflects_recent_campaigns(as_admin, admin, make_user):
    from apps.accounts import services as accounts
    from apps.campaigns import services as campaigns
    from apps.campaigns.models import Segment
    from apps.campaigns.tests.conftest import BLOCKS

    subscriber = member(make_user, "reader@example.com")
    accounts.set_marketing_consent(subscriber.pk, True)
    segment = Segment.objects.create(name="all", definition={})
    campaign = campaigns.create_campaign(
        actor=admin, data={"name": "Oct", "subject": "Hi", "blocks": BLOCKS}
    )
    campaign.segment = segment
    campaign.save()
    campaigns.send_now(actor=admin, campaign_id=campaign.pk)
    campaigns.send_batch(campaign.pk)
    recipient = campaign.recipients.get()
    campaigns.record_delivery("opened", recipient.provider_message_id)
    email = as_admin.get(BASE).json()["email"]
    assert (
        email["recent_campaigns"][0]["name"] == "Oct" and email["recent_campaigns"][0]["sent"] == 1
    )
    assert email["average_open_rate"] == 1.0 and email["average_click_rate"] == 0.0


def test_the_home_page_never_touches_the_raw_event_table(
    as_admin, make_user, django_assert_max_num_queries
):
    for i in range(30):
        analytics.track(
            "post_created",
            actor_id=member(make_user, f"u{i}@example.com").pk,
            properties={"category": "update"},
        )
    dashboard.refresh(days=1)
    from django.db import connection
    from django.test.utils import CaptureQueriesContext

    with CaptureQueriesContext(connection) as queries:
        assert as_admin.get(BASE).status_code == 200
    assert not [q for q in queries if "analytics_event" in q["sql"]]
    assert len(queries) < 60


# --- the refresh button and schedule ---


def test_a_super_admin_can_refresh_on_demand(make_user, client_for, db):
    root = client_for(make_user(roles=("super_admin",), email="root@example.com"), mfa_age=5)
    response = root.post(f"{BASE}/refresh")
    assert response.status_code == 202
    assert DashboardState.objects.get().refreshed_at is not None  # tasks run inline in tests


def test_the_refresh_runs_hourly():
    entry = settings.CELERY_BEAT_SCHEDULE["dashboard-refresh"]
    assert entry["task"] == "adminconsole.refresh_dashboard" and entry["schedule"] == 3600.0


# --- access control ---


ENDPOINTS = [
    ("get", BASE),
    ("get", f"{BASE}/metrics"),
    ("get", f"{BASE}/series?metric=registrations"),
    ("get", f"{BASE}/funnel"),
    ("post", f"{BASE}/refresh"),
]


@pytest.mark.parametrize("method, url", ENDPOINTS)
def test_visitors_and_members_cannot_see_the_dashboard(
    api_client, make_user, client_for, method, url
):
    assert getattr(api_client, method)(url).status_code == 401
    assert getattr(client_for(member(make_user, "m@example.com")), method)(url).status_code == 403


@pytest.mark.parametrize("method, url", ENDPOINTS)
def test_content_editors_do_not_get_the_dashboard(make_user, client_for, method, url):
    editor = client_for(make_user(roles=("content_editor",), email="e@example.com"), mfa_age=5)
    assert getattr(editor, method)(url).status_code == 403


@pytest.mark.parametrize("method, url", ENDPOINTS)
def test_admins_without_an_mfa_check_are_refused(admin, client_for, method, url):
    assert getattr(client_for(admin), method)(url).status_code == 403


def test_only_a_super_admin_can_force_a_refresh(as_admin):
    assert as_admin.post(f"{BASE}/refresh").status_code == 403


def test_the_learning_section_reports_courses_enrolments_and_completion(as_admin, make_user):
    from apps.learning import learn
    from apps.learning.tests.conftest import build_course, lesson_ids

    teacher = make_user(roles=("content_editor",), email="teacher@example.com")
    course = build_course(teacher)
    build_course(teacher, title="Second", publish=False)
    done, started = member(make_user, "done@example.com"), member(make_user, "started@example.com")
    for user in (done, started):
        learn.enrol(user_id=user.pk, course_id=course.pk)
    for lesson in lesson_ids(course):
        learn.update_progress(
            user_id=done.pk, lesson_id=lesson, position_seconds=None, completed=True
        )
    dashboard.refresh(days=1)
    learning = as_admin.get(BASE).json()["learning"]
    assert learning["available"] is True and learning["published_courses"] == 1
    assert (learning["enrolments"], learning["completed"], learning["completion_rate"]) == (
        2,
        1,
        0.5,
    )
    assert (
        learning["enrolments_last_30_days"] == 2 and learning["lessons_completed_last_30_days"] == 3
    )
