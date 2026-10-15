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
