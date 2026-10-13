"""The venture profile: its fields, their rules, completeness and what depends on what.

The profile is entered by the member. Validation applies to whatever is sent; the fields that
are required before a score can run are checked separately (``missing_required``), so the wizard
can save half finished steps.
"""

import re
from collections.abc import Callable
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, TypeAdapter, ValidationError

from apps.core.text import plain
from apps.toolkit.ventures import geo

SCORE_REQUIRED = (
    "name",
    "startup_idea",
    "target_regions",
    "problem",
    "solution",
    "revenue_models",
)
CURRENCIES = ("NGN", "KES", "GHS", "ZAR", "EGP", "USD")
Currency = Literal["NGN", "KES", "GHS", "ZAR", "EGP", "USD"]


def _text(min_length: int = 0, max_length: int = 2000) -> Any:
    return Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=min_length, max_length=max_length)
    ]


class PricePoint(BaseModel):
    model_config = ConfigDict(extra="forbid")
    label: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=60)]
    amount_minor: Annotated[int, Field(ge=0, le=10**12)]
    currency: Currency
    period: Literal["one_off", "day", "week", "month", "quarter", "year"] = "month"


class Traction(BaseModel):
    model_config = ConfigDict(extra="forbid")
    users: Annotated[int, Field(ge=0, le=10**9)] | None = None
    revenue_minor: Annotated[int, Field(ge=0, le=10**13)] | None = None
    currency: Currency | None = None
    pilots: Annotated[int, Field(ge=0, le=10**6)] | None = None
    partnerships: Annotated[int, Field(ge=0, le=10**6)] | None = None
    notes: Annotated[str, StringConstraints(max_length=1000)] = ""


class Funding(BaseModel):
    model_config = ConfigDict(extra="forbid")
    amount_minor: Annotated[int, Field(ge=0, le=10**13)] | None = None
    currency: Currency | None = None
    use_of_funds: Annotated[
        list[
            Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
        ],
        Field(max_length=8),
    ] = []
    timeline: Annotated[str, StringConstraints(max_length=200)] = ""


Region = Literal["north_america", "europe", "latin_america", "middle_east", "africa"]
RevenueModel = Literal[
    "subscription",
    "transaction_fee",
    "marketplace_commission",
    "product_sales",
    "services",
    "licensing",
    "advertising",
    "other",
]
REVENUE_MODELS = (
    "subscription",
    "transaction_fee",
    "marketplace_commission",
    "product_sales",
    "services",
    "licensing",
    "advertising",
    "other",
)

Step = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=300)]
Feature = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]

# Field name to the type it must satisfy. Text goes through ``plain`` first (see PRE).
TYPES: dict[str, Any] = {
    "name": _text(2, 80),
    "one_liner": _text(0, 160),
    "country": str,
    "city": _text(0, 80),
    "sector": _text(0, 80),
    "stage": Literal["idea", "prototype", "launched", "revenue"],
    "startup_idea": _text(20, 2000),
    "business_concept": _text(0, 2000),
    "target_regions": Annotated[list[Region], Field(min_length=1, max_length=5)],
    "target_countries": Annotated[list[str], Field(max_length=54)],
    "target_customer": _text(0, 1000),
    "customer_type": Literal["consumers", "businesses", "government", "mixed"],
    "estimated_customers": Annotated[int, Field(ge=0, le=10**10)],
    "problem": _text(20, 2000),
    "problem_today": _text(0, 2000),
    "problem_evidence": _text(0, 2000),
    "solution": _text(20, 2000),
    "how_it_works": Annotated[list[Step], Field(max_length=10)],
    "key_features": Annotated[list[Feature], Field(max_length=6)],
    "differentiator": _text(0, 1000),
    "product_status": Literal["concept", "in_development", "beta", "live"],
    "revenue_models": Annotated[list[RevenueModel], Field(min_length=1, max_length=8)],
    "price_points": Annotated[list[PricePoint], Field(max_length=10)],
    "sales_channel": _text(0, 500),
    "traction": Traction,
    "funding": Funding,
}
ADAPTERS: dict[str, TypeAdapter[Any]] = {name: TypeAdapter(tp) for name, tp in TYPES.items()}
FIELD_NAMES = tuple(TYPES)

_TEXT_FIELDS = {
    "name",
    "one_liner",
    "city",
    "sector",
    "startup_idea",
    "business_concept",
    "target_customer",
    "problem",
    "problem_today",
    "problem_evidence",
    "solution",
    "differentiator",
    "sales_channel",
}


def _upper_country(value: str) -> str:
    code = value.strip().upper()
    if code not in geo.COUNTRIES:
        raise ValueError("Use a two letter country code.")
    return code


def _african(codes: list[str]) -> list[str]:
    unique = list(dict.fromkeys(c.strip().upper() for c in codes))
    if any(c not in geo.AFRICA for c in unique):
        raise ValueError("Target countries must be African countries.")
    return unique


def _unique(values: list[Any]) -> list[Any]:
    return list(dict.fromkeys(values))


POST: dict[str, Callable[[Any], Any]] = {
    "country": _upper_country,
    "target_countries": _african,
    "target_regions": _unique,
    "revenue_models": _unique,
}

# Relative weights for completeness; competitors and team are rows, not fields.
WEIGHTS: dict[str, int] = {
    "name": 5,
    "one_liner": 3,
    "country": 2,
    "city": 1,
    "sector": 3,
    "stage": 3,
    "startup_idea": 10,
    "business_concept": 4,
    "target_regions": 6,
    "target_countries": 2,
    "target_customer": 5,
    "customer_type": 3,
    "estimated_customers": 2,
    "problem": 10,
    "problem_today": 3,
    "problem_evidence": 3,
    "solution": 10,
    "how_it_works": 3,
    "key_features": 3,
    "differentiator": 3,
    "product_status": 2,
    "revenue_models": 6,
    "price_points": 3,
    "sales_channel": 2,
    "competitors": 3,
    "team": 4,
    "traction": 3,
    "funding": 3,
}

# What goes out of date when a field changes.
_ALL_CONTENT = ("score", "plan", "deck", "prototype")
DEPENDENTS: dict[str, tuple[str, ...]] = {
    "name": ("plan", "deck", "prototype"),
    "one_liner": ("plan", "deck", "prototype"),
    "country": ("score", "plan", "forecast", "deck"),
    "city": ("plan", "deck"),
    "sector": ("score", "plan", "deck", "prototype"),
    "stage": ("score", "plan", "deck"),
    "startup_idea": _ALL_CONTENT,
    "business_concept": _ALL_CONTENT,
    "target_regions": ("score", "plan", "forecast", "deck"),
    "target_countries": ("score", "plan", "forecast", "deck"),
    "target_customer": ("score", "plan", "forecast", "deck"),
    "customer_type": ("score", "plan", "forecast", "deck"),
    "estimated_customers": ("score", "plan", "forecast", "deck"),
    "problem": _ALL_CONTENT,
    "problem_today": _ALL_CONTENT,
    "problem_evidence": ("score", "plan", "deck"),
    "solution": _ALL_CONTENT,
    "how_it_works": _ALL_CONTENT,
    "key_features": _ALL_CONTENT,
    "differentiator": _ALL_CONTENT,
    "product_status": ("score", "plan", "deck", "prototype"),
    "revenue_models": ("score", "plan", "forecast", "deck"),
    "price_points": ("score", "plan", "forecast", "deck"),
    "sales_channel": ("plan", "forecast", "deck"),
    "competitors": ("score", "plan", "deck"),
    "team": ("score", "plan", "deck"),
    "traction": ("score", "plan", "forecast", "deck"),
    "funding": ("plan", "forecast", "deck"),
}


class ProfileInvalid(Exception):
    def __init__(self, errors: dict[str, list[str]]) -> None:
        super().__init__("invalid profile")
        self.errors = errors


_CLEARED: tuple[Any, ...] = ("", None, [], {})


def _message(error: Any) -> str:
    return re.sub(r"^Value error, ", "", str(error.get("msg", "Invalid value.")))


def _dump(value: Any) -> Any:
    if isinstance(value, BaseModel):
        return value.model_dump()
    if isinstance(value, list):
        return [_dump(item) for item in value]
    return value


def validate_patch(patch: dict[str, Any]) -> dict[str, Any]:
    """Check only the fields sent. A cleared field (blank, null or empty) becomes ``None``."""
    unknown = sorted(set(patch) - set(FIELD_NAMES))
    if unknown:
        raise ProfileInvalid({name: ["Unknown field."] for name in unknown})
    cleaned: dict[str, Any] = {}
    errors: dict[str, list[str]] = {}
    for name, value in patch.items():
        if isinstance(value, str) and name in _TEXT_FIELDS:
            value = plain(value)
        if value in _CLEARED:
            cleaned[name] = None
            continue
        try:
            built = ADAPTERS[name].validate_python(value)
            if name in POST:
                built = POST[name](built)
        except ValidationError as exc:
            errors[name] = [_message(e) for e in exc.errors()] or ["Invalid value."]
            continue
        except ValueError as exc:
            errors[name] = [str(exc)]
            continue
        cleaned[name] = _dump(built)
    if errors:
        raise ProfileInvalid(errors)
    return cleaned


def cross_check(fields: dict[str, Any]) -> dict[str, list[str]]:
    """Rules that involve several fields."""
    errors: dict[str, list[str]] = {}
    if fields.get("target_countries") and "africa" not in (fields.get("target_regions") or []):
        errors["target_countries"] = ["Choose Africa as a target region to name countries."]
    return errors


def is_filled(name: str, fields: dict[str, Any], *, competitors: int, team: int) -> bool:
    if name == "competitors":
        return competitors > 0
    if name == "team":
        return team > 0
    value = fields.get(name)
    if isinstance(value, dict):
        return any(v not in _CLEARED and v != [] for v in value.values())
    return value not in _CLEARED


def completeness(fields: dict[str, Any], *, competitors: int, team: int) -> int:
    total = sum(WEIGHTS.values())
    done = sum(
        weight
        for name, weight in WEIGHTS.items()
        if is_filled(name, fields, competitors=competitors, team=team)
    )
    return round(100 * done / total)


def missing_required(fields: dict[str, Any]) -> list[str]:
    return [name for name in SCORE_REQUIRED if fields.get(name) in _CLEARED]
