from typing import Any

from apps.toolkit.decks import service
from apps.toolkit.decks.models import Deck
from apps.toolkit.jobs import services as jobs
from apps.toolkit.ventures import services as ventures
from apps.toolkit.ventures.models import Venture


def export_decks(venture: Venture) -> list[dict[str, Any]]:
    return [
        {
            "id": str(d.pk),
            "title": d.title,
            "template": d.template_slug,
            "status": d.status,
            "version": d.version,
            "content": d.content,
            "images": [
                {"id": str(a.pk), "filename": a.filename, "width": a.width, "height": a.height}
                for a in d.assets.all()
            ],
        }
        for d in Deck.objects.filter(venture=venture, deleted_at__isnull=True)
    ]


def register() -> None:
    jobs.register("exports.deck", service.export_deck, queue="exports")
    ventures.register_eraser(service.erase_for)
    ventures.register_exporter("decks", export_decks)
