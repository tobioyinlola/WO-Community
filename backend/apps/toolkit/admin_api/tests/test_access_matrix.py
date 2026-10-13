"""Every toolkit route, tried as the people who must not get in.

The routes are discovered from the URL configuration, so a new endpoint is covered the day it is
added: it must refuse anonymous callers, refuse unapproved members, and answer 404 (not 403, not
200) to a different member asking about someone else's venture.
"""

import re
import uuid
from typing import Any

import pytest
from django.urls import URLPattern, URLResolver

from apps.toolkit import urls as toolkit_urls
from apps.toolkit.testing import BASE

pytestmark = pytest.mark.django_db

METHODS = ("get", "post", "put", "patch", "delete")
PUBLIC = {"tk-public-share"}
CATALOGUES = {
    "tk-forecast-templates",
    "tk-deck-templates",
    "tk-proto-components",
    "tk-proto-templates",
    "tk-shared",
}
CONVERTER = re.compile(r"<(?:(?P<kind>\w+):)?(?P<name>\w+)>")


def routes() -> list[tuple[str, str, Any]]:
    found: list[tuple[str, str, Any]] = []

    def walk(patterns: list[Any], prefix: str) -> None:
        for item in patterns:
            if isinstance(item, URLResolver):
                walk(item.url_patterns, prefix + str(item.pattern))
            elif isinstance(item, URLPattern) and item.name and item.name.startswith("tk-"):
                found.append((item.name, prefix + str(item.pattern), item.callback))

    walk(toolkit_urls.urlpatterns, "")
    return found


def fill(route: str, venture_id: str) -> str:
    def replace(match: re.Match[str]) -> str:
        name, kind = match.group("name"), match.group("kind")
        if name == "venture_id":
            return venture_id
        if kind == "uuid":
            return str(uuid.uuid4())
        if kind == "int":
            return "1"
        return "token"

    return BASE + "/" + CONVERTER.sub(replace, route)


def methods_of(callback: Any) -> list[str]:
    cls = getattr(callback, "cls", None) or getattr(callback, "view_class", None)
    return [m for m in METHODS if cls is not None and hasattr(cls, m)]


def test_the_route_list_is_not_empty():
    names = {n for n, _, _ in routes()}
    assert len(names) > 60
    assert {"tk-score", "tk-plan", "tk-forecast", "tk-decks", "tk-conversations"} <= names


def test_anonymous_callers_are_refused_everywhere(api_client, full_venture):
    failures = []
    for name, route, callback in routes():
        if name in PUBLIC:
            continue
        for method in methods_of(callback):
            response = getattr(api_client, method)(
                fill(route, full_venture["id"]), {}, format="json"
            )
            if response.status_code != 401:
                failures.append((name, method, response.status_code))
    assert not failures, failures


def test_unapproved_members_are_refused_everywhere(pending_client, full_venture):
    failures = []
    for name, route, callback in routes():
        if name in PUBLIC:
            continue
        for method in methods_of(callback):
            response = getattr(pending_client, method)(
                fill(route, full_venture["id"]), {}, format="json"
            )
            if response.status_code not in (403, 404):
                failures.append((name, method, response.status_code))
    assert not failures, failures


def test_another_members_venture_does_not_exist_for_everyone_else(other_client, full_venture):
    failures = []
    checked = 0
    for name, route, callback in routes():
        if name in PUBLIC or name.startswith("tk-admin") or "venture_id" not in route:
            continue
        if name in CATALOGUES:
            continue
        for method in methods_of(callback):
            checked += 1
            response = getattr(other_client, method)(
                fill(route, full_venture["id"]), {}, format="json"
            )
            if response.status_code != 404:
                failures.append((name, method, response.status_code))
    assert checked > 80
    assert not failures, failures


def test_jobs_and_exports_of_other_members_do_not_exist(client, other_client, full_venture):
    started = client.post(f"{BASE}/ventures/{full_venture['id']}/score")
    assert started.status_code == 202
    job = started.json()["id"]
    assert other_client.get(f"{BASE}/jobs/{job}").status_code == 404
    assert other_client.post(f"{BASE}/jobs/{job}/cancel").status_code == 404
    assert other_client.get(f"{BASE}/exports/{uuid.uuid4()}").status_code == 404


def test_admin_routes_need_staff_with_the_permission(client, api_client, full_venture):
    failures = []
    for name, route, callback in routes():
        if not name.startswith("tk-admin"):
            continue
        for method in methods_of(callback):
            url = fill(route, full_venture["id"])
            if api_client.generic(method.upper(), url).status_code != 401:
                failures.append((name, method, "anonymous"))
            if client.generic(method.upper(), url).status_code != 403:
                failures.append((name, method, "member"))
    assert not failures, failures
