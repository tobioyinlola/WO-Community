"""Small fixed-window counters on the shared cache.

Used for per-account and per-address limits that DRF's per-request throttles
cannot express, such as counting only failed logins.
"""

from django.core.cache import cache


def hit(key: str, window_seconds: int) -> int:
    """Count one event in the current window and return the new total."""
    cache.add(key, 0, window_seconds)
    try:
        return int(cache.incr(key))
    except ValueError:  # the key expired between add and incr
        cache.set(key, 1, window_seconds)
        return 1


def current(key: str) -> int:
    return int(cache.get(key, 0))


def reset(key: str) -> None:
    cache.delete(key)
