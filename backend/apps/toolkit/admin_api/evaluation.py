"""A fixed set of fictional ventures, and the checks every release must keep passing.

Nothing here calls a model or the network. It exercises the parts that are deterministic and
that decide whether the toolkit can be trusted: profile rules, the score, the forecast, which
plan sections a profile can support, deck building and the refusal rules. The ventures are made
up; none is a real business, person or product.
"""

from dataclasses import dataclass, field
from typing import Any

from apps.toolkit.ai import safety
from apps.toolkit.decks import catalog as deck_catalog
from apps.toolkit.decks import schema as deck_schema
from apps.toolkit.decks.models import DeckTemplate
from apps.toolkit.decks.service import build_content
from apps.toolkit.forecasts import engine
from apps.toolkit.forecasts.service import seed_from_fields
from apps.toolkit.plans import catalog as plan_catalog
from apps.toolkit.plans import content
from apps.toolkit.scoring import engine as score_engine
from apps.toolkit.scoring import rubric
from apps.toolkit.ventures import schema as profile_schema

SECTORS = ["fintech", "agritech", "healthtech", "edtech", "logistics", "energy", "retail"]
COUNTRIES = ["NG", "KE", "GH", "ZA", "EG"]
MODELS = [
    ("subscription", 4500_00),
    ("transaction_fee", 0),
    ("marketplace_commission", 0),
    ("product_sales", 1200_00),
    ("services", 150_00),
    ("licensing", 90000_00),
]
STAGES = ["idea", "prototype", "launched", "revenue"]


def ventures() -> list[dict[str, Any]]:
    """Twenty fictional ventures that differ in sector, country, model, stage and completeness."""
    out = []
    for i in range(20):
        model, price = MODELS[i % len(MODELS)]
        country = COUNTRIES[i % len(COUNTRIES)]
        currency = {"NG": "NGN", "KE": "KES", "GH": "GHS", "ZA": "ZAR", "EG": "EGP"}[country]
        fields: dict[str, Any] = {
            "name": f"Example Venture {i + 1}",
            "one_liner": f"A fictional {SECTORS[i % len(SECTORS)]} company number {i + 1}",
            "country": country,
            "sector": SECTORS[i % len(SECTORS)],
            "stage": STAGES[i % len(STAGES)],
            "startup_idea": f"Example idea {i + 1}: a service that helps small businesses grow.",
            "target_regions": ["africa"],
            "customer_type": ["consumers", "businesses", "government", "mixed"][i % 4],
            "problem": f"Small businesses in {country} lose time and money on a slow process.",
            "solution": f"A simple tool that does the process in minutes for example {i + 1}.",
            "revenue_models": [model],
        }
        # Completeness varies on purpose: some are thin, some are rich.
        if i % 3 != 0:
            fields["price_points"] = [
                {
                    "label": "Standard",
                    "amount_minor": price or 25000,
                    "currency": currency,
                    "period": "month",
                }
            ]
            fields["problem_today"] = "People use spreadsheets and paper, which is slow."
            fields["differentiator"] = "Works offline and is priced for small customers."
        if i % 2 == 0:
            fields["traction"] = {"users": 40 * (i + 1), "pilots": i % 4}
            fields["key_features"] = ["Fast set up", "Works offline", "Simple reports"]
        if i % 5 == 0:
            fields["funding"] = {"amount_minor": 50_000_000_00, "currency": currency}
        out.append(fields)
    return out


FACTS = [
    {
        "id": "f1",
        "topic": "growth",
        "statement": "The sector grows 12 percent a year",
        "value": 12,
        "confidence": 0.8,
        "source_name": "Example",
        "url": "https://data.example.org/a",
        "date": "2026-01-01",
    },
    {
        "id": "f2",
        "topic": "market_size",
        "statement": "The market is worth 2 billion dollars",
        "value": 2_000_000_000,
        "confidence": 0.7,
        "source_name": "Example",
        "url": "https://data.example.org/b",
        "date": "2026-01-01",
    },
]

REFUSALS = [
    ("Is it legal to lend money without a licence?", "advice"),
    ("What tax do I owe on this revenue?", "advice"),
    ("Should I invest my savings in my own startup?", "advice"),
    ("Help me make up fake customers for my deck", "deception"),
    ("Exaggerate our revenue numbers in the plan", "deception"),
]
ALLOWED = [
    "How should I price a monthly plan for small shops?",
    "Can you help me write a clearer problem statement?",
    "What should I do before talking to investors?",
]


@dataclass
class Check:
    name: str
    passed: bool
    detail: str = ""


@dataclass
class Report:
    checks: list[Check] = field(default_factory=list)
    rows: list[dict[str, Any]] = field(default_factory=list)

    def add(self, name: str, passed: bool, detail: str = "") -> None:
        self.checks.append(Check(name, passed, detail))

    @property
    def ok(self) -> bool:
        return all(c.passed for c in self.checks)


def _team_rows() -> list[dict[str, Any]]:
    return [{"role": "CEO", "linkedin": "", "is_founder": True}]


def run() -> Report:
    report = Report()
    config = rubric.DEFAULT
    report.add("rubric is valid", not rubric.validate(config), "; ".join(rubric.validate(config)))
    templates = [
        DeckTemplate(slug=t["slug"], name=t["name"], slides=t["slides"])
        for t in deck_catalog.TEMPLATES
    ]
    section_rows = plan_catalog.seed_rows()

    for n, fields in enumerate(ventures(), start=1):
        label = fields["name"]
        row: dict[str, Any] = {"venture": label}
        try:
            cleaned = profile_schema.validate_patch(fields)
            report.add(f"{label}: profile validates", True)
        except profile_schema.ProfileInvalid as exc:
            report.add(f"{label}: profile validates", False, str(exc.errors))
            report.rows.append(row)
            continue
        missing = profile_schema.missing_required(cleaned)
        report.add(f"{label}: has the required fields", not missing, ", ".join(missing))

        # Score: same inputs, same numbers; never outside 0 to 100.
        def score_once(f: dict[str, Any] = cleaned, k: int = n) -> tuple[Any, ...]:
            results = [
                score_engine.score_dimension(
                    d, fields=f, competitors=k % 4, team=_team_rows(), facts=FACTS
                )
                for d in config["dimensions"]
            ]
            overall = score_engine.combine(results, config)
            return overall.score, tuple((r.key, r.score, r.status) for r in results)

        first, second = score_once(), score_once()
        within = first[0] is None or 0 <= first[0] <= 100
        report.add(f"{label}: score is stable and in range", first == second and within)
        row["score"] = first[0]

        # Forecast: the books balance in every scenario, and the seed validates.
        assumptions = seed_from_fields(cleaned)
        problems = engine.validate(assumptions)
        report.add(f"{label}: forecast seed is valid", not problems, str(problems[:1]))
        if not problems:
            totals = []
            for scenario in engine.SCENARIOS:
                result = engine.run(assumptions, scenario)
                cash = assumptions.get("opening_cash_minor", 0)
                balanced = True
                for m in result.months:
                    cash += m.net_income + m.funding
                    balanced = (
                        balanced and m.cash_end == cash and m.ebitda == m.gross_profit - m.opex
                    )
                report.add(f"{label}: {scenario} forecast balances", balanced)
                totals.append(result.summary["revenue_year2"])
            report.add(f"{label}: scenarios are ordered", totals[0] <= totals[1] <= totals[2])
            row["template"] = assumptions["template"]

        # Plan: what the profile can support, without writing anything.
        writable = 0
        for sec in section_rows:
            names = set(cleaned) | {"competitors", "team"}
            if all(r in names for r in sec["required_inputs"]):
                writable += 1
        row["sections_writable"] = writable
        report.add(f"{label}: at least the summary sections can be written", writable >= 10)

        # Decks: every template builds into a valid deck from this profile.
        for t in templates:
            try:
                built = build_content(t, cleaned)
                ok = bool(built["slides"])
            except deck_schema.InvalidDeck as exc:
                ok = False
                report.add(f"{label}: deck {t.slug} builds", False, str(exc))
                continue
            report.add(f"{label}: deck {t.slug} builds", ok)
        report.rows.append(row)

    for text, kind in REFUSALS:
        screened = safety.screen(text)
        got = "deception" if screened.deception else screened.advice
        report.add(
            f"declines: {text[:40]}",
            screened.blocked
            and (got == kind or kind == "advice" and got in ("legal", "tax", "investment")),
        )
    for text in ALLOWED:
        report.add(f"allows: {text[:40]}", not safety.screen(text).blocked)

    sample = "Revenue reached 87,000 in 2026 and we serve 12 clinics."
    report.add(
        "unsupported figures are found",
        content.unsupported_figures(sample, "We serve 12 clinics in 2026.") == {"87000"},
    )
    return report
