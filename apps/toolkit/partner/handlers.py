from typing import Any

from apps.toolkit.jobs import services as jobs
from apps.toolkit.partner import service
from apps.toolkit.partner.models import ChangeSet, Conversation, Decision, Nudge
from apps.toolkit.ventures import services as ventures
from apps.toolkit.ventures.models import Venture


def export_partner(venture: Venture) -> dict[str, Any]:
    return {
        "conversations": [
            {
                "id": str(c.pk),
                "title": c.title,
                "messages": [
                    {"author": m.role, "text": m.text, "at": m.created_at.isoformat()}
                    for m in c.messages.all()
                ],
            }
            for c in Conversation.objects.filter(venture=venture)
        ],
        "change_sets": [
            {"id": str(s.pk), "status": s.status, "changes": s.changes}
            for s in ChangeSet.objects.filter(venture=venture)
        ],
        "decisions": [
            {"text": d.text, "rationale": d.rationale, "decided_on": d.decided_on.isoformat()}
            for d in Decision.objects.filter(venture=venture)
        ],
        "nudges": [
            {"week": n.week_key, "text": n.text} for n in Nudge.objects.filter(venture=venture)
        ],
    }


def register() -> None:
    jobs.register("partner.reply", service.reply)
    ventures.register_exporter("partner", export_partner)
