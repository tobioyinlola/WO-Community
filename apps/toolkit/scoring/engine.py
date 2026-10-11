"""Turning a rubric, a profile and sourced facts into scores. Deterministic and offline.

The same inputs and the same rubric always give the same numbers. A dimension with too little
evidence is reported as ``insufficient_data`` and left out of the total (its weight is shared
among the rest); it is never guessed. No model is involved here: models only write the words
around these numbers afterwards.
"""

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any


@dataclass
class Evidence:
    kind: str  # "profile" or "fact"
    text: str
    ref: str = ""  # the profile field, or the fact id
    source_name: str = ""
    url: str = ""
    date: str = ""


@dataclass
class Gap:
    field: str
    tip: str
    points: int  # points of this dimension still available from this check
    action: str = "edit_profile"


@dataclass
class DimensionResult:
    key: str
    label: str
    weight: int
    score: int | None
    status: str  # "scored" or "insufficient_data"
    evidence: list[Evidence] = field(default_factory=list)
    gaps: list[Gap] = field(default_factory=list)
    reason: str = ""


@dataclass
class Overall:
    score: int | None
    verdict: str
    scored_weight: int
    explanation: str


def _round(value: float) -> int:
    return int(value + 0.5)


def _value(path: str, fields: dict[str, Any], competitors: int, team: list[dict[str, Any]]) -> Any:
    if path == "competitors":
        return competitors
    if path == "team":
        return len(team)
    if path == "team.founders":
        return sum(1 for t in team if t.get("is_founder"))
    if path == "team.roles":
        return len({t.get("role", "").strip().lower() for t in team if t.get("role")})
    if path == "team.linkedin":
        return sum(1 for t in team if t.get("linkedin"))
    head, _, tail = path.partition(".")
    value = fields.get(head)
    if tail and isinstance(value, dict):
        return value.get(tail)
    return value


def _present(value: Any) -> bool:
    return value not in (None, "", [], {}, 0) if not isinstance(value, bool) else value


def _points(check: dict[str, Any], value: Any) -> tuple[int, int]:
    """(points earned, most points this check could give)."""
    if "bands" in check:
        bands = sorted(check["bands"], key=lambda b: -b[0])
        best = max(p for _, p in bands)
        number = (
            value if isinstance(value, int | float | Decimal) and not isinstance(value, bool) else 0
        )
        for floor, pts in bands:
            if number >= floor:
                return pts, best
        return 0, best
    if "bands_enum" in check:
        table = check["bands_enum"]
        return int(table.get(value, 0)), max(table.values())
    best = int(check.get("points", 0))
    if "min_length" in check:
        ok = isinstance(value, str) and len(value.strip()) >= check["min_length"]
    elif "min_count" in check:
        count = value if isinstance(value, int) else len(value or [])
        ok = count >= check["min_count"]
    else:  # "present"
        ok = _present(value)
    return (best if ok else 0), best


def _describe(path: str, value: Any) -> str:
    if isinstance(value, str):
        text = value.strip().replace("\n", " ")
        return text if len(text) <= 140 else text[:139] + "…"
    if isinstance(value, bool):
        return "yes" if value else "no"
    return str(value)


def _by_checks(
    dim: dict[str, Any],
    fields: dict[str, Any],
    competitors: int,
    team: list[dict[str, Any]],
) -> DimensionResult:
    result = DimensionResult(dim["key"], dim["label"], dim["weight"], None, "scored")
    values = {c["field"]: _value(c["field"], fields, competitors, team) for c in dim["checks"]}
    needed = dim.get("requires_any")
    if needed and not any(_present(_value(path, fields, competitors, team)) for path in needed):
        result.status, result.reason = "insufficient_data", "Nothing entered yet for this area."
        for check in dim["checks"]:
            result.gaps.append(
                Gap(
                    check["field"],
                    check.get("tip", ""),
                    _points(check, None)[1],
                    check.get("action", "edit_profile"),
                )
            )
        return result
    total = 0
    for check in dim["checks"]:
        value = values[check["field"]]
        earned, best = _points(check, value)
        total += earned
        if earned and _present(value):
            result.evidence.append(
                Evidence(
                    "profile",
                    f"{check['field']}: {_describe(check['field'], value)}",
                    check["field"],
                )
            )
        if earned < best:
            result.gaps.append(
                Gap(
                    check["field"],
                    check.get("tip", ""),
                    best - earned,
                    check.get("action", "edit_profile"),
                )
            )
    result.score = min(100, total)
    return result


def _fact_evidence(fact: dict[str, Any]) -> Evidence:
    return Evidence(
        "fact",
        fact["statement"],
        str(fact["id"]),
        fact.get("source_name", ""),
        fact.get("url", ""),
        fact.get("date", ""),
    )


def _by_facts(dim: dict[str, Any], facts: list[dict[str, Any]]) -> DimensionResult:
    result = DimensionResult(dim["key"], dim["label"], dim["weight"], None, "scored")
    relevant = sorted(
        (f for f in facts if f["topic"] in dim["fact_topics"]),
        key=lambda f: (-float(f.get("confidence", 0)), str(f["id"])),
    )
    if len(relevant) < dim.get("min_facts", 1):
        result.status = "insufficient_data"
        result.reason = "No reliable sources were found for this area."
        result.gaps.append(Gap("sector", dim.get("tip", ""), dim.get("base", 50)))
        return result
    result.evidence = [_fact_evidence(f) for f in relevant[:5]]
    if dim["key"] == "risk":
        words = [w.lower() for w in dim.get("penalty_words", [])]
        hits = sum(1 for f in relevant if any(w in f["statement"].lower() for w in words))
        penalty = min(dim.get("max_penalty", 40), hits * dim.get("penalty_each", 8))
        result.score = max(0, dim.get("base", 75) - penalty)
        if penalty:
            result.gaps.append(
                Gap(
                    "regulation",
                    "Check the licences and approvals your sector needs.",
                    penalty,
                    "find_mentor",
                )
            )
        return result
    score = dim.get("base", 40)
    growth = next(
        (f for f in relevant if f["topic"] == "growth" and f.get("value") is not None), None
    )
    if growth is not None:
        for floor, pts in sorted(dim["growth_bands"], key=lambda b: -b[0]):
            if float(growth["value"]) >= floor:
                score = pts
                break
    else:
        result.gaps.append(Gap("sector", "Find a growth rate for your market.", 15))
    if any(f["topic"] == "market_size" and f.get("value") is not None for f in relevant):
        score += dim.get("size_bonus", 10)
    else:
        result.gaps.append(
            Gap(
                "target_regions",
                "Add the regions so market size can be found.",
                dim.get("size_bonus", 10),
            )
        )
    result.score = min(100, score)
    return result


def score_dimension(
    dim: dict[str, Any],
    *,
    fields: dict[str, Any],
    competitors: int,
    team: list[dict[str, Any]],
    facts: list[dict[str, Any]],
) -> DimensionResult:
    if "checks" in dim:
        return _by_checks(dim, fields, competitors, team)
    return _by_facts(dim, facts)


def verdict_for(score: int, config: dict[str, Any]) -> str:
    for band in sorted(config["verdicts"], key=lambda v: -v["min"]):
        if score >= band["min"]:
            return str(band["label"])
    return str(config["verdicts"][-1]["label"])


def combine(results: list[DimensionResult], config: dict[str, Any]) -> Overall:
    scored = [r for r in results if r.status == "scored" and r.score is not None]
    weight = sum(r.weight for r in scored)
    if weight < config.get("min_scored_weight", 40):
        return Overall(
            None,
            "Not enough information to score yet",
            weight,
            "Too little of the rubric could be backed by evidence to give an overall score. "
            "Fill in the missing areas and try again.",
        )
    total = sum((r.score or 0) * r.weight for r in scored) / weight
    score = _round(total)
    skipped = [r.label for r in results if r.status != "scored"]
    note = f" {', '.join(skipped)} could not be assessed and are not counted." if skipped else ""
    return Overall(
        score,
        verdict_for(score, config),
        weight,
        "The score is the weighted average of the areas that could be assessed "
        f"({weight} of 100 weight).{note}",
    )
