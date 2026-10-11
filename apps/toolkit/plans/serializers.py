from rest_framework import serializers


class TkPlanSectionBriefSerializer(serializers.Serializer):
    number = serializers.IntegerField()
    chapter = serializers.CharField()
    title = serializers.CharField()
    status = serializers.ChoiceField(choices=["drafted", "needs_input", "edited", "needs_refresh"])
    stale = serializers.BooleanField()
    stale_fields = serializers.ListField(child=serializers.CharField())
    prompts = serializers.ListField(child=serializers.DictField())
    version = serializers.IntegerField()
    edited_by_member = serializers.BooleanField()
    word_count = serializers.IntegerField()
    updated_at = serializers.DateTimeField()


class TkPlanSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    version = serializers.IntegerField()
    status = serializers.ChoiceField(choices=["generating", "ready", "failed"])
    created_at = serializers.DateTimeField()
    updated_at = serializers.DateTimeField()
    sections = TkPlanSectionBriefSerializer(many=True)


class TkCitationSerializer(serializers.Serializer):
    number = serializers.IntegerField()
    claim_text = serializers.CharField()
    source_name = serializers.CharField(allow_blank=True)
    url = serializers.CharField()
    date = serializers.CharField()


class TkPlanSectionSerializer(TkPlanSectionBriefSerializer):
    guidance = serializers.CharField()
    content = serializers.DictField(
        help_text='`{"blocks": [...]}`: paragraph, heading, bullets or table blocks of plain '
        "text. `cites` on a block lists citation numbers."
    )
    citations = TkCitationSerializer(many=True)


class TkPlanGenerateSerializer(serializers.Serializer):
    sections = serializers.ListField(
        child=serializers.IntegerField(min_value=1, max_value=99),
        required=False,
        max_length=44,
        help_text="Rewrite only these sections. Leave out to write the whole plan.",
    )
    overwrite_edited = serializers.BooleanField(
        required=False,
        default=False,
        help_text="Also rewrite sections you edited yourself. Off by default.",
    )


class TkPlanSectionSaveSerializer(serializers.Serializer):
    content = serializers.DictField()
    base_version = serializers.IntegerField(
        min_value=1, help_text="The section version you loaded; a different one answers 409."
    )
    citations = serializers.ListField(
        child=serializers.DictField(),
        required=False,
        max_length=20,
        help_text="Sources that come with an accepted suggestion.",
    )


class TkPlanAssistSerializer(serializers.Serializer):
    action = serializers.ChoiceField(
        choices=[
            "shorten",
            "expand",
            "rewrite_for_investors",
            "simplify",
            "add_data",
            "localise",
        ]
    )
    country = serializers.CharField(required=False, allow_blank=True, max_length=60)


class TkPlanProposalSerializer(serializers.Serializer):
    action = serializers.CharField()
    content = serializers.DictField()
    citations = TkCitationSerializer(many=True)
    removed_figures = serializers.ListField(child=serializers.CharField())
    missing = serializers.ListField(child=serializers.DictField())


class TkPlanReadinessRowSerializer(serializers.Serializer):
    number = serializers.IntegerField()
    title = serializers.CharField()
    status = serializers.CharField()
    stale = serializers.BooleanField()
    problems = serializers.ListField(child=serializers.CharField())


class TkPlanReadinessSerializer(serializers.Serializer):
    ready = serializers.BooleanField()
    sections = TkPlanReadinessRowSerializer(many=True)
    blockers = serializers.ListField(child=serializers.CharField())


class TkPlanVersionSerializer(serializers.Serializer):
    version = serializers.IntegerField()
    label = serializers.CharField(allow_blank=True)  # type: ignore[assignment]
    created_at = serializers.DateTimeField()
