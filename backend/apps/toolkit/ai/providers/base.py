from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


class ProviderTemporary(Exception):
    """Rate limited, timed out or a provider error. The same call may work shortly."""

    def __init__(self, reason: str, retry_after: float | None = None) -> None:
        super().__init__(reason)
        self.retry_after = retry_after


class ProviderRejected(Exception):
    """The provider will not take this request (too long, policy). Retrying cannot help."""


class ProviderMisconfigured(Exception):
    """Our credentials or settings are not accepted. Needs a person."""


class InvalidOutput(Exception):
    """The model answered, but not in the shape asked for."""


@dataclass(frozen=True)
class TextResult:
    text: str
    input_tokens: int = 0
    output_tokens: int = 0
    model: str = ""


@dataclass(frozen=True)
class StructuredResult:
    data: dict[str, Any]
    input_tokens: int = 0
    output_tokens: int = 0
    model: str = ""


@dataclass
class Message:
    role: str  # "user" or "assistant"
    content: str


@dataclass
class CallMetadata:
    """Identifiers only. Never member text: this may end up in logs."""

    prompt_id: str
    prompt_version: int
    task: str = "default"
    model: str = ""
    variables: dict[str, Any] = field(default_factory=dict)  # for the fake; not sent anywhere


class LLMProvider(ABC):
    name = "unknown"

    @abstractmethod
    def generate_text(
        self,
        *,
        system: str,
        messages: list[Message],
        max_tokens: int,
        temperature: float,
        metadata: CallMetadata,
    ) -> TextResult:
        """Free text. May raise ProviderTemporary, ProviderRejected or ProviderMisconfigured."""

    @abstractmethod
    def generate_structured(
        self,
        *,
        system: str,
        messages: list[Message],
        json_schema: dict[str, Any],
        max_tokens: int,
        metadata: CallMetadata,
    ) -> StructuredResult:
        """A JSON object for the schema (the caller validates it). InvalidOutput if unparsable."""
