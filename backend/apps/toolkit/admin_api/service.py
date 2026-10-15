"""What staff can change in the toolkit, and what they can learn about its use.

Staff change *content the tools run on* (templates, plan sections, the score rubric); they never
read a member's venture. Usage and quality reports are built from identifiers, counts and sizes:
no prompt, no output and no member text is stored in the tables they read.
"""

import csv
import io
from datetime import date, datetime, time, timedelta
from typing import Any

from django.conf import settings
from django.db import transaction
from django.db.models import Count, Exists, F, Max, OuterRef, Q, Subquery, Sum
from django.db.models.functions import TruncDate
from django.utils import timezone
from rest_framework import exceptions

from apps.audit import services as audit
from apps.toolkit.ai.models import AIRun
from apps.toolkit.ai.research.gather import TOPICS
from apps.toolkit.decks import schema as deck_schema
from apps.toolkit.decks.models import DeckTemplate
from apps.toolkit.decks.service import build_content
from apps.toolkit.forecasts.models import Forecast
from apps.toolkit.jobs.models import AIJob
from apps.toolkit.partner.models import Conversation
from apps.toolkit.plans.models import PlanSectionDef
from apps.toolkit.prototypes import spec as prototype_spec
from apps.toolkit.prototypes.models import PrototypeTemplate
from apps.toolkit.scoring import rubric
from apps.toolkit.scoring.models import Assessment, ScoreRubric
from apps.toolkit.ventures import schema as profile_schema
from apps.toolkit.ventures.models import Venture

PLAN_OUTPUTS = ("forecast",)
PLAN_FIELDS = set(profile_schema.FIELD_NAMES) | {"competitors", "team"}
MAX_REPORT_DAYS = 366


def _fail(field: str, message: str) -> exceptions.ValidationError:
    return exceptions.ValidationError({field: [message]})


# --- deck templates --------------------------------------------------------------------------


def _check_deck_slides(slides: Any) -> list[dict[str, Any]]:
    """A template must build into a valid deck from an empty profile."""
    if not isinstance(slides, list) or not 1 <= len(slides) <= 40:
        raise _fail("slides", "A template has between 1 and 40 slides.")
    probe = DeckTemplate(slug="probe", name="probe", slides=slides)
    try:
        build_content(probe, {})
    except (deck_schema.InvalidDeck, KeyError, TypeError) as exc:
        raise _fail("slides", f"Does not build into a valid deck: {exc}") from exc
    return list(slides)


def save_deck_template(
    *,
    actor: Any,
    slug: str,
    name: str,
    description: str,
    slides: Any,
    active: bool,
    position: int | None = None,
) -> DeckTemplate:
    checked = _check_deck_slides(slides)
    with transaction.atomic():
        row, created = DeckTemplate.objects.get_or_create(
            slug=slug,
            defaults={"name": name, "description": description, "slides": checked},
        )
        before = {"name": row.name, "slides": len(row.slides), "active": row.active}
        row.name, row.description, row.slides, row.active = name, description, checked, active
        if position is not None:
            row.position = position
        row.save()
        audit.record(
            actor=actor,
            action="toolkit.deck_template_saved",
            target_type="deck_template",
            target_id=row.pk,
            before=None if created else before,
            after={"slug": slug, "slides": len(checked), "active": active},
        )
    return row


# --- prototype templates ---------------------------------------------------------------------


def save_prototype_template(
    *,
    actor: Any,
    slug: str,
    name: str,
    description: str,
    spec: Any,
    active: bool,
) -> PrototypeTemplate:
    try:
        prototype_spec.clean(spec)
    except prototype_spec.InvalidSpec as exc:
        raise _fail(exc.path, exc.message) from exc
    with transaction.atomic():
        row, created = PrototypeTemplate.objects.get_or_create(
            slug=slug, defaults={"name": name, "description": description, "spec": spec}
        )
        before = {"name": row.name, "active": row.active}
        row.name, row.description, row.spec, row.active = name, description, spec, active
        row.save()
        audit.record(
            actor=actor,
            action="toolkit.prototype_template_saved",
            target_type="prototype_template",
            target_id=row.pk,
            before=None if created else before,
            after={"slug": slug, "active": active},
        )
    return row


# --- plan sections ---------------------------------------------------------------------------


def save_plan_section(*, actor: Any, number: int, changes: dict[str, Any]) -> PlanSectionDef:
    from apps.toolkit.plans import service as plans

    plans.ensure_catalog()
    row = PlanSectionDef.objects.filter(number=number).first()
    if row is None:
        raise exceptions.NotFound()
    depends = changes.get("depends_on", row.depends_on)
    required = changes.get("required_inputs", row.required_inputs)
    unknown = (set(depends.get("fields", [])) | set(required)) - PLAN_FIELDS
    if unknown:
        raise _fail("depends_on", "Unknown profile fields: " + ", ".join(sorted(unknown)))
    bad_topics = set(depends.get("facts", [])) - set(TOPICS)
    if bad_topics:
        raise _fail("depends_on", "Unknown research topics: " + ", ".join(sorted(bad_topics)))
    bad_outputs = set(depends.get("outputs", [])) - set(PLAN_OUTPUTS)
    if bad_outputs:
        raise _fail("depends_on", "Unknown outputs: " + ", ".join(sorted(bad_outputs)))
    if number == 1 and changes.get("active") is False:
        raise _fail("active", "The executive summary cannot be switched off.")
    before = {
        "title": row.title,
        "active": row.active,
        "depends_on": row.depends_on,
        "required_inputs": row.required_inputs,
    }
    for name in ("title", "guidance", "chapter", "active"):
        if name in changes:
            setattr(row, name, changes[name])
    row.depends_on = {
        "fields": list(depends.get("fields", [])),
        "facts": list(depends.get("facts", [])),
        "outputs": list(depends.get("outputs", [])),
    }
    row.required_inputs = list(required)
    row.save()
    audit.record(
        actor=actor,
        action="toolkit.plan_section_saved",
        target_type="plan_section_def",
        target_id=row.pk,
        before=before,
        after={"title": row.title, "active": row.active},
    )
    return row


# --- the score rubric ------------------------------------------------------------------------


def create_rubric(*, actor: Any, config: Any, notes: str) -> ScoreRubric:
    problems = rubric.validate(config if isinstance(config, dict) else {})
    if problems:
        raise exceptions.ValidationError({"config": problems})
    with transaction.atomic():
        latest = ScoreRubric.objects.select_for_update().order_by("-version").first()
        row = ScoreRubric.objects.create(
            version=(latest.version + 1) if latest else 1,
            active=False,
            notes=notes[:300],
            config=config,
        )
        audit.record(
            actor=actor,
            action="toolkit.rubric_created",
            target_type="score_rubric",
            target_id=row.pk,
            after={"version": row.version},
        )
    return row


def activate_rubric(*, actor: Any, version: int) -> ScoreRubric:
    with transaction.atomic():
        row = ScoreRubric.objects.select_for_update().filter(version=version).first()
        if row is None:
            raise exceptions.NotFound()
        ScoreRubric.objects.filter(active=True).exclude(pk=row.pk).update(active=False)
        row.active = True
        row.save(update_fields=["active", "updated_at"])
        audit.record(
            actor=actor,
            action="toolkit.rubric_activated",
            target_type="score_rubric",
            target_id=row.pk,
            after={"version": version},
        )
    return row


# --- usage and quality -----------------------------------------------------------------------


def _window(date_from: date | None, date_to: date | None) -> tuple[datetime, datetime]:
    end_day = date_to or timezone.now().date()
    start_day = date_from or (end_day - timedelta(days=29))
    if start_day > end_day:
        raise _fail("from", "The start is after the end.")
    if (end_day - start_day).days >= MAX_REPORT_DAYS:
        raise _fail("from", f"At most {MAX_REPORT_DAYS} days at a time.")
    tz = timezone.get_current_timezone()
    return (
        timezone.make_aware(datetime.combine(start_day, time.min), tz),
        timezone.make_aware(datetime.combine(end_day + timedelta(days=1), time.min), tz),
    )


def usage(*, date_from: date | None, date_to: date | None, group_by: str) -> list[dict[str, Any]]:
    """AI use grouped by day, prompt or agent. Counts, tokens and estimated cost only."""
    if group_by not in ("day", "prompt", "agent"):
        raise _fail("group_by", "Use day, prompt or agent.")
    start, end = _window(date_from, date_to)
    rows = AIRun.objects.filter(created_at__gte=start, created_at__lt=end)
    if group_by == "day":
        grouped = rows.annotate(grp=TruncDate("created_at"))
    elif group_by == "prompt":
        grouped = rows.annotate(grp=F("prompt_id"))
    else:
        grouped = rows.annotate(grp=F("agent"))
    totals = (
        grouped.values("grp")
        .annotate(
            runs=Count("id"),
            tokens_in=Sum("input_tokens"),
            tokens_out=Sum("output_tokens"),
            cost=Sum("estimated_cost_minor"),
        )
        .order_by("grp")
    )
    outcomes: dict[Any, dict[str, int]] = {}
    for row in grouped.values("grp", "outcome").annotate(n=Count("id")):
        outcomes.setdefault(row["grp"], {})[row["outcome"]] = row["n"]
    return [
        {
            "key": str(t["grp"]),
            "runs": t["runs"],
            "input_tokens": t["tokens_in"] or 0,
            "output_tokens": t["tokens_out"] or 0,
            "estimated_cost_minor": t["cost"] or 0,
            "currency": settings.AI_COST_CURRENCY,
            "outcomes": outcomes.get(t["grp"], {}),
        }
        for t in totals
    ]


def usage_csv(rows: list[dict[str, Any]]) -> str:
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(
        ["key", "runs", "input_tokens", "output_tokens", "estimated_cost_minor", "currency", "ok"]
    )
    for r in rows:
        writer.writerow(
            [
                _safe_cell(r["key"]),
                r["runs"],
                r["input_tokens"],
                r["output_tokens"],
                r["estimated_cost_minor"],
                r["currency"],
                r["outcomes"].get("ok", 0),
            ]
        )
    return out.getvalue()


def _safe_cell(value: str) -> str:
    """Stop a spreadsheet treating a cell as a formula."""
    return "'" + value if value[:1] in ("=", "+", "-", "@") else value


def quality(*, limit: int = 100) -> dict[str, Any]:
    """Where outputs are failing: refused model answers and failed jobs, by prompt and kind."""
    since = timezone.now() - timedelta(days=7)
    bad_runs = AIRun.objects.filter(created_at__gte=since).exclude(outcome="ok")
    by_prompt = [
        {"prompt_id": p, "outcome": o, "count": n}
        for p, o, n in bad_runs.values_list("prompt_id", "outcome")
        .annotate(n=Count("id"))
        .order_by("-n", "prompt_id")[:50]
    ]
    failed_jobs = AIJob.objects.filter(created_at__gte=since, status="failed")
    by_kind = [
        {"kind": k, "error_code": c, "count": n}
        for k, c, n in failed_jobs.values_list("kind", "error_code")
        .annotate(n=Count("id"))
        .order_by("-n", "kind")[:50]
    ]
    recent = [
        {
            "id": r.pk,
            "created_at": r.created_at,
            "prompt_id": r.prompt_id,
            "prompt_version": r.prompt_version,
            "outcome": r.outcome,
            "model": r.model,
            "job_id": r.job_id,
        }
        for r in bad_runs.order_by("-created_at")[:limit]
    ]
    total = AIRun.objects.filter(created_at__gte=since).count()
    return {
        "window_days": 7,
        "runs": total,
        "not_ok": bad_runs.count(),
        "by_prompt": by_prompt,
        "failed_jobs": by_kind,
        "recent": recent,
    }


def settings_view() -> dict[str, Any]:
    """The toolkit's configuration, without any secret."""
    return {
        "features": dict(settings.TOOLKIT_FEATURES),
        "ai_provider": str(settings.AI_PROVIDER).rsplit(".", 1)[-1],
        "ai_fallback_provider": str(settings.AI_FALLBACK_PROVIDER or ""),
        "ai_daily_run_ceiling": settings.AI_DAILY_RUN_CEILING,
        "research_provider": str(settings.RESEARCH_PROVIDER).rsplit(".", 1)[-1],
        "research_domains": len(settings.RESEARCH_ALLOWED_DOMAINS),
        "max_ventures_per_member": settings.TOOLKIT_MAX_VENTURES_PER_MEMBER,
        "export_retention_days": settings.EXPORT_RETENTION_DAYS,
        "venture_delete_grace_days": settings.VENTURE_DELETE_GRACE_DAYS,
    }


# --- ventures, for oversight ---


def ventures(*, q: str = "", include_deleted: bool = False) -> Any:
    """Every venture with its owner and how far it has gone, newest first.

    Only names, dates and counts: what a member wrote stays private to them.
    """
    rows = Venture.objects.select_related("owner")
    if not include_deleted:
        rows = rows.filter(deleted_at__isnull=True)
    if q.strip():
        term = q.strip()
        rows = rows.filter(Q(name__icontains=term) | Q(owner__email__icontains=term))
    latest = Assessment.objects.filter(venture=OuterRef("pk")).order_by("-created_at")
    return rows.annotate(
        latest_score=Subquery(latest.values("overall_score")[:1]),
        scored_at=Max("assessments__created_at"),
        plan_count=Count("plans", distinct=True),
        deck_count=Count("decks", distinct=True),
        prototype_count=Count("prototypes", distinct=True),
        conversation_count=Count("conversations", distinct=True),
        share_count=Count("share_links", distinct=True),
        has_forecast=Exists(Forecast.objects.filter(venture=OuterRef("pk"))),
        has_partner=Exists(Conversation.objects.filter(venture=OuterRef("pk"))),
    ).order_by("-created_at", "id")


def venture_row(v: Any) -> dict[str, Any]:
    return {
        "id": v.pk,
        "name": v.name,
        "status": "deleted" if v.deleted_at else v.status,
        "owner_id": v.owner_id,
        "owner_email": v.owner.email,
        "profile_completeness": v.profile_completeness,
        "latest_score": v.latest_score,
        "scored_at": v.scored_at,
        "plans": v.plan_count,
        "has_forecast": v.has_forecast,
        "decks": v.deck_count,
        "prototypes": v.prototype_count,
        "partner_conversations": v.conversation_count,
        "share_links": v.share_count,
        "created_at": v.created_at,
        "updated_at": v.updated_at,
    }


def venture_totals() -> dict[str, int]:
    live = Venture.objects.filter(deleted_at__isnull=True)
    return {
        "ventures": live.count(),
        "founders": live.values("owner_id").distinct().count(),
        "scored": live.filter(assessments__isnull=False).distinct().count(),
        "with_plan": live.filter(plans__isnull=False).distinct().count(),
        "with_deck": live.filter(decks__isnull=False).distinct().count(),
    }
