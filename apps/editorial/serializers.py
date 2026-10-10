from rest_framework import serializers

from apps.core.serializers import ImageSerializer, StrictSerializer
from apps.editorial.models import ITEM_TYPES, REACTION_KINDS, WIN_KINDS

MAX_MARKUP = 40_000


class ItemWriteMixin(serializers.Serializer):
    type = serializers.ChoiceField(choices=ITEM_TYPES)
    title = serializers.CharField(max_length=160)
    body = serializers.CharField(max_length=MAX_MARKUP, trim_whitespace=False)
    external_url = serializers.CharField(max_length=300, required=False, allow_blank=True)
    comments_enabled = serializers.BooleanField(required=False)
    public = serializers.BooleanField(required=False)
    startup_ids = serializers.ListField(
        child=serializers.UUIDField(), required=False, max_length=10
    )
    banner_starts_at = serializers.DateTimeField(required=False, allow_null=True)
    banner_ends_at = serializers.DateTimeField(required=False, allow_null=True)


class ItemCreateSerializer(ItemWriteMixin, StrictSerializer):
    pass


class ItemUpdateSerializer(StrictSerializer):
    type = serializers.ChoiceField(choices=ITEM_TYPES, required=False)
    title = serializers.CharField(max_length=160, required=False)
    body = serializers.CharField(max_length=MAX_MARKUP, required=False, trim_whitespace=False)
    external_url = serializers.CharField(max_length=300, required=False, allow_blank=True)
    comments_enabled = serializers.BooleanField(required=False)
    public = serializers.BooleanField(required=False)
    startup_ids = serializers.ListField(
        child=serializers.UUIDField(), required=False, max_length=10
    )
    banner_starts_at = serializers.DateTimeField(required=False, allow_null=True)
    banner_ends_at = serializers.DateTimeField(required=False, allow_null=True)


class ScheduleSerializer(StrictSerializer):
    publish_at = serializers.DateTimeField()


class CoverSerializer(StrictSerializer):
    upload_id = serializers.UUIDField()


class ItemCommentModerationSerializer(StrictSerializer):
    reason = serializers.CharField(required=False, allow_blank=True, max_length=500, default="")


class EditorialQuerySerializer(StrictSerializer):
    type = serializers.ChoiceField(choices=ITEM_TYPES, required=False, default="")
    cursor = serializers.CharField(required=False, allow_blank=True, max_length=400, default="")
    limit = serializers.IntegerField(required=False, min_value=1, max_value=50, default=20)


class EditorialPageQuerySerializer(StrictSerializer):
    cursor = serializers.CharField(required=False, allow_blank=True, max_length=400, default="")
    limit = serializers.IntegerField(required=False, min_value=1, max_value=50, default=20)


class AdminQuerySerializer(StrictSerializer):
    status = serializers.ChoiceField(
        choices=["draft", "scheduled", "published"], required=False, default=""
    )
    type = serializers.ChoiceField(choices=ITEM_TYPES, required=False, default="")
    q = serializers.CharField(required=False, allow_blank=True, max_length=100, default="")
    limit = serializers.IntegerField(required=False, min_value=1, max_value=100)
    offset = serializers.IntegerField(required=False, min_value=0)


class CommentWriteSerializer(StrictSerializer):
    body = serializers.CharField(max_length=MAX_MARKUP, trim_whitespace=False)


class ItemReactionSerializer(StrictSerializer):
    kind = serializers.ChoiceField(choices=REACTION_KINDS)


class WinCreateSerializer(StrictSerializer):
    kind = serializers.ChoiceField(choices=WIN_KINDS)
    title = serializers.CharField(max_length=160)
    evidence_url = serializers.CharField(max_length=300)
    details = serializers.CharField(max_length=1000, required=False, allow_blank=True)
    startup_id = serializers.UUIDField(required=False, allow_null=True)


class WinQuerySerializer(StrictSerializer):
    status = serializers.ChoiceField(
        choices=["pending", "approved", "rejected"], required=False, default="pending"
    )
    limit = serializers.IntegerField(required=False, min_value=1, max_value=100)
    offset = serializers.IntegerField(required=False, min_value=0)


class WinReviewSerializer(StrictSerializer):
    reason = serializers.CharField(required=False, allow_blank=True, max_length=500, default="")


# --- output ---


class ItemStartupSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    slug = serializers.CharField()
    name = serializers.CharField()
    logo = ImageSerializer(allow_null=True)


class PersonSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    name = serializers.CharField()
    headline = serializers.CharField(allow_blank=True)
    photo = ImageSerializer(allow_null=True)
    slug = serializers.CharField(allow_null=True)


class EditorialItemSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    slug = serializers.CharField()
    type = serializers.CharField()
    title = serializers.CharField()
    excerpt = serializers.CharField()
    body = serializers.CharField(help_text="Sanitised HTML")
    cover = ImageSerializer(allow_null=True)
    startups = ItemStartupSerializer(many=True)
    external_url = serializers.CharField(allow_blank=True)
    comments_enabled = serializers.BooleanField()
    published_at = serializers.DateTimeField(allow_null=True)
    comment_count = serializers.IntegerField()
    reaction_count = serializers.IntegerField()
    reactions = serializers.DictField(child=serializers.IntegerField())
    my_reactions = serializers.ListField(child=serializers.CharField())


class EditorialItemPageSerializer(serializers.Serializer):
    results = EditorialItemSerializer(many=True)
    next_cursor = serializers.CharField(allow_null=True)


class AdminItemSerializer(EditorialItemSerializer):
    status = serializers.CharField()
    public = serializers.BooleanField()
    publish_at = serializers.DateTimeField(allow_null=True)
    banner_starts_at = serializers.DateTimeField(allow_null=True)
    banner_ends_at = serializers.DateTimeField(allow_null=True)
    created_by = serializers.UUIDField(allow_null=True)
    created_at = serializers.DateTimeField()
    edited_at = serializers.DateTimeField(allow_null=True)


class BannerSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    slug = serializers.CharField()
    title = serializers.CharField()
    excerpt = serializers.CharField()
    external_url = serializers.CharField(allow_blank=True)
    ends_at = serializers.DateTimeField()


class ItemCommentSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    item_id = serializers.UUIDField()
    body = serializers.CharField(help_text="Sanitised HTML")
    author = PersonSerializer()
    created_at = serializers.DateTimeField()
    edited_at = serializers.DateTimeField(allow_null=True)
    mine = serializers.BooleanField()


class ItemCommentPageSerializer(serializers.Serializer):
    results = ItemCommentSerializer(many=True)
    next_cursor = serializers.CharField(allow_null=True)


class ItemReactionResultSerializer(serializers.Serializer):
    created = serializers.BooleanField()
    reactions = serializers.DictField(child=serializers.IntegerField())
    reaction_count = serializers.IntegerField()


class WinSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    kind = serializers.CharField()
    title = serializers.CharField()
    evidence_url = serializers.CharField()
    details = serializers.CharField(allow_blank=True)
    startup_id = serializers.UUIDField(allow_null=True)
    status = serializers.CharField()
    review_note = serializers.CharField(allow_blank=True)
    created_at = serializers.DateTimeField()
    reviewed_at = serializers.DateTimeField(allow_null=True)


class WinPageSerializer(serializers.Serializer):
    results = WinSerializer(many=True)
    next_cursor = serializers.CharField(allow_null=True)


class AdminWinSerializer(WinSerializer):
    submitter_id = serializers.UUIDField()
    item_id = serializers.UUIDField(allow_null=True)
    reviewed_by = serializers.UUIDField(allow_null=True)


class PublicSummarySerializer(serializers.Serializer):
    slug = serializers.CharField()
    type = serializers.CharField()
    title = serializers.CharField()
    excerpt = serializers.CharField()
    cover = ImageSerializer(allow_null=True)
    published_at = serializers.DateTimeField()


class PublicPageSerializer(serializers.Serializer):
    results = PublicSummarySerializer(many=True)
    next_cursor = serializers.CharField(allow_null=True)


class NewsOpenGraphSerializer(serializers.Serializer):
    title = serializers.CharField()
    description = serializers.CharField()
    url = serializers.CharField()
    type = serializers.CharField()
    image = serializers.CharField(allow_null=True)


class PublicItemSerializer(PublicSummarySerializer):
    body = serializers.CharField(help_text="Sanitised HTML")
    startups = ItemStartupSerializer(many=True)
    external_url = serializers.CharField(allow_blank=True)
    share_url = serializers.CharField()
    open_graph = NewsOpenGraphSerializer()
