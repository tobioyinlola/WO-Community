from rest_framework import serializers


class TkDeckTemplateSerializer(serializers.Serializer):
    slug = serializers.CharField()
    name = serializers.CharField()
    description = serializers.CharField(allow_blank=True)
    slide_count = serializers.IntegerField()


class TkDeckBriefSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    title = serializers.CharField()
    template_slug = serializers.CharField(allow_blank=True)
    status = serializers.ChoiceField(choices=["draft", "ready"])
    version = serializers.IntegerField()
    slide_count = serializers.IntegerField()
    updated_at = serializers.DateTimeField()


class TkDeckSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    title = serializers.CharField()
    template_slug = serializers.CharField(allow_blank=True)
    status = serializers.ChoiceField(choices=["draft", "ready"])
    version = serializers.IntegerField()
    content = serializers.DictField(help_text='`{"slides": [...], "theme": {...}}`')
    updated_at = serializers.DateTimeField()


class TkDeckShownSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    title = serializers.CharField()
    version = serializers.IntegerField()
    slides = serializers.ListField(child=serializers.DictField())
    theme = serializers.DictField()


class TkDeckCreateSerializer(serializers.Serializer):
    template = serializers.CharField(max_length=40)
    title = serializers.CharField(required=False, allow_blank=True, max_length=120)


class TkDeckUpdateSerializer(serializers.Serializer):
    title = serializers.CharField(required=False, max_length=120)
    status = serializers.ChoiceField(choices=["draft", "ready"], required=False)


class TkDeckPatchSerializer(serializers.Serializer):
    base_version = serializers.IntegerField(min_value=1)
    ops = serializers.ListField(
        child=serializers.DictField(),
        max_length=200,
        help_text="add, remove, replace, move on /slides/... or /theme/...",
    )
    label = serializers.CharField(  # type: ignore[assignment]
        required=False, allow_blank=True, max_length=80
    )


class TkDeckVersionSerializer(serializers.Serializer):
    version = serializers.IntegerField()
    label = serializers.CharField(allow_blank=True)  # type: ignore[assignment]
    created_at = serializers.DateTimeField()


class TkDeckFindingSerializer(serializers.Serializer):
    slide = serializers.IntegerField(help_text="1 based; 0 for the whole deck")
    element = serializers.CharField(allow_blank=True)
    code = serializers.CharField()
    severity = serializers.ChoiceField(choices=["error", "warning", "info"])
    message = serializers.CharField()


class TkDeckAssetSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    filename = serializers.CharField(allow_blank=True)
    width = serializers.IntegerField()
    height = serializers.IntegerField()
    size = serializers.IntegerField()
    url = serializers.CharField(help_text="A signed link that expires quickly")


class TkDeckAssetUploadSerializer(serializers.Serializer):
    file = serializers.FileField()


class TkDeckAssistSerializer(serializers.Serializer):
    slide_id = serializers.CharField(max_length=16)
    action = serializers.ChoiceField(choices=["shorten", "punchier", "simplify"])


class TkDeckAssistResultSerializer(serializers.Serializer):
    slide_id = serializers.CharField()
    action = serializers.CharField()
    elements = serializers.ListField(child=serializers.DictField())
    removed = serializers.ListField(child=serializers.CharField())


class TkDeckExportSerializer(serializers.Serializer):
    format = serializers.ChoiceField(choices=["pptx", "pdf"], default="pptx")
