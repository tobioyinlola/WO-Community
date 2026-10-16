"""Onyeka, the community's AI founder advisor: one ongoing conversation per member.

Onyeka sees what the member has told the community about themselves and their startups, and the
ventures they are building in the launch toolkit, and advises on the business against what the
leading early stage programmes look for. Like the venture partner, advice the platform must not
give is declined in code before any model is called, and replies arrive through a job so a slow
model never holds a web worker.
"""

import json
import re
import time
from typing import Any
from uuid import UUID

from django.conf import settings
from django.db import transaction
from rest_framework import exceptions

from apps.core.text import plain
from apps.profiles import selectors as profiles
from apps.startups import selectors as startups
from apps.toolkit.advisor.models import AdvisorMessage
from apps.toolkit.ai import runner, safety
from apps.toolkit.jobs import services as jobs
from apps.toolkit.jobs.models import AIJob
from apps.toolkit.jobs.services import JobContext, JobFailed
from apps.toolkit.scoring import selectors as scoring
from apps.toolkit.ventures.selectors import mine, profile_of

MAX_MESSAGE_CHARS = 2000
HISTORY_TURNS = 12
KEEP_MESSAGES = 200  # older messages are removed so the conversation stays bounded
PAGE = 50
FRAMEWORKS = ("yc", "techstars", "antler", "founder_institute")

# Onyeka speaks as an AI and may say so, so only our delimiters and talk of its own
# instructions count as a leak here (the shared check also refuses "as an AI").
_LEAK = re.compile(
    r"(<<<\s*(?:END )?DATA|ignore (?:all )?(?:previous|prior|above) (?:instructions|rules)|"
    r"my (?:system )?(?:instructions|prompt) (?:are|is|say))",
    re.IGNORECASE,
)

# How the answer should read. A spoken answer is short, so it starts sooner and is easy to follow
# by ear; the written one can use the full length and a short list.
TEXT_STYLE = "written: up to 250 words; short lists are fine"
VOICE_STYLE = (
    "spoken aloud in a conversation: at most 90 words, two or three short sentences per point, "
    "no lists, no symbols or abbreviations that read badly aloud; weave the single most important "
    "next step into the answer and give at most one next step"
)
VOICE_MAX_TOKENS = 600

GREETING = (
    "Hi, I'm Onyeka, founder of WO Community. I'm here as your AI advisor: tell me what you're "
    "building and where you're stuck, and I'll help you think it through the way Y Combinator, "
    "Techstars, Antler and Founder Institute would look at it."
)


def _trim(value: Any, limit: int = 500) -> Any:
    if isinstance(value, str):
        return value[:limit]
    if isinstance(value, list):
        return [_trim(v, limit) for v in value[:10]]
    if isinstance(value, dict):
        return {k: _trim(v, limit) for k, v in value.items() if v not in (None, "", [], {})}
    return value


def assemble_context(owner_id: UUID) -> dict[str, Any]:
    """What Onyeka may know: the member's own profile, startups and ventures, bounded in size."""
    _, me = profiles.own_profile(owner_id)
    context: dict[str, Any] = {
        "founder": _trim(
            {
                k: me.get(k)
                for k in ("full_name", "headline", "bio", "city", "country", "skills")
                if k in me
            }
        ),
        "startups": [],
        "ventures": [],
    }
    for _, view in startups.my_startups(owner_id)[:3]:
        context["startups"].append(
            _trim(
                {
                    k: view.get(k)
                    for k in (
                        "name",
                        "pitch",
                        "description",
                        "sector",
                        "stage",
                        "country",
                        "city",
                        "year_founded",
                        "website_url",
                        "traction",
                    )
                }
            )
        )
    for venture in mine(owner_id)[:3]:
        entry: dict[str, Any] = {"name": venture.name, "profile": _trim(profile_of(venture).fields)}
        assessment = scoring.latest(venture)
        if assessment is not None:
            entry["validation_score"] = {
                "overall": assessment.overall_score,
                "verdict": assessment.verdict,
                "gaps": [g["text"] for g in assessment.gaps][:3],
            }
        context["ventures"].append(entry)
    return context


def history(owner_id: UUID, *, before: AdvisorMessage | None = None) -> list[AdvisorMessage]:
    rows = AdvisorMessage.objects.filter(owner_id=owner_id)
    if before is not None:
        rows = rows.filter(created_at__lt=before.created_at)
    return list(reversed(rows.order_by("-created_at", "-id")[:PAGE]))


def _prune(owner_id: UUID) -> None:
    stale = AdvisorMessage.objects.filter(owner_id=owner_id).order_by("-created_at", "-id")[
        KEEP_MESSAGES:
    ]
    AdvisorMessage.objects.filter(pk__in=list(stale.values_list("pk", flat=True))).delete()


def clear(owner_id: UUID) -> None:
    AdvisorMessage.objects.filter(owner_id=owner_id).delete()


def wait_for(job_id: UUID, seconds: float) -> AIJob | None:
    """Wait up to ``seconds`` for a job to finish; ``None`` if it has not by then."""
    deadline = time.monotonic() + max(0.0, seconds)
    while True:
        job = AIJob.objects.filter(pk=job_id).first()
        if job is not None and job.status in ("succeeded", "failed", "cancelled"):
            return job
        if time.monotonic() >= deadline:
            return None
        time.sleep(0.25)


def post_message(
    *, owner_id: UUID, text: str, key: str = "", voice: bool = False
) -> dict[str, Any]:
    """Store the member's message and answer it: now if it is quick, otherwise as a job."""
    cleaned = plain(text).strip()
    if not cleaned:
        raise exceptions.ValidationError({"text": ["Write a message."]})
    if len(cleaned) > MAX_MESSAGE_CHARS:
        raise exceptions.ValidationError({"text": [f"At most {MAX_MESSAGE_CHARS} characters."]})
    runner.require_ai()  # Onyeka is all conversation: without AI, say so before storing anything
    with transaction.atomic():
        mine_ = AdvisorMessage.objects.create(owner_id=owner_id, role="user", text=cleaned)
        screened = safety.screen(cleaned)
        if screened.blocked:
            declined = AdvisorMessage.objects.create(
                owner_id=owner_id,
                role="assistant",
                text=screened.reply,
                meta={
                    "declined": "deception" if screened.deception else screened.advice,
                    "reply_to": str(mine_.pk),
                },
            )
            return {"user_message": mine_, "assistant_message": declined, "job": None}
    _prune(owner_id)
    job, _ = jobs.start(
        owner_id=owner_id,
        kind="advisor.reply",
        payload={"message_id": str(mine_.pk), "voice": voice},
        idempotency_key=key,
    )
    finished = wait_for(job.pk, settings.AI_PARTNER_REPLY_TIMEOUT_SECONDS)
    if finished is not None and finished.status == "succeeded":
        reply_row = AdvisorMessage.objects.filter(
            pk=finished.result_ref.get("id"), owner_id=owner_id
        ).first()
        return {"user_message": mine_, "assistant_message": reply_row, "job": None}
    return {"user_message": mine_, "assistant_message": None, "job": job}


def reply(ctx: JobContext) -> dict[str, Any]:
    """The ``advisor.reply`` job. Payload: ``message_id`` of the member's message."""
    message = AdvisorMessage.objects.filter(
        pk=str(ctx.payload.get("message_id", "")), owner_id=ctx.owner_id, role="user"
    ).first()
    if message is None:
        raise JobFailed("no_message", "That message no longer exists.")
    done = AdvisorMessage.objects.filter(
        owner_id=ctx.owner_id, role="assistant", meta__reply_to=str(message.pk)
    ).first()
    if done is not None:
        return {"type": "advisor_message", "id": str(done.pk)}  # a retry of a finished job
    earlier = [
        {"role": m.role, "text": m.text[:1200]}
        for m in history(ctx.owner_id, before=message)[-HISTORY_TURNS:]
    ]
    spoken = bool(ctx.payload.get("voice"))
    ctx.progress(30, "Thinking")
    answer = runner.structured(
        prompt_id="advisor.reply",
        variables={
            "context": json.loads(json.dumps(assemble_context(ctx.owner_id), default=str)),
            "history": earlier,
            "message": message.text,
            "style": VOICE_STYLE if spoken else TEXT_STYLE,
        },
        owner_id=ctx.owner_id,
        job=ctx.job,
        max_tokens=VOICE_MAX_TOKENS if spoken else None,
    )
    raw = str(answer.get("reply", ""))
    text = plain(raw).strip()
    if not text or _LEAK.search(raw):
        text = "I couldn't put a good answer together. Could you tell me a little more?"
    meta: dict[str, Any] = {
        "voice": spoken,
        "reply_to": str(message.pk),
        "next_steps": [plain(str(s))[:200] for s in answer.get("next_steps", [])][:3],
        "frameworks": [f for f in answer.get("frameworks", []) if f in FRAMEWORKS][:4],
    }
    row = AdvisorMessage.objects.create(
        owner_id=ctx.owner_id, role="assistant", text=text, meta=meta
    )
    return {"type": "advisor_message", "id": str(row.pk)}
