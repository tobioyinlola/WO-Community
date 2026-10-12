from typing import Any

from rest_framework import serializers

from apps.core.serializers import StrictSerializer
from apps.core.text import plain
from apps.support import domain, selectors
from apps.support.models import SupportAttachment, SupportCannedReply, SupportMessage, SupportTicket
from apps.uploads import services as uploads

Category = serializers.ChoiceField(choices=domain.CATEGORIES)


def _words(value: str) -> str:
    return plain(value)


# --- input ---


class AttachmentIdsField(serializers.ListField):
    def __init__(self, **kwargs: Any) -> None:
        super().__init__(
            child=serializers.UUIDField(),
            required=False,
            max_length=domain.MAX_ATTACHMENTS,
            default=list,
            help_text=f"Ready `support_attachment` uploads, at most {domain.MAX_ATTACHMENTS}.",
            **kwargs,
        )


class TicketCreateSerializer(StrictSerializer):
    category = Category
    subject = serializers.CharField(min_length=domain.SUBJECT_MIN, max_length=domain.SUBJECT_MAX)
    message = serializers.CharField(
        min_length=domain.FIRST_MESSAGE_MIN, max_length=domain.MESSAGE_MAX, trim_whitespace=True
    )
    attachments = AttachmentIdsField()

    def validate_subject(self, value: str) -> str:
        cleaned = _words(value)
        if len(cleaned) < domain.SUBJECT_MIN:
            raise serializers.ValidationError(f"Use at least {domain.SUBJECT_MIN} characters.")
        return cleaned

    def validate_message(self, value: str) -> str:
        if len(_words(value)) < domain.FIRST_MESSAGE_MIN:
            raise serializers.ValidationError(
                f"Tell us a little more: use at least {domain.FIRST_MESSAGE_MIN} characters."
            )
        return value


class PublicContactSerializer(StrictSerializer):
    name = serializers.CharField(min_length=2, max_length=120, trim_whitespace=True)
    email = serializers.EmailField(max_length=254)
    subject = serializers.CharField(min_length=domain.SUBJECT_MIN, max_length=domain.SUBJECT_MAX)
    message = serializers.CharField(
        min_length=domain.FIRST_MESSAGE_MIN, max_length=domain.MESSAGE_MAX, trim_whitespace=True
    )
    # A field people never see. A bot that fills in every field fills this one too.
    website = serializers.CharField(required=False, allow_blank=True, max_length=200, default="")


class MessageCreateSerializer(StrictSerializer):
    message = serializers.CharField(
        min_length=1, max_length=domain.MESSAGE_MAX, trim_whitespace=True
    )
    attachments = AttachmentIdsField()

    def validate_message(self, value: str) -> str:
        if not _words(value):
            raise serializers.ValidationError("Write something first.")
        return value


class FeedbackSerializer(StrictSerializer):
    satisfaction = serializers.ChoiceField(choices=domain.SATISFACTION)
    comment = serializers.CharField(required=False, allow_blank=True, max_length=500, default="")


class AdminMessageSerializer(StrictSerializer):
    body = serializers.CharField(min_length=1, max_length=20_000, trim_whitespace=True)
    internal = serializers.BooleanField(required=False, default=False)
    status = serializers.ChoiceField(
        choices=("in_progress", "awaiting_member", "resolved"),
        required=False,
        default="awaiting_member",
        help_text="Where the request goes after this reply. Ignored for an internal note.",
    )
    attachments = AttachmentIdsField()


class AdminTicketUpdateSerializer(StrictSerializer):
    status = serializers.ChoiceField(choices=domain.STATUSES, required=False)
    assignee = serializers.UUIDField(required=False, allow_null=True)
    priority = serializers.ChoiceField(choices=domain.PRIORITIES, required=False)
    category = serializers.ChoiceField(choices=domain.CATEGORIES, required=False)


class AdminTicketQuerySerializer(StrictSerializer):
    q = serializers.CharField(required=False, allow_blank=True, max_length=100, default="")
    status = serializers.ChoiceField(
        choices=("open", *domain.STATUSES), required=False, allow_blank=True, default=""
    )
    category = serializers.ChoiceField(
        choices=domain.CATEGORIES, required=False, allow_blank=True, default=""
    )
    priority = serializers.ChoiceField(
        choices=domain.PRIORITIES, required=False, allow_blank=True, default=""
    )
    assignee = serializers.CharField(required=False, allow_blank=True, max_length=40, default="")
    created_after = serializers.DateField(required=False, allow_null=True, default=None)
    created_before = serializers.DateField(required=False, allow_null=True, default=None)
    ordering = serializers.ChoiceField(
        choices=selectors.ADMIN_ORDERINGS, required=False, default="-last_activity_at"
    )
    limit = serializers.IntegerField(required=False, min_value=1, max_value=100)
    offset = serializers.IntegerField(required=False, min_value=0)

    def validate_assignee(self, value: str) -> str:
        if value in ("", "me", "unassigned"):
            return value
        serializers.UUIDField().run_validation(value)
        return value


class CannedReplySerializer(StrictSerializer):
    title = serializers.CharField(min_length=2, max_length=80)
    body = serializers.CharField(min_length=1, max_length=4000)
    category = serializers.ChoiceField(
        choices=domain.CATEGORIES, required=False, allow_blank=True, default=""
    )
    active = serializers.BooleanField(required=False, default=True)


# --- output ---


class AuthorSerializer(serializers.Serializer):
    id = serializers.UUIDField(allow_null=True)
    name = serializers.CharField()
    is_support = serializers.BooleanField()
    avatar = serializers.DictField(allow_null=True)


class AttachmentSerializer(serializers.ModelSerializer):
    class Meta:
        model = SupportAttachment
        fields = ["id", "filename", "size", "content_type"]


class MessageSerializer(serializers.ModelSerializer):
    author = serializers.SerializerMethodField()
    attachments = AttachmentSerializer(many=True)

    class Meta:
        model = SupportMessage
        fields = ["id", "author", "body", "is_internal", "created_at", "attachments"]

    def get_author(self, obj: SupportMessage) -> dict[str, Any]:
        return dict(AuthorSerializer(selectors.author_card(obj)).data)


class TicketSerializer(serializers.ModelSerializer):
    reference = serializers.CharField()
    category_label = serializers.SerializerMethodField()
    status_label = serializers.SerializerMethodField()
    can_reopen = serializers.SerializerMethodField()

    class Meta:
        model = SupportTicket
        fields = [
            "id",
            "reference",
            "number",
            "subject",
            "category",
            "category_label",
            "status",
            "status_label",
            "created_at",
            "last_activity_at",
            "resolved_at",
            "can_reopen",
            "satisfaction",
            "satisfaction_comment",
        ]

    def get_category_label(self, obj: SupportTicket) -> str:
        return domain.CATEGORY_LABELS[obj.category]

    def get_status_label(self, obj: SupportTicket) -> str:
        return domain.STATUS_LABELS[obj.status]

    def get_can_reopen(self, obj: SupportTicket) -> bool:
        return selectors.can_reopen(obj)


class TicketDetailSerializer(TicketSerializer):
    messages = serializers.SerializerMethodField()

    class Meta(TicketSerializer.Meta):
        fields = [*TicketSerializer.Meta.fields, "messages"]

    def get_messages(self, obj: SupportTicket) -> list[dict[str, Any]]:
        rows = selectors.messages(obj, include_internal=False)
        return list(MessageSerializer(rows, many=True).data)


class PersonSerializer(serializers.Serializer):
    id = serializers.UUIDField(allow_null=True)
    name = serializers.CharField()
    email = serializers.CharField()
    avatar = serializers.DictField(allow_null=True)


def person(user: Any, fallback_name: str = "", fallback_email: str = "") -> dict[str, Any]:
    profile = getattr(user, "founder_profile", None) if user else None
    name = (profile.full_name if profile else "") or fallback_name
    return {
        "id": user.pk if user else None,
        "name": name or (user.email.split("@")[0] if user else "Unknown"),
        "email": user.email if user else fallback_email,
        "avatar": uploads.image_urls(profile.photo_key) if profile and profile.photo_key else None,
    }


class AdminTicketRowSerializer(TicketSerializer):
    priority = serializers.CharField()
    member = serializers.SerializerMethodField()
    assignee = serializers.SerializerMethodField()
    first_response_at = serializers.DateTimeField()
    is_overdue = serializers.SerializerMethodField()

    class Meta(TicketSerializer.Meta):
        fields = [
            *TicketSerializer.Meta.fields,
            "priority",
            "member",
            "assignee",
            "first_response_at",
            "is_overdue",
            "reopened_count",
        ]

    def get_member(self, obj: SupportTicket) -> dict[str, Any]:
        return dict(PersonSerializer(person(obj.member, obj.name, obj.email)).data)

    def get_assignee(self, obj: SupportTicket) -> dict[str, Any] | None:
        if obj.assignee is None:
            return None
        return dict(PersonSerializer(person(obj.assignee)).data)

    def get_is_overdue(self, obj: SupportTicket) -> bool:
        from datetime import timedelta

        from django.utils import timezone

        from apps.support import services

        return (
            obj.status == "open"
            and obj.first_response_at is None
            and timezone.now() - obj.created_at > timedelta(hours=services.sla_hours())
        )


class AdminTicketDetailSerializer(AdminTicketRowSerializer):
    messages = serializers.SerializerMethodField()
    previous_tickets = serializers.SerializerMethodField()
    member_joined_at = serializers.SerializerMethodField()

    class Meta(AdminTicketRowSerializer.Meta):
        fields = [
            *AdminTicketRowSerializer.Meta.fields,
            "messages",
            "previous_tickets",
            "member_joined_at",
        ]

    def get_messages(self, obj: SupportTicket) -> list[dict[str, Any]]:
        return list(
            MessageSerializer(selectors.messages(obj, include_internal=True), many=True).data
        )

    def get_previous_tickets(self, obj: SupportTicket) -> int:
        return selectors.previous_count(obj)

    def get_member_joined_at(self, obj: SupportTicket) -> Any:
        return obj.member.created_at if obj.member else None


class CountsSerializer(serializers.Serializer):
    open = serializers.IntegerField()
    in_progress = serializers.IntegerField()
    awaiting_member = serializers.IntegerField()
    resolved = serializers.IntegerField()
    resolved_this_week = serializers.IntegerField()
    working = serializers.IntegerField()
    total = serializers.IntegerField()


class StatsSerializer(serializers.Serializer):
    counts = CountsSerializer()
    median_first_response_seconds = serializers.IntegerField(allow_null=True)
    overdue = serializers.IntegerField()
    sla_hours = serializers.IntegerField()


class CannedReplyOutSerializer(serializers.ModelSerializer):
    class Meta:
        model = SupportCannedReply
        fields = ["id", "title", "body", "category", "active"]


class AttachmentLinkSerializer(serializers.Serializer):
    url = serializers.CharField()
    expires_in = serializers.IntegerField()


class TicketCreatedSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    reference = serializers.CharField()
