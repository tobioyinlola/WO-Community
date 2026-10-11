"""Sweep every route: a visitor with no login must get 401 from anything that is not public.

This catches a view that forgets its policy, a route added with the wrong one, and any endpoint
that answers (or crashes) before checking who is asking. Each route is tried with every method.
"""

import re
import uuid

import pytest
from django.urls import URLPattern, URLResolver, get_resolver

pytestmark = pytest.mark.django_db

METHODS = ("get", "post", "put", "patch", "delete")
SAMPLE_ID = str(uuid.uuid4())


def _walk(patterns, prefix=""):
    for pattern in patterns:
        if isinstance(pattern, URLResolver):
            yield from _walk(pattern.url_patterns, prefix + str(pattern.pattern))
        elif isinstance(pattern, URLPattern):
            yield prefix + str(pattern.pattern), pattern.callback


def _fill(route: str) -> str:
    """Turn a route pattern into a concrete path."""
    route = re.sub(r"<(?:uuid|int|slug|str):\w+>", lambda m: _sample(m.group(0)), route)

    def group(match: re.Match[str]) -> str:
        name, body = match.group(1), match.group(2)
        return SAMPLE_ID if name.endswith("id") else body.split("|")[0]

    route = re.sub(r"\(\?P<(\w+)>([^)]*)\)", group, route)
    return "/" + route.replace("^", "").replace("$", "")


def _sample(token: str) -> str:
    return SAMPLE_ID if token.startswith("<uuid") else "x"


def _non_public_routes():
    routes = []
    for route, callback in _walk(get_resolver().url_patterns):
        view_class = getattr(callback, "cls", None)
        policy = getattr(view_class, "policy", None)
        if policy is not None and policy.name != "public":
            routes.append(_fill(route))
    return sorted(set(routes))


ROUTES = _non_public_routes()


def test_the_sweep_actually_finds_the_routes():
    assert len(ROUTES) > 120
    assert any("/admin/" in r for r in ROUTES) and any("/me/" in r for r in ROUTES)


@pytest.mark.parametrize("route", ROUTES)
def test_visitors_get_401_from_every_protected_route(api_client, route):
    for method in METHODS:
        response = getattr(api_client, method)(route)
        assert (
            response.status_code == 401
        ), f"{method.upper()} {route} answered {response.status_code}"


ADMIN_ROUTES = [r for r in ROUTES if "/admin/" in r]


@pytest.mark.parametrize("route", ADMIN_ROUTES)
def test_ordinary_members_get_403_from_every_admin_route(make_user, client_for, route):
    from django.utils import timezone

    member = make_user(
        email="plain@example.com", approved_at=timezone.now(), email_verified_at=timezone.now()
    )
    client = client_for(member, mfa_age=5)
    for method in METHODS:
        response = getattr(client, method)(route)
        assert (
            response.status_code == 403
        ), f"{method.upper()} {route} answered {response.status_code}"


@pytest.mark.parametrize("route", ADMIN_ROUTES)
def test_admins_without_an_mfa_check_get_403_from_every_admin_route(make_user, client_for, route):
    admin = make_user(roles=("super_admin",), email="root@example.com")
    client = client_for(admin)  # logged in, but no second factor on the session
    for method in METHODS:
        response = getattr(client, method)(route)
        assert (
            response.status_code == 403
        ), f"{method.upper()} {route} answered {response.status_code}"
