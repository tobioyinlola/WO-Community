from rest_framework import serializers

from apps.core.serializers import ImageSerializer, StrictSerializer
from apps.learning.models import ACCESS, LESSON_TYPES, LEVELS

MAX_MARKUP = 60_000


# --- input ---


class CourseFieldsMixin(serializers.Serializer):
    title = serializers.CharField(max_length=160)
    description = serializers.CharField(max_length=MAX_MARKUP, trim_whitespace=False)
    instructor = serializers.CharField(max_length=120)
    category = serializers.CharField(max_length=60)
    level = serializers.ChoiceField(choices=LEVELS)
    access = serializers.ChoiceField(choices=ACCESS, required=False)
    price_minor = serializers.IntegerField(
        min_value=1, max_value=100_000_000, required=False, allow_null=True
    )
    currency = serializers.CharField(min_length=3, max_length=3, required=False, allow_blank=True)
    open_to_visitors = serializers.BooleanField(required=False)
    certificate_enabled = serializers.BooleanField(required=False)


class CourseCreateSerializer(CourseFieldsMixin, StrictSerializer):
    pass


class CourseUpdateSerializer(StrictSerializer):
    title = serializers.CharField(max_length=160, required=False)
    description = serializers.CharField(
        max_length=MAX_MARKUP, required=False, trim_whitespace=False
    )
    instructor = serializers.CharField(max_length=120, required=False)
    category = serializers.CharField(max_length=60, required=False)
    level = serializers.ChoiceField(choices=LEVELS, required=False)
    access = serializers.ChoiceField(choices=ACCESS, required=False)
    price_minor = serializers.IntegerField(
        min_value=1, max_value=100_000_000, required=False, allow_null=True
    )
    currency = serializers.CharField(min_length=3, max_length=3, required=False, allow_blank=True)
    open_to_visitors = serializers.BooleanField(required=False)
    certificate_enabled = serializers.BooleanField(required=False)


class ModuleWriteSerializer(StrictSerializer):
    title = serializers.CharField(max_length=160)


class LessonCreateSerializer(StrictSerializer):
    type = serializers.ChoiceField(choices=LESSON_TYPES)
    title = serializers.CharField(max_length=160)
    duration_seconds = serializers.IntegerField(
        min_value=1, max_value=86_400, required=False, allow_null=True
    )
    video_url = serializers.CharField(max_length=300, required=False)
    body = serializers.CharField(max_length=MAX_MARKUP, required=False, trim_whitespace=False)
    resource_url = serializers.CharField(max_length=300, required=False)
    resource_name = serializers.CharField(max_length=160, required=False)


class LessonUpdateSerializer(StrictSerializer):
    type = serializers.ChoiceField(choices=LESSON_TYPES, required=False)
    title = serializers.CharField(max_length=160, required=False)
    duration_seconds = serializers.IntegerField(
        min_value=1, max_value=86_400, required=False, allow_null=True
    )
    video_url = serializers.CharField(max_length=300, required=False)
    body = serializers.CharField(max_length=MAX_MARKUP, required=False, trim_whitespace=False)
    resource_url = serializers.CharField(max_length=300, required=False)
    resource_name = serializers.CharField(max_length=160, required=False)


class OrderSerializer(StrictSerializer):
    ids = serializers.ListField(child=serializers.UUIDField(), max_length=200)


class CourseCoverSerializer(StrictSerializer):
    upload_id = serializers.UUIDField()


class GrantSerializer(StrictSerializer):
    user_id = serializers.UUIDField()


class CatalogueQuerySerializer(StrictSerializer):
    q = serializers.CharField(required=False, allow_blank=True, max_length=100, default="")
    category = serializers.CharField(required=False, allow_blank=True, max_length=60, default="")
    level = serializers.ChoiceField(choices=LEVELS, required=False, default="")
    access = serializers.ChoiceField(choices=ACCESS, required=False, default="")
    enrolled = serializers.BooleanField(required=False, default=False)
    cursor = serializers.CharField(required=False, allow_blank=True, max_length=400, default="")
    limit = serializers.IntegerField(required=False, min_value=1, max_value=50, default=20)


class PageQuerySerializer(StrictSerializer):
    cursor = serializers.CharField(required=False, allow_blank=True, max_length=400, default="")
    limit = serializers.IntegerField(required=False, min_value=1, max_value=50, default=20)


class AdminQuerySerializer(StrictSerializer):
    status = serializers.ChoiceField(choices=["draft", "published"], required=False, default="")
    access = serializers.ChoiceField(choices=ACCESS, required=False, default="")
    q = serializers.CharField(required=False, allow_blank=True, max_length=100, default="")
    limit = serializers.IntegerField(required=False, min_value=1, max_value=100)
    offset = serializers.IntegerField(required=False, min_value=0)


class ProgressSerializer(StrictSerializer):
    position_seconds = serializers.IntegerField(min_value=0, max_value=86_400, required=False)
    completed = serializers.BooleanField(required=False)

    def validate(self, attrs: dict) -> dict:
        if not attrs:
            raise serializers.ValidationError("Send position_seconds, completed or both.")
        return attrs


class RatingSerializer(StrictSerializer):
    stars = serializers.IntegerField(min_value=1, max_value=5)
    feedback = serializers.CharField(max_length=1000, required=False, allow_blank=True, default="")


# --- output ---


class PriceSerializer(serializers.Serializer):
    amount_minor = serializers.IntegerField(help_text="In the smallest unit (kobo, cents)")
    currency = serializers.CharField()


class RatingSummarySerializer(serializers.Serializer):
    average = serializers.FloatField(allow_null=True)
    count = serializers.IntegerField()


class CourseProgressSerializer(serializers.Serializer):
    enrolled = serializers.BooleanField()
    percent = serializers.IntegerField()
    completed_lessons = serializers.IntegerField(required=False)
    total_lessons = serializers.IntegerField(required=False)
    completed_at = serializers.DateTimeField(required=False, allow_null=True)
    origin = serializers.CharField(required=False)


class CourseSummarySerializer(serializers.Serializer):
    id = serializers.UUIDField()
    slug = serializers.CharField()
    title = serializers.CharField()
    excerpt = serializers.CharField()
    instructor = serializers.CharField()
    category = serializers.CharField()
    level = serializers.CharField()
    cover = ImageSerializer(allow_null=True)
    access = serializers.CharField()
    price = PriceSerializer(allow_null=True)
    open_to_visitors = serializers.BooleanField()
    certificate_enabled = serializers.BooleanField()
    rating = RatingSummarySerializer()
    lesson_count = serializers.IntegerField()
    status = serializers.CharField()
    progress = CourseProgressSerializer()


class CoursePageSerializer(serializers.Serializer):
    results = CourseSummarySerializer(many=True)
    next_cursor = serializers.CharField(allow_null=True)


class OutlineLessonSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    type = serializers.CharField()
    title = serializers.CharField()
    position = serializers.IntegerField()
    duration_seconds = serializers.IntegerField(allow_null=True)
    locked = serializers.BooleanField(help_text="True until you have access to open it")
    completed = serializers.BooleanField()


class OutlineModuleSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    title = serializers.CharField()
    position = serializers.IntegerField()
    lessons = OutlineLessonSerializer(many=True)


class ResumeSerializer(serializers.Serializer):
    lesson_id = serializers.UUIDField()
    position_seconds = serializers.IntegerField()


class MyRatingSerializer(serializers.Serializer):
    stars = serializers.IntegerField()
    feedback = serializers.CharField(allow_blank=True)


class CourseDetailSerializer(CourseSummarySerializer):
    description = serializers.CharField(help_text="Sanitised HTML")
    modules = OutlineModuleSerializer(many=True)
    resume = ResumeSerializer(allow_null=True)
    my_rating = MyRatingSerializer(allow_null=True)


class VideoSerializer(serializers.Serializer):
    provider = serializers.CharField()
    video_id = serializers.CharField()
    url = serializers.CharField()
    embed_url = serializers.CharField(help_text="Privacy-enhanced youtube-nocookie.com address")


class ResourceSerializer(serializers.Serializer):
    url = serializers.CharField()
    name = serializers.CharField()


class LessonProgressSerializer(serializers.Serializer):
    position_seconds = serializers.IntegerField()
    completed = serializers.BooleanField()


class LessonCourseSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    slug = serializers.CharField()
    title = serializers.CharField()


class LessonModuleSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    title = serializers.CharField()


class LessonDetailSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    course = LessonCourseSerializer()
    module = LessonModuleSerializer()
    type = serializers.CharField()
    title = serializers.CharField()
    duration_seconds = serializers.IntegerField(allow_null=True)
    video = VideoSerializer(allow_null=True)
    body = serializers.CharField(allow_blank=True, help_text="Sanitised HTML for reading lessons")
    resource = ResourceSerializer(allow_null=True)
    previous_lesson_id = serializers.UUIDField(allow_null=True)
    next_lesson_id = serializers.UUIDField(allow_null=True)
    progress = LessonProgressSerializer(allow_null=True)


class CertificateSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    code = serializers.CharField()
    holder_name = serializers.CharField()
    course_title = serializers.CharField()
    issued_at = serializers.DateTimeField()
    verify_url = serializers.CharField()


class VerifiedCertificateSerializer(serializers.Serializer):
    valid = serializers.BooleanField()
    code = serializers.CharField()
    holder_name = serializers.CharField()
    course_title = serializers.CharField()
    issued_at = serializers.DateTimeField()
    verify_url = serializers.CharField()


class PublicCourseSummarySerializer(serializers.Serializer):
    slug = serializers.CharField()
    title = serializers.CharField()
    excerpt = serializers.CharField()
    instructor = serializers.CharField()
    category = serializers.CharField()
    level = serializers.CharField()
    cover = ImageSerializer(allow_null=True)
    lesson_count = serializers.IntegerField()


class PublicCoursePageSerializer(serializers.Serializer):
    results = PublicCourseSummarySerializer(many=True)
    next_cursor = serializers.CharField(allow_null=True)


class PublicOutlineLessonSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    type = serializers.CharField()
    title = serializers.CharField()
    position = serializers.IntegerField()
    duration_seconds = serializers.IntegerField(allow_null=True)


class PublicOutlineModuleSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    title = serializers.CharField()
    position = serializers.IntegerField()
    lessons = PublicOutlineLessonSerializer(many=True)


class PublicCourseSerializer(serializers.Serializer):
    slug = serializers.CharField()
    title = serializers.CharField()
    instructor = serializers.CharField()
    category = serializers.CharField()
    level = serializers.CharField()
    cover = ImageSerializer(allow_null=True)
    rating = RatingSummarySerializer()
    description = serializers.CharField(help_text="Sanitised HTML")
    modules = PublicOutlineModuleSerializer(many=True)


class CategoriesSerializer(serializers.Serializer):
    categories = serializers.ListField(child=serializers.CharField())


class EnrolmentResultSerializer(serializers.Serializer):
    course_id = serializers.UUIDField()
    origin = serializers.CharField()
    started_at = serializers.DateTimeField()
    created = serializers.BooleanField()


class LessonProgressResultSerializer(serializers.Serializer):
    lesson_id = serializers.UUIDField()
    position_seconds = serializers.IntegerField()
    completed = serializers.BooleanField()
    course_percent = serializers.IntegerField()
    course_completed = serializers.BooleanField()


class AdminLessonSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    type = serializers.CharField()
    title = serializers.CharField()
    position = serializers.IntegerField()
    duration_seconds = serializers.IntegerField(allow_null=True)
    video_url = serializers.CharField(allow_blank=True)
    video_id = serializers.CharField(allow_blank=True)
    body = serializers.CharField(allow_blank=True)
    resource_url = serializers.CharField(allow_blank=True)
    resource_name = serializers.CharField(allow_blank=True)


class AdminModuleSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    title = serializers.CharField()
    position = serializers.IntegerField()
    lessons = AdminLessonSerializer(many=True)


class AdminCourseSerializer(CourseSummarySerializer):
    description = serializers.CharField(help_text="Sanitised HTML")
    price_minor = serializers.IntegerField(allow_null=True)
    currency = serializers.CharField(allow_blank=True)
    published_at = serializers.DateTimeField(allow_null=True)
    created_at = serializers.DateTimeField()
    edited_at = serializers.DateTimeField(allow_null=True)
    modules = AdminModuleSerializer(many=True)


class LessonStatSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    title = serializers.CharField()
    completed_by = serializers.IntegerField()


class CourseStatsSerializer(serializers.Serializer):
    enrolled = serializers.IntegerField()
    completed = serializers.IntegerField()
    completion_rate = serializers.FloatField(allow_null=True)
    rating = RatingSummarySerializer()
    lessons = LessonStatSerializer(many=True)


class AdminEnrolmentSerializer(serializers.Serializer):
    user_id = serializers.UUIDField()
    origin = serializers.CharField()
    started_at = serializers.DateTimeField()
    completed_at = serializers.DateTimeField(allow_null=True)
    percent = serializers.IntegerField()


class AdminRatingSerializer(serializers.Serializer):
    user_id = serializers.UUIDField()
    stars = serializers.IntegerField()
    feedback = serializers.CharField(allow_blank=True)
    created_at = serializers.DateTimeField()
