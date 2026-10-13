"""The research store: sourced facts, collected once and reused.

A fact is kept only if it has a source, and only if its supporting quote really appears in the
page it came from. That second check is what stops a model from "finding" a statistic the page
never made. Facts are shared and not personal: they hold no venture content, so one member's
research can serve another's, and a search is cached by (question, region, day).
"""

import hashlib
import re
from decimal import Decimal
from typing import Any
from uuid import UUID

import structlog
from django.conf import settings
from django.utils import timezone
from django.utils.module_loading import import_string

from apps.toolkit.ai import runner
from apps.toolkit.ai.models import Fact, ResearchCache, Source
from apps.toolkit.ai.research.base import Page, ResearchFailed, ResearchProvider
from apps.toolkit.jobs.models import AIJob
from apps.toolkit.ventures.models import Venture

logger = structlog.get_logger(__name__)

PAGES_PER_QUERY = 3
FACTS_PER_TOPIC = 6


def get_provider() -> ResearchProvider:
    provider: ResearchProvider = import_string(settings.RESEARCH_PROVIDER)()
    return provider


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().lower()


def _source_for(page: Page, retrieved_at: Any) -> Source:
    url_hash = hashlib.sha256(page.url.encode()).hexdigest()
    content_hash = hashlib.sha256(page.text.encode()).hexdigest()
    source, created = Source.objects.get_or_create(
        url_hash=url_hash,
        defaults={
            "url": page.url[:1000],
            "title": page.title[:300],
            "publisher": page.publisher[:200],
            "published_at": page.published,
            "retrieved_at": retrieved_at,
            "content_hash": content_hash,
            "excerpt": page.text[:500],
        },
    )
    if not created and source.content_hash != content_hash:
        source.content_hash, source.retrieved_at = content_hash, retrieved_at
        source.excerpt, source.title = page.text[:500], page.title[:300]
        source.save()
    return source


def _extract(
    *,
    page: Page,
    topic: str,
    region: str,
    sector: str,
    owner_id: UUID,
    venture: Venture | None,
    job: AIJob | None,
) -> list[dict[str, Any]]:
    answer = runner.structured(
        prompt_id="research.extract_facts",
        variables={
            "topic": topic,
            "region": region or "any",
            "sector": sector or "any",
            "page": {"title": page.title, "text": page.text[:12000]},
        },
        owner_id=owner_id,
        venture=venture,
        job=job,
    )
    haystack = _norm(page.text)
    kept = []
    for fact in answer.get("facts", []):
        quote = _norm(str(fact.get("quote", "")))
        if len(quote) >= 5 and quote in haystack and str(fact.get("statement", "")).strip():
            kept.append(fact)
        else:
            logger.info("toolkit_fact_dropped", reason="quote_not_in_page")
    return kept


def collect(
    *,
    topic: str,
    query: str,
    region: str,
    sector: str,
    owner_id: UUID,
    venture: Venture | None = None,
    job: AIJob | None = None,
) -> list[Fact]:
    """Facts for one topic: from the cache for today if there are any, otherwise researched."""
    day = timezone.now().date().isoformat()
    key = hashlib.sha256(f"{topic}|{query}|{region}|{sector}|{day}".encode()).hexdigest()
    cached = ResearchCache.objects.filter(key=key).first()
    if cached is not None:
        return list(Fact.objects.filter(pk__in=cached.fact_ids).select_related("source"))
    provider = get_provider()
    found: list[Fact] = []
    try:
        hits = provider.search(query, region=region, limit=PAGES_PER_QUERY)
    except ResearchFailed:
        hits = []
    now = timezone.now()
    for hit in hits[:PAGES_PER_QUERY]:
        try:
            page = provider.fetch(hit.url)
        except ResearchFailed:
            continue
        source = _source_for(page, now)
        for item in _extract(
            page=page,
            topic=topic,
            region=region,
            sector=sector,
            owner_id=owner_id,
            venture=venture,
            job=job,
        ):
            value = item.get("value")
            fact = Fact.objects.create(
                source=source,
                topic=topic,
                statement=str(item["statement"])[:600],
                value=Decimal(str(value)) if value is not None else None,
                unit=str(item.get("unit", ""))[:30],
                region=str(item.get("region") or region)[:40],
                sector=sector[:80],
                confidence=Decimal(str(round(float(item.get("confidence", 0.5)), 2))),
                retrieved_at=now,
            )
            found.append(fact)
            if len(found) >= FACTS_PER_TOPIC:
                break
        if len(found) >= FACTS_PER_TOPIC:
            break
    ResearchCache.objects.get_or_create(key=key, defaults={"fact_ids": [str(f.pk) for f in found]})
    return found


def stored_facts(topic: str, region: str = "", sector: str = "", limit: int = 8) -> list[Fact]:
    queryset = Fact.objects.filter(topic=topic).select_related("source")
    if region:
        queryset = queryset.filter(region__in=[region, ""])
    if sector:
        queryset = queryset.filter(sector__in=[sector, ""])
    return list(queryset.order_by("-confidence", "-retrieved_at")[:limit])
