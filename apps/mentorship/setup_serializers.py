from rest_framework import serializers

from apps.core.serializers import StrictSerializer
from apps.mentorship.models import EXCEPTION_KINDS, PRICING_MODES
from apps.mentorship.serializers import LANGUAGE_CODES, WeeklyWindowSerializer

CLOCK_PATTERN = r"^\d{2}:\d{2}$"  # HH:MM in the mentor time zone


class WeeklyWindowWriteSerializer(StrictSerializer):
    weekday = serializers.IntegerField(min_value=0, max_value=6)
    start = serializers.RegexField(CLOCK_PATTERN)
    end = serializers.RegexField(CLOCK_PATTERN)


class ExceptionSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    type = serializers.ChoiceField(choices=EXCEPTION_KINDS)
    starts_on = serializers.DateField(allow_null=True)
    ends_on = serializers.DateField(allow_null=True)
    starts_at = serializers.DateTimeField(allow_null=True)
    ends_at = serializers.DateTimeField(allow_null=True)
    note = serializers.CharField(allow_blank=True)


class PriceRowSerializer(serializers.Serializer):
    length_minutes = serializers.IntegerField()
    price_minor = serializers.IntegerField()


class PriceRowWriteSerializer(StrictSerializer):
    length_minutes = serializers.IntegerField()
    price_minor = serializers.IntegerField()


class SetupOptionsSerializer(serializers.Serializer):
    lengths = serializers.ListField(child=serializers.IntegerField())
    buffers = serializers.ListField(child=serializers.IntegerField())
    notice_hours = serializers.ListField(child=serializers.IntegerField())
    window_days = serializers.ListField(child=serializers.IntegerField())
    currencies = serializers.ListField(child=serializers.CharField())


class MentorSetupSerializer(serializers.Serializer):
    timezone = serializers.CharField()
    accepting_new = serializers.BooleanField()
    weekly = WeeklyWindowSerializer(many=True)
    exceptions = ExceptionSerializer(many=True)
    session_lengths = serializers.ListField(child=serializers.IntegerField())
    default_length = serializers.IntegerField()
    buffer_minutes = serializers.IntegerField()
    min_notice_hours = serializers.IntegerField()
    max_per_week = serializers.IntegerField()
    booking_window_days = serializers.IntegerField()
    pricing_mode = serializers.ChoiceField(choices=PRICING_MODES)
    default_price_minor = serializers.IntegerField(allow_null=True)
    currency = serializers.CharField(allow_blank=True)
    prices = PriceRowSerializer(many=True)
    payments_enabled = serializers.BooleanField(
        help_text="False while online payment is off: paid sessions are requests the mentor "
        "confirms and payment is arranged directly."
    )
    meeting_provider = serializers.CharField(allow_blank=True)
    personal_link = serializers.CharField(allow_blank=True)
    meeting_providers = serializers.ListField(child=serializers.CharField())
    about = serializers.CharField(allow_blank=True)
    expertise = serializers.ListField(child=serializers.CharField())
    topics = serializers.ListField(child=serializers.CharField())
    languages = serializers.ListField(child=serializers.CharField())
    stages = serializers.ListField(child=serializers.CharField())
    industries = serializers.ListField(child=serializers.CharField())
    options = SetupOptionsSerializer()


class MentorSetupUpdateSerializer(StrictSerializer):
    session_lengths = serializers.ListField(
        child=serializers.IntegerField(), max_length=3, required=False
    )
    default_length = serializers.IntegerField(required=False)
    buffer_minutes = serializers.IntegerField(required=False)
    min_notice_hours = serializers.IntegerField(required=False)
    max_per_week = serializers.IntegerField(min_value=1, max_value=20, required=False)
    booking_window_days = serializers.IntegerField(required=False)
    accepting_new = serializers.BooleanField(required=False)
    pricing_mode = serializers.ChoiceField(choices=PRICING_MODES, required=False)
    default_price_minor = serializers.IntegerField(required=False, allow_null=True)
    currency = serializers.CharField(max_length=3, required=False, allow_blank=True)
    prices = PriceRowWriteSerializer(  # type: ignore[call-arg]
        many=True, required=False, max_length=3
    )
    meeting_provider = serializers.CharField(max_length=12, required=False, allow_blank=True)
    personal_link = serializers.CharField(max_length=500, required=False, allow_blank=True)
    about = serializers.CharField(max_length=1000, required=False, allow_blank=True)
    expertise = serializers.ListField(
        child=serializers.CharField(max_length=50), max_length=8, required=False
    )
    topics = serializers.ListField(
        child=serializers.CharField(max_length=50), max_length=10, required=False
    )
    languages = serializers.ListField(
        child=serializers.ChoiceField(choices=LANGUAGE_CODES), max_length=5, required=False
    )
    stages = serializers.ListField(
        child=serializers.SlugField(max_length=80), max_length=4, required=False
    )
    industries = serializers.ListField(
        child=serializers.SlugField(max_length=80), max_length=5, required=False
    )
    timezone = serializers.CharField(max_length=64, required=False)
    acknowledge = serializers.BooleanField(
        required=False,
        default=False,
        help_text="Keep sessions already agreed even though the change leaves them outside "
        "the schedule.",
    )


class WeeklyUpdateSerializer(StrictSerializer):
    weekly = WeeklyWindowWriteSerializer(many=True, max_length=35)  # type: ignore[call-arg]
    timezone = serializers.CharField(max_length=64, required=False)
    acknowledge = serializers.BooleanField(required=False, default=False)


class WeeklySerializer(serializers.Serializer):
    timezone = serializers.CharField()
    weekly = WeeklyWindowSerializer(many=True)
    exceptions = ExceptionSerializer(many=True)


class ExceptionCreateSerializer(StrictSerializer):
    type = serializers.ChoiceField(choices=EXCEPTION_KINDS)
    starts_on = serializers.DateField(required=False, help_text="blocked: the first day off")
    ends_on = serializers.DateField(required=False, help_text="blocked: the last day off")
    note = serializers.CharField(max_length=120, required=False, allow_blank=True, default="")
    date = serializers.DateField(required=False, help_text="extra: the day")
    start = serializers.RegexField(CLOCK_PATTERN, required=False)
    end = serializers.RegexField(CLOCK_PATTERN, required=False)
    acknowledge = serializers.BooleanField(required=False, default=False)


class AcknowledgeSerializer(StrictSerializer):
    acknowledge = serializers.BooleanField(required=False, default=False)


class ConflictSessionSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    starts_at = serializers.DateTimeField()
    ends_at = serializers.DateTimeField()
    status = serializers.CharField()
    topic = serializers.CharField()


class ScheduleConflictSerializer(serializers.Serializer):
    status = serializers.IntegerField()
    code = serializers.CharField()
    title = serializers.CharField()
    detail = serializers.CharField()
    sessions = ConflictSessionSerializer(many=True)


class SlotsQuerySerializer(serializers.Serializer):
    # `from` is a Python keyword, so the field is added to the class body by name.
    vars()["from"] = serializers.DateField(required=False)
    to = serializers.DateField(required=False)
    length = serializers.IntegerField(min_value=30, max_value=60, required=False)
    tz = serializers.CharField(max_length=64, required=False, allow_blank=True, default="")


class BookableSlotSerializer(serializers.Serializer):
    starts_at = serializers.DateTimeField()
    ends_at = serializers.DateTimeField()
    local_date = serializers.DateField()
    local_time = serializers.CharField()


class SlotPriceSerializer(serializers.Serializer):
    price_minor = serializers.IntegerField()
    currency = serializers.CharField()
    payment = serializers.CharField()


class SlotsSerializer(serializers.Serializer):
    mentor_timezone = serializers.CharField()
    timezone = serializers.CharField()
    length_minutes = serializers.IntegerField()
    lengths = serializers.ListField(child=serializers.IntegerField())
    accepting_new = serializers.BooleanField()
    price = SlotPriceSerializer(allow_null=True)
    slots = BookableSlotSerializer(many=True)
    sessions_left_this_week = serializers.IntegerField()
