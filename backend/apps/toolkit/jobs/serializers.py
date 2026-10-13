from rest_framework import serializers

from apps.toolkit.jobs.models import JOB_STATUSES


class TkJobSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    kind = serializers.CharField()
    venture_id = serializers.UUIDField(allow_null=True)
    status = serializers.ChoiceField(choices=JOB_STATUSES)
    progress = serializers.IntegerField(help_text="0 to 100")
    step_label = serializers.CharField(allow_blank=True, help_text="What it is doing now")
    result = serializers.DictField(help_text="What was made, once it succeeded")
    error_code = serializers.CharField(allow_blank=True)
    error_detail = serializers.CharField(allow_blank=True, help_text="Safe to show the member")
    group_id = serializers.UUIDField(allow_null=True)
    created_at = serializers.DateTimeField()
    started_at = serializers.DateTimeField(allow_null=True)
    finished_at = serializers.DateTimeField(allow_null=True)


class TkExportFileSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    kind = serializers.CharField()
    filename = serializers.CharField()
    content_type = serializers.CharField()
    size = serializers.IntegerField()
    expires_at = serializers.DateTimeField()
    url = serializers.CharField(help_text="A signed download link; it expires quickly")
    url_expires_in = serializers.IntegerField(help_text="Seconds the link works for")
