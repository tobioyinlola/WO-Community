# ruff: noqa: E501
"""Email templates: the copy, the typed variables and the branded layout around them.

Each template has a key, a subject, a preview line and a body written in a tiny, safe markup:

    Paragraphs are separated by a blank line.
    **bold**   [link text](https://example.com)   [link text]({{some_url}})
    Lines that start with "- " make a list.
    {{first_name|there}}   gives "there" when first_name is empty.
    [button: Label | {{review_url}}]   makes the one bulletproof button.
    {{items}}   alone on a line spreads a list variable into bullets.

Everything an administrator types is escaped before the markup is read, and every variable is
escaped when it is put in, so no copy or data can add HTML. Links must be https (or a variable that
holds one). A paragraph that mentions an optional variable left empty is dropped whole.

The layout and brand elements are code, not copy: only the words are editable.
"""

import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from django.conf import settings
from django.utils.html import escape as _escape


def escape(value: Any) -> str:
    return str(_escape(value))


# {{name}} or {{name|fallback}}; the fallback is used when the value is empty.
PLACEHOLDER = re.compile(r"\{\{\s*([a-z_][a-z0-9_]*)\s*(?:\|([^{}|]*))?\}\}")


def names_in(text: str) -> set[str]:
    return {m.group(1) for m in PLACEHOLDER.finditer(text)}


BOLD = re.compile(r"\*\*(.+?)\*\*")
LINK = re.compile(r"\[([^\]\[]+?)\]\(([^()\s]+)\)")
BUTTON = re.compile(r"^\[button:\s*(.+?)\s*\|\s*(.+?)\s*\]$")
SAFE_LINK = re.compile(r"^(https://[^\s\"'<>]+|\{\{[a-z_][a-z0-9_]*\}\})$")

# Brand colours (frontend/src/styles/tokens.css). Text is forest or a muted forest, never gold on cream.
FOREST = "#06372F"
CREAM = "#EEEBE3"
PAPER = "#FFFFFF"
MUTED = "#3C5A52"
LINE = "#D8D3C6"
FONT = "'Hanken Grotesk', Arial, Helvetica, sans-serif"

TRANSACTIONAL = "transactional"
BROADCAST = "broadcast"


class TemplateError(ValueError):
    """The copy or the data does not fit the template."""


@dataclass(frozen=True)
class Var:
    name: str
    kind: str = "text"  # text, url, int, lines
    required: bool = True
    sample: str = ""
    # The copy must keep this variable (a link the email is useless without).
    must_appear: bool = False


@dataclass(frozen=True)
class TemplateDef:
    key: str
    name: str
    stream: str
    about: str
    subject: str
    preheader: str
    body: str
    variables: tuple[Var, ...] = field(default_factory=tuple)

    def var(self, name: str) -> Var | None:
        return next((v for v in self.variables if v.name == name), None)

    def sample(self) -> dict[str, Any]:
        return {v.name: v.sample for v in self.variables}


def _t(
    key: str,
    name: str,
    about: str,
    subject: str,
    preheader: str,
    body: str,
    *variables: Var,
    stream: str = TRANSACTIONAL,
) -> TemplateDef:
    return TemplateDef(key, name, stream, about, subject, preheader, body, tuple(variables))


FIRST = Var("first_name", required=False, sample="Ada")
HI = "Hi {{first_name|there}},\n\n"

TEMPLATES: dict[str, TemplateDef] = {
    t.key: t
    for t in (
        _t(
            "verification",
            "Verify your email",
            "Sent right after someone applies, to confirm their address.",
            "Confirm your email to join WO Community",
            "One quick step and your application goes to our team.",
            HI
            + "Thanks for applying to WO Community, the community for founders, operators and investors.\n\n"
            "Please confirm this is your email address. It takes a few seconds, and your application goes to our team once it's confirmed.\n\n"
            "[button: Confirm my email | {{verify_url}}]\n\n"
            "This link works for 24 hours. If it has expired, sign in and we'll send you a new one.\n\n"
            "If you didn't apply, you can ignore this email. Nothing will happen without confirmation.",
            FIRST,
            Var(
                "verify_url",
                "url",
                sample="https://app.example.com/verify-email?token=abc",
                must_appear=True,
            ),
        ),
        _t(
            "welcome",
            "Welcome",
            "Sent when a member's account is ready to use.",
            "Welcome to WO Community, {{first_name|there}}",
            "Your account is approved. Here's where to start.",
            HI + "Good news: your account is approved and live. Welcome to WO Community.\n\n"
            "Here are three good first steps:\n\n"
            "- **Finish your profile** so the right people can find you in the directory.\n"
            "- **Introduce yourself** in the community feed.\n"
            "- **Look at what's coming up**: events, courses and mentors.\n\n"
            "[button: Go to the community | {{app_url}}]",
            FIRST,
            Var("app_url", "url", sample="https://app.example.com/home", must_appear=True),
        ),
        _t(
            "invitation",
            "You're invited",
            "Sent when an admin invites someone. Invited members are approved when they accept.",
            "You're invited to join WO Community",
            "Your place is reserved. Accept in one click.",
            HI
            + "You've been invited to join WO Community, a community for founders, operators and investors who want real connections and practical help, not noise.\n\n"
            'A note from the team: "{{note}}"\n\n'
            "Your invitation includes a reserved place, so there is no waiting list. Accept it and set up your account in a couple of minutes.\n\n"
            "[button: Accept my invitation | {{register_url}}]\n\n"
            "This invitation is for this email address only and expires on {{expires_on}}.",
            FIRST,
            Var("note", required=False, sample="We would love to have you."),
            Var(
                "register_url",
                "url",
                sample="https://app.example.com/register?invitation=abc",
                must_appear=True,
            ),
            Var("expires_on", sample="20 October 2026"),
        ),
        _t(
            "account_approved",
            "Welcome (account approved)",
            "Sent when an admin approves an application.",
            "Welcome to WO Community, {{first_name|there}}",
            "Your account is approved. Here's where to start.",
            HI
            + "Good news: your application is approved and your account is live. Welcome to WO Community.\n\n"
            "Here are three good first steps:\n\n"
            "- **Finish your profile** so the right people can find you in the directory.\n"
            "- **Introduce yourself** in the community feed.\n"
            "- **Look at what's coming up**: events, courses and mentors.\n\n"
            "[button: Go to the community | {{login_url}}]",
            FIRST,
            Var("login_url", "url", sample="https://app.example.com/login", must_appear=True),
        ),
        _t(
            "account_not_approved",
            "Application not approved",
            "Sent when an admin declines an application.",
            "An update on your WO Community application",
            "Thank you for applying. Here's our decision.",
            HI + "Thank you for applying to WO Community and for the time you put into it.\n\n"
            "After reviewing your application, we're not able to offer you a place right now.\n\n"
            "Our reviewer's note: {{reason}}\n\n"
            "This isn't a permanent decision. If your situation changes, you're welcome to apply again.",
            FIRST,
            Var("reason", required=False, sample="We could not confirm the details you gave."),
        ),
        _t(
            "password_reset",
            "Reset your password",
            "Sent when someone asks to reset a password.",
            "Reset your WO Community password",
            "This link works for 60 minutes.",
            HI + "We received a request to reset the password on your WO Community account.\n\n"
            "[button: Choose a new password | {{reset_url}}]\n\n"
            "This link works for 60 minutes and can be used once.\n\n"
            "If you didn't ask for this, you can ignore this email. Your password won't change. If you're worried someone else is trying to get in, sign in and change your password.",
            FIRST,
            Var(
                "reset_url",
                "url",
                sample="https://app.example.com/reset-password?token=abc",
                must_appear=True,
            ),
        ),
        _t(
            "announcement",
            "News or announcement",
            "A broadcast about news or an announcement.",
            "{{title}}",
            "{{summary}}",
            HI + "**{{title}}**\n\n{{summary}}\n\n[button: Read more | {{link_url}}]",
            FIRST,
            Var("title", sample="A new cohort is open"),
            Var("summary", sample="Applications for the next cohort close on Friday."),
            Var("link_url", "url", sample="https://app.example.com/news/cohort", must_appear=True),
            stream=BROADCAST,
        ),
        _t(
            "job_approved",
            "Job approved",
            "Sent to the person who posted a job when it goes live.",
            "Your job post is live: {{job_title}}",
            "Members can see it now.",
            HI + "**{{job_title}}** is approved and live. We'll remind you before it ends.\n\n"
            "Candidates apply through the method you gave, so keep an eye on it. We don't collect applications on the platform.\n\n"
            "[button: View the live post | {{job_url}}]",
            FIRST,
            Var("job_title", sample="Backend engineer"),
            Var("job_url", "url", sample="https://app.example.com/jobs/1", must_appear=True),
        ),
        _t(
            "job_rejected",
            "Job not approved",
            "Sent to the person who posted a job when it is not approved.",
            "Your job post needs a change: {{job_title}}",
            "Here's what to fix before it can go live.",
            HI
            + "We weren't able to approve **{{job_title}}** as it stands.\n\nReason: {{reason}}\n\n"
            "You can edit the post and send it back for review.\n\n"
            "[button: Edit and resubmit | {{job_url}}]",
            FIRST,
            Var("job_title", sample="Backend engineer"),
            Var("reason", sample="Please add the salary range."),
            Var("job_url", "url", sample="https://app.example.com/jobs/1/edit", must_appear=True),
        ),
        _t(
            "mentor_approved",
            "Mentor application approved",
            "Sent when a mentor application is approved.",
            "You're now a WO Community mentor",
            "Set your availability and pricing to start receiving requests.",
            HI + "Welcome aboard. Your mentor application is approved.\n\n"
            "{{note}}\n\n"
            "The next step is to set your availability and choose whether your sessions are free or paid. You can change both whenever you like in Settings.\n\n"
            "[button: Set my availability | {{url}}]",
            FIRST,
            Var("note", required=False, sample="Thank you for giving your time."),
            Var(
                "url",
                "url",
                sample="https://app.example.com/settings/mentorship",
                must_appear=True,
            ),
        ),
        _t(
            "mentor_not_approved",
            "Mentor application not approved",
            "Sent when a mentor application is declined.",
            "An update on your mentor application",
            "Thank you for applying.",
            HI
            + "Thank you for applying to become a mentor. We're not able to approve your application right now.\n\n"
            "Our reviewer's note: {{note}}\n\n"
            "You're welcome to apply again whenever your experience or availability changes, and you remain a valued member of the community.\n\n"
            "[button: View my application | {{url}}]",
            FIRST,
            Var("note", required=False, sample="We would like to see more mentoring experience."),
            Var(
                "url",
                "url",
                sample="https://app.example.com/mentors/become",
                must_appear=True,
            ),
        ),
        _t(
            "ticket_received",
            "Support request received",
            "Sent when a support request arrives.",
            "We've got your request: {{reference}}",
            "We'll reply here and in the app.",
            HI
            + "Thanks for getting in touch. Your request **{{reference}}: {{subject}}** is with our team. We aim to reply within 24 hours.\n\n"
            "You can follow the conversation and add more details any time in the app.\n\n"
            "[button: View my request | {{ticket_url}}]",
            FIRST,
            Var("reference", sample="WO-1042"),
            Var("subject", sample="I cannot upload my logo"),
            Var("ticket_url", "url", sample="https://app.example.com/support/1", must_appear=True),
        ),
        _t(
            "ticket_reply",
            "Reply to a support request",
            "Sent when support replies to a request.",
            "New reply on your request {{reference}}",
            "{{excerpt}}",
            HI + "Our team has replied to your request **{{reference}}**.\n\n{{excerpt}}\n\n"
            "[button: Read and reply | {{ticket_url}}]",
            FIRST,
            Var("reference", sample="WO-1042"),
            Var("excerpt", required=False, sample="Thanks, we have fixed that for you."),
            Var("ticket_url", "url", sample="https://app.example.com/support/1", must_appear=True),
        ),
        _t(
            "ticket_resolved",
            "Support request resolved",
            "Sent when a support request is marked as resolved.",
            "Your request {{reference}} is marked as resolved",
            "Reply if you still need help.",
            HI
            + "We've marked your request **{{reference}}** as resolved. If everything is sorted, there's nothing more to do.\n\n"
            "{{excerpt}}\n\n"
            "If you still need help, open the request and reply, and we'll pick it straight back up.\n\n"
            "[button: View my request | {{ticket_url}}]",
            FIRST,
            Var("reference", sample="WO-1042"),
            Var("excerpt", required=False, sample="We have fixed your logo upload."),
            Var("ticket_url", "url", sample="https://app.example.com/support/1", must_appear=True),
        ),
        _t(
            "course_access",
            "Access granted",
            "Sent when a member gets access to a course.",
            "You now have access to {{course_title}}",
            "It's ready for you.",
            HI + "Your access to **{{course_title}}** is confirmed and ready to use.\n\n"
            "[button: Start the course | {{course_url}}]",
            FIRST,
            Var("course_title", sample="Founder fundamentals"),
            Var(
                "course_url",
                "url",
                sample="https://app.example.com/learn/courses/1",
                must_appear=True,
            ),
        ),
        _t(
            "certificate_issued",
            "Course completed, certificate issued",
            "Sent when a certificate is ready.",
            "You finished {{course_title}}. Your certificate is ready",
            "Well done. Download your certificate of completion.",
            HI
            + "Congratulations. You've completed **{{course_title}}**, and your certificate of completion is ready.\n\n"
            "You can download it any time from My learning.\n\n"
            "[button: Download my certificate | {{certificate_url}}]",
            FIRST,
            Var("course_title", sample="Founder fundamentals"),
            Var(
                "certificate_url",
                "url",
                sample="https://app.example.com/learn/certificates/1",
                must_appear=True,
            ),
        ),
        _t(
            "admin_approval_needed",
            "Approval needed",
            "Sent to admins when one thing needs their approval. More in the next 15 minutes are batched.",
            "Needs your approval: {{what}} from {{who}}",
            "There's a new item waiting for your review.",
            HI + "There's a new item waiting for your review.\n\n"
            "**Type:** {{what}}\n**From:** {{who}}\n\n"
            "[button: Review request | {{review_url}}]\n\n"
            "You can choose which approval emails you get in your [notification settings]({{settings_url}}).",
            FIRST,
            Var("what", sample="New member request"),
            Var("who", sample="ada@example.com"),
            Var(
                "review_url",
                "url",
                sample="https://app.example.com/admin/approvals",
                must_appear=True,
            ),
            Var("settings_url", "url", sample="https://app.example.com/admin/settings"),
        ),
        _t(
            "admin_approval_digest",
            "Approvals digest",
            "Sent to admins at most every 15 minutes when more items arrive.",
            "{{count}} items waiting for your review",
            "{{kind}}",
            HI + "{{count}} more items are waiting for your review: **{{kind}}**\n\n{{items}}\n\n"
            "[button: Open the approvals queue | {{review_url}}]\n\n"
            "You can choose which approval emails you get in your [notification settings]({{settings_url}}).",
            FIRST,
            Var("count", "int", sample="3"),
            Var("kind", sample="New member requests"),
            Var("items", "lines", sample="ada@example.com\nkofi@example.com"),
            Var(
                "review_url",
                "url",
                sample="https://app.example.com/admin/approvals",
                must_appear=True,
            ),
            Var("settings_url", "url", sample="https://app.example.com/admin/settings"),
        ),
        _t(
            "event_reminder",
            "Event reminder",
            "Sent before an event a member registered for.",
            "Reminder: {{event_title}} starts {{when}}",
            "Here's everything you need to join.",
            HI + "A quick reminder that **{{event_title}}** starts {{when}}.\n\n"
            "[button: Join the event | {{event_url}}]",
            FIRST,
            Var("event_title", sample="Founders Friday"),
            Var("when", sample="in 24 hours"),
            Var("event_url", "url", sample="https://app.example.com/events/1", must_appear=True),
        ),
        _t(
            "digest",
            "Community digest",
            "A broadcast round up of what happened, weekly or monthly.",
            "Your WO Community {{period|week}}",
            "What happened in the community.",
            HI + "Here's what happened in WO Community this {{period|week}}:\n\n{{items}}\n\n"
            "[button: See what's new | {{link_url}}]",
            FIRST,
            Var("period", required=False, sample="week"),
            Var("items", "lines", sample="12 new members joined\n3 new roles were posted"),
            Var("link_url", "url", sample="https://app.example.com/home", must_appear=True),
            stream=BROADCAST,
        ),
        _t(
            "notice",
            "Other notifications",
            "Every other notification that is also sent by email, such as mentoring, event and account updates.",
            "{{title}}",
            "{{title}}",
            HI + "{{title}}\n\n{{detail}}\n\n[button: Open in WO Community | {{link_url}}]",
            FIRST,
            Var("title", sample="Your mentoring session starts in 1 hour"),
            Var("detail", required=False, sample="Join a few minutes early."),
            Var("link_url", "url", sample="https://app.example.com/home", must_appear=True),
        ),
    )
}


# --- checking copy ---

SPAMMY = re.compile(r"(!{2,}|\?{2,}|\$\$|FREE!!|(?i:\bact now\b|\bclick here\b|\b100% free\b))")


def check_subject(subject: str) -> str:
    subject = " ".join(subject.split())
    if not subject or len(subject) > 120:
        raise TemplateError("The subject needs 1 to 120 characters.")
    letters = [c for c in PLACEHOLDER.sub("", subject) if c.isalpha()]
    if len(letters) >= 6 and all(c.isupper() for c in letters):
        raise TemplateError("The subject is all capital letters, which looks like spam.")
    if SPAMMY.search(subject):
        raise TemplateError("The subject uses a spam trigger such as !! or 'click here'.")
    if re.match(r"(?i)^\s*(re|fwd?):", subject):
        raise TemplateError("The subject cannot start with Re: or Fwd:.")
    return subject


def check_copy(tpl: TemplateDef, subject: str, preheader: str, body: str) -> None:
    """Raise ``TemplateError`` if the copy would break the email."""
    check_subject(subject)
    if len(preheader) > 150:
        raise TemplateError("The preview text can be up to 150 characters.")
    if not body.strip() or len(body) > 5000:
        raise TemplateError("The body needs 1 to 5000 characters.")
    if "<" in body or ">" in body:
        raise TemplateError("HTML is not allowed; use **bold**, [links](https://...) and lists.")
    known = {v.name for v in tpl.variables}
    used: set[str] = set()
    for text in (subject, preheader, body):
        used |= names_in(text)
    unknown = used - known
    if unknown:
        raise TemplateError(
            "Unknown placeholder: " + ", ".join("{{" + n + "}}" for n in sorted(unknown)) + "."
        )
    for var in tpl.variables:
        if var.must_appear and var.name not in used:
            raise TemplateError(
                f"The body must keep {{{{{var.name}}}}}, or the email stops working."
            )
    if body.count("](") != len(LINK.findall(body)):
        raise TemplateError("Links must look like [text](https://example.com).")
    for _, target in LINK.findall(body):
        if not SAFE_LINK.match(target):
            raise TemplateError(f"Links must start with https://. Found: {target}")
    buttons = [line for line in body.splitlines() if line.strip().startswith("[button:")]
    if len(buttons) > 1:
        raise TemplateError("Use one button per email.")
    for line in buttons:
        match = BUTTON.match(line.strip())
        if not match or not SAFE_LINK.match(match.group(2)):
            raise TemplateError(
                "A button looks like [button: Label | https://link or {{variable}}]."
            )


# --- variables ---


def _coerce(var: Var, value: Any) -> str:
    if value is None or value == "":
        if var.required:
            raise TemplateError(f"Missing value for {var.name}.")
        return ""
    if var.kind == "int":
        try:
            return str(int(value))
        except (TypeError, ValueError) as exc:
            raise TemplateError(f"{var.name} must be a whole number.") from exc
    if isinstance(value, datetime):
        value = f"{value:%d %B %Y}"
    text = str(value)
    if var.kind == "url":
        if not re.match(r"^https?://[^\s\"'<>]+$", text) or (
            text.startswith("http://") and settings.FRONTEND_BASE_URL.startswith("https://")
        ):
            raise TemplateError(f"{var.name} must be a full https:// link.")
        return text
    if var.kind == "lines":
        return "\n".join(line.strip()[:300] for line in text.splitlines() if line.strip())
    return " ".join(text.split())[:1000]


def clean_values(tpl: TemplateDef, values: dict[str, Any]) -> dict[str, str]:
    return {v.name: _coerce(v, values.get(v.name)) for v in tpl.variables}


# --- turning copy into html and text ---


def _fill(text: str, values: dict[str, str]) -> str:
    """Put escaped values into already escaped copy."""
    # The copy around it is escaped already, and so is a fallback written in it.
    return PLACEHOLDER.sub(
        lambda m: escape(values.get(m.group(1), "")) or (m.group(2) or "").strip(), text
    )


def _inline_html(raw: str, values: dict[str, str], tpl: TemplateDef) -> str:
    text = escape(raw)
    text = BOLD.sub(r"<strong>\1</strong>", text)

    def link(m: re.Match[str]) -> str:
        target = m.group(2)
        if target.startswith("{{"):
            target = _fill(target, values)
        return (
            f'<a href="{target}" style="color:{FOREST};text-decoration:underline">{m.group(1)}</a>'
        )

    text = LINK.sub(link, text)
    return _fill(text, values)


def _inline_text(raw: str, values: dict[str, str]) -> str:
    def plain(match: re.Match[str]) -> str:
        return f"{match.group(1)} ({_fill_raw(match.group(2), values)})"

    text = LINK.sub(plain, raw)
    text = BOLD.sub(r"\1", text)
    return _fill_raw(text, values)


def _fill_raw(text: str, values: dict[str, str]) -> str:
    return PLACEHOLDER.sub(lambda m: values.get(m.group(1), "") or (m.group(2) or "").strip(), text)


def _empty_optional(tpl: TemplateDef, text: str, values: dict[str, str]) -> bool:
    """True when the block names an optional variable that has no value."""
    for match in PLACEHOLDER.finditer(text):
        if match.group(2) is not None:
            continue  # it has a fallback, so it is never empty
        name = match.group(1)
        var = tpl.var(name)
        if var is not None and not var.required and not values.get(name):
            return True
    return False


def _blocks(body: str) -> list[list[str]]:
    return [
        [line for line in block.splitlines() if line.strip()]
        for block in re.split(r"\n\s*\n", body.strip())
        if block.strip()
    ]


def button_html(label: str, url: str) -> str:
    return (
        '<table role="presentation" cellspacing="0" cellpadding="0" border="0" '
        'style="margin:24px 0"><tr><td align="center" bgcolor="' + FOREST + '" '
        'style="border-radius:8px;background:' + FOREST + '">'
        f'<a href="{escape(url)}" style="display:inline-block;padding:14px 28px;'
        f"font-family:{FONT};font-size:16px;font-weight:700;line-height:20px;color:{CREAM};"
        f'text-decoration:none;border-radius:8px">{escape(label)}</a></td></tr></table>'
    )


def body_to_parts(tpl: TemplateDef, body: str, values: dict[str, str]) -> tuple[str, str]:
    """The copy as (html fragment, plain text) with the data filled in."""
    html: list[str] = []
    text: list[str] = []
    paragraph = f"margin:0 0 16px;font-family:{FONT};font-size:16px;line-height:24px;color:{FOREST}"
    for block in _blocks(body):
        joined = "\n".join(block)
        if _empty_optional(tpl, joined, values):
            continue
        first = block[0].strip()
        button = BUTTON.match(first)
        if button and len(block) == 1:
            label, target = button.group(1), _fill_raw(button.group(2), values)
            html.append(button_html(_fill_raw(label, values), target))
            text.append(f"{_fill_raw(label, values)}: {target}")
            continue
        if len(block) == 1 and PLACEHOLDER.fullmatch(first):
            name = PLACEHOLDER.fullmatch(first).group(1)  # type: ignore[union-attr]
            var = tpl.var(name)
            if var is not None and var.kind == "lines":
                lines = [line for line in values.get(name, "").splitlines() if line]
                if not lines:
                    continue
                items = "".join(f'<li style="margin:0 0 6px">{escape(line)}</li>' for line in lines)
                html.append(f'<ul style="{paragraph};padding-left:20px">{items}</ul>')
                text.append("\n".join(f"- {line}" for line in lines))
                continue
        if all(line.strip().startswith("- ") for line in block):
            items = "".join(
                f'<li style="margin:0 0 6px">{_inline_html(line.strip()[2:], values, tpl)}</li>'
                for line in block
            )
            html.append(f'<ul style="{paragraph};padding-left:20px">{items}</ul>')
            text.append("\n".join(f"- {_inline_text(line.strip()[2:], values)}" for line in block))
            continue
        html.append(
            f'<p style="{paragraph}">'
            + "<br>".join(_inline_html(line, values, tpl) for line in block)
            + "</p>"
        )
        text.append("\n".join(_inline_text(line, values) for line in block))
    return "".join(html), "\n\n".join(text)


def signoff_lines() -> list[str]:
    return [line for line in settings.EMAIL_SIGNOFF.splitlines() if line.strip()]


def layout(
    *,
    subject: str,
    preheader: str,
    body_html: str,
    broadcast: bool = False,
    unsubscribe_url: str = "",
    preferences_url: str = "",
) -> str:
    """The branded frame: logo, 600 px column, sign off and footer."""
    sign = "".join(
        f'<p style="margin:0;font-family:{FONT};font-size:16px;line-height:24px;color:{FOREST}">'
        f"{escape(line)}</p>"
        for line in signoff_lines()
    )
    footer_parts = [escape(settings.CAMPAIGN_FOOTER)]
    if broadcast and unsubscribe_url:
        footer_parts.append(
            "You are receiving this because you opted in to news from WO Community."
        )
        footer_parts.append(
            f'<a href="{escape(preferences_url or unsubscribe_url)}" style="color:{MUTED}">'
            f'Email preferences</a> · <a href="{escape(unsubscribe_url)}" style="color:{MUTED}">'
            "Unsubscribe</a>"
        )
    elif preferences_url:
        footer_parts.append(
            f'<a href="{escape(preferences_url)}" style="color:{MUTED}">'
            "Change which emails you get</a>"
        )
    hidden = (
        f'<div style="display:none;max-height:0;overflow:hidden;opacity:0;color:transparent">'
        f"{escape(preheader)}</div>"
        if preheader
        else ""
    )
    return (
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        '<meta name="color-scheme" content="light dark">'
        '<meta name="supported-color-schemes" content="light dark">'
        f"<title>{escape(subject)}</title>"
        "<style>@media (max-width:620px){.wo-col{width:100%!important}.wo-pad{padding:24px 20px!important}}"
        "@media (prefers-color-scheme:dark){.wo-bg{background:#0B1F1A!important}"
        ".wo-card{background:#12302A!important}.wo-card p,.wo-card li,.wo-card strong,"
        ".wo-card a{color:#EEEBE3!important}}</style></head>"
        f'<body class="wo-bg" style="margin:0;padding:0;background:{CREAM}">{hidden}'
        f'<table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" '
        f'class="wo-bg" style="background:{CREAM}"><tr>'
        f'<td align="center" style="padding:24px 12px">'
        f'<table role="presentation" width="600" cellspacing="0" cellpadding="0" border="0" '
        f'class="wo-col wo-card" style="width:600px;max-width:100%;background:{PAPER};'
        f'border-radius:12px"><tr><td class="wo-pad" style="padding:32px 40px 8px">'
        f'<img src="{escape(settings.EMAIL_LOGO_URL)}" width="140" alt="WO Community" '
        f'style="display:block;border:0;height:auto;font-family:{FONT};font-size:18px;'
        f'font-weight:700;color:{FOREST}"></td></tr>'
        f'<tr><td class="wo-pad" style="padding:16px 40px 8px">{body_html}</td></tr>'
        f'<tr><td class="wo-pad" style="padding:8px 40px 32px">{sign}</td></tr></table>'
        f'<table role="presentation" width="600" cellspacing="0" cellpadding="0" border="0" '
        f'class="wo-col" style="width:600px;max-width:100%"><tr><td style="padding:16px 40px;'
        f'font-family:{FONT};font-size:12px;line-height:18px;color:{MUTED};text-align:center">'
        + "<br>".join(footer_parts)
        + "</td></tr></table></td></tr></table></body></html>"
    )


@dataclass(frozen=True)
class Copy:
    subject: str
    preheader: str
    body: str


@dataclass(frozen=True)
class Rendered:
    subject: str
    preheader: str
    html: str
    text: str


def default_copy(tpl: TemplateDef) -> Copy:
    return Copy(tpl.subject, tpl.preheader, tpl.body)


def render(
    key: str,
    values: dict[str, Any],
    *,
    copy: Copy | None = None,
    unsubscribe_url: str = "",
    preferences_url: str = "",
) -> Rendered:
    """One email as subject, html and plain text. ``copy`` replaces the default wording."""
    tpl = TEMPLATES[key]
    use = copy or default_copy(tpl)
    clean = clean_values(tpl, values)
    subject = check_subject(_fill_raw(use.subject, clean))
    preheader = _fill_raw(use.preheader, clean)
    body_html, body_text = body_to_parts(tpl, use.body, clean)
    broadcast = tpl.stream == BROADCAST
    html = layout(
        subject=subject,
        preheader=preheader,
        body_html=body_html,
        broadcast=broadcast,
        unsubscribe_url=unsubscribe_url,
        preferences_url=preferences_url,
    )
    footer = [settings.CAMPAIGN_FOOTER]
    if broadcast and unsubscribe_url:
        footer += ["You are receiving this because you opted in to news from WO Community."]
        footer += [f"Unsubscribe: {unsubscribe_url}"]
    elif preferences_url:
        footer += [f"Change which emails you get: {preferences_url}"]
    text = "\n\n".join([body_text, "\n".join(signoff_lines()), "--\n" + "\n".join(footer)])
    return Rendered(subject=subject, preheader=preheader, html=html, text=text)
