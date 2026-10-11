"""Reads other tools use from forecasts, so they never reach into its tables."""

from typing import Any

from apps.toolkit.ventures.models import Venture


def headline(venture: Venture) -> dict[str, Any] | None:
    """The saved forecast's headline numbers, or ``None`` while the venture has no forecast.

    ``{"version": n, "currency": "NGN", "figures": {...}}``. Plans cite these as the venture's
    own numbers; they are never produced by a model.
    """
    return None
