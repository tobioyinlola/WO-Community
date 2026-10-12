import pytest

from apps.toolkit.plans import catalog, content


def test_markup_is_stripped_and_blank_blocks_dropped():
    cleaned = content.clean(
        {
            "blocks": [
                {"type": "paragraph", "text": "<script>alert(1)</script>Hello <b>world</b>"},
                {"type": "paragraph", "text": "   "},
                {"type": "bullets", "items": ["<i>one</i>", ""]},
            ]
        }
    )
    assert cleaned["blocks"][0]["text"] == "Hello world"
    assert "<" not in str(cleaned)
    assert [b["type"] for b in cleaned["blocks"]] == ["paragraph", "bullets"]


@pytest.mark.parametrize(
    "bad",
    [
        {},
        {"blocks": "x"},
        {"blocks": [{"type": "html", "text": "x"}]},
        {"blocks": [{"type": "paragraph", "text": "x" * 4001}]},
        {"blocks": [{"type": "table", "columns": ["a"], "rows": [["1", "2"]]}]},
        {"blocks": [{"type": "paragraph", "text": "x", "cites": ["a"]}]},
        {"blocks": [{"type": "paragraph", "text": "x"}] * 41},
    ],
)
def test_invalid_content_is_refused(bad):
    with pytest.raises(content.InvalidContent):
        content.clean(bad)


def test_figures_are_compared_after_normalising():
    assert content.figures("Sales of 1,200 units and 3.5 percent") == {"1200", "3.5"}
    allowed = "We serve 1200 traders in Lagos."
    assert content.unsupported_figures("Over 1,200 traders.", allowed) == set()
    assert content.unsupported_figures("Over 50,000 traders in 2026.", allowed) == {"50000"}
    assert (
        content.unsupported_figures("Three of 5 offices.", "") == set()
    )  # small numbers and years


def test_unsupported_sentences_are_removed_without_touching_the_rest():
    blocks = {
        "blocks": [
            {
                "type": "paragraph",
                "text": "Traders lose sales. The market is worth 9,000,000 dollars. We help them.",
                "cites": [],
            },
            {"type": "bullets", "items": ["Fast", "Used by 77777 people"], "cites": []},
        ]
    }
    out = content.drop_sentences_with(blocks, {"9000000", "77777"})
    assert out["blocks"][0]["text"] == "Traders lose sales. We help them."
    assert out["blocks"][1]["items"] == ["Fast"]


def test_the_catalogue_has_44_sections_and_known_fields():
    from apps.toolkit.ventures import schema

    assert [s[0] for s in catalog.SECTIONS] == list(range(1, 45))
    known = set(schema.FIELD_NAMES) | {"competitors", "team"}
    for number, _chapter, _title, _guide, deps, required in catalog.SECTIONS:
        assert set(deps["fields"]) <= known, number
        assert set(required) <= known, number
