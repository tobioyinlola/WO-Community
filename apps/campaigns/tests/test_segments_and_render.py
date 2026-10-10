from datetime import timedelta

import pytest
from django.utils import timezone
from rest_framework import exceptions

from apps.accounts.models import User
from apps.campaigns import render, segments
from apps.campaigns.tests.conftest import BLOCKS, set_profile, subscriber
from apps.notifications import services as notifications

pytestmark = pytest.mark.django_db


def emails(definition):
    return sorted(email for _, email in segments.recipients(segments.clean(definition)))


# --- who may be mailed at all ---


def test_only_active_verified_members_who_agreed_are_ever_mailed(make_user):
    subscriber(make_user, "yes@example.com")
    subscriber(make_user, "declined@example.com", consent=False)
    subscriber(make_user, "pending@example.com", status="pending")
    subscriber(make_user, "suspended@example.com", status="suspended")
    unverified = make_user(email="unverified@example.com", approved_at=timezone.now())
    from apps.accounts import services as accounts

    accounts.set_marketing_consent(unverified.pk, True)
    assert emails({}) == ["yes@example.com"]


def test_the_latest_consent_wins(make_user):
    from apps.accounts import services as accounts

    user = subscriber(make_user, "flip@example.com")
    accounts.set_marketing_consent(user.pk, False)
    assert emails({}) == []
    accounts.set_marketing_consent(user.pk, True)
    assert emails({}) == ["flip@example.com"]


def test_suppressed_addresses_are_excluded_even_with_consent(make_user):
    subscriber(make_user, "ok@example.com")
    subscriber(make_user, "bounced@example.com")
    notifications.suppress("Bounced@Example.com", "bounced")
    assert emails({}) == ["ok@example.com"]


def test_preview_separates_matching_from_mailable(make_user):
    subscriber(make_user, "a@example.com")
    subscriber(make_user, "b@example.com", consent=False)
    assert segments.preview({}) == {"matching": 2, "eligible": 1}


# --- the attributes ---


def test_country_filter(make_user):
    ng = subscriber(make_user, "ng@example.com")
    ke = subscriber(make_user, "ke@example.com")
    subscriber(make_user, "none@example.com")
    set_profile(ng, country="NG")
    set_profile(ke, country="KE")
    assert emails({"country": ["ng"]}) == ["ng@example.com"]
    assert emails({"country": ["NG", "KE"]}) == ["ke@example.com", "ng@example.com"]


def test_sector_and_stage_filters_use_the_members_startups(make_user, client_for):
    from apps.startups.tests.conftest import STARTUPS, new_startup_body

    fin = subscriber(make_user, "fin@example.com")
    other = subscriber(make_user, "other@example.com")
    client_for(fin).post(STARTUPS, new_startup_body(sector="fintech", stage="seed"))
    client_for(other).post(STARTUPS, new_startup_body(sector="healthtech", stage="idea"))
    assert emails({"sector": ["fintech"]}) == ["fin@example.com"]
    assert emails({"stage": ["idea"]}) == ["other@example.com"]
    assert (
        emails({"sector": ["fintech"], "stage": ["idea"]}) == []
    )  # all given conditions must hold


def test_skills_filter(make_user):
    from apps.profiles.models import FounderProfile
    from apps.profiles.services import get_or_create_profile
    from apps.reference.models import Skill

    user = subscriber(make_user, "skilled@example.com")
    subscriber(make_user, "plain@example.com")
    skill = Skill.objects.first()
    FounderProfile.objects.get(pk=get_or_create_profile(user.pk).pk).skills.add(skill)
    assert emails({"skills": [skill.slug]}) == ["skilled@example.com"]


def test_role_filter_finds_mentors(make_user):
    subscriber(make_user, "mentor@example.com", roles=("member", "mentor"))
    subscriber(make_user, "member@example.com")
    assert emails({"roles": ["mentor"]}) == ["mentor@example.com"]


def test_joined_and_last_active_date_filters(make_user):
    old = subscriber(make_user, "old@example.com")
    subscriber(make_user, "new@example.com")
    User.objects.filter(pk=old.pk).update(
        created_at=timezone.now() - timedelta(days=100),
        last_login=timezone.now() - timedelta(days=50),
    )
    cutoff = (timezone.now() - timedelta(days=30)).date().isoformat()
    assert emails({"joined_after": cutoff}) == ["new@example.com"]
    assert emails({"joined_before": cutoff}) == ["old@example.com"]
    assert emails({"last_active_before": cutoff}) == ["old@example.com"]
    assert emails({"last_active_after": cutoff}) == []


def test_completeness_range(make_user):
    high = subscriber(make_user, "high@example.com")
    low = subscriber(make_user, "low@example.com")
    set_profile(high, completeness_score=90)
    set_profile(low, completeness_score=20)
    assert emails({"completeness_min": 80}) == ["high@example.com"]
    assert emails({"completeness_max": 50}) == ["low@example.com"]
    assert emails({"completeness_min": 10, "completeness_max": 95}) == [
        "high@example.com",
        "low@example.com",
    ]


def test_tags(make_user, client_for):
    from apps.feed.tests.conftest import write_post
    from apps.startups.models import Startup
    from apps.startups.tests.conftest import STARTUPS, new_startup_body

    complete = subscriber(make_user, "complete@example.com")
    incomplete = subscriber(make_user, "incomplete@example.com")
    poster = subscriber(make_user, "poster@example.com")
    set_profile(complete, completeness_score=85)
    client = client_for(poster)
    write_post(client)
    startup = client_for(complete).post(STARTUPS, new_startup_body()).json()["id"]
    Startup.objects.filter(pk=startup).update(directory_opt_in=True)
    assert emails({"tags": ["profile_complete"]}) == ["complete@example.com"]
    assert "complete@example.com" not in emails({"tags": ["registered_incomplete"]})
    assert "incomplete@example.com" in emails({"tags": ["registered_incomplete"]})
    assert emails({"tags": ["directory_listed"]}) == ["complete@example.com"]
    assert emails({"tags": ["founder_active"]}) == ["poster@example.com"]
    assert "poster@example.com" not in emails({"tags": ["founder_dormant"]})
    assert incomplete


def test_job_posters_tag(make_user, client_for):
    from apps.jobs.tests.conftest import job_body

    poster = subscriber(make_user, "boss@example.com")
    subscriber(make_user, "worker@example.com")
    client_for(poster).post("/api/v1/jobs", job_body(), format="json")
    from apps.jobs.models import Job

    Job.objects.update(published_at=timezone.now(), status="published")
    assert emails({"tags": ["job_poster"]}) == ["boss@example.com"]


def test_several_values_in_one_list_mean_any_of_them_and_empty_means_everyone(make_user):
    for i in range(3):
        subscriber(make_user, f"m{i}@example.com")
    assert len(emails({})) == 3


# --- the definition is strictly checked ---


@pytest.mark.parametrize(
    "definition",
    [
        {"nonsense": 1},
        {"country": ["XX"]},
        {"country": []},
        {"country": "NG"},
        {"sector": ["not-a-sector"]},
        {"stage": ["not-a-stage"]},
        {"skills": ["not-a-skill"]},
        {"roles": ["admin"]},
        {"tags": ["vip"]},
        {"completeness_min": 101},
        {"completeness_min": 80, "completeness_max": 20},
        {"joined_after": "2026-02-01", "joined_before": "2026-01-01"},
        {"joined_after": "yesterday"},
        {"country": ["NG"] * 51},
        {"sql": "1=1; DROP TABLE"},
    ],
)
def test_bad_definitions_are_refused(definition):
    with pytest.raises(exceptions.ValidationError):
        segments.clean(definition)


def test_cleaning_normalises_and_serialises_the_definition():
    cleaned = segments.clean({"country": ["ng", "NG", "ke"], "joined_after": "2026-01-01"})
    assert cleaned == {"country": ["NG", "KE"], "joined_after": "2026-01-01"}


# --- blocks and merge fields ---


def clean(blocks, owner):
    return render.clean_blocks(blocks, owner_id=owner)


def test_valid_blocks_are_cleaned(admin):
    cleaned = clean(BLOCKS, admin.pk)
    assert [b["type"] for b in cleaned] == ["heading", "paragraph", "button", "divider"]


@pytest.mark.parametrize(
    "blocks",
    [
        [],
        "nope",
        [{"type": "video"}],
        [{"type": "heading", "text": ""}],
        [{"type": "heading", "text": "x" * 151}],
        [{"type": "heading", "text": "ok", "level": 5}],
        [{"type": "paragraph", "html": "<p></p>"}],
        [{"type": "paragraph", "html": "<p>{{last_name}}</p>"}],
        [{"type": "heading", "text": "{{password}}"}],
        [{"type": "button", "label": "Go", "url": "http://insecure.example.com"}],
        [{"type": "button", "label": "Go", "url": "javascript:alert(1)"}],
        [{"type": "button", "label": "", "url": "https://x.example.com"}],
        [{"type": "button", "label": "Go", "url": "https://x.example.com", "onclick": "x()"}],
        [{"type": "image"}],
        [{"type": "image", "image_key": "media/profile_photo/abc"}],
        [{"type": "divider"}] * 41,
    ],
)
def test_bad_blocks_are_refused(admin, blocks):
    with pytest.raises(exceptions.ValidationError):
        clean(blocks, admin.pk)


def test_paragraph_markup_is_sanitised(admin):
    [block] = clean(
        [{"type": "paragraph", "html": "<p onclick='x()'>hi</p><script>bad()</script><h1>x</h1>"}],
        admin.pk,
    )
    assert (
        "<script" not in block["html"]
        and "onclick" not in block["html"]
        and "<h1" not in block["html"]
    )


def rendered(admin, first="Ada", blocks=None):
    return render.render(
        preheader="Preview text",
        blocks=clean(blocks or BLOCKS, admin.pk),
        first_name=first,
        unsubscribe_url="https://app.test/unsubscribe?token=abc",
    )


def test_merge_fields_are_filled_and_everything_is_escaped(admin):
    page, text = rendered(admin, first="<b>Ada</b>")
    assert "Hello &lt;b&gt;Ada&lt;/b&gt;" in page and "<b>Ada</b>" not in page
    assert "</strong>, &lt;b&gt;Ada&lt;/b&gt;." in page
    assert "Read more: https://wocommunity.example.com/news" in text


def test_a_member_with_no_name_is_greeted_politely(admin):
    page, text = rendered(admin, first="")
    assert "Hello there" in page and "HELLO THERE" in text


def test_every_email_carries_an_unsubscribe_link_and_the_preheader(admin):
    page, text = rendered(admin)
    assert 'href="https://app.test/unsubscribe?token=abc"' in page
    assert "Unsubscribe: https://app.test/unsubscribe?token=abc" in text
    assert "opted in" in page and "Preview text" in page


def test_a_link_in_a_button_cannot_break_out_of_its_attribute(admin):
    page, _ = rendered(
        admin,
        blocks=[
            {
                "type": "button",
                "label": 'Go"><script>x()</script>',
                "url": 'https://x.example.com/?a=1&b="2',
            }
        ],
    )
    assert "<script>x()" not in page


def test_learning_tags(make_user):
    from apps.learning import learn
    from apps.learning.tests.conftest import build_course, lesson_ids

    teacher = make_user(roles=("content_editor",), email="teacher@example.com")
    free = build_course(teacher, title="Free one")
    paid = build_course(teacher, title="Paid one", access="paid", price_minor=100, currency="USD")
    starter = subscriber(make_user, "starter@example.com")
    finisher = subscriber(make_user, "finisher@example.com")
    buyer = subscriber(make_user, "buyer@example.com")
    subscriber(make_user, "bystander@example.com")
    learn.enrol(user_id=starter.pk, course_id=free.pk)
    learn.enrol(user_id=finisher.pk, course_id=free.pk)
    for lesson in lesson_ids(free):
        learn.update_progress(
            user_id=finisher.pk, lesson_id=lesson, position_seconds=None, completed=True
        )
    learn.grant(actor=teacher, course_id=paid.pk, user_id=buyer.pk)
    assert emails({"tags": ["learner_free"]}) == ["finisher@example.com", "starter@example.com"]
    assert emails({"tags": ["learner_paid"]}) == ["buyer@example.com"]
    assert emails({"tags": ["course_completed"]}) == ["finisher@example.com"]
