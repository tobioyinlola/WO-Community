"""The score pipeline: check, research, calculate, explain, save.

The numbers come from ``engine`` (rubric plus profile plus sourced facts). The model only writes
the explanations and next steps around them. Research queries are built from the sector, the
target regions and the customer type, never from the member's free text, so what a member wrote
about their idea does not leave the platform in a search request.
"""

from typing import Any

import structlog
from django.db import transaction

from apps.toolkit.ai import runner
from apps.toolkit.ai.research import gather
from apps.toolkit.jobs.services import JobCancelled, JobContext, JobFailed
from apps.toolkit.scoring import engine, rubric
from apps.toolkit.scoring.models import Assessment, ScoreRubric
from apps.toolkit.ventures import schema
from apps.toolkit.ventures import services as ventures
from apps.toolkit.ventures.models import OutputState, Venture
from apps.toolkit.ventures.selectors import profile_of

logger = structlog.get_logger(__name__)


def active_rubric() -> tuple[int, dict[str, Any]]:
    row = ScoreRubric.objects.filter(active=True).first()
    if row is None:
        row = ensure_default_rubric()
    return row.version, row.config


def ensure_default_rubric() -> ScoreRubric:
    row = ScoreRubric.objects.filter(active=True).first()
    if row is not None:
        return row
    latest = ScoreRubric.objects.order_by("-version").first()
    return ScoreRubric.objects.create(
        version=(latest.version + 1) if latest else 1,
        active=True,
        notes="Default rubric",
        config=rubric.DEFAULT,
    )


def _team_rows(venture: Venture) -> list[dict[str, Any]]:
    return [
        {"role": t.role, "linkedin": t.linkedin, "is_founder": t.is_founder}
        for t in venture.team.all()
    ]


def calculate(
    venture: Venture, config: dict[str, Any], facts: list[dict[str, Any]]
) -> tuple[list[engine.DimensionResult], engine.Overall]:
    fields = profile_of(venture).fields
    competitors = venture.competitors.count()
    team = _team_rows(venture)
    results = [
        engine.score_dimension(d, fields=fields, competitors=competitors, team=team, facts=facts)
        for d in config["dimensions"]
    ]
    return results, engine.combine(results, config)


def _fallback_text(result: engine.DimensionResult) -> tuple[str, str]:
    if result.status != "scored":
        return (
            f"{result.label} could not be assessed yet. {result.reason}".strip(),
            result.gaps[0].tip if result.gaps else "Add more detail to this area.",
        )
    where = "a solid base" if (result.score or 0) >= 60 else "room to grow"
    return (
        f"{result.label} scored {result.score} out of 100, which shows {where}.",
        result.gaps[0].tip if result.gaps else "Keep this up to date as the venture develops.",
    )


def _explain(
    *,
    ctx: JobContext,
    venture: Venture,
    fields: dict[str, Any],
    results: list[engine.DimensionResult],
    overall: engine.Overall,
) -> dict[str, tuple[str, str]]:
    payload = [
        {
            "key": r.key,
            "label": r.label,
            "score": r.score,
            "status": r.status,
            "evidence": [e.text for e in r.evidence[:4]],
            "gaps": [g.tip for g in sorted(r.gaps, key=lambda g: -g.points)[:3]],
        }
        for r in results
    ]
    answer = runner.structured(
        prompt_id="score.explain",
        variables={
            "venture": {
                "name": fields.get("name", ""),
                "sector": fields.get("sector", ""),
                "stage": fields.get("stage", ""),
            },
            "overall": {"score": overall.score, "verdict": overall.verdict},
            "dimensions": payload,
        },
        owner_id=ctx.owner_id,
        venture=venture,
        job=ctx.job,
    )
    given = {d["key"]: (d["explanation"], d["next_step"]) for d in answer.get("dimensions", [])}
    return {r.key: given.get(r.key) or _fallback_text(r) for r in results}


def _evidence_json(items: list[engine.Evidence]) -> list[dict[str, Any]]:
    return [
        {
            "kind": e.kind,
            "text": e.text,
            "ref": e.ref,
            "source_name": e.source_name,
            "url": e.url,
            "date": e.date,
        }
        for e in items
    ]


def build_assessment(
    *,
    venture: Venture,
    rubric_version: int,
    profile_version: int,
    config: dict[str, Any],
    results: list[engine.DimensionResult],
    overall: engine.Overall,
    texts: dict[str, tuple[str, str]],
) -> Assessment:
    scored = sorted(
        (r for r in results if r.status == "scored"), key=lambda r: (-(r.score or 0), r.key)
    )
    weak = sorted(
        (r for r in results if r.status == "scored"), key=lambda r: ((r.score or 0), r.key)
    )
    strengths = [
        {"dimension": r.key, "label": r.label, "score": r.score, "text": texts[r.key][0]}
        for r in scored
        if (r.score or 0) >= 50
    ][:3]
    gaps = [
        {"dimension": r.key, "label": r.label, "score": r.score, "text": texts[r.key][0]}
        for r in weak
        if (r.score or 0) < 70
    ][:3]
    for r in results:  # areas that could not be assessed are gaps too
        if r.status != "scored" and len(gaps) < 3:
            gaps.append(
                {"dimension": r.key, "label": r.label, "score": None, "text": texts[r.key][0]}
            )
    # Next actions: every unmet check, worth what it adds to the overall score.
    actions: list[dict[str, Any]] = []
    weights_total = max(1, overall.scored_weight or sum(r.weight for r in results))
    for r in results:
        for gap in r.gaps:
            gain = round(gap.points * r.weight / weights_total / 1.0, 1)
            actions.append(
                {
                    "dimension": r.key,
                    "label": r.label,
                    "text": gap.tip or texts[r.key][1],
                    "field": gap.field,
                    "estimated_points": max(1, round(gain)),
                    "action": {"type": gap.action, "field": gap.field},
                }
            )
    actions.sort(key=lambda a: (-a["estimated_points"], a["dimension"], a["field"]))
    return Assessment(
        venture=venture,
        rubric_version=rubric_version,
        profile_version=profile_version,
        overall_score=overall.score,
        verdict=overall.verdict,
        dimensions=[
            {
                "key": r.key,
                "label": r.label,
                "weight": r.weight,
                "score": r.score,
                "status": r.status,
                "reason": r.reason,
                "evidence": _evidence_json(r.evidence),
                "explanation": texts[r.key][0],
                "next_step": texts[r.key][1],
            }
            for r in results
        ],
        strengths=strengths,
        gaps=gaps,
        next_actions=actions[:8],
        explanation=overall.explanation,
        scored_weight=overall.scored_weight,
    )


def generate(ctx: JobContext) -> dict[str, Any]:
    """The ``score.generate`` job."""
    venture = ctx.venture
    if venture is None:
        raise JobFailed("no_venture", "This job needs a venture.")
    before = OutputState.objects.filter(
        venture=venture, output_type="score", output_id__isnull=True
    ).first()
    previous = before.status if before else "not_started"
    ventures.set_output_state(venture, "score", "generating")
    try:
        profile = profile_of(venture)
        missing = schema.missing_required(profile.fields)
        if missing:
            raise JobFailed(
                "profile_incomplete",
                "Complete these fields first: " + ", ".join(missing),
            )
        version, config = active_rubric()
        ctx.progress(5, "Reading your profile")
        facts = gather.as_rows(
            gather.gather(
                fields=profile.fields,
                owner_id=ctx.owner_id,
                venture=venture,
                job=ctx.job,
                topics=["market_size", "growth", "competition", "regulation"],
            )
        )
        ctx.progress(55, "Scoring each area")
        results, overall = calculate(venture, config, facts)
        ctx.progress(70, "Writing the report")
        texts = _explain(
            ctx=ctx, venture=venture, fields=profile.fields, results=results, overall=overall
        )
        with transaction.atomic():
            fresh = profile_of(venture)
            assessment = build_assessment(
                venture=venture,
                rubric_version=version,
                profile_version=fresh.version,
                config=config,
                results=results,
                overall=overall,
                texts=texts,
            )
            assessment.save()
            ventures.set_output_state(venture, "score", "ready")
        return {"type": "score", "id": str(assessment.pk)}
    except JobCancelled:
        ventures.set_output_state(
            venture, "score", previous if previous != "generating" else "not_started"
        )
        raise
    except Exception:
        ventures.set_output_state(venture, "score", "failed")
        raise
