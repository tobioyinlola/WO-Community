from rest_framework import serializers

from apps.core.serializers import StrictSerializer


class TkSuggestSerializer(StrictSerializer):
    field = serializers.CharField(max_length=40)
    intent = serializers.CharField(
        max_length=500,
        required=False,
        allow_blank=True,
        default="",
        help_text="What you want, for example 'shorter' or 'more specific about farmers'.",
    )


class TkSuggestionsSerializer(serializers.Serializer):
    field = serializers.CharField()
    suggestions = serializers.ListField(child=serializers.CharField())


class TkFillFromTextSerializer(StrictSerializer):
    text = serializers.CharField(max_length=5000)


class TkProposedFieldsSerializer(serializers.Serializer):
    proposed = serializers.DictField(help_text="Valid values, ready to send to PATCH profile.")
    rejected = serializers.DictField(help_text="Fields the text suggested that did not validate.")
