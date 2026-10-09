from abc import ABC, abstractmethod


class BreachChecker(ABC):
    """Tells whether a password appears in known data breaches."""

    @abstractmethod
    def is_breached(self, password: str) -> bool:
        """True only when the password is known to be breached.

        Implementations must fail open: if the lookup cannot be completed they
        return False, so an outage at the provider never blocks sign-ups.
        """
