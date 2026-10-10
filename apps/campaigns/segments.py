"""Audiences: a validated JSON definition compiled into queries.

An admin builds a segment from a fixed list of attributes. The definition is checked by a strict
serializer (unknown keys, wrong types and out-of-range values are refused), and each attribute is
answered by the module that owns it, returning ids. Nothing the admin types is ever put into SQL or
evaluated: values only select from fixed filters.
"""

from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any
from uuid import UUID

from django.utils import timezone
from rest_framework import serializers

from apps.accounts import services as accounts
from apps.core.serializers import StrictSerializer
from apps.feed import selectors as feed
from apps.jobs import selectors as jobs
from apps.learning import selectors as learning
from apps.notifications import services as notifications
from apps.profiles import selectors as profiles
from apps.reference import selectors as reference
from apps.startups import selectors as startups

TAGS = (
    "profile_complete",
    "registered_incomplete",
    "directory_listed",
    "founder_active",
    "founder_dormant",
    "job_poster",
    "learner_free",
    "learner_paid",
    "course_completed",
)
ROLES = ("member", "mentor")
PROFILE_COMPLETE_SCORE = 80
ACTIVE_DAYS = 30
DORMANT_DAYS = 60
CHUNK = 500


def _slug_list(field_name: str, check: Any) -> serializers.ListField:
    class Slugs(serializers.ListField):
        def to_internal_value(self, data: Any) -> list[str]:
            values = super().to_internal_value(data)
            unknown = [v for v in values if not check(v)]
            if unknown:
                raise serializers.ValidationError(f"Unknown {field_name}: {', '.join(unknown)}.")
            return list(dict.fromkeys(values))

    return Slugs(child=serializers.CharField(max_length=80), max_length=20, allow_empty=False)


class SegmentDefinitionSerializer(StrictSerializer):
    country = serializers.ListField(
        child=serializers.CharField(min_length=2, max_length=2),
        max_length=50,
        allow_empty=False,
        required=False,
    )
    sector = _slug_list("sector", lambda s: reference.get_sector(s) is not None)
    stage = _slug_list("stage", lambda s: reference.get_stage(s) is not None)
    skills = _slug_list("skill", lambda s: bool(reference.skills_by_slug([s])))
    roles = serializers.ListField(
        child=serializers.ChoiceField(choices=ROLES), max_length=2, allow_empty=False
    )
    joined_after = serializers.DateField()
    joined_before = serializers.DateField()
    last_active_after = serializers.DateField()
    last_active_before = serializers.DateField()
    completeness_min = serializers.IntegerField(min_value=0, max_value=100)
    completeness_max = serializers.IntegerField(min_value=0, max_value=100)
    tags = serializers.ListField(
        child=serializers.ChoiceField(choices=TAGS), max_length=len(TAGS), allow_empty=False
    )

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        for field_ in self.fields.values():
            field_.required = False

    def validate_country(self, value: list[str]) -> list[str]:
        codes = list(dict.fromkeys(v.upper() for v in value))
        unknown = [c for c in codes if not reference.is_country(c)]
        if unknown:
            raise serializers.ValidationError(f"Unknown country: {', '.join(unknown)}.")
        return codes

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        for low, high in (
            ("joined_after", "joined_before"),
            ("last_active_after", "last_active_before"),
            ("completeness_min", "completeness_max"),
        ):
            if low in attrs and high in attrs and attrs[low] > attrs[high]:
                raise serializers.ValidationError({high: f"Must not be before {low}."})
        return attrs


def clean(definition: dict[str, Any]) -> dict[str, Any]:
    """The definition in a form safe to store as JSON (dates as text)."""
    serializer = SegmentDefinitionSerializer(data=definition)
    serializer.is_valid(raise_exception=True)
    return {
        key: value.isoformat() if hasattr(value, "isoformat") else value
        for key, value in serializer.validated_data.items()
    }


@dataclass
class Filters:
    include: list[Any] = field(default_factory=list)
    exclude: list[Any] = field(default_factory=list)


def _date(definition: dict[str, Any], key: str) -> Any:
    raw = definition.get(key)
    return None if raw is None else serializers.DateField().to_internal_value(raw)


def compile_filters(definition: dict[str, Any]) -> Filters:
    """Turn a stored definition into id sets that must (include) or must not (exclude) match."""
    f = Filters()
    if "country" in definition:
        f.include.append(profiles.ids_by_country(definition["country"]))
    if "sector" in definition:
        f.include.append(startups.member_ids_by_sector(definition["sector"]))
    if "stage" in definition:
        f.include.append(startups.member_ids_by_stage(definition["stage"]))
    if "skills" in definition:
        f.include.append(profiles.ids_with_skills(definition["skills"]))
    if "roles" in definition:
        f.include.append(accounts.ids_with_roles(definition["roles"]))
    after, before = _date(definition, "joined_after"), _date(definition, "joined_before")
    if after or before:
        f.include.append(accounts.ids_joined(after, before))
    after, before = _date(definition, "last_active_after"), _date(definition, "last_active_before")
    if after or before:
        f.include.append(accounts.ids_last_active(after, before))
    if "completeness_min" in definition or "completeness_max" in definition:
        f.include.append(
            profiles.ids_by_completeness(
                definition.get("completeness_min", 0), definition.get("completeness_max", 100)
            )
        )
    now = timezone.now()
    for tag in definition.get("tags", []):
        if tag == "profile_complete":
            f.include.append(profiles.ids_by_completeness(PROFILE_COMPLETE_SCORE, 100))
        elif tag == "registered_incomplete":
            f.exclude.append(profiles.ids_by_completeness(PROFILE_COMPLETE_SCORE, 100))
        elif tag == "directory_listed":
            f.include.append(startups.member_ids_in_directory())
        elif tag == "founder_active":
            f.include.append(feed.active_author_ids(now - timedelta(days=ACTIVE_DAYS)))
        elif tag == "founder_dormant":
            f.exclude.append(feed.active_author_ids(now - timedelta(days=DORMANT_DAYS)))
        elif tag == "job_poster":
            f.include.append(jobs.poster_ids())
        elif tag == "learner_free":
            f.include.append(learning.learner_ids("free"))
        elif tag == "learner_paid":
            f.include.append(learning.learner_ids("paid"))
        elif tag == "course_completed":
            f.include.append(learning.completer_ids())
    return f


def _members(definition: dict[str, Any], *, consented_only: bool) -> Any:
    f = compile_filters(definition)
    queryset = accounts.marketing_audience() if consented_only else accounts.active_members()
    for ids in f.include:
        queryset = queryset.filter(pk__in=ids)
    for ids in f.exclude:
        queryset = queryset.exclude(pk__in=ids)
    return queryset


def _unsuppressed(rows: list[tuple[UUID, str]]) -> list[tuple[UUID, str]]:
    blocked: set[str] = set()
    for start in range(0, len(rows), CHUNK):
        blocked |= notifications.suppressed_among([e for _, e in rows[start : start + CHUNK]])
    return [(uid, email) for uid, email in rows if email.strip().lower() not in blocked]


def recipients(definition: dict[str, Any]) -> list[tuple[UUID, str]]:
    """Everyone who may be mailed for this segment: matching, consented, not suppressed."""
    rows = list(_members(definition, consented_only=True).values_list("pk", "email"))
    return _unsuppressed(rows)


def preview(definition: dict[str, Any]) -> dict[str, int]:
    """How many members match, and how many of them can actually be mailed."""
    return {
        "matching": _members(definition, consented_only=False).count(),
        "eligible": len(recipients(definition)),
    }
