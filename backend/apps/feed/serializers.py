from typing import Any

from rest_framework import serializers

from apps.core.serializers import ImageSerializer, StrictSerializer
from apps.feed.models import CATEGORIES, REACTION_KINDS, REPORT_REASONS

MAX_BODY_MARKUP = 20_000  # the raw request; the text limit is applied after cleaning


class ImageInputSerializer(StrictSerializer):
    """Keep an existing image (``image_id``) or add a finished upload (``upload_id``)."""

    image_id = serializers.UUIDField(required=False)
    upload_id = serializers.UUIDField(required=False)
    alt = serializers.CharField(required=False, allow_blank=True, max_length=300, default="")

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        if ("image_id" in attrs) == ("upload_id" in attrs):
            raise serializers.ValidationError("Send either image_id or upload_id.")
        return attrs


class ShareInputSerializer(StrictSerializer):
    kind = serializers.ChoiceField(choices=["course", "event"])
    ref = serializers.CharField(max_length=120, help_text="The course's slug, or the event's id")


class ShareCardSerializer(serializers.Serializer):
    kind = serializers.CharField()
    ref = serializers.CharField()
    title = serializers.CharField()
    excerpt = serializers.CharField(allow_blank=True)
    url = serializers.CharField(help_text="Where a member opens it, within the app")
    badge = serializers.CharField()
    action = serializers.CharField()
    image = serializers.CharField(allow_null=True)
    facts = serializers.ListField(child=serializers.CharField())
    by = serializers.CharField(allow_blank=True)


class PostCreateSerializer(StrictSerializer):
    category = serializers.ChoiceField(choices=CATEGORIES)
    body = serializers.CharField(
        max_length=MAX_BODY_MARKUP,
        trim_whitespace=False,
        allow_blank=True,
        help_text="Required, unless the post shares a course or event.",
    )
    share = ShareInputSerializer(
        required=False, allow_null=True, default=None, help_text="A course or event to share"
    )
    images = serializers.ListField(
        child=ImageInputSerializer(), required=False, default=list, max_length=10
    )
    startup_id = serializers.UUIDField(required=False, allow_null=True, default=None)
    mentions = serializers.ListField(
        child=serializers.UUIDField(), required=False, default=list, max_length=20
    )


class PostUpdateSerializer(StrictSerializer):
    category = serializers.ChoiceField(choices=CATEGORIES, required=False)
    body = serializers.CharField(max_length=MAX_BODY_MARKUP, trim_whitespace=False, required=False)
    images = serializers.ListField(child=ImageInputSerializer(), required=False, max_length=10)
    mentions = serializers.ListField(child=serializers.UUIDField(), required=False, max_length=20)


class CommentCreateSerializer(StrictSerializer):
    body = serializers.CharField(max_length=MAX_BODY_MARKUP, trim_whitespace=False)
    parent_id = serializers.UUIDField(required=False, allow_null=True, default=None)
    mentions = serializers.ListField(
        child=serializers.UUIDField(), required=False, default=list, max_length=20
    )


class CommentUpdateSerializer(StrictSerializer):
    body = serializers.CharField(max_length=MAX_BODY_MARKUP, trim_whitespace=False)


class ReactionSerializer(StrictSerializer):
    kind = serializers.ChoiceField(choices=REACTION_KINDS)


class FeedQuerySerializer(StrictSerializer):
    sort = serializers.ChoiceField(choices=["newest", "engaged"], required=False, default="newest")
    scope = serializers.ChoiceField(
        choices=["all", "following", "mine"], required=False, default="all"
    )
    category = serializers.ChoiceField(choices=CATEGORIES, required=False, default="")
    country = serializers.RegexField(r"^[A-Za-z]{2}$", required=False, default="")
    cursor = serializers.CharField(required=False, allow_blank=True, max_length=400, default="")
    limit = serializers.IntegerField(required=False, min_value=1, max_value=50, default=20)

    def validate_country(self, value: str) -> str:
        return value.upper()


class CommentQuerySerializer(StrictSerializer):
    cursor = serializers.CharField(required=False, allow_blank=True, max_length=400, default="")
    limit = serializers.IntegerField(required=False, min_value=1, max_value=50, default=20)


class AuthorSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    name = serializers.CharField()
    headline = serializers.CharField(allow_blank=True)
    photo = ImageSerializer(allow_null=True)
    slug = serializers.CharField(allow_null=True)
    following = serializers.BooleanField(default=False)


class PostStartupSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    slug = serializers.CharField()
    name = serializers.CharField()
    logo = ImageSerializer(allow_null=True)
    following = serializers.BooleanField(default=False)


class PostImageSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    urls = ImageSerializer()
    alt = serializers.CharField(allow_blank=True)


class LinkPreviewSerializer(serializers.Serializer):
    url = serializers.CharField()
    title = serializers.CharField(allow_blank=True)
    description = serializers.CharField(allow_blank=True)
    site_name = serializers.CharField(allow_blank=True)
    image = ImageSerializer(allow_null=True)


class PostSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    category = serializers.CharField()
    body = serializers.CharField(help_text="Sanitised HTML")
    country = serializers.CharField(allow_blank=True)
    author = AuthorSerializer()
    startup = PostStartupSerializer(allow_null=True)
    images = PostImageSerializer(many=True)
    previews = LinkPreviewSerializer(many=True, help_text="Cards for links, once fetched")
    created_at = serializers.DateTimeField()
    edited_at = serializers.DateTimeField(allow_null=True)
    official = serializers.BooleanField(help_text="Marked as an official announcement")
    comments_enabled = serializers.BooleanField()
    pinned = serializers.BooleanField()
    featured = serializers.BooleanField()
    hidden = serializers.BooleanField(help_text="Only ever true for the author's own view")
    comment_count = serializers.IntegerField()
    reaction_count = serializers.IntegerField()
    reactions = serializers.DictField(child=serializers.IntegerField())
    my_reactions = serializers.ListField(child=serializers.CharField())
    mine = serializers.BooleanField()
    shared = ShareCardSerializer(allow_null=True, help_text="The course or event it shares")
    shared_gone = serializers.BooleanField(
        help_text="It shared something no longer available (unpublished, say)"
    )
    shareable = serializers.BooleanField(
        help_text="Whether a link to it may be shared outside the platform"
    )


class FeedSerializer(serializers.Serializer):
    results = PostSerializer(many=True)
    pinned = PostSerializer(many=True, required=False)
    next_cursor = serializers.CharField(allow_null=True)


class ReplySerializer(serializers.Serializer):
    id = serializers.UUIDField()
    post_id = serializers.UUIDField()
    parent_id = serializers.UUIDField(allow_null=True)
    body = serializers.CharField(help_text="Sanitised HTML")
    author = AuthorSerializer()
    created_at = serializers.DateTimeField()
    edited_at = serializers.DateTimeField(allow_null=True)
    reaction_count = serializers.IntegerField()
    reactions = serializers.DictField(child=serializers.IntegerField())
    my_reactions = serializers.ListField(child=serializers.CharField())
    mine = serializers.BooleanField()


class CommentSerializer(ReplySerializer):
    replies = ReplySerializer(many=True)


class CommentListSerializer(serializers.Serializer):
    results = CommentSerializer(many=True)
    next_cursor = serializers.CharField(allow_null=True)


class ReactionResultSerializer(serializers.Serializer):
    created = serializers.BooleanField()
    reactions = serializers.DictField(child=serializers.IntegerField())
    reaction_count = serializers.IntegerField()


class ModerationSerializer(StrictSerializer):
    reason = serializers.CharField(required=False, allow_blank=True, max_length=500, default="")


class FollowSerializer(StrictSerializer):
    type = serializers.ChoiceField(choices=["member", "startup"])
    id = serializers.UUIDField()


class FollowResultSerializer(serializers.Serializer):
    type = serializers.CharField()
    id = serializers.UUIDField()
    following = serializers.BooleanField()


class SuggestionQuerySerializer(StrictSerializer):
    limit = serializers.IntegerField(required=False, min_value=1, max_value=30, default=10)


class SuggestionSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    slug = serializers.CharField()
    name = serializers.CharField()
    headline = serializers.CharField(allow_blank=True)
    image = ImageSerializer(allow_null=True)
    score = serializers.IntegerField()
    reasons = serializers.ListField(child=serializers.CharField())


class FollowingQuerySerializer(StrictSerializer):
    type = serializers.ChoiceField(choices=["member", "startup"], required=False, default="")
    cursor = serializers.CharField(required=False, allow_blank=True, max_length=400, default="")
    limit = serializers.IntegerField(required=False, min_value=1, max_value=100, default=50)


class FollowingItemSerializer(serializers.Serializer):
    type = serializers.CharField()
    id = serializers.UUIDField()
    slug = serializers.CharField(allow_null=True)
    name = serializers.CharField()
    headline = serializers.CharField(allow_blank=True)
    image = ImageSerializer(allow_null=True)
    followed_at = serializers.DateTimeField()


class FollowingListSerializer(serializers.Serializer):
    results = FollowingItemSerializer(many=True)
    next_cursor = serializers.CharField(allow_null=True)


class ReportCreateSerializer(StrictSerializer):
    reason = serializers.ChoiceField(choices=REPORT_REASONS)
    details = serializers.CharField(required=False, allow_blank=True, max_length=500, default="")


class ReportReceivedSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    status = serializers.CharField()
    created = serializers.BooleanField(help_text="False if you had already reported this")


class ReportQuerySerializer(StrictSerializer):
    status = serializers.ChoiceField(
        choices=["open", "reviewed", "actioned"], required=False, default="open"
    )
    target_type = serializers.ChoiceField(
        choices=["post", "comment", "news_comment"],
        required=False,
        default="",
        help_text="`news_comment` is a comment on news or a win.",
    )
    reason = serializers.ChoiceField(choices=REPORT_REASONS, required=False, default="")
    limit = serializers.IntegerField(required=False, min_value=1, max_value=100)
    offset = serializers.IntegerField(required=False, min_value=0)


class ReportPersonSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    name = serializers.CharField()


class ReportTargetSerializer(serializers.Serializer):
    type = serializers.CharField()
    id = serializers.UUIDField()
    post_id = serializers.UUIDField(allow_null=True)
    state = serializers.ChoiceField(choices=["visible", "hidden", "removed"])
    excerpt = serializers.CharField(allow_blank=True)
    created_at = serializers.DateTimeField(allow_null=True)
    author = ReportPersonSerializer(allow_null=True)


class AdminReportSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    status = serializers.CharField()
    reason = serializers.CharField()
    details = serializers.CharField(allow_blank=True)
    created_at = serializers.DateTimeField()
    reporter = ReportPersonSerializer()
    handled_by = serializers.UUIDField(allow_null=True)
    handled_at = serializers.DateTimeField(allow_null=True)
    note = serializers.CharField(allow_blank=True)
    open_reports_on_target = serializers.IntegerField()
    target = ReportTargetSerializer()


class ReportReviewSerializer(StrictSerializer):
    note = serializers.CharField(required=False, allow_blank=True, max_length=500, default="")


class ReportActionSerializer(StrictSerializer):
    action = serializers.ChoiceField(choices=["hide", "remove"])
    note = serializers.CharField(required=False, allow_blank=True, max_length=500, default="")


class AdminPreviewQuerySerializer(StrictSerializer):
    q = serializers.CharField(required=False, allow_blank=True, max_length=200, default="")
    status = serializers.ChoiceField(
        choices=["pending", "ready", "failed"], required=False, default=""
    )
    limit = serializers.IntegerField(required=False, min_value=1, max_value=100)
    offset = serializers.IntegerField(required=False, min_value=0)


class AdminPreviewSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    url = serializers.CharField()
    domain = serializers.CharField()
    status = serializers.CharField()
    title = serializers.CharField(allow_blank=True)
    site_name = serializers.CharField(allow_blank=True)
    fail_code = serializers.CharField(allow_blank=True)
    attempts = serializers.IntegerField()
    fetched_at = serializers.DateTimeField(allow_null=True)
    posts = serializers.IntegerField(help_text="How many posts show this card.")
    blocked = serializers.BooleanField()


class BlockDomainSerializer(StrictSerializer):
    domain = serializers.CharField(max_length=253, help_text="example.com, or a pasted address.")
    reason = serializers.CharField(required=False, allow_blank=True, max_length=300, default="")


class BlockedDomainSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    domain = serializers.CharField()
    reason = serializers.CharField(allow_blank=True)
    created_at = serializers.DateTimeField()


class FeedActivityQuerySerializer(StrictSerializer):
    limit = serializers.IntegerField(required=False, min_value=1, max_value=30, default=8)


class FeedActivitySerializer(serializers.Serializer):
    id = serializers.UUIDField()
    kind = serializers.ChoiceField(choices=["comment", "reaction"])
    detail = serializers.CharField(allow_blank=True, help_text="The comment text, or the reaction")
    actor = AuthorSerializer()
    post_id = serializers.UUIDField()
    post_author = serializers.CharField()
    post_excerpt = serializers.CharField(allow_blank=True)
    mine = serializers.BooleanField()
    created_at = serializers.DateTimeField()
