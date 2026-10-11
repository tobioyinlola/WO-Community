"""Mentor recommendations: a weighted sum of signals, each between 0 and 1, with reasons.

A signal with no data for this founder (no stated needs, no startup, no languages) is left out
and the remaining weights are rescaled, so a sparse profile is not punished. Mentors who are
paused, revoked or at capacity are removed before scoring, and the founder never sees themselves.
"""

import hashlib
import json
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from django.conf import settings
from django.core.cache import cache
from django.utils import timezone

from apps.analytics import services as analytics
from apps.mentorship import cache as data_version
from apps.mentorship import domain, scheduling, selectors
from apps.mentorship.domain import LANGUAGES
from apps.mentorship.models import MentorProfile, SeekerNeeds
from apps.reference import selectors as reference
from apps.startups import selectors as startups

PRIOR_RATING = 4.0  # what a mentor with no ratings is assumed to be
PRIOR_WEIGHT = 5  # how many ratings that assumption is worth
AVAILABILITY_TARGET = 10  # bookable start times in two weeks that count as fully available
AVAILABILITY_DAYS = 14
MAX_NEEDS = 5
CACHED_RESULTS = 50


@dataclass
class Signal:
    key: str
    score: float | None  # None means no data for this founder
    text: str


def normalise(value: str) -> str:
    return " ".join(value.lower().replace("-", " ").split())


def _words(value: str) -> set[str]:
    return {w for w in normalise(value).split() if len(w) >= 4}


def _terms(need: str) -> set[str]:
    base = normalise(need)
    terms = {base}
    for key, synonyms in settings.MENTORSHIP_SYNONYMS.items():
        group = {normalise(key), *(normalise(s) for s in synonyms)}
        if base in group:
            terms |= group
    return terms


def _matches(need: str, tag: str) -> bool:
    tag_norm = normalise(tag)
    for term in _terms(need):
        if term == tag_norm or term in tag_norm or tag_norm in term:
            return True
        if _words(term) & _words(tag_norm):
            return True
    return False


def expertise_signal(needs: list[str], profile: MentorProfile) -> Signal:
    if not needs:
        return Signal("expertise", None, "")
    hits = [n for n in needs if any(_matches(n, tag) for tag in profile.expertise)]
    if not hits:
        return Signal("expertise", 0.0, "")
    return Signal("expertise", len(hits) / len(needs), "Covers " + ", ".join(hits))


def fit_signal(pairs: list[tuple[str, str]], profile: MentorProfile) -> Signal:
    if not pairs:
        return Signal("fit", None, "")
    best, text = 0.0, ""
    names = {s.slug: s.name for s in reference.sectors()}
    names |= {s.slug: s.name for s in reference.stages()}
    for sector, stage in pairs:
        sector_ok, stage_ok = sector in profile.industries, stage in profile.stages
        score = 0.5 * sector_ok + 0.5 * stage_ok
        if score > best:
            best = score
            parts = []
            if sector_ok:
                parts.append(f"{names.get(sector, sector)} startups")
            if stage_ok:
                parts.append(f"{names.get(stage, stage)} stage")
            text = "Advises " + " and ".join(parts)
    return Signal("fit", best, text if best else "")


def language_signal(languages: list[str], profile: MentorProfile) -> Signal:
    if not languages:
        return Signal("language", None, "")
    shared = [c for c in profile.languages if c in languages]
    if not shared:
        return Signal("language", 0.0, "")
    return Signal("language", 1.0, "Speaks " + ", ".join(LANGUAGES.get(c, c) for c in shared))


def quality_signal(profile: MentorProfile) -> Signal:
    average = (profile.rating_total + PRIOR_RATING * PRIOR_WEIGHT) / (
        profile.rating_count + PRIOR_WEIGHT
    )
    score = max(0.0, min(1.0, (average - 1) / 4))
    if profile.rating_count:
        return Signal("quality", score, f"Rated {average:.1f} by {profile.rating_count} founders")
    return Signal("quality", score, "")


def availability_signal(profile: MentorProfile, now: Any) -> Signal:
    starts = scheduling.bookable_starts(profile, days=AVAILABILITY_DAYS, now=now)
    score = min(1.0, len(starts) / AVAILABILITY_TARGET)
    text = f"{len(starts)} times free in the next two weeks" if starts else ""
    return Signal("availability", score, text)


def capacity_signal(profile: MentorProfile, now: Any) -> Signal:
    left = scheduling.capacity_left(profile, now)
    return Signal("capacity", left / profile.capacity_per_week, f"{left} sessions free this week")


def score_mentor(
    profile: MentorProfile,
    *,
    needs: list[str],
    languages: list[str],
    pairs: list[tuple[str, str]],
    now: Any,
) -> dict[str, Any] | None:
    if scheduling.capacity_left(profile, now) == 0:
        return None
    signals = [
        expertise_signal(needs, profile),
        fit_signal(pairs, profile),
        availability_signal(profile, now),
        language_signal(languages, profile),
        capacity_signal(profile, now),
        quality_signal(profile),
    ]
    weights = settings.MENTORSHIP_MATCH_WEIGHTS
    used = [s for s in signals if s.score is not None]
    total_weight = sum(weights[s.key] for s in used)
    total = sum(weights[s.key] * (s.score or 0.0) for s in used) / total_weight
    return {
        "score": round(total * 100),
        "reasons": [
            {"key": s.key, "score": round((s.score or 0.0) * 100), "text": s.text}
            for s in used
            if s.text
        ],
        "components": {s.key: round(s.score or 0.0, 3) for s in used},
    }


def clean_needs(values: list[str]) -> list[str]:
    needs: list[str] = []
    for value in values:
        tag = normalise(value)
        if tag and tag not in needs:
            needs.append(tag)
    return needs[:MAX_NEEDS]


def saved(user_id: UUID) -> dict[str, list[str]]:
    row = SeekerNeeds.objects.filter(user_id=user_id).first()
    return {
        "needs": list(row.needs) if row else [],
        "languages": list(row.languages) if row else [],
    }


def save(user_id: UUID, needs: list[str], languages: list[str]) -> dict[str, list[str]]:
    cleaned = clean_needs(needs)
    for need in cleaned:
        if not 2 <= len(need) <= 50:
            raise domain.invalid("needs", "Each need must be 2 to 50 characters.")
    row, _ = SeekerNeeds.objects.update_or_create(
        user_id=user_id,
        defaults={"needs": cleaned, "languages": domain.languages(languages) if languages else []},
    )
    return {"needs": row.needs, "languages": row.languages}


def recommend(
    viewer: Any, *, needs: list[str] | None, limit: int, now: Any = None
) -> list[dict[str, Any]]:
    """Top mentors for this founder, scored now or taken from a 15 minute cache."""
    stored = saved(viewer.pk)
    wanted = clean_needs(needs) if needs else stored["needs"]
    languages = stored["languages"]
    pairs = startups.sector_stage_of_member(viewer.pk)
    key_source = json.dumps([wanted, languages, sorted(pairs), data_version.version()])
    key = f"mentorship:rec:{viewer.pk}:{hashlib.sha256(key_source.encode()).hexdigest()[:16]}"
    ranked = cache.get(key)
    if ranked is None:
        now = now or timezone.now()
        scored = []
        for profile in selectors.listed().exclude(user_id=viewer.pk):
            result = score_mentor(profile, needs=wanted, languages=languages, pairs=pairs, now=now)
            if result is not None:
                scored.append((str(profile.user_id), result))
        scored.sort(key=lambda item: (-item[1]["score"], item[0]))
        ranked = scored[:CACHED_RESULTS]
        cache.set(key, ranked, settings.MENTORSHIP_RECOMMENDATION_TTL_SECONDS)
    top = ranked[:limit]
    found = {
        str(p.user_id): p
        for p in selectors.listed().filter(user_id__in=[UUID(uid) for uid, _ in top])
    }
    shown = [(found[uid], result) for uid, result in top if uid in found]
    views = selectors.views(viewer, [p for p, _ in shown])
    out = [{**view, **result} for view, (_, result) in zip(views, shown, strict=True)]
    analytics.track(
        "mentor_recommendation_shown", actor_id=viewer.pk, properties={"count": len(out)}
    )
    return out
