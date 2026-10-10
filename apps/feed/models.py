from django.conf import settings
from django.db import models
from django.db.models import Q

from apps.core.models import BaseModel, SoftDeleteModel

CATEGORIES = ("update", "question", "win", "resource", "event", "opportunity")
REACTION_KINDS = ("like", "celebrate", "insightful")


class Post(BaseModel, SoftDeleteModel):
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="feed_posts"
    )
    # Set when the author posts on behalf of one of their startups.
    startup = models.ForeignKey(
        "startups.Startup", null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    category = models.CharField(max_length=12)
    body = models.TextField()  # sanitised HTML
    body_text = models.TextField()  # the same words with the markup removed
    # The author's country when they posted, so the feed can be filtered by country.
    country = models.CharField(max_length=2, blank=True)
    pinned_at = models.DateTimeField(null=True, blank=True)
    featured_at = models.DateTimeField(null=True, blank=True)
    hidden_at = models.DateTimeField(null=True, blank=True)
    edited_at = models.DateTimeField(null=True, blank=True)
    comment_count = models.PositiveIntegerField(default=0)
    reaction_count = models.PositiveIntegerField(default=0)
    reaction_counts = models.JSONField(default=dict, blank=True)
    # Reactions plus twice the comments: the "most engaged" order.
    engagement = models.PositiveIntegerField(default=0)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=Q(category__in=CATEGORIES), name="feed_post_category_valid"
            ),
        ]
        indexes = [
            models.Index(fields=["-created_at", "-id"], name="feed_post_newest_idx"),
            models.Index(fields=["-engagement", "-created_at", "-id"], name="feed_post_hot_idx"),
            models.Index(fields=["category", "-created_at"], name="feed_post_category_idx"),
            models.Index(fields=["author", "-created_at"], name="feed_post_author_idx"),
            models.Index(fields=["country", "-created_at"], name="feed_post_country_idx"),
        ]


class PostImage(BaseModel):
    post = models.ForeignKey(Post, on_delete=models.CASCADE, related_name="images")
    base_key = models.CharField(max_length=200)
    alt_text = models.CharField(max_length=200, blank=True)
    position = models.PositiveSmallIntegerField()

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["post", "position"], name="feed_image_position_unique")
        ]
        ordering = ["position"]


class Comment(BaseModel, SoftDeleteModel):
    post = models.ForeignKey(Post, on_delete=models.CASCADE, related_name="comments")
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="feed_comments"
    )
    # Replies go one level deep: the parent of a reply is always a top-level comment.
    parent = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.CASCADE, related_name="replies"
    )
    body = models.TextField()  # sanitised HTML
    hidden_at = models.DateTimeField(null=True, blank=True)
    edited_at = models.DateTimeField(null=True, blank=True)
    reaction_count = models.PositiveIntegerField(default=0)
    reaction_counts = models.JSONField(default=dict, blank=True)

    class Meta:
        indexes = [models.Index(fields=["post", "created_at", "id"], name="feed_comment_post_idx")]


class Reaction(BaseModel):
    """A member's reaction to a post or a comment. One row per member, target and kind."""

    class Target(models.TextChoices):
        POST = "post"
        COMMENT = "comment"

    target_type = models.CharField(max_length=8, choices=Target.choices)
    target_id = models.UUIDField()
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="feed_reactions"
    )
    kind = models.CharField(max_length=12)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["target_type", "target_id", "user", "kind"], name="feed_reaction_unique"
            ),
            models.CheckConstraint(
                condition=Q(kind__in=REACTION_KINDS), name="feed_reaction_kind_valid"
            ),
        ]
        indexes = [models.Index(fields=["user", "target_type", "target_id"], name="feed_mine_idx")]


class Follow(BaseModel):
    """A member following another member or a startup, to build their Following feed."""

    class Kind(models.TextChoices):
        MEMBER = "member"
        STARTUP = "startup"

    follower = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="feed_follows"
    )
    followee_type = models.CharField(max_length=8, choices=Kind.choices)
    followee_id = models.UUIDField()

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["follower", "followee_type", "followee_id"], name="feed_follow_unique"
            ),
            models.CheckConstraint(
                condition=Q(followee_type__in=["member", "startup"]),
                name="feed_follow_type_valid",
            ),
        ]
        indexes = [
            models.Index(fields=["follower", "-created_at", "-id"], name="feed_follow_mine_idx"),
            models.Index(fields=["followee_type", "followee_id"], name="feed_follow_target_idx"),
        ]


REPORT_REASONS = ("spam", "harassment", "misinformation", "illegal", "inappropriate", "other")


class Report(BaseModel):
    """A member's complaint about a post or comment, handled in the admin moderation queue."""

    class Status(models.TextChoices):
        OPEN = "open"
        REVIEWED = "reviewed"  # looked at, nothing needed doing
        ACTIONED = "actioned"  # the content was hidden or removed

    target_type = models.CharField(max_length=8, choices=Reaction.Target.choices)
    target_id = models.UUIDField()
    reporter = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="feed_reports"
    )
    reason = models.CharField(max_length=14)
    details = models.CharField(max_length=500, blank=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.OPEN)
    handled_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    handled_at = models.DateTimeField(null=True, blank=True)
    note = models.CharField(max_length=500, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["reporter", "target_type", "target_id"], name="feed_report_once"
            ),
            models.CheckConstraint(
                condition=Q(reason__in=REPORT_REASONS), name="feed_report_reason"
            ),
            models.CheckConstraint(
                condition=Q(status__in=["open", "reviewed", "actioned"]), name="feed_report_status"
            ),
        ]
        indexes = [
            models.Index(fields=["status", "created_at"], name="feed_report_queue_idx"),
            models.Index(fields=["target_type", "target_id"], name="feed_report_target_idx"),
        ]


class LinkPreview(BaseModel):
    """The card for a web address, fetched once and shared by every post that links to it."""

    class Status(models.TextChoices):
        PENDING = "pending"
        READY = "ready"
        FAILED = "failed"

    url_hash = models.CharField(max_length=64, unique=True)
    url = models.CharField(max_length=2000)
    status = models.CharField(max_length=8, choices=Status.choices, default=Status.PENDING)
    title = models.CharField(max_length=200, blank=True)
    description = models.CharField(max_length=300, blank=True)
    site_name = models.CharField(max_length=100, blank=True)
    image_key = models.CharField(max_length=200, blank=True)
    fail_code = models.CharField(max_length=30, blank=True)
    attempts = models.PositiveSmallIntegerField(default=0)
    fetched_at = models.DateTimeField(null=True, blank=True)


class PostLink(BaseModel):
    post = models.ForeignKey(Post, on_delete=models.CASCADE, related_name="links")
    preview = models.ForeignKey(LinkPreview, on_delete=models.PROTECT, related_name="posts")
    position = models.PositiveSmallIntegerField()

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["post", "position"], name="feed_link_position"),
            models.UniqueConstraint(fields=["post", "preview"], name="feed_link_once"),
        ]
        ordering = ["position"]
