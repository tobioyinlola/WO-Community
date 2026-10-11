"""Read side of mentorship: the directory, views of mentors and applications, admin lists."""

from typing import Any
from uuid import UUID

from django.db.models import Q, QuerySet
from rest_framework import exceptions

from apps.accounts import services as accounts
from apps.core.keyset import paginate
from apps.mentorship.domain import LANGUAGES
from apps.mentorship.models import MentorApplication, MentorInterest, MentorProfile
from apps.profiles import selectors as profiles
from apps.reference import selectors as reference


def listed() -> QuerySet[MentorProfile]:
    """Mentors who can be found: active, not paused, account still an active member."""
    return MentorProfile.objects.filter(
        status=MentorProfile.Status.ACTIVE,
        paused=False,
        user_id__in=accounts.active_user_ids(),
    )


def filter_mentors(
    queryset: QuerySet[MentorProfile],
    *,
    q: str = "",
    expertise: str = "",
    industry: str = "",
    stage: str = "",
    country: str = "",
    language: str = "",
    available: bool = False,
) -> QuerySet[MentorProfile]:
    if expertise:
        queryset = queryset.filter(expertise__contains=[" ".join(expertise.lower().split())])
    if industry:
        queryset = queryset.filter(industries__contains=[industry])
    if stage:
        queryset = queryset.filter(stages__contains=[stage])
    if language:
        queryset = queryset.filter(languages__contains=[language])
    if country:
        queryset = queryset.filter(user_id__in=profiles.ids_by_country([country]))
    if available:
        from apps.mentorship import scheduling

        queryset = queryset.filter(
            user_id__in=scheduling.has_availability(queryset.values_list("user_id", flat=True))
        )
    if q:
        needle = " ".join(q.lower().split())
        queryset = queryset.filter(
            Q(user_id__in=profiles.ids_by_name(q))
            | Q(current_role__icontains=q)
            | Q(company__icontains=q)
            | Q(expertise__contains=[needle])
        )
    return queryset


def _names(table: Any) -> dict[str, str]:
    return {row.slug: row.name for row in table}


def views(viewer: Any, rows: list[MentorProfile]) -> list[dict[str, Any]]:
    cards = profiles.cards_for(viewer, [r.user_id for r in rows])
    sectors, stages = _names(reference.sectors()), _names(reference.stages())
    out = []
    for row in rows:
        card = cards[row.user_id]
        out.append(
            {
                "id": row.user_id,
                "name": card["name"],
                "headline": card["headline"],
                "photo": card["photo"],
                "slug": card["slug"],
                "about": row.about,
                "expertise": row.expertise,
                "years_experience": row.years_experience,
                "current_role": row.current_role,
                "company": row.company,
                "industries": [{"slug": s, "name": sectors.get(s, s)} for s in row.industries],
                "stages": [{"slug": s, "name": stages.get(s, s)} for s in row.stages],
                "languages": [{"code": c, "name": LANGUAGES.get(c, c)} for c in row.languages],
                "timezone": row.timezone,
                "capacity_per_week": row.capacity_per_week,
                "session_minutes": row.session_minutes,
                "paused": row.paused,
                "rating_average": (
                    round(row.rating_total / row.rating_count, 2) if row.rating_count else None
                ),
                "rating_count": row.rating_count,
            }
        )
    return out


def directory(viewer: Any, *, cursor: str, limit: int, **filters: Any) -> dict[str, Any]:
    queryset = filter_mentors(listed(), **filters)
    rows, next_cursor = paginate(
        queryset, fields=("approved_at", "id"), sort="mentors", cursor=cursor, limit=limit
    )
    return {"results": views(viewer, rows), "next_cursor": next_cursor}


def detail(viewer: Any, user_id: UUID) -> dict[str, Any]:
    """A mentor page. A mentor sees their own while paused; others see it only while listed."""
    profile = MentorProfile.objects.filter(
        user_id=user_id, status=MentorProfile.Status.ACTIVE
    ).first()
    if profile is None:
        raise exceptions.NotFound()
    if profile.user_id != viewer.pk and not listed().filter(pk=profile.pk).exists():
        raise exceptions.NotFound()
    return views(viewer, [profile])[0]


def own_view(viewer: Any) -> dict[str, Any] | None:
    profile = MentorProfile.objects.filter(user_id=viewer.pk).first()
    return views(viewer, [profile])[0] if profile else None


# --- applications ---


def application_view(application: MentorApplication) -> dict[str, Any]:
    sectors, stages = _names(reference.sectors()), _names(reference.stages())
    return {
        "id": application.pk,
        "status": application.status,
        "expertise": application.expertise,
        "years_experience": application.years_experience,
        "current_role": application.current_role,
        "company": application.company,
        "linkedin_url": application.linkedin_url,
        "industries": [{"slug": s, "name": sectors.get(s, s)} for s in application.industries],
        "stages": [{"slug": s, "name": stages.get(s, s)} for s in application.stages],
        "languages": [{"code": c, "name": LANGUAGES.get(c, c)} for c in application.languages],
        "timezone": application.timezone,
        "weekly_hours": application.weekly_hours,
        "availability_note": application.availability_note,
        "motivation": application.motivation,
        "decision_reason": application.decision_reason,
        "decided_at": application.decided_at,
        "created_at": application.created_at,
    }


def admin_applications(*, status: str = "", q: str = "") -> QuerySet[MentorApplication]:
    queryset = MentorApplication.objects.all()
    if status:
        queryset = queryset.filter(status=status)
    if q:
        queryset = queryset.filter(applicant_id__in=profiles.ids_by_name(q))
    return queryset.order_by("created_at", "id")  # oldest waiting first


def admin_application_views(viewer: Any, rows: list[MentorApplication]) -> list[dict[str, Any]]:
    emails = accounts.emails_for([r.applicant_id for r in rows])
    return [
        {
            **application_view(row),
            "applicant": {
                "id": row.applicant_id,
                "name": profiles.full_name_of(row.applicant_id) or "Community member",
                "email": emails.get(row.applicant_id, ""),
            },
            "decided_by": row.decided_by_id,
        }
        for row in rows
    ]


def admin_mentor_views(viewer: Any, rows: list[MentorProfile]) -> list[dict[str, Any]]:
    return [
        {
            **view,
            "status": row.status,
            "revoke_reason": row.revoke_reason,
            "approved_at": row.approved_at,
        }
        for view, row in zip(views(viewer, rows), rows, strict=True)
    ]


def admin_mentors(*, status: str = "", q: str = "") -> QuerySet[MentorProfile]:
    queryset = MentorProfile.objects.all()
    if status:
        queryset = queryset.filter(status=status)
    if q:
        queryset = queryset.filter(user_id__in=profiles.ids_by_name(q))
    return queryset.order_by("-approved_at", "id")


# --- for segments and dashboards ---


def applicant_ids() -> set[UUID]:
    return set(MentorApplication.objects.values_list("applicant_id", flat=True))


def mentor_ids() -> set[UUID]:
    return set(
        MentorProfile.objects.filter(status=MentorProfile.Status.ACTIVE).values_list(
            "user_id", flat=True
        )
    )


def snapshot() -> dict[str, int]:
    return {
        "pending_applications": MentorApplication.objects.filter(
            status=MentorApplication.Status.PENDING
        ).count(),
        "active_mentors": MentorProfile.objects.filter(status=MentorProfile.Status.ACTIVE).count(),
        "listed_mentors": listed().count(),
    }


def mentoring_summary(user_id: UUID) -> dict[str, Any]:
    """Where the member stands as a mentor, and whether to prompt them to apply."""
    from apps.mentorship.applications import REAPPLY_AFTER

    is_mentor = accounts.has_role(user_id, "mentor")
    latest = MentorApplication.objects.filter(applicant_id=user_id).order_by("-created_at").first()
    status = latest.status if latest else None
    can_apply_after = None
    if latest and latest.status == MentorApplication.Status.DECLINED and latest.decided_at:
        can_apply_after = latest.decided_at + REAPPLY_AFTER
    waiting = status in ("pending", "info_requested")
    interested = MentorInterest.objects.filter(user_id=user_id).exists()
    return {
        "is_mentor": is_mentor,
        "application_id": latest.pk if latest else None,
        "application_status": status,
        "interested": interested,
        "can_apply": not is_mentor and not waiting and not _cooling_down(can_apply_after),
        "can_apply_after": can_apply_after if _cooling_down(can_apply_after) else None,
        "prompt_to_apply": interested and not is_mentor and latest is None,
    }


def _cooling_down(until: Any) -> bool:
    from django.utils import timezone

    return until is not None and timezone.now() < until
