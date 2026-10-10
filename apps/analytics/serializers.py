from rest_framework import serializers

from apps.core.serializers import StrictSerializer

MAX_BATCH = 50


class EventItemSerializer(StrictSerializer):
    name = serializers.CharField(max_length=60)
    properties = serializers.DictField(required=False, default=dict)
    occurred_at = serializers.DateTimeField(required=False)


class EventBatchSerializer(StrictSerializer):
    anonymous_id = serializers.UUIDField(required=False, allow_null=True, default=None)
    events = EventItemSerializer(many=True, min_length=1, max_length=MAX_BATCH)  # type: ignore[call-arg]


class RejectedEventSerializer(serializers.Serializer):
    index = serializers.IntegerField()
    reason = serializers.CharField()


class BatchResultSerializer(serializers.Serializer):
    accepted = serializers.IntegerField()
    rejected = RejectedEventSerializer(many=True)


class PreferenceSerializer(StrictSerializer):
    opt_out = serializers.BooleanField()
