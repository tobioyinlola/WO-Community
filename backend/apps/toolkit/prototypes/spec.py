"""Checking a prototype's specification against the registry and its limits."""

import re
import secrets
from typing import Any

from django.conf import settings

from apps.core.text import plain
from apps.toolkit.prototypes.registry import COMPONENTS

KINDS = ("web", "mobile")
PALETTES = ("light", "dark", "warm", "forest")
FONTS = ("sans", "serif")
MAX_DEPTH = 8
MAX_NODES_PER_SCREEN = 120
MAX_NODES = 800
ID = re.compile(r"^[a-z0-9]{1,16}$")
ACTION_TYPES = ("navigate", "back", "none")


class InvalidSpec(Exception):
    def __init__(self, path: str, message: str) -> None:
        super().__init__(f"{path}: {message}")
        self.path = path
        self.message = message


class _Ctx:
    def __init__(self) -> None:
        self.ids: set[str] = set()
        self.nodes = 0
        self.screen_nodes = 0
        self.actions: list[tuple[str, str]] = []  # (path, screen id) to check at the end


def _new_id(ctx: _Ctx) -> str:
    while True:
        candidate = secrets.token_hex(4)
        if candidate not in ctx.ids:
            ctx.ids.add(candidate)
            return candidate


def _take_id(value: Any, path: str, ctx: _Ctx) -> str:
    if value in (None, ""):
        return _new_id(ctx)
    if not isinstance(value, str) or not ID.match(value) or value in ctx.ids:
        raise InvalidSpec(path, "An id is 1 to 16 lowercase letters or digits and must be unique.")
    ctx.ids.add(value)
    return value


def _prop(rule: tuple[Any, ...], value: Any, path: str) -> Any:
    kind = rule[0]
    if kind == "text":
        if not isinstance(value, str):
            raise InvalidSpec(path, "Must be text.")
        text = plain(value).strip()
        if len(text) > rule[1]:
            raise InvalidSpec(path, f"Too long ({rule[1]} characters at most).")
        return text
    if kind == "enum":
        if value not in rule[1]:
            raise InvalidSpec(path, "Choose one of: " + ", ".join(rule[1]) + ".")
        return value
    if kind == "int":
        if isinstance(value, bool) or not isinstance(value, int) or not rule[1] <= value <= rule[2]:
            raise InvalidSpec(path, f"A whole number from {rule[1]} to {rule[2]}.")
        return value
    if kind == "bool":
        if not isinstance(value, bool):
            raise InvalidSpec(path, "Must be true or false.")
        return value
    if kind == "texts":
        if not isinstance(value, list) or len(value) > rule[1]:
            raise InvalidSpec(path, f"A list of at most {rule[1]} items.")
        return [_prop(("text", rule[2]), v, path) for v in value]
    if kind == "numbers":
        if not isinstance(value, list) or len(value) > rule[1]:
            raise InvalidSpec(path, f"A list of at most {rule[1]} numbers.")
        for v in value:
            if isinstance(v, bool) or not isinstance(v, int | float) or abs(v) > 10**9:
                raise InvalidSpec(path, "Numbers only.")
        return list(value)
    if kind == "rows":
        if not isinstance(value, list) or len(value) > rule[1]:
            raise InvalidSpec(path, f"At most {rule[1]} rows.")
        return [
            [_prop(("text", 60), cell, path) for cell in row[: rule[2]]]
            for row in value
            if isinstance(row, list)
        ]
    raise InvalidSpec(path, "Unsupported property.")


def _node(node: Any, path: str, depth: int, ctx: _Ctx) -> dict[str, Any]:
    if not isinstance(node, dict) or node.get("component") not in COMPONENTS:
        raise InvalidSpec(f"{path}/component", "Not a known component.")
    if depth > MAX_DEPTH:
        raise InvalidSpec(path, f"Nested more than {MAX_DEPTH} levels.")
    ctx.nodes += 1
    ctx.screen_nodes += 1
    if ctx.screen_nodes > MAX_NODES_PER_SCREEN:
        raise InvalidSpec(path, f"A screen can have {MAX_NODES_PER_SCREEN} components.")
    if ctx.nodes > MAX_NODES:
        raise InvalidSpec(path, f"A prototype can have {MAX_NODES} components.")
    reg = COMPONENTS[node["component"]]
    given = node.get("props") or {}
    if not isinstance(given, dict):
        raise InvalidSpec(f"{path}/props", "Must be an object.")
    props: dict[str, Any] = {}
    for name, value in given.items():
        if name not in reg["props"]:
            raise InvalidSpec(f"{path}/props/{name}", "Not a property of this component.")
        props[name] = _prop(reg["props"][name], value, f"{path}/props/{name}")
    out: dict[str, Any] = {
        "id": _take_id(node.get("id"), f"{path}/id", ctx),
        "component": node["component"],
        "props": props,
        "children": [],
    }
    action = node.get("action")
    if action not in (None, {}):
        if not reg["action"]:
            raise InvalidSpec(f"{path}/action", "This component cannot navigate.")
        if not isinstance(action, dict) or action.get("type") not in ACTION_TYPES:
            raise InvalidSpec(f"{path}/action", "Use navigate, back or none.")
        out["action"] = {"type": action["type"]}
        if action["type"] == "navigate":
            target = action.get("screen")
            if not isinstance(target, str):
                raise InvalidSpec(f"{path}/action/screen", "Name the screen to go to.")
            out["action"]["screen"] = target
            ctx.actions.append((f"{path}/action/screen", target))
    children = node.get("children") or []
    if children and not reg["children"]:
        raise InvalidSpec(f"{path}/children", "This component cannot hold others.")
    if not isinstance(children, list):
        raise InvalidSpec(f"{path}/children", "Must be a list.")
    out["children"] = [
        _node(child, f"{path}/children/{i}", depth + 1, ctx) for i, child in enumerate(children)
    ]
    return out


def clean(spec: Any) -> dict[str, Any]:
    """The validated, cleaned specification, or ``InvalidSpec`` naming the first problem."""
    if not isinstance(spec, dict) or not isinstance(spec.get("screens"), list):
        raise InvalidSpec("/screens", "A prototype has a list of screens.")
    screens_in = spec["screens"]
    if not 1 <= len(screens_in) <= settings.PROTOTYPE_MAX_SCREENS:
        raise InvalidSpec("/screens", f"Between 1 and {settings.PROTOTYPE_MAX_SCREENS} screens.")
    kind = spec.get("kind", "web")
    if kind not in KINDS:
        raise InvalidSpec("/kind", "Web or mobile.")
    theme = spec.get("theme") or {}
    palette, font = theme.get("palette", "light"), theme.get("font", "sans")
    if palette not in PALETTES or font not in FONTS:
        raise InvalidSpec("/theme", "Unknown palette or font.")
    ctx = _Ctx()
    screens: list[dict[str, Any]] = []
    for i, screen in enumerate(screens_in):
        path = f"/screens/{i}"
        if not isinstance(screen, dict):
            raise InvalidSpec(path, "A screen is an object.")
        name = plain(str(screen.get("name", ""))).strip()
        if not 1 <= len(name) <= 60:
            raise InvalidSpec(f"{path}/name", "Between 1 and 60 characters.")
        ctx.screen_nodes = 0
        root = screen.get("root") or {"component": "container", "children": []}
        screens.append(
            {
                "id": _take_id(screen.get("id"), f"{path}/id", ctx),
                "name": name,
                "root": _node(root, f"{path}/root", 1, ctx),
            }
        )
    known = {s["id"] for s in screens}
    for path, target in ctx.actions:
        if target not in known:
            raise InvalidSpec(path, "That screen does not exist.")
    start = spec.get("start") or screens[0]["id"]
    if start not in known:
        raise InvalidSpec("/start", "The start screen does not exist.")
    return {
        "kind": kind,
        "theme": {"palette": palette, "font": font},
        "start": start,
        "screens": screens,
    }
