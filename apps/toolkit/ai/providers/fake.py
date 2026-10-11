from collections.abc import Callable
from typing import Any, ClassVar

from apps.toolkit.ai.providers.base import (
    CallMetadata,
    LLMProvider,
    Message,
    StructuredResult,
    TextResult,
)


def example_from_schema(schema: dict[str, Any]) -> Any:
    """The smallest value that satisfies a JSON schema, so tests and local runs need no model."""
    if "enum" in schema:
        return schema["enum"][0]
    if "const" in schema:
        return schema["const"]
    for key in ("anyOf", "oneOf"):
        if key in schema:
            return example_from_schema(schema[key][0])
    kind = schema.get("type")
    if isinstance(kind, list):
        kind = next((k for k in kind if k != "null"), kind[0])
    if kind == "object" or "properties" in schema:
        properties = schema.get("properties", {})
        return {name: example_from_schema(sub) for name, sub in properties.items()}
    if kind == "array":
        item = schema.get("items", {})
        return [example_from_schema(item) for _ in range(schema.get("minItems", 0))]
    if kind == "integer":
        return int(schema.get("minimum", 0))
    if kind == "number":
        return float(schema.get("minimum", 0))
    if kind == "boolean":
        return False
    if kind == "null":
        return None
    text = "Sample text"
    return text.ljust(int(schema.get("minLength", 0)), ".")[: int(schema.get("maxLength", 10**6))]


class FakeLLMProvider(LLMProvider):
    """Deterministic and offline. Tests set ``canned`` by prompt id to script what comes back."""

    name = "fake"
    canned: ClassVar[dict[str, Any]] = {}
    texts: ClassVar[dict[str, Any]] = {}
    calls: ClassVar[list[CallMetadata]] = []

    @classmethod
    def reset(cls) -> None:
        cls.canned.clear()
        cls.texts.clear()
        cls.calls.clear()

    @staticmethod
    def _tokens(*parts: str) -> int:
        return max(1, sum(len(p) for p in parts) // 4)

    def generate_text(
        self,
        *,
        system: str,
        messages: list[Message],
        max_tokens: int,
        temperature: float,
        metadata: CallMetadata,
    ) -> TextResult:
        self.calls.append(metadata)
        scripted = self.texts.get(metadata.prompt_id)
        if isinstance(scripted, Exception):
            raise scripted
        if callable(scripted):
            text = scripted(metadata.variables, messages)
        elif scripted is not None:
            text = scripted
        else:
            text = f"Fake reply for {metadata.prompt_id}."
        used = self._tokens(system, *[m.content for m in messages])
        return TextResult(text, used, self._tokens(text), "fake-model")

    def generate_structured(
        self,
        *,
        system: str,
        messages: list[Message],
        json_schema: dict[str, Any],
        max_tokens: int,
        metadata: CallMetadata,
    ) -> StructuredResult:
        self.calls.append(metadata)
        scripted: Any = self.canned.get(metadata.prompt_id)
        if isinstance(scripted, list):  # a queue: one answer per call, the last one repeats
            scripted = scripted.pop(0) if len(scripted) > 1 else scripted[0]
        if isinstance(scripted, Exception):
            raise scripted
        if isinstance(scripted, Callable):  # type: ignore[arg-type]
            scripted = scripted(metadata.variables, messages)
        data = scripted if scripted is not None else example_from_schema(json_schema)
        used = self._tokens(system, *[m.content for m in messages])
        return StructuredResult(dict(data), used, self._tokens(str(data)), "fake-model")
