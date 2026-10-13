"""Names and help for the assumptions, so the interface does not hard code them."""

from typing import Any

from apps.toolkit.forecasts import engine

TEMPLATE_INFO: dict[str, dict[str, str]] = {
    "subscription": {
        "label": "Subscription",
        "help": "Customers pay every month and some leave. Revenue grows with new customers.",
    },
    "marketplace": {
        "label": "Marketplace",
        "help": "You earn a commission on the value traded between buyers and sellers.",
    },
    "transaction_fee": {
        "label": "Transaction fees",
        "help": "You earn a percentage and a fixed fee on each transaction you process.",
    },
    "product_sales": {
        "label": "Product sales",
        "help": "You sell units at a price and each unit has a cost.",
    },
    "services": {
        "label": "Services",
        "help": "Billable people sell their time at a rate; more hires mean more revenue.",
    },
    "licensing": {
        "label": "Licensing",
        "help": "Customers pay an annual licence fee and renew at a rate.",
    },
}

DRIVER_INFO: dict[str, tuple[str, str]] = {
    "initial_customers": ("Customers at the start", "Paying customers on day one."),
    "new_customers_month1": ("New customers in month 1", "How many sign up in the first month."),
    "new_customer_growth_pct": ("Monthly growth in sign ups", "Percent more sign ups each month."),
    "churn_pct": ("Monthly churn", "Percent of customers who leave each month."),
    "price_minor": ("Price", "In minor units (kobo, cents) per customer per month, or per unit."),
    "price_growth_pct_year": ("Yearly price rise", "Percent the price goes up each year."),
    "gmv_month1_minor": ("Value traded in month 1", "Total value of sales through you."),
    "gmv_growth_pct": ("Monthly growth in value traded", "Percent growth each month."),
    "take_rate_pct": ("Your commission", "Percent of the value traded that you keep."),
    "transactions_month1": ("Transactions in month 1", "How many you process in month one."),
    "transactions_growth_pct": ("Monthly growth in transactions", "Percent growth each month."),
    "avg_value_minor": ("Average transaction value", "In minor units."),
    "fee_pct": ("Fee percentage", "Percent of the transaction value you charge."),
    "fixed_fee_minor": ("Fixed fee", "In minor units, added to each transaction."),
    "units_month1": ("Units sold in month 1", "How many you sell in month one."),
    "units_growth_pct": ("Monthly growth in units", "Percent growth each month."),
    "unit_cost_minor": ("Cost per unit", "What each unit costs you, in minor units."),
    "billable_staff_start": ("Billable people at the start", "People who sell their time."),
    "staff_added_per_quarter": ("People added each quarter", "New billable hires."),
    "utilisation_pct": ("Utilisation", "Percent of hours that are billed."),
    "hours_per_month": ("Hours per person per month", "Working hours available."),
    "hourly_rate_minor": ("Hourly rate", "In minor units."),
    "staff_cost_minor": ("Monthly cost per person", "In minor units."),
    "new_licences_month1": ("New licences in month 1", "Licences sold in month one."),
    "new_licences_growth_pct": ("Monthly growth in licences", "Percent growth each month."),
    "annual_fee_minor": ("Annual licence fee", "In minor units."),
    "renewal_rate_pct": ("Renewal rate", "Percent of licences renewed each year."),
}


def templates() -> list[dict[str, Any]]:
    out = []
    for name in engine.TEMPLATES:
        out.append(
            {
                "template": name,
                **TEMPLATE_INFO[name],
                "drivers": [
                    {
                        "name": key,
                        "label": DRIVER_INFO[key][0],
                        "help": DRIVER_INFO[key][1],
                        "kind": spec["kind"],
                        "default": spec["default"],
                        "max": spec.get("max"),
                    }
                    for key, spec in engine.DRIVERS[name].items()
                ],
            }
        )
    return out
