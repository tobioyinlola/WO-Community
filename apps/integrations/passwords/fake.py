from typing import ClassVar

from apps.integrations.passwords.base import BreachChecker


class FakeBreachChecker(BreachChecker):
    """Flags a fixed set of passwords. Never touches the network."""

    breached: ClassVar[set[str]] = {"Password123!456", "qwerty-qwerty-123"}

    def is_breached(self, password: str) -> bool:
        return password in self.breached
