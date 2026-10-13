"""Constants for toolkit tests. Imports nothing, so any module's tests can use it."""

from typing import Any

BASE = "/api/v1/toolkit"

# A profile with every field a score needs, for tests that start from a complete venture.
FULL_PROFILE: dict[str, Any] = {
    "name": "Mamapesa",
    "one_liner": "Instant working capital for market traders",
    "country": "NG",
    "city": "Lagos",
    "stage": "launched",
    "startup_idea": "A mobile wallet that gives market traders instant stock loans.",
    "target_regions": ["africa"],
    "target_countries": ["NG", "GH"],
    "customer_type": "businesses",
    "problem": "Market traders lose sales every week because they cannot buy stock on time.",
    "solution": "Traders get a small stock loan in minutes, repaid from daily sales.",
    "revenue_models": ["transaction_fee", "subscription"],
    "price_points": [
        {"label": "Pro", "amount_minor": 500000, "currency": "NGN", "period": "month"}
    ],
}
