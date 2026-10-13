from datetime import timedelta

import pytest
from django.utils import timezone

from apps.mentorship import lifecycle
from apps.mentorship.models import MentorProfile, MentorSession, SessionFeedback
from apps.mentorship.tests.conftest import ask, times_of
from apps.notifications.models import Notification

pytestmark = pytest.mark.django_db

SESSIONS = "/api/v1/sessions"


def notices(user, kind):
    return Notification.objects.filter(user=user, type=kind)


def move(session_id, starts_at, minutes=45):
    ends_at = starts_at + timedelta(minutes=minutes)
    MentorSession.objects.filter(pk=session_id).update(
        starts_at=starts_at, ends_at=ends_at, time_span=(starts_at, ends_at)
    )


def book(mentee_client, mentor, index=0):
    response = ask(mentee_client, mentor, times_of(mentee_client, mentor)[index])
    assert response.status_code == 201, response.content
    return response.json()


def confirmed(mentee_client, mentor_client, mentor, run_outbox, index=0):
    session = book(mentee_client, mentor, index)
    assert mentor_client.post(f"{SESSIONS}/{session['id']}/accept").status_code == 200
    run_outbox()
    return session


# --- requests that nobody answers ---


def test_an_unanswered_request_lapses_and_frees_its_time(
    booking_mentor, mentee, mentee_client, run_outbox, settings
):
    session = book(mentee_client, booking_mentor)
    held = session["starts_at"]
    assert lifecycle.expire_requests() == 0  # still fresh

    MentorSession.objects.filter(pk=session["id"]).update(
        created_at=timezone.now() - timedelta(hours=settings.MENTORSHIP_REQUEST_TTL_HOURS + 1)
    )
    assert lifecycle.expire_requests() == 1
    assert lifecycle.expire_requests() == 0
    row = MentorSession.objects.get(pk=session["id"])
    assert row.status == "expired"
    run_outbox()
    assert notices(mentee, "session_expired").count() == 1
    assert any(t[:16] == held[:16] for t in times_of(mentee_client, booking_mentor))
    # The founder may ask again now the earlier request is closed.
    assert ask(mentee_client, booking_mentor, held).status_code == 201


def test_a_request_close_to_its_start_lapses(booking_mentor, mentee_client):
    session = book(mentee_client, booking_mentor)
    soon = timezone.now() + timedelta(hours=1)
    move(session["id"], soon)
    assert lifecycle.expire_requests() == 1


def test_a_confirmed_session_does_not_lapse(
    booking_mentor, mentee_client, applicant_client, run_outbox
):
    session = confirmed(mentee_client, applicant_client, booking_mentor, run_outbox)
    MentorSession.objects.filter(pk=session["id"]).update(
        created_at=timezone.now() - timedelta(days=30)
    )
    assert lifecycle.expire_requests() == 0


# --- reminders ---


def test_both_people_get_a_day_and_an_hour_reminder_once(
    booking_mentor, mentee, mentee_client, applicant_client, run_outbox
):
    session = confirmed(mentee_client, applicant_client, booking_mentor, run_outbox)
    MentorSession.objects.filter(pk=session["id"]).update(
        confirmed_at=timezone.now() - timedelta(days=3)
    )
    now = timezone.now()
    move(session["id"], now + timedelta(hours=20))
    assert lifecycle.send_reminders(now) == 1
    assert lifecycle.send_reminders(now) == 0  # claimed; a restart never repeats it
    assert notices(mentee, "session_reminder").get().payload["when"] == "24h"
    assert notices(booking_mentor, "session_reminder").count() == 1

    move(session["id"], now + timedelta(minutes=50))
    assert lifecycle.send_reminders(now) == 1
    assert [
        n.payload["when"] for n in notices(mentee, "session_reminder").order_by("created_at")
    ] == [
        "24h",
        "1h",
    ]


def test_a_session_confirmed_inside_a_window_skips_that_reminder(
    booking_mentor, mentee, mentee_client, applicant_client, run_outbox
):
    session = confirmed(mentee_client, applicant_client, booking_mentor, run_outbox)
    now = timezone.now()
    move(session["id"], now + timedelta(hours=10))  # confirmed just now, inside the 24 hour window
    assert lifecycle.send_reminders(now) == 0
    assert notices(mentee, "session_reminder").count() == 0


def test_cancelled_sessions_send_no_reminders(
    booking_mentor, mentee, mentee_client, applicant_client, run_outbox
):
    session = confirmed(mentee_client, applicant_client, booking_mentor, run_outbox)
    MentorSession.objects.filter(pk=session["id"]).update(
        confirmed_at=timezone.now() - timedelta(days=3)
    )
    mentee_client.post(
        f"{SESSIONS}/{session['id']}/cancel", {"reason": "Plans changed"}, format="json"
    )
    move(session["id"], timezone.now() + timedelta(hours=3))
    assert lifecycle.send_reminders() == 0


# --- finishing ---


def test_a_finished_session_is_marked_held_and_feedback_is_asked_for(
    booking_mentor, mentee, mentee_client, applicant_client, run_outbox
):
    session = confirmed(mentee_client, applicant_client, booking_mentor, run_outbox)
    assert lifecycle.complete_due() == 0  # not over yet

    over = timezone.now() - timedelta(hours=2)
    move(session["id"], over)
    assert lifecycle.complete_due() == 1
    assert lifecycle.complete_due() == 0
    row = MentorSession.objects.get(pk=session["id"])
    assert row.status == "completed" and row.completed_at is not None

    run_outbox()
    assert notices(mentee, "session_feedback_request").count() == 1
    assert notices(booking_mentor, "session_feedback_request").count() == 1
    view = mentee_client.get(f"{SESSIONS}/{session['id']}").json()
    assert view["feedback"]["can_give"] is True and view["actions"]["cancel"] is False
    assert [r["id"] for r in mentee_client.get(SESSIONS, {"state": "past"}).json()["results"]] == [
        session["id"]
    ]


# --- feedback ---


def held_session(mentee_client, applicant_client, mentor, run_outbox):
    session = confirmed(mentee_client, applicant_client, mentor, run_outbox)
    move(session["id"], timezone.now() - timedelta(hours=2))
    lifecycle.complete_due()
    return session


def feedback_url(session):
    return f"{SESSIONS}/{session['id']}/feedback"


def test_feedback_opens_only_after_the_session(
    booking_mentor, mentee_client, applicant_client, run_outbox
):
    session = confirmed(mentee_client, applicant_client, booking_mentor, run_outbox)
    response = mentee_client.put(feedback_url(session), {"stars": 5}, format="json")
    assert response.status_code == 409
    view = mentee_client.get(f"{SESSIONS}/{session['id']}").json()
    assert view["feedback"]["can_give"] is False


def test_stars_build_the_mentor_rating_and_editing_corrects_it(
    booking_mentor, mentee_client, applicant_client, run_outbox
):
    session = held_session(mentee_client, applicant_client, booking_mentor, run_outbox)
    profile = MentorProfile.objects.get(user=booking_mentor)
    assert (profile.rating_count, profile.rating_total) == (0, 0)

    first = mentee_client.put(
        feedback_url(session), {"stars": 4, "comment": "Very practical advice."}, format="json"
    )
    assert first.status_code == 200 and first.json()["stars"] == 4
    profile.refresh_from_db()
    assert (profile.rating_count, profile.rating_total) == (1, 4)

    again = mentee_client.put(feedback_url(session), {"stars": 5}, format="json")
    assert again.status_code == 200
    profile.refresh_from_db()
    assert (profile.rating_count, profile.rating_total) == (1, 5)  # corrected, not doubled
    assert SessionFeedback.objects.filter(session_id=session["id"]).count() == 1
    shown = mentor_rating(applicant_client, booking_mentor)
    assert shown == {"rating_average": 5.0, "rating_count": 1}


def mentor_rating(client, mentor):
    body = client.get(f"/api/v1/mentors/{mentor.pk}").json()
    return {"rating_average": body["rating_average"], "rating_count": body["rating_count"]}


def test_stars_are_required_and_must_be_between_one_and_five(
    booking_mentor, mentee_client, applicant_client, run_outbox
):
    session = held_session(mentee_client, applicant_client, booking_mentor, run_outbox)
    assert (
        mentee_client.put(feedback_url(session), {"comment": "Nice"}, format="json").status_code
        == 400
    )
    assert mentee_client.put(feedback_url(session), {"stars": 6}, format="json").status_code == 400
    assert mentee_client.put(feedback_url(session), {"stars": 0}, format="json").status_code == 400
    bad = mentee_client.put(
        feedback_url(session), {"stars": 3, "outcome": "mentee_no_show"}, format="json"
    )
    assert bad.status_code == 400


def test_the_mentor_sees_the_comment_and_the_founder_never_sees_the_mentors_note(
    booking_mentor, mentee_client, applicant_client, as_admin, run_outbox
):
    session = held_session(mentee_client, applicant_client, booking_mentor, run_outbox)
    mentee_client.put(
        feedback_url(session), {"stars": 5, "comment": "Great session"}, format="json"
    )
    applicant_client.put(
        feedback_url(session),
        {"outcome": "held", "comment": "Well prepared founder"},
        format="json",
    )
    mentee_view = mentee_client.get(f"{SESSIONS}/{session['id']}").json()["feedback"]
    mentor_view = applicant_client.get(f"{SESSIONS}/{session['id']}").json()["feedback"]
    admin_view = as_admin.get(f"/api/v1/admin/sessions/{session['id']}").json()["feedback"]
    assert mentee_view["mine"]["comment"] == "Great session"
    assert mentee_view["from_mentor"] is None and mentee_view["from_mentee"] is None
    assert mentor_view["from_mentee"]["comment"] == "Great session"
    assert mentor_view["mine"]["comment"] == "Well prepared founder"
    assert mentor_view["from_mentor"] is None
    assert admin_view["from_mentee"]["stars"] == 5
    assert admin_view["from_mentor"]["comment"] == "Well prepared founder"


def test_a_mentor_can_record_that_the_founder_did_not_come(
    booking_mentor, mentee_client, applicant_client, run_outbox
):
    session = held_session(mentee_client, applicant_client, booking_mentor, run_outbox)
    response = applicant_client.put(
        feedback_url(session), {"outcome": "mentee_no_show"}, format="json"
    )
    assert response.status_code == 200
    assert MentorSession.objects.get(pk=session["id"]).status == "no_show"
    undone = applicant_client.put(feedback_url(session), {"outcome": "held"}, format="json")
    assert undone.status_code == 200
    assert MentorSession.objects.get(pk=session["id"]).status == "completed"


def test_a_founder_can_report_that_the_mentor_did_not_come_without_rating(
    booking_mentor, mentee_client, applicant_client, run_outbox
):
    session = held_session(mentee_client, applicant_client, booking_mentor, run_outbox)
    mentee_client.put(feedback_url(session), {"stars": 5}, format="json")
    response = mentee_client.put(
        feedback_url(session),
        {"outcome": "mentor_no_show", "comment": "Nobody joined."},
        format="json",
    )
    assert response.status_code == 200 and response.json()["stars"] is None
    profile = MentorProfile.objects.get(user=booking_mentor)
    assert (profile.rating_count, profile.rating_total) == (
        0,
        0,
    )  # the earlier stars were taken back


def test_the_feedback_window_closes(
    booking_mentor, mentee_client, applicant_client, run_outbox, settings
):
    session = held_session(mentee_client, applicant_client, booking_mentor, run_outbox)
    old = timezone.now() - timedelta(days=settings.MENTORSHIP_FEEDBACK_WINDOW_DAYS + 1)
    MentorSession.objects.filter(pk=session["id"]).update(completed_at=old)
    assert mentee_client.put(feedback_url(session), {"stars": 5}, format="json").status_code == 409


def test_strangers_cannot_give_feedback(
    booking_mentor, mentee_client, applicant_client, other_client, run_outbox
):
    session = held_session(mentee_client, applicant_client, booking_mentor, run_outbox)
    assert other_client.put(feedback_url(session), {"stars": 1}, format="json").status_code == 404


# --- the rating and speed feed matching ---


def test_reply_speed_lifts_a_mentors_quality_score(booking_mentor):
    from apps.mentorship import matching, selectors

    profile = MentorProfile.objects.get(user=booking_mentor)
    base = matching.quality_signal(profile)
    fast = matching.quality_signal(profile, 1.0)
    slow = matching.quality_signal(profile, 160.0)
    assert fast.score > base.score > slow.score
    assert "within a day" in fast.text
    # Too few answered requests say nothing about speed.
    assert selectors.median_response_hours([booking_mentor.pk]) == {}


def test_median_reply_time_needs_enough_answers(
    booking_mentor, mentee, mentee_client, applicant_client, make_user, client_for
):
    from apps.mentorship import selectors
    from apps.mentorship.tests.conftest import active

    sessions = []
    for index, email in enumerate(("a@example.com", "b@example.com", "c@example.com")):
        founder = client_for(active(make_user, email))
        response = ask(founder, booking_mentor, times_of(founder, booking_mentor)[index * 3])
        assert response.status_code == 201
        sessions.append(response.json()["id"])
    for session_id in sessions:
        assert applicant_client.post(f"{SESSIONS}/{session_id}/accept").status_code == 200
    for hours, session_id in zip((1, 3, 10), sessions, strict=True):
        MentorSession.objects.filter(pk=session_id).update(
            created_at=timezone.now() - timedelta(hours=hours), responded_at=timezone.now()
        )
    speeds = selectors.median_response_hours([booking_mentor.pk])
    assert round(speeds[booking_mentor.pk]) == 3
