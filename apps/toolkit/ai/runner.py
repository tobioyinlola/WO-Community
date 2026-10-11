"""Calling a model: ceiling, routing, validation, retries and usage, in one place.

Agents never talk to a provider directly. They name a prompt and give variables; this module
renders it, calls the provider (with the fallback and the breaker), checks structured answers
against the prompt's schema, retries an invalid answer a couple of times with the error, and
records an ``AIRun`` for every call. Failures leave as ``JobFailed`` (will not get better) or
``TransientError`` (try again shortly), which the job runner already understands.
"""

import time
from typing import Any
from uuid import UUID

import jsonschema  # type: ignore[import-untyped]
import structlog
from django.conf import settings
from django.utils import timezone

from apps.core import ratelimit
from apps.toolkit.ai import prompts, providers
from apps.toolkit.ai.models import AIRun
from apps.toolkit.ai.providers.base import (
    CallMetadata,
    InvalidOutput,
    Message,
    ProviderMisconfigured,
    ProviderRejected,
    ProviderTemporary,
)
from apps.toolkit.jobs.models import AIJob
from apps.toolkit.jobs.services import JobFailed, TransientError
from apps.toolkit.ventures.models import Venture

logger = structlog.get_logger(__name__)

INVALID_RETRIES = 2


class CeilingReached(Exception):
    """The member has used the day's allowance of model calls."""


def check_ceiling(owner_id: UUID) -> None:
    today = timezone.now().date().isoformat()
    used = ratelimit.hit(f"toolkit:ai:day:{owner_id}:{today}", 86400)
    if used > settings.AI_DAILY_RUN_CEILING:
        raise CeilingReached()


def _cost(model: str, input_tokens: int, output_tokens: int) -> int:
    prices = settings.AI_PRICE_PER_MILLION_TOKENS.get(model)
    if not prices:
        return 0
    cents_in, cents_out = prices
    return -(-(input_tokens * cents_in + output_tokens * cents_out) // 1_000_000)


def _record(
    *,
    owner_id: UUID | None,
    job: AIJob | None,
    venture: Venture | None,
    prompt: prompts.Prompt,
    agent: str,
    provider: str,
    model: str,
    input_tokens: int,
    output_tokens: int,
    started: float,
    outcome: str,
) -> None:
    AIRun.objects.create(
        owner_id=owner_id,
        job=job,
        venture=venture,
        agent=agent,
        provider=provider,
        model=model,
        prompt_id=prompt.id,
        prompt_version=prompt.version,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        duration_ms=int((time.monotonic() - started) * 1000),
        estimated_cost_minor=_cost(model, input_tokens, output_tokens),
        currency=settings.AI_COST_CURRENCY,
        outcome=outcome,
    )


def _call(
    *,
    prompt_id: str,
    variables: dict[str, Any],
    owner_id: UUID,
    venture: Venture | None,
    job: AIJob | None,
    history: list[Message] | None,
    structured: bool,
    max_tokens: int | None,
    temperature: float,
) -> Any:
    check_ceiling(owner_id)
    prompt = prompts.get(prompt_id)
    system, user = prompts.render(prompt, variables)
    messages = [*(history or []), Message("user", user)]
    model = providers.model_for(prompt.task)
    meta = CallMetadata(
        prompt_id=prompt.id,
        prompt_version=prompt.version,
        task=prompt.task,
        model=model,
        variables=variables,
    )
    tokens = max_tokens or prompt.max_tokens
    last_error = ""
    for attempt in range(INVALID_RETRIES + 1):
        if attempt and last_error:
            messages = [
                *messages,
                Message(
                    "user",
                    "Your last answer was not valid: "
                    f"{last_error}. Answer again with only a JSON object that matches the schema.",
                ),
            ]
        result: Any = None
        for name, provider in providers.providers_for(prompt.task):
            started = time.monotonic()
            try:
                if structured:
                    if prompt.schema is None:
                        raise KeyError(f"prompt {prompt.id} has no schema")
                    result = provider.generate_structured(
                        system=system,
                        messages=messages,
                        json_schema=prompt.schema,
                        max_tokens=tokens,
                        metadata=meta,
                    )
                else:
                    result = provider.generate_text(
                        system=system,
                        messages=messages,
                        max_tokens=tokens,
                        temperature=temperature,
                        metadata=meta,
                    )
            except ProviderTemporary as exc:
                providers.record_failure(name)
                _record(
                    owner_id=owner_id,
                    job=job,
                    venture=venture,
                    prompt=prompt,
                    agent=prompt.agent,
                    provider=name,
                    model=model,
                    input_tokens=0,
                    output_tokens=0,
                    started=started,
                    outcome="timeout",
                )
                logger.warning("toolkit_provider_temporary", provider=name, reason=str(exc)[:80])
                continue
            except ProviderMisconfigured as exc:
                providers.record_failure(name)
                logger.error("toolkit_provider_misconfigured", provider=name, reason=str(exc)[:80])
                raise JobFailed(
                    "ai_unavailable", "The assistant is not available right now."
                ) from exc
            except ProviderRejected as exc:
                _record(
                    owner_id=owner_id,
                    job=job,
                    venture=venture,
                    prompt=prompt,
                    agent=prompt.agent,
                    provider=name,
                    model=model,
                    input_tokens=0,
                    output_tokens=0,
                    started=started,
                    outcome="rejected",
                )
                raise JobFailed("request_rejected", "The request could not be processed.") from exc
            except InvalidOutput as exc:
                last_error = str(exc)
                _record(
                    owner_id=owner_id,
                    job=job,
                    venture=venture,
                    prompt=prompt,
                    agent=prompt.agent,
                    provider=name,
                    model=model,
                    input_tokens=0,
                    output_tokens=0,
                    started=started,
                    outcome="invalid_output",
                )
                result = None
                break
            providers.record_success(name)
            break
        else:
            raise TransientError("every provider failed")
        if result is None:
            continue  # an unusable answer: ask again
        if structured:
            try:
                jsonschema.validate(result.data, prompt.schema)
            except jsonschema.ValidationError as exc:
                last_error = exc.message[:300]
                _record(
                    owner_id=owner_id,
                    job=job,
                    venture=venture,
                    prompt=prompt,
                    agent=prompt.agent,
                    provider=name,
                    model=result.model or model,
                    input_tokens=result.input_tokens,
                    output_tokens=result.output_tokens,
                    started=started,
                    outcome="invalid_output",
                )
                continue
        _record(
            owner_id=owner_id,
            job=job,
            venture=venture,
            prompt=prompt,
            agent=prompt.agent,
            provider=name,
            model=result.model or model,
            input_tokens=result.input_tokens,
            output_tokens=result.output_tokens,
            started=started,
            outcome="ok",
        )
        return result.data if structured else result.text
    raise JobFailed("invalid_model_output", "The assistant could not produce a usable answer.")


def structured(
    *,
    prompt_id: str,
    variables: dict[str, Any],
    owner_id: UUID,
    venture: Venture | None = None,
    job: AIJob | None = None,
    history: list[Message] | None = None,
    max_tokens: int | None = None,
) -> dict[str, Any]:
    """A JSON answer that matches the prompt's schema, or ``JobFailed`` / ``TransientError``."""
    data: dict[str, Any] = _call(
        prompt_id=prompt_id,
        variables=variables,
        owner_id=owner_id,
        venture=venture,
        job=job,
        history=history,
        structured=True,
        max_tokens=max_tokens,
        temperature=0.2,
    )
    return data


def text(
    *,
    prompt_id: str,
    variables: dict[str, Any],
    owner_id: UUID,
    venture: Venture | None = None,
    job: AIJob | None = None,
    history: list[Message] | None = None,
    max_tokens: int | None = None,
    temperature: float = 0.5,
) -> str:
    out: str = _call(
        prompt_id=prompt_id,
        variables=variables,
        owner_id=owner_id,
        venture=venture,
        job=job,
        history=history,
        structured=False,
        max_tokens=max_tokens,
        temperature=temperature,
    )
    return out
