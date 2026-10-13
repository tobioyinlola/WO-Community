"""Figures the console shows that come from several modules."""

from typing import Any

from apps.accounts import referrals
from apps.accounts import selectors as accounts
from apps.editorial import reporting as editorial_reporting
from apps.editorial import selectors as editorial
from apps.feed import moderation
from apps.jobs import selectors as jobs
from apps.support import selectors as support


def queue_counts() -> dict[str, int]:
    """How many items of each kind are waiting for an admin."""
    return {
        **accounts.registration_queue_counts(),
        "open_reports": moderation.open_report_count() + editorial_reporting.open_count(),
        "jobs_awaiting_review": jobs.pending_count(),
        "wins_awaiting_review": editorial.pending_wins(),
        "support_unanswered": support.unanswered_count(),
        "support_overdue": support.overdue_count(),
    }


def application_of(user: Any) -> dict[str, Any]:
    """The profile and first startup a person gave on joining, and what has happened since."""
    from apps.profiles.models import FounderProfile
    from apps.startups.models import Startup

    profile = FounderProfile.objects.filter(user_id=user.pk).first()
    startup = (
        Startup.objects.filter(owner_id=user.pk)
        .select_related("sector", "stage")
        .order_by("created_at")
        .first()
    )
    timeline: list[dict[str, Any]] = [{"kind": "registered", "at": user.created_at, "note": ""}]
    if user.email_verified_at:
        timeline.append({"kind": "email_verified", "at": user.email_verified_at, "note": ""})
    decided = user.approved_at or (user.status_changed_at if user.status != "pending" else None)
    if decided:
        note = user.status_reason or (
            f"Approved by {user.approval_source}" if user.approval_source else ""
        )
        timeline.append({"kind": "decided", "at": decided, "note": note})
    if user.last_login:
        timeline.append({"kind": "last_signed_in", "at": user.last_login, "note": ""})
    return {
        "member": user,
        "profile": (
            {
                "full_name": profile.full_name,
                "headline": profile.headline,
                "country": profile.country,
                "city": profile.city,
                "website_url": profile.website_url,
                "linkedin_url": profile.linkedin_url,
                "completeness": profile.completeness_score,
            }
            if profile
            else None
        ),
        "startup": (
            {
                "name": startup.name,
                "country": startup.country,
                "city": startup.city,
                "sector": startup.sector.name,
                "stage": startup.stage.name,
                "pitch": startup.pitch,
                "website_url": startup.website_url,
                "completeness": startup.completeness_score,
            }
            if startup
            else None
        ),
        "timeline": timeline,
        "referral": {
            "kind": user.referral_source,
            "kind_label": referrals.SOURCE_LABELS.get(user.referral_source, ""),
            "detail": user.referral_detail,
            "referrer": _referrer_card(user.referred_by_id),
            "code_used": user.referral_code_used,
        },
    }


def _referrer_card(user_id: Any) -> dict[str, Any] | None:
    """Who brought someone in: their id and the name on their profile, else their email's start."""
    from apps.accounts.models import User
    from apps.profiles.models import FounderProfile

    if user_id is None:
        return None
    user = User.objects.filter(pk=user_id).first()
    if user is None:
        return None
    name = (
        FounderProfile.objects.filter(user_id=user_id).values_list("full_name", flat=True).first()
    )
    return {"id": user.pk, "name": name or user.email.split("@")[0]}


def applicant_summaries(user_ids: list[Any]) -> dict[Any, dict[str, Any]]:
    """Name, country, first startup and referrer for a page of members, in a few queries."""
    from apps.accounts.models import User
    from apps.profiles.models import FounderProfile
    from apps.startups.models import Startup

    out: dict[Any, dict[str, Any]] = {
        uid: {"name": "", "country": "", "startup": "", "sector": "", "stage": "", "referrer": None}
        for uid in user_ids
    }
    referred = dict(
        User.objects.filter(pk__in=user_ids, referred_by__isnull=False).values_list(
            "pk", "referred_by_id"
        )
    )
    referrer_ids = set(referred.values())
    names = dict(
        FounderProfile.objects.filter(user_id__in=referrer_ids).values_list("user_id", "full_name")
    )
    emails = dict(User.objects.filter(pk__in=referrer_ids).values_list("pk", "email"))
    for uid, by in referred.items():
        out[uid]["referrer"] = {"id": by, "name": names.get(by) or emails.get(by, "").split("@")[0]}
    for uid, name, country in FounderProfile.objects.filter(user_id__in=user_ids).values_list(
        "user_id", "full_name", "country"
    ):
        out[uid]["name"] = name
        out[uid]["country"] = country
    seen: set[Any] = set()
    for startup in (
        Startup.objects.filter(owner_id__in=user_ids)
        .select_related("sector", "stage")
        .order_by("created_at")
    ):
        if startup.owner_id in seen:
            continue
        seen.add(startup.owner_id)
        out[startup.owner_id].update(
            startup=startup.name, sector=startup.sector.name, stage=startup.stage.name
        )
        if not out[startup.owner_id]["country"]:
            out[startup.owner_id]["country"] = startup.country
    return out
