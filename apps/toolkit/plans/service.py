"""Writing the business plan, section by section, only from what the venture and the sources say.

The order of work: check the profile, research once, write each section from the fields and facts
it depends on (a section missing a required input is left for the founder, with a question, not
filled with invention), review every figure against the venture's data and the facts, and write
the executive summary last from the finished sections. Sections a member edited are kept unless
they ask for them to be rewritten.
"""

import json
from typing import Any
from uuid import UUID

import structlog
from django.conf import settings
from django.db import transaction
from rest_framework import exceptions

from apps.core.errors import ConflictError
from apps.core.text import plain
from apps.toolkit.ai import runner, safety
from apps.toolkit.ai.models import Fact
from apps.toolkit.ai.research import gather
from apps.toolkit.forecasts import selectors as forecasts
from apps.toolkit.jobs import exports
from apps.toolkit.jobs.services import JobCancelled, JobContext, JobFailed
from apps.toolkit.plans import catalog, content, export
from apps.toolkit.plans.models import (
    BusinessPlan,
    Citation,
    PlanSection,
    PlanSectionDef,
    PlanVersion,
)
from apps.toolkit.ventures import schema
from apps.toolkit.ventures import services as ventures
from apps.toolkit.ventures.models import OutputState, Venture, VentureProfileVersion
from apps.toolkit.ventures.selectors import profile_of

logger = structlog.get_logger(__name__)

SUMMARY = 1
ACTIONS = ("shorten", "expand", "rewrite_for_investors", "simplify", "add_data", "localise")
MAX_FACTS_PER_SECTION = 6


# --- the catalogue ---------------------------------------------------------------------------


def ensure_catalog() -> None:
    """Create any section the catalogue has and the database lacks. Admin edits are kept."""
    have = set(PlanSectionDef.objects.values_list("number", flat=True))
    PlanSectionDef.objects.bulk_create(
        PlanSectionDef(**row) for row in catalog.seed_rows() if row["number"] not in have
    )


def active_definitions() -> list[PlanSectionDef]:
    ensure_catalog()
    return list(PlanSectionDef.objects.filter(active=True).order_by("number"))


# --- reading what a section is written from --------------------------------------------------


def venture_data(venture: Venture, wanted: list[str] | None = None) -> dict[str, Any]:
    """The venture's own content, limited to ``wanted`` names, with empty fields left out."""
    fields = profile_of(venture).fields
    names = wanted if wanted is not None else list(fields)
    data: dict[str, Any] = {}
    for name in names:
        if name == "competitors":
            value: Any = [
                {"name": c.name, "differentiator": c.differentiator}
                for c in venture.competitors.all()
            ]
        elif name == "team":
            value = [
                {"name": t.name, "role": t.role, "founder": t.is_founder}
                for t in venture.team.all()
            ]
        else:
            value = fields.get(name)
        if value not in (None, "", [], {}):
            data[name] = value
    return data


def _missing(defn: PlanSectionDef, data: dict[str, Any]) -> list[dict[str, str]]:
    return [
        {"field": name, "message": _question(name)}
        for name in defn.required_inputs
        if name not in data
    ]


def _question(name: str) -> str:
    label = name.replace("_", " ")
    return f"Add your {label} to your venture profile so this section can be written."


def _facts_for(defn: PlanSectionDef, facts: list[Fact]) -> list[Fact]:
    topics = defn.depends_on.get("facts", [])
    chosen = [f for f in facts if f.topic in topics]
    chosen.sort(key=lambda f: (-float(f.confidence), str(f.pk)))
    return chosen[:MAX_FACTS_PER_SECTION]


def _fact_rows(facts: list[Fact]) -> list[dict[str, Any]]:
    return [
        {
            "n": i,
            "statement": f.statement,
            "source": f.source.publisher or f.source.title,
            "date": f.retrieved_at.date().isoformat(),
        }
        for i, f in enumerate(facts, start=1)
    ]


def _allowed_text(data: dict[str, Any], facts: list[Fact], extra: Any = None) -> str:
    parts = [json.dumps(data, default=str, ensure_ascii=False)]
    parts.extend(f.statement for f in facts)
    parts.extend(str(f.value) for f in facts if f.value is not None)
    if extra:
        parts.append(json.dumps(extra, default=str, ensure_ascii=False))
    return "\n".join(parts)


# --- one section -----------------------------------------------------------------------------


def _attach_citations(
    section: PlanSection, blocks: dict[str, Any], facts: list[Fact]
) -> dict[str, Any]:
    """Turn positions in the fact list into numbered citations on the section."""
    numbering: dict[int, int] = {}
    out: list[dict[str, Any]] = []
    for block in blocks["blocks"]:
        block = dict(block)
        mapped: list[int] = []
        for position in block.get("cites", []):
            if not 1 <= position <= len(facts):
                continue
            if position not in numbering:
                numbering[position] = len(numbering) + 1
            mapped.append(numbering[position])
        if "cites" in block:
            block["cites"] = sorted(set(mapped))
        out.append(block)
    section.citations.all().delete()
    Citation.objects.bulk_create(
        Citation(
            section=section,
            number=number,
            source=facts[position - 1].source,
            claim_text=facts[position - 1].statement[:600],
        )
        for position, number in numbering.items()
    )
    return {"blocks": out}


def _write(
    *,
    ctx: JobContext,
    venture: Venture,
    defn: PlanSectionDef,
    data: dict[str, Any],
    facts: list[Fact],
    forecast: dict[str, Any] | None,
) -> tuple[dict[str, Any], list[dict[str, str]]]:
    """The cleaned blocks and the questions for the founder. Unsupported figures are removed."""
    allowed = _allowed_text(data, facts, forecast)
    notes = ""
    result: dict[str, Any] = {"blocks": []}
    answer: dict[str, Any] = {}
    for attempt in (1, 2):
        answer = runner.structured(
            prompt_id=defn.prompt_id,
            variables={
                "section": f"{defn.number}. {defn.title}",
                "guidance": defn.guidance,
                "venture": data,
                "facts": _fact_rows(facts),
                "forecast": forecast if "forecast" in defn.depends_on.get("outputs", []) else None,
                "notes": notes or "none",
            },
            owner_id=ctx.owner_id,
            venture=venture,
            job=ctx.job,
        )
        try:
            result = content.clean({"blocks": answer.get("blocks", [])})
        except content.InvalidContent as exc:
            raise JobFailed("invalid_output", exc.message) from exc
        bad = content.unsupported_figures(content.text_of(result), allowed)
        if not bad:
            break
        if attempt == 1:
            notes = "These figures were removed because they are not in the data: " + ", ".join(
                sorted(bad)
            )
            continue
        result = content.drop_sentences_with(result, bad)
    if safety.leaks_instructions(content.text_of(result)):
        result = {"blocks": []}
    asked = [
        {"field": str(m.get("field", ""))[:60], "message": plain(str(m.get("message", "")))[:240]}
        for m in answer.get("missing", [])
        if m.get("message")
    ]
    return result, asked


def _save_section(
    plan: BusinessPlan,
    defn: PlanSectionDef,
    *,
    blocks: dict[str, Any],
    prompts: list[dict[str, str]],
    facts: list[Fact],
    profile_version: int,
    forecast_version: int | None,
) -> PlanSection:
    section, created = PlanSection.objects.get_or_create(
        plan=plan, number=defn.number, defaults={"definition": defn}
    )
    section.definition = defn
    marked = _attach_citations(section, blocks, facts)
    section.content = marked
    section.prompts = prompts
    section.status = "drafted" if marked["blocks"] else "needs_input"
    section.edited_by_member = False
    section.profile_version = profile_version
    section.forecast_version = forecast_version
    if not created:
        section.version += 1
    section.save()
    return section


def _carry_over(previous: PlanSection, plan: BusinessPlan) -> None:
    kept = PlanSection.objects.create(
        plan=plan,
        definition=previous.definition,
        number=previous.number,
        content=previous.content,
        status=previous.status,
        prompts=previous.prompts,
        version=previous.version,
        edited_by_member=previous.edited_by_member,
        profile_version=previous.profile_version,
        forecast_version=previous.forecast_version,
    )
    Citation.objects.bulk_create(
        Citation(
            section=kept,
            number=c.number,
            source=c.source,
            claim_text=c.claim_text,
            position_ref=c.position_ref,
        )
        for c in previous.citations.all()
    )


# --- the plan --------------------------------------------------------------------------------


def latest(venture: Venture) -> BusinessPlan | None:
    return BusinessPlan.objects.filter(venture=venture).order_by("-version").first()


def snapshot(plan: BusinessPlan, label: str = "") -> PlanVersion:
    last = plan.versions.order_by("-version").first()
    row = PlanVersion.objects.create(
        plan=plan,
        version=(last.version + 1) if last else 1,
        label=label[:80],
        snapshot=[
            {
                "number": s.number,
                "content": s.content,
                "status": s.status,
                "prompts": s.prompts,
                "edited": s.edited_by_member,
            }
            for s in plan.sections.all()
        ],
    )
    old = plan.versions.order_by("-version").values_list("pk", flat=True)[
        settings.PLAN_VERSIONS_KEPT :
    ]
    PlanVersion.objects.filter(pk__in=list(old)).delete()
    return row


def _summary(
    *,
    ctx: JobContext,
    venture: Venture,
    plan: BusinessPlan,
    defn: PlanSectionDef,
    data: dict[str, Any],
    forecast: dict[str, Any] | None,
) -> tuple[dict[str, Any], list[dict[str, str]]]:
    parts = [
        {"title": s.definition.title, "text": content.text_of(s.content)[:900]}
        for s in plan.sections.select_related("definition").order_by("number")
        if s.number != SUMMARY and s.content.get("blocks")
    ]
    if not parts:
        return {"blocks": []}, [
            {"field": "problem", "message": "Fill in more of the plan to get a summary."}
        ]
    answer = runner.structured(
        prompt_id="plan.executive_summary",
        variables={"venture": data, "sections": parts},
        owner_id=ctx.owner_id,
        venture=venture,
        job=ctx.job,
    )
    paragraphs = [plain(str(p)) for p in answer.get("paragraphs", []) if str(p).strip()]
    result = {"blocks": [{"type": "paragraph", "text": p, "cites": []} for p in paragraphs]}
    allowed = _allowed_text(data, [], [p["text"] for p in parts]) + json.dumps(forecast or {})
    bad = content.unsupported_figures(content.text_of(result), allowed)
    if bad:
        result = content.drop_sentences_with(result, bad)
    try:
        return content.clean(result), []
    except content.InvalidContent as exc:
        raise JobFailed("invalid_output", exc.message) from exc


def generate(ctx: JobContext) -> dict[str, Any]:
    """The ``plan.generate`` job. Payload: ``sections`` (numbers) and ``overwrite_edited``."""
    venture = ctx.venture
    if venture is None:
        raise JobFailed("no_venture", "This job needs a venture.")
    wanted = {int(n) for n in ctx.payload.get("sections", [])}
    overwrite = bool(ctx.payload.get("overwrite_edited", False))
    before = OutputState.objects.filter(
        venture=venture, output_type="plan", output_id__isnull=True
    ).first()
    previous_status = before.status if before else "not_started"
    ventures.set_output_state(venture, "plan", "generating")
    plan: BusinessPlan | None = None
    try:
        profile = profile_of(venture)
        missing = schema.missing_required(profile.fields)
        if missing:
            raise JobFailed(
                "profile_incomplete", "Complete these fields first: " + ", ".join(missing)
            )
        definitions = active_definitions()
        if wanted:
            definitions = [d for d in definitions if d.number in wanted]
            if not definitions:
                raise JobFailed("no_sections", "None of those sections exist.")
        old = latest(venture)
        forecast = forecasts.headline(venture)
        forecast_version = forecast["version"] if forecast else None
        ctx.progress(4, "Reading your profile")
        topics = sorted({t for d in definitions for t in d.depends_on.get("facts", [])})
        facts = (
            gather.gather(
                fields=profile.fields,
                owner_id=ctx.owner_id,
                venture=venture,
                job=ctx.job,
                topics=topics,
            )
            if topics
            else []
        )
        ctx.progress(20, "Researching your market")
        with transaction.atomic():
            if wanted and old is not None:
                plan = old
                snapshot(plan, "Before rewrite")
            else:
                plan = BusinessPlan.objects.create(
                    venture=venture,
                    version=(old.version + 1) if old else 1,
                    status="generating",
                )
                if old is not None:
                    for previous in old.sections.select_related("definition"):
                        if previous.edited_by_member and not overwrite:
                            _carry_over(previous, plan)
            plan.status = "generating"
            plan.generated_for_profile_version = profile.version
            plan.generated_for_forecast_version = forecast_version
            plan.save()
        order = [d for d in definitions if d.number != SUMMARY]
        order += [d for d in definitions if d.number == SUMMARY]
        written = 0
        failed = 0
        for i, defn in enumerate(order):
            ctx.progress(20 + int(70 * i / max(1, len(order))), f"Writing: {defn.title}")
            existing = plan.sections.filter(number=defn.number).first()
            if existing and existing.edited_by_member and not overwrite:
                continue
            wanted_fields = list(defn.depends_on.get("fields", []))
            data = venture_data(venture, wanted_fields)
            if defn.number == SUMMARY:
                blocks, asked = _summary(
                    ctx=ctx,
                    venture=venture,
                    plan=plan,
                    defn=defn,
                    data=venture_data(venture),
                    forecast=forecast,
                )
                section_facts: list[Fact] = []
            else:
                asked = _missing(defn, data)
                section_facts = _facts_for(defn, facts)
                if asked:
                    blocks = {"blocks": []}
                else:
                    try:
                        blocks, asked = _write(
                            ctx=ctx,
                            venture=venture,
                            defn=defn,
                            data=data,
                            facts=section_facts,
                            forecast=forecast,
                        )
                    except JobFailed as exc:
                        if exc.code == "invalid_output":
                            logger.warning("plan_section_failed", number=defn.number)
                            blocks = {"blocks": []}
                            asked = [
                                {
                                    "field": "",
                                    "message": "This section could not be written "
                                    "automatically. Try again, or write it yourself.",
                                }
                            ]
                            failed += 1
                        else:
                            raise
            _save_section(
                plan,
                defn,
                blocks=blocks,
                prompts=asked,
                facts=section_facts,
                profile_version=profile.version,
                forecast_version=forecast_version,
            )
            written += 1
        if order and written == 0 and failed:
            raise JobFailed("generation_failed", "No section could be written. Try again.")
        with transaction.atomic():
            plan.status = "ready"
            plan.save(update_fields=["status", "updated_at"])
            snapshot(plan, "Generated")
            if wanted:
                ventures.set_output_state(venture, "plan", previous_status or "ready")
                if previous_status in ("not_started", "generating", "failed"):
                    ventures.set_output_state(venture, "plan", "ready")
            else:
                ventures.set_output_state(venture, "plan", "ready")
        return {"type": "plan", "id": str(plan.pk), "version": plan.version}
    except JobCancelled:
        if plan is not None and plan.status == "generating":
            plan.status = "failed"
            plan.save(update_fields=["status", "updated_at"])
        ventures.set_output_state(
            venture, "plan", previous_status if previous_status != "generating" else "not_started"
        )
        raise
    except Exception:
        if plan is not None:
            plan.status = "failed"
            plan.save(update_fields=["status", "updated_at"])
        ventures.set_output_state(
            venture,
            "plan",
            "failed" if previous_status in ("not_started", "failed") else previous_status,
        )
        raise


# --- editing ---------------------------------------------------------------------------------


def section_of(venture: Venture, number: int) -> PlanSection | None:
    plan = latest(venture)
    if plan is None:
        return None
    return plan.sections.select_related("definition").filter(number=number).first()


def save_section(section: PlanSection, *, new_content: Any, base_version: int) -> PlanSection:
    """Replace a section's text. A stale ``base_version`` is refused so nothing is overwritten."""
    try:
        cleaned = content.clean(new_content)
    except content.InvalidContent as exc:
        raise exceptions.ValidationError({"content": [exc.message]}) from exc
    with transaction.atomic():
        locked = PlanSection.objects.select_for_update().get(pk=section.pk)
        if locked.version != base_version:
            raise ConflictError(
                "This section changed elsewhere. Reload and try again.", code="stale"
            )
        keep = {n for b in cleaned["blocks"] for n in b.get("cites", [])}
        locked.citations.exclude(number__in=keep).delete()
        locked.content = cleaned
        locked.status = "edited"
        locked.edited_by_member = True
        locked.prompts = []
        locked.version += 1
        locked.save()
    return locked


def restore_version(plan: BusinessPlan, version: int) -> BusinessPlan:
    row = plan.versions.filter(version=version).first()
    if row is None:
        raise exceptions.NotFound()
    with transaction.atomic():
        snapshot(plan, f"Before restoring version {version}")
        by_number = {s.number: s for s in plan.sections.all()}
        for item in row.snapshot:
            target = by_number.get(item["number"])
            if target is None:
                continue
            target.content = item["content"]
            target.status = item["status"]
            target.prompts = item.get("prompts", [])
            target.edited_by_member = item.get("edited", False)
            target.version += 1
            target.save()
            keep = {n for b in item["content"].get("blocks", []) for n in b.get("cites", [])}
            target.citations.exclude(number__in=keep).delete()
    return plan


def propose(
    *,
    venture: Venture,
    owner_id: UUID,
    section: PlanSection,
    action: str,
    country: str = "",
) -> dict[str, Any]:
    """A rewritten section for the member to accept or discard. Nothing is saved here."""
    if action not in ACTIONS:
        raise exceptions.ValidationError({"action": ["Not a known action."]})
    defn = section.definition
    data = venture_data(venture, list(defn.depends_on.get("fields", [])))
    facts: list[Fact] = []
    if action == "add_data":
        profile = profile_of(venture)
        facts = _facts_for(
            defn,
            gather.gather(
                fields=profile.fields,
                owner_id=owner_id,
                venture=venture,
                job=None,
                topics=list(defn.depends_on.get("facts", [])) or None,
            ),
        )
    current = content.text_of(section.content)
    if not current.strip():
        raise exceptions.ValidationError({"section": ["This section has no text yet."]})
    answer = runner.structured(
        prompt_id="plan.rewrite",
        variables={
            "action": action,
            "country": country[:60] or "not given",
            "section": f"{defn.number}. {defn.title}",
            "current": section.content,
            "venture": data,
            "facts": _fact_rows(facts),
        },
        owner_id=owner_id,
        venture=venture,
    )
    try:
        proposed = content.clean({"blocks": answer.get("blocks", [])})
    except content.InvalidContent as exc:
        raise exceptions.ValidationError({"content": [exc.message]}) from exc
    allowed = _allowed_text(data, facts, current)
    bad = content.unsupported_figures(content.text_of(proposed), allowed)
    removed = sorted(bad)
    if bad:
        proposed = content.drop_sentences_with(proposed, bad)
    cited: list[dict[str, Any]] = []
    if facts:
        numbering: dict[int, int] = {}
        for block in proposed["blocks"]:
            mapped = []
            for position in block.get("cites", []):
                if 1 <= position <= len(facts):
                    numbering.setdefault(position, len(numbering) + 1)
                    mapped.append(numbering[position])
            if "cites" in block:
                block["cites"] = sorted(set(mapped))
        cited = [
            {
                "number": number,
                "claim_text": facts[p - 1].statement,
                "source_name": facts[p - 1].source.publisher or facts[p - 1].source.title,
                "url": facts[p - 1].source.url,
            }
            for p, number in numbering.items()
        ]
    return {
        "action": action,
        "content": proposed,
        "citations": cited,
        "removed_figures": removed,
        "missing": [
            {"field": str(m.get("field", ""))[:60], "message": plain(str(m.get("message", "")))}
            for m in answer.get("missing", [])
        ],
    }


def accept_proposal(
    section: PlanSection, *, proposal: Any, citations: list[dict[str, Any]], base_version: int
) -> PlanSection:
    """Save a proposal the member accepted, together with the sources it cites."""
    from apps.toolkit.ai.models import Source

    saved = save_section(section, new_content=proposal, base_version=base_version)
    for item in citations:
        source = Source.objects.filter(url=item.get("url", "")).first()
        if source is None:
            continue
        Citation.objects.update_or_create(
            section=saved,
            number=int(item["number"]),
            defaults={"source": source, "claim_text": str(item.get("claim_text", ""))[:600]},
        )
    return saved


# --- staleness and readiness -----------------------------------------------------------------


def stale_fields(venture: Venture, section: PlanSection) -> list[str]:
    """Fields this section depends on that changed after it was written."""
    deps = set(section.definition.depends_on.get("fields", []))
    changed: set[str] = set()
    rows = VentureProfileVersion.objects.filter(
        venture=venture, version__gt=section.profile_version
    ).values_list("changed_fields", flat=True)
    for fields in rows:
        changed.update(set(fields) & deps)
    state = OutputState.objects.filter(
        venture=venture, output_type="plan", output_id__isnull=True
    ).first()
    if state is not None and state.status == "needs_refresh":
        changed.update(set(state.stale_fields) & deps & {"competitors", "team"})
    if "forecast" in section.definition.depends_on.get("outputs", []):
        now = forecasts.headline(venture)
        current = now["version"] if now else None
        if current != section.forecast_version and (current is not None):
            changed.add("forecast")
    return sorted(changed)


def readiness(venture: Venture) -> dict[str, Any]:
    plan = latest(venture)
    if plan is None:
        return {"ready": False, "sections": [], "blockers": ["No plan has been generated."]}
    rows: list[dict[str, Any]] = []
    blockers: list[str] = []
    for section in plan.sections.select_related("definition").order_by("number"):
        stale = stale_fields(venture, section)
        problems: list[str] = []
        if not section.content.get("blocks"):
            problems.append("Empty")
        if section.prompts:
            problems.append("Needs your input")
        if stale:
            problems.append("Out of date")
        rows.append(
            {
                "number": section.number,
                "title": section.definition.title,
                "status": section.status,
                "stale": bool(stale),
                "problems": problems,
            }
        )
        if problems:
            blockers.append(f"{section.definition.title}: {', '.join(problems).lower()}")
    return {"ready": not blockers, "sections": rows, "blockers": blockers}


# --- export ----------------------------------------------------------------------------------


def export_plan(ctx: JobContext) -> dict[str, Any]:
    """The ``exports.plan`` job. Payload: ``format`` (docx or pdf)."""
    from apps.toolkit.plans import selectors

    venture = ctx.venture
    if venture is None:
        raise JobFailed("no_venture", "This job needs a venture.")
    fmt = str(ctx.payload.get("format", "docx"))
    if fmt not in ("docx", "pdf"):
        raise JobFailed("bad_format", "Choose docx or pdf.")
    plan = latest(venture)
    if plan is None:
        raise JobFailed("no_plan", "Write the plan first.")
    ctx.progress(10, "Collecting sections")
    sections = [
        {
            "chapter": s.definition.chapter,
            "title": s.definition.title,
            "blocks": s.content.get("blocks", []),
            "citations": selectors.citations_of(s),
        }
        for s in plan.sections.select_related("definition").order_by("number")
        if s.content.get("blocks")
    ]
    if not sections:
        raise JobFailed("empty_plan", "The plan has no text yet.")
    ctx.progress(40, "Building the document")
    body = export.document(venture.name, plan.version, sections)
    data = export.render_docx(body) if fmt == "docx" else export.render_pdf(body)
    safe = "".join(ch for ch in venture.name if ch.isalnum() or ch in " -_").strip() or "plan"
    file = exports.store(
        venture=venture,
        owner_id=ctx.owner_id,
        kind=f"plan.{fmt}",
        filename=f"{safe} business plan v{plan.version}.{fmt}",
        content_type=export.DOCX_TYPE if fmt == "docx" else export.PDF_TYPE,
        data=data,
    )
    return exports.result_of(file)
