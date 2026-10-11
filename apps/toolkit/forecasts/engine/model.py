"""Twenty four months of revenue, costs and cash from a set of assumptions.

Everything is deterministic: the same assumptions always give the same figures, and no model or
network is involved. Money is whole minor units (kobo, cents) rounded half up each month; rates
are percentages as entered. The structure is the same for every template: a revenue driver
produces revenue and cost of sales, shared cost lines are added, then tax and funding give cash.
"""

from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Context, Decimal, localcontext
from typing import Any

MONTHS = 24
CURRENCIES = ("NGN", "KES", "GHS", "ZAR", "EGP", "USD")
TEMPLATES = (
    "subscription",
    "marketplace",
    "transaction_fee",
    "product_sales",
    "services",
    "licensing",
)
SCENARIOS = ("conservative", "base", "optimistic")
# How each scenario bends the base case: growth of volumes, churn, and operating costs.
SCENARIO_FACTORS: dict[str, dict[str, Decimal]] = {
    "conservative": {"growth": Decimal("0.6"), "churn": Decimal("1.3"), "cost": Decimal("1.1")},
    "base": {"growth": Decimal(1), "churn": Decimal(1), "cost": Decimal(1)},
    "optimistic": {"growth": Decimal("1.3"), "churn": Decimal("0.8"), "cost": Decimal("0.95")},
}

ZERO = Decimal(0)
ONE = Decimal(1)
HUNDRED = Decimal(100)


def dec(value: Any, default: str = "0") -> Decimal:
    if value is None or value == "":
        return Decimal(default)
    return Decimal(str(value))


CAP = 10**18  # a figure beyond this is meaningless; it is held here and flagged, not crashed on


def money(value: Decimal) -> int:
    if value >= CAP:
        return CAP
    if value <= -CAP:
        return -CAP
    return int(value.quantize(ONE, rounding=ROUND_HALF_UP))


def _pct(value: Any) -> Decimal:
    return dec(value) / HUNDRED


# What a member can set per template, with a sensible empty starting point. The key is the
# assumption name; ``kind`` tells the interface how to show it and the validator what to accept.
DRIVERS: dict[str, dict[str, dict[str, Any]]] = {
    "subscription": {
        "initial_customers": {"kind": "count", "default": 0},
        "new_customers_month1": {"kind": "count", "default": 20},
        "new_customer_growth_pct": {"kind": "pct", "default": 8, "max": 100},
        "churn_pct": {"kind": "pct", "default": 4, "max": 100},
        "price_minor": {"kind": "money", "default": 0},
        "price_growth_pct_year": {"kind": "pct", "default": 0, "max": 100},
    },
    "marketplace": {
        "gmv_month1_minor": {"kind": "money", "default": 0},
        "gmv_growth_pct": {"kind": "pct", "default": 10, "max": 100},
        "take_rate_pct": {"kind": "pct", "default": 10, "max": 100},
    },
    "transaction_fee": {
        "transactions_month1": {"kind": "count", "default": 100},
        "transactions_growth_pct": {"kind": "pct", "default": 10, "max": 100},
        "avg_value_minor": {"kind": "money", "default": 0},
        "fee_pct": {"kind": "pct", "default": 1.5, "max": 100},
        "fixed_fee_minor": {"kind": "money", "default": 0},
    },
    "product_sales": {
        "units_month1": {"kind": "count", "default": 50},
        "units_growth_pct": {"kind": "pct", "default": 8, "max": 100},
        "price_minor": {"kind": "money", "default": 0},
        "unit_cost_minor": {"kind": "money", "default": 0},
    },
    "services": {
        "billable_staff_start": {"kind": "count", "default": 2},
        "staff_added_per_quarter": {"kind": "count", "default": 1},
        "utilisation_pct": {"kind": "pct", "default": 65, "max": 100},
        "hours_per_month": {"kind": "count", "default": 160, "max": 744},
        "hourly_rate_minor": {"kind": "money", "default": 0},
        "staff_cost_minor": {"kind": "money", "default": 0},
    },
    "licensing": {
        "new_licences_month1": {"kind": "count", "default": 2},
        "new_licences_growth_pct": {"kind": "pct", "default": 6, "max": 100},
        "annual_fee_minor": {"kind": "money", "default": 0},
        "renewal_rate_pct": {"kind": "pct", "default": 85, "max": 100},
    },
}

# The cost lines every template shares.
COST_DEFAULTS: dict[str, Any] = {
    "cogs_pct": 15,
    "marketing_monthly_minor": 0,
    "marketing_growth_pct_month": 0,
    "salaries": [],  # {role, monthly_minor, count, start_month}
    "fixed": [],  # {label, monthly_minor}
    "annual_raise_pct": 0,
}

MAX_MONEY = 10**15  # minor units: keeps every product well inside what is meaningful


def defaults(template: str, currency: str = "NGN") -> dict[str, Any]:
    """A complete, valid starting assumption set for a template."""
    return {
        "template": template,
        "currency": currency,
        "opening_cash_minor": 0,
        "drivers": {k: v["default"] for k, v in DRIVERS[template].items()},
        "costs": {k: (list(v) if isinstance(v, list) else v) for k, v in COST_DEFAULTS.items()},
        "funding": [],  # {month, amount_minor, label}
        "tax_rate_pct": 0,
        "market_customers": None,  # the member's estimate, used only for a sanity check
    }


@dataclass
class Month:
    index: int  # 1 to 24
    revenue: int = 0
    cogs: int = 0
    gross_profit: int = 0
    marketing: int = 0
    salaries: int = 0
    fixed: int = 0
    opex: int = 0
    ebitda: int = 0
    tax: int = 0
    net_income: int = 0
    funding: int = 0
    cash_end: int = 0
    kpis: dict[str, int] = field(default_factory=dict)


@dataclass
class Result:
    scenario: str
    currency: str
    months: list[Month]
    summary: dict[str, Any]
    unit_economics: dict[str, Any]
    warnings: list[dict[str, str]]


class Invalid(Exception):
    def __init__(self, problems: list[dict[str, str]]) -> None:
        super().__init__("invalid assumptions")
        self.problems = problems


def validate(a: dict[str, Any]) -> list[dict[str, str]]:
    """Problems with a set of assumptions as ``{path, message}``. Empty means it can run."""
    problems: list[dict[str, str]] = []

    def bad(path: str, message: str) -> None:
        problems.append({"path": path, "message": message})

    template = a.get("template")
    if template not in TEMPLATES:
        bad("template", "Choose one of the revenue templates.")
        return problems
    if a.get("currency") not in CURRENCIES:
        bad("currency", "Choose one of: " + ", ".join(CURRENCIES) + ".")

    def number(path: str, value: Any, *, low: float = 0, high: float = float(MAX_MONEY)) -> None:
        if isinstance(value, bool) or not isinstance(value, int | float | str | Decimal):
            bad(path, "Enter a number.")
            return
        try:
            n = Decimal(str(value))
        except Exception:
            bad(path, "Enter a number.")
            return
        if not n.is_finite() or n < Decimal(str(low)) or n > Decimal(str(high)):
            bad(path, f"Enter a number from {low:g} to {high:g}.")

    number("opening_cash_minor", a.get("opening_cash_minor", 0))
    number("tax_rate_pct", a.get("tax_rate_pct", 0), high=100)
    drivers = a.get("drivers") or {}
    for name, spec in DRIVERS[template].items():
        value = drivers.get(name, spec["default"])
        high = float(spec.get("max", MAX_MONEY))
        number(f"drivers.{name}", value, high=high)
    for name in drivers:
        if name not in DRIVERS[template]:
            bad(f"drivers.{name}", "Not an assumption of this template.")
    costs = a.get("costs") or {}
    number("costs.cogs_pct", costs.get("cogs_pct", 0), high=100)
    number("costs.marketing_monthly_minor", costs.get("marketing_monthly_minor", 0))
    number("costs.marketing_growth_pct_month", costs.get("marketing_growth_pct_month", 0), high=100)
    number("costs.annual_raise_pct", costs.get("annual_raise_pct", 0), high=100)
    salaries = costs.get("salaries") or []
    if not isinstance(salaries, list) or len(salaries) > 30:
        bad("costs.salaries", "Add up to 30 roles.")
        salaries = []
    for i, row in enumerate(salaries):
        if not isinstance(row, dict):
            bad(f"costs.salaries.{i}", "Each role needs a name, a monthly cost and a count.")
            continue
        number(f"costs.salaries.{i}.monthly_minor", row.get("monthly_minor", 0))
        number(f"costs.salaries.{i}.count", row.get("count", 1), high=1000)
        number(f"costs.salaries.{i}.start_month", row.get("start_month", 1), low=1, high=MONTHS)
    fixed = costs.get("fixed") or []
    if not isinstance(fixed, list) or len(fixed) > 30:
        bad("costs.fixed", "Add up to 30 fixed costs.")
        fixed = []
    for i, row in enumerate(fixed):
        if not isinstance(row, dict):
            bad(f"costs.fixed.{i}", "Each cost needs a label and a monthly amount.")
            continue
        number(f"costs.fixed.{i}.monthly_minor", row.get("monthly_minor", 0))
    funding = a.get("funding") or []
    if not isinstance(funding, list) or len(funding) > 12:
        bad("funding", "Add up to 12 funding events.")
        funding = []
    for i, row in enumerate(funding):
        if not isinstance(row, dict):
            bad(f"funding.{i}", "Each event needs a month and an amount.")
            continue
        number(f"funding.{i}.month", row.get("month", 1), low=1, high=MONTHS)
        number(f"funding.{i}.amount_minor", row.get("amount_minor", 0))
    return problems


def _revenue_driver(
    template: str, d: dict[str, Any], t: int, state: dict[str, Decimal], f: dict[str, Decimal]
) -> tuple[Decimal, Decimal, dict[str, int]]:
    """Revenue, direct cost of sales for the month, and the month's KPIs."""
    grow = f["growth"]
    churn_f = f["churn"]

    def rate(name: str) -> Decimal:
        return _pct(d[name]) * grow

    if template == "subscription":
        new = dec(d["new_customers_month1"]) * (ONE + rate("new_customer_growth_pct")) ** (t - 1)
        prev = state.get("customers", dec(d["initial_customers"]))
        churned = prev * min(ONE, _pct(d["churn_pct"]) * churn_f)
        customers = prev + new - churned
        state["customers"] = customers
        state["new_total"] = state.get("new_total", ZERO) + new
        price = dec(d["price_minor"]) * (ONE + _pct(d["price_growth_pct_year"])) ** ((t - 1) // 12)
        return (
            customers * price,
            ZERO,
            {"customers": money(customers), "new_customers": money(new)},
        )
    if template == "marketplace":
        gmv = dec(d["gmv_month1_minor"]) * (ONE + rate("gmv_growth_pct")) ** (t - 1)
        return gmv * _pct(d["take_rate_pct"]), ZERO, {"gmv_minor": money(gmv)}
    if template == "transaction_fee":
        count = dec(d["transactions_month1"]) * (ONE + rate("transactions_growth_pct")) ** (t - 1)
        per = dec(d["avg_value_minor"]) * _pct(d["fee_pct"]) + dec(d["fixed_fee_minor"])
        volume = count * dec(d["avg_value_minor"])
        return count * per, ZERO, {"transactions": money(count), "volume_minor": money(volume)}
    if template == "product_sales":
        units = dec(d["units_month1"]) * (ONE + rate("units_growth_pct")) ** (t - 1)
        revenue = units * dec(d["price_minor"])
        return revenue, units * dec(d["unit_cost_minor"]), {"units": money(units)}
    if template == "services":
        staff = dec(d["billable_staff_start"]) + dec(d["staff_added_per_quarter"]) * (
            (t - 1) // 3
        ) * (grow)
        hours = staff * dec(d["hours_per_month"]) * _pct(d["utilisation_pct"])
        revenue = hours * dec(d["hourly_rate_minor"])
        return revenue, staff * dec(d["staff_cost_minor"]), {"billable_staff": money(staff)}
    # licensing
    new = dec(d["new_licences_month1"]) * (ONE + rate("new_licences_growth_pct")) ** (t - 1)
    prev = state.get("licences", ZERO)
    lapse = (ONE - _pct(d["renewal_rate_pct"])) * churn_f / Decimal(12)
    active = prev * (ONE - min(ONE, lapse)) + new
    state["licences"] = active
    state["new_total"] = state.get("new_total", ZERO) + new
    return active * dec(d["annual_fee_minor"]) / Decimal(12), ZERO, {"licences": money(active)}


def run(assumptions: dict[str, Any], scenario: str = "base", context: Any = None) -> Result:
    """Calculate the forecast. Raises ``Invalid`` when the assumptions cannot be used."""
    problems = validate(assumptions)
    if problems:
        raise Invalid(problems)
    if scenario not in SCENARIOS:
        raise Invalid([{"path": "scenario", "message": "Unknown scenario."}])
    with localcontext(Context(prec=120)):
        return _run(assumptions, scenario)


def _run(assumptions: dict[str, Any], scenario: str) -> Result:
    f = SCENARIO_FACTORS[scenario]
    template = assumptions["template"]
    d = {
        k: assumptions.get("drivers", {}).get(k, v["default"]) for k, v in DRIVERS[template].items()
    }
    costs = {**COST_DEFAULTS, **(assumptions.get("costs") or {})}
    tax_rate = _pct(assumptions.get("tax_rate_pct", 0))
    funding_by_month: dict[int, int] = {}
    for row in assumptions.get("funding") or []:
        m = int(dec(row.get("month", 1)))
        funding_by_month[m] = funding_by_month.get(m, 0) + money(dec(row.get("amount_minor", 0)))

    state: dict[str, Decimal] = {}
    months: list[Month] = []
    cash = money(dec(assumptions.get("opening_cash_minor", 0)))
    losses = ZERO  # carried forward against later profit
    cost_f = f["cost"]
    for t in range(1, MONTHS + 1):
        revenue_raw, direct_raw, kpis = _revenue_driver(template, d, t, state, f)
        revenue = money(revenue_raw)
        cogs = money(direct_raw + revenue_raw * _pct(costs["cogs_pct"]))
        year_step = (ONE + _pct(costs["annual_raise_pct"])) ** ((t - 1) // 12)
        marketing = money(
            dec(costs["marketing_monthly_minor"])
            * (ONE + _pct(costs["marketing_growth_pct_month"])) ** (t - 1)
            * cost_f
        )
        salaries = money(
            sum(
                (
                    dec(r.get("monthly_minor", 0)) * dec(r.get("count", 1), "1")
                    for r in costs["salaries"]
                    if int(dec(r.get("start_month", 1), "1")) <= t
                ),
                ZERO,
            )
            * year_step
            * cost_f
        )
        fixed = money(sum((dec(r.get("monthly_minor", 0)) for r in costs["fixed"]), ZERO) * cost_f)
        opex = marketing + salaries + fixed
        gross = revenue - cogs
        ebitda = gross - opex
        taxable = ZERO
        if ebitda > 0:
            taxable = max(ZERO, Decimal(ebitda) - losses)
            losses = max(ZERO, losses - Decimal(ebitda))
        else:
            losses += Decimal(-ebitda)
        tax = money(taxable * tax_rate)
        net = ebitda - tax
        inflow = funding_by_month.get(t, 0)
        cash = cash + net + inflow
        months.append(
            Month(
                index=t,
                revenue=revenue,
                cogs=cogs,
                gross_profit=gross,
                marketing=marketing,
                salaries=salaries,
                fixed=fixed,
                opex=opex,
                ebitda=ebitda,
                tax=tax,
                net_income=net,
                funding=inflow,
                cash_end=cash,
                kpis=kpis,
            )
        )
    summary = _summary(months, assumptions)
    return Result(
        scenario=scenario,
        currency=assumptions["currency"],
        months=months,
        summary=summary,
        unit_economics=_unit_economics(template, d, costs, months, state),
        warnings=_warnings(assumptions, months, summary),
    )


def _summary(months: list[Month], a: dict[str, Any]) -> dict[str, Any]:
    first, second = months[:12], months[12:]
    rev1, rev2 = sum(m.revenue for m in first), sum(m.revenue for m in second)
    lowest = min(months, key=lambda m: (m.cash_end, m.index))
    cash_out = next((m.index for m in months if m.cash_end < 0), None)
    break_even: int | None = None
    for i, m in enumerate(months):
        if all(x.ebitda >= 0 for x in months[i:]) and m.revenue > 0:
            break_even = m.index
            break
    opening = money(dec(a.get("opening_cash_minor", 0)))
    return {
        "revenue_year1": rev1,
        "revenue_year2": rev2,
        "gross_profit_year1": sum(m.gross_profit for m in first),
        "gross_profit_year2": sum(m.gross_profit for m in second),
        "gross_margin_pct_year1": (
            round(100 * sum(m.gross_profit for m in first) / rev1, 1) if rev1 else None
        ),
        "net_income_year1": sum(m.net_income for m in first),
        "net_income_year2": sum(m.net_income for m in second),
        "ending_cash": months[-1].cash_end,
        "lowest_cash": lowest.cash_end,
        "lowest_cash_month": lowest.index,
        "cash_out_month": cash_out,
        "runway_months": (cash_out - 1) if cash_out else None,  # None: lasts the whole period
        "break_even_month": break_even,
        "extra_funding_needed": max(0, -lowest.cash_end),
        "total_funding": sum(m.funding for m in months),
        "opening_cash": opening,
        "revenue_month24": months[-1].revenue,
        "annual_run_rate": months[-1].revenue * 12,
    }


def _unit_economics(
    template: str,
    d: dict[str, Any],
    costs: dict[str, Any],
    months: list[Month],
    state: dict[str, Decimal],
) -> dict[str, Any]:
    """Customer value measures, where the template has customers to measure them on."""
    out: dict[str, Any] = {"available": False}
    if template not in ("subscription", "licensing", "product_sales"):
        return out
    rev = sum(m.revenue for m in months)
    gross = sum(m.gross_profit for m in months)
    margin = (Decimal(gross) / Decimal(rev)) if rev else ZERO
    marketing = sum(m.marketing for m in months)
    if template == "subscription":
        price = dec(d["price_minor"])
        churn = _pct(d["churn_pct"])
        new_total = state.get("new_total", ZERO)
        cac = (Decimal(marketing) / new_total) if new_total and marketing else None
        monthly_margin = price * margin
        ltv = (monthly_margin / churn) if churn > 0 else None
        out = {
            "available": True,
            "revenue_per_customer_month": money(price),
            "lifetime_months": round(float(ONE / churn), 1) if churn > 0 else None,
            "ltv": money(ltv) if ltv is not None else None,
            "cac": money(cac) if cac is not None else None,
            "ltv_to_cac": round(float(ltv / cac), 1) if ltv and cac else None,
            "payback_months": (
                round(float(cac / monthly_margin), 1) if cac and monthly_margin > 0 else None
            ),
        }
    elif template == "licensing":
        fee = dec(d["annual_fee_minor"])
        lapse = ONE - _pct(d["renewal_rate_pct"])
        new_total = state.get("new_total", ZERO)
        cac = (Decimal(marketing) / new_total) if new_total and marketing else None
        ltv = (fee * margin / lapse) if lapse > 0 else None
        out = {
            "available": True,
            "revenue_per_customer_year": money(fee),
            "ltv": money(ltv) if ltv is not None else None,
            "cac": money(cac) if cac is not None else None,
            "ltv_to_cac": round(float(ltv / cac), 1) if ltv and cac else None,
        }
    else:
        unit = dec(d["price_minor"]) - dec(d["unit_cost_minor"])
        out = {
            "available": True,
            "contribution_per_unit": money(unit),
            "unit_margin_pct": (
                round(float(unit / dec(d["price_minor"]) * HUNDRED), 1)
                if dec(d["price_minor"]) > 0
                else None
            ),
        }
    return out


def _warnings(a: dict[str, Any], months: list[Month], s: dict[str, Any]) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []

    def warn(code: str, message: str, severity: str = "warning") -> None:
        out.append({"code": code, "severity": severity, "message": message})

    d = a.get("drivers", {})
    template = a["template"]
    growth_key = {
        "subscription": "new_customer_growth_pct",
        "marketplace": "gmv_growth_pct",
        "transaction_fee": "transactions_growth_pct",
        "product_sales": "units_growth_pct",
        "licensing": "new_licences_growth_pct",
    }.get(template)
    if growth_key and dec(d.get(growth_key, 0)) > 30:
        warn(
            "growth_very_high",
            f"Growth of {dec(d.get(growth_key))}% a month for two years is far above what most "
            "ventures achieve. Check it against what you have seen so far.",
        )
    if template == "subscription" and dec(d.get("churn_pct", 0)) < Decimal("0.5"):
        warn("churn_very_low", "Monthly churn under 0.5% is rare. Be ready to justify it.")
    if s["revenue_year1"] and (s["gross_margin_pct_year1"] or 0) > 95:
        warn("margin_very_high", "A gross margin above 95% leaves no room for direct costs.")
    if all(m.opex == 0 for m in months):
        warn("no_operating_costs", "No salaries, marketing or fixed costs are entered.")
    if s["revenue_year1"] == 0 and s["revenue_year2"] == 0:
        warn("no_revenue", "The assumptions produce no revenue. Check prices and volumes.", "error")
    if s["cash_out_month"] is not None:
        warn(
            "cash_runs_out",
            f"Cash runs out in month {s['cash_out_month']}. Extra funding of "
            f"{s['extra_funding_needed']} minor units is needed to stay positive.",
            "error",
        )
    if any(abs(m.revenue) >= CAP or abs(m.cash_end) >= CAP for m in months):
        warn(
            "figures_too_large",
            "These assumptions produce figures too large to be meaningful. Check the growth rates.",
            "error",
        )
    market = a.get("market_customers")
    if market:
        top = max((m.kpis.get("customers") or m.kpis.get("licences") or 0) for m in months)
        if top > int(dec(market)):
            warn(
                "beyond_market",
                "The forecast has more customers than the market size you estimated.",
            )
    return out


def sensitivity(assumptions: dict[str, Any], change_pct: int = 20) -> list[dict[str, Any]]:
    """How much year two revenue and the lowest cash move if each main assumption moves."""
    base = run(assumptions)
    template = assumptions["template"]
    names = [n for n, spec in DRIVERS[template].items() if spec["kind"] in ("pct", "money")]
    rows: list[dict[str, Any]] = []
    for name in names:
        value = dec(
            (assumptions.get("drivers") or {}).get(name, DRIVERS[template][name]["default"])
        )
        if value == 0:
            continue
        row: dict[str, Any] = {"assumption": f"drivers.{name}", "value": float(value)}
        for label, factor in (
            ("down", ONE - Decimal(change_pct) / HUNDRED),
            ("up", ONE + Decimal(change_pct) / HUNDRED),
        ):
            changed = {**assumptions, "drivers": {**assumptions.get("drivers", {})}}
            moved = value * factor
            cap = DRIVERS[template][name].get("max")
            if cap is not None:
                moved = min(moved, Decimal(str(cap)))
            changed["drivers"][name] = float(moved) if "." in str(moved) else int(moved)
            r = run(changed)
            row[label] = {
                "revenue_year2": r.summary["revenue_year2"],
                "revenue_year2_change": r.summary["revenue_year2"] - base.summary["revenue_year2"],
                "lowest_cash": r.summary["lowest_cash"],
                "lowest_cash_change": r.summary["lowest_cash"] - base.summary["lowest_cash"],
            }
        row["impact"] = max(
            abs(row["down"]["revenue_year2_change"]), abs(row["up"]["revenue_year2_change"])
        )
        rows.append(row)
    rows.sort(key=lambda r: (-r["impact"], r["assumption"]))
    return rows


def to_dict(result: Result) -> dict[str, Any]:
    return {
        "scenario": result.scenario,
        "currency": result.currency,
        "months": [
            {
                "month": m.index,
                "revenue": m.revenue,
                "cogs": m.cogs,
                "gross_profit": m.gross_profit,
                "marketing": m.marketing,
                "salaries": m.salaries,
                "fixed": m.fixed,
                "opex": m.opex,
                "ebitda": m.ebitda,
                "tax": m.tax,
                "net_income": m.net_income,
                "funding": m.funding,
                "cash_end": m.cash_end,
                "kpis": m.kpis,
            }
            for m in result.months
        ],
        "summary": result.summary,
        "unit_economics": result.unit_economics,
        "warnings": result.warnings,
    }
