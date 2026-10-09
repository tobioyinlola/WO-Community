from typing import Any

from rest_framework import serializers


class StrictSerializer(serializers.Serializer):
    """Rejects fields the serializer does not declare.

    Silently ignoring unknown input hides client bugs and makes mass
    assignment mistakes easy to miss.
    """

    def to_internal_value(self, data: Any) -> Any:
        if isinstance(data, dict):
            unknown = set(data) - set(self.fields)
            if unknown:
                raise serializers.ValidationError(dict.fromkeys(sorted(unknown), "Unknown field."))
        return super().to_internal_value(data)


class StrictModelSerializer(serializers.ModelSerializer, StrictSerializer):
    pass
