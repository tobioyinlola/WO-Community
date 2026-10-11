"""One sitemap for every public page, built from each module's own list."""

from typing import Any

from apps.directory import selectors as directory
from apps.editorial import selectors as editorial
from apps.events import selectors as events
from apps.jobs import selectors as jobs
from apps.learning import selectors as learning


def _entries(rows: list[dict[str, Any]], prefix: str, stamp: str = "updated_at") -> list[dict]:
    return [{"path": f"{prefix}/{row['slug']}", "lastmod": row.get(stamp)} for row in rows]


def build() -> dict[str, list[dict[str, Any]]]:
    people = directory.sitemap()
    return {
        "startups": [{"path": e["path"], "lastmod": e["lastmod"]} for e in people["startups"]],
        "founders": [{"path": e["path"], "lastmod": e["lastmod"]} for e in people["founders"]],
        "jobs": _entries(jobs.public_sitemap(), "/jobs"),
        "news": _entries(editorial.public_sitemap(), "/news"),
        "events": _entries(events.public_sitemap(), "/events"),
        "courses": _entries(learning.public_sitemap(), "/courses"),
    }
