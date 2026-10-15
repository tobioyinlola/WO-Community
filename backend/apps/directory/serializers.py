"""Query validation and the output allow-list.

Output serializers repeat the read model's shape on purpose: whatever a row
holds, only these fields can ever leave the API.
"""

from typing import Any

from rest_framework import serializers

from apps.core.serializers import ImageSerializer, StrictSerializer

MAX_SKILL_FILTERS = 5
PUBLIC_PREVIEW = 10


class _Query(StrictSerializer):
    q = serializers.CharField(max_length=100, required=False, allow_blank=True, default="")
    country = serializers.CharField(min_length=2, max_length=2, required=False, default="")
    skills = serializers.CharField(max_length=500, required=False, allow_blank=True, default="")
    sort = serializers.ChoiceField(choices=["newest", "alphabetical"], default="newest")
    # Visitors see a preview: at most this many, and no further pages. Members see everyone.
    limit = serializers.IntegerField(min_value=1, max_value=PUBLIC_PREVIEW, default=PUBLIC_PREVIEW)

    def validate_q(self, value: str) -> str:
        return " ".join(value.split())

    def validate_skills(self, value: str) -> list[str]:
        slugs = [part.strip() for part in value.split(",") if part.strip()]
        if len(slugs) > MAX_SKILL_FILTERS:
            raise serializers.ValidationError(f"Use at most {MAX_SKILL_FILTERS} skills.")
        field = serializers.SlugField(max_length=80)
        return [field.run_validation(slug) for slug in dict.fromkeys(slugs)]


class StartupQuerySerializer(_Query):
    sector = serializers.SlugField(max_length=80, required=False, default="")
    stage = serializers.SlugField(max_length=80, required=False, default="")
    featured = serializers.BooleanField(required=False, default=False)


class FounderQuerySerializer(_Query):
    pass


class SitemapQuerySerializer(StrictSerializer):
    pass


def clean_query(serializer_class: type[StrictSerializer], params: Any) -> dict[str, Any]:
    serializer = serializer_class(data=params)
    serializer.is_valid(raise_exception=True)
    return dict(serializer.validated_data)


# --- output ---


class NamedSerializer(serializers.Serializer):
    slug = serializers.CharField()
    name = serializers.CharField()


class FounderRefSerializer(serializers.Serializer):
    slug = serializers.CharField()
    full_name = serializers.CharField()
    headline = serializers.CharField(required=False)


class TractionPublicSerializer(serializers.Serializer):
    kind = serializers.CharField()
    value = serializers.JSONField()
    as_of_date = serializers.CharField()


class StartupCardSerializer(serializers.Serializer):
    slug = serializers.CharField()
    name = serializers.CharField()
    pitch = serializers.CharField()
    logo = ImageSerializer(allow_null=True)
    sector = NamedSerializer()
    stage = NamedSerializer()
    country = serializers.CharField()
    city = serializers.CharField()
    year_founded = serializers.IntegerField(allow_null=True)
    featured = serializers.BooleanField()
    founders = FounderRefSerializer(many=True)


class StartupDetailSerializer(StartupCardSerializer):
    description = serializers.CharField(required=False)
    website_url = serializers.CharField(required=False)
    traction = TractionPublicSerializer(many=True)
    url = serializers.CharField()
    structured_data = serializers.JSONField()


class DirectorySkillSerializer(serializers.Serializer):
    slug = serializers.CharField()
    name = serializers.CharField()


class FounderCardSerializer(serializers.Serializer):
    slug = serializers.CharField()
    full_name = serializers.CharField()
    badges = serializers.ListField(child=serializers.CharField())
    headline = serializers.CharField(required=False)
    photo = ImageSerializer(required=False, allow_null=True)
    country = serializers.CharField(required=False)
    city = serializers.CharField(required=False)
    skills = DirectorySkillSerializer(many=True, required=False)


class LinkedStartupSerializer(serializers.Serializer):
    slug = serializers.CharField()
    name = serializers.CharField()
    pitch = serializers.CharField()
    sector = NamedSerializer()


class FounderDetailSerializer(FounderCardSerializer):
    bio = serializers.CharField(required=False)
    custom_skills = serializers.ListField(child=serializers.CharField(), required=False)
    open_to = serializers.ListField(child=serializers.CharField(), required=False)
    linkedin_url = serializers.CharField(required=False)
    x_url = serializers.CharField(required=False)
    website_url = serializers.CharField(required=False)
    startups = LinkedStartupSerializer(many=True)
    url = serializers.CharField()
    structured_data = serializers.JSONField()


def startup_page(results: list[dict[str, Any]], has_more: bool) -> dict[str, Any]:
    return {"results": StartupCardSerializer(results, many=True).data, "has_more": has_more}


def founder_page(results: list[dict[str, Any]], has_more: bool) -> dict[str, Any]:
    return {"results": FounderCardSerializer(results, many=True).data, "has_more": has_more}


class StartupPageSerializer(serializers.Serializer):
    results = StartupCardSerializer(many=True)
    has_more = serializers.BooleanField(help_text="More are listed: members can see them all.")


class FounderPageSerializer(serializers.Serializer):
    results = FounderCardSerializer(many=True)
    has_more = serializers.BooleanField(help_text="More are listed: members can see them all.")


class SitemapEntrySerializer(serializers.Serializer):
    slug = serializers.CharField()
    path = serializers.CharField()
    lastmod = serializers.DateTimeField()


class SitemapSerializer(serializers.Serializer):
    startups = SitemapEntrySerializer(many=True)
    founders = SitemapEntrySerializer(many=True)
