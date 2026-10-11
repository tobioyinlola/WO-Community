"""The 44 sections of a business plan, as seed data.

The catalogue is stored in the database and admin managed (titles, guidance, inputs, switching a
section off); this file is only what a fresh install starts with. ``fields`` are profile fields
the section is written from, ``facts`` are research topics it may cite, and ``outputs`` are other
tools whose results it uses (``forecast``).
"""

from typing import Any

Section = tuple[int, str, str, str, dict[str, list[str]], list[str]]

CH1 = "Executive summary"
CH2 = "Problem and opportunity"
CH3 = "Solution and product"
CH4 = "Market"
CH5 = "Competition"
CH6 = "Business model and go to market"
CH7 = "Operations and milestones"
CH8 = "Team and organisation"
CH9 = "Financial plan"
CH10 = "Risk and compliance"
CH11 = "Appendix"

_PROFILE = ["name", "one_liner", "sector", "stage", "country", "city"]
_PROBLEM = ["problem", "problem_today", "problem_evidence", "target_customer"]
_SOLUTION = ["solution", "how_it_works", "key_features", "differentiator", "product_status"]
_MARKET = [
    "target_regions",
    "target_countries",
    "target_customer",
    "customer_type",
    "estimated_customers",
]
_MODEL = ["revenue_models", "price_points", "sales_channel"]
_FIN = {
    "fields": ["revenue_models", "price_points", "funding", "traction"],
    "outputs": ["forecast"],
    "facts": ["benchmarks"],
}

SECTIONS: list[Section] = [
    (
        1,
        CH1,
        "Executive summary",
        "A one page summary an investor can read first: the problem, the solution, the market, the "
        "model, the team and the ask.",
        {
            "fields": [*_PROFILE, "problem", "solution", "revenue_models", "target_regions"],
            "facts": [],
            "outputs": [],
        },
        ["name", "problem", "solution"],
    ),
    (
        2,
        CH1,
        "Business overview",
        "What the venture is, where it is based, its stage and what it does in plain language.",
        {"fields": [*_PROFILE, "startup_idea", "business_concept"], "facts": [], "outputs": []},
        ["startup_idea"],
    ),
    (
        3,
        CH1,
        "Mission and vision",
        "Why the venture exists and what it wants the world to look like. Only what the founders "
        "have said; no slogans.",
        {"fields": ["startup_idea", "business_concept", "problem"], "facts": [], "outputs": []},
        [],
    ),
    (
        4,
        CH1,
        "Key highlights",
        "The few facts that make the venture credible: traction, team, market, differentiation.",
        {
            "fields": ["traction", "team", "differentiator", "stage"],
            "facts": ["market_size"],
            "outputs": [],
        },
        [],
    ),
    (
        5,
        CH2,
        "The problem",
        "Who has the problem, how often, how much it costs them, and why it matters.",
        {"fields": _PROBLEM, "facts": [], "outputs": []},
        ["problem"],
    ),
    (
        6,
        CH2,
        "How the problem is solved today",
        "The current alternatives and workarounds, and why they fall short.",
        {
            "fields": ["problem_today", "problem", "competitors"],
            "facts": ["competition"],
            "outputs": [],
        },
        ["problem_today"],
    ),
    (
        7,
        CH2,
        "Evidence of the problem",
        "What shows the problem is real: interviews, surveys, usage, public data.",
        {"fields": ["problem_evidence", "problem"], "facts": ["market_size"], "outputs": []},
        ["problem_evidence"],
    ),
    (
        8,
        CH2,
        "The opportunity",
        "The size and urgency of the chance, and why now.",
        {
            "fields": ["problem", "solution", "target_regions", "sector"],
            "facts": ["market_size", "growth"],
            "outputs": [],
        },
        [],
    ),
    (
        9,
        CH3,
        "The solution",
        "What the venture offers and how it solves the problem, without jargon.",
        {"fields": _SOLUTION, "facts": [], "outputs": []},
        ["solution"],
    ),
    (
        10,
        CH3,
        "How it works",
        "The customer's journey from first contact to value, step by step.",
        {"fields": ["how_it_works", "solution"], "facts": [], "outputs": []},
        ["how_it_works"],
    ),
    (
        11,
        CH3,
        "Key features",
        "The few features that deliver the value and why customers care about each.",
        {"fields": ["key_features", "solution"], "facts": [], "outputs": []},
        ["key_features"],
    ),
    (
        12,
        CH3,
        "Product roadmap",
        "What exists today and what comes next, in order, using only plans the founders stated.",
        {
            "fields": ["product_status", "key_features", "stage", "funding"],
            "facts": [],
            "outputs": [],
        },
        [],
    ),
    (
        13,
        CH3,
        "Technology and infrastructure",
        "The technology the product relies on and what is built versus bought.",
        {"fields": ["solution", "how_it_works", "product_status"], "facts": [], "outputs": []},
        [],
    ),
    (
        14,
        CH3,
        "Differentiation and defensibility",
        "What makes the venture hard to copy: know how, data, relationships, regulation, brand.",
        {
            "fields": ["differentiator", "solution", "competitors"],
            "facts": ["competition"],
            "outputs": [],
        },
        ["differentiator"],
    ),
    (
        15,
        CH4,
        "Target customers",
        "Who the customers are, how they decide and how many there are.",
        {"fields": _MARKET, "facts": [], "outputs": []},
        ["target_customer"],
    ),
    (
        16,
        CH4,
        "Market size",
        "How big the market is, from sourced figures, and how the venture's share is reasoned.",
        {
            "fields": ["target_regions", "target_countries", "sector", "estimated_customers"],
            "facts": ["market_size"],
            "outputs": [],
        },
        [],
    ),
    (
        17,
        CH4,
        "Market trends and growth",
        "How the market is changing and what is driving it.",
        {"fields": ["sector", "target_regions"], "facts": ["growth", "market_size"], "outputs": []},
        [],
    ),
    (
        18,
        CH4,
        "Regional analysis",
        "How the target regions and countries differ for this venture.",
        {
            "fields": ["target_regions", "target_countries", "country"],
            "facts": ["market_size", "regulation"],
            "outputs": [],
        },
        ["target_regions"],
    ),
    (
        19,
        CH4,
        "Customer segments",
        "The main groups of customers, what each wants and how they are reached.",
        {
            "fields": ["target_customer", "customer_type", "estimated_customers"],
            "facts": [],
            "outputs": [],
        },
        [],
    ),
    (
        20,
        CH5,
        "Competitive landscape",
        "Who else serves these customers and how they compare, factually.",
        {"fields": ["competitors", "problem_today"], "facts": ["competition"], "outputs": []},
        ["competitors"],
    ),
    (
        21,
        CH5,
        "Competitive advantage",
        "Why customers will choose this venture, in terms they would recognise.",
        {
            "fields": ["differentiator", "solution", "competitors"],
            "facts": ["competition"],
            "outputs": [],
        },
        ["differentiator"],
    ),
    (
        22,
        CH5,
        "Positioning",
        "How the venture wants to be seen compared with the alternatives.",
        {"fields": ["one_liner", "differentiator", "target_customer"], "facts": [], "outputs": []},
        [],
    ),
    (
        23,
        CH6,
        "Business model",
        "How the venture creates, delivers and captures value.",
        {"fields": _MODEL + ["customer_type"], "facts": ["benchmarks"], "outputs": []},
        ["revenue_models"],
    ),
    (
        24,
        CH6,
        "Revenue streams",
        "Each way the venture earns money and who pays.",
        {"fields": ["revenue_models", "price_points"], "facts": [], "outputs": ["forecast"]},
        ["revenue_models"],
    ),
    (
        25,
        CH6,
        "Pricing strategy",
        "What is charged, why that level, and how price compares with the alternatives.",
        {
            "fields": ["price_points", "revenue_models", "customer_type"],
            "facts": ["benchmarks"],
            "outputs": ["forecast"],
        },
        ["price_points"],
    ),
    (
        26,
        CH6,
        "Sales channels",
        "How customers find and buy: direct, partners, marketplaces, agents.",
        {
            "fields": ["sales_channel", "target_customer", "customer_type"],
            "facts": [],
            "outputs": [],
        },
        ["sales_channel"],
    ),
    (
        27,
        CH6,
        "Marketing and customer acquisition",
        "How the venture will win its first and next customers, and what that costs.",
        {
            "fields": ["sales_channel", "target_customer", "target_regions"],
            "facts": ["benchmarks"],
            "outputs": ["forecast"],
        },
        [],
    ),
    (
        28,
        CH6,
        "Partnerships and distribution",
        "The partners the venture relies on or wants, and what each brings.",
        {"fields": ["traction", "sales_channel", "differentiator"], "facts": [], "outputs": []},
        [],
    ),
    (
        29,
        CH7,
        "Operating model",
        "How the venture runs day to day: people, processes, tools and locations.",
        {"fields": ["how_it_works", "team", "country", "city"], "facts": [], "outputs": []},
        [],
    ),
    (
        30,
        CH7,
        "Key suppliers and dependencies",
        "What the venture depends on that it does not control, and the fallback.",
        {"fields": ["solution", "how_it_works"], "facts": [], "outputs": []},
        [],
    ),
    (
        31,
        CH7,
        "Milestones and timeline",
        "The next 18 to 24 months in milestones, tied to funding where the founders stated it.",
        {
            "fields": ["stage", "product_status", "funding", "traction"],
            "facts": [],
            "outputs": ["forecast"],
        },
        [],
    ),
    (
        32,
        CH7,
        "Key metrics",
        "The measures the founders will watch and the targets they have stated.",
        {
            "fields": ["traction", "revenue_models"],
            "facts": ["benchmarks"],
            "outputs": ["forecast"],
        },
        [],
    ),
    (
        33,
        CH8,
        "The founding team",
        "Who the founders are and why they are the right people, from what they have said.",
        {"fields": ["team"], "facts": [], "outputs": []},
        ["team"],
    ),
    (
        34,
        CH8,
        "Advisors and mentors",
        "Advisors, mentors and supporters, if any.",
        {"fields": ["team"], "facts": [], "outputs": []},
        [],
    ),
    (
        35,
        CH8,
        "Hiring plan",
        "The roles the venture needs next and when.",
        {"fields": ["team", "funding"], "facts": [], "outputs": ["forecast"]},
        [],
    ),
    (
        36,
        CH8,
        "Organisation and governance",
        "Who decides what, ownership and how the team is organised.",
        {"fields": ["team"], "facts": [], "outputs": []},
        [],
    ),
    (
        37,
        CH9,
        "Financial overview",
        "The headline of the forecast: revenue, costs, cash and when the venture breaks even.",
        _FIN,
        [],
    ),
    (
        38,
        CH9,
        "Revenue forecast",
        "Revenue by stream over the forecast period and the assumptions behind it.",
        _FIN,
        [],
    ),
    (
        39,
        CH9,
        "Cost structure",
        "Where the money goes: cost of sales, people, marketing and fixed costs.",
        _FIN,
        [],
    ),
    (
        40,
        CH9,
        "Funding requirements and use of funds",
        "How much is needed, what it buys and what it achieves.",
        {"fields": ["funding", "traction"], "outputs": ["forecast"], "facts": []},
        [],
    ),
    (
        41,
        CH9,
        "Unit economics and break even",
        "What it costs to win a customer, what a customer is worth and when the venture "
        "reaches break even.",
        _FIN,
        [],
    ),
    (
        42,
        CH10,
        "Risks and mitigation",
        "The main risks, honestly stated, and what the founders will do about each.",
        {
            "fields": ["stage", "solution", "revenue_models", "competitors"],
            "facts": ["regulation", "competition"],
            "outputs": [],
        },
        [],
    ),
    (
        43,
        CH10,
        "Regulation and compliance",
        "Licences, approvals and rules that apply in the target regions.",
        {
            "fields": ["sector", "target_regions", "target_countries", "solution"],
            "facts": ["regulation"],
            "outputs": [],
        },
        [],
    ),
    (
        44,
        CH11,
        "Assumptions and sources",
        "The assumptions the plan rests on, and the sources cited.",
        {"fields": ["target_regions"], "facts": [], "outputs": ["forecast"]},
        [],
    ),
]


def seed_rows() -> list[dict[str, Any]]:
    return [
        {
            "number": n,
            "chapter": chapter,
            "title": title,
            "guidance": guidance,
            "depends_on": {
                "fields": dep.get("fields", []),
                "facts": dep.get("facts", []),
                "outputs": dep.get("outputs", []),
            },
            "required_inputs": required,
        }
        for n, chapter, title, guidance, dep, required in SECTIONS
    ]
