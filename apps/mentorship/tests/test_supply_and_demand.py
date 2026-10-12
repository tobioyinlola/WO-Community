from datetime import timedelta

import pytest
from django.utils import timezone

from apps.mentorship import selectors
from apps.mentorship.models import MentorSession, SeekerNeeds
from apps.mentorship.tests.conftest import ask, times_of

pytestmark = pytest.mark.django_db

SESSIONS = "/api/v1/sessions"


def test_supply_reports_capacity_times_and_expertise(booking_mentor, mentee_client):
    figures = selectors.supply_and_demand()
    assert figures["weekly_capacity"] == 3 and figures["mentors_with_times"] == 1
    topics = {row["topic"] for row in figures["top_expertise"]}
    assert {"fundraising", "go-to-market"} <= topics
    assert figures["requests_30d"] == 0 and figures["acceptance_rate_30d"] is None
    assert figures["median_response_hours_30d"] is None and figures["average_rating"] is None


def test_demand_counts_requests_answers_speed_and_needs(
    booking_mentor, mentee, mentee_client, applicant_client
):
    SeekerNeeds.objects.create(user=mentee, needs=["fundraising", "hiring"])
    first = ask(mentee_client, booking_mentor, times_of(mentee_client, booking_mentor)[0]).json()
    applicant_client.post(f"{SESSIONS}/{first['id']}/accept")
    MentorSession.objects.filter(pk=first["id"]).update(
        created_at=timezone.now() - timedelta(hours=6), responded_at=timezone.now()
    )
    second = ask(mentee_client, booking_mentor, times_of(mentee_client, booking_mentor)[3]).json()
    MentorSession.objects.filter(pk=second["id"]).update(
        created_at=timezone.now() - timedelta(hours=60)
    )

    figures = selectors.supply_and_demand()
    assert figures["requests_30d"] == 2
    assert figures["acceptance_rate_30d"] == 1.0  # one answered, and it was accepted
    assert figures["median_response_hours_30d"] == pytest.approx(6.0, abs=0.1)
    assert figures["unanswered_over_48h"] == 1
    assert {"topic": "fundraising", "founders": 1} in figures["top_needs"]


def test_no_show_rate_and_rating_show_whether_it_works(booking_mentor, mentee, mentee_client):
    from apps.mentorship.models import MentorProfile

    MentorProfile.objects.filter(user=booking_mentor).update(rating_count=2, rating_total=9)
    past = timezone.now() - timedelta(days=2)
    for index, status in enumerate(("completed", "completed", "completed", "no_show")):
        begin = past - timedelta(hours=index * 2)
        MentorSession.objects.create(
            mentor=booking_mentor,
            mentee=mentee,
            starts_at=begin,
            ends_at=begin + timedelta(minutes=45),
            time_span=(begin, begin + timedelta(minutes=45)),
            topic="t",
            message="m",
            status=status,
        )
    figures = selectors.supply_and_demand()
    assert figures["no_show_rate_30d"] == 0.25 and figures["average_rating"] == 4.5
