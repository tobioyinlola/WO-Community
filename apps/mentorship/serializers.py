from rest_framework import serializers

from apps.core.serializers import ImageSerializer, StrictSerializer
from apps.mentorship.domain import LANGUAGES
from apps.mentorship.models import APPLICATION_STATUSES

LANGUAGE_CODES = sorted(LANGUAGES)


class ApplicationCreateSerializer(StrictSerializer):
    expertise = serializers.ListField(child=serializers.CharField(max_length=50), max_length=8)
    years_experience = serializers.IntegerField(min_value=1, max_value=60)
    current_role = serializers.CharField(max_length=120)
    company = serializers.CharField(max_length=120)
    linkedin_url = serializers.CharField(max_length=300)
    industries = serializers.ListField(child=serializers.SlugField(max_length=80), max_length=5)
    stages = serializers.ListField(child=serializers.SlugField(max_length=80), max_length=4)
    languages = serializers.ListField(
        child=serializers.ChoiceField(choices=LANGUAGE_CODES), max_length=5
    )
    timezone = serializers.CharField(max_length=64)
    weekly_hours = serializers.IntegerField(min_value=1, max_value=40)
    availability_note = serializers.CharField(max_length=500, required=False, allow_blank=True)
    motivation = serializers.CharField(max_length=1500)
    accept_conduct = serializers.BooleanField()


class ApplicationUpdateSerializer(StrictSerializer):
    expertise = serializers.ListField(
        child=serializers.CharField(max_length=50), max_length=8, required=False
    )
    years_experience = serializers.IntegerField(min_value=1, max_value=60, required=False)
    current_role = serializers.CharField(max_length=120, required=False)
    company = serializers.CharField(max_length=120, required=False)
    linkedin_url = serializers.CharField(max_length=300, required=False)
    industries = serializers.ListField(
        child=serializers.SlugField(max_length=80), max_length=5, required=False
    )
    stages = serializers.ListField(
        child=serializers.SlugField(max_length=80), max_length=4, required=False
    )
    languages = serializers.ListField(
        child=serializers.ChoiceField(choices=LANGUAGE_CODES), max_length=5, required=False
    )
    timezone = serializers.CharField(max_length=64, required=False)
    weekly_hours = serializers.IntegerField(min_value=1, max_value=40, required=False)
    availability_note = serializers.CharField(max_length=500, required=False, allow_blank=True)
    motivation = serializers.CharField(max_length=1500, required=False)


class MentorTagSerializer(serializers.Serializer):
    slug = serializers.CharField()
    name = serializers.CharField()


class MentorLanguageSerializer(serializers.Serializer):
    code = serializers.CharField()
    name = serializers.CharField()


class MentorApplicationSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    status = serializers.ChoiceField(choices=APPLICATION_STATUSES)
    expertise = serializers.ListField(child=serializers.CharField())
    years_experience = serializers.IntegerField()
    current_role = serializers.CharField()
    company = serializers.CharField()
    linkedin_url = serializers.CharField()
    industries = MentorTagSerializer(many=True)
    stages = MentorTagSerializer(many=True)
    languages = MentorLanguageSerializer(many=True)
    timezone = serializers.CharField()
    weekly_hours = serializers.IntegerField()
    availability_note = serializers.CharField()
    motivation = serializers.CharField()
    decision_reason = serializers.CharField(help_text="The decline reason, or what is asked for.")
    decided_at = serializers.DateTimeField(allow_null=True)
    created_at = serializers.DateTimeField()


class ApplicantSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    name = serializers.CharField()
    email = serializers.CharField()


class AdminMentorApplicationSerializer(MentorApplicationSerializer):
    applicant = ApplicantSerializer()
    decided_by = serializers.UUIDField(allow_null=True)


class MentorSerializer(serializers.Serializer):
    id = serializers.UUIDField(help_text="The member id of the mentor.")
    name = serializers.CharField()
    headline = serializers.CharField()
    photo = ImageSerializer(allow_null=True)
    slug = serializers.CharField(allow_null=True)
    about = serializers.CharField()
    expertise = serializers.ListField(child=serializers.CharField())
    years_experience = serializers.IntegerField()
    current_role = serializers.CharField()
    company = serializers.CharField()
    industries = MentorTagSerializer(many=True)
    stages = MentorTagSerializer(many=True)
    languages = MentorLanguageSerializer(many=True)
    timezone = serializers.CharField()
    capacity_per_week = serializers.IntegerField()
    session_minutes = serializers.IntegerField()
    paused = serializers.BooleanField()
    rating_average = serializers.FloatField(allow_null=True)
    rating_count = serializers.IntegerField()


class MentorPageSerializer(serializers.Serializer):
    results = MentorSerializer(many=True)
    next_cursor = serializers.CharField(allow_null=True)


class MentorQuerySerializer(serializers.Serializer):
    q = serializers.CharField(max_length=80, required=False, allow_blank=True)
    expertise = serializers.CharField(max_length=50, required=False, allow_blank=True)
    industry = serializers.SlugField(max_length=80, required=False, allow_blank=True)
    stage = serializers.SlugField(max_length=80, required=False, allow_blank=True)
    country = serializers.CharField(max_length=2, required=False, allow_blank=True)
    language = serializers.ChoiceField(choices=LANGUAGE_CODES, required=False)
    available = serializers.BooleanField(
        required=False, help_text="Only mentors who have published availability."
    )
    cursor = serializers.CharField(required=False, allow_blank=True, default="")
    limit = serializers.IntegerField(min_value=1, max_value=50, default=20)


class MentorProfileUpdateSerializer(StrictSerializer):
    about = serializers.CharField(max_length=1000, required=False, allow_blank=True)
    expertise = serializers.ListField(
        child=serializers.CharField(max_length=50), max_length=8, required=False
    )
    years_experience = serializers.IntegerField(min_value=1, max_value=60, required=False)
    current_role = serializers.CharField(max_length=120, required=False)
    company = serializers.CharField(max_length=120, required=False)
    industries = serializers.ListField(
        child=serializers.SlugField(max_length=80), max_length=5, required=False
    )
    stages = serializers.ListField(
        child=serializers.SlugField(max_length=80), max_length=4, required=False
    )
    languages = serializers.ListField(
        child=serializers.ChoiceField(choices=LANGUAGE_CODES), max_length=5, required=False
    )
    timezone = serializers.CharField(max_length=64, required=False)
    capacity_per_week = serializers.IntegerField(min_value=1, max_value=20, required=False)
    session_minutes = serializers.ChoiceField(choices=[30, 45, 60], required=False)
    paused = serializers.BooleanField(required=False)


class DecisionSerializer(StrictSerializer):
    decision = serializers.ChoiceField(choices=["approve", "decline", "request_info"])
    reason = serializers.CharField(max_length=1000, required=False, allow_blank=True)


class MentorReasonSerializer(StrictSerializer):
    reason = serializers.CharField(max_length=1000)


class AdminQuerySerializer(serializers.Serializer):
    status = serializers.CharField(max_length=14, required=False, allow_blank=True)
    q = serializers.CharField(max_length=80, required=False, allow_blank=True)
    limit = serializers.IntegerField(min_value=1, max_value=100, required=False)
    offset = serializers.IntegerField(min_value=0, required=False)


class AdminMentorSerializer(MentorSerializer):
    status = serializers.CharField()
    revoke_reason = serializers.CharField()
    approved_at = serializers.DateTimeField()


class MentoringSummarySerializer(serializers.Serializer):
    is_mentor = serializers.BooleanField()
    application_id = serializers.UUIDField(allow_null=True)
    application_status = serializers.ChoiceField(choices=APPLICATION_STATUSES, allow_null=True)
    interested = serializers.BooleanField(help_text="Ticked the mentor option at registration.")
    can_apply = serializers.BooleanField()
    can_apply_after = serializers.DateTimeField(allow_null=True)
    prompt_to_apply = serializers.BooleanField(
        help_text="Said they want to mentor at registration and have not applied yet."
    )


class WeeklyWindowSerializer(StrictSerializer):
    weekday = serializers.IntegerField(min_value=0, max_value=6, help_text="0 is Monday.")
    start = serializers.CharField(max_length=5, help_text="HH:MM in the mentor time zone.")
    end = serializers.CharField(max_length=5, help_text="HH:MM, up to 24:00.")


class OneOffWindowSerializer(StrictSerializer):
    starts_at = serializers.DateTimeField()
    ends_at = serializers.DateTimeField()


class MentorScheduleSerializer(serializers.Serializer):
    timezone = serializers.CharField()
    session_minutes = serializers.IntegerField()
    weekly = WeeklyWindowSerializer(many=True)
    one_off = OneOffWindowSerializer(many=True)


class MentorScheduleUpdateSerializer(StrictSerializer):
    timezone = serializers.CharField(max_length=64, required=False)
    weekly = WeeklyWindowSerializer(many=True, required=False)
    one_off = OneOffWindowSerializer(many=True, required=False)


class BookableTimesSerializer(serializers.Serializer):
    timezone = serializers.CharField()
    session_minutes = serializers.IntegerField()
    times = serializers.ListField(child=serializers.DateTimeField())
    sessions_left_this_week = serializers.IntegerField()


class BookableQuerySerializer(serializers.Serializer):
    days = serializers.IntegerField(min_value=1, max_value=30, default=14)


class ReasonItemSerializer(serializers.Serializer):
    key = serializers.CharField()
    score = serializers.IntegerField(help_text="0 to 100 for this signal.")
    text = serializers.CharField()


class RecommendedMentorSerializer(MentorSerializer):
    score = serializers.IntegerField(help_text="0 to 100.")
    reasons = ReasonItemSerializer(many=True)
    components = serializers.DictField(child=serializers.FloatField())


class RecommendationQuerySerializer(serializers.Serializer):
    needs = serializers.CharField(
        required=False, allow_blank=True, max_length=300, help_text="Comma list of up to 5 needs."
    )
    limit = serializers.IntegerField(min_value=1, max_value=20, default=10)


class NeedsSerializer(serializers.Serializer):
    needs = serializers.ListField(child=serializers.CharField(max_length=50))
    languages = serializers.ListField(child=serializers.CharField())


class NeedsUpdateSerializer(StrictSerializer):
    needs = serializers.ListField(child=serializers.CharField(max_length=50), max_length=5)
    languages = serializers.ListField(
        child=serializers.ChoiceField(choices=LANGUAGE_CODES), max_length=5, required=False
    )
