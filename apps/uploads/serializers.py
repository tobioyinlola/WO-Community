from typing import Any

from django.conf import settings
from rest_framework import serializers

from apps.core.serializers import StrictSerializer
from apps.uploads import services
from apps.uploads.models import Upload, UploadPurpose


class UploadRequestSerializer(StrictSerializer):
    purpose = serializers.ChoiceField(choices=UploadPurpose.values)
    content_type = serializers.CharField(max_length=40)
    size = serializers.IntegerField(min_value=1)
    filename = serializers.CharField(max_length=255, required=False, allow_blank=True, default="")


class UploadFormSerializer(serializers.Serializer):
    url = serializers.CharField()
    method = serializers.CharField()
    form_data = serializers.DictField(child=serializers.CharField())
    expires_in = serializers.IntegerField()


class UploadSerializer(serializers.ModelSerializer):
    urls = serializers.SerializerMethodField()
    reason = serializers.CharField(source="reject_reason")

    class Meta:
        model = Upload
        fields = ["id", "purpose", "status", "reason", "width", "height", "urls", "expires_at"]
        read_only_fields = fields

    def get_urls(self, obj: Upload) -> dict[str, str] | None:
        if obj.status != "ready":
            return None  # nothing that is not clean and processed is ever linked
        return services.image_urls(obj.base_key)


class UploadCreatedSerializer(serializers.Serializer):
    upload = UploadSerializer()
    form = UploadFormSerializer()
    max_size = serializers.IntegerField()


def created_body(upload: Upload, post: Any) -> dict[str, Any]:
    return {
        "upload": upload,
        "form": {
            "url": post.url,
            "method": "POST",
            "form_data": post.fields,
            "expires_in": post.expires_in,
        },
        "max_size": settings.UPLOAD_MAX_BYTES,
    }
