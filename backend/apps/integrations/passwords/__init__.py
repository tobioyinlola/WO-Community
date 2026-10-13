from django.conf import settings
from django.utils.module_loading import import_string

from apps.integrations.passwords.base import BreachChecker

__all__ = ["BreachChecker", "get_breach_checker"]


def get_breach_checker() -> BreachChecker:
    """Checker selected by the PASSWORD_BREACH_CHECKER setting (dotted path)."""
    checker: BreachChecker = import_string(settings.PASSWORD_BREACH_CHECKER)()
    return checker
