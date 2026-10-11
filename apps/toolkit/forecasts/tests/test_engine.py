import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from apps.toolkit.forecasts import engine

TEMPLATES = engine.TEMPLATES
PRICE_KEYS = {
    "subscription": "price_minor",
    "marketplace": "gmv_month1_minor",
    "transaction_fee": "avg_value_minor",
    "product_sales": "price_minor",
    "services": "hourly_rate_minor",
    "licensing": "annual_fee_minor",
}


def subscription():
    a = engine.defaults("subscription")
    a["drivers"].update(
        {
            "initial_customers": 0,
            "new_customers_month1": 10,
            "new_customer_growth_pct": 0,
            "churn_pct": 0,
            "price_minor": 1000,
        }
    )
    a["costs"].update({"cogs_pct": 10})
    return a


def test_a_hand_worked_subscription_case():
    a = subscription()
    a["costs"]["fixed"] = [{"label": "Office", "monthly_minor": 50000}]
    r = engine.run(a)
    assert r.months[0].revenue == 10_000  # 10 customers at 1,000
    assert r.months[23].revenue == 240_000  # nobody leaves and ten join each month
    assert r.summary["revenue_year1"] == 10_000 * sum(range(1, 13))
    assert r.months[0].cogs == 1_000
    assert r.months[0].ebitda == 10_000 - 1_000 - 50_000
    assert r.months[0].cash_end == -41_000
    assert r.summary["cash_out_month"] == 1 and r.summary["extra_funding_needed"] > 0
    assert r.summary["break_even_month"] is not None
    assert any(w["code"] == "cash_runs_out" for w in r.warnings)


def test_churn_and_growth_compound():
    a = subscription()
    a["drivers"].update({"new_customer_growth_pct": 10, "churn_pct": 5})
    r = engine.run(a)
    customers = [m.kpis["customers"] for m in r.months]
    assert customers[0] == 10
    assert customers[1] == 21  # 9.5 stay (5% leave) and 11 join: 20.5, rounded half up
    assert customers == sorted(customers)


def test_tax_is_charged_on_profit_after_earlier_losses():
    a = engine.defaults("product_sales")
    a["drivers"].update({"units_month1": 10, "units_growth_pct": 0, "price_minor": 1000})
    a["costs"].update({"cogs_pct": 0, "fixed": [{"label": "Rent", "monthly_minor": 4000}]})
    a["tax_rate_pct"] = 10
    r = engine.run(a)
    assert {m.ebitda for m in r.months} == {6000}
    assert all(m.tax == 600 for m in r.months)
    a["costs"]["fixed"] = [{"label": "Rent", "monthly_minor": 12000}]
    loss = engine.run(a)
    assert {m.ebitda for m in loss.months} == {-2000} and all(m.tax == 0 for m in loss.months)


def test_funding_lands_in_its_month_and_stays():
    a = subscription()
    a["costs"]["fixed"] = [{"label": "Office", "monthly_minor": 50000}]
    without = engine.run(a)
    a["funding"] = [{"month": 3, "amount_minor": 1_000_000, "label": "Seed"}]
    funded = engine.run(a)
    for before, after in zip(without.months, funded.months, strict=True):
        extra = 1_000_000 if after.index >= 3 else 0
        assert after.cash_end - before.cash_end == extra
    assert funded.summary["total_funding"] == 1_000_000


def test_scenarios_are_ordered():
    a = engine.defaults("subscription")
    a["drivers"].update({"price_minor": 5000, "new_customers_month1": 30})
    a["costs"]["fixed"] = [{"label": "Rent", "monthly_minor": 100000}]
    low, base, high = (engine.run(a, s) for s in ("conservative", "base", "optimistic"))
    assert low.summary["revenue_year2"] < base.summary["revenue_year2"]
    assert base.summary["revenue_year2"] < high.summary["revenue_year2"]


def test_sensitivity_ranks_the_assumptions_that_matter_most():
    a = engine.defaults("subscription")
    a["drivers"].update({"price_minor": 5000, "new_customers_month1": 30})
    rows = engine.sensitivity(a)
    assert rows and rows == sorted(rows, key=lambda r: (-r["impact"], r["assumption"]))
    price = next(r for r in rows if r["assumption"] == "drivers.price_minor")
    assert price["up"]["revenue_year2_change"] > 0 > price["down"]["revenue_year2_change"]


@pytest.mark.parametrize(
    ("mutate", "path"),
    [
        (lambda a: a.update(currency="XXX"), "currency"),
        (lambda a: a.update(template="lemonade"), "template"),
        (lambda a: a["drivers"].update(price_minor=-1), "drivers.price_minor"),
        (lambda a: a["drivers"].update(churn_pct=101), "drivers.churn_pct"),
        (lambda a: a["drivers"].update(nonsense=1), "drivers.nonsense"),
        (lambda a: a["costs"].update(cogs_pct="lots"), "costs.cogs_pct"),
        (lambda a: a.update(funding=[{"month": 30, "amount_minor": 1}]), "funding.0.month"),
        (lambda a: a.update(tax_rate_pct=float("nan")), "tax_rate_pct"),
    ],
)
def test_invalid_assumptions_are_named_and_refused(mutate, path):
    a = engine.defaults("subscription")
    mutate(a)
    assert path in {p["path"] for p in engine.validate(a)}
    with pytest.raises(engine.Invalid):
        engine.run(a)


def test_sanity_warnings_flag_implausible_inputs():
    a = engine.defaults("subscription")
    a["drivers"].update({"price_minor": 1000, "new_customer_growth_pct": 50, "churn_pct": 0})
    a["market_customers"] = 100
    codes = {w["code"] for w in engine.run(a).warnings}
    assert {"growth_very_high", "churn_very_low", "no_operating_costs", "beyond_market"} <= codes


def test_every_template_runs_in_every_currency():
    for template in TEMPLATES:
        for currency in engine.CURRENCIES:
            a = engine.defaults(template, currency)
            a["drivers"][PRICE_KEYS[template]] = 2500
            r = engine.run(a)
            assert len(r.months) == 24 and r.currency == currency


def test_unit_economics_for_a_subscription():
    a = subscription()
    a["drivers"]["churn_pct"] = 5
    a["costs"]["marketing_monthly_minor"] = 20_000
    ue = engine.run(a).unit_economics
    assert ue["available"] and ue["lifetime_months"] == 20.0
    assert ue["ltv"] > 0 and ue["cac"] > 0 and ue["ltv_to_cac"] is not None


# --- properties that hold for every valid set of assumptions ---------------------------------

money = st.integers(min_value=0, max_value=10**9)
pct = st.floats(min_value=0, max_value=60, allow_nan=False)


@st.composite
def assumption_sets(draw):
    template = draw(st.sampled_from(TEMPLATES))
    a = engine.defaults(template, draw(st.sampled_from(engine.CURRENCIES)))
    for name, spec in engine.DRIVERS[template].items():
        if spec["kind"] == "money":
            a["drivers"][name] = draw(money)
        elif spec["kind"] == "pct":
            a["drivers"][name] = draw(pct)
        else:
            a["drivers"][name] = draw(st.integers(min_value=0, max_value=spec.get("max", 100_000)))
    a["costs"]["cogs_pct"] = draw(st.floats(min_value=0, max_value=100, allow_nan=False))
    a["costs"]["fixed"] = [{"label": "x", "monthly_minor": draw(money)}]
    a["costs"]["salaries"] = [
        {
            "role": "r",
            "monthly_minor": draw(money),
            "count": draw(st.integers(1, 20)),
            "start_month": draw(st.integers(1, 24)),
        }
    ]
    a["funding"] = [{"month": draw(st.integers(1, 24)), "amount_minor": draw(money), "label": "f"}]
    a["opening_cash_minor"] = draw(money)
    a["tax_rate_pct"] = draw(st.floats(min_value=0, max_value=60, allow_nan=False))
    return a


LIGHT = settings(max_examples=60, deadline=None, suppress_health_check=[HealthCheck.too_slow])


@LIGHT
@given(assumption_sets(), st.sampled_from(engine.SCENARIOS))
def test_the_books_always_balance(a, scenario):
    r = engine.run(a, scenario)
    cash = a["opening_cash_minor"]
    for m in r.months:
        assert m.revenue >= 0 and m.cogs >= 0 and m.tax >= 0
        assert m.gross_profit == m.revenue - m.cogs
        assert m.opex == m.marketing + m.salaries + m.fixed
        assert m.ebitda == m.gross_profit - m.opex
        assert m.net_income == m.ebitda - m.tax
        cash += m.net_income + m.funding
        assert m.cash_end == cash
    assert r.summary["ending_cash"] == r.months[-1].cash_end
    assert r.summary["lowest_cash"] == min(m.cash_end for m in r.months)


@LIGHT
@given(assumption_sets())
def test_the_same_assumptions_give_the_same_forecast(a):
    assert engine.to_dict(engine.run(a)) == engine.to_dict(engine.run(a))


@LIGHT
@given(assumption_sets())
def test_sensitivity_never_fails_on_valid_assumptions(a):
    for row in engine.sensitivity(a):
        assert row["impact"] >= 0
