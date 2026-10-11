import copy

import pytest

from apps.toolkit.scoring import engine, rubric

CONFIG = rubric.DEFAULT
DIMS = {d["key"]: d for d in CONFIG["dimensions"]}


def score(key, fields=None, competitors=0, team=None, facts=None):
    return engine.score_dimension(
        DIMS[key], fields=fields or {}, competitors=competitors, team=team or [], facts=facts or []
    )


def fact(topic, statement, value=None, confidence=0.8, fid="f1"):
    return {
        "id": fid,
        "topic": topic,
        "statement": statement,
        "value": value,
        "unit": "percent",
        "confidence": confidence,
        "source_name": "Example Data",
        "url": "https://data.example.org/x",
        "date": "2026-01-01",
    }


def test_the_default_rubric_is_valid_and_adds_up():
    assert rubric.validate(CONFIG) == []
    assert sum(d["weight"] for d in CONFIG["dimensions"]) == 100


@pytest.mark.parametrize(
    ("mutate", "expected"),
    [
        (lambda c: c["dimensions"][0].update(weight=50), "add up to"),
        (lambda c: c["dimensions"].append(dict(c["dimensions"][0])), "unique"),
        (lambda c: c.update(verdicts=[{"min": 50, "label": "x"}]), "every score"),
        (lambda c: c.update(dimensions=[]), "at least one"),
    ],
)
def test_a_broken_rubric_is_explained(mutate, expected):
    config = copy.deepcopy(CONFIG)
    mutate(config)
    assert any(expected in problem for problem in rubric.validate(config))


def test_problem_clarity_adds_up_what_is_there_and_lists_what_is_missing():
    full = score(
        "problem_clarity",
        {
            "problem": "x" * 100,
            "problem_today": "y" * 40,
            "problem_evidence": "z" * 40,
            "target_customer": "w" * 40,
            "estimated_customers": 5000,
        },
    )
    assert full.score == 100 and full.gaps == [] and full.status == "scored"
    partial = score("problem_clarity", {"problem": "x" * 100})
    assert partial.score == 30
    assert {g.field for g in partial.gaps} == {
        "problem_today",
        "problem_evidence",
        "target_customer",
        "estimated_customers",
    }
    assert sum(g.points for g in partial.gaps) == 70


def test_an_area_with_nothing_entered_is_not_scored():
    empty = score("problem_clarity", {})
    assert empty.status == "insufficient_data" and empty.score is None
    assert empty.gaps  # but it still says what would let it be scored
    assert score("team").status == "insufficient_data"


def test_traction_bands_and_stage():
    low = score("traction", {"stage": "idea"})
    high = score(
        "traction",
        {"stage": "revenue", "traction": {"revenue_minor": 100, "users": 600, "pilots": 2}},
    )
    assert low.score == 0 and high.score == 100
    mid = score("traction", {"stage": "launched", "traction": {"users": 60}})
    assert mid.score == 25 + 12


def test_the_team_is_judged_on_founders_roles_and_links():
    team = [
        {"role": "CEO", "linkedin": "https://linkedin.com/in/a", "is_founder": True},
        {"role": "CTO", "linkedin": "", "is_founder": True},
    ]
    assert score("team", team=team).score == 100
    solo = score("team", team=team[:1])
    assert solo.score == 30 + 20
    empty = score("team", team=[])
    assert empty.status == "insufficient_data"
    assert any(g.action == "find_mentor" for g in empty.gaps)


def test_market_score_comes_from_sourced_growth_and_size():
    facts = [
        fact("growth", "The market grows 18 percent a year", 18, fid="g"),
        fact("market_size", "The market is worth 4 billion dollars", 4e9, fid="s"),
    ]
    result = score("market", facts=facts)
    assert result.score == 80 + 10
    assert [e.kind for e in result.evidence] == ["fact", "fact"]
    assert result.evidence[0].url == "https://data.example.org/x"


def test_no_sources_means_not_assessed_rather_than_guessed():
    assert score("market").status == "insufficient_data"
    assert score("risk").status == "insufficient_data"
    only_size = score("market", facts=[fact("market_size", "Worth 1 billion", 1e9)])
    assert only_size.status == "scored" and only_size.score == 40 + 10  # no growth figure found


def test_regulation_facts_lower_the_risk_score():
    calm = score("risk", facts=[fact("regulation", "Companies register online in one day")])
    heavy = score(
        "risk",
        facts=[
            fact("regulation", "A licence from the central bank is required", fid="a"),
            fact("regulation", "Foreign firms need a permit and approval", fid="b"),
        ],
    )
    assert calm.score == 75 and heavy.score == 75 - 16


def test_the_overall_score_ignores_areas_that_could_not_be_assessed():
    results = [
        engine.DimensionResult("a", "A", 50, 80, "scored"),
        engine.DimensionResult("b", "B", 30, 40, "scored"),
        engine.DimensionResult("c", "C", 20, None, "insufficient_data"),
    ]
    overall = engine.combine(results, CONFIG)
    assert overall.score == round((80 * 50 + 40 * 30) / 80) and overall.scored_weight == 80
    assert "C" in overall.explanation and overall.verdict == "Promising, with gaps to close"


def test_too_little_evidence_gives_no_overall_score():
    results = [
        engine.DimensionResult("a", "A", 20, 90, "scored"),
        engine.DimensionResult("b", "B", 80, None, "insufficient_data"),
    ]
    overall = engine.combine(results, CONFIG)
    assert overall.score is None and "Not enough" in overall.verdict


def test_the_same_inputs_always_give_the_same_score():
    fields = {"problem": "p" * 90, "problem_today": "t" * 40, "traction": {"users": 12}}
    first = [score(key, fields) for key in DIMS]
    second = [score(key, fields) for key in DIMS]
    assert [(r.key, r.score, r.status) for r in first] == [
        (r.key, r.score, r.status) for r in second
    ]
