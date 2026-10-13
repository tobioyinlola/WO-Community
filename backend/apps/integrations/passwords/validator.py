from typing import Any

from django.core.exceptions import ValidationError

from apps.integrations.passwords import get_breach_checker


class NotBreachedValidator:
    """Django password validator backed by the configured breach checker."""

    def validate(self, password: str, user: Any = None) -> None:
        if get_breach_checker().is_breached(password):
            raise ValidationError(
                "This password has appeared in a known data breach. Choose a different one.",
                code="password_breached",
            )

    def get_help_text(self) -> str:
        return "Your password must not appear in known data breaches."
