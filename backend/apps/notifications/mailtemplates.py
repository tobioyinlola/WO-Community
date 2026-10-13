# ruff: noqa: E501
"""Email templates: the copy, the typed variables and the branded layout around them.

Each template has a key, a subject, a preview line and a body written in a tiny, safe markup:

    Paragraphs are separated by a blank line.
    **bold**   [link text](https://example.com)   [link text]({{some_url}})
    Lines that start with "- " make a list.
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


PLACEHOLDER = re.compile(r"\{\{\s*([a-z_][a-z0-9_]*)\s*\}\}")
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

TEMPLATES: dict[str, TemplateDef] = {
    t.key: t
    for t in (
        _t(
            "verification",
            "Email verification",
            "Sent when someone registers, to confirm their address.",
            "Confirm your email address",
            "One step left to join WO Community.",
            "Welcome to WO Community.\n\nConfirm your email address to continue.\n\n"
            "[button: Confirm email address | {{verify_url}}]\n\n"
            "The link expires in 24 hours. If you did not register, you can ignore this message.",
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
            "Welcome to WO Community",
            "Here is where to start.",
            "Hi {{first_name}},\n\nWelcome to WO Community, the community for founders building in Africa.\n\n"
            "Start by completing your profile and introducing yourself.\n\n"
            "[button: Open WO Community | {{app_url}}]",
            FIRST,
            Var("app_url", "url", sample="https://app.example.com/home", must_appear=True),
        ),
        _t(
            "invitation",
            "Invitation",
            "Sent when an admin invites someone to join.",
            "You are invited to join WO Community",
            "Your place is waiting.",
            "You have been invited to join WO Community, the community for founders.\n\n"
            "{{note}}\n\n"
            "[button: Create your account | {{register_url}}]\n\n"
            "This invitation is for this email address only and expires on {{expires_on}}.",
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
            "Account approved",
            "Sent when a registration is approved.",
            "Your WO Community account is approved",
            "You can sign in now.",
            "Welcome aboard. Your account has been approved and you can now sign in.\n\n"
            "[button: Sign in | {{login_url}}]",
            Var("login_url", "url", sample="https://app.example.com/login", must_appear=True),
        ),
        _t(
            "account_not_approved",
            "Account not approved",
            "Sent when a registration is not accepted.",
            "Your WO Community registration",
            "An update on your request.",
            "We could not approve your registration at this time.\n\nReason: {{reason}}\n\n"
            "If you think this is a mistake, reply to this email and our team will look again.",
            Var("reason", sample="We could not confirm the details you gave."),
        ),
        _t(
            "password_reset",
            "Password reset",
            "Sent when someone asks to reset a password.",
            "Reset your password",
            "Choose a new password.",
            "Use this button to choose a new password.\n\n"
            "[button: Choose a new password | {{reset_url}}]\n\n"
            "The link expires in 1 hour. If you did not ask for this, you can ignore this message.",
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
            "Hi {{first_name}},\n\n**{{title}}**\n\n{{summary}}\n\n[button: Read more | {{link_url}}]",
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
            "Your job is live: {{job_title}}",
            "Members can see it now.",
            "Your job **{{job_title}}** has been approved and is now live.\n\n"
            "[button: View the job | {{job_url}}]\n\n"
            "Applications are handled directly by the employer.",
            Var("job_title", sample="Backend engineer"),
            Var("job_url", "url", sample="https://app.example.com/jobs/1", must_appear=True),
        ),
        _t(
            "job_rejected",
            "Job rejected",
            "Sent to the person who posted a job when it is not approved.",
            "Your job was not approved: {{job_title}}",
            "You can fix it and send it back.",
            "Your job **{{job_title}}** was not approved.\n\nReason: {{reason}}\n\n"
            "You can edit it and send it back for review.\n\n"
            "[button: Edit the job | {{job_url}}]",
            Var("job_title", sample="Backend engineer"),
            Var("reason", sample="Please add the salary range."),
            Var("job_url", "url", sample="https://app.example.com/jobs/1/edit", must_appear=True),
        ),
        _t(
            "mentor_decision",
            "Mentor application decided",
            "Sent when a mentor application is decided.",
            "Your mentor application: {{outcome}}",
            "We have decided.",
            "We have reviewed your application to become a mentor. It was **{{outcome}}**.\n\n"
            "{{note}}\n\n[button: See the details | {{url}}]",
            Var("outcome", sample="approved"),
            Var("note", required=False, sample="Thank you for giving your time."),
            Var(
                "url",
                "url",
                sample="https://app.example.com/mentoring/application",
                must_appear=True,
            ),
        ),
        _t(
            "ticket_received",
            "Support ticket received",
            "Sent when a support request arrives.",
            "We received your request {{reference}}",
            "We will reply soon.",
            "Thanks for getting in touch. We received your request **{{reference}}**: {{subject}}.\n\n"
            "We will reply as soon as we can. You can follow it here.\n\n"
            "[button: View your request | {{ticket_url}}]",
            Var("reference", sample="WO-1042"),
            Var("subject", sample="I cannot upload my logo"),
            Var("ticket_url", "url", sample="https://app.example.com/support/1", must_appear=True),
        ),
        _t(
            "ticket_reply",
            "Support ticket reply",
            "Sent when support replies to a request.",
            "Support replied to {{reference}}",
            "You have a new reply.",
            "Support replied to your request **{{reference}}**.\n\n{{excerpt}}\n\n"
            "[button: Read the reply | {{ticket_url}}]",
            Var("reference", sample="WO-1042"),
            Var("excerpt", required=False, sample="Thanks, we have fixed that for you."),
            Var("ticket_url", "url", sample="https://app.example.com/support/1", must_appear=True),
        ),
        _t(
            "course_access",
            "Course access granted",
            "Sent when a member gets access to a course.",
            "You now have access to {{course_title}}",
            "Start learning today.",
            "You now have access to **{{course_title}}**.\n\n[button: Start the course | {{course_url}}]",
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
            "Certificate issued",
            "Sent when a certificate is ready.",
            "Your certificate for {{course_title}}",
            "Congratulations on finishing.",
            "Congratulations. You completed **{{course_title}}** and your certificate is ready.\n\n"
            "[button: View your certificate | {{certificate_url}}]",
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
            "Admin approval needed",
            "Sent to admins when one thing needs their approval.",
            "Needs your approval: {{what}}",
            "{{who}} is waiting.",
            "**{{what}}**\n\nFrom: {{who}}\n\n[button: Review request | {{review_url}}]\n\n"
            "You can change which of these emails you get in your [notification settings]({{settings_url}}).",
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
            "Admin approval digest",
            "Sent to admins at most every 15 minutes when more items arrive.",
            "{{count}} more waiting for your approval",
            "{{kind}}",
            "**{{count}} more: {{kind}}**\n\n{{items}}\n\n[button: Review requests | {{review_url}}]\n\n"
            "You can change which of these emails you get in your [notification settings]({{settings_url}}).",
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
            "{{event_title}} starts {{when}}",
            "A reminder from WO Community.",
            "**{{event_title}}** starts {{when}}.\n\n[button: See the event | {{event_url}}]",
            Var("event_title", sample="Founders Friday"),
            Var("when", sample="in 24 hours"),
            Var("event_url", "url", sample="https://app.example.com/events/1", must_appear=True),
        ),
        _t(
            "digest",
            "Weekly or monthly digest",
            "A broadcast round up of what happened.",
            "Your WO Community {{period}} round up",
            "What happened in the community.",
            "Hi {{first_name}},\n\nHere is what happened this {{period}}.\n\n{{items}}\n\n"
            "[button: See it all | {{link_url}}]",
            FIRST,
            Var("period", sample="week"),
            Var("items", "lines", sample="12 new members joined\n3 new jobs were posted"),
            Var("link_url", "url", sample="https://app.example.com/home", must_appear=True),
            stream=BROADCAST,
        ),
        _t(
            "notice",
            "Other notifications",
            "Every other notification that is also sent by email, such as mentoring updates.",
            "{{title}}",
            "{{title}}",
            "{{title}}\n\n{{detail}}\n\n[button: Open | {{link_url}}]",
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
        used |= set(PLACEHOLDER.findall(text))
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
    return PLACEHOLDER.sub(lambda m: escape(values.get(m.group(1), "")), text)


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
    return PLACEHOLDER.sub(lambda m: values.get(m.group(1), ""), text)


def _empty_optional(tpl: TemplateDef, text: str, values: dict[str, str]) -> bool:
    """True when the block names an optional variable that has no value."""
    for name in PLACEHOLDER.findall(text):
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
