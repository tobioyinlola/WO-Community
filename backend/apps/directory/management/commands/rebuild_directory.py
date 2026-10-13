from typing import Any

from django.core.management.base import BaseCommand

from apps.directory import services


class Command(BaseCommand):
    help = "Rebuild the public directory from the source records (first load, or after a restore)."

    def handle(self, *args: Any, **options: Any) -> None:
        counts = services.reconcile()
        self.stdout.write(
            f"Directory rebuilt: {counts['startups']} startups, "
            f"{counts['founders']} founders, {counts['removed']} stale rows removed."
        )
