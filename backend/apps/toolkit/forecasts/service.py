"""The forecast: assumptions the founder owns, figures the engine calculates.

A model never produces a number that ends up in a forecast. It may *propose* an assumption from a
sourced benchmark; the proposal is returned for the founder to accept, and the engine does all the
arithmetic from what they saved.
"""

from typing import Any
from uuid import UUID

from django.db import transaction
from rest_framework import exceptions

from apps.core.errors import ConflictError
from apps.toolkit.ai import runner
from apps.toolkit.ai.models import Fact
from apps.toolkit.ai.research import gather
from apps.toolkit.forecasts import engine
from apps.toolkit.forecasts.models import Forecast, ForecastVersion
from apps.toolkit.jobs import exports
from apps.toolkit.jobs.services import JobContext, JobFailed
from apps.toolkit.ventures import services as ventures
from apps.toolkit.ventures.models import Venture
from apps.toolkit.ventures.selectors import profile_of

MODEL_TO_TEMPLATE = {
    "subscription": "subscription",
    "transaction_fee": "transaction_fee",
    "marketplace_commission": "marketplace",
    "product_sales": "product_sales",
    "services": "services",
    "licensing": "licensing",
}
COUNTRY_CURRENCY = {"NG": "NGN", "KE": "KES", "GH": "GHS", "ZA": "ZAR", "EG": "EGP"}
VERSIONS_KEPT = 30


def get(venture: Venture) -> Forecast | None:
    return Forecast.objects.filter(venture=venture).first()


def seed_assumptions(venture: Venture) -> dict[str, Any]:
    """A starting point from the profile: its template, currency, price and funding."""
    return seed_from_fields(profile_of(venture).fields)


def seed_from_fields(fields: dict[str, Any]) -> dict[str, Any]:
    """The same, from profile fields alone (no database), so it can be checked in bulk."""
    template = next(
        (MODEL_TO_TEMPLATE[m] for m in fields.get("revenue_models", []) if m in MODEL_TO_TEMPLATE),
        "subscription",
    )
    prices = fields.get("price_points") or []
    currency = (
        (prices[0].get("currency") if prices else None)
        or (fields.get("funding") or {}).get("currency")
        or COUNTRY_CURRENCY.get(fields.get("country", ""), "USD")
    )
    a = engine.defaults(template, currency)
    if prices:
        first = prices[0]
        amount = int(first["amount_minor"])
        per = {"year": 12, "quarter": 3}.get(first.get("period", "month"), 1)
        if template in ("subscription",):
            a["drivers"]["price_minor"] = round(amount / per)
        elif template == "licensing":
            a["drivers"]["annual_fee_minor"] = amount * (12 // per if per in (1, 3, 12) else 1)
        elif template == "product_sales":
            a["drivers"]["price_minor"] = amount
        elif template == "services":
            a["drivers"]["hourly_rate_minor"] = amount
    funding = fields.get("funding") or {}
    if funding.get("amount_minor"):
        a["funding"] = [
            {"month": 1, "amount_minor": int(funding["amount_minor"]), "label": "Planned funding"}
        ]
    if fields.get("estimated_customers"):
        a["market_customers"] = int(fields["estimated_customers"])
    return a


def _problems(assumptions: dict[str, Any]) -> None:
    problems = engine.validate(assumptions)
    if problems:
        raise exceptions.ValidationError({p["path"]: [p["message"]] for p in problems})


def _snapshot(forecast: Forecast, note: str) -> None:
    ForecastVersion.objects.create(
        forecast=forecast,
        version=forecast.version,
        assumptions=forecast.assumptions,
        note=note[:120],
    )
    old = forecast.versions.order_by("-version").values_list("pk", flat=True)[VERSIONS_KEPT:]
    ForecastVersion.objects.filter(pk__in=list(old)).delete()


def create(venture: Venture, assumptions: dict[str, Any] | None = None) -> Forecast:
    """Start the forecast from the profile (or from given assumptions)."""
    if get(venture) is not None:
        raise ConflictError("This venture already has a forecast.", code="exists")
    body = assumptions or seed_assumptions(venture)
    _problems(body)
    with transaction.atomic():
        forecast = Forecast.objects.create(
            venture=venture,
            template=body["template"],
            currency=body["currency"],
            assumptions=body,
            version=1,
        )
        _snapshot(forecast, "Started")
        ventures.set_output_state(venture, "forecast", "ready")
    return forecast


def save(
    venture: Venture, assumptions: dict[str, Any], *, base_version: int, note: str = ""
) -> Forecast:
    _problems(assumptions)
    with transaction.atomic():
        forecast = Forecast.objects.select_for_update().get(venture=venture)
        if forecast.version != base_version:
            raise ConflictError(
                "The forecast changed elsewhere. Reload and try again.", code="stale"
            )
        forecast.assumptions = assumptions
        forecast.template = assumptions["template"]
        forecast.currency = assumptions["currency"]
        forecast.version += 1
        forecast.save()
        _snapshot(forecast, note or "Edited")
        ventures.set_output_state(venture, "forecast", "ready")
    return forecast


def restore(venture: Venture, version: int) -> Forecast:
    forecast = get(venture)
    row = forecast.versions.filter(version=version).first() if forecast else None
    if forecast is None or row is None:
        raise exceptions.NotFound()
    return save(
        venture,
        row.assumptions,
        base_version=forecast.version,
        note=f"Restored version {version}",
    )


def compute(forecast: Forecast, scenario: str = "base") -> engine.Result:
    return engine.run(forecast.assumptions, scenario)


def all_scenarios(forecast: Forecast) -> dict[str, dict[str, Any]]:
    return {s: engine.run(forecast.assumptions, s).summary for s in engine.SCENARIOS}


# --- proposals -------------------------------------------------------------------------------


def suggest(*, venture: Venture, owner_id: UUID, forecast: Forecast) -> dict[str, Any]:
    """Assumptions the sources support, as a proposal. Nothing is saved."""
    runner.require_ai()  # sourced benchmarks need the model to read them
    a = forecast.assumptions
    template = a["template"]
    # Rates only: prices, volumes and costs are the founder's to set.
    names = [n for n, spec in engine.DRIVERS[template].items() if spec["kind"] == "pct"]
    profile = profile_of(venture)
    facts: list[Fact] = gather.gather(
        fields=profile.fields,
        owner_id=owner_id,
        venture=venture,
        job=None,
        topics=["benchmarks", "growth"],
    )[:8]
    if not facts:
        return {"proposals": [], "message": "No reliable benchmarks were found for this sector."}
    answer = runner.structured(
        prompt_id="forecast.assumptions",
        variables={
            "template": template,
            "names": names,
            "entered": a.get("drivers", {}),
            "venture": {
                "sector": profile.fields.get("sector", ""),
                "regions": profile.fields.get("target_regions", []),
                "stage": profile.fields.get("stage", ""),
            },
            "facts": [
                {"n": i, "statement": f.statement, "source": f.source.publisher or f.source.title}
                for i, f in enumerate(facts, start=1)
            ],
        },
        owner_id=owner_id,
        venture=venture,
    )
    proposals: list[dict[str, Any]] = []
    for item in answer.get("proposals", []):
        name = str(item.get("name", ""))
        position = int(item.get("fact", 0))
        if name not in names or not 1 <= position <= len(facts):
            continue
        trial = {**a, "drivers": {**a.get("drivers", {}), name: item["value"]}}
        if any(p["path"] == f"drivers.{name}" for p in engine.validate(trial)):
            continue
        fact = facts[position - 1]
        proposals.append(
            {
                "name": name,
                "value": item["value"],
                "current": a.get("drivers", {}).get(name),
                "rationale": str(item.get("rationale", ""))[:300],
                "source_name": fact.source.publisher or fact.source.title,
                "url": fact.source.url,
                "statement": fact.statement,
            }
        )
    return {"proposals": proposals, "message": ""}


# --- headline for other tools ----------------------------------------------------------------


def headline(venture: Venture) -> dict[str, Any] | None:
    forecast = get(venture)
    if forecast is None:
        return None
    r = compute(forecast)
    s = r.summary
    return {
        "version": forecast.version,
        "currency": forecast.currency,
        "figures": {
            "revenue_year1": s["revenue_year1"],
            "revenue_year2": s["revenue_year2"],
            "gross_margin_pct_year1": s["gross_margin_pct_year1"],
            "net_income_year1": s["net_income_year1"],
            "net_income_year2": s["net_income_year2"],
            "break_even_month": s["break_even_month"],
            "lowest_cash": s["lowest_cash"],
            "extra_funding_needed": s["extra_funding_needed"],
            "total_funding": s["total_funding"],
            "annual_run_rate": s["annual_run_rate"],
        },
        "warnings": [w["message"] for w in r.warnings if w["severity"] == "error"],
    }


def series(venture: Venture, name: str) -> dict[str, Any] | None:
    """Quarterly revenue or end-of-quarter cash, for a chart. ``None`` without a forecast."""
    forecast = get(venture)
    if forecast is None or name not in ("revenue", "cash"):
        return None
    months = compute(forecast).months
    values = []
    for q in range(8):
        chunk = months[q * 3 : q * 3 + 3]
        values.append(sum(m.revenue for m in chunk) if name == "revenue" else chunk[-1].cash_end)
    return {
        "labels": [f"Q{q % 4 + 1} Y{q // 4 + 1}" for q in range(8)],
        "values": values,
        "currency": forecast.currency,
    }


# --- export job ------------------------------------------------------------------------------


def export_forecast(ctx: JobContext) -> dict[str, Any]:
    """The ``exports.forecast`` job. Payload: ``format`` (xlsx or pdf)."""
    from apps.toolkit.forecasts import export

    venture = ctx.venture
    if venture is None:
        raise JobFailed("no_venture", "This job needs a venture.")
    fmt = str(ctx.payload.get("format", "xlsx"))
    if fmt not in ("xlsx", "pdf"):
        raise JobFailed("bad_format", "Choose xlsx or pdf.")
    forecast = get(venture)
    if forecast is None:
        raise JobFailed("no_forecast", "Create the forecast first.")
    ctx.progress(20, "Calculating")
    results = {s: engine.run(forecast.assumptions, s) for s in engine.SCENARIOS}
    ctx.progress(60, "Building the file")
    body = export.document(venture.name, forecast, results)
    data = export.render_xlsx(body) if fmt == "xlsx" else export.render_pdf(body)
    safe = "".join(ch for ch in venture.name if ch.isalnum() or ch in " -_").strip() or "forecast"
    file = exports.store(
        venture=venture,
        owner_id=ctx.owner_id,
        kind=f"forecast.{fmt}",
        filename=f"{safe} forecast v{forecast.version}.{fmt}",
        content_type=export.XLSX_TYPE if fmt == "xlsx" else export.PDF_TYPE,
        data=data,
    )
    return exports.result_of(file)
