import json
from typing import Any

from django.core.management.base import BaseCommand, CommandError

from apps.toolkit.admin_api import evaluation


class Command(BaseCommand):
    help = (
        "Run the toolkit's offline quality checks over twenty fictional ventures. "
        "Exits with an error if any check fails."
    )

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument("--json", action="store_true", help="Print the report as JSON")

    def handle(self, *args: Any, **options: Any) -> None:
        report = evaluation.run()
        failed = [c for c in report.checks if not c.passed]
        if options["json"]:
            self.stdout.write(
                json.dumps(
                    {
                        "ok": report.ok,
                        "checks": len(report.checks),
                        "failed": [{"name": c.name, "detail": c.detail} for c in failed],
                        "ventures": report.rows,
                    },
                    indent=2,
                )
            )
        else:
            self.stdout.write(f"{len(report.checks)} checks, {len(failed)} failed")
            for row in report.rows:
                self.stdout.write(
                    f"  {row.get('venture', '?'):<22} score={row.get('score')!s:<5} "
                    f"template={row.get('template', '-'):<24} "
                    f"sections={row.get('sections_writable', '-')}"
                )
            for check in failed:
                self.stdout.write(self.style.ERROR(f"FAILED: {check.name} {check.detail}"))
        if failed:
            raise CommandError(f"{len(failed)} evaluation checks failed.")
