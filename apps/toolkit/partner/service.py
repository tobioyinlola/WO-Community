"""The venture partner: a conversation grounded in one venture's own data.

What the partner may do is deliberately narrow. It reads this venture's profile, score, forecast
headline, plan progress and decision log; it replies in plain words; it may *propose* changes to
profile fields, which become a change set the founder applies or dismisses and can undo. Advice
the platform must not give is declined in code before any model is called, and figures in a reply
that appear nowhere in the venture's data or the founder's message are removed.
"""

import json
import time
from datetime import date, timedelta
from typing import Any
from uuid import UUID

import structlog
from django.conf import settings
from django.db import transaction
from django.utils import timezone
from rest_framework import exceptions

from apps.core.errors import ConflictError
from apps.core.text import plain
from apps.toolkit.ai import runner, safety
from apps.toolkit.forecasts import selectors as forecasts
from apps.toolkit.jobs import services as jobs
from apps.toolkit.jobs.models import AIJob
from apps.toolkit.jobs.services import JobContext, JobFailed
from apps.toolkit.partner.models import ChangeSet, Conversation, Decision, Message, Nudge
from apps.toolkit.plans import content as plan_content
from apps.toolkit.plans import service as plans
from apps.toolkit.scoring import selectors as scoring
from apps.toolkit.ventures import schema
from apps.toolkit.ventures import services as ventures
from apps.toolkit.ventures.models import Venture
from apps.toolkit.ventures.selectors import profile_of

logger = structlog.get_logger(__name__)

MAX_CONVERSATIONS = 30
MAX_MESSAGES = 200
HISTORY_TURNS = 10
MAX_MESSAGE_CHARS = 2000
POLL_EVERY = 0.25


# --- conversations ---------------------------------------------------------------------------


def start(venture: Venture, owner_id: UUID, title: str = "") -> Conversation:
    if Conversation.objects.filter(venture=venture).count() >= MAX_CONVERSATIONS:
        raise ConflictError(
            f"A venture can have {MAX_CONVERSATIONS} conversations. Delete one first.",
            code="limit",
        )
    return Conversation.objects.create(
        venture=venture, owner_id=owner_id, title=plain(title).strip()[:120]
    )


def get(venture: Venture, owner_id: UUID, conversation_id: UUID) -> Conversation | None:
    return Conversation.objects.filter(
        pk=conversation_id, venture=venture, owner_id=owner_id
    ).first()


# --- what the partner is given ---------------------------------------------------------------


def _trim(value: Any, limit: int = 600) -> Any:
    if isinstance(value, str):
        return value[:limit]
    if isinstance(value, list):
        return [_trim(v, limit) for v in value[:12]]
    if isinstance(value, dict):
        return {k: _trim(v, limit) for k, v in value.items()}
    return value


def assemble_context(venture: Venture) -> dict[str, Any]:
    """Everything the partner may know, from this venture only and bounded in size."""
    fields = profile_of(venture).fields
    context: dict[str, Any] = {
        "profile": _trim(fields),
        "competitors": [c.name for c in venture.competitors.all()[:8]],
        "team": [{"role": t.role, "founder": t.is_founder} for t in venture.team.all()[:20]],
        "missing_for_score": schema.missing_required(fields),
    }
    assessment = scoring.latest(venture)
    if assessment is not None:
        context["score"] = {
            "overall": assessment.overall_score,
            "verdict": assessment.verdict,
            "gaps": [g["text"] for g in assessment.gaps][:3],
        }
    headline = forecasts.headline(venture)
    if headline is not None:
        context["forecast"] = {"currency": headline["currency"], **headline["figures"]}
    plan = plans.latest(venture)
    if plan is not None:
        statuses = list(plan.sections.values_list("status", flat=True))
        context["plan"] = {
            "sections": len(statuses),
            "needs_input": statuses.count("needs_input"),
            "edited": statuses.count("edited"),
        }
    context["decisions"] = [
        {"decided_on": d.decided_on.isoformat(), "text": d.text}
        for d in Decision.objects.filter(venture=venture)[:5]
    ]
    return context


def _history(conversation: Conversation, upto: Message) -> list[dict[str, str]]:
    rows = list(
        conversation.messages.filter(created_at__lte=upto.created_at)
        .exclude(pk=upto.pk)
        .order_by("-created_at")[:HISTORY_TURNS]
    )
    return [{"role": m.role, "text": m.text[:1000]} for m in reversed(rows)]


# --- replying --------------------------------------------------------------------------------


def _decline(conversation: Conversation, text: str, screened: safety.Screening) -> Message:
    return Message.objects.create(
        conversation=conversation,
        role="assistant",
        text=screened.reply,
        meta={"declined": "deception" if screened.deception else screened.advice},
    )


def post_message(
    *, venture: Venture, owner_id: UUID, conversation: Conversation, text: str, key: str = ""
) -> dict[str, Any]:
    """Store the founder's message and answer it: now if it is quick, otherwise as a job."""
    cleaned = plain(text).strip()
    if not cleaned:
        raise exceptions.ValidationError({"text": ["Write a message."]})
    if len(cleaned) > MAX_MESSAGE_CHARS:
        raise exceptions.ValidationError({"text": [f"At most {MAX_MESSAGE_CHARS} characters."]})
    if conversation.messages.count() >= MAX_MESSAGES:
        raise ConflictError("This conversation is full. Start a new one.", code="limit")
    with transaction.atomic():
        user_message = Message.objects.create(conversation=conversation, role="user", text=cleaned)
        conversation.save(update_fields=["updated_at"])
        if not conversation.title:
            conversation.title = cleaned[:60]
            conversation.save(update_fields=["title", "updated_at"])
        screened = safety.screen(cleaned)
        if screened.blocked:
            return {
                "user_message": user_message,
                "assistant_message": _decline(conversation, cleaned, screened),
                "change_set": None,
                "job": None,
            }
    job, _ = jobs.start(
        owner_id=owner_id,
        kind="partner.reply",
        venture=venture,
        payload={"message_id": str(user_message.pk)},
        idempotency_key=key,
    )
    finished = wait_for(job.pk, settings.AI_PARTNER_REPLY_TIMEOUT_SECONDS)
    if finished is not None and finished.status == "succeeded":
        reply = Message.objects.filter(pk=finished.result_ref.get("id")).first()
        return {
            "user_message": user_message,
            "assistant_message": reply,
            "change_set": getattr(reply, "change_set", None) if reply else None,
            "job": None,
        }
    return {"user_message": user_message, "assistant_message": None, "change_set": None, "job": job}


def wait_for(job_id: UUID, seconds: float) -> AIJob | None:
    """Wait up to ``seconds`` for a job to finish; ``None`` if it has not by then."""
    deadline = time.monotonic() + max(0.0, seconds)
    while True:
        job = AIJob.objects.filter(pk=job_id).first()
        if job is not None and job.status in ("succeeded", "failed", "cancelled"):
            return job
        if time.monotonic() >= deadline:
            return None
        time.sleep(POLL_EVERY)


def _known_text(context: dict[str, Any], message: str, history: list[dict[str, str]]) -> str:
    return "\n".join(
        [
            json.dumps(context, default=str, ensure_ascii=False),
            message,
            *[h["text"] for h in history if h["role"] == "user"],
        ]
    )


def _label(name: str) -> str:
    return name.replace("_", " ").capitalize()


def _proposed_changes(venture: Venture, raw: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Keep only changes that are valid profile values and actually differ from now."""
    fields = profile_of(venture).fields
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in raw:
        name = str(item.get("field", ""))
        if name in seen or name not in schema.FIELD_NAMES:
            continue
        try:
            built = schema.validate_patch({name: item.get("value")})
        except schema.ProfileInvalid:
            continue
        value = built.get(name)
        if value is None or value == fields.get(name):
            continue
        seen.add(name)
        out.append(
            {
                "field": name,
                "label": _label(name),
                "from": fields.get(name),
                "to": value,
                "reason": plain(str(item.get("reason", "")))[:240],
                "applied": False,
            }
        )
    return out


def reply(ctx: JobContext) -> dict[str, Any]:
    """The ``partner.reply`` job. Payload: ``message_id`` of the founder's message."""
    venture = ctx.venture
    if venture is None:
        raise JobFailed("no_venture", "This job needs a venture.")
    message = Message.objects.filter(
        pk=str(ctx.payload.get("message_id", "")), conversation__venture=venture, role="user"
    ).first()
    if message is None:
        raise JobFailed("no_message", "That message no longer exists.")
    existing = (
        message.conversation.messages.filter(role="assistant", created_at__gt=message.created_at)
        .order_by("created_at")
        .first()
    )
    if existing is not None and existing.meta.get("reply_to") == str(message.pk):
        return {"type": "message", "id": str(existing.pk)}  # a retry of a job that finished
    context = assemble_context(venture)
    history = _history(message.conversation, message)
    ctx.progress(30, "Thinking")
    answer = runner.structured(
        prompt_id="partner.reply",
        variables={"context": context, "history": history, "message": message.text},
        owner_id=ctx.owner_id,
        venture=venture,
        job=ctx.job,
    )
    text = plain(str(answer.get("reply", ""))).strip()
    allowed = _known_text(context, message.text, history)
    if not text or safety.leaks_instructions(text):
        text = "I could not put a good answer together. Could you say a little more?"
    bad = plan_content.unsupported_figures(text, allowed)
    if bad:
        kept = plan_content.drop_sentences_with(
            {"blocks": [{"type": "paragraph", "text": text, "cites": []}]}, bad
        )
        text = " ".join(b["text"] for b in kept["blocks"]) or text
    meta: dict[str, Any] = {
        "reply_to": str(message.pk),
        "next_steps": [plain(str(s))[:200] for s in answer.get("next_steps", [])][:3],
        "mentor_topics": [plain(str(t))[:40] for t in answer.get("mentor_topics", [])][:3],
    }
    changes = _proposed_changes(venture, answer.get("changes", []))
    with transaction.atomic():
        assistant = Message.objects.create(
            conversation=message.conversation, role="assistant", text=text, meta=meta
        )
        if changes:
            ChangeSet.objects.create(venture=venture, message=assistant, changes=changes)
        message.conversation.save(update_fields=["updated_at"])
    return {"type": "message", "id": str(assistant.pk)}


# --- change sets -----------------------------------------------------------------------------


def _change_set(venture: Venture, change_set_id: UUID) -> ChangeSet:
    row = ChangeSet.objects.filter(pk=change_set_id, venture=venture).first()
    if row is None:
        raise exceptions.NotFound()
    return row


def apply_changes(
    venture: Venture, change_set_id: UUID, *, fields: list[str] | None = None
) -> ChangeSet:
    """Write the chosen changes to the profile. Each is marked as an accepted suggestion."""
    with transaction.atomic():
        row = (
            ChangeSet.objects.select_for_update().filter(pk=change_set_id, venture=venture).first()
        )
        if row is None:
            raise exceptions.NotFound()
        if row.status != "proposed":
            raise ConflictError("This change set was already dealt with.", code="settled")
        chosen = [c for c in row.changes if fields is None or c["field"] in fields]
        if not chosen:
            raise exceptions.ValidationError({"fields": ["Choose at least one change."]})
        current = profile_of(venture).fields
        for change in chosen:
            if current.get(change["field"]) != change["from"]:
                change["from"] = current.get(change["field"])  # undo goes back to what is now
        _, changed = ventures.update_profile(
            venture=venture,
            patch={c["field"]: c["to"] for c in chosen},
            actor="change_set",
            source="ai_suggested_accepted",
            accepted_fields={c["field"] for c in chosen},
        )
        for change in row.changes:
            change["applied"] = change["field"] in changed
        row.status = "applied"
        row.applied_at = timezone.now()
        row.save()
    return row


def undo_changes(venture: Venture, change_set_id: UUID) -> tuple[ChangeSet, list[str]]:
    """Put back the previous values, except where the founder has changed a field since."""
    with transaction.atomic():
        row = (
            ChangeSet.objects.select_for_update().filter(pk=change_set_id, venture=venture).first()
        )
        if row is None:
            raise exceptions.NotFound()
        if row.status != "applied":
            raise ConflictError("Only applied changes can be undone.", code="not_applied")
        current = profile_of(venture).fields
        restore: dict[str, Any] = {}
        skipped: list[str] = []
        for change in row.changes:
            if not change.get("applied"):
                continue
            if current.get(change["field"]) == change["to"]:
                restore[change["field"]] = change["from"]
            else:
                skipped.append(change["field"])
        if restore:
            ventures.update_profile(
                venture=venture,
                patch=dict(restore),
                actor="change_set",
                source="member",
            )
        row.status = "undone"
        row.undone_at = timezone.now()
        row.save()
    return row, skipped


def dismiss_changes(venture: Venture, change_set_id: UUID) -> ChangeSet:
    row = _change_set(venture, change_set_id)
    if row.status != "proposed":
        raise ConflictError("This change set was already dealt with.", code="settled")
    row.status = "dismissed"
    row.save(update_fields=["status", "updated_at"])
    return row


# --- decisions -------------------------------------------------------------------------------


def record_decision(
    venture: Venture, *, text: str, rationale: str = "", decided_on: date | None = None
) -> Decision:
    clean_text = plain(text).strip()
    if not 3 <= len(clean_text) <= 300:
        raise exceptions.ValidationError({"text": ["Between 3 and 300 characters."]})
    if Decision.objects.filter(venture=venture).count() >= 500:
        raise ConflictError("The decision log is full.", code="limit")
    return Decision.objects.create(
        venture=venture,
        text=clean_text,
        rationale=plain(rationale).strip()[:1000],
        decided_on=decided_on or timezone.now().date(),
    )


# --- mentors ---------------------------------------------------------------------------------

DIMENSION_TOPICS = {
    "problem_clarity": "product",
    "market": "market research",
    "demand": "sales",
    "competition": "strategy",
    "business_model": "business model",
    "team": "hiring",
    "traction": "growth",
    "risk": "compliance",
}


def mentor_topics(venture: Venture, extra: list[str] | None = None) -> list[str]:
    """What the venture most needs help with: weakest score areas, then topics the partner named."""
    topics: list[str] = []
    assessment = scoring.latest(venture)
    if assessment is not None:
        weak = sorted(
            (d for d in assessment.dimensions if d["status"] == "scored"),
            key=lambda d: (d["score"], d["key"]),
        )[:3]
        topics += [DIMENSION_TOPICS[d["key"]] for d in weak if d["key"] in DIMENSION_TOPICS]
    for t in extra or []:
        if t.lower() not in topics:
            topics.append(t.lower())
    return topics[:6]


def suggest_mentors(viewer: Any, venture: Venture, limit: int = 3) -> dict[str, Any]:
    """Listed mentors whose experience fits, ranked by overlap. Nobody is contacted."""
    from apps.mentorship import selectors as mentorship

    fields = profile_of(venture).fields
    topics = mentor_topics(venture)
    candidates = mentorship.listed()
    sector = fields.get("sector")
    pool = candidates.filter(industries__contains=[sector]) if sector else candidates
    rows = list(pool.order_by("-approved_at")[:60])
    if sector and len(rows) < limit:
        rows = list(candidates.order_by("-approved_at")[:60])

    def score(row: Any) -> tuple[int, int, str]:
        expertise = " ".join(row.expertise).lower()
        hits = sum(1 for t in topics if any(word in expertise for word in t.split()))
        sector_hit = 1 if sector and sector in row.industries else 0
        return (-(hits * 2 + sector_hit), -row.years_experience, str(row.user_id))

    ranked = sorted(rows, key=score)[:limit]
    return {"topics": topics, "mentors": mentorship.views(viewer, ranked)}


# --- weekly nudges ---------------------------------------------------------------------------


def week_key(now: Any = None) -> str:
    iso = (now or timezone.now()).isocalendar()
    return f"{iso.year}-W{iso.week:02d}"


def _next_step(venture: Venture) -> tuple[str, str, dict[str, Any]] | None:
    """The single most useful next step, from fixed rules and the venture's own state."""
    fields = profile_of(venture).fields
    missing = schema.missing_required(fields)
    if missing:
        first = missing[0].replace("_", " ")
        return (
            "complete_profile",
            f"Add your {first} to your venture profile; it unlocks your validation score.",
            {"type": "edit_profile", "field": missing[0]},
        )
    assessment = scoring.latest(venture)
    if assessment is None:
        return (
            "run_score",
            "Run your validation score to see where to focus.",
            {"type": "open_score"},
        )
    top = assessment.next_actions[0] if assessment.next_actions else None
    forecast = forecasts.headline(venture)
    if forecast is None:
        return (
            "start_forecast",
            "Start your financial forecast; investors will ask for it.",
            {"type": "open_forecast"},
        )
    plan = plans.latest(venture)
    if plan is None:
        return (
            "write_plan",
            "Write your business plan from what you have entered.",
            {"type": "open_plan"},
        )
    if top is not None:
        return ("act_on_score", str(top["text"])[:300], dict(top["action"]))
    return None


def create_nudge(venture: Venture, now: Any = None) -> Nudge | None:
    step = _next_step(venture)
    if step is None:
        return None
    code, text, action = step
    nudge, created = Nudge.objects.get_or_create(
        venture=venture,
        week_key=week_key(now),
        defaults={"code": code, "text": text[:300], "action": action},
    )
    return nudge if created else None


def weekly_nudges(now: Any = None) -> int:
    """Create this week's nudge for every venture that wants one. Safe to run twice."""
    since = (now or timezone.now()) - timedelta(days=90)
    made = 0
    ventures_qs = Venture.objects.filter(
        deleted_at__isnull=True,
        status="active",
        nudges_enabled=True,
        updated_at__gte=since,
        owner__status="active",
    )
    for venture in ventures_qs.iterator():
        if create_nudge(venture, now) is not None:
            made += 1
    return made
