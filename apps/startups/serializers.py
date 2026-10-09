import datetime
from typing import Any

from django.utils import timezone
from rest_framework import serializers

from apps.core.serializers import ImageSerializer, StrictSerializer
from apps.core.text import clean_url, plain
from apps.core.visibility import LEVELS
from apps.reference import selectors as reference
from apps.startups import domain


def _required_text(value: str) -> str:
    cleaned = plain(value)
    if not cleaned:
        raise serializers.ValidationError("This field may not be blank.")
    return cleaned


class _StartupFields(StrictSerializer):
    """Validation shared by create and update."""

    def validate_name(self, value: str) -> str:
        return _required_text(value)

    def validate_pitch(self, value: str) -> str:
        return _required_text(value)

    def validate_city(self, value: str) -> str:
        return _required_text(value)

    def validate_description(self, value: str) -> str:
        return plain(value)

    def validate_country(self, value: str) -> str:
        code = value.upper()
        if not reference.is_country(code):
            raise serializers.ValidationError("Choose a country from the list.")
        return code

    def validate_year_founded(self, value: int | None) -> int | None:
        if value is not None and value > timezone.now().year:
            raise serializers.ValidationError("The year cannot be in the future.")
        return value

    def validate_website_url(self, value: str) -> str:
        return clean_url(value)


class StartupCreateSerializer(_StartupFields):
    name = serializers.CharField(max_length=120)
    pitch = serializers.CharField(max_length=160)
    country = serializers.CharField(min_length=2, max_length=2)
    city = serializers.CharField(max_length=100)
    sector = serializers.CharField(max_length=80)
    stage = serializers.CharField(max_length=80)
    year_founded = serializers.IntegerField(min_value=domain.MIN_YEAR, required=False)
    description = serializers.CharField(
        max_length=domain.MAX_DESCRIPTION, required=False, allow_blank=True
    )
    website_url = serializers.CharField(max_length=300, required=False, allow_blank=True)


class StartupUpdateSerializer(_StartupFields):
    name = serializers.CharField(max_length=120, required=False)
    pitch = serializers.CharField(max_length=160, required=False)
    country = serializers.CharField(min_length=2, max_length=2, required=False)
    city = serializers.CharField(max_length=100, required=False)
    sector = serializers.CharField(max_length=80, required=False)
    stage = serializers.CharField(max_length=80, required=False)
    year_founded = serializers.IntegerField(
        min_value=domain.MIN_YEAR, required=False, allow_null=True
    )
    description = serializers.CharField(
        max_length=domain.MAX_DESCRIPTION, required=False, allow_blank=True
    )
    website_url = serializers.CharField(max_length=300, required=False, allow_blank=True)
    directory_opt_in = serializers.BooleanField(required=False)


class VisibilityUpdateSerializer(StrictSerializer):
    """Body: group name to level, for example ``{"description": "public"}``."""

    def to_internal_value(self, data: Any) -> dict[str, str]:
        if not isinstance(data, dict) or not data:
            raise serializers.ValidationError({"non_field_errors": ["Send at least one group."]})
        errors: dict[str, str] = {}
        for group, level in data.items():
            if group not in domain.GROUP_FIELDS:
                errors[str(group)] = "Unknown field group."
            elif level not in LEVELS:
                errors[str(group)] = f"Choose one of: {', '.join(LEVELS)}."
        if errors:
            raise serializers.ValidationError(errors)
        return {str(g): str(lvl) for g, lvl in data.items()}


class TeamAddSerializer(StrictSerializer):
    email = serializers.EmailField(max_length=254)
    title = serializers.CharField(max_length=80, required=False, allow_blank=True, default="")
    is_founder = serializers.BooleanField(required=False, default=False)

    def validate_title(self, value: str) -> str:
        return plain(value)


class TractionItemSerializer(StrictSerializer):
    kind = serializers.ChoiceField(choices=domain.TRACTION_KINDS)
    value = serializers.JSONField()
    as_of_date = serializers.DateField(required=False)
    visibility = serializers.ChoiceField(choices=LEVELS, required=False, default="private")

    def validate_as_of_date(self, value: datetime.date) -> datetime.date:
        if value > timezone.now().date():
            raise serializers.ValidationError("The date cannot be in the future.")
        return value

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        kind, value = attrs["kind"], attrs["value"]
        if kind == "users":
            if isinstance(value, bool) or not isinstance(value, int):
                raise serializers.ValidationError({"value": "Enter a whole number."})
            if not 0 <= value <= domain.MAX_USERS:
                raise serializers.ValidationError({"value": "Enter a realistic number."})
        elif kind in domain.BANDS:
            if value not in domain.BANDS[kind]:
                allowed = ", ".join(domain.BANDS[kind])
                raise serializers.ValidationError({"value": f"Choose one of: {allowed}."})
        else:
            if not isinstance(value, str):
                raise serializers.ValidationError({"value": "Enter text."})
            text = plain(value)
            if not text or len(text) > 300:
                raise serializers.ValidationError({"value": "Enter 1 to 300 characters."})
            attrs["value"] = text
        return attrs


class TractionReplaceSerializer(StrictSerializer):
    metrics = TractionItemSerializer(  # type: ignore[call-arg]
        many=True, max_length=domain.MAX_TRACTION_ITEMS
    )

    def validate_metrics(self, value: list[dict[str, Any]]) -> list[dict[str, Any]]:
        seen = [item["kind"] for item in value if item["kind"] in domain.SINGLE_VALUE_KINDS]
        repeated = sorted({kind for kind in seen if seen.count(kind) > 1})
        if repeated:
            raise serializers.ValidationError(f"Only one entry allowed for: {', '.join(repeated)}.")
        return value


# --- output ---


class LogoSetSerializer(StrictSerializer):
    upload_id = serializers.UUIDField()


class NamedSlugSerializer(serializers.Serializer):
    slug = serializers.CharField()
    name = serializers.CharField()


class TeamMemberSerializer(serializers.Serializer):
    id = serializers.UUIDField(required=False)
    user_id = serializers.UUIDField(required=False)
    email = serializers.EmailField(required=False)
    title = serializers.CharField()
    is_founder = serializers.BooleanField()


class TractionOutSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    kind = serializers.CharField()
    value = serializers.JSONField()
    as_of_date = serializers.DateField()
    visibility = serializers.CharField()


class StartupCompletenessSerializer(serializers.Serializer):
    score = serializers.IntegerField()
    next_missing_field = serializers.CharField(allow_null=True)


class StartupSerializer(serializers.Serializer):
    """Output shape. Fields of hidden groups are absent, not blank."""

    id = serializers.UUIDField()
    slug = serializers.CharField()
    featured = serializers.BooleanField()
    traction = TractionOutSerializer(many=True)
    name = serializers.CharField(required=False)
    pitch = serializers.CharField(required=False)
    logo = ImageSerializer(required=False, allow_null=True)
    sector = NamedSlugSerializer(required=False)
    stage = NamedSlugSerializer(required=False)
    country = serializers.CharField(required=False)
    city = serializers.CharField(required=False)
    year_founded = serializers.IntegerField(required=False, allow_null=True)
    description = serializers.CharField(required=False)
    website_url = serializers.CharField(required=False)
    team = TeamMemberSerializer(many=True, required=False)
    owner_id = serializers.UUIDField(required=False)
    directory_opt_in = serializers.BooleanField(required=False)
    visibility = serializers.DictField(child=serializers.CharField(), required=False)
    completeness = StartupCompletenessSerializer(required=False)
