from rest_framework import serializers

from apps.core.serializers import StrictSerializer


class TkAdminDeckTemplateSerializer(serializers.Serializer):
    slug = serializers.CharField()
    name = serializers.CharField()
    description = serializers.CharField(allow_blank=True)
    slides = serializers.ListField(child=serializers.DictField())
    position = serializers.IntegerField()
    active = serializers.BooleanField()


class TkAdminDeckTemplateWriteSerializer(StrictSerializer):
    slug = serializers.SlugField(max_length=40)
    name = serializers.CharField(max_length=80)
    description = serializers.CharField(required=False, allow_blank=True, max_length=300)
    slides = serializers.ListField(child=serializers.DictField(), max_length=40)
    position = serializers.IntegerField(required=False, min_value=0, max_value=999)
    active = serializers.BooleanField(default=True)


class TkAdminPrototypeTemplateSerializer(serializers.Serializer):
    slug = serializers.CharField()
    name = serializers.CharField()
    description = serializers.CharField(allow_blank=True)
    spec = serializers.DictField()
    active = serializers.BooleanField()


class TkAdminPrototypeTemplateWriteSerializer(StrictSerializer):
    slug = serializers.SlugField(max_length=40)
    name = serializers.CharField(max_length=80)
    description = serializers.CharField(required=False, allow_blank=True, max_length=300)
    spec = serializers.DictField()
    active = serializers.BooleanField(default=True)


class TkAdminPlanSectionSerializer(serializers.Serializer):
    number = serializers.IntegerField()
    chapter = serializers.CharField()
    title = serializers.CharField()
    guidance = serializers.CharField()
    depends_on = serializers.DictField()
    required_inputs = serializers.ListField(child=serializers.CharField())
    active = serializers.BooleanField()


class TkAdminPlanSectionWriteSerializer(StrictSerializer):
    chapter = serializers.CharField(required=False, max_length=80)
    title = serializers.CharField(required=False, max_length=120)
    guidance = serializers.CharField(required=False, max_length=2000)
    depends_on = serializers.DictField(required=False)
    required_inputs = serializers.ListField(
        child=serializers.CharField(max_length=40), required=False, max_length=12
    )
    active = serializers.BooleanField(required=False)


class TkAdminRubricSerializer(serializers.Serializer):
    version = serializers.IntegerField()
    active = serializers.BooleanField()
    notes = serializers.CharField(allow_blank=True)
    config = serializers.DictField()
    created_at = serializers.DateTimeField()


class TkAdminRubricWriteSerializer(StrictSerializer):
    config = serializers.DictField()
    notes = serializers.CharField(required=False, allow_blank=True, max_length=300)


class TkAdminUsageQuerySerializer(StrictSerializer):
    date_from = serializers.DateField(required=False, source="start")
    date_to = serializers.DateField(required=False, source="end")
    group_by = serializers.ChoiceField(choices=["day", "prompt", "agent"], default="day")


class TkAdminUsageRowSerializer(serializers.Serializer):
    key = serializers.CharField()
    runs = serializers.IntegerField()
    input_tokens = serializers.IntegerField()
    output_tokens = serializers.IntegerField()
    estimated_cost_minor = serializers.IntegerField()
    currency = serializers.CharField()
    outcomes = serializers.DictField(child=serializers.IntegerField())


class TkAdminQualitySerializer(serializers.Serializer):
    window_days = serializers.IntegerField()
    runs = serializers.IntegerField()
    not_ok = serializers.IntegerField()
    by_prompt = serializers.ListField(child=serializers.DictField())
    failed_jobs = serializers.ListField(child=serializers.DictField())
    recent = serializers.ListField(child=serializers.DictField())


class TkAdminSettingsSerializer(serializers.Serializer):
    features = serializers.DictField(child=serializers.BooleanField())
    ai_provider = serializers.CharField()
    ai_fallback_provider = serializers.CharField(allow_blank=True)
    ai_daily_run_ceiling = serializers.IntegerField()
    research_provider = serializers.CharField()
    research_domains = serializers.IntegerField()
    max_ventures_per_member = serializers.IntegerField()
    export_retention_days = serializers.IntegerField()
    venture_delete_grace_days = serializers.IntegerField()


class TkAdminVentureQuerySerializer(StrictSerializer):
    q = serializers.CharField(required=False, allow_blank=True, max_length=120, default="")
    include_deleted = serializers.BooleanField(required=False, default=False)
    limit = serializers.IntegerField(required=False, min_value=1, max_value=100)
    offset = serializers.IntegerField(required=False, min_value=0)


class TkAdminVentureSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    name = serializers.CharField()
    status = serializers.CharField()
    owner_id = serializers.UUIDField()
    owner_email = serializers.CharField()
    profile_completeness = serializers.IntegerField()
    latest_score = serializers.IntegerField(allow_null=True)
    scored_at = serializers.DateTimeField(allow_null=True)
    plans = serializers.IntegerField()
    has_forecast = serializers.BooleanField()
    decks = serializers.IntegerField()
    prototypes = serializers.IntegerField()
    partner_conversations = serializers.IntegerField()
    share_links = serializers.IntegerField()
    created_at = serializers.DateTimeField()
    updated_at = serializers.DateTimeField()


class TkAdminVentureTotalsSerializer(serializers.Serializer):
    ventures = serializers.IntegerField()
    founders = serializers.IntegerField()
    scored = serializers.IntegerField()
    with_plan = serializers.IntegerField()
    with_deck = serializers.IntegerField()


class TkAdminVenturePageSerializer(serializers.Serializer):
    count = serializers.IntegerField()
    next = serializers.CharField(allow_null=True)
    previous = serializers.CharField(allow_null=True)
    results = TkAdminVentureSerializer(many=True)
    totals = TkAdminVentureTotalsSerializer()
