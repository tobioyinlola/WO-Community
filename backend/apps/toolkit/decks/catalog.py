"""Deck templates as seed data. The database holds the live copies (admin managed).

A slide spec is a layout, a title and element specs. An element spec either carries fixed text
(``text``) or says what to copy from the venture (``fill``): a profile field, or ``linked`` data
that is looked up when the deck is shown so figures never drift from the forecast.
"""

from typing import Any

Spec = dict[str, Any]


def _h(text: str) -> Spec:
    return {"type": "heading", "text": text}


def _t(fill: str) -> Spec:
    return {"type": "text", "fill": fill}


def _b(fill: str) -> Spec:
    return {"type": "bullets", "fill": fill}


def _profile(ref: str) -> Spec:
    return {"type": "linked", "kind": "profile_field", "ref": ref}


def _metric(ref: str, label: str) -> Spec:
    return {"type": "linked", "kind": "forecast_metric", "ref": ref, "label": label}


def _series(ref: str, label: str) -> Spec:
    return {"type": "linked", "kind": "forecast_series", "ref": ref, "label": label}


TITLE: Spec = {
    "layout": "title",
    "title": "",
    "elements": [{"type": "linked", "kind": "profile_field", "ref": "name"}, _profile("one_liner")],
}
PROBLEM: Spec = {
    "layout": "statement",
    "title": "The problem",
    "elements": [_t("problem"), _t("problem_today")],
}
SOLUTION: Spec = {
    "layout": "statement",
    "title": "Our solution",
    "elements": [_t("solution")],
}
HOW: Spec = {"layout": "bullets", "title": "How it works", "elements": [_b("how_it_works")]}
PRODUCT: Spec = {"layout": "bullets", "title": "What you get", "elements": [_b("key_features")]}
MARKET: Spec = {
    "layout": "statement",
    "title": "The market",
    "elements": [_t("target_customer"), _t("estimated_customers")],
}
MODEL: Spec = {
    "layout": "bullets",
    "title": "How we make money",
    "elements": [_b("revenue_models"), _t("sales_channel")],
}
TRACTION: Spec = {
    "layout": "metrics",
    "title": "Traction",
    "elements": [
        {"type": "metric", "fill": "traction.users", "label": "Users"},
        {"type": "metric", "fill": "traction.pilots", "label": "Pilots"},
        {"type": "metric", "fill": "traction.partnerships", "label": "Partnerships"},
        {"type": "metric", "fill": "traction.revenue_minor", "label": "Revenue to date"},
    ],
}
COMPETITION: Spec = {
    "layout": "statement",
    "title": "Competition",
    "elements": [
        {"type": "linked", "kind": "competitors"},
        _t("differentiator"),
    ],
}
FINANCIALS: Spec = {
    "layout": "metrics",
    "title": "The numbers",
    "elements": [
        _metric("revenue_year1", "Year 1 revenue"),
        _metric("revenue_year2", "Year 2 revenue"),
        _metric("break_even_month", "Break even month"),
        _series("revenue", "Revenue by quarter"),
    ],
}
TEAM: Spec = {
    "layout": "team",
    "title": "The team",
    "elements": [{"type": "linked", "kind": "team"}],
}
ASK: Spec = {
    "layout": "bullets",
    "title": "The ask",
    "elements": [_metric("total_funding", "Raising"), _b("use_of_funds")],
}
CLOSING: Spec = {
    "layout": "closing",
    "title": "Thank you",
    "elements": [_profile("name"), _profile("one_liner")],
}

TEMPLATES: list[dict[str, Any]] = [
    {
        "slug": "investor_pitch",
        "name": "Investor pitch",
        "description": "The full story for an investor meeting: 13 slides.",
        "slides": [
            TITLE,
            PROBLEM,
            SOLUTION,
            HOW,
            PRODUCT,
            MARKET,
            MODEL,
            TRACTION,
            COMPETITION,
            FINANCIALS,
            TEAM,
            ASK,
            CLOSING,
        ],
    },
    {
        "slug": "demo_day",
        "name": "Demo day (three minutes)",
        "description": "A short talk for a stage: 8 slides.",
        "slides": [TITLE, PROBLEM, SOLUTION, TRACTION, MARKET, MODEL, TEAM, ASK],
    },
    {
        "slug": "accelerator",
        "name": "Accelerator application",
        "description": "What programmes usually ask to see: 10 slides.",
        "slides": [
            TITLE,
            PROBLEM,
            SOLUTION,
            MARKET,
            MODEL,
            TRACTION,
            COMPETITION,
            FINANCIALS,
            TEAM,
            ASK,
        ],
    },
    {
        "slug": "teaser",
        "name": "Teaser",
        "description": "Five slides to send before a call.",
        "slides": [TITLE, PROBLEM, SOLUTION, TRACTION, TEAM],
    },
]
