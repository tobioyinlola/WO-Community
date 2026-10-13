from rest_framework import serializers

from apps.core.serializers import StrictSerializer
from apps.learning.serializers import CourseDetailSerializer, CourseSummarySerializer

# --- input ---


class AccessRequestSerializer(StrictSerializer):
    message = serializers.CharField(required=False, allow_blank=True, max_length=500, default="")


class BodySerializer(StrictSerializer):
    body = serializers.CharField(min_length=1, max_length=2000, trim_whitespace=True)


class NoteCreateSerializer(StrictSerializer):
    body = serializers.CharField(min_length=1, max_length=2000, trim_whitespace=True)
    seconds = serializers.IntegerField(min_value=0, max_value=86_400, required=False, default=0)


class ReviewsQuerySerializer(StrictSerializer):
    cursor = serializers.CharField(required=False, allow_blank=True, max_length=400, default="")
    limit = serializers.IntegerField(required=False, min_value=1, max_value=50, default=10)


# --- output ---


class PromoVideoSerializer(serializers.Serializer):
    video_id = serializers.CharField()
    embed_url = serializers.CharField()


class CoursePageDetailSerializer(CourseDetailSerializer):
    """The landing page: the outline and description plus everything that sells and explains."""

    learn_bullets = serializers.ListField(child=serializers.CharField())
    requirements = serializers.ListField(child=serializers.CharField())
    audience = serializers.CharField(allow_blank=True)
    promo_video = PromoVideoSerializer(allow_null=True)
    rating_distribution = serializers.DictField(child=serializers.IntegerField())
    can_review = serializers.BooleanField()
    related = CourseSummarySerializer(many=True)
    announcement_count = serializers.IntegerField()
    last_updated = serializers.DateTimeField()
    section_count = serializers.IntegerField()


class ReviewSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    stars = serializers.IntegerField()
    feedback = serializers.CharField(allow_blank=True)
    created_at = serializers.DateTimeField()
    reviewer = serializers.CharField()
    mine = serializers.BooleanField()


class ReviewPageSerializer(serializers.Serializer):
    results = ReviewSerializer(many=True)
    next_cursor = serializers.CharField(allow_null=True)
    average = serializers.FloatField(allow_null=True)
    count = serializers.IntegerField()
    distribution = serializers.DictField(child=serializers.IntegerField())


class WishlistStateSerializer(serializers.Serializer):
    saved = serializers.BooleanField()


class AccessRequestResultSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    status = serializers.CharField()
    created_at = serializers.DateTimeField()


class AnswerSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    body = serializers.CharField()
    author = serializers.CharField()
    is_staff = serializers.BooleanField()
    mine = serializers.BooleanField()
    created_at = serializers.DateTimeField()


class QuestionSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    body = serializers.CharField()
    asker = serializers.CharField()
    mine = serializers.BooleanField()
    created_at = serializers.DateTimeField()
    answers = AnswerSerializer(many=True)


class NoteSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    seconds = serializers.IntegerField()
    body = serializers.CharField()
    created_at = serializers.DateTimeField()


class AnnouncementSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    title = serializers.CharField()
    body = serializers.CharField(help_text="Sanitised HTML")
    created_at = serializers.DateTimeField()


# --- the console ---


class PublishRequestSerializer(StrictSerializer):
    unlisted = serializers.BooleanField(
        required=False,
        default=False,
        help_text="Open the course by its link only, without listing it in the catalogue.",
    )


class AdminPersonSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    name = serializers.CharField()
    email = serializers.CharField()


class AdminRequestCourseSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    title = serializers.CharField()


class AdminAccessRequestSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    status = serializers.CharField()
    message = serializers.CharField(allow_blank=True)
    created_at = serializers.DateTimeField()
    decided_at = serializers.DateTimeField(allow_null=True)
    course = AdminRequestCourseSerializer()
    user = AdminPersonSerializer()


class AdminRequestsQuerySerializer(StrictSerializer):
    status = serializers.CharField(required=False, allow_blank=True, max_length=10, default="")
    limit = serializers.IntegerField(required=False, min_value=1, max_value=100)
    offset = serializers.IntegerField(required=False, min_value=0)

    def validate_status(self, value: str) -> str:
        if value and value not in ("pending", "approved", "rejected"):
            raise serializers.ValidationError("Choose pending, approved or rejected.")
        return value


class AdminLearnerSerializer(serializers.Serializer):
    user_id = serializers.UUIDField()
    name = serializers.CharField()
    email = serializers.CharField()
    origin = serializers.CharField()
    started_at = serializers.DateTimeField()
    completed_at = serializers.DateTimeField(allow_null=True)
    percent = serializers.IntegerField()


class AdminReviewSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    user_id = serializers.UUIDField()
    reviewer = serializers.CharField()
    stars = serializers.IntegerField()
    feedback = serializers.CharField(allow_blank=True)
    created_at = serializers.DateTimeField()
    hidden = serializers.BooleanField()


class AdminAnswerSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    body = serializers.CharField()
    author = serializers.CharField()
    is_staff = serializers.BooleanField()
    hidden = serializers.BooleanField()
    created_at = serializers.DateTimeField()


class AdminQuestionSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    lecture = serializers.CharField()
    lesson_id = serializers.UUIDField()
    body = serializers.CharField()
    asker = serializers.CharField()
    created_at = serializers.DateTimeField()
    hidden = serializers.BooleanField()
    answers = AdminAnswerSerializer(many=True)


class AnnouncementCreateSerializer(StrictSerializer):
    title = serializers.CharField(min_length=1, max_length=160, trim_whitespace=True)
    body = serializers.CharField(min_length=1, max_length=20_000, trim_whitespace=False)


class YouTubeValidateSerializer(StrictSerializer):
    url = serializers.CharField(max_length=300)


class YouTubeCheckedSerializer(serializers.Serializer):
    video_id = serializers.CharField()
    url = serializers.CharField()
    title = serializers.CharField(allow_blank=True)
    thumbnail = serializers.CharField()


class BulkLinksSerializer(StrictSerializer):
    urls = serializers.ListField(
        child=serializers.CharField(max_length=300), min_length=1, max_length=30
    )
