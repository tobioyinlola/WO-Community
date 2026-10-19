"""The daily note to admins about approvals still waiting after a day."""

from datetime import timedelta

from django.conf import settings
from django.utils import timezone

from apps.accounts import services as accounts
from apps.adminconsole import selectors
from apps.notifications import adminalerts, emails
from apps.notifications.models import AdminAlert

# The queue figure that says how many of a kind are still waiting. Kinds without a figure here
# (mentor applications, course requests) are left out of the summary rather than guessed at.
STILL_WAITING = {
    "member_signup": "registrations_awaiting_approval",
    "job_pending": "jobs_awaiting_review",
    "content_report": "open_reports",
    "support_ticket": "support_unanswered",
}


def send_stale_summary() -> int:
    cutoff = timezone.now() - timedelta(hours=24)
    counts = selectors.queue_counts()
    lines: dict[str, str] = {}
    for kind, figure in STILL_WAITING.items():
        if kind == "member_signup" and not settings.EMAIL_PENDING_APPROVAL_NOTICES:
            continue
        waiting = int(counts.get(figure, 0))
        if waiting and AdminAlert.objects.filter(kind=kind, created_at__lt=cutoff).exists():
            lines[kind] = f"{adminalerts.KINDS[kind].label}: {waiting} still waiting"
    if not lines:
        return 0
    sent = 0
    for user_id in {u for kind in lines for u in adminalerts.recipients(kind)}:
        mine = [text for kind, text in lines.items() if user_id in adminalerts.recipients(kind)]
        contact = accounts.get_contact(user_id)
        if contact is None or not mine:
            continue
        emails.send_templated(
            contact.email,
            "admin_still_pending",
            {
                "count": len(mine),
                "items": "\n".join(mine),
                "review_url": f"{settings.FRONTEND_BASE_URL}/admin/approvals",
            },
            category="admin_approval_daily",
        )
        sent += 1
    return sent
