from datetime import datetime, timedelta

import pytest
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.integrations.meetings.fake import FakeMeetingProvider
from apps.mentorship import scheduling
from apps.mentorship.models import MentorProfile, MentorSession
from apps.mentorship.tests.conftest import (
    active,
    ask,
    become_mentor,
    open_schedule,
    times_of,
)
from apps.notifications.models import Notification

pytestmark = pytest.mark.django_db

SESSIONS = "/api/v1/sessions"


def when(value: str) -> datetime:
    return datetime.fromisoformat(value)


def book(mentee_client, mentor, index=0):
    start = times_of(mentee_client, mentor)[index]
    response = ask(mentee_client, mentor, start)
    assert response.status_code == 201, response.content
    return response.json()


def confirmed(mentee_client, mentor_client, mentor, run_outbox, index=0):
    session = book(mentee_client, mentor, index)
    answer = mentor_client.post(f"{SESSIONS}/{session['id']}/accept")
    assert answer.status_code == 200, answer.content
    run_outbox()
    return mentee_client.get(f"{SESSIONS}/{session['id']}").json()


def notices(user, kind):
    return Notification.objects.filter(user=user, type=kind)


# --- asking ---


def test_a_founder_asks_for_a_time_and_the_mentor_is_told(
    booking_mentor, mentee, mentee_client, applicant_client, run_outbox
):
    first, second = times_of(mentee_client, booking_mentor)[:2]
    response = ask(mentee_client, booking_mentor, first)
    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "requested" and body["role"] == "mentee"
    assert body["starts_at"].startswith(first[:16])
    assert (when(body["ends_at"]) - when(body["starts_at"])) == timedelta(minutes=45)
    assert body["actions"]["cancel"] and not body["actions"]["accept"]
    assert body["meeting"] == {"provider": "", "state": "", "url": ""}

    run_outbox()
    assert notices(booking_mentor, "session_requested").count() == 1
    # The held time is gone from what others are offered; the next one is still there.
    others = times_of(mentee_client, booking_mentor)
    assert first not in others and second in others
    mentor_view = applicant_client.get(f"{SESSIONS}/{body['id']}").json()
    assert mentor_view["role"] == "mentor" and mentor_view["actions"]["accept"]


def test_only_a_listed_bookable_time_can_be_requested(
    booking_mentor, mentee_client, applicant_client
):
    start = when(times_of(mentee_client, booking_mentor)[0])
    off_grid = (start + timedelta(minutes=10)).isoformat()
    assert ask(mentee_client, booking_mentor, off_grid).status_code == 409
    past = (timezone.now() - timedelta(days=1)).isoformat()
    assert ask(mentee_client, booking_mentor, past).status_code == 409
    soon = (timezone.now() + timedelta(hours=1)).isoformat()
    assert ask(mentee_client, booking_mentor, soon).status_code == 409


def test_a_request_needs_a_topic_and_a_real_message(booking_mentor, mentee_client):
    start = times_of(mentee_client, booking_mentor)[0]
    assert ask(mentee_client, booking_mentor, start, message="Hi").status_code == 400
    assert ask(mentee_client, booking_mentor, start, topic="x").status_code == 400
    assert ask(mentee_client, booking_mentor, start, extra="field").status_code == 400
    body = ask(mentee_client, booking_mentor, start, topic="<b>Hiring</b> plans").json()
    assert body["topic"] == "Hiring plans"  # markup is stripped


def test_you_cannot_book_yourself_or_a_non_mentor(
    booking_mentor, applicant_client, mentee_client, other
):
    start = times_of(applicant_client, booking_mentor)[0]
    assert ask(applicant_client, booking_mentor, start).status_code == 400
    assert ask(mentee_client, other, start).status_code == 404  # a member who is not a mentor


def test_a_paused_or_revoked_mentor_cannot_be_asked(
    booking_mentor, mentee_client, applicant_client, as_admin
):
    start = times_of(mentee_client, booking_mentor)[0]
    applicant_client.put("/api/v1/me/mentor-profile", {"paused": True}, format="json")
    assert ask(mentee_client, booking_mentor, start).status_code == 404
    applicant_client.put("/api/v1/me/mentor-profile", {"paused": False}, format="json")
    as_admin.post(
        f"/api/v1/admin/mentors/{booking_mentor.pk}/revoke", {"reason": "x"}, format="json"
    )
    assert ask(mentee_client, booking_mentor, start).status_code == 404


def test_visitors_and_unapproved_accounts_cannot_ask(booking_mentor, api_client):
    assert api_client.get(SESSIONS).status_code == 401


def test_one_waiting_request_per_mentor(booking_mentor, mentee_client):
    times = times_of(mentee_client, booking_mentor)
    assert ask(mentee_client, booking_mentor, times[0]).status_code == 201
    again = ask(mentee_client, booking_mentor, times[3])
    assert again.status_code == 409
    assert "already have a request" in again.json()["detail"]


def test_a_founder_has_a_limited_number_of_open_requests(
    booking_mentor, mentee_client, make_user, client_for, as_admin, settings
):
    settings.MENTORSHIP_MAX_OPEN_REQUESTS = 1
    start = times_of(mentee_client, booking_mentor)[0]
    assert ask(mentee_client, booking_mentor, start).status_code == 201

    second = active(make_user, "mentor-two@example.com")
    second_client = client_for(second)
    become_mentor(second, second_client, as_admin, linkedin_url="https://www.linkedin.com/in/b")
    open_schedule(second_client)
    blocked = ask(mentee_client, second, times_of(mentee_client, second)[0])
    assert blocked.status_code == 409 and "waiting" in blocked.json()["detail"]


def test_requests_are_limited_per_day(booking_mentor, mentee_client, settings):
    settings.MENTORSHIP_REQUESTS_PER_DAY = 1
    times = times_of(mentee_client, booking_mentor)
    assert ask(mentee_client, booking_mentor, times[0]).status_code == 201
    assert ask(mentee_client, booking_mentor, times[1]).status_code == 429


def test_two_founders_cannot_hold_the_same_time(
    booking_mentor, mentee_client, make_user, client_for
):
    start = times_of(mentee_client, booking_mentor)[0]
    assert ask(mentee_client, booking_mentor, start).status_code == 201
    rival = client_for(active(make_user, "rival@example.com"))
    assert ask(rival, booking_mentor, start).status_code == 409


def test_the_database_refuses_overlapping_holds(booking_mentor, mentee, make_user):
    start = timezone.now() + timedelta(days=3)
    end = start + timedelta(minutes=45)

    def make(user, begin=start, finish=end, status="requested", mentor=booking_mentor):
        return MentorSession.objects.create(
            mentor=mentor,
            mentee=user,
            starts_at=begin,
            ends_at=finish,
            time_span=(begin, finish),
            topic="t",
            message="m",
            status=status,
        )

    make(mentee)
    rival = active(make_user, "rival2@example.com")
    with pytest.raises(IntegrityError), transaction.atomic():  # the mentor is already held
        make(rival, start + timedelta(minutes=30), end + timedelta(minutes=30))
    # Touching sessions are fine, and a closed session holds nothing.
    make(rival, end, end + timedelta(minutes=45))
    make(rival, start, end, status="declined")
    # The founder cannot be in two places either.
    other_mentor = active(make_user, "mentor-three@example.com")
    with pytest.raises(IntegrityError), transaction.atomic():
        make(mentee, start, end, mentor=other_mentor)


# --- the mentor answers ---


def test_confirming_creates_the_meeting_and_tells_the_founder(
    booking_mentor, mentee, mentee_client, applicant_client, run_outbox
):
    session = book(mentee_client, booking_mentor)
    answer = applicant_client.post(f"{SESSIONS}/{session['id']}/accept")
    assert answer.status_code == 200
    body = answer.json()
    assert body["status"] == "confirmed" and body["meeting"]["state"] == "pending"
    assert body["meeting"]["url"] == ""

    run_outbox()
    assert notices(mentee, "session_confirmed").count() == 1
    for client in (mentee_client, applicant_client):
        view = client.get(f"{SESSIONS}/{session['id']}").json()
        assert view["meeting"]["state"] == "ready"
        assert view["meeting"]["url"] == f"https://meet.test/google_meet/{session['id']}"
        assert view["meeting"]["provider"] == "google_meet"
    meeting = FakeMeetingProvider.meetings[f"fake-{session['id']}"]
    assert sorted(meeting["attendees"]) == ["applicant@example.com", "mentee@example.com"]


def test_a_mentor_can_choose_zoom(booking_mentor, mentee_client, applicant_client, run_outbox):
    saved = applicant_client.put(
        "/api/v1/me/mentor-profile", {"meeting_provider": "zoom"}, format="json"
    )
    assert saved.status_code == 200 and saved.json()["meeting_provider"] == "zoom"
    assert (
        applicant_client.put(
            "/api/v1/me/mentor-profile", {"meeting_provider": "skype"}, format="json"
        ).status_code
        == 400
    )
    view = confirmed(mentee_client, applicant_client, booking_mentor, run_outbox)
    assert view["meeting"]["provider"] == "zoom"
    assert "/zoom/" in view["meeting"]["url"]


def test_declining_needs_a_reason_the_founder_sees(
    booking_mentor, mentee, mentee_client, applicant_client, run_outbox
):
    session = book(mentee_client, booking_mentor)
    url = f"{SESSIONS}/{session['id']}/decline"
    assert applicant_client.post(url, {}, format="json").status_code == 400
    done = applicant_client.post(url, {"reason": "I am travelling that week."}, format="json")
    assert done.status_code == 200 and done.json()["status"] == "declined"
    run_outbox()
    note = notices(mentee, "session_declined").get()
    assert note.payload["reason"] == "I am travelling that week."
    # The held time is free again.
    assert session["starts_at"][:16] in " ".join(times_of(mentee_client, booking_mentor))


def test_only_the_mentor_answers_and_only_once(
    booking_mentor, mentee_client, applicant_client, other_client
):
    session = book(mentee_client, booking_mentor)
    url = f"{SESSIONS}/{session['id']}"
    assert mentee_client.post(f"{url}/accept").status_code == 403
    assert other_client.post(f"{url}/accept").status_code == 404  # not a participant
    assert other_client.get(url).status_code == 404
    assert applicant_client.post(f"{url}/accept").status_code == 200
    assert applicant_client.post(f"{url}/accept").status_code == 409
    assert (
        applicant_client.post(f"{url}/decline", {"reason": "no thanks"}, format="json").status_code
        == 409
    )


def test_a_request_whose_time_has_passed_cannot_be_confirmed(
    booking_mentor, mentee_client, applicant_client
):
    session = book(mentee_client, booking_mentor)
    row = MentorSession.objects.get(pk=session["id"])
    begin = timezone.now() - timedelta(hours=1)
    MentorSession.objects.filter(pk=row.pk).update(
        starts_at=begin,
        ends_at=begin + timedelta(minutes=45),
        time_span=(begin, begin + timedelta(minutes=45)),
    )
    assert applicant_client.post(f"{SESSIONS}/{session['id']}/accept").status_code == 409


# --- capacity ---


def test_a_full_week_offers_no_more_times_but_the_next_week_does(
    booking_mentor, mentee_client, applicant_client
):
    applicant_client.put("/api/v1/me/mentor-profile", {"capacity_per_week": 1}, format="json")
    first = when(times_of(mentee_client, booking_mentor)[0])
    assert ask(mentee_client, booking_mentor, first.isoformat()).status_code == 201
    profile = MentorProfile.objects.get(user=booking_mentor)
    week_start, week_end = scheduling.week_bounds(profile.timezone, first)
    remaining = [when(t) for t in times_of(mentee_client, booking_mentor, days=30)]
    assert remaining and all(not (week_start <= t < week_end) for t in remaining)
    assert any(t >= week_end for t in remaining)
    body = mentee_client.get(f"/api/v1/mentors/{booking_mentor.pk}/availability").json()
    assert body["sessions_left_this_week"] in (0, 1)


def test_the_last_place_in_a_week_goes_to_one_request(
    booking_mentor, mentee_client, applicant_client, make_user, client_for
):
    applicant_client.put("/api/v1/me/mentor-profile", {"capacity_per_week": 1}, format="json")
    times = times_of(mentee_client, booking_mentor)
    same_week = [
        t
        for t in times
        if scheduling.week_bounds("Africa/Lagos", when(t))[0]
        == scheduling.week_bounds("Africa/Lagos", when(times[0]))[0]
    ]
    assert len(same_week) >= 2
    assert ask(mentee_client, booking_mentor, same_week[0]).status_code == 201
    rival = client_for(active(make_user, "rival3@example.com"))
    assert ask(rival, booking_mentor, same_week[1]).status_code == 409


def test_declined_and_cancelled_sessions_give_the_place_back(
    booking_mentor, mentee_client, applicant_client
):
    applicant_client.put("/api/v1/me/mentor-profile", {"capacity_per_week": 1}, format="json")
    first = when(times_of(mentee_client, booking_mentor)[0])
    session = ask(mentee_client, booking_mentor, first.isoformat()).json()
    profile = MentorProfile.objects.get(user=booking_mentor)
    assert scheduling.sessions_in_week(profile.user_id, first) == 1
    mentee_client.post(f"{SESSIONS}/{session['id']}/cancel", {}, format="json")
    assert scheduling.sessions_in_week(profile.user_id, first) == 0


# --- cancelling ---


def test_a_founder_can_withdraw_a_waiting_request(
    booking_mentor, mentee_client, applicant_client, run_outbox
):
    session = book(mentee_client, booking_mentor)
    response = mentee_client.post(f"{SESSIONS}/{session['id']}/cancel", {}, format="json")
    assert response.status_code == 200 and response.json()["status"] == "cancelled"
    assert mentee_client.post(f"{SESSIONS}/{session['id']}/cancel").status_code == 409
    # The mentor declines a waiting request; cancel is for agreed sessions.
    again = book(mentee_client, booking_mentor, 1)
    assert applicant_client.post(f"{SESSIONS}/{again['id']}/cancel").status_code == 409


def test_cancelling_a_confirmed_session_needs_a_reason_and_removes_the_meeting(
    booking_mentor, mentee, mentee_client, applicant_client, run_outbox
):
    view = confirmed(mentee_client, applicant_client, booking_mentor, run_outbox)
    url = f"{SESSIONS}/{view['id']}/cancel"
    assert mentee_client.post(url, {}, format="json").status_code == 400
    response = applicant_client.post(url, {"reason": "A clash came up."}, format="json")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "cancelled" and body["reason"] == "A clash came up."
    assert body["cancelled_by"] == str(booking_mentor.pk)

    run_outbox()
    assert FakeMeetingProvider.meetings == {}
    note = notices(mentee, "session_cancelled").get()
    assert note.payload["reason"] == "A clash came up."
    assert notices(booking_mentor, "session_cancelled").count() == 0  # not told of their own act
    assert MentorSession.objects.get(pk=view["id"]).meeting_external_id == ""


def test_a_cancellation_inside_a_day_is_marked_late(
    booking_mentor, mentee_client, applicant_client, run_outbox
):
    view = confirmed(mentee_client, applicant_client, booking_mentor, run_outbox)
    soon = timezone.now() + timedelta(hours=5)
    MentorSession.objects.filter(pk=view["id"]).update(
        starts_at=soon,
        ends_at=soon + timedelta(minutes=45),
        time_span=(soon, soon + timedelta(minutes=45)),
    )
    body = mentee_client.post(
        f"{SESSIONS}/{view['id']}/cancel", {"reason": "Something came up."}, format="json"
    ).json()
    assert body["late_cancel"] is True


def test_a_session_that_has_started_cannot_be_cancelled(
    booking_mentor, mentee_client, applicant_client, run_outbox
):
    view = confirmed(mentee_client, applicant_client, booking_mentor, run_outbox)
    begin = timezone.now() - timedelta(minutes=5)
    MentorSession.objects.filter(pk=view["id"]).update(
        starts_at=begin,
        ends_at=begin + timedelta(minutes=45),
        time_span=(begin, begin + timedelta(minutes=45)),
    )
    response = mentee_client.post(
        f"{SESSIONS}/{view['id']}/cancel", {"reason": "Too late."}, format="json"
    )
    assert response.status_code == 409


# --- rescheduling ---


def test_a_new_time_takes_effect_when_the_other_person_accepts(
    booking_mentor, mentee, mentee_client, applicant_client, run_outbox
):
    view = confirmed(mentee_client, applicant_client, booking_mentor, run_outbox)
    original = view["starts_at"]
    new = times_of(mentee_client, booking_mentor)[6]
    url = f"{SESSIONS}/{view['id']}/reschedule"
    proposed = mentee_client.post(url, {"starts_at": new, "note": "Exam that day"}, format="json")
    assert proposed.status_code == 200
    body = proposed.json()
    assert body["starts_at"] == original  # unchanged until accepted
    assert body["proposal"]["by_me"] is True and body["proposal"]["note"] == "Exam that day"
    assert body["actions"]["answer_reschedule"] is False

    run_outbox()
    assert notices(booking_mentor, "session_reschedule_proposed").count() == 1
    mentor_view = applicant_client.get(f"{SESSIONS}/{view['id']}").json()
    assert mentor_view["actions"]["answer_reschedule"] is True
    # The proposer cannot accept their own suggestion.
    assert mentee_client.post(f"{url}/accept").status_code == 403

    accepted = applicant_client.post(f"{url}/accept")
    assert accepted.status_code == 200
    moved = accepted.json()
    assert when(moved["starts_at"]) == when(new)
    assert moved["proposal"] is None and moved["reschedule_count"] == 1

    run_outbox()
    assert notices(mentee, "session_rescheduled").count() == 1
    meeting = FakeMeetingProvider.meetings[f"fake-{view['id']}"]
    assert meeting["starts_at"] == when(new)
    assert MentorSession.objects.get(pk=view["id"]).reminded_24h_at is None


def test_the_other_person_can_keep_the_original_time(
    booking_mentor, mentee, mentee_client, applicant_client, run_outbox
):
    view = confirmed(mentee_client, applicant_client, booking_mentor, run_outbox)
    new = times_of(mentee_client, booking_mentor)[6]
    url = f"{SESSIONS}/{view['id']}/reschedule"
    mentee_client.post(url, {"starts_at": new}, format="json")
    run_outbox()
    kept = applicant_client.delete(url)
    assert kept.status_code == 200 and kept.json()["proposal"] is None
    assert kept.json()["starts_at"] == view["starts_at"]
    run_outbox()
    assert notices(mentee, "session_reschedule_closed").get().payload["withdrawn"] is False
    assert applicant_client.delete(url).status_code == 409  # nothing left to answer


def test_the_proposer_can_withdraw(
    booking_mentor, mentee, mentee_client, applicant_client, run_outbox
):
    view = confirmed(mentee_client, applicant_client, booking_mentor, run_outbox)
    url = f"{SESSIONS}/{view['id']}/reschedule"
    new = times_of(mentee_client, booking_mentor)[6]
    applicant_client.post(url, {"starts_at": new}, format="json")
    assert applicant_client.delete(url).status_code == 200
    run_outbox()
    assert notices(mentee, "session_reschedule_closed").get().payload["withdrawn"] is True


def test_only_bookable_times_can_be_suggested_and_only_a_few_moves_are_allowed(
    booking_mentor, mentee_client, applicant_client, run_outbox, settings
):
    view = confirmed(mentee_client, applicant_client, booking_mentor, run_outbox)
    url = f"{SESSIONS}/{view['id']}/reschedule"
    odd = (when(view["starts_at"]) + timedelta(days=1, minutes=7)).isoformat()
    assert mentee_client.post(url, {"starts_at": odd}, format="json").status_code == 409
    assert (
        mentee_client.post(url, {"starts_at": view["starts_at"]}, format="json").status_code == 400
    )
    settings.MENTORSHIP_MAX_RESCHEDULES = 0
    new = times_of(mentee_client, booking_mentor)[6]
    assert mentee_client.post(url, {"starts_at": new}, format="json").status_code == 409


def test_accepting_fails_when_the_time_was_taken_meanwhile(
    booking_mentor, mentee_client, applicant_client, run_outbox, make_user, client_for
):
    view = confirmed(mentee_client, applicant_client, booking_mentor, run_outbox)
    target = times_of(mentee_client, booking_mentor)[6]
    url = f"{SESSIONS}/{view['id']}/reschedule"
    assert mentee_client.post(url, {"starts_at": target}, format="json").status_code == 200
    rival = client_for(active(make_user, "rival4@example.com"))
    assert ask(rival, booking_mentor, target).status_code == 201
    taken = applicant_client.post(f"{url}/accept")
    assert taken.status_code == 409
    assert applicant_client.get(f"{SESSIONS}/{view['id']}").json()["starts_at"] == view["starts_at"]


def test_a_request_that_is_still_waiting_cannot_be_moved(booking_mentor, mentee_client):
    session = book(mentee_client, booking_mentor)
    new = times_of(mentee_client, booking_mentor)[6]
    response = mentee_client.post(
        f"{SESSIONS}/{session['id']}/reschedule", {"starts_at": new}, format="json"
    )
    assert response.status_code == 409


# --- the meeting ---


def test_a_failed_meeting_lets_the_mentor_add_their_own_link(
    booking_mentor, mentee, mentee_client, applicant_client, run_outbox
):
    from apps.integrations.meetings import MeetingRejected

    FakeMeetingProvider.failure = MeetingRejected("bad time")
    view = confirmed(mentee_client, applicant_client, booking_mentor, run_outbox)
    assert view["meeting"]["state"] == "failed" and view["meeting"]["url"] == ""
    assert notices(booking_mentor, "session_meeting_failed").count() == 1
    mentor_view = applicant_client.get(f"{SESSIONS}/{view['id']}").json()
    assert mentor_view["actions"]["add_link"] is True

    link = f"{SESSIONS}/{view['id']}/meeting-link"
    assert (
        mentee_client.put(link, {"url": "https://meet.example.com/x"}, format="json").status_code
        == 403
    )
    assert (
        applicant_client.put(
            link, {"url": "http://insecure.example.com"}, format="json"
        ).status_code
        == 400
    )
    done = applicant_client.put(link, {"url": "https://meet.example.com/x"}, format="json")
    assert done.status_code == 200
    assert done.json()["meeting"] == {
        "provider": "manual",
        "state": "ready",
        "url": "https://meet.example.com/x",
    }
    assert (
        applicant_client.put(link, {"url": "https://meet.example.com/y"}, format="json").status_code
        == 409
    )
    run_outbox()
    assert notices(mentee, "session_meeting_ready").count() == 1


def test_a_provider_that_stays_down_ends_in_a_failed_meeting(
    booking_mentor, mentee_client, applicant_client
):
    from apps.core.models import OutboxEvent
    from apps.integrations.meetings import MeetingTemporarilyUnavailable
    from apps.mentorship import session_tasks

    FakeMeetingProvider.failure = MeetingTemporarilyUnavailable("down")
    session = book(mentee_client, booking_mentor)
    applicant_client.post(f"{SESSIONS}/{session['id']}/accept")
    event = OutboxEvent.objects.get(topic="mentorship.session_confirmed")

    # Early attempts are left to retry; the meeting is still wanted.
    with pytest.raises(Exception):  # noqa: B017  # celery's Retry, as it would be re-queued
        session_tasks.create_meeting.apply(args=[str(event.id)], retries=0, throw=True)
    assert MentorSession.objects.get(pk=session["id"]).meeting_state == "pending"
    # The last attempt gives up and asks the mentor to add a link.
    session_tasks.create_meeting.apply(args=[str(event.id)], retries=5)
    row = MentorSession.objects.get(pk=session["id"])
    assert row.meeting_state == "failed"
    assert notices(booking_mentor, "session_meeting_failed").count() == 1


def test_a_meeting_made_after_a_cancellation_is_removed(
    booking_mentor, mentee_client, applicant_client, run_outbox
):
    session = book(mentee_client, booking_mentor)
    applicant_client.post(f"{SESSIONS}/{session['id']}/accept")
    # The founder cancels before the worker picks the booking up.
    mentee_client.post(
        f"{SESSIONS}/{session['id']}/cancel", {"reason": "Plans changed."}, format="json"
    )
    run_outbox()
    assert FakeMeetingProvider.meetings == {}
    assert MentorSession.objects.get(pk=session["id"]).meeting_external_id == ""


# --- reading ---


def test_lists_show_only_your_sessions_by_state(
    booking_mentor, mentee, mentee_client, applicant_client, other_client, run_outbox
):
    pending = book(mentee_client, booking_mentor, 0)
    done = applicant_client.post(f"{SESSIONS}/{pending['id']}/accept")
    assert done.status_code == 200
    declined_request = book(mentee_client, booking_mentor, 3)
    applicant_client.post(
        f"{SESSIONS}/{declined_request['id']}/decline", {"reason": "Not a fit."}, format="json"
    )
    waiting = book(mentee_client, booking_mentor, 6)

    def ids(client, **params):
        body = client.get(SESSIONS, params).json()
        return [row["id"] for row in body["results"]]

    assert ids(mentee_client, state="upcoming") == [pending["id"]]
    assert ids(mentee_client, state="pending") == [waiting["id"]]
    assert ids(mentee_client, state="closed") == [declined_request["id"]]
    assert set(ids(mentee_client, state="all")) == {
        pending["id"],
        waiting["id"],
        declined_request["id"],
    }
    assert ids(applicant_client, role="mentor", state="pending") == [waiting["id"]]
    assert ids(applicant_client, role="mentee", state="all") == []
    assert ids(other_client, state="all") == []
    assert mentee_client.get(SESSIONS, {"state": "nope"}).status_code == 400


def test_the_list_pages_with_a_cursor(booking_mentor, mentee_client, applicant_client):
    for index in (0, 3, 6):
        session = book(mentee_client, booking_mentor, index)
        applicant_client.post(f"{SESSIONS}/{session['id']}/accept")
        # One waiting request per mentor, so each is confirmed before the next.
    first = mentee_client.get(SESSIONS, {"state": "upcoming", "limit": 2}).json()
    assert len(first["results"]) == 2 and first["next_cursor"]
    second = mentee_client.get(
        SESSIONS, {"state": "upcoming", "limit": 2, "cursor": first["next_cursor"]}
    ).json()
    assert len(second["results"]) == 1 and second["next_cursor"] is None
    starts = [r["starts_at"] for r in first["results"] + second["results"]]
    assert starts == sorted(starts)


def test_the_calendar_file_is_a_valid_event(
    booking_mentor, mentee_client, applicant_client, run_outbox, other_client
):
    view = confirmed(mentee_client, applicant_client, booking_mentor, run_outbox)
    response = mentee_client.get(f"{SESSIONS}/{view['id']}/calendar.ics")
    assert response.status_code == 200
    assert response["Content-Type"].startswith("text/calendar")
    text = response.content.decode()
    assert "BEGIN:VEVENT" in text and f"UID:session-{view['id']}@wocommunity" in text
    assert "https://meet.test/google_meet/" in text
    assert other_client.get(f"{SESSIONS}/{view['id']}/calendar.ics").status_code == 404


# --- a mentor who is withdrawn ---


def test_revoking_a_mentor_cancels_their_open_sessions(
    booking_mentor, mentee, mentee_client, applicant_client, as_admin, run_outbox
):
    agreed = confirmed(mentee_client, applicant_client, booking_mentor, run_outbox, index=0)
    waiting = book(mentee_client, booking_mentor, 3)
    revoke = as_admin.post(
        f"/api/v1/admin/mentors/{booking_mentor.pk}/revoke", {"reason": "Conduct"}, format="json"
    )
    assert revoke.status_code == 200
    run_outbox()
    run_outbox()
    for session_id in (agreed["id"], waiting["id"]):
        row = MentorSession.objects.get(pk=session_id)
        assert row.status == "cancelled" and row.cancelled_by_id is None
    assert FakeMeetingProvider.meetings == {}
    assert notices(mentee, "session_cancelled").count() == 2
    assert "no longer available" in notices(mentee, "session_cancelled").first().payload["reason"]


# --- admin ---


def test_admins_see_and_cancel_sessions(
    booking_mentor, mentee, mentee_client, applicant_client, as_admin, run_outbox, other_client
):
    view = confirmed(mentee_client, applicant_client, booking_mentor, run_outbox)
    assert other_client.get("/api/v1/admin/sessions").status_code == 403
    listing = as_admin.get("/api/v1/admin/sessions", {"status": "confirmed"}).json()
    assert [r["id"] for r in listing["results"]] == [view["id"]]
    assert listing["results"][0]["mentee_email"] == "mentee@example.com"
    one = as_admin.get(f"/api/v1/admin/sessions/{view['id']}")
    assert one.status_code == 200 and one.json()["role"] == "admin"
    assert one.json()["meeting"]["url"]  # support can open the meeting

    url = f"/api/v1/admin/sessions/{view['id']}/cancel"
    assert as_admin.post(url, {}, format="json").status_code == 400
    done = as_admin.post(url, {"reason": "Reported by the founder"}, format="json")
    assert done.status_code == 200 and done.json()["status"] == "cancelled"
    run_outbox()
    assert notices(mentee, "session_cancelled").count() == 1
    assert notices(booking_mentor, "session_cancelled").count() == 1
    assert as_admin.post(url, {"reason": "again"}, format="json").status_code == 409
    filtered = as_admin.get("/api/v1/admin/sessions", {"mentor_id": str(booking_mentor.pk)})
    assert filtered.json()["count"] == 1
    assert as_admin.get("/api/v1/admin/sessions", {"status": "bogus"}).status_code == 400


def test_the_dashboard_and_segments_know_about_sessions(
    booking_mentor, mentee, mentee_client, applicant_client, as_admin, run_outbox
):
    book(mentee_client, booking_mentor)
    snapshot = as_admin.get("/api/v1/admin/dashboard").json()["mentorship"]
    assert snapshot["requests_waiting"] == 1 and snapshot["sessions_upcoming"] == 0
    from apps.mentorship import selectors

    assert selectors.mentee_ids() == {mentee.pk}


# --- a member who is suspended or removed ---

MEMBERS = "/api/v1/admin/members"


def test_suspending_a_founder_cancels_their_open_sessions(
    booking_mentor, mentee, mentee_client, applicant_client, as_admin, run_outbox
):
    agreed = confirmed(mentee_client, applicant_client, booking_mentor, run_outbox, index=0)
    waiting = book(mentee_client, booking_mentor, 3)
    done = as_admin.post(f"{MEMBERS}/{mentee.pk}/suspend", {"reason": "Spam"}, format="json")
    assert done.status_code == 200, done.content
    run_outbox()
    run_outbox()  # the cancellations are events of their own
    for session_id in (agreed["id"], waiting["id"]):
        row = MentorSession.objects.get(pk=session_id)
        assert row.status == "cancelled" and row.cancelled_by_id is None
    assert FakeMeetingProvider.meetings == {}
    assert notices(booking_mentor, "session_cancelled").count() == 2  # the mentor is told


def test_removing_a_mentor_member_cancels_sessions_in_both_roles(
    booking_mentor, mentee, mentee_client, applicant_client, as_admin, run_outbox
):
    as_mentor = confirmed(mentee_client, applicant_client, booking_mentor, run_outbox)
    removed = as_admin.post(
        f"{MEMBERS}/{booking_mentor.pk}/remove", {"reason": "Left"}, format="json"
    )
    assert removed.status_code in (200, 204), removed.content
    run_outbox()
    run_outbox()  # the cancellations are events of their own
    assert MentorSession.objects.get(pk=as_mentor["id"]).status == "cancelled"
    assert notices(mentee, "session_cancelled").count() == 1
