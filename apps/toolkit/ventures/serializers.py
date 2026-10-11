from rest_framework import serializers

from apps.core.serializers import StrictSerializer


class TkVentureCreateSerializer(StrictSerializer):
    name = serializers.CharField(max_length=80)
    from_startup_id = serializers.UUIDField(
        required=False, help_text="Copy from a startup profile you own or are on the team of."
    )


class TkVentureUpdateSerializer(StrictSerializer):
    name = serializers.CharField(max_length=80, required=False)
    archived = serializers.BooleanField(required=False)
    nudges_enabled = serializers.BooleanField(required=False)


class TkVentureSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    name = serializers.CharField()
    status = serializers.CharField()
    profile_completeness = serializers.IntegerField()
    imported_from_startup = serializers.UUIDField(allow_null=True)
    nudges_enabled = serializers.BooleanField()
    created_at = serializers.DateTimeField()
    updated_at = serializers.DateTimeField()
    deleted_at = serializers.DateTimeField(allow_null=True)


class TkVenturePageSerializer(serializers.Serializer):
    results = TkVentureSerializer(many=True)


class TkCompetitorSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    name = serializers.CharField()
    website = serializers.CharField(allow_blank=True)
    differentiator = serializers.CharField(allow_blank=True)


class TkTeamMemberSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    name = serializers.CharField()
    role = serializers.CharField()
    linkedin = serializers.CharField(allow_blank=True)
    is_founder = serializers.BooleanField()


class TkProfileSerializer(serializers.Serializer):
    version = serializers.IntegerField()
    fields = serializers.DictField(  # type: ignore[assignment]
        help_text="Validated profile fields; see the wizard steps."
    )
    field_meta = serializers.DictField(help_text="Where each value came from and when it changed.")
    completeness = serializers.IntegerField()
    missing_required = serializers.ListField(child=serializers.CharField())
    competitors = TkCompetitorSerializer(many=True)
    team = TkTeamMemberSerializer(many=True)


class TkOutputStateSerializer(serializers.Serializer):
    type = serializers.ChoiceField(choices=["score", "plan", "forecast", "deck", "prototype"])
    id = serializers.UUIDField(allow_null=True)
    status = serializers.ChoiceField(
        choices=["not_started", "generating", "ready", "needs_refresh", "failed"]
    )
    stale_fields = serializers.ListField(child=serializers.CharField())
    last_generated_at = serializers.DateTimeField(allow_null=True)


class TkProfileUpdateSerializer(StrictSerializer):
    fields = serializers.DictField(  # type: ignore[assignment]
        help_text="Only the fields that changed. Null or blank clears."
    )
    base_version = serializers.IntegerField(
        required=False, help_text="The version you loaded; a different one answers 409."
    )


class TkProfileUpdateResultSerializer(serializers.Serializer):
    profile = TkProfileSerializer()
    changed = serializers.ListField(child=serializers.CharField())
    outputs = TkOutputStateSerializer(many=True)


class TkImportStartupSerializer(StrictSerializer):
    startup_id = serializers.UUIDField()


class TkProfileVersionSerializer(serializers.Serializer):
    version = serializers.IntegerField()
    changed_fields = serializers.ListField(child=serializers.CharField())
    actor = serializers.CharField()
    created_at = serializers.DateTimeField()


class TkPackageSerializer(serializers.Serializer):
    venture = TkVentureSerializer()
    completeness = serializers.IntegerField()
    missing_required = serializers.ListField(child=serializers.CharField())
    ready_for_score = serializers.BooleanField()
    outputs = TkOutputStateSerializer(many=True)
    next_steps = serializers.ListField(child=serializers.CharField())


class TkCompetitorWriteSerializer(StrictSerializer):
    name = serializers.CharField(max_length=120)
    website = serializers.CharField(max_length=300, required=False, allow_blank=True)
    differentiator = serializers.CharField(max_length=500, required=False, allow_blank=True)


class TkCompetitorPatchSerializer(StrictSerializer):
    name = serializers.CharField(max_length=120, required=False)
    website = serializers.CharField(max_length=300, required=False, allow_blank=True)
    differentiator = serializers.CharField(max_length=500, required=False, allow_blank=True)


class TkTeamWriteSerializer(StrictSerializer):
    name = serializers.CharField(max_length=120)
    role = serializers.CharField(max_length=120)
    linkedin = serializers.CharField(max_length=300, required=False, allow_blank=True)
    is_founder = serializers.BooleanField(required=False)


class TkTeamPatchSerializer(StrictSerializer):
    name = serializers.CharField(max_length=120, required=False)
    role = serializers.CharField(max_length=120, required=False)
    linkedin = serializers.CharField(max_length=300, required=False, allow_blank=True)
    is_founder = serializers.BooleanField(required=False)
