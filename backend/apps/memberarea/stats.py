"""A member's own numbers for the dashboard: reach in the feed, learning, mentoring and events.

Counted from the source tables on each call; every query is an indexed count for one member.
"""

from datetime import timedelta
from typing import Any
from uuid import UUID

from django.db.models import Q
from django.utils import timezone

from apps.events.models import EventRegistration
from apps.feed.models import Comment, Follow, Post, Reaction
from apps.learning.models import Certificate, Enrolment
from apps.mentorship.models import MentorSession

TREND_DAYS = 30


def for_member(user_id: UUID) -> dict[str, Any]:
    now = timezone.now()
    since = now - timedelta(days=TREND_DAYS)

    followers = Follow.objects.filter(followee_type=Follow.Kind.MEMBER, followee_id=user_id)
    posts = Post.objects.filter(author_id=user_id, deleted_at__isnull=True)
    post_ids = posts.values("id")
    reactions = Reaction.objects.filter(target_type="post", target_id__in=post_ids).exclude(
        user_id=user_id
    )
    comments = Comment.objects.filter(post_id__in=post_ids, deleted_at__isnull=True).exclude(
        author_id=user_id
    )
    enrolments = Enrolment.objects.filter(user_id=user_id)
    sessions = MentorSession.objects.filter(Q(mentor_id=user_id) | Q(mentee_id=user_id))
    registrations = EventRegistration.objects.filter(user_id=user_id)

    return {
        "trend_days": TREND_DAYS,
        "followers": followers.count(),
        "followers_recent": followers.filter(created_at__gte=since).count(),
        "posts": posts.count(),
        "reactions_received": reactions.count(),
        "reactions_recent": reactions.filter(created_at__gte=since).count(),
        "comments_received": comments.count(),
        "comments_recent": comments.filter(created_at__gte=since).count(),
        "courses_in_progress": enrolments.filter(completed_at__isnull=True).count(),
        "courses_completed": enrolments.filter(completed_at__isnull=False).count(),
        "certificates": Certificate.objects.filter(
            enrolment__user_id=user_id, revoked_at__isnull=True
        ).count(),
        "sessions_completed": sessions.filter(status=MentorSession.Status.COMPLETED).count(),
        "sessions_upcoming": sessions.filter(
            status=MentorSession.Status.CONFIRMED, starts_at__gte=now
        ).count(),
        "events_attended": registrations.filter(checked_in_at__isnull=False).count(),
        "events_upcoming": registrations.filter(event__starts_at__gte=now).count(),
    }
