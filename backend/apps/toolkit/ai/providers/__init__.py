"""Choosing a model provider for a kind of task, with a fallback when one keeps failing."""

import time
from typing import Any

from django.conf import settings
from django.core.cache import cache
from django.utils.module_loading import import_string

from apps.toolkit.ai.providers.base import LLMProvider

DEFAULT_PATH = "apps.toolkit.ai.providers.http.ChatCompletionsProvider"
FAILURES_TO_OPEN = 5
WINDOW_SECONDS = 60
OPEN_SECONDS = 30


def _load(name: str) -> LLMProvider:
    if name == "fake":
        from apps.toolkit.ai.providers.fake import FakeLLMProvider

        return FakeLLMProvider()
    provider: LLMProvider = import_string(DEFAULT_PATH if name == "http" else name)()
    return provider


def _key(name: str, what: str) -> str:
    return f"toolkit:ai:breaker:{name}:{what}"


def is_open(name: str) -> bool:
    return bool(cache.get(_key(name, "open")))


def record_failure(name: str) -> None:
    """Count a failure; enough of them in a minute open the breaker for a short while."""
    cache.add(_key(name, "count"), 0, WINDOW_SECONDS)
    try:
        count = cache.incr(_key(name, "count"))
    except ValueError:
        count = 1
    if count >= FAILURES_TO_OPEN:
        cache.set(_key(name, "open"), time.time(), OPEN_SECONDS)


def record_success(name: str) -> None:
    cache.delete(_key(name, "count"))


def model_for(task: str) -> str:
    routing: dict[str, Any] = settings.AI_MODEL_ROUTING
    return str(routing.get(task) or routing["default"])


def providers_for(task: str) -> list[tuple[str, LLMProvider]]:
    """The provider to use first, then the fallback if there is one. An open breaker skips ahead."""
    names = [settings.AI_PROVIDER]
    if settings.AI_FALLBACK_PROVIDER and settings.AI_FALLBACK_PROVIDER != settings.AI_PROVIDER:
        names.append(settings.AI_FALLBACK_PROVIDER)
    usable = [n for n in names if not is_open(n)] or names[-1:]
    return [(n, _load(n)) for n in usable]
