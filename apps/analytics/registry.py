"""Every analytics event, defined once.

An event is accepted only if its name is listed here and every property is one
the entry allows, with the right type. There is no free text type: a property
is a number, a yes/no, one of a fixed set of words, or a short identifier
(a slug). That is how bios, posts and other personal text are kept out of
analytics by construction rather than by care.

``client`` marks events the browser may report (things only the browser can
see, such as a page view). Everything else is recorded by the server when the
action really happens, and a browser cannot claim it.
"""

import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

SLUG = re.compile(r"^[a-z0-9][a-z0-9_-]{0,79}$")
MAX_PROPERTIES = 12


class InvalidEvent(ValueError):
    """The event is not in the registry, or its properties do not match."""


@dataclass(frozen=True)
class Prop:
    kind: str  # "enum", "int", "bool" or "slug"
    required: bool = False
    choices: tuple[str, ...] = ()
    low: int = 0
    high: int = 1_000_000


@dataclass(frozen=True)
class Spec:
    client: bool = False
    props: Mapping[str, Prop] = field(default_factory=dict)


def enum(*choices: str, required: bool = True) -> Prop:
    return Prop("enum", required=required, choices=choices)


def number(low: int = 0, high: int = 1_000_000, required: bool = False) -> Prop:
    return Prop("int", required=required, low=low, high=high)


def flag(required: bool = False) -> Prop:
    return Prop("bool", required=required)


def slug(required: bool = True) -> Prop:
    return Prop("slug", required=required)


STEPS = ("account", "profile", "startup", "consent", "verification")
PLACES = ("home", "directory", "startup_page", "founder_page", "jobs", "news")
PLAN = ("free", "paid")

EVENTS: dict[str, Spec] = {
    # Registration funnel
    "registration_started": Spec(
        client=True, props={"source": enum("organic", "invite", "referral")}
    ),
    "registration_step_completed": Spec(client=True, props={"step": enum(*STEPS)}),
    "registration_abandoned": Spec(client=True, props={"step": enum(*STEPS)}),
    "email_verified": Spec(),
    "member_approved": Spec(
        props={
            "approval_source": enum("admin", "invitation"),
            "time_to_decision_hours": number(high=100_000),
        }
    ),
    "member_rejected": Spec(props={"time_to_decision_hours": number(high=100_000)}),
    "onboarding_completed": Spec(),
    # Profile and directory
    "profile_updated": Spec(props={"completeness": number(high=100)}),
    "directory_viewed": Spec(
        client=True, props={"filtered": flag(), "page": number(low=1, high=1000)}
    ),
    "startup_page_viewed": Spec(client=True, props={"startup_slug": slug()}),
    "website_link_clicked": Spec(client=True, props={"startup_slug": slug()}),
    "join_cta_clicked": Spec(client=True, props={"location": enum(*PLACES)}),
    # Content and jobs
    "post_created": Spec(props={"category": slug()}),
    "post_reacted": Spec(props={"kind": enum("like", "celebrate", "insightful")}),
    "comment_created": Spec(),
    "job_created": Spec(props={"job_type": slug()}),
    "job_viewed": Spec(client=True, props={"job_id": slug()}),
    "job_apply_clicked": Spec(client=True, props={"job_id": slug()}),
    "job_shared": Spec(
        client=True, props={"channel": enum("copy", "linkedin", "x", "whatsapp", "email")}
    ),
    "win_submitted": Spec(props={"kind": enum("award", "funding", "partnership")}),
    "news_item_viewed": Spec(client=True, props={"item_type": slug()}),
    # Learning
    "course_viewed": Spec(client=True, props={"course_id": slug()}),
    "course_enrolled": Spec(props={"course_id": slug(), "access": enum(*PLAN)}),
    "lesson_started": Spec(props={"course_id": slug()}),
    "lesson_completed": Spec(props={"course_id": slug()}),
    "course_completed": Spec(props={"course_id": slug()}),
    "course_checkout_started": Spec(props={"course_id": slug()}),
    "course_purchased": Spec(props={"course_id": slug()}),
    # Mentorship
    "mentor_application_submitted": Spec(),
    "mentor_application_approved": Spec(),
    "mentor_application_declined": Spec(),
    "mentor_viewed": Spec(client=True, props={"mentor_id": slug()}),
    "mentor_recommendation_shown": Spec(props={"count": number(high=100)}),
    "mentor_recommendation_clicked": Spec(client=True, props={"mentor_id": slug()}),
    "mentorship_requested": Spec(),
    "mentorship_accepted": Spec(props={"response_hours": number(high=100_000)}),
    "mentorship_declined": Spec(props={"response_hours": number(high=100_000)}),
    "session_booked": Spec(),
    "session_rescheduled": Spec(),
    "session_cancelled": Spec(props={"cancelled_by": enum("mentor", "founder")}),
    "session_completed": Spec(),
    "session_feedback_submitted": Spec(props={"rating": number(low=1, high=5)}),
    # Email
    "newsletter_sent": Spec(props={"campaign": slug(), "segment": slug(required=False)}),
    "newsletter_delivered": Spec(props={"campaign": slug()}),
    "newsletter_opened": Spec(props={"campaign": slug()}),
    "newsletter_clicked": Spec(props={"campaign": slug()}),
    "newsletter_unsubscribed": Spec(props={"campaign": slug()}),
    # Admin
    "member_removed": Spec(),
    "member_suspended": Spec(),
    "invitation_sent": Spec(props={"role": enum("member", "mentor"), "bulk": flag()}),
    "invitation_registered": Spec(props={"role": enum("member", "mentor")}),
    "report_actioned": Spec(props={"outcome": enum("reviewed", "actioned")}),
}


def validate(
    name: str, properties: Mapping[str, Any] | None, *, from_client: bool
) -> dict[str, Any]:
    """Return the cleaned properties, or raise ``InvalidEvent``."""
    spec = EVENTS.get(name)
    if spec is None:
        raise InvalidEvent("unknown event")
    if from_client and not spec.client:
        raise InvalidEvent("this event is recorded by the server")
    properties = properties or {}
    if not isinstance(properties, Mapping) or len(properties) > MAX_PROPERTIES:
        raise InvalidEvent("properties must be a small object")
    unknown = set(properties) - set(spec.props)
    if unknown:
        raise InvalidEvent(f"unknown property: {sorted(unknown)[0]}")
    cleaned: dict[str, Any] = {}
    for key, prop in spec.props.items():
        if key not in properties:
            if prop.required:
                raise InvalidEvent(f"missing property: {key}")
            continue
        cleaned[key] = _check(key, prop, properties[key])
    return cleaned


def _check(key: str, prop: Prop, value: Any) -> Any:
    if prop.kind == "bool":
        if not isinstance(value, bool):
            raise InvalidEvent(f"{key} must be true or false")
        return value
    if prop.kind == "int":
        if (
            isinstance(value, bool)
            or not isinstance(value, int)
            or not prop.low <= value <= prop.high
        ):
            raise InvalidEvent(f"{key} must be a whole number from {prop.low} to {prop.high}")
        return value
    if not isinstance(value, str):
        raise InvalidEvent(f"{key} must be text from a fixed set")
    if prop.kind == "enum":
        if value not in prop.choices:
            raise InvalidEvent(f"{key} must be one of: {', '.join(prop.choices)}")
        return value
    if prop.kind == "slug":
        if not SLUG.match(value):
            raise InvalidEvent(f"{key} must be a short identifier (letters, numbers, - and _)")
        return value
    raise InvalidEvent(f"{key} has an unsupported type")  # pragma: no cover
