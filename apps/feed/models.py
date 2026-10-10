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
