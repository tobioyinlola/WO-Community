from typing import Any

from apps.toolkit.scoring import rubric
from apps.toolkit.scoring.models import Assessment
from apps.toolkit.ventures.models import Venture


def view(a: Assessment) -> dict[str, Any]:
    return {
        "id": a.pk,
        "created_at": a.created_at,
        "overall_score": a.overall_score,
        "verdict": a.verdict,
        "rubric_version": a.rubric_version,
        "profile_version": a.profile_version,
        "dimensions": a.dimensions,
        "strengths": a.strengths,
        "gaps": a.gaps,
        "next_actions": a.next_actions,
        "explanation": a.explanation,
        "scored_weight": a.scored_weight,
        "disclaimer": rubric.DISCLAIMER,
    }


def latest(venture: Venture) -> Assessment | None:
    return Assessment.objects.filter(venture=venture).first()


def history(venture: Venture, limit: int = 50) -> list[dict[str, Any]]:
    rows = Assessment.objects.filter(venture=venture).order_by("created_at")[:limit]
    return [
        {
            "id": a.pk,
            "created_at": a.created_at,
            "overall_score": a.overall_score,
            "verdict": a.verdict,
            "rubric_version": a.rubric_version,
        }
        for a in rows
    ]


def summary(venture: Venture, assessment: Assessment) -> dict[str, Any]:
    """A one page version for sharing: no evidence detail, no profile text."""
    return {
        "venture_name": venture.name,
        "generated_at": assessment.created_at,
        "overall_score": assessment.overall_score,
        "verdict": assessment.verdict,
        "dimensions": [
            {"label": d["label"], "score": d["score"], "status": d["status"]}
            for d in assessment.dimensions
        ],
        "strengths": [s["text"] for s in assessment.strengths],
        "gaps": [g["text"] for g in assessment.gaps],
        "disclaimer": rubric.DISCLAIMER,
    }
