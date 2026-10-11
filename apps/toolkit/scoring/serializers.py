from rest_framework import serializers

from apps.toolkit.jobs.serializers import TkJobSerializer


class TkEvidenceSerializer(serializers.Serializer):
    kind = serializers.ChoiceField(choices=["profile", "fact"])
    text = serializers.CharField()
    ref = serializers.CharField(allow_blank=True)
    source_name = serializers.CharField(allow_blank=True)
    url = serializers.CharField(allow_blank=True)
    date = serializers.CharField(allow_blank=True)


class TkDimensionSerializer(serializers.Serializer):
    key = serializers.CharField()
    label = serializers.CharField()  # type: ignore[assignment]
    weight = serializers.IntegerField()
    score = serializers.IntegerField(allow_null=True)
    status = serializers.ChoiceField(choices=["scored", "insufficient_data"])
    reason = serializers.CharField(allow_blank=True)
    evidence = TkEvidenceSerializer(many=True)
    explanation = serializers.CharField()
    next_step = serializers.CharField()


class TkFindingSerializer(serializers.Serializer):
    dimension = serializers.CharField()
    label = serializers.CharField()  # type: ignore[assignment]
    score = serializers.IntegerField(allow_null=True)
    text = serializers.CharField()


class TkNextActionSerializer(serializers.Serializer):
    dimension = serializers.CharField()
    label = serializers.CharField()  # type: ignore[assignment]
    text = serializers.CharField()
    field = serializers.CharField()
    estimated_points = serializers.IntegerField(help_text="Roughly what it adds to the score.")
    action = serializers.DictField(
        help_text="{type: edit_profile|open_forecast|find_mentor, field}"
    )


class TkAssessmentSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    created_at = serializers.DateTimeField()
    overall_score = serializers.IntegerField(allow_null=True)
    verdict = serializers.CharField()
    rubric_version = serializers.IntegerField()
    profile_version = serializers.IntegerField()
    dimensions = TkDimensionSerializer(many=True)
    strengths = TkFindingSerializer(many=True)
    gaps = TkFindingSerializer(many=True)
    next_actions = TkNextActionSerializer(many=True)
    explanation = serializers.CharField()
    scored_weight = serializers.IntegerField()
    disclaimer = serializers.CharField()


class TkScoreHistoryItemSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    created_at = serializers.DateTimeField()
    overall_score = serializers.IntegerField(allow_null=True)
    verdict = serializers.CharField()
    rubric_version = serializers.IntegerField()


class TkScoreSummaryDimensionSerializer(serializers.Serializer):
    label = serializers.CharField()  # type: ignore[assignment]
    score = serializers.IntegerField(allow_null=True)
    status = serializers.CharField()


class TkScoreSummarySerializer(serializers.Serializer):
    venture_name = serializers.CharField()
    generated_at = serializers.DateTimeField()
    overall_score = serializers.IntegerField(allow_null=True)
    verdict = serializers.CharField()
    dimensions = TkScoreSummaryDimensionSerializer(many=True)
    strengths = serializers.ListField(child=serializers.CharField())
    gaps = serializers.ListField(child=serializers.CharField())
    disclaimer = serializers.CharField()


class TkJobStartedSerializer(TkJobSerializer):
    pass
