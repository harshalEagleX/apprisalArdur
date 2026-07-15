"""Human-verified binding overrides: the compiler must apply an override VERBATIM
(bypassing the LLM binder and the label-dictionary filter) so a --force recompile
can't regenerate a hand-fixed binding away. Deterministic — no LLM involved."""

from app.language import compiler as C


_OVERRIDES = {
    "EQ-34": {
        "bound_labels": ["utilities_typical"],
        "scope": "subject",
        "expects": "utilities_typical == True",
        "judgeable": "text",
    },
    "EQ-110": {
        # cross-doc ref + a not-in-dictionary label must survive un-filtered
        "bound_labels": ["lender_name", "engagement.lender_name"],
        "scope": "cross_document",
        "expects": "lender_name == engagement.lender_name",
        "judgeable": "needs_engagement",
    },
    "EQ-109": {
        "bound_labels": ["amc_name"],
        "scope": "subject",
        "expects": "amc_name present",
        "judgeable": "text",
        "check_text": "Softened text — any AMC name satisfies.",
    },
}


def _row(item_id, check_text="Original check text", section="site"):
    return {"item_id": item_id, "check_text": check_text, "section": section,
            "item": "X", "reject_text": None}


def test_override_wins_verbatim_without_llm():
    item = C._compile_item(_row("EQ-34"), client=None, overrides=_OVERRIDES)
    assert item.bound_by == "manual"
    assert item.bound_labels == ["utilities_typical"]
    assert item.expects == "utilities_typical == True"
    assert item.scope == "subject"


def test_override_preserves_crossdoc_and_unknown_labels():
    # engagement.-prefixed and any non-dictionary label must NOT be filtered out.
    item = C._compile_item(_row("EQ-110"), client=None, overrides=_OVERRIDES)
    assert item.bound_labels == ["lender_name", "engagement.lender_name"]
    assert item.scope == "cross_document"
    assert item.judgeable == "needs_engagement"


def test_override_can_restate_check_text():
    item = C._compile_item(_row("EQ-109", check_text="Must be Fastapp"),
                           client=None, overrides=_OVERRIDES)
    assert item.check_text == "Softened text — any AMC name satisfies."


def test_non_override_item_untouched():
    # An item with no override compiles by the normal path (never 'manual').
    item = C._compile_item(_row("EQ-999"), client=None, overrides=_OVERRIDES)
    assert item.bound_by != "manual"


def test_equitysolutions_overrides_load():
    ov = C._load_overrides("EQUITYSOLUTIONS")
    assert "EQ-34" in ov and ov["EQ-34"]["bound_labels"] == ["utilities_typical"]
    # a missing AMC returns empty, never raises
    assert C._load_overrides("NO_SUCH_AMC") == {}
