from typing import Any

from rest_framework import serializers

from apps.campaigns.segments import SegmentDefinitionSerializer
from apps.core.serializers import StrictSerializer

MAX_MARKUP = 20_000


class SegmentWriteSerializer(StrictSerializer):
    name = serializers.CharField(max_length=100)
    definition = SegmentDefinitionSerializer()


class SegmentUpdateSerializer(StrictSerializer):
    name = serializers.CharField(max_length=100, required=False)
    definition = SegmentDefinitionSerializer(required=False)


class SegmentPreviewSerializer(StrictSerializer):
    definition = SegmentDefinitionSerializer()


class SegmentSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    name = serializers.CharField()
    definition = serializers.DictField()
    created_at = serializers.DateTimeField()


class PreviewResultSerializer(serializers.Serializer):
    matching = serializers.IntegerField(help_text="Active members who fit the segment")
    eligible = serializers.IntegerField(
        help_text="Of those, the ones who agreed to marketing mail and are not suppressed"
    )


class BlockListField(serializers.ListField):
    """Blocks are validated in depth by the renderer; here we only bound the size."""

    child = serializers.DictField()


class TemplateWriteSerializer(StrictSerializer):
    name = serializers.CharField(max_length=100)
    blocks = serializers.ListField(child=serializers.DictField(), max_length=40)


class TemplateSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    name = serializers.CharField()
    blocks = serializers.ListField(child=serializers.DictField())
    created_at = serializers.DateTimeField()


class CampaignCreateSerializer(StrictSerializer):
    name = serializers.CharField(max_length=120)
    subject = serializers.CharField(max_length=150)
    preheader = serializers.CharField(max_length=150, required=False, allow_blank=True)
    blocks = serializers.ListField(child=serializers.DictField(), max_length=40, required=False)
    template_id = serializers.UUIDField(required=False)
    segment_id = serializers.UUIDField(required=False, allow_null=True)
    include_subscribers = serializers.BooleanField(
        required=False,
        help_text="Also send to confirmed newsletter subscribers who are not members.",
    )

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        if "blocks" in attrs and "template_id" in attrs:
            raise serializers.ValidationError("Send either blocks or template_id.")
        return attrs


class CampaignUpdateSerializer(StrictSerializer):
    name = serializers.CharField(max_length=120, required=False)
    subject = serializers.CharField(max_length=150, required=False)
    preheader = serializers.CharField(max_length=150, required=False, allow_blank=True)
    blocks = serializers.ListField(child=serializers.DictField(), max_length=40, required=False)
    segment_id = serializers.UUIDField(required=False, allow_null=True)
    include_subscribers = serializers.BooleanField(required=False)


class CampaignScheduleSerializer(StrictSerializer):
    scheduled_at = serializers.DateTimeField()


class CampaignQuerySerializer(StrictSerializer):
    status = serializers.ChoiceField(
        choices=["draft", "scheduled", "sending", "paused", "sent", "cancelled"],
        required=False,
        default="",
    )
    limit = serializers.IntegerField(required=False, min_value=1, max_value=100)
    offset = serializers.IntegerField(required=False, min_value=0)


class ReportSerializer(serializers.Serializer):
    recipients = serializers.IntegerField()
    queued = serializers.IntegerField()
    sent = serializers.IntegerField()
    skipped = serializers.IntegerField()
    failed = serializers.IntegerField()
    delivered = serializers.IntegerField()
    opened = serializers.IntegerField()
    clicked = serializers.IntegerField()
    bounced = serializers.IntegerField()
    unsubscribed = serializers.IntegerField()
    complained = serializers.IntegerField()
    open_rate = serializers.FloatField()
    click_rate = serializers.FloatField()


class CampaignSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    name = serializers.CharField()
    subject = serializers.CharField()
    preheader = serializers.CharField(allow_blank=True)
    blocks = serializers.ListField(child=serializers.DictField())
    segment_id = serializers.UUIDField(allow_null=True)
    include_subscribers = serializers.BooleanField()
    status = serializers.CharField()
    scheduled_at = serializers.DateTimeField(allow_null=True)
    started_at = serializers.DateTimeField(allow_null=True)
    finished_at = serializers.DateTimeField(allow_null=True)
    recipient_count = serializers.IntegerField()
    created_at = serializers.DateTimeField()


class UnsubscribeSerializer(StrictSerializer):
    token = serializers.CharField(max_length=500)


class UnsubscribeResultSerializer(serializers.Serializer):
    detail = serializers.CharField()


class NewsletterSignupSerializer(StrictSerializer):
    email = serializers.EmailField(max_length=254)
    # A field people never see. Anything typed into it means the form was filled in by a bot.
    website = serializers.CharField(required=False, allow_blank=True, max_length=200, default="")


class NewsletterTokenSerializer(StrictSerializer):
    token = serializers.CharField(max_length=500)


class NewsletterResultSerializer(serializers.Serializer):
    detail = serializers.CharField()


class SubscriberSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    email = serializers.EmailField()
    status = serializers.CharField()
    signed_up_from = serializers.CharField()
    created_at = serializers.DateTimeField()
    confirmed_at = serializers.DateTimeField(allow_null=True)
    unsubscribed_at = serializers.DateTimeField(allow_null=True)


class SubscriberCountsSerializer(serializers.Serializer):
    confirmed = serializers.IntegerField()
    pending = serializers.IntegerField()
    unsubscribed = serializers.IntegerField()


class SubscriberQuerySerializer(StrictSerializer):
    status = serializers.ChoiceField(
        choices=["pending", "confirmed", "unsubscribed"], required=False, default=""
    )
    q = serializers.CharField(required=False, allow_blank=True, max_length=254, default="")
    limit = serializers.IntegerField(required=False, min_value=1, max_value=200)
    offset = serializers.IntegerField(required=False, min_value=0)
