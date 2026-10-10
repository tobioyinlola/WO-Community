import datetime
from types import SimpleNamespace

import pytest
from rest_framework.exceptions import ValidationError

from apps.core import etag
from apps.core.text import clean_url, plain
from apps.core.visibility import (
    Audience,
    Level,
    audience_for,
    can_see,
    effective_levels,
    project,
)

# --- visibility ---

MATRIX = [
    (Level.PRIVATE, Audience.PUBLIC, False),
    (Level.PRIVATE, Audience.MEMBER, False),
    (Level.PRIVATE, Audience.OWNER, True),
    (Level.MEMBERS, Audience.PUBLIC, False),
    (Level.MEMBERS, Audience.MEMBER, True),
    (Level.MEMBERS, Audience.OWNER, True),
    (Level.PUBLIC, Audience.PUBLIC, True),
    (Level.PUBLIC, Audience.MEMBER, True),
    (Level.PUBLIC, Audience.OWNER, True),
]


@pytest.mark.parametrize(("level", "audience", "expected"), MATRIX)
def test_visibility_matrix(level, audience, expected):
    assert can_see(level.value, audience) is expected


def test_unknown_levels_are_never_visible_to_others():
    assert can_see("secret", Audience.MEMBER) is False
    assert can_see("secret", Audience.PUBLIC) is False


def user(pk, status="active", authenticated=True):
    return SimpleNamespace(pk=pk, status=status, is_authenticated=authenticated)


def test_audience_depends_on_who_is_looking():
    assert audience_for(None) == Audience.PUBLIC
    assert audience_for(user(1, authenticated=False)) == Audience.PUBLIC
    assert audience_for(user(1), {1}) == Audience.OWNER
    assert audience_for(user(2), {1}) == Audience.MEMBER
    assert audience_for(user(2, status="pending"), {1}) == Audience.PUBLIC
    assert audience_for(user(2, status="suspended"), {1}) == Audience.PUBLIC


def test_a_pending_owner_still_sees_their_own_data():
    assert audience_for(user(1, status="pending"), {1}) == Audience.OWNER


def test_effective_levels_layers_choices_over_defaults_and_ignores_junk():
    defaults = {"a": "members", "b": "private"}
    assert effective_levels({"b": "public", "c": "public", "a": "bogus"}, defaults) == {
        "a": "members",
        "b": "public",
    }
    assert effective_levels(None, defaults) == defaults


def test_project_includes_only_permitted_groups_and_hides_unlisted_ones():
    groups = {"x": {"one": 1}, "y": {"two": 2}, "z": {"three": 3}}
    levels = {"x": "public", "y": "members"}  # z has no level, so it stays hidden
    assert project(groups, levels, Audience.PUBLIC) == {"one": 1}
    assert project(groups, levels, Audience.MEMBER) == {"one": 1, "two": 2}
    assert project(groups, levels, Audience.OWNER) == {"one": 1, "two": 2}


# --- etag ---


def record(pk=1, stamp=datetime.datetime(2026, 1, 1, tzinfo=datetime.UTC)):
    return SimpleNamespace(pk=pk, updated_at=stamp)


def test_etag_changes_when_the_record_changes():
    first = etag.etag_for(record())
    assert first.startswith('"') and first.endswith('"')
    assert etag.etag_for(record()) == first
    assert etag.etag_for(record(stamp=datetime.datetime(2026, 1, 2, tzinfo=datetime.UTC))) != first
    assert etag.etag_for(record(pk=2)) != first


def test_a_matching_header_passes_including_weak_form():
    item = record()
    etag.assert_matches(etag.etag_for(item), item)
    etag.assert_matches("W/" + etag.etag_for(item), item)


def test_missing_header_is_428_and_stale_header_is_412():
    item = record()
    with pytest.raises(etag.PreconditionRequiredError):
        etag.assert_matches(None, item)
    with pytest.raises(etag.PreconditionRequiredError):
        etag.assert_matches("", item)
    with pytest.raises(etag.PreconditionFailedError):
        etag.assert_matches('"stale"', item)
    with pytest.raises(etag.PreconditionFailedError):
        etag.assert_matches("*", item)


# --- text ---


@pytest.mark.parametrize(
    ("raw", "cleaned"),
    [
        ("  Hello  ", "Hello"),
        ("<b>Bold</b> move", "Bold move"),
        ("<script>alert(1)</script>Safe", "Safe"),
        ("Tom &amp; Jerry", "Tom & Jerry"),
        ("ARR > $1M", "ARR > $1M"),
        ("bell\x07 char", "bell char"),
        ("<img src=x onerror=alert(1)>Pic", "Pic"),
    ],
)
def test_plain_text_is_stripped_of_markup_and_control_characters(raw, cleaned):
    assert plain(raw) == cleaned


def test_blank_links_clear_the_field():
    assert clean_url("") == "" and clean_url("   ") == ""


def test_good_links_pass():
    assert clean_url("https://example.com/path?q=1") == "https://example.com/path?q=1"
    assert clean_url("https://www.linkedin.com/in/ada", hosts=("linkedin.com",))
    assert clean_url("https://x.com/ada", hosts=("x.com", "twitter.com"))


@pytest.mark.parametrize(
    "link",
    [
        "http://example.com",
        "javascript:alert(1)",
        "ftp://example.com",
        "//example.com",
        "https://localhost/x",
        "https://127.0.0.1/",
        "https://[::1]/",
        "https://user:pw@example.com/",
        "https://intranet/",
        "example.com",
        "https://" + "a" * 300 + ".com",
    ],
)
def test_unsafe_or_malformed_links_are_refused(link):
    with pytest.raises(ValidationError):
        clean_url(link)


def test_links_can_be_limited_to_a_domain():
    with pytest.raises(ValidationError):
        clean_url("https://evil.example.com/in/ada", hosts=("linkedin.com",))
    with pytest.raises(ValidationError):
        clean_url("https://notlinkedin.com/in/ada", hosts=("linkedin.com",))
