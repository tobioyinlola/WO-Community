"""CI guard: every routed API view must declare a policy (default deny)."""

from django.urls import URLPattern, URLResolver, get_resolver

from apps.core.policies import Policy


def _views(patterns, prefix=""):
    for pattern in patterns:
        if isinstance(pattern, URLResolver):
            yield from _views(pattern.url_patterns, prefix + str(pattern.pattern))
        elif isinstance(pattern, URLPattern):
            yield prefix + str(pattern.pattern), pattern.callback


def test_every_route_declares_a_policy():
    missing = []
    count = 0
    for route, callback in _views(get_resolver().url_patterns):
        count += 1
        view_class = getattr(callback, "cls", None) or getattr(callback, "view_class", None)
        if view_class is None or not isinstance(getattr(view_class, "policy", None), Policy):
            missing.append(route)
    assert count > 0
    assert not missing, f"Routes without a policy: {missing}"
