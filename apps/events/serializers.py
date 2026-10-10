from rest_framework import serializers

from apps.core.serializers import ImageSerializer, StrictSerializer
from apps.events.models import EVENT_TYPES

MAX_MARKUP = 40_000


class EventFieldsMixin(serializers.Serializer):
    type = serializers.ChoiceField(choices=EVENT_TYPES)
    title = serializers.CharField(max_length=160)
    description = serializers.CharField(max_length=MAX_MARKUP, trim_whitespace=False)
    starts_at = serializers.DateTimeField()
    ends_at = serializers.DateTimeField()
    timezone = serializers.CharField(max_length=64, required=False)
    location = serializers.CharField(max_length=200, required=False, allow_blank=True)
    link = serializers.CharField(max_length=300, required=False, allow_blank=True)
    capacity = serializers.IntegerField(
        min_value=1, max_value=100_000, required=False, allow_null=True
    )
    registration_open = serializers.BooleanField(required=False)
    public = serializers.BooleanField(required=False)
    recording_url = serializers.CharField(max_length=300, required=False, allow_blank=True)
    summary = serializers.CharField(
        max_length=MAX_MARKUP, required=False, allow_blank=True, trim_whitespace=False
    )


class EventCreateSerializer(EventFieldsMixin, StrictSerializer):
    pass


class EventUpdateSerializer(StrictSerializer):
    type = serializers.ChoiceField(choices=EVENT_TYPES, required=False)
    title = serializers.CharField(max_length=160, required=False)
    description = serializers.CharField(
        max_length=MAX_MARKUP, required=False, trim_whitespace=False
    )
    starts_at = serializers.DateTimeField(required=False)
    ends_at = serializers.DateTimeField(required=False)
    timezone = serializers.CharField(max_length=64, required=False)
    location = serializers.CharField(max_length=200, required=False, allow_blank=True)
    link = serializers.CharField(max_length=300, required=False, allow_blank=True)
    capacity = serializers.IntegerField(
        min_value=1, max_value=100_000, required=False, allow_null=True
    )
    registration_open = serializers.BooleanField(required=False)
    public = serializers.BooleanField(required=False)
    recording_url = serializers.CharField(max_length=300, required=False, allow_blank=True)
    summary = serializers.CharField(
        max_length=MAX_MARKUP, required=False, allow_blank=True, trim_whitespace=False
    )


class SlotInputSerializer(StrictSerializer):
    startup_id = serializers.UUIDField()
    pitch_link = serializers.CharField(max_length=300, required=False, allow_blank=True, default="")


class SlotsSerializer(StrictSerializer):
    slots = serializers.ListField(child=SlotInputSerializer(), max_length=20)


class EventReasonSerializer(StrictSerializer):
    reason = serializers.CharField(required=False, allow_blank=True, max_length=500, default="")


class CheckInSerializer(StrictSerializer):
    present = serializers.BooleanField(default=True)


class ListQuerySerializer(StrictSerializer):
    when = serializers.ChoiceField(choices=["upcoming", "past"], required=False, default="upcoming")
    type = serializers.ChoiceField(choices=EVENT_TYPES, required=False, default="")
    registered = serializers.BooleanField(required=False, default=False)
    cursor = serializers.CharField(required=False, allow_blank=True, max_length=400, default="")
    limit = serializers.IntegerField(required=False, min_value=1, max_value=50, default=20)


class PublicQuerySerializer(StrictSerializer):
    when = serializers.ChoiceField(choices=["upcoming", "past"], required=False, default="upcoming")
    type = serializers.ChoiceField(choices=EVENT_TYPES, required=False, default="")
    cursor = serializers.CharField(required=False, allow_blank=True, max_length=400, default="")
    limit = serializers.IntegerField(required=False, min_value=1, max_value=50, default=20)


class AdminQuerySerializer(StrictSerializer):
    status = serializers.ChoiceField(
        choices=["draft", "published", "cancelled"], required=False, default=""
    )
    type = serializers.ChoiceField(choices=EVENT_TYPES, required=False, default="")
    q = serializers.CharField(required=False, allow_blank=True, max_length=100, default="")
    limit = serializers.IntegerField(required=False, min_value=1, max_value=100)
    offset = serializers.IntegerField(required=False, min_value=0)


class AttendeeQuerySerializer(StrictSerializer):
    limit = serializers.IntegerField(required=False, min_value=1, max_value=100)
    offset = serializers.IntegerField(required=False, min_value=0)


# --- output ---


class EventStartupSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    slug = serializers.CharField()
    name = serializers.CharField()
    logo = ImageSerializer(allow_null=True)


class SlotSerializer(serializers.Serializer):
    position = serializers.IntegerField()
    pitch_link = serializers.CharField(allow_blank=True)
    startup = EventStartupSerializer()


class EventSummarySerializer(serializers.Serializer):
    id = serializers.UUIDField()
    slug = serializers.CharField()
    type = serializers.CharField()
    title = serializers.CharField()
    excerpt = serializers.CharField()
    starts_at = serializers.DateTimeField()
    ends_at = serializers.DateTimeField()
    timezone = serializers.CharField()
    location = serializers.CharField(allow_blank=True)
    status = serializers.CharField()
    past = serializers.BooleanField()
    capacity = serializers.IntegerField(allow_null=True)
    registered_count = serializers.IntegerField()
    spots_left = serializers.IntegerField(allow_null=True)
    registration_open = serializers.BooleanField(help_text="Whether you could register right now")
    registered = serializers.BooleanField()


class EventSerializer(EventSummarySerializer):
    description = serializers.CharField(help_text="Sanitised HTML")
    link = serializers.CharField(allow_blank=True, help_text="Where to join online")
    recording_url = serializers.CharField(allow_blank=True, help_text="Once the event is over")
    summary = serializers.CharField(allow_blank=True, help_text="Once the event is over")
    slots = SlotSerializer(many=True)


class EventPageSerializer(serializers.Serializer):
    results = EventSummarySerializer(many=True)
    next_cursor = serializers.CharField(allow_null=True)


class AdminEventSerializer(EventSerializer):
    public = serializers.BooleanField()
    created_by = serializers.UUIDField(allow_null=True)
    created_at = serializers.DateTimeField()
    edited_at = serializers.DateTimeField(allow_null=True)


class RegistrationResultSerializer(serializers.Serializer):
    event_id = serializers.UUIDField()
    registered = serializers.BooleanField()
    registered_count = serializers.IntegerField()
    spots_left = serializers.IntegerField(allow_null=True)


class AttendeeSerializer(serializers.Serializer):
    user_id = serializers.UUIDField()
    name = serializers.CharField()
    email = serializers.EmailField()
    registered_at = serializers.DateTimeField()
    checked_in_at = serializers.DateTimeField(allow_null=True)


class PublicEventSummarySerializer(serializers.Serializer):
    slug = serializers.CharField()
    type = serializers.CharField()
    title = serializers.CharField()
    excerpt = serializers.CharField()
    starts_at = serializers.DateTimeField()
    ends_at = serializers.DateTimeField()
    timezone = serializers.CharField()
    location = serializers.CharField(allow_blank=True)
    past = serializers.BooleanField()


class PublicEventPageSerializer(serializers.Serializer):
    results = PublicEventSummarySerializer(many=True)
    next_cursor = serializers.CharField(allow_null=True)


class EventOpenGraphSerializer(serializers.Serializer):
    title = serializers.CharField()
    description = serializers.CharField()
    url = serializers.CharField()
    type = serializers.CharField()
    image = serializers.CharField(allow_null=True)


class PublicEventSerializer(PublicEventSummarySerializer):
    description = serializers.CharField(help_text="Sanitised HTML")
    recording_url = serializers.CharField(allow_blank=True)
    summary = serializers.CharField(allow_blank=True)
    slots = SlotSerializer(many=True)
    share_url = serializers.CharField()
    open_graph = EventOpenGraphSerializer()
