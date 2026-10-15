from rest_framework import serializers

from apps.toolkit.jobs.serializers import TkJobSerializer


class TkAdvisorMessageSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    author = serializers.ChoiceField(choices=["user", "assistant"], help_text="Who wrote it")
    text = serializers.CharField()
    next_steps = serializers.ListField(child=serializers.CharField())
    frameworks = serializers.ListField(
        child=serializers.ChoiceField(choices=["yc", "techstars", "antler", "founder_institute"]),
        help_text="Which programmes' thinking the answer drew on",
    )
    declined = serializers.CharField(allow_null=True, help_text="legal, tax, investment, deception")
    created_at = serializers.DateTimeField()


class TkAdvisorConversationSerializer(serializers.Serializer):
    greeting = serializers.CharField(help_text="What Onyeka says before the first message")
    ai_enabled = serializers.BooleanField(help_text="Whether Onyeka can answer right now")
    messages = TkAdvisorMessageSerializer(many=True, help_text="The latest messages, oldest first")


class TkAdvisorSendSerializer(serializers.Serializer):
    text = serializers.CharField(max_length=2000)


class TkAdvisorReplySerializer(serializers.Serializer):
    user_message = TkAdvisorMessageSerializer()
    assistant_message = TkAdvisorMessageSerializer(allow_null=True)
    job = TkJobSerializer(
        allow_null=True,
        help_text="Present (with HTTP 202) when the reply is not ready yet: poll it, then read "
        "the conversation again",
    )


class TkAdvisorTranscribeSerializer(serializers.Serializer):
    audio = serializers.FileField(help_text="The recording, up to 4 MB")


class TkAdvisorTranscriptSerializer(serializers.Serializer):
    text = serializers.CharField(help_text="What was said")
