import pytest
from django.utils import timezone

from apps.learning import learn
from apps.learning.models import Enrolment
from apps.learning.tests.conftest import build_course

pytestmark = pytest.mark.django_db


def test_the_dashboard_shows_mentoring_figures_and_the_course_breakdown(make_user, client_for):
    admin = make_user(roles=("community_admin",), email="dash@example.com")
    editor = make_user(roles=("content_editor",), email="editor-dash@example.com")
    course = build_course(editor)
    learner = make_user(
        email="learner-dash@example.com",
        approved_at=timezone.now(),
        email_verified_at=timezone.now(),
    )
    learn.enrol(user_id=learner.pk, course_id=course.pk)
    Enrolment.objects.filter(user=learner).update(completed_at=timezone.now())
    body = client_for(admin, mfa_age=5).get("/api/v1/admin/dashboard").json()
    mentoring = body["mentorship"]
    assert mentoring["weekly_capacity"] == 0 and mentoring["top_needs"] == []
    assert mentoring["requests_30d"] == 0 and mentoring["acceptance_rate_30d"] is None
    [row] = body["learning"]["courses"]
    assert row["title"] == course.title and row["enrolments"] == 1
    assert row["completed"] == 1 and row["completion_rate"] == 1.0
