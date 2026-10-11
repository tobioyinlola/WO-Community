from rest_framework import serializers

from apps.toolkit.sharing.models import SUBJECT_TYPES


class TkShareCreateSerializer(serializers.Serializer):
    subject_type = serializers.ChoiceField(choices=list(SUBJECT_TYPES))
    subject_id = serializers.UUIDField(
        help_text="The deck or prototype id; for the plan or score summary, the venture id."
    )
    password = serializers.CharField(required=False, allow_blank=True, max_length=72)
    expires_in_days = serializers.IntegerField(required=False, min_value=1, max_value=365)


class TkShareSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    subject_type = serializers.ChoiceField(choices=list(SUBJECT_TYPES))
    subject_id = serializers.UUIDField()
    has_password = serializers.BooleanField()
    expires_at = serializers.DateTimeField(allow_null=True)
    revoked_at = serializers.DateTimeField(allow_null=True)
    view_count = serializers.IntegerField()
    last_viewed_at = serializers.DateTimeField(allow_null=True)
    created_at = serializers.DateTimeField()


class TkShareCreatedSerializer(TkShareSerializer):
    token = serializers.CharField(help_text="Shown once; only a hash is kept")
    url = serializers.CharField(help_text="The page address to share")


class TkSharePasswordSerializer(serializers.Serializer):
    password = serializers.CharField(max_length=72)


class TkSharedContentSerializer(serializers.Serializer):
    type = serializers.ChoiceField(choices=["deck", "plan_summary", "score_summary"])
    title = serializers.CharField()
    venture_name = serializers.CharField(required=False)
    slides = serializers.ListField(child=serializers.DictField(), required=False)
    theme = serializers.DictField(required=False)
    sections = serializers.ListField(child=serializers.DictField(), required=False)
    overall_score = serializers.IntegerField(required=False, allow_null=True)
    verdict = serializers.CharField(required=False)
    dimensions = serializers.ListField(child=serializers.DictField(), required=False)
    strengths = serializers.ListField(child=serializers.CharField(), required=False)
    gaps = serializers.ListField(child=serializers.CharField(), required=False)
    disclaimer = serializers.CharField(required=False)
    generated_at = serializers.DateTimeField(required=False)
