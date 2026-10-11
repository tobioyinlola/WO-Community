"""The default rubric and the rules a rubric must satisfy.

A rubric is plain data so an admin can change weights, thresholds and what counts as evidence
without a release. The engine only reads it; it never contains a number a model produced.
"""

from typing import Any

DISCLAIMER = (
    "This score is an automated assessment from the information you entered and public sources "
    "we could find. It is guidance to help you decide what to do next, not a prediction of "
    "success, and not financial, legal or investment advice."
)

DEFAULT: dict[str, Any] = {
    "verdicts": [
        {"min": 75, "label": "Strong foundation"},
        {"min": 60, "label": "Promising, with gaps to close"},
        {"min": 40, "label": "Early stage: validate the basics"},
        {"min": 0, "label": "Not ready yet: start with the basics"},
    ],
    # A score needs at least this share of the weights to be backed by evidence.
    "min_scored_weight": 40,
    "dimensions": [
        {
            "key": "problem_clarity",
            "label": "Problem clarity",
            "weight": 15,
            "requires_any": ["problem"],
            "checks": [
                {
                    "field": "problem",
                    "min_length": 80,
                    "points": 30,
                    "tip": "Describe the problem in a few specific sentences.",
                },
                {
                    "field": "problem_today",
                    "min_length": 30,
                    "points": 20,
                    "tip": "Say how people deal with the problem today.",
                },
                {
                    "field": "problem_evidence",
                    "min_length": 30,
                    "points": 25,
                    "tip": "Add evidence the problem is real: interviews, numbers, quotes.",
                },
                {
                    "field": "target_customer",
                    "min_length": 30,
                    "points": 15,
                    "tip": "Describe exactly who has this problem.",
                },
                {
                    "field": "estimated_customers",
                    "present": True,
                    "points": 10,
                    "tip": "Estimate how many people or businesses have it.",
                },
            ],
        },
        {
            "key": "market",
            "label": "Market size and growth",
            "weight": 15,
            "fact_topics": ["market_size", "growth"],
            "min_facts": 1,
            # Annual growth in percent: the first band whose floor the figure reaches.
            "growth_bands": [[25, 90], [15, 80], [8, 65], [3, 45], [-1000, 20]],
            "size_bonus": 10,
            "base": 40,
            "tip": "Add the target regions and sector so market data can be found.",
        },
        {
            "key": "demand",
            "label": "Customer demand signals",
            "weight": 15,
            "requires_any": ["traction", "problem_evidence", "estimated_customers"],
            "checks": [
                {
                    "field": "traction.users",
                    "bands": [[1000, 40], [100, 30], [10, 20], [1, 10]],
                    "tip": "Record how many people use or have signed up for it.",
                },
                {
                    "field": "traction.pilots",
                    "bands": [[3, 25], [1, 15]],
                    "tip": "Run a pilot with a real customer and record it.",
                },
                {
                    "field": "traction.partnerships",
                    "bands": [[2, 15], [1, 10]],
                    "tip": "Record partnerships or letters of intent.",
                },
                {
                    "field": "problem_evidence",
                    "min_length": 30,
                    "points": 15,
                    "tip": "Add evidence of demand: waiting lists, surveys, interviews.",
                },
                {
                    "field": "estimated_customers",
                    "present": True,
                    "points": 5,
                    "tip": "Estimate how many customers you could reach.",
                },
            ],
        },
        {
            "key": "competition",
            "label": "Competition and differentiation",
            "weight": 10,
            "requires_any": ["competitors", "differentiator"],
            "checks": [
                {
                    "field": "differentiator",
                    "min_length": 30,
                    "points": 35,
                    "tip": "Explain what you do that others do not.",
                },
                {
                    "field": "competitors",
                    "min_count": 1,
                    "points": 20,
                    "tip": "List the competitors and alternatives your customers consider.",
                },
                {
                    "field": "competitors",
                    "min_count": 3,
                    "points": 20,
                    "tip": "List at least three competitors or alternatives.",
                },
                {
                    "field": "problem_today",
                    "min_length": 30,
                    "points": 25,
                    "tip": "Describe the current alternative customers use.",
                },
            ],
        },
        {
            "key": "business_model",
            "label": "Business model strength",
            "weight": 15,
            "requires_any": ["revenue_models"],
            "checks": [
                {
                    "field": "revenue_models",
                    "min_count": 1,
                    "points": 30,
                    "tip": "Choose how the venture earns money.",
                },
                {
                    "field": "price_points",
                    "min_count": 1,
                    "points": 30,
                    "tip": "Add at least one price point.",
                    "action": "open_forecast",
                },
                {
                    "field": "sales_channel",
                    "min_length": 15,
                    "points": 20,
                    "tip": "Say how customers will find and buy from you.",
                },
                {
                    "field": "customer_type",
                    "present": True,
                    "points": 10,
                    "tip": "Say whether customers are consumers, businesses or government.",
                },
                {
                    "field": "key_features",
                    "min_count": 1,
                    "points": 10,
                    "tip": "List the key features customers pay for.",
                },
            ],
        },
        {
            "key": "team",
            "label": "Team fit",
            "weight": 10,
            "requires_any": ["team"],
            "checks": [
                {
                    "field": "team",
                    "min_count": 1,
                    "points": 30,
                    "tip": "Add yourself and your co-founders.",
                    "action": "find_mentor",
                },
                {
                    "field": "team.founders",
                    "min_count": 2,
                    "points": 25,
                    "tip": "Add co-founders if you have them; two or more add resilience.",
                },
                {
                    "field": "team.roles",
                    "min_count": 2,
                    "points": 25,
                    "tip": "Cover more than one skill: product, technical, commercial.",
                },
                {
                    "field": "team.linkedin",
                    "min_count": 1,
                    "points": 20,
                    "tip": "Add a LinkedIn profile for at least one founder.",
                },
            ],
        },
        {
            "key": "traction",
            "label": "Traction",
            "weight": 10,
            "requires_any": ["traction", "stage"],
            "checks": [
                {
                    "field": "stage",
                    "bands_enum": {"revenue": 35, "launched": 25, "prototype": 10, "idea": 0},
                    "tip": "Keep your stage up to date.",
                },
                {
                    "field": "traction.revenue_minor",
                    "bands": [[1, 35]],
                    "tip": "Record revenue once you have it.",
                },
                {
                    "field": "traction.users",
                    "bands": [[500, 20], [50, 12], [1, 6]],
                    "tip": "Record users or customers.",
                },
                {"field": "traction.pilots", "bands": [[1, 10]], "tip": "Record pilots."},
            ],
        },
        {
            "key": "risk",
            "label": "Regulatory and operating risk",
            "weight": 10,
            "fact_topics": ["regulation"],
            "min_facts": 1,
            "base": 75,
            "penalty_words": [
                "licence",
                "license",
                "permit",
                "prohibited",
                "restricted",
                "capital requirement",
                "approval",
                "ban",
                "compliance",
            ],
            "penalty_each": 8,
            "max_penalty": 40,
            "tip": "Add your target regions and sector so regulation can be checked.",
        },
    ],
}


def validate(config: dict[str, Any]) -> list[str]:
    """Problems with a rubric, in words an admin can act on. Empty means usable."""
    problems: list[str] = []
    dims = config.get("dimensions")
    if not isinstance(dims, list) or not dims:
        return ["A rubric needs at least one dimension."]
    keys: set[str] = set()
    total = 0
    for dim in dims:
        key = dim.get("key", "")
        if not key or key in keys:
            problems.append(f"Dimension keys must be unique and not blank ({key or 'blank'}).")
        keys.add(key)
        weight = dim.get("weight")
        if not isinstance(weight, int) or not 1 <= weight <= 100:
            problems.append(f"{key}: weight must be a whole number from 1 to 100.")
        else:
            total += weight
        if "checks" not in dim and "fact_topics" not in dim:
            problems.append(f"{key}: needs checks or fact topics.")
    if total != 100:
        problems.append(f"Weights add up to {total}; they must add up to 100.")
    verdicts = config.get("verdicts") or []
    if not verdicts or min(v.get("min", 0) for v in verdicts) != 0:
        problems.append("Verdicts must cover every score, down to 0.")
    return problems
