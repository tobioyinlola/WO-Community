import pytest

from apps.notifications import mailtemplates as mt
from apps.notifications.notify import app_path, mail_template_for

URL = "https://app.example.com/x"


def test_a_fallback_fills_an_empty_value_and_keeps_the_paragraph():
    copy = mt.Copy(
        "Welcome, {{first_name|there}}",
        "p",
        "Hi {{first_name|there}},\n\n[button: Go | {{app_url}}]",
    )
    assert mt.render("welcome", {"app_url": URL}, copy=copy).subject == "Welcome, there"
    named = mt.render("welcome", {"app_url": URL, "first_name": "Ada"}, copy=copy)
    assert named.subject == "Welcome, Ada" and named.text.startswith("Hi Ada,")


@pytest.mark.parametrize("key", sorted(mt.TEMPLATES))
def test_every_default_copy_passes_its_own_checks_and_signs_off_once(key):
    tpl = mt.TEMPLATES[key]
    mt.check_copy(tpl, tpl.subject, tpl.preheader, tpl.body)
    rendered = mt.render(key, tpl.sample())
    assert rendered.text.count("Best regards,") == 1
    assert "reply to this email" not in rendered.text.lower()


@pytest.mark.parametrize(
    ("path", "screen"),
    [
        ("/home", "/app"),
        ("/sessions/abc", "/app/mentors/sessions"),
        ("/posts/abc", "/app/feed"),
        ("/jobs/1", "/app/jobs/1"),
        ("/admin/support?ticket=1", "/admin/support?ticket=1"),
        ("/news/a-story", "/news/a-story"),
    ],
)
def test_notification_links_open_real_screens(path, screen):
    assert app_path(path) == screen


def test_mentor_decisions_use_their_own_templates():
    approved = mail_template_for(
        "mentor_application_decision", "t", "", URL, {"decision": "approved"}
    )
    declined = mail_template_for(
        "mentor_application_decision",
        "t",
        "",
        URL,
        {"decision": "declined", "reason": "More detail"},
    )
    more_info = mail_template_for("mentor_application_decision", "t", "", URL, {"decision": "info"})
    assert approved[0] == "mentor_approved"
    assert declined == ("mentor_not_approved", {"note": "More detail", "url": URL})
    assert more_info[0] == "notice"


def _rendered(type_, payload, **kwargs):
    key, values = mail_template_for(type_, "t", "", URL, payload, **kwargs)
    return key, mt.render(key, values)


def test_a_session_request_says_who_and_when_in_the_mentors_time_zone():
    key, email = _rendered(
        "session_requested",
        {
            "starts_at": "2026-10-20T14:00:00+00:00",
            "timezone": "Africa/Lagos",
            "message": "Help with my deck",
            "payment": "arranged",
        },
        who="Ada Obi",
    )
    assert key == "session_requested"
    assert email.subject == "Ada Obi would like a session with you"
    assert "on Tuesday 20 October 2026 at 3:00 PM (Africa/Lagos)" in email.text
    assert '"Help with my deck"' in email.text
    assert "agree payment directly" in email.text


def test_the_members_own_time_zone_wins_once_they_have_set_one():
    _, email = _rendered(
        "session_confirmed",
        {"starts_at": "2026-10-20T14:00:00+00:00", "timezone": "Africa/Lagos"},
        who="Kofi",
        tz="Europe/London",
    )
    assert email.subject == "Your session is confirmed for Tuesday 20 October 2026"
    assert "3:00 PM (Europe/London)" in email.text
    assert "We'll add the meeting link to your session page" in email.text
    assert "payment" not in email.text


def test_event_emails_carry_the_date_place_and_changes():
    payload = {
        "title": "Founders Friday",
        "starts_at": "2026-10-23T17:00:00+00:00",
        "timezone": "Africa/Lagos",
        "where": "Online",
    }
    key, registered = _rendered("event_registered", payload)
    assert key == "event_registered"
    assert "**" not in registered.text
    assert "When: Friday 23 October 2026, 6:00 PM (Africa/Lagos)" in registered.text
    assert "Where: Online" in registered.text
    _, moved = _rendered("event_rescheduled", payload)
    assert moved.subject == "Update on Founders Friday"
    assert "The new date and time is Friday 23 October 2026, 6:00 PM (Africa/Lagos)." in moved.text
    _, cancelled = _rendered("event_cancelled", payload)
    assert "it has been cancelled." in cancelled.text and "new date" not in cancelled.text


def test_an_older_reminder_without_times_still_sends():
    _, email = _rendered("event_reminder", {"title": "Founders Friday", "when": "1h"})
    assert email.subject == "Reminder: Founders Friday starts in 1 hour"
    assert "When:" not in email.text


def test_removals_and_replies_use_their_own_templates():
    assert _rendered("job_changed", {"title": "Engineer", "what": "removed"})[0] == "job_removed"
    assert _rendered("job_changed", {"title": "Engineer", "what": "closed"})[0] == "notice"
    key, post = _rendered("post_moderated", {"what": "removed", "reason": "Spam"})
    assert key == "post_removed" and "Reason: Spam" in post.text
    assert "/legal/conduct" in post.text
    _, reply = _rendered("reply", {"excerpt": "Agreed"}, who="Ada")
    assert reply.subject == "Ada replied to your comment"
    assert '"Agreed"' in reply.text


def test_job_expiry_gives_the_date():
    key, email = _rendered(
        "job_expiring", {"title": "Engineer", "expires_at": "2026-10-18T09:00:00+00:00"}
    )
    assert key == "job_expiring"
    assert email.subject == "Your job post ends in 3 days: Engineer"
    assert "come down on Sunday 18 October 2026" in email.text
