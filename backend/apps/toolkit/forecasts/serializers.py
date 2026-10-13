from rest_framework import serializers


class TkForecastDriverInfoSerializer(serializers.Serializer):
    name = serializers.CharField()
    label = serializers.CharField()  # type: ignore[assignment]
    help = serializers.CharField()
    kind = serializers.ChoiceField(choices=["count", "pct", "money"])
    default = serializers.FloatField()
    max = serializers.FloatField(allow_null=True)


class TkForecastTemplateSerializer(serializers.Serializer):
    template = serializers.CharField()
    label = serializers.CharField()  # type: ignore[assignment]
    help = serializers.CharField()
    drivers = TkForecastDriverInfoSerializer(many=True)


class TkForecastAssumptionsSerializer(serializers.Serializer):
    template = serializers.CharField()
    currency = serializers.CharField()
    opening_cash_minor = serializers.IntegerField(min_value=0, required=False)
    drivers = serializers.DictField()
    costs = serializers.DictField()
    funding = serializers.ListField(child=serializers.DictField(), required=False)
    tax_rate_pct = serializers.FloatField(required=False)
    market_customers = serializers.IntegerField(required=False, allow_null=True)


class TkForecastSerializer(serializers.Serializer):
    version = serializers.IntegerField()
    template = serializers.CharField()
    currency = serializers.CharField()
    assumptions = serializers.DictField()
    updated_at = serializers.DateTimeField()


class TkForecastCreateSerializer(serializers.Serializer):
    assumptions = TkForecastAssumptionsSerializer(
        required=False, help_text="Leave out to start from the venture profile."
    )


class TkForecastSaveSerializer(serializers.Serializer):
    assumptions = TkForecastAssumptionsSerializer()
    base_version = serializers.IntegerField(min_value=1)
    note = serializers.CharField(required=False, allow_blank=True, max_length=120)


class TkForecastMonthSerializer(serializers.Serializer):
    month = serializers.IntegerField()
    revenue = serializers.IntegerField()
    cogs = serializers.IntegerField()
    gross_profit = serializers.IntegerField()
    marketing = serializers.IntegerField()
    salaries = serializers.IntegerField()
    fixed = serializers.IntegerField()
    opex = serializers.IntegerField()
    ebitda = serializers.IntegerField()
    tax = serializers.IntegerField()
    net_income = serializers.IntegerField()
    funding = serializers.IntegerField()
    cash_end = serializers.IntegerField()
    kpis = serializers.DictField(child=serializers.IntegerField())


class TkForecastWarningSerializer(serializers.Serializer):
    code = serializers.CharField()
    severity = serializers.ChoiceField(choices=["warning", "error"])
    message = serializers.CharField()


class TkForecastResultSerializer(serializers.Serializer):
    scenario = serializers.ChoiceField(choices=["conservative", "base", "optimistic"])
    currency = serializers.CharField()
    version = serializers.IntegerField()
    months = TkForecastMonthSerializer(many=True)
    summary = serializers.DictField()
    unit_economics = serializers.DictField()
    warnings = TkForecastWarningSerializer(many=True)


class TkForecastScenariosSerializer(serializers.Serializer):
    currency = serializers.CharField()
    version = serializers.IntegerField()
    conservative = serializers.DictField()
    base = serializers.DictField()
    optimistic = serializers.DictField()


class TkForecastSensitivitySerializer(serializers.Serializer):
    assumption = serializers.CharField()
    value = serializers.FloatField()
    impact = serializers.IntegerField()
    down = serializers.DictField()
    up = serializers.DictField()


class TkForecastProposalSerializer(serializers.Serializer):
    name = serializers.CharField()
    value = serializers.FloatField()
    current = serializers.FloatField(allow_null=True)
    rationale = serializers.CharField()
    source_name = serializers.CharField(allow_blank=True)
    url = serializers.CharField()
    statement = serializers.CharField()


class TkForecastSuggestionSerializer(serializers.Serializer):
    proposals = TkForecastProposalSerializer(many=True)
    message = serializers.CharField(allow_blank=True)


class TkForecastExportSerializer(serializers.Serializer):
    format = serializers.ChoiceField(choices=["xlsx", "pdf"], default="xlsx")


class TkForecastVersionSerializer(serializers.Serializer):
    version = serializers.IntegerField()
    note = serializers.CharField(allow_blank=True)
    created_at = serializers.DateTimeField()
