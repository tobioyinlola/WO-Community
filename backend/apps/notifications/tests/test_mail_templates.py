import pytest
from rest_framework import exceptions

from apps.audit.models import AuditLog
from apps.integrations.email.fake import FakeEmailAdapter
from apps.notifications import emails, templatestore
from apps.notifications import mailtemplates as mt
from apps.notifications.models import EmailTemplate, EmailTemplateVersion

pytestmark = pytest.mark.django_db

KEYS = list(mt.TEMPLATES)


@pytest.fixture(autouse=True)
def clear_sent():
    FakeEmailAdapter.reset()


@pytest.mark.parametrize("key", KEYS)
def test_every_template_renders_html_and_text_with_sample_data(key):
    tpl = mt.TEMPLATES[key]
    out = mt.render(key, tpl.sample())
    assert out.subject and "{{" not in out.subject + out.html + out.text
    assert out.html.startswith("<!doctype html>") and 'alt="WO Community"' in out.html
    assert 'name="color-scheme"' in out.html and 'width="600"' in out.html
    assert out.html.count("<a ") <= 4 and "<script" not in out.html
    assert out.html.count('bgcolor="#06372F"') <= 1  # one button at most
    # The sign off ends the message in both forms and is not repeated by the footer.
    assert out.text.count("Best regards,") == 1 and out.text.count("The WO Community Team") == 1
    assert out.html.count("Best regards,") == 1 and out.html.count("The WO Community Team") == 1
    assert out.text.strip() and "<" not in out.text.replace("<-", "")


@pytest.mark.parametrize("key", KEYS)
def test_every_template_renders_without_its_optional_data(key):
    tpl = mt.TEMPLATES[key]
    values = {v.name: v.sample for v in tpl.variables if v.required}
    out = mt.render(key, values)
    assert out.html and out.text and "{{" not in out.html + out.text


def test_a_missing_required_value_is_refused():
    with pytest.raises(mt.TemplateError, match="Missing value for verify_url"):
        mt.render("verification", {})


def test_optional_paragraphs_are_dropped_when_empty_and_kept_when_given():
    base = {"register_url": "https://x.example/r", "expires_on": "1 May 2026"}
    without = mt.render("invitation", base)
    with_note = mt.render("invitation", {**base, "note": "We would love to have you."})
    assert "love to have you" not in without.text and "love to have you" in with_note.text


def test_data_is_escaped_and_cannot_add_markup():
    out = mt.render(
        "job_rejected",
        {
            "job_title": "<script>alert(1)</script>",
            "reason": '"><img src=x onerror=1> **bold** [a](https://evil.example)',
            "job_url": "https://x.example/j",
        },
    )
    assert "<script" not in out.html and "<img src=x" not in out.html
    assert "&lt;script&gt;" in out.html
    assert "<strong>bold</strong>" not in out.html  # markup in data is not read as markup
    assert 'href="https://evil.example"' not in out.html


@pytest.mark.parametrize("bad", ["javascript:alert(1)", "data:text/html,x", "ftp://x.example", "x"])
def test_a_link_variable_must_be_a_web_link(bad):
    with pytest.raises(mt.TemplateError):
        mt.render("verification", {"verify_url": bad})


def test_a_whole_number_variable_is_checked():
    values = {**mt.TEMPLATES["admin_approval_digest"].sample(), "count": "many"}
    with pytest.raises(mt.TemplateError):
        mt.render("admin_approval_digest", values)


def test_list_variables_become_bullets_in_both_forms():
    out = mt.render("digest", mt.TEMPLATES["digest"].sample())
    assert "<li" in out.html and "- 12 new members joined" in out.text


def test_a_broadcast_has_an_unsubscribe_link_and_a_transactional_email_does_not():
    sample = mt.TEMPLATES["announcement"].sample()
    broadcast = mt.render("announcement", sample, unsubscribe_url="https://x.example/u?t=1")
    assert "Unsubscribe" in broadcast.html and "https://x.example/u?t=1" in broadcast.text
    plain = mt.render("verification", mt.TEMPLATES["verification"].sample())
    assert "Unsubscribe" not in plain.html


def test_the_sign_off_is_a_setting(settings):
    settings.EMAIL_SIGNOFF = "Warmly,\nThe Team"
    out = mt.render("welcome", mt.TEMPLATES["welcome"].sample())
    assert "Warmly," in out.text and "Best regards," not in out.text


# --- checking edited copy ---


def copy_for(key, **fields):
    tpl = mt.TEMPLATES[key]
    base = {"subject": tpl.subject, "preheader": tpl.preheader, "body": tpl.body}
    base.update(fields)
    return tpl, base


@pytest.mark.parametrize(
    ("fields", "message"),
    [
        ({"body": "Hello {{nonsense}}"}, "Unknown placeholder"),
        ({"body": "Hello, no link at all"}, "must keep"),
        ({"body": "[button: Go | {{verify_url}}] <b>x</b>"}, "HTML is not allowed"),
        ({"body": "[a](javascript:alert(1)) [button: Go | {{verify_url}}]"}, "https://"),
        (
            {"body": "[button: One | {{verify_url}}]\n\n[button: Two | {{verify_url}}]"},
            "one button",
        ),
        ({"subject": "BUY NOW AND SAVE BIG"}, "all capital"),
        ({"subject": "Hello!!"}, "spam trigger"),
        ({"subject": "Re: your account"}, "Re:"),
        ({"preheader": "x" * 151}, "150"),
    ],
)
def test_bad_copy_is_refused(fields, message):
    tpl, copy = copy_for("verification", **fields)
    with pytest.raises(mt.TemplateError, match=message):
        mt.check_copy(tpl, copy["subject"], copy["preheader"], copy["body"])


# --- saving, history, restore and reset ---


def test_saving_changes_the_wording_and_keeps_every_version(make_user):
    actor = make_user(roles=("super_admin",))
    row = templatestore.save(
        actor=actor,
        key="account_approved",
        subject="You are in",
        preheader="Welcome",
        body="You are in!\n\n[button: Sign in | {{login_url}}]",
    )
    assert row.version == 2
    out = emails.render_template("account_approved", {"login_url": "https://x.example/l"})
    assert out.subject == "You are in" and "You are in!" in out.text
    assert [v.version for v in templatestore.versions("account_approved")] == [2, 1]
    assert AuditLog.objects.filter(action="email.template_edited", target_id="account_approved")


def test_restore_puts_an_earlier_wording_back_as_a_new_version(make_user):
    actor = make_user(roles=("super_admin",))
    templatestore.save(
        actor=actor,
        key="account_approved",
        subject="Edited",
        preheader="",
        body="Edited\n\n[button: Go | {{login_url}}]",
    )
    restored = templatestore.restore(actor=actor, key="account_approved", version=1)
    assert restored.version == 3
    assert templatestore.effective_copy("account_approved").subject == (
        mt.TEMPLATES["account_approved"].subject
    )


def test_reset_goes_back_to_the_built_in_wording_and_keeps_history(make_user):
    actor = make_user(roles=("super_admin",))
    templatestore.save(
        actor=actor,
        key="welcome",
        subject="Edited",
        preheader="",
        body="Edited\n\n[button: Go | {{app_url}}]",
    )
    templatestore.reset(actor=actor, key="welcome")
    assert not EmailTemplate.objects.filter(key="welcome").exists()
    assert EmailTemplateVersion.objects.filter(template_key="welcome").count() == 2
    assert templatestore.effective_copy("welcome").subject == mt.TEMPLATES["welcome"].subject
    assert AuditLog.objects.filter(action="email.template_reset").exists()


def test_saving_bad_copy_changes_nothing(make_user):
    with pytest.raises(exceptions.ValidationError):
        templatestore.save(
            actor=make_user(roles=("super_admin",)),
            key="welcome",
            subject="Hi",
            preheader="",
            body="No button or link here",
        )
    assert not EmailTemplate.objects.exists()


# --- what actually goes out ---


def test_the_verification_email_is_multipart_with_the_sign_off():
    emails.send_verification("ada@example.com", "tok123")
    [sent] = FakeEmailAdapter.sent
    assert sent.html_body.startswith("<!doctype html>") and sent.text_body
    assert (
        "verify-email?token=tok123" in sent.html_body
        and "verify-email?token=tok123" in sent.text_body
    )
    assert sent.text_body.rstrip().count("The WO Community Team") == 1


def test_an_edited_template_is_what_gets_sent(make_user):
    templatestore.save(
        actor=make_user(roles=("super_admin",)),
        key="verification",
        subject="Please confirm",
        preheader="",
        body="Almost there.\n\n[button: Confirm | {{verify_url}}]",
    )
    emails.send_verification("ada@example.com", "tok")
    assert FakeEmailAdapter.sent[0].subject == "Please confirm"
    assert "Almost there." in FakeEmailAdapter.sent[0].text_body
