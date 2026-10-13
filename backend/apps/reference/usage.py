"""How many records use each reference entry.

The reference lists sit at the bottom of the module stack, so they cannot look
at the startups and profiles that use them. Those modules register a counter
instead, and the admin screens and the delete guard ask the registry.
"""

from collections.abc import Callable

# Given a kind's slugs, returns how many records use each. One grouped query per module.
Counter = Callable[[list[str]], dict[str, int]]

_counters: dict[str, list[Counter]] = {}


def register(kind: str, counter: Counter) -> None:
    registered = _counters.setdefault(kind, [])
    if counter not in registered:
        registered.append(counter)


def counts(kind: str, slugs: list[str]) -> dict[str, int]:
    totals = dict.fromkeys(slugs, 0)
    for counter in _counters.get(kind, []):
        for slug, number in counter(slugs).items():
            totals[slug] = totals.get(slug, 0) + number
    return totals
