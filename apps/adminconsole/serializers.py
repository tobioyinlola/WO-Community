from typing import Any

from rest_framework import serializers

from apps.accounts import services
from apps.accounts.selectors import INVITATION_STATUSES, STATUSES
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


class InvitationQuerySerializer(StrictSerializer):
    q = serializers.CharField(required=False, allow_blank=True, max_length=100, default="")
    status = serializers.ChoiceField(choices=INVITATION_STATUSES, required=False, default="")
    limit = serializers.IntegerField(required=False, min_value=1, max_value=100)
    offset = serializers.IntegerField(required=False, min_value=0)


class InvitationCreateSerializer(StrictSerializer):
    email = serializers.EmailField(max_length=254)
    role = serializers.CharField(required=False, max_length=20, default="member")
    message = serializers.CharField(
        required=False, allow_blank=True, max_length=1000, default="", trim_whitespace=False
    )


class BulkInvitationSerializer(StrictSerializer):
    csv = serializers.CharField(max_length=300_000, trim_whitespace=False)


class InvitationSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    email = serializers.EmailField()
    role = serializers.CharField()
    message = serializers.CharField()
    status = serializers.SerializerMethodField()
    invited_by = serializers.UUIDField(source="invited_by_id", allow_null=True)
    created_at = serializers.DateTimeField()
    expires_at = serializers.DateTimeField()
    last_sent_at = serializers.DateTimeField()
    opened_at = serializers.DateTimeField()
    registered_at = serializers.DateTimeField()

    def get_status(self, obj: Any) -> str:
        return services.invitation_status(obj)


class BulkRowSerializer(serializers.Serializer):
    row = serializers.IntegerField()
    email = serializers.CharField(allow_blank=True)
    result = serializers.ChoiceField(choices=["created", "skipped"])
    reason = serializers.CharField(allow_blank=True)


class BulkReportSerializer(serializers.Serializer):
    created = serializers.IntegerField()
    skipped = serializers.IntegerField()
    rows = BulkRowSerializer(many=True)


class QueueCountsSerializer(serializers.Serializer):
    registrations_awaiting_approval = serializers.IntegerField()
    registrations_unverified = serializers.IntegerField()
    open_reports = serializers.IntegerField()
    jobs_awaiting_review = serializers.IntegerField()
