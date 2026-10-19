from rest_framework import serializers

from apps.core.serializers import ImageSerializer, StrictSerializer
from apps.learning.models import ACCESS, CERTIFICATE_STATUSES, LESSON_TYPES, LEVELS

MAX_MARKUP = 60_000


# --- input ---


def _list_of_text() -> serializers.ListField:
    return serializers.ListField(
        child=serializers.CharField(max_length=200), required=False, max_length=12
    )


class CourseFieldsMixin(serializers.Serializer):
    """What can be set on a course. Only the title is needed to start a draft."""

    title = serializers.CharField(max_length=160)
    subtitle = serializers.CharField(max_length=180, required=False, allow_blank=True)
    description = serializers.CharField(
        max_length=MAX_MARKUP, required=False, trim_whitespace=False
    )
    instructor = serializers.CharField(max_length=120, required=False)
    category = serializers.CharField(max_length=60, required=False)
    level = serializers.ChoiceField(choices=LEVELS, required=False)
    language = serializers.CharField(max_length=8, required=False)
    learn_bullets = _list_of_text()
    requirements = _list_of_text()
    audience = serializers.CharField(max_length=1000, required=False, allow_blank=True)
    promo_video_url = serializers.CharField(max_length=300, required=False, allow_blank=True)
    enrolment_active = serializers.BooleanField(required=False)
    access = serializers.ChoiceField(choices=ACCESS, required=False)
    price_minor = serializers.IntegerField(
        min_value=1, max_value=100_000_000, required=False, allow_null=True
    )
    currency = serializers.CharField(min_length=3, max_length=3, required=False, allow_blank=True)
    promo_price_minor = serializers.IntegerField(
        min_value=1, max_value=100_000_000, required=False, allow_null=True
    )
    promo_starts_at = serializers.DateTimeField(required=False, allow_null=True)
    promo_ends_at = serializers.DateTimeField(required=False, allow_null=True)
    open_to_visitors = serializers.BooleanField(required=False)
    certificate_enabled = serializers.BooleanField(required=False)


class CourseCreateSerializer(CourseFieldsMixin, StrictSerializer):
    pass


class CourseUpdateSerializer(CourseFieldsMixin, StrictSerializer):
    title = serializers.CharField(max_length=160, required=False)


class ModuleWriteSerializer(StrictSerializer):
    title = serializers.CharField(max_length=160)


class LessonCreateSerializer(StrictSerializer):
    type = serializers.ChoiceField(choices=LESSON_TYPES)
    title = serializers.CharField(max_length=160)
    duration_seconds = serializers.IntegerField(
        min_value=1, max_value=86_400, required=False, allow_null=True
    )
    description = serializers.CharField(max_length=2000, required=False, allow_blank=True)
    is_preview = serializers.BooleanField(required=False)
    video_url = serializers.CharField(max_length=300, required=False)
    body = serializers.CharField(max_length=MAX_MARKUP, required=False, trim_whitespace=False)
    resource_url = serializers.CharField(max_length=300, required=False)
    resource_name = serializers.CharField(max_length=160, required=False)
    upload_id = serializers.UUIDField(
        required=False, help_text="A ready `course_file` upload, instead of `resource_url`."
    )


class LessonUpdateSerializer(StrictSerializer):
    type = serializers.ChoiceField(choices=LESSON_TYPES, required=False)
    title = serializers.CharField(max_length=160, required=False)
    duration_seconds = serializers.IntegerField(
        min_value=1, max_value=86_400, required=False, allow_null=True
    )
    description = serializers.CharField(max_length=2000, required=False, allow_blank=True)
    is_preview = serializers.BooleanField(required=False)
    video_url = serializers.CharField(max_length=300, required=False)
    body = serializers.CharField(max_length=MAX_MARKUP, required=False, trim_whitespace=False)
    resource_url = serializers.CharField(max_length=300, required=False)
    resource_name = serializers.CharField(max_length=160, required=False)
    upload_id = serializers.UUIDField(
        required=False, help_text="A ready `course_file` upload, instead of `resource_url`."
    )


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
    language = serializers.CharField(required=False, allow_blank=True, max_length=8, default="")
    rating_min = serializers.IntegerField(required=False, min_value=0, max_value=5, default=0)
    duration = serializers.ChoiceField(
        choices=("short", "medium", "long"), required=False, allow_blank=True, default=""
    )
    sort = serializers.ChoiceField(
        choices=("newest", "popular", "rating"), required=False, default="newest"
    )
    cursor = serializers.CharField(required=False, allow_blank=True, max_length=400, default="")
    limit = serializers.IntegerField(required=False, min_value=1, max_value=50, default=20)


class ShelfQuerySerializer(StrictSerializer):
    state = serializers.ChoiceField(
        choices=("all", "in_progress", "completed", "wishlist"), required=False, default="all"
    )
    cursor = serializers.CharField(required=False, allow_blank=True, max_length=400, default="")
    limit = serializers.IntegerField(required=False, min_value=1, max_value=50, default=20)


class PageQuerySerializer(StrictSerializer):
    cursor = serializers.CharField(required=False, allow_blank=True, max_length=400, default="")
    limit = serializers.IntegerField(required=False, min_value=1, max_value=50, default=20)


class AdminQuerySerializer(StrictSerializer):
    status = serializers.ChoiceField(
        choices=["draft", "published", "unlisted"], required=False, default=""
    )
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
    original_minor = serializers.IntegerField(
        allow_null=True, help_text="The usual price, while a promotion is running"
    )
    promo_ends_at = serializers.DateTimeField(allow_null=True)


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
    time_remaining_seconds = serializers.IntegerField(required=False)


class CourseSummarySerializer(serializers.Serializer):
    id = serializers.UUIDField()
    slug = serializers.CharField()
    title = serializers.CharField()
    subtitle = serializers.CharField(allow_blank=True)
    excerpt = serializers.CharField()
    instructor = serializers.CharField()
    category = serializers.CharField()
    level = serializers.CharField()
    language = serializers.CharField()
    language_label = serializers.CharField()
    learners_count = serializers.IntegerField()
    duration_seconds = serializers.IntegerField()
    enrolment_active = serializers.BooleanField()
    cover = ImageSerializer(allow_null=True)
    access = serializers.CharField()
    price = PriceSerializer(allow_null=True)
    open_to_visitors = serializers.BooleanField()
    certificate_enabled = serializers.BooleanField()
    rating = RatingSummarySerializer()
    lesson_count = serializers.IntegerField()
    status = serializers.CharField()
    progress = CourseProgressSerializer()
    wishlisted = serializers.BooleanField()
    access_request = serializers.CharField(allow_null=True)


class CoursePageSerializer(serializers.Serializer):
    results = CourseSummarySerializer(many=True)
    next_cursor = serializers.CharField(allow_null=True)


class OutlineLessonSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    type = serializers.CharField()
    title = serializers.CharField()
    position = serializers.IntegerField()
    duration_seconds = serializers.IntegerField(allow_null=True)
    preview = serializers.BooleanField(help_text="Anyone signed in may watch it before enrolling")
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
    kind = serializers.ChoiceField(
        choices=["link", "file"],
        help_text="`link` opens `url`; `file` is a stored document, fetched with "
        "`GET /lessons/{id}/file`.",
    )
    url = serializers.CharField(allow_blank=True)
    name = serializers.CharField()
    size = serializers.IntegerField(allow_null=True)
    content_type = serializers.CharField(allow_blank=True)


class LessonFileSerializer(serializers.Serializer):
    url = serializers.CharField(help_text="Signed address; saves the file as an attachment.")
    expires_in = serializers.IntegerField(help_text="Seconds the address stays valid.")
    name = serializers.CharField()
    size = serializers.IntegerField(allow_null=True)
    content_type = serializers.CharField()


class AdminLessonFileSerializer(serializers.Serializer):
    name = serializers.CharField()
    size = serializers.IntegerField(allow_null=True)
    content_type = serializers.CharField()


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
    description = serializers.CharField(allow_blank=True)
    preview = serializers.BooleanField()
    video = VideoSerializer(allow_null=True)
    body = serializers.CharField(allow_blank=True, help_text="Sanitised HTML for reading lessons")
    resource = ResourceSerializer(allow_null=True)
    previous_lesson_id = serializers.UUIDField(allow_null=True)
    next_lesson_id = serializers.UUIDField(allow_null=True)
    progress = LessonProgressSerializer(allow_null=True)


class CertificateSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    course_slug = serializers.CharField()
    number = serializers.CharField(help_text="For example WO-C-2026-000341")
    holder_name = serializers.CharField()
    course_title = serializers.CharField()
    issued_at = serializers.DateTimeField()
    hours = serializers.FloatField(help_text="The length of the course, in hours")
    status = serializers.ChoiceField(choices=CERTIFICATE_STATUSES)
    title_text = serializers.CharField()
    signatory_name = serializers.CharField(allow_blank=True)
    signatory_title = serializers.CharField(allow_blank=True)
    signature_url = serializers.CharField(allow_null=True)
    verify_url = serializers.CharField()
    show_on_profile = serializers.BooleanField(
        help_text="Whether the holder lists this certificate on their profile"
    )


class CertificateChoiceSerializer(serializers.Serializer):
    show_on_profile = serializers.BooleanField()


class ProfileCertificateSerializer(serializers.Serializer):
    number = serializers.CharField()
    course_title = serializers.CharField()
    issued_at = serializers.DateTimeField()
    hours = serializers.FloatField()
    verify_url = serializers.CharField()


class CertificateDownloadSerializer(serializers.Serializer):
    url = serializers.CharField(help_text="A short lived address that downloads the PDF")
    expires_in = serializers.IntegerField(help_text="Seconds the address works for")
    filename = serializers.CharField()


class VerifiedCertificateSerializer(serializers.Serializer):
    valid = serializers.BooleanField()
    status = serializers.ChoiceField(choices=CERTIFICATE_STATUSES)
    number = serializers.CharField()
    holder_name = serializers.CharField(allow_blank=True)
    course_title = serializers.CharField(allow_blank=True)
    issued_at = serializers.DateTimeField(allow_null=True)
    hours = serializers.FloatField(allow_null=True)
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
    access = serializers.CharField(help_text="free or paid")


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
    description = serializers.CharField(allow_blank=True)
    is_preview = serializers.BooleanField()
    video_url = serializers.CharField(allow_blank=True)
    video_id = serializers.CharField(allow_blank=True)
    body = serializers.CharField(allow_blank=True)
    resource_url = serializers.CharField(allow_blank=True)
    resource_name = serializers.CharField(allow_blank=True)
    file = AdminLessonFileSerializer(allow_null=True, required=False)


class AdminModuleSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    title = serializers.CharField()
    position = serializers.IntegerField()
    lessons = AdminLessonSerializer(many=True)


class PublishCheckSerializer(serializers.Serializer):
    key = serializers.CharField()
    text = serializers.CharField()
    done = serializers.BooleanField()
    step = serializers.IntegerField()


class AdminCourseSerializer(CourseSummarySerializer):
    description = serializers.CharField(help_text="Sanitised HTML")
    learn_bullets = serializers.ListField(child=serializers.CharField())
    requirements = serializers.ListField(child=serializers.CharField())
    audience = serializers.CharField(allow_blank=True)
    promo_video_id = serializers.CharField(allow_blank=True)
    promo_price_minor = serializers.IntegerField(allow_null=True)
    promo_starts_at = serializers.DateTimeField(allow_null=True)
    promo_ends_at = serializers.DateTimeField(allow_null=True)
    checklist = PublishCheckSerializer(many=True)
    pending_requests = serializers.IntegerField()
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


class CertificateSettingsWriteSerializer(StrictSerializer):
    title_text = serializers.CharField(max_length=60, required=False)
    signatory_name = serializers.CharField(max_length=120, required=False, allow_blank=True)
    signatory_title = serializers.CharField(max_length=120, required=False, allow_blank=True)
    signature_upload_id = serializers.UUIDField(
        required=False, help_text="A ready `cert_signature` upload."
    )
    remove_signature = serializers.BooleanField(required=False)


class CertificatePreviewSerializer(CertificateSettingsWriteSerializer):
    holder_name = serializers.CharField(max_length=160, required=False)


class CertificateSettingsSerializer(serializers.Serializer):
    title_text = serializers.CharField()
    signatory_name = serializers.CharField(allow_blank=True)
    signatory_title = serializers.CharField(allow_blank=True)
    signature_url = serializers.CharField(allow_null=True)
    version = serializers.IntegerField()
    updated_at = serializers.DateTimeField()


class AdminCertificateSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    number = serializers.CharField()
    holder_name = serializers.CharField()
    email = serializers.CharField()
    course_title = serializers.CharField()
    issued_at = serializers.DateTimeField()
    hours = serializers.FloatField()
    status = serializers.ChoiceField(choices=CERTIFICATE_STATUSES)
    revoked_at = serializers.DateTimeField(allow_null=True)
    revoked_reason = serializers.CharField(allow_blank=True)
    template_version = serializers.IntegerField(allow_null=True)


class AdminCertificatesQuerySerializer(StrictSerializer):
    q = serializers.CharField(required=False, allow_blank=True, max_length=100, default="")
    status = serializers.ChoiceField(choices=CERTIFICATE_STATUSES, required=False, default="")
    limit = serializers.IntegerField(required=False, min_value=1, max_value=100)
    offset = serializers.IntegerField(required=False, min_value=0)


class RevokeSerializer(StrictSerializer):
    reason = serializers.CharField(min_length=1, max_length=300, trim_whitespace=True)


class ReissueSerializer(StrictSerializer):
    holder_name = serializers.CharField(max_length=160, required=False, trim_whitespace=True)
