from rest_framework import serializers

from apps.toolkit.jobs.serializers import TkJobSerializer


class TkChangeSerializer(serializers.Serializer):
    field = serializers.CharField()
    label = serializers.CharField()  # type: ignore[assignment]
    from_value = serializers.JSONField(source="from", allow_null=True)
    to_value = serializers.JSONField(source="to")
    reason = serializers.CharField(allow_blank=True)
    applied = serializers.BooleanField()


class TkChangeSetSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    status = serializers.ChoiceField(choices=["proposed", "applied", "undone", "dismissed"])
    changes = TkChangeSerializer(many=True)
    applied_at = serializers.DateTimeField(allow_null=True)
    undone_at = serializers.DateTimeField(allow_null=True)


class TkMessageSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    author = serializers.ChoiceField(choices=["user", "assistant"], help_text="Who wrote it")
    text = serializers.CharField()
    next_steps = serializers.ListField(child=serializers.CharField())
    mentor_topics = serializers.ListField(child=serializers.CharField())
    declined = serializers.CharField(allow_null=True, help_text="legal, tax, investment, deception")
    change_set = TkChangeSetSerializer(allow_null=True)
    created_at = serializers.DateTimeField()


class TkConversationSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    title = serializers.CharField(allow_blank=True)
    message_count = serializers.IntegerField()
    updated_at = serializers.DateTimeField()


class TkConversationDetailSerializer(TkConversationSerializer):
    messages = TkMessageSerializer(many=True)


class TkConversationCreateSerializer(serializers.Serializer):
    title = serializers.CharField(required=False, allow_blank=True, max_length=120)


class TkSendMessageSerializer(serializers.Serializer):
    text = serializers.CharField(max_length=2000)


class TkPartnerReplySerializer(serializers.Serializer):
    user_message = TkMessageSerializer()
    assistant_message = TkMessageSerializer(allow_null=True)
    job = TkJobSerializer(
        allow_null=True,
        help_text="Present (with HTTP 202) when the reply is not ready yet: poll it, then read "
        "the conversation",
    )


class TkChangeApplySerializer(serializers.Serializer):
    accept = serializers.ListField(
        child=serializers.CharField(max_length=60),
        required=False,
        max_length=6,
        help_text="Apply only these fields. Leave out to apply all.",
    )


class TkChangeUndoSerializer(serializers.Serializer):
    change_set = TkChangeSetSerializer()
    skipped = serializers.ListField(
        child=serializers.CharField(), help_text="Fields left alone because you changed them since"
    )


class TkDecisionSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    text = serializers.CharField()
    rationale = serializers.CharField(allow_blank=True)
    decided_on = serializers.DateField()
    created_at = serializers.DateTimeField()


class TkDecisionCreateSerializer(serializers.Serializer):
    text = serializers.CharField(min_length=3, max_length=300)
    rationale = serializers.CharField(required=False, allow_blank=True, max_length=1000)
    decided_on = serializers.DateField(required=False)


class TkNudgeSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    week_key = serializers.CharField()
    code = serializers.CharField()
    text = serializers.CharField()
    action = serializers.DictField()
    read_at = serializers.DateTimeField(allow_null=True)
    created_at = serializers.DateTimeField()


class TkMentorSuggestionSerializer(serializers.Serializer):
    topics = serializers.ListField(child=serializers.CharField())
    mentors = serializers.ListField(child=serializers.DictField())
