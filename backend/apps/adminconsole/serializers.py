from typing import Any

from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from apps.accounts import referrals, services
from apps.accounts.selectors import INVITATION_STATUSES, MEMBER_ORDERINGS, STATUSES
from apps.core.serializers import StrictSerializer


class MemberQuerySerializer(StrictSerializer):
    """Allow-listed filters for the members table."""

    q = serializers.CharField(required=False, allow_blank=True, max_length=100, default="")
    status = serializers.ChoiceField(choices=STATUSES, required=False, default="")
    role = serializers.CharField(required=False, max_length=30, default="")
    email_verified = serializers.BooleanField(required=False, allow_null=True, default=None)
    joined_after = serializers.DateField(required=False, default=None)
    joined_before = serializers.DateField(required=False, default=None)
    referral_source = serializers.CharField(
        required=False, allow_blank=True, max_length=12, default=""
    )
    referred_by = serializers.UUIDField(required=False, allow_null=True, default=None)
    ordering = serializers.ChoiceField(
        choices=MEMBER_ORDERINGS, required=False, default="-created_at"
    )
    limit = serializers.IntegerField(required=False, min_value=1, max_value=100)
    offset = serializers.IntegerField(required=False, min_value=0)

    def validate_referral_source(self, value: str) -> str:
        if value and value != "none" and value not in referrals.SOURCES:
            raise serializers.ValidationError("Choose one of the listed sources, or none.")
        return value


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


class ReferrerSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    name = serializers.CharField()


class MemberRowSerializer(MemberSerializer):
    """A member in the table: the account, plus what they gave on joining."""

    name = serializers.SerializerMethodField()
    country = serializers.SerializerMethodField()
    startup = serializers.SerializerMethodField()
    sector = serializers.SerializerMethodField()
    stage = serializers.SerializerMethodField()
    referral_source = serializers.SerializerMethodField()
    referral_label = serializers.SerializerMethodField()
    referral_detail = serializers.SerializerMethodField()
    referrer = serializers.SerializerMethodField()

    def _summary(self, obj: Any) -> dict[str, Any]:
        return self.context.get("summaries", {}).get(obj.pk, {})

    def get_name(self, obj: Any) -> str:
        return self._summary(obj).get("name", "")

    def get_country(self, obj: Any) -> str:
        return self._summary(obj).get("country", "")

    def get_startup(self, obj: Any) -> str:
        return self._summary(obj).get("startup", "")

    def get_sector(self, obj: Any) -> str:
        return self._summary(obj).get("sector", "")

    def get_stage(self, obj: Any) -> str:
        return self._summary(obj).get("stage", "")

    def get_referral_source(self, obj: Any) -> str:
        return str(obj.referral_source)

    def get_referral_label(self, obj: Any) -> str:
        return referrals.SOURCE_LABELS.get(obj.referral_source, "")

    def get_referral_detail(self, obj: Any) -> str:
        return str(obj.referral_detail)

    @extend_schema_field(ReferrerSerializer(allow_null=True))
    def get_referrer(self, obj: Any) -> dict[str, Any] | None:
        who = self._summary(obj).get("referrer")
        return who or None


class InvitationQuerySerializer(StrictSerializer):
    q = serializers.CharField(required=False, allow_blank=True, max_length=100, default="")
    status = serializers.ChoiceField(choices=INVITATION_STATUSES, required=False, default="")
    role = serializers.CharField(
        required=False,
        allow_blank=True,
        max_length=20,
        default="",
        help_text="A role, or `team` for every console role",
    )
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


class InvitationBatchSerializer(StrictSerializer):
    emails = serializers.ListField(
        child=serializers.CharField(max_length=254), min_length=1, max_length=200
    )
    role = serializers.CharField(required=False, default="member", max_length=30)
    message = serializers.CharField(
        required=False, allow_blank=True, default="", max_length=500, trim_whitespace=False
    )
    idempotency_key = serializers.CharField(max_length=80, help_text="One per submit.")


class InvitationCheckSerializer(StrictSerializer):
    emails = serializers.ListField(
        child=serializers.CharField(max_length=254), min_length=1, max_length=200
    )


class InvitationCheckRowSerializer(serializers.Serializer):
    email = serializers.CharField()
    state = serializers.ChoiceField(choices=["ok", "invalid", "member", "pending"])


class InvitationBatchRowSerializer(serializers.Serializer):
    email = serializers.CharField()
    result = serializers.ChoiceField(choices=["sent", "skipped", "failed"])
    reason = serializers.CharField(allow_blank=True)


class InvitationBatchResultSerializer(serializers.Serializer):
    sent = serializers.IntegerField()
    skipped = serializers.IntegerField()
    failed = serializers.IntegerField()
    results = InvitationBatchRowSerializer(many=True)


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
    wins_awaiting_review = serializers.IntegerField()
    support_unanswered = serializers.IntegerField()
    support_overdue = serializers.IntegerField()


class ApplicantProfileSerializer(serializers.Serializer):
    full_name = serializers.CharField()
    headline = serializers.CharField()
    country = serializers.CharField()
    city = serializers.CharField()
    website_url = serializers.CharField()
    linkedin_url = serializers.CharField()
    completeness = serializers.IntegerField()


class ApplicantStartupSerializer(serializers.Serializer):
    name = serializers.CharField()
    country = serializers.CharField()
    city = serializers.CharField()
    sector = serializers.CharField()
    stage = serializers.CharField()
    pitch = serializers.CharField()
    website_url = serializers.CharField()
    completeness = serializers.IntegerField()


class TimelineEntrySerializer(serializers.Serializer):
    kind = serializers.ChoiceField(
        choices=["registered", "email_verified", "decided", "last_signed_in"]
    )
    at = serializers.DateTimeField()
    note = serializers.CharField(allow_blank=True)


class ApplicantReferralSerializer(serializers.Serializer):
    kind = serializers.CharField(allow_blank=True)
    kind_label = serializers.CharField(allow_blank=True)
    detail = serializers.CharField(allow_blank=True)
    referrer = ReferrerSerializer(allow_null=True)
    code_used = serializers.CharField(allow_blank=True)


class ApplicationSerializer(serializers.Serializer):
    """What a person told us when they asked to join, for the admin deciding on them."""

    member = MemberSerializer()
    profile = ApplicantProfileSerializer(allow_null=True)
    startup = ApplicantStartupSerializer(allow_null=True)
    timeline = TimelineEntrySerializer(many=True)
    referral = ApplicantReferralSerializer()
