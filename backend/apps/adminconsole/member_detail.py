"""One member in full, for the drawer in Admin > Members.

Each section is read with a handful of queries for the whole page, never one per row.
"""

from typing import Any

from django.db.models import Q
from rest_framework import serializers

from apps.accounts.models import User
from apps.audit.models import AuditLog
from apps.events.models import EventRegistration
from apps.feed.models import Comment, Post
from apps.jobs.models import Job
from apps.learning.models import Certificate, Enrolment
from apps.mentorship.models import MentorProfile, MentorSession, MentorSettings
from apps.profiles.models import FounderProfile
from apps.startups.models import Startup
from apps.support.models import SupportTicket

OPEN_TICKET = ("open", "pending", "new")


class PersonRefSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    name = serializers.CharField()


class ProfileSectionSerializer(serializers.Serializer):
    full_name = serializers.CharField()
    headline = serializers.CharField()
    bio = serializers.CharField()
    country = serializers.CharField()
    city = serializers.CharField()
    website_url = serializers.CharField()
    linkedin_url = serializers.CharField()
    x_url = serializers.CharField()
    skills = serializers.ListField(child=serializers.CharField())
    open_to = serializers.ListField(child=serializers.CharField())
    completeness = serializers.IntegerField()
    startup_name = serializers.CharField()
    industry = serializers.CharField()
    stage = serializers.CharField()
    pitch = serializers.CharField()


class AccountSectionSerializer(serializers.Serializer):
    invited_by = PersonRefSerializer(allow_null=True)
    referred_by = PersonRefSerializer(allow_null=True)
    approved_by = PersonRefSerializer(allow_null=True)


class ActivitySectionSerializer(serializers.Serializer):
    posts = serializers.IntegerField()
    comments = serializers.IntegerField()
    events_attended = serializers.IntegerField()
    jobs_posted = serializers.IntegerField()


class CertificateRefSerializer(serializers.Serializer):
    number = serializers.CharField()
    course_title = serializers.CharField()
    issued_at = serializers.DateTimeField()
    revoked = serializers.BooleanField()


class LearningSectionSerializer(serializers.Serializer):
    courses_started = serializers.IntegerField()
    courses_completed = serializers.IntegerField()
    certificates = CertificateRefSerializer(many=True)


class MentorshipSectionSerializer(serializers.Serializer):
    status = serializers.CharField()
    paused = serializers.BooleanField()
    capacity_per_week = serializers.IntegerField()
    session_minutes = serializers.IntegerField()
    default_price_minor = serializers.IntegerField(allow_null=True)
    sessions_as_mentor = serializers.IntegerField()
    sessions_as_mentee = serializers.IntegerField()


class TicketRefSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    number = serializers.IntegerField()
    subject = serializers.CharField()
    status = serializers.CharField()


class AuditRefSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    created_at = serializers.DateTimeField()
    action = serializers.CharField()
    outcome = serializers.CharField()


class MemberFullSerializer(serializers.Serializer):
    """The member row's account fields plus every section the drawer shows."""

    id = serializers.UUIDField()
    email = serializers.EmailField()
    status = serializers.CharField()
    roles = serializers.ListField(child=serializers.CharField())
    email_verified_at = serializers.DateTimeField(allow_null=True)
    approved_at = serializers.DateTimeField(allow_null=True)
    approval_source = serializers.CharField()
    status_reason = serializers.CharField()
    status_changed_at = serializers.DateTimeField(allow_null=True)
    last_login = serializers.DateTimeField(allow_null=True)
    created_at = serializers.DateTimeField()
    name = serializers.CharField()
    profile = ProfileSectionSerializer()
    account = AccountSectionSerializer()
    activity = ActivitySectionSerializer()
    learning = LearningSectionSerializer()
    mentorship = MentorshipSectionSerializer(allow_null=True)
    open_tickets = TicketRefSerializer(many=True)
    audit = AuditRefSerializer(many=True)


def _ref(user_id: Any, names: dict[Any, str]) -> dict[str, Any] | None:
    return {"id": user_id, "name": names[user_id]} if user_id and user_id in names else None


def build(user: User) -> dict[str, Any]:
    profile = FounderProfile.objects.filter(user_id=user.pk).first()
    startup = (
        Startup.objects.filter(owner_id=user.pk)
        .select_related("sector", "stage")
        .order_by("created_at")
        .first()
    )
    related_ids = {user.approved_by_id, user.referred_by_id, _invited_by(user)} - {None}
    emails = dict(User.objects.filter(pk__in=related_ids).values_list("pk", "email"))
    full = dict(
        FounderProfile.objects.filter(user_id__in=related_ids).values_list("user_id", "full_name")
    )
    names = {i: full.get(i) or emails.get(i, "").split("@")[0] for i in emails}

    enrolments = Enrolment.objects.filter(user_id=user.pk)
    certificates = Certificate.objects.filter(enrolment__user_id=user.pk).order_by("-issued_at")[
        :10
    ]
    mentor = MentorProfile.objects.filter(user_id=user.pk).first()
    prices = MentorSettings.objects.filter(user_id=user.pk).first() if mentor else None
    audit_rows = AuditLog.objects.filter(Q(target_type="user", target_id=str(user.pk))).order_by(
        "-created_at", "-seq"
    )[:10]

    return {
        "id": user.pk,
        "email": user.email,
        "status": user.status,
        "roles": sorted(user.role_names()),
        "email_verified_at": user.email_verified_at,
        "approved_at": user.approved_at,
        "approval_source": user.approval_source,
        "status_reason": user.status_reason,
        "status_changed_at": user.status_changed_at,
        "last_login": user.last_login,
        "created_at": user.created_at,
        "name": (profile.full_name if profile else "") or user.email,
        "profile": {
            "full_name": profile.full_name if profile else "",
            "headline": profile.headline if profile else "",
            "bio": profile.bio if profile else "",
            "country": profile.country if profile else "",
            "city": profile.city if profile else "",
            "website_url": profile.website_url if profile else "",
            "linkedin_url": profile.linkedin_url if profile else "",
            "x_url": profile.x_url if profile else "",
            "skills": (
                list(profile.skills.values_list("name", flat=True)) + list(profile.custom_skills)
                if profile
                else []
            ),
            "open_to": list(profile.open_to) if profile else [],
            "completeness": profile.completeness_score if profile else 0,
            "startup_name": startup.name if startup else "",
            "industry": startup.sector.name if startup else "",
            "stage": startup.stage.name if startup else "",
            "pitch": startup.pitch if startup else "",
        },
        "account": {
            "invited_by": _ref(_invited_by(user), names),
            "referred_by": _ref(user.referred_by_id, names),
            "approved_by": _ref(user.approved_by_id, names),
        },
        "activity": {
            "posts": Post.objects.filter(author_id=user.pk).count(),
            "comments": Comment.objects.filter(author_id=user.pk).count(),
            "events_attended": EventRegistration.objects.filter(
                user_id=user.pk, checked_in_at__isnull=False
            ).count(),
            "jobs_posted": Job.objects.filter(poster_id=user.pk).count(),
        },
        "learning": {
            "courses_started": enrolments.count(),
            "courses_completed": enrolments.filter(completed_at__isnull=False).count(),
            "certificates": [
                {
                    "number": c.code,
                    "course_title": c.course_title,
                    "issued_at": c.issued_at,
                    "revoked": c.revoked_at is not None,
                }
                for c in certificates
            ],
        },
        "mentorship": (
            {
                "status": mentor.status,
                "paused": mentor.paused,
                "capacity_per_week": mentor.capacity_per_week,
                "session_minutes": mentor.session_minutes,
                "default_price_minor": prices.default_price_minor if prices else None,
                "sessions_as_mentor": MentorSession.objects.filter(mentor_id=user.pk).count(),
                "sessions_as_mentee": MentorSession.objects.filter(mentee_id=user.pk).count(),
            }
            if mentor
            else None
        ),
        "open_tickets": [
            {"id": t.pk, "number": t.number, "subject": t.subject, "status": t.status}
            for t in SupportTicket.objects.filter(member_id=user.pk)
            .exclude(status__in=("resolved", "closed"))
            .order_by("-last_activity_at")[:5]
        ],
        "audit": [
            {"id": a.id, "created_at": a.created_at, "action": a.action, "outcome": a.outcome}
            for a in audit_rows
        ],
    }


def _invited_by(user: User) -> Any:
    from apps.accounts.models import Invitation

    return (
        Invitation.objects.filter(accepted_by_id=user.pk)
        .values_list("invited_by_id", flat=True)
        .first()
    )
