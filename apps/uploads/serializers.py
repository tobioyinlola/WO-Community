from typing import Any

from django.conf import settings
from rest_framework import serializers

from apps.core.serializers import StrictSerializer
from apps.uploads import services
from apps.uploads.models import DOCUMENT_PURPOSES, Upload, UploadPurpose


class UploadRequestSerializer(StrictSerializer):
    purpose = serializers.ChoiceField(choices=UploadPurpose.values)
    content_type = serializers.CharField(max_length=100)
    size = serializers.IntegerField(min_value=1)
    filename = serializers.CharField(max_length=255, required=False, allow_blank=True, default="")


class UploadFormSerializer(serializers.Serializer):
    url = serializers.CharField()
    method = serializers.CharField()
    form_data = serializers.DictField(child=serializers.CharField())
    headers = serializers.DictField(child=serializers.CharField())
    expires_in = serializers.IntegerField()


class UploadSerializer(serializers.ModelSerializer):
    urls = serializers.SerializerMethodField()
    reason = serializers.CharField(source="reject_reason")
    filename = serializers.CharField(source="original_filename")

    class Meta:
        model = Upload
        fields = [
            "id",
            "purpose",
            "status",
            "reason",
            "width",
            "height",
            "urls",
            "filename",
            "size",
            "expires_at",
        ]
        read_only_fields = fields

    def get_urls(self, obj: Upload) -> dict[str, str] | None:
        if obj.status != "ready" or obj.purpose in DOCUMENT_PURPOSES:
            return None  # nothing unclean is linked, and documents have no public address
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
            "method": post.method,
            "form_data": post.fields,
            "headers": post.headers,
            "expires_in": post.expires_in,
        },
        "max_size": settings.UPLOAD_MAX_BYTES,
    }
