from rest_framework import serializers

from apps.core.serializers import ImageSerializer, StrictSerializer
from apps.mentorship.models import SESSION_STATUSES
from apps.mentorship.session_selectors import FILTERS


class SessionRequestSerializer(StrictSerializer):
    mentor_id = serializers.UUIDField(help_text="The member id of the mentor.")
    starts_at = serializers.DateTimeField(
        help_text="One of the start times from `GET /mentors/{id}/availability`."
    )
    length_minutes = serializers.IntegerField(
        min_value=30,
        max_value=60,
        required=False,
        help_text="One of the lengths the mentor offers; their usual length when left out.",
    )
    topic = serializers.CharField(max_length=120, help_text="What you want help with.")
    message = serializers.CharField(
        max_length=1000, help_text="20 to 1000 characters introducing yourself and your goal."
    )


class SessionReasonSerializer(StrictSerializer):
    reason = serializers.CharField(max_length=1000)


class SessionOptionalReasonSerializer(StrictSerializer):
    reason = serializers.CharField(max_length=1000, required=False, allow_blank=True, default="")


class RescheduleSerializer(StrictSerializer):
    starts_at = serializers.DateTimeField(help_text="One of the mentor's bookable start times.")
    note = serializers.CharField(max_length=500, required=False, allow_blank=True, default="")


class MeetingLinkSerializer(StrictSerializer):
    url = serializers.CharField(max_length=300, help_text="An https link to your own meeting.")


class SessionFeedbackSerializer(StrictSerializer):
    stars = serializers.IntegerField(
        min_value=1, max_value=5, required=False, help_text="Founders: 1 to 5."
    )
    comment = serializers.CharField(max_length=1000, required=False, allow_blank=True, default="")
    outcome = serializers.ChoiceField(
        choices=["held", "mentor_no_show", "mentee_no_show"],
        default="held",
        help_text="Founders: `held` or `mentor_no_show`. Mentors: `held` or `mentee_no_show`.",
    )


class SessionPartySerializer(serializers.Serializer):
    id = serializers.UUIDField()
    name = serializers.CharField()
    headline = serializers.CharField()
    photo = ImageSerializer(allow_null=True)
    slug = serializers.CharField(allow_null=True)


class SessionMeetingSerializer(serializers.Serializer):
    provider = serializers.CharField(help_text="google_meet, zoom, manual or blank.")
    state = serializers.ChoiceField(choices=["", "pending", "ready", "failed"])
    url = serializers.CharField(help_text="Blank until the meeting is ready.")


class SessionProposalSerializer(serializers.Serializer):
    starts_at = serializers.DateTimeField()
    ends_at = serializers.DateTimeField()
    proposed_by = serializers.UUIDField(allow_null=True)
    note = serializers.CharField()
    by_me = serializers.BooleanField()


class FeedbackItemSerializer(serializers.Serializer):
    stars = serializers.IntegerField(allow_null=True)
    comment = serializers.CharField()
    outcome = serializers.CharField()
    updated_at = serializers.DateTimeField()


class SessionFeedbackViewSerializer(serializers.Serializer):
    mine = FeedbackItemSerializer(allow_null=True)
    from_mentee = FeedbackItemSerializer(
        allow_null=True, help_text="Shown to the mentor and admins only."
    )
    from_mentor = FeedbackItemSerializer(allow_null=True, help_text="Shown to admins only.")
    can_give = serializers.BooleanField()
    closes_at = serializers.DateTimeField(allow_null=True)


class SessionActionsSerializer(serializers.Serializer):
    accept = serializers.BooleanField()
    decline = serializers.BooleanField()
    cancel = serializers.BooleanField()
    reschedule = serializers.BooleanField()
    answer_reschedule = serializers.BooleanField()
    add_link = serializers.BooleanField()


class SessionPriceSerializer(serializers.Serializer):
    price_minor = serializers.IntegerField(help_text="In the smallest unit (kobo, cents)")
    currency = serializers.CharField()
    payment = serializers.CharField(
        help_text='"arranged": payment is settled directly between mentor and mentee.'
    )


class MentoringSessionSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    status = serializers.ChoiceField(choices=SESSION_STATUSES)
    role = serializers.ChoiceField(choices=["mentor", "mentee", "admin"])
    starts_at = serializers.DateTimeField()
    ends_at = serializers.DateTimeField()
    topic = serializers.CharField()
    message = serializers.CharField()
    length_minutes = serializers.IntegerField()
    price = SessionPriceSerializer(allow_null=True)
    mentor = SessionPartySerializer()
    mentee = SessionPartySerializer()
    meeting = SessionMeetingSerializer()
    proposal = SessionProposalSerializer(allow_null=True)
    reschedule_count = serializers.IntegerField()
    reason = serializers.CharField(help_text="Why it was declined or cancelled.")
    cancelled_by = serializers.UUIDField(allow_null=True)
    late_cancel = serializers.BooleanField()
    created_at = serializers.DateTimeField()
    responded_at = serializers.DateTimeField(allow_null=True)
    confirmed_at = serializers.DateTimeField(allow_null=True)
    feedback = SessionFeedbackViewSerializer()
    actions = SessionActionsSerializer()


class MentoringSessionPageSerializer(serializers.Serializer):
    results = MentoringSessionSerializer(many=True)
    next_cursor = serializers.CharField(allow_null=True)


class SessionQuerySerializer(serializers.Serializer):
    role = serializers.ChoiceField(choices=["mentor", "mentee"], required=False)
    state = serializers.ChoiceField(
        choices=list(FILTERS),
        default="upcoming",
        help_text="`upcoming` confirmed and not yet over, `pending` waiting for an answer, "
        "`past` held or missed, `closed` declined, cancelled or lapsed.",
    )
    cursor = serializers.CharField(required=False, allow_blank=True, default="")
    limit = serializers.IntegerField(min_value=1, max_value=50, default=20)


class AdminMentoringSessionSerializer(MentoringSessionSerializer):
    mentor_email = serializers.CharField()
    mentee_email = serializers.CharField()


class AdminSessionQuerySerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=list(SESSION_STATUSES), required=False)
    mentor_id = serializers.UUIDField(required=False)
    mentee_id = serializers.UUIDField(required=False)
    limit = serializers.IntegerField(min_value=1, max_value=100, required=False)
    offset = serializers.IntegerField(min_value=0, required=False)
