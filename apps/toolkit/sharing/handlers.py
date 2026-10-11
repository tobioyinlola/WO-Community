from typing import Any

from apps.toolkit.sharing.models import ShareLink
from apps.toolkit.ventures import services as ventures
from apps.toolkit.ventures.models import Venture


def export_shares(venture: Venture) -> list[dict[str, Any]]:
    """Links the member made. The token is not kept, so it cannot be exported."""
    return [
        {
            "subject_type": s.subject_type,
            "subject_id": str(s.subject_id),
            "has_password": bool(s.password_hash),
            "expires_at": s.expires_at.isoformat() if s.expires_at else None,
            "revoked_at": s.revoked_at.isoformat() if s.revoked_at else None,
            "view_count": s.view_count,
        }
        for s in ShareLink.objects.filter(venture=venture)
    ]


def register() -> None:
    ventures.register_exporter("shares", export_shares)
