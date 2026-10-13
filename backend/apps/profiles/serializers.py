from typing import Any

from rest_framework import serializers

from apps.core.serializers import ImageSerializer, StrictSerializer
from apps.core.text import clean_url, plain
from apps.core.visibility import LEVELS
from apps.profiles import domain
from apps.reference import selectors as reference


def _plain_field(value: str) -> str:
    return plain(value)


class ProfileUpdateSerializer(StrictSerializer):
    """Partial update. Fields not listed here (slug, visibility, score) cannot be set."""

    full_name = serializers.CharField(min_length=2, max_length=120, required=False)
    headline = serializers.CharField(max_length=160, required=False, allow_blank=True)
    bio = serializers.CharField(max_length=500, required=False, allow_blank=True)
    country = serializers.CharField(min_length=2, max_length=2, required=False)
    city = serializers.CharField(max_length=100, required=False, allow_blank=True)
    skills = serializers.ListField(
        child=serializers.SlugField(max_length=80),
        required=False,
        max_length=domain.MAX_SKILLS,
    )
    custom_skills = serializers.ListField(
        child=serializers.CharField(max_length=domain.MAX_CUSTOM_SKILL_LENGTH),
        required=False,
        max_length=domain.MAX_CUSTOM_SKILLS,
    )
    open_to = serializers.ListField(
        child=serializers.ChoiceField(choices=domain.OPEN_TO_CHOICES), required=False
    )
    linkedin_url = serializers.CharField(max_length=300, required=False, allow_blank=True)
    x_url = serializers.CharField(max_length=300, required=False, allow_blank=True)
    website_url = serializers.CharField(max_length=300, required=False, allow_blank=True)

    def validate_full_name(self, value: str) -> str:
        cleaned = _plain_field(value)
        if len(cleaned) < 2:
            raise serializers.ValidationError("Enter your name.")
        return cleaned

    def validate_headline(self, value: str) -> str:
        return _plain_field(value)

    def validate_bio(self, value: str) -> str:
        return _plain_field(value)

    def validate_city(self, value: str) -> str:
        return _plain_field(value)

    def validate_country(self, value: str) -> str:
        code = value.upper()
        if not reference.is_country(code):
            raise serializers.ValidationError("Choose a country from the list.")
        return code

    def validate_skills(self, value: list[str]) -> list[str]:
        return list(dict.fromkeys(value))

    def validate_custom_skills(self, value: list[str]) -> list[str]:
        cleaned = [_plain_field(item) for item in value]
        unique = list(dict.fromkeys(item for item in cleaned if item))
        return unique

    def validate_open_to(self, value: list[str]) -> list[str]:
        return list(dict.fromkeys(value))

    def validate_linkedin_url(self, value: str) -> str:
        return clean_url(value, hosts=("linkedin.com",))

    def validate_x_url(self, value: str) -> str:
        return clean_url(value, hosts=("x.com", "twitter.com"))

    def validate_website_url(self, value: str) -> str:
        return clean_url(value)


class VisibilityUpdateSerializer(StrictSerializer):
    """Body: group name to level, for example ``{"bio": "public"}``."""

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


class PhotoSetSerializer(StrictSerializer):
    upload_id = serializers.UUIDField()


class SkillSerializer(serializers.Serializer):
    slug = serializers.CharField()
    name = serializers.CharField()


class ProfileCompletenessSerializer(serializers.Serializer):
    score = serializers.IntegerField()
    next_missing_field = serializers.CharField(allow_null=True)


class ProfileSerializer(serializers.Serializer):
    """Output shape. Every field is optional because hidden groups are left out entirely."""

    user_id = serializers.UUIDField()
    slug = serializers.CharField()
    badges = serializers.ListField(child=serializers.CharField())
    full_name = serializers.CharField(required=False)
    headline = serializers.CharField(required=False)
    photo = ImageSerializer(required=False, allow_null=True)
    bio = serializers.CharField(required=False)
    country = serializers.CharField(required=False)
    city = serializers.CharField(required=False)
    skills = SkillSerializer(many=True, required=False)
    custom_skills = serializers.ListField(child=serializers.CharField(), required=False)
    open_to = serializers.ListField(child=serializers.CharField(), required=False)
    linkedin_url = serializers.CharField(required=False)
    x_url = serializers.CharField(required=False)
    website_url = serializers.CharField(required=False)
    visibility = serializers.DictField(child=serializers.CharField(), required=False)
    completeness = ProfileCompletenessSerializer(required=False)
