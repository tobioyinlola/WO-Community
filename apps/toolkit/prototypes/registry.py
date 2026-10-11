"""The components a prototype may use, and what each accepts.

A prototype is a tree of these. Nothing else can appear: no markup, no script, no address a member
typed. Navigation is only between the prototype's own screens. The front end draws each component
from its name and props; this registry is the contract both sides share.
"""

from typing import Any

# Prop kinds: ("text", max) ("enum", values) ("int", low, high) ("bool",) ("texts", items, max)
TEXT = ("text", 120)
LONG = ("text", 400)
SHORT = ("text", 40)
SIZE = ("enum", ("sm", "md", "lg"))
TONE = ("enum", ("neutral", "primary", "success", "warning", "danger"))
ALIGN = ("enum", ("start", "center", "end"))


def _c(
    category: str,
    label: str,
    props: dict[str, tuple[Any, ...]] | None = None,
    *,
    children: bool = False,
    action: bool = False,
) -> dict[str, Any]:
    return {
        "category": category,
        "label": label,
        "props": props or {},
        "children": children,
        "action": action,
    }


COMPONENTS: dict[str, dict[str, Any]] = {
    # layout
    "container": _c("layout", "Container", {"padding": SIZE, "tone": TONE}, children=True),
    "row": _c("layout", "Row", {"gap": SIZE, "align": ALIGN}, children=True),
    "column": _c("layout", "Column", {"gap": SIZE, "align": ALIGN}, children=True),
    "grid": _c("layout", "Grid", {"columns": ("int", 1, 4), "gap": SIZE}, children=True),
    "card": _c("layout", "Card", {"title": TEXT, "tone": TONE}, children=True, action=True),
    "divider": _c("layout", "Divider"),
    "spacer": _c("layout", "Spacer", {"size": SIZE}),
    "scroll": _c(
        "layout", "Scroll area", {"direction": ("enum", ("vertical", "horizontal"))}, children=True
    ),
    "tabs": _c("layout", "Tabs", {"labels": ("texts", 6, 30)}, children=True),
    "modal": _c("layout", "Dialog", {"title": TEXT}, children=True),
    # text
    "heading": _c("text", "Heading", {"text": TEXT, "level": ("int", 1, 4), "align": ALIGN}),
    "text": _c("text", "Text", {"text": LONG, "tone": TONE, "align": ALIGN}),
    "label": _c("text", "Label", {"text": SHORT}),
    "badge": _c("text", "Badge", {"text": SHORT, "tone": TONE}),
    "quote": _c("text", "Quote", {"text": LONG, "author": TEXT}),
    "list": _c("text", "List", {"items": ("texts", 12, 120), "ordered": ("bool",)}),
    "list_item": _c("text", "List item", {"title": TEXT, "subtitle": TEXT}, action=True),
    # inputs
    "text_input": _c(
        "input", "Text field", {"label": TEXT, "placeholder": TEXT, "required": ("bool",)}
    ),
    "email_input": _c(
        "input", "Email field", {"label": TEXT, "placeholder": TEXT, "required": ("bool",)}
    ),
    "password_input": _c("input", "Password field", {"label": TEXT, "required": ("bool",)}),
    "number_input": _c("input", "Number field", {"label": TEXT, "placeholder": SHORT}),
    "textarea": _c(
        "input", "Text area", {"label": TEXT, "placeholder": TEXT, "rows": ("int", 2, 10)}
    ),
    "select": _c("input", "Dropdown", {"label": TEXT, "options": ("texts", 12, 60)}),
    "checkbox": _c("input", "Checkbox", {"label": TEXT, "checked": ("bool",)}),
    "radio_group": _c("input", "Radio buttons", {"label": TEXT, "options": ("texts", 8, 60)}),
    "toggle": _c("input", "Switch", {"label": TEXT, "on": ("bool",)}),
    "slider": _c(
        "input", "Slider", {"label": TEXT, "min": ("int", 0, 1000), "max": ("int", 1, 1000)}
    ),
    "date_picker": _c("input", "Date", {"label": TEXT}),
    "search": _c("input", "Search field", {"placeholder": TEXT}),
    # actions
    "button": _c("action", "Button", {"text": SHORT, "tone": TONE, "size": SIZE}, action=True),
    "link": _c("action", "Link", {"text": SHORT}, action=True),
    "icon_button": _c("action", "Icon button", {"icon": SHORT, "label": SHORT}, action=True),
    "fab": _c("action", "Floating button", {"icon": SHORT, "label": SHORT}, action=True),
    # data
    "table": _c(
        "data",
        "Table",
        {"columns": ("texts", 6, 30), "rows": ("rows", 8, 6)},
    ),
    "stat": _c("data", "Figure", {"label": SHORT, "value": SHORT, "change": SHORT, "tone": TONE}),
    "chart_bar": _c(
        "data", "Bar chart", {"title": TEXT, "labels": ("texts", 12, 20), "values": ("numbers", 12)}
    ),
    "chart_line": _c(
        "data",
        "Line chart",
        {"title": TEXT, "labels": ("texts", 12, 20), "values": ("numbers", 12)},
    ),
    "progress": _c("data", "Progress", {"label": SHORT, "value": ("int", 0, 100)}),
    "avatar": _c("data", "Avatar", {"name": SHORT, "size": SIZE}),
    "image_placeholder": _c(
        "data", "Image", {"label": TEXT, "ratio": ("enum", ("1:1", "4:3", "16:9"))}
    ),
    "map_placeholder": _c("data", "Map", {"label": TEXT}),
    "rating": _c("data", "Rating", {"value": ("int", 0, 5)}),
    "timeline": _c("data", "Timeline", {"items": ("texts", 8, 80)}),
    # navigation
    "navbar": _c(
        "navigation", "Top bar", {"title": TEXT, "items": ("texts", 6, 20)}, children=True
    ),
    "tab_bar": _c("navigation", "Bottom tabs", {"labels": ("texts", 5, 20)}),
    "sidebar": _c("navigation", "Side menu", {"items": ("texts", 10, 30)}),
    "breadcrumbs": _c("navigation", "Breadcrumbs", {"items": ("texts", 5, 30)}),
    "stepper": _c("navigation", "Steps", {"steps": ("texts", 6, 30), "current": ("int", 1, 6)}),
    # feedback
    "alert": _c("feedback", "Alert", {"text": LONG, "tone": TONE}),
    "toast": _c("feedback", "Notice", {"text": TEXT, "tone": TONE}),
    "empty_state": _c("feedback", "Empty state", {"title": TEXT, "text": LONG}),
    "skeleton": _c("feedback", "Loading placeholder", {"lines": ("int", 1, 8)}),
}


def catalogue() -> list[dict[str, Any]]:
    """The registry in a form the editor can list."""
    out = []
    for name, spec in COMPONENTS.items():
        out.append(
            {
                "name": name,
                "label": spec["label"],
                "category": spec["category"],
                "children": spec["children"],
                "action": spec["action"],
                "props": {
                    prop: {"kind": rule[0], **_describe(rule)}
                    for prop, rule in spec["props"].items()
                },
            }
        )
    return out


def _describe(rule: tuple[Any, ...]) -> dict[str, Any]:
    kind = rule[0]
    if kind == "text":
        return {"max_length": rule[1]}
    if kind == "enum":
        return {"values": list(rule[1])}
    if kind == "int":
        return {"min": rule[1], "max": rule[2]}
    if kind == "texts":
        return {"max_items": rule[1], "max_length": rule[2]}
    if kind == "rows":
        return {"max_rows": rule[1], "max_columns": rule[2]}
    if kind == "numbers":
        return {"max_items": rule[1]}
    return {}
