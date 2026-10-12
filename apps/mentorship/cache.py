"""A version number that changes whenever mentor data does, so cached matches never go stale."""

from django.core.cache import cache

KEY = "mentorship:data-version"


def version() -> int:
    value = cache.get(KEY)
    if value is None:
        cache.add(KEY, 1, timeout=None)
        value = cache.get(KEY, 1)
    return int(value)


def bump() -> None:
    try:
        cache.incr(KEY)
    except ValueError:
        cache.add(KEY, 2, timeout=None)
