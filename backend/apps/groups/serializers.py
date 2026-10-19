from rest_framework import serializers

from apps.core.serializers import ImageSerializer, StrictSerializer
from apps.groups.models import MAX_MESSAGE


class GroupLastMessageSerializer(serializers.Serializer):
    author = serializers.CharField()
    text = serializers.CharField()
    created_at = serializers.DateTimeField()


class ChatGroupSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    name = serializers.CharField()
    description = serializers.CharField(allow_blank=True)
    emoji = serializers.CharField(allow_blank=True)
    member_count = serializers.IntegerField()
    joined = serializers.BooleanField()
    unread = serializers.IntegerField(
        help_text="Messages from others since you last read, up to 99"
    )
    last_message = GroupLastMessageSerializer(
        allow_null=True, help_text="Only for groups you are in"
    )
    last_activity_at = serializers.DateTimeField(allow_null=True)


class ChatAuthorSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    name = serializers.CharField()
    headline = serializers.CharField(allow_blank=True)
    photo = ImageSerializer(allow_null=True)
    slug = serializers.CharField(allow_null=True)


class GroupReplySerializer(serializers.Serializer):
    id = serializers.UUIDField()
    author = serializers.CharField()
    text = serializers.CharField(allow_blank=True)
    deleted = serializers.BooleanField()


class GroupReactionCountSerializer(serializers.Serializer):
    emoji = serializers.CharField()
    count = serializers.IntegerField()
    mine = serializers.BooleanField()


class GroupMessageSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    author = ChatAuthorSerializer()
    body = serializers.CharField(allow_blank=True, help_text="Blank once deleted")
    deleted = serializers.BooleanField()
    removed = serializers.BooleanField(help_text="Taken down by an admin")
    mine = serializers.BooleanField()
    created_at = serializers.DateTimeField()
    reply_to = GroupReplySerializer(allow_null=True)
    reactions = GroupReactionCountSerializer(many=True)


class GroupMessagePageSerializer(serializers.Serializer):
    results = GroupMessageSerializer(many=True)
    older = serializers.CharField(allow_null=True, help_text="Cursor for earlier messages")


class GroupMessageQuerySerializer(StrictSerializer):
    cursor = serializers.CharField(required=False, default="", allow_blank=True)
    limit = serializers.IntegerField(required=False, default=50, min_value=1, max_value=100)


class GroupMessageCreateSerializer(StrictSerializer):
    body = serializers.CharField(max_length=MAX_MESSAGE * 2, trim_whitespace=False)
    reply_to = serializers.UUIDField(required=False, allow_null=True, default=None)


class GroupReactionSerializer(StrictSerializer):
    emoji = serializers.CharField(max_length=16)


class GroupReactionResultSerializer(serializers.Serializer):
    on = serializers.BooleanField(help_text="Whether your reaction is now there")
    reactions = GroupReactionCountSerializer(many=True)


class GroupMembershipSerializer(serializers.Serializer):
    joined = serializers.BooleanField()


# --- admin ---


class AdminChatGroupSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    name = serializers.CharField()
    description = serializers.CharField(allow_blank=True)
    emoji = serializers.CharField(allow_blank=True)
    sort = serializers.IntegerField()
    archived = serializers.BooleanField()
    member_count = serializers.IntegerField()
    message_count = serializers.IntegerField()
    last_activity_at = serializers.DateTimeField(allow_null=True)
    created_at = serializers.DateTimeField()


class AdminGroupWriteSerializer(StrictSerializer):
    name = serializers.CharField(max_length=60, required=False)
    description = serializers.CharField(max_length=300, required=False, allow_blank=True)
    emoji = serializers.CharField(max_length=16, required=False, allow_blank=True)
    sort = serializers.IntegerField(min_value=0, required=False)
    archived = serializers.BooleanField(required=False)
