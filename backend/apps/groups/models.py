from django.conf import settings
from django.db import models
from django.db.models import Q
from django.db.models.functions import Lower

from apps.core.models import BaseModel, SoftDeleteModel

MAX_MESSAGE = 2000


class ChatGroup(BaseModel):
    """A chat channel members join, such as the WO Women's Group. Admins make and archive them."""

    name = models.CharField(max_length=60)
    description = models.CharField(max_length=300, blank=True)
    emoji = models.CharField(max_length=16, blank=True)
    sort = models.PositiveIntegerField(default=0)
    archived_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )

    class Meta:
        ordering = ("sort", "name")
        constraints = [
            models.UniqueConstraint(Lower("name"), name="chatgroup_name_unique_ci"),
        ]

    def __str__(self) -> str:
        return self.name


class GroupMember(BaseModel):
    group = models.ForeignKey(ChatGroup, on_delete=models.CASCADE, related_name="members")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="+")
    # Messages after this are unread for this member.
    last_read_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["group", "user"], name="groupmember_once"),
        ]
        indexes = [models.Index(fields=["user"], name="groupmember_user")]


class GroupMessage(BaseModel, SoftDeleteModel):
    group = models.ForeignKey(ChatGroup, on_delete=models.CASCADE, related_name="messages")
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="+")
    body = models.TextField(max_length=MAX_MESSAGE)
    reply_to = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    # Set when an admin, not the author, took the message down.
    removed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )

    class Meta:
        indexes = [
            models.Index(fields=["group", "-created_at"], name="groupmessage_recent"),
        ]
        constraints = [
            models.CheckConstraint(condition=~Q(body=""), name="groupmessage_body_not_blank"),
        ]


class MessageReaction(BaseModel):
    message = models.ForeignKey(GroupMessage, on_delete=models.CASCADE, related_name="reactions")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="+")
    emoji = models.CharField(max_length=16)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["message", "user", "emoji"], name="messagereaction_once"
            ),
        ]
