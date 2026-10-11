"""Researching a venture's market from what is safe to send out: sector, regions, nothing else.

Several tools need the same facts (the score, the plan, the forecast assumptions), so this lives
below all of them. Questions are built from the sector and the target regions only; what a member
wrote about their idea never appears in a search request.
"""

from concurrent.futures import ThreadPoolExecutor
from typing import Any

from django.conf import settings
from django.db import connections

from apps.toolkit.ai.models import Fact
from apps.toolkit.ai.research import service
from apps.toolkit.jobs.models import AIJob
from apps.toolkit.ventures.models import Venture

REGION_NAMES = {
    "north_america": "North America",
    "europe": "Europe",
    "latin_america": "Latin America",
    "middle_east": "Middle East",
    "africa": "Africa",
}
TOPICS = {
    "market_size": "{sector} market size {regions}",
    "growth": "{sector} market annual growth rate {regions}",
    "competition": "{sector} competitors landscape {regions}",
    "regulation": "{sector} regulation licensing requirements {regions}",
    "benchmarks": "{sector} typical customer acquisition cost churn margins {regions}",
}


def queries(
    fields: dict[str, Any], topics: list[str] | None = None
) -> dict[str, tuple[str, str, str]]:
    """topic -> (query, region key, sector slug)."""
    sector = str(fields.get("sector") or "startup").replace("-", " ")
    regions = fields.get("target_regions") or []
    region_text = " and ".join(REGION_NAMES[r] for r in regions if r in REGION_NAMES)
    region_key = regions[0] if regions else ""
    wanted = topics or list(TOPICS)
    return {
        topic: (
            TOPICS[topic].format(sector=sector, regions=region_text).strip(),
            region_key,
            str(fields.get("sector") or ""),
        )
        for topic in wanted
    }


def gather(
    *,
    fields: dict[str, Any],
    owner_id: Any,
    venture: Venture | None,
    job: AIJob | None,
    topics: list[str] | None = None,
) -> list[Fact]:
    """Facts for the topics, deduplicated. Questions run side by side when allowed."""
    plan = queries(fields, topics)

    def one(topic: str) -> list[Fact]:
        query, region, sector = plan[topic]
        try:
            return service.collect(
                topic=topic,
                query=query,
                region=region,
                sector=sector,
                owner_id=owner_id,
                venture=venture,
                job=job,
            )
        finally:
            if settings.TOOLKIT_PARALLEL_RESEARCH:
                connections.close_all()

    names = list(plan)
    if settings.TOOLKIT_PARALLEL_RESEARCH and len(names) > 1:
        with ThreadPoolExecutor(max_workers=len(names)) as pool:
            batches = list(pool.map(one, names))
    else:
        batches = [one(t) for t in names]
    seen: set[Any] = set()
    found: list[Fact] = []
    for batch in batches:
        for fact in batch:
            if fact.pk not in seen:
                seen.add(fact.pk)
                found.append(fact)
    return found


def as_rows(facts: list[Fact]) -> list[dict[str, Any]]:
    return [
        {
            "id": f.pk,
            "topic": f.topic,
            "statement": f.statement,
            "value": f.value,
            "unit": f.unit,
            "confidence": f.confidence,
            "source_name": f.source.publisher or f.source.title,
            "url": f.source.url,
            "date": f.retrieved_at.date().isoformat(),
        }
        for f in facts
    ]
