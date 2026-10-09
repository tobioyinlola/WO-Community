from rest_framework import serializers

from apps.accounts.selectors import STATUSES
from apps.core.serializers import StrictSerializer


class MemberQuerySerializer(StrictSerializer):
    """Allow-listed filters for the members table."""

    q = serializers.CharField(required=False, allow_blank=True, max_length=100, default="")
    status = serializers.ChoiceField(choices=STATUSES, required=False, default="")
    role = serializers.CharField(required=False, max_length=30, default="")
    email_verified = serializers.BooleanField(required=False, allow_null=True, default=None)
    joined_after = serializers.DateField(required=False, default=None)
    joined_before = serializers.DateField(required=False, default=None)
    limit = serializers.IntegerField(required=False, min_value=1, max_value=100)
    offset = serializers.IntegerField(required=False, min_value=0)


class ReasonSerializer(StrictSerializer):
    reason = serializers.CharField(max_length=1000, allow_blank=False, trim_whitespace=True)


class MemberSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    email = serializers.EmailField()
    status = serializers.CharField()
    roles = serializers.SerializerMethodField()
    email_verified_at = serializers.DateTimeField()
    approved_at = serializers.DateTimeField()
    approval_source = serializers.CharField()
    status_reason = serializers.CharField()
    status_changed_at = serializers.DateTimeField()
    last_login = serializers.DateTimeField()
    created_at = serializers.DateTimeField()

    def get_roles(self, obj: object) -> list[str]:
        return sorted(obj.role_names())  # type: ignore[attr-defined]


class QueueCountsSerializer(serializers.Serializer):
    registrations_awaiting_approval = serializers.IntegerField()
    registrations_unverified = serializers.IntegerField()
