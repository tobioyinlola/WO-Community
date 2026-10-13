"""A model provider that speaks the widely implemented chat completions HTTP API.

Point ``AI_BASE_URL`` at any service that implements it and set ``AI_API_KEY``. Requests ask the
service not to store or train on content where it supports that, and carry no member identifiers.
"""

import json
from typing import Any

import httpx
from django.conf import settings

from apps.toolkit.ai.providers.base import (
    CallMetadata,
    InvalidOutput,
    LLMProvider,
    Message,
    ProviderMisconfigured,
    ProviderRejected,
    ProviderTemporary,
    StructuredResult,
    TextResult,
)


class ChatCompletionsProvider(LLMProvider):
    name = "http"

    def __init__(self, client: httpx.Client | None = None) -> None:
        self._client = client

    @property
    def client(self) -> httpx.Client:
        if self._client is None:
            if not settings.AI_BASE_URL or not settings.AI_API_KEY:
                raise ProviderMisconfigured("AI_BASE_URL and AI_API_KEY must be set")
            self._client = httpx.Client(
                base_url=settings.AI_BASE_URL.rstrip("/"),
                headers={"Authorization": f"Bearer {settings.AI_API_KEY}"},
                timeout=httpx.Timeout(settings.AI_REQUEST_TIMEOUT_SECONDS, connect=5.0),
            )
        return self._client

    def _post(self, body: dict[str, Any]) -> dict[str, Any]:
        try:
            response = self.client.post("/chat/completions", json=body)
        except httpx.TimeoutException as exc:
            raise ProviderTemporary("timeout") from exc
        except httpx.HTTPError as exc:
            raise ProviderTemporary("network_error") from exc
        status = response.status_code
        if status in (401, 403):
            raise ProviderMisconfigured(f"provider refused our credentials ({status})")
        if status in (408, 409, 425, 429) or status >= 500:
            try:
                retry_after = float(response.headers.get("retry-after", ""))
            except ValueError:
                retry_after = None
            raise ProviderTemporary(f"status {status}", retry_after)
        if status >= 400:
            raise ProviderRejected(f"status {status}")
        try:
            return dict(response.json())
        except ValueError as exc:
            raise ProviderTemporary("unreadable response") from exc

    @staticmethod
    def _body(
        model: str, system: str, messages: list[Message], max_tokens: int, temperature: float
    ) -> dict[str, Any]:
        return {
            "model": model,
            "messages": [
                {"role": "system", "content": system},
                *[{"role": m.role, "content": m.content} for m in messages],
            ],
            "max_tokens": max_tokens,
            "temperature": temperature,
            "store": False,  # no retention where the service supports the flag
        }

    @staticmethod
    def _content(data: dict[str, Any]) -> tuple[str, int, int, str]:
        try:
            text = data["choices"][0]["message"]["content"] or ""
        except (KeyError, IndexError, TypeError) as exc:
            raise InvalidOutput("no message in the response") from exc
        usage = data.get("usage") or {}
        return (
            str(text),
            int(usage.get("prompt_tokens", 0)),
            int(usage.get("completion_tokens", 0)),
            str(data.get("model", "")),
        )

    def generate_text(
        self,
        *,
        system: str,
        messages: list[Message],
        max_tokens: int,
        temperature: float,
        metadata: CallMetadata,
    ) -> TextResult:
        body = self._body(metadata.model, system, messages, max_tokens, temperature)
        text, prompt, completion, model = self._content(self._post(body))
        return TextResult(text, prompt, completion, model)

    def generate_structured(
        self,
        *,
        system: str,
        messages: list[Message],
        json_schema: dict[str, Any],
        max_tokens: int,
        metadata: CallMetadata,
    ) -> StructuredResult:
        body = self._body(metadata.model, system, messages, max_tokens, 0.2)
        body["response_format"] = {
            "type": "json_schema",
            "json_schema": {"name": metadata.prompt_id.replace(".", "_"), "schema": json_schema},
        }
        text, prompt, completion, model = self._content(self._post(body))
        try:
            data = json.loads(text)
        except ValueError as exc:
            raise InvalidOutput("the answer was not JSON") from exc
        if not isinstance(data, dict):
            raise InvalidOutput("the answer was not a JSON object")
        return StructuredResult(data, prompt, completion, model)
