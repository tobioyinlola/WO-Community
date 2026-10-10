from typing import Any

from rest_framework import serializers

from apps.core.serializers import ImageSerializer, StrictSerializer
from apps.jobs.models import APPLY_METHODS, JOB_TYPES

MAX_MARKUP = 20_000


class JobFieldsMixin(serializers.Serializer):
    """Fields shared by creating and editing a job."""

    title = serializers.CharField(max_length=140)
    type = serializers.ChoiceField(choices=JOB_TYPES)
    organisation = serializers.CharField(max_length=120, required=False, allow_blank=True)
    startup_id = serializers.UUIDField(required=False, allow_null=True)
    location = serializers.CharField(max_length=120, required=False, allow_blank=True)
    remote = serializers.BooleanField(required=False)
    description = serializers.CharField(max_length=MAX_MARKUP, trim_whitespace=False)
    requirements = serializers.CharField(
        max_length=MAX_MARKUP, required=False, allow_blank=True, trim_whitespace=False
    )
    compensation = serializers.CharField(max_length=120, required=False, allow_blank=True)
    apply_method = serializers.ChoiceField(choices=APPLY_METHODS)
    apply_target = serializers.CharField(max_length=300)
    deadline = serializers.DateField(required=False, allow_null=True)


class JobCreateSerializer(JobFieldsMixin, StrictSerializer):
    pass


class JobUpdateSerializer(StrictSerializer):
    title = serializers.CharField(max_length=140, required=False)
    type = serializers.ChoiceField(choices=JOB_TYPES, required=False)
    organisation = serializers.CharField(max_length=120, required=False, allow_blank=True)
    startup_id = serializers.UUIDField(required=False, allow_null=True)
    location = serializers.CharField(max_length=120, required=False, allow_blank=True)
    remote = serializers.BooleanField(required=False)
    description = serializers.CharField(
        max_length=MAX_MARKUP, required=False, trim_whitespace=False
    )
    requirements = serializers.CharField(
        max_length=MAX_MARKUP, required=False, allow_blank=True, trim_whitespace=False
    )
    compensation = serializers.CharField(max_length=120, required=False, allow_blank=True)
    apply_method = serializers.ChoiceField(choices=APPLY_METHODS, required=False)
    apply_target = serializers.CharField(max_length=300, required=False)
    deadline = serializers.DateField(required=False, allow_null=True)


class RenewSerializer(StrictSerializer):
    deadline = serializers.DateField(required=False, allow_null=True, default=None)


class BoardQuerySerializer(StrictSerializer):
    q = serializers.CharField(required=False, allow_blank=True, max_length=100, default="")
    type = serializers.ChoiceField(choices=JOB_TYPES, required=False, default="")
    remote = serializers.BooleanField(required=False, allow_null=True, default=None)
    startup_id = serializers.UUIDField(required=False, allow_null=True, default=None)
    location = serializers.CharField(required=False, allow_blank=True, max_length=120, default="")
    posted_within_days = serializers.IntegerField(
        required=False, min_value=1, max_value=90, allow_null=True, default=None
    )
    cursor = serializers.CharField(required=False, allow_blank=True, max_length=400, default="")
    limit = serializers.IntegerField(required=False, min_value=1, max_value=50, default=20)


class PublicQuerySerializer(StrictSerializer):
    q = serializers.CharField(required=False, allow_blank=True, max_length=100, default="")
    type = serializers.ChoiceField(choices=JOB_TYPES, required=False, default="")
    remote = serializers.BooleanField(required=False, allow_null=True, default=None)
    location = serializers.CharField(required=False, allow_blank=True, max_length=120, default="")
    cursor = serializers.CharField(required=False, allow_blank=True, max_length=400, default="")
    limit = serializers.IntegerField(required=False, min_value=1, max_value=50, default=20)


class PageQuerySerializer(StrictSerializer):
    cursor = serializers.CharField(required=False, allow_blank=True, max_length=400, default="")
    limit = serializers.IntegerField(required=False, min_value=1, max_value=50, default=20)


class AlertFiltersSerializer(StrictSerializer):
    q = serializers.CharField(required=False, allow_blank=True, max_length=100)
    type = serializers.ChoiceField(choices=JOB_TYPES, required=False)
    remote = serializers.BooleanField(required=False)
    startup_id = serializers.UUIDField(required=False)
    location = serializers.CharField(required=False, allow_blank=True, max_length=120)


class AlertCreateSerializer(StrictSerializer):
    filters = AlertFiltersSerializer()
    frequency = serializers.ChoiceField(choices=["instant", "daily"])


class AlertSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    filters = serializers.DictField()
    frequency = serializers.CharField()
    last_sent_at = serializers.DateTimeField(allow_null=True)
    created_at = serializers.DateTimeField()


class PosterSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    name = serializers.CharField()
    headline = serializers.CharField(allow_blank=True)
    photo = ImageSerializer(allow_null=True)
    slug = serializers.CharField(allow_null=True)


class StartupRefSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    slug = serializers.CharField()
    name = serializers.CharField()
    logo = ImageSerializer(allow_null=True)


class ApplySerializer(serializers.Serializer):
    method = serializers.CharField()
    target = serializers.CharField(required=False)


class JobSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    slug = serializers.CharField()
    title = serializers.CharField()
    type = serializers.CharField()
    organisation = serializers.CharField(allow_blank=True)
    startup = StartupRefSerializer(allow_null=True)
    poster = PosterSerializer(allow_null=True)
    location = serializers.CharField(allow_blank=True)
    remote = serializers.BooleanField()
    description = serializers.CharField(help_text="Sanitised HTML")
    requirements = serializers.CharField(allow_blank=True, help_text="Sanitised HTML")
    compensation = serializers.CharField(allow_blank=True)
    apply = ApplySerializer()
    deadline = serializers.DateField(allow_null=True)
    status = serializers.CharField()
    origin = serializers.CharField(help_text="member or admin")
    published_at = serializers.DateTimeField(allow_null=True)
    expires_at = serializers.DateTimeField(allow_null=True)
    created_at = serializers.DateTimeField()
    edited_at = serializers.DateTimeField(allow_null=True)
    share_url = serializers.CharField()
    mine = serializers.BooleanField()
    saved = serializers.BooleanField()
    review_note = serializers.CharField(allow_blank=True)


class JobPageSerializer(serializers.Serializer):
    results = JobSerializer(many=True)
    next_cursor = serializers.CharField(allow_null=True)


class PublicJobSummarySerializer(serializers.Serializer):
    slug = serializers.CharField()
    title = serializers.CharField()
    type = serializers.CharField()
    organisation = serializers.CharField(allow_blank=True)
    startup = StartupRefSerializer(allow_null=True)
    location = serializers.CharField(allow_blank=True)
    remote = serializers.BooleanField()
    published_at = serializers.DateTimeField()
    expires_at = serializers.DateTimeField()


class PublicJobPageSerializer(serializers.Serializer):
    results = PublicJobSummarySerializer(many=True)
    next_cursor = serializers.CharField(allow_null=True)


class OpenGraphSerializer(serializers.Serializer):
    title = serializers.CharField()
    description = serializers.CharField()
    url = serializers.CharField()
    type = serializers.CharField()
    image = serializers.CharField(allow_null=True)


class PublicJobSerializer(PublicJobSummarySerializer):
    description = serializers.CharField(help_text="Sanitised HTML")
    requirements = serializers.CharField(allow_blank=True, help_text="Sanitised HTML")
    compensation = serializers.CharField(allow_blank=True)
    apply = ApplySerializer(help_text="The target is shown only for links, never for email")
    deadline = serializers.DateField(allow_null=True)
    share_url = serializers.CharField()
    open_graph = OpenGraphSerializer()


class JobSitemapEntrySerializer(serializers.Serializer):
    slug = serializers.CharField()
    updated_at = serializers.DateTimeField()


class JobSitemapListSerializer(serializers.Serializer):
    results = JobSitemapEntrySerializer(many=True)


class SaveResultSerializer(serializers.Serializer):
    job_id = serializers.UUIDField()
    saved = serializers.BooleanField()


def public_data(data: dict[str, Any]) -> dict[str, Any]:
    return data


class AdminJobSerializer(JobSerializer):
    poster_id = serializers.UUIDField()
    reviewed_by = serializers.UUIDField(allow_null=True)
    reviewed_at = serializers.DateTimeField(allow_null=True)


class AdminJobQuerySerializer(StrictSerializer):
    status = serializers.ChoiceField(
        choices=["pending", "published", "closed", "expired", "rejected", "removed"],
        required=False,
        default="",
    )
    origin = serializers.ChoiceField(choices=["member", "admin"], required=False, default="")
    q = serializers.CharField(required=False, allow_blank=True, max_length=100, default="")
    limit = serializers.IntegerField(required=False, min_value=1, max_value=100)
    offset = serializers.IntegerField(required=False, min_value=0)


class AdminJobCreateSerializer(JobCreateSerializer):
    """Same fields; the service insists on an external link for admin jobs."""


class ReviewSerializer(StrictSerializer):
    reason = serializers.CharField(required=False, allow_blank=True, max_length=500, default="")


class JobSettingsSerializer(StrictSerializer):
    require_approval = serializers.BooleanField()
    default_duration_days = serializers.IntegerField(min_value=1, max_value=365)
