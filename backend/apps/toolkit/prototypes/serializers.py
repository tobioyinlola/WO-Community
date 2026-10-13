from rest_framework import serializers


class TkPrototypeTemplateSerializer(serializers.Serializer):
    slug = serializers.CharField()
    name = serializers.CharField()
    description = serializers.CharField(allow_blank=True)
    screen_count = serializers.IntegerField()
    kind = serializers.ChoiceField(choices=["web", "mobile"])


class TkComponentSerializer(serializers.Serializer):
    name = serializers.CharField()
    label = serializers.CharField()  # type: ignore[assignment]
    category = serializers.CharField()
    children = serializers.BooleanField(help_text="Can hold other components")
    action = serializers.BooleanField(help_text="Can navigate between screens")
    props = serializers.DictField()


class TkPrototypeBriefSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    title = serializers.CharField()
    template_slug = serializers.CharField(allow_blank=True)
    kind = serializers.ChoiceField(choices=["web", "mobile"])
    version = serializers.IntegerField()
    screen_count = serializers.IntegerField()
    updated_at = serializers.DateTimeField()


class TkPrototypeSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    title = serializers.CharField()
    template_slug = serializers.CharField(allow_blank=True)
    version = serializers.IntegerField()
    spec = serializers.DictField(
        help_text="`{kind, theme, start, screens: [{id, name, root}]}`; a screen is a tree of "
        "registry components"
    )
    updated_at = serializers.DateTimeField()


class TkPrototypeCreateSerializer(serializers.Serializer):
    template = serializers.CharField(max_length=40)
    title = serializers.CharField(required=False, allow_blank=True, max_length=120)


class TkPrototypeGenerateSerializer(serializers.Serializer):
    kind = serializers.ChoiceField(choices=["web", "mobile"], default="web")
    brief = serializers.CharField(required=False, allow_blank=True, max_length=500)
    title = serializers.CharField(required=False, allow_blank=True, max_length=120)


class TkPrototypePatchSerializer(serializers.Serializer):
    base_version = serializers.IntegerField(min_value=1)
    ops = serializers.ListField(child=serializers.DictField(), max_length=200)
    label = serializers.CharField(  # type: ignore[assignment]
        required=False, allow_blank=True, max_length=80
    )


class TkPrototypeRenameSerializer(serializers.Serializer):
    title = serializers.CharField(max_length=120)


class TkPrototypeVersionSerializer(serializers.Serializer):
    version = serializers.IntegerField()
    label = serializers.CharField(allow_blank=True)  # type: ignore[assignment]
    created_at = serializers.DateTimeField()
