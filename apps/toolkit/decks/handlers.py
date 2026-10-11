from apps.toolkit.decks import service
from apps.toolkit.jobs import services as jobs
from apps.toolkit.ventures import services as ventures


def register() -> None:
    jobs.register("exports.deck", service.export_deck, queue="exports")
    ventures.register_eraser(service.erase_for)
