import pytest

from apps.analytics import registry
from apps.analytics.registry import EVENTS, InvalidEvent, validate

# Every event named in the requirements (PRD section 11.1), grouped as written there.
REQUIRED_EVENTS = {
    "registration": [
        "registration_started",
        "registration_step_completed",
        "registration_abandoned",
        "email_verified",
        "member_approved",
        "member_rejected",
        "onboarding_completed",
    ],
    "profile and directory": [
        "profile_updated",
        "directory_viewed",
        "startup_page_viewed",
        "website_link_clicked",
        "join_cta_clicked",
    ],
    "content and jobs": [
        "post_created",
        "post_reacted",
        "comment_created",
        "job_created",
        "job_viewed",
        "job_apply_clicked",
        "job_shared",
        "win_submitted",
        "news_item_viewed",
    ],
    "learning": [
        "course_viewed",
        "course_enrolled",
        "lesson_started",
        "lesson_completed",
        "course_completed",
        "course_checkout_started",
        "course_purchased",
    ],
    "mentorship": [
        "mentor_application_submitted",
        "mentor_application_approved",
        "mentor_application_declined",
        "mentor_viewed",
        "mentor_recommendation_shown",
        "mentor_recommendation_clicked",
        "mentorship_requested",
        "mentorship_accepted",
        "mentorship_declined",
        "session_booked",
        "session_rescheduled",
        "session_cancelled",
        "session_completed",
        "session_feedback_submitted",
    ],
    "email": [
        "newsletter_sent",
        "newsletter_delivered",
        "newsletter_opened",
        "newsletter_clicked",
        "newsletter_unsubscribed",
    ],
    "admin": [
        "member_removed",
        "member_suspended",
        "invitation_sent",
        "invitation_registered",
        "report_actioned",
    ],
}

# Only things the browser alone can see may be reported by the browser.
BROWSER_EVENTS = {
    "registration_started",
    "registration_step_completed",
    "registration_abandoned",
    "directory_viewed",
    "startup_page_viewed",
    "website_link_clicked",
    "join_cta_clicked",
    "job_viewed",
    "job_apply_clicked",
    "job_shared",
    "news_item_viewed",
    "course_viewed",
    "mentor_viewed",
    "mentor_recommendation_clicked",
}


@pytest.mark.parametrize(
    ("group", "name"), [(g, n) for g, names in REQUIRED_EVENTS.items() for n in names]
)
def test_every_event_in_the_requirements_is_registered(group, name):
    assert name in EVENTS, f"{name} ({group}) is missing from the registry"


def test_the_registry_holds_nothing_beyond_the_requirements():
    required = {name for names in REQUIRED_EVENTS.values() for name in names}
    assert set(EVENTS) == required


def test_only_browser_events_can_come_from_the_browser():
    assert {name for name, spec in EVENTS.items() if spec.client} == BROWSER_EVENTS


@pytest.mark.parametrize("name", sorted(set(EVENTS) - BROWSER_EVENTS))
def test_a_browser_cannot_claim_a_server_event(name):
    with pytest.raises(InvalidEvent, match="server"):
        validate(name, {}, from_client=True)


def test_the_server_may_record_browser_events_too():
    assert validate("directory_viewed", {"filtered": True}, from_client=False) == {"filtered": True}


def test_unknown_events_are_refused():
    with pytest.raises(InvalidEvent, match="unknown event"):
        validate("member_promoted", {}, from_client=False)


def test_properties_are_cleaned_and_optional_ones_may_be_left_out():
    assert validate("directory_viewed", {}, from_client=True) == {}
    assert validate("directory_viewed", {"page": 3}, from_client=True) == {"page": 3}
    assert validate("registration_started", {"source": "invite"}, from_client=True) == {
        "source": "invite"
    }


def test_required_properties_must_be_present():
    with pytest.raises(InvalidEvent, match="missing property: source"):
        validate("registration_started", {}, from_client=True)
    with pytest.raises(InvalidEvent, match="missing property: startup_slug"):
        validate("startup_page_viewed", None, from_client=True)


def test_properties_not_in_the_registry_are_refused():
    with pytest.raises(InvalidEvent, match="unknown property: email"):
        validate("directory_viewed", {"email": "a@example.com"}, from_client=True)


@pytest.mark.parametrize(
    ("name", "properties"),
    [
        ("registration_started", {"source": "twitter"}),
        ("registration_started", {"source": 1}),
        ("directory_viewed", {"page": 0}),
        ("directory_viewed", {"page": 1001}),
        ("directory_viewed", {"page": "2"}),
        ("directory_viewed", {"page": 2.5}),
        ("directory_viewed", {"page": True}),
        ("directory_viewed", {"filtered": 1}),
        ("directory_viewed", {"filtered": "yes"}),
        ("member_approved", {"approval_source": "admin", "time_to_decision_hours": -1}),
        ("session_feedback_submitted", {"rating": 6}),
    ],
)
def test_wrong_types_and_ranges_are_refused(name, properties):
    with pytest.raises(InvalidEvent):
        validate(name, properties, from_client=False)


@pytest.mark.parametrize(
    "value",
    [
        "hello world",
        "Capital",
        "a" * 81,
        "",
        "-starts-with-dash",
        "has/slash",
        "<script>",
        "name@example.com",
        "x; DROP TABLE users",
        {"nested": "object"},
        ["list"],
        None,
        42,
    ],
)
def test_free_text_and_odd_values_cannot_be_smuggled_in_as_identifiers(value):
    with pytest.raises(InvalidEvent):
        validate("startup_page_viewed", {"startup_slug": value}, from_client=True)


@pytest.mark.parametrize("value", ["acme-pay-1a2b3c", "a", "x_y-z", "a" * 80])
def test_real_identifiers_pass(value):
    assert validate("startup_page_viewed", {"startup_slug": value}, from_client=True)


def test_too_many_properties_are_refused():
    many = {f"p{n}": n for n in range(registry.MAX_PROPERTIES + 1)}
    with pytest.raises(InvalidEvent):
        validate("directory_viewed", many, from_client=True)


def test_properties_must_be_an_object():
    with pytest.raises(InvalidEvent):
        validate("directory_viewed", ["a"], from_client=True)  # type: ignore[arg-type]


def test_no_property_anywhere_is_free_text():
    kinds = {prop.kind for spec in EVENTS.values() for prop in spec.props.values()}
    assert kinds <= {"enum", "int", "bool", "slug"}
