"""Starting prototypes, as seed data. The database holds the live copies (admin managed).

Each is a few screens built from registry components. ``{name}`` in text is replaced with the
venture's name when a prototype is made from it.
"""

from typing import Any

Node = dict[str, Any]


def n(component: str, props: dict[str, Any] | None = None, *children: Node, **extra: Any) -> Node:
    node: Node = {"component": component, "props": props or {}, "children": list(children)}
    node.update(extra)
    return node


def go(screen: str) -> dict[str, str]:
    return {"type": "navigate", "screen": screen}


def screen(sid: str, name: str, *children: Node) -> dict[str, Any]:
    return {"id": sid, "name": name, "root": n("container", {"padding": "md"}, *children)}


def bar(title: str = "{name}") -> Node:
    return n("navbar", {"title": title, "items": ["Home", "About"]})


def spec(kind: str, *screens: dict[str, Any], palette: str = "light") -> dict[str, Any]:
    return {
        "kind": kind,
        "theme": {"palette": palette, "font": "sans"},
        "start": screens[0]["id"],
        "screens": list(screens),
    }


def _landing() -> dict[str, Any]:
    return spec(
        "web",
        screen(
            "home",
            "Home",
            bar(),
            n("heading", {"text": "{name}", "level": 1, "align": "center"}),
            n("text", {"text": "Say in one sentence what you do and for whom.", "align": "center"}),
            n(
                "button",
                {"text": "Get started", "tone": "primary", "size": "lg"},
                action=go("signup"),
            ),
            n(
                "grid",
                {"columns": 3, "gap": "md"},
                n("card", {"title": "Feature one"}, n("text", {"text": "What it does for you."})),
                n("card", {"title": "Feature two"}, n("text", {"text": "Why it matters."})),
                n("card", {"title": "Feature three"}, n("text", {"text": "How it saves time."})),
            ),
        ),
        screen(
            "signup",
            "Sign up",
            bar(),
            n("heading", {"text": "Create your account", "level": 2}),
            n("text_input", {"label": "Full name", "required": True}),
            n("email_input", {"label": "Email", "required": True}),
            n("password_input", {"label": "Password", "required": True}),
            n("button", {"text": "Create account", "tone": "primary"}, action=go("home")),
        ),
    )


def _onboarding() -> dict[str, Any]:
    return spec(
        "mobile",
        screen(
            "welcome",
            "Welcome",
            n("image_placeholder", {"label": "Welcome picture", "ratio": "4:3"}),
            n("heading", {"text": "Welcome to {name}", "level": 1, "align": "center"}),
            n("text", {"text": "A short line on the benefit.", "align": "center"}),
            n("button", {"text": "Continue", "tone": "primary"}, action=go("profile")),
        ),
        screen(
            "profile",
            "About you",
            n("stepper", {"steps": ["Account", "About you", "Done"], "current": 2}),
            n("text_input", {"label": "Your name"}),
            n("select", {"label": "I am a", "options": ["Customer", "Business", "Student"]}),
            n("button", {"text": "Next", "tone": "primary"}, action=go("done")),
        ),
        screen(
            "done",
            "All set",
            n("empty_state", {"title": "You are ready", "text": "Everything is set up."}),
            n("button", {"text": "Start", "tone": "primary"}, action=go("welcome")),
        ),
    )


def _dashboard() -> dict[str, Any]:
    return spec(
        "web",
        screen(
            "overview",
            "Overview",
            bar(),
            n(
                "row",
                {"gap": "md"},
                n("stat", {"label": "Revenue", "value": "0", "change": "+0%", "tone": "success"}),
                n("stat", {"label": "Customers", "value": "0", "change": "+0%"}),
                n("stat", {"label": "Orders", "value": "0", "change": "+0%"}),
            ),
            n(
                "chart_bar",
                {"title": "Sales by month", "labels": ["Jan", "Feb", "Mar"], "values": [3, 5, 8]},
            ),
            n(
                "table",
                {
                    "columns": ["Name", "Status", "Amount"],
                    "rows": [["Example one", "Paid", "0"], ["Example two", "Pending", "0"]],
                },
            ),
        ),
    )


def _marketplace() -> dict[str, Any]:
    return spec(
        "mobile",
        screen(
            "browse",
            "Browse",
            n("search", {"placeholder": "Search listings"}),
            n(
                "list_item",
                {"title": "Listing one", "subtitle": "Seller, location"},
                action=go("listing"),
            ),
            n(
                "list_item",
                {"title": "Listing two", "subtitle": "Seller, location"},
                action=go("listing"),
            ),
            n("tab_bar", {"labels": ["Browse", "Saved", "Account"]}),
        ),
        screen(
            "listing",
            "Listing",
            n("image_placeholder", {"label": "Photo", "ratio": "4:3"}),
            n("heading", {"text": "Listing one", "level": 2}),
            n("rating", {"value": 4}),
            n("text", {"text": "Describe what is on offer."}),
            n("button", {"text": "Buy now", "tone": "primary"}, action=go("checkout")),
        ),
        screen(
            "checkout",
            "Checkout",
            n("stepper", {"steps": ["Cart", "Pay", "Done"], "current": 2}),
            n("text_input", {"label": "Delivery address"}),
            n("radio_group", {"label": "Payment", "options": ["Card", "Mobile money", "Cash"]}),
            n("button", {"text": "Place order", "tone": "primary"}, action=go("browse")),
        ),
    )


def _booking() -> dict[str, Any]:
    return spec(
        "mobile",
        screen(
            "services",
            "Services",
            n("heading", {"text": "Book with {name}", "level": 2}),
            n(
                "card",
                {"title": "Service one"},
                n("text", {"text": "30 minutes"}),
                action=go("when"),
            ),
            n(
                "card",
                {"title": "Service two"},
                n("text", {"text": "60 minutes"}),
                action=go("when"),
            ),
        ),
        screen(
            "when",
            "Choose a time",
            n("date_picker", {"label": "Date"}),
            n("select", {"label": "Time", "options": ["09:00", "11:00", "14:00", "16:00"]}),
            n("button", {"text": "Confirm", "tone": "primary"}, action=go("confirmed")),
        ),
        screen(
            "confirmed",
            "Booked",
            n("alert", {"text": "Your booking is confirmed.", "tone": "success"}),
            n("button", {"text": "Back to services"}, action=go("services")),
        ),
    )


def _learning() -> dict[str, Any]:
    return spec(
        "web",
        screen(
            "courses",
            "Courses",
            bar(),
            n(
                "grid",
                {"columns": 2},
                n(
                    "card",
                    {"title": "Course one"},
                    n("progress", {"label": "Progress", "value": 40}),
                    action=go("lesson"),
                ),
                n(
                    "card",
                    {"title": "Course two"},
                    n("progress", {"label": "Progress", "value": 0}),
                    action=go("lesson"),
                ),
            ),
        ),
        screen(
            "lesson",
            "Lesson",
            bar(),
            n("breadcrumbs", {"items": ["Courses", "Course one", "Lesson 1"]}),
            n("heading", {"text": "Lesson 1", "level": 2}),
            n("text", {"text": "Lesson text goes here."}),
            n("button", {"text": "Next lesson", "tone": "primary"}, action=go("courses")),
        ),
    )


def _settings() -> dict[str, Any]:
    return spec(
        "web",
        screen(
            "account",
            "Account",
            bar(),
            n("heading", {"text": "Settings", "level": 2}),
            n("text_input", {"label": "Display name"}),
            n("toggle", {"label": "Email me about updates", "on": True}),
            n("toggle", {"label": "Dark mode"}),
            n("button", {"text": "Save changes", "tone": "primary"}),
        ),
    )


def _admin() -> dict[str, Any]:
    return spec(
        "web",
        screen(
            "list",
            "Records",
            bar("{name} admin"),
            n("search", {"placeholder": "Search records"}),
            n(
                "table",
                {
                    "columns": ["Name", "Owner", "Updated"],
                    "rows": [["Record one", "Ada", "Today"], ["Record two", "Tunde", "Yesterday"]],
                },
            ),
            n("button", {"text": "Add record", "tone": "primary"}, action=go("edit")),
        ),
        screen(
            "edit",
            "Edit record",
            bar("{name} admin"),
            n("text_input", {"label": "Name"}),
            n("textarea", {"label": "Notes", "rows": 4}),
            n("button", {"text": "Save", "tone": "primary"}, action=go("list")),
        ),
    )


def _feed() -> dict[str, Any]:
    return spec(
        "mobile",
        screen(
            "feed",
            "Updates",
            n("heading", {"text": "What is new", "level": 2}),
            n(
                "card",
                {"title": "Update one"},
                n("avatar", {"name": "Ada"}),
                n("text", {"text": "A short update."}),
                action=go("detail"),
            ),
            n("fab", {"icon": "plus", "label": "New"}, action=go("detail")),
            n("tab_bar", {"labels": ["Home", "Explore", "Me"]}),
        ),
        screen(
            "detail",
            "Detail",
            n("timeline", {"items": ["Created", "Reviewed", "Published"]}),
            n("button", {"text": "Back"}, action={"type": "back"}),
        ),
    )


TEMPLATES: list[dict[str, Any]] = [
    {
        "slug": "landing",
        "name": "Landing page",
        "description": "A page that explains the offer and signs people up.",
        "spec": _landing(),
    },
    {
        "slug": "onboarding",
        "name": "Onboarding flow",
        "description": "Three steps from welcome to ready.",
        "spec": _onboarding(),
    },
    {
        "slug": "dashboard",
        "name": "Dashboard",
        "description": "Key figures, a chart and a table.",
        "spec": _dashboard(),
    },
    {
        "slug": "marketplace",
        "name": "Marketplace app",
        "description": "Browse, view a listing, check out.",
        "spec": _marketplace(),
    },
    {
        "slug": "booking",
        "name": "Booking app",
        "description": "Pick a service, a time and confirm.",
        "spec": _booking(),
    },
    {
        "slug": "learning",
        "name": "Learning platform",
        "description": "Courses with progress and a lesson page.",
        "spec": _learning(),
    },
    {
        "slug": "settings",
        "name": "Account settings",
        "description": "A simple settings page.",
        "spec": _settings(),
    },
    {
        "slug": "admin",
        "name": "Admin console",
        "description": "A searchable list and an edit form.",
        "spec": _admin(),
    },
    {
        "slug": "updates",
        "name": "Updates feed",
        "description": "A feed with detail and a new-item button.",
        "spec": _feed(),
    },
]
