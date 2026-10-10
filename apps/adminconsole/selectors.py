"""Figures the console shows that come from several modules."""

from apps.accounts import selectors as accounts
from apps.editorial import selectors as editorial
from apps.feed import moderation
from apps.jobs import selectors as jobs


def queue_counts() -> dict[str, int]:
    """How many items of each kind are waiting for an admin."""
    return {
        **accounts.registration_queue_counts(),
        "open_reports": moderation.open_report_count(),
        "jobs_awaiting_review": jobs.pending_count(),
        "wins_awaiting_review": editorial.pending_wins(),
    }
