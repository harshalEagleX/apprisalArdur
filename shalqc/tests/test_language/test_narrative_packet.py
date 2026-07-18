"""Row-3 regression: narrative-class packets must carry the section's actual
prose (commentary / summaries / addendum) so a text check is judged on text,
not on an empty values block. Previously a narrative item that bound to no
field reached the judge blind and was forced to REVIEW."""

from app.extraction.result import ExtractedField, ExtractedFieldSet, Source
from app.language.packet_v2 import build_packet, Sources
from app.language.spec import CompiledItem


def _fs(**fields):
    fs = ExtractedFieldSet()
    for name, val in fields.items():
        fs.add(ExtractedField(canonical_name=name, value=val, raw_value="",
                              source=Source.XML, confidence=0.9, page=1))
    return fs


def _item(section, scope="cross_section", labels=None,
          check_text="commentary must support the selections"):
    return CompiledItem.from_yaml({
        "item_id": "EQ-T", "check_text": check_text,
        "reject_text": None, "section": section, "item_name": "t",
        "bound_labels": labels or [], "scope": scope, "expects": "",
        "judgeable": "text", "conditional": None,
    })


def test_unbound_narrative_check_gets_section_prose():
    fs = _fs(market_conditions_commentary="Values stable; supply in balance.",
             addendum_text="Overflow commentary.")
    pkt = build_packet(_item("mc_1004"), Sources.of(fs))
    nt = pkt.to_json().get("narrative_text")
    assert nt and nt["market_conditions_commentary"].startswith("Values stable")
    assert nt["addendum_text"] == "Overflow commentary."


def test_prose_already_bound_is_not_duplicated():
    fs = _fs(sales_comparison_summary="Bracketed by comps 1 and 3.")
    pkt = build_packet(_item("sales_comparison", labels=["sales_comparison_summary"]), Sources.of(fs))
    # it is in values; narrative_text must not repeat it
    assert "sales_comparison_summary" in pkt.values
    assert not (pkt.narrative_text or {}).get("sales_comparison_summary")


def test_non_narrative_scope_without_comment_ask_gets_no_narrative_text():
    # bloat control: a plain value check outside a narrative scope still gets no prose
    fs = _fs(market_conditions_commentary="text")
    pkt = build_packet(_item("neighborhood", scope="subject", labels=["x"],
                             check_text="tax year must not be blank"), Sources.of(fs))
    assert pkt.narrative_text is None


def test_non_narrative_scope_that_asks_for_a_comment_gets_prose():
    # ESMI-0049134: EQ-21/EQ-30/EQ-127 are value/zoning/photo checks (non-narrative
    # scope) that hinge on a written comment. Withholding the prose forced a false
    # "no comment found" reject against a report that DID comment.
    # the widened arm is addendum-only (token control): it answers "is the comment
    # there?" from the routed addendum block, not from every prose field in the section.
    fs = _fs(addendum_text="-:MARKET CONDITIONS:- Value exceeds predominant; explained here.")
    pkt = build_packet(_item("neighborhood", scope="subject", labels=["x"],
                             check_text="a comment is required when value exceeds predominant"),
                       Sources.of(fs))
    assert pkt.narrative_text is not None
    assert "predominant" in pkt.narrative_text["addendum_text"]


def test_no_prose_present_yields_none():
    fs = _fs(some_number="123")
    pkt = build_packet(_item("neighborhood"), Sources.of(fs))
    assert pkt.narrative_text is None


def _hint(pkt, name):
    for h in pkt.computed_hints:
        if h.get("hint") == name:
            return h.get("value")
    return None


def test_runtime_context_current_year_always_injected():
    """P4 (F6): every packet carries current_year so a tax/reference-year check
    resolves deterministically instead of hedging to REVIEW."""
    import datetime
    fs = _fs(some_number="123")
    pkt = build_packet(_item("subject", scope="subject", labels=["some_number"]),
                       Sources.of(fs))
    assert _hint(pkt, "current_year") == datetime.date.today().year


def test_runtime_context_effective_year_when_present():
    fs = _fs(effective_date="07/07/2026")
    pkt = build_packet(_item("subject", scope="subject", labels=["effective_date"]),
                       Sources.of(fs))
    assert _hint(pkt, "effective_date_year") == 2026


def test_runtime_context_no_effective_year_when_absent():
    fs = _fs(some_number="123")
    pkt = build_packet(_item("subject", scope="subject", labels=["some_number"]),
                       Sources.of(fs))
    assert _hint(pkt, "effective_date_year") is None


# ── P1 / F5: the judge packet carries the RESOLVED value, never the raw slot ───

def test_packet_value_is_resolved_not_raw_preresolution_slot():
    """F5 guard: the judge context is built from the resolver output (ExtractedField
    .value), NOT the verbatim `raw_value`. This is the single-source-of-truth
    contract — a future change that fed the judge a pre-resolution slot would flip
    this test. (The card's displayed values derive from the SAME packet, so the two
    can never disagree the way the old two-pipeline architecture did.)"""
    fs = ExtractedFieldSet()
    fs.add(ExtractedField(canonical_name="location", value="Suburban",
                          raw_value="Sub.", source=Source.XML, confidence=0.95, page=2))
    pkt = build_packet(_item("neighborhood", scope="subject", labels=["location"]),
                       Sources.of(fs))
    entry = pkt.to_json()["values"]["location"]
    assert entry["v"] == "Suburban"        # resolved value reaches the judge
    assert entry["v"] != "Sub."            # never the raw pre-resolution slot


# ── addendum stitching / section routing (ESMI-0049134) ──────────────────────

def test_addendum_is_split_by_section_headers_and_routed():
    from app.language.packet_v2 import _stitch_addendum, _addendum_for_section
    blob = ("Scope of the Appraisal boilerplate. "
            "-:MARKET CONDITIONS:- Market appears to have stabilized. "
            "-:HIGHEST AND BEST USE:- Current use as a multi family home. "
            "-:COMMENTS ON SALES COMPARISON:- Value slightly greater than predominant.")
    secs = _stitch_addendum(blob)
    assert "MARKET CONDITIONS" in secs and "HIGHEST AND BEST USE" in secs
    # each checklist section gets ITS block, not the boilerplate head
    assert "stabilized" in _addendum_for_section(blob, "neighborhood")
    assert "multi family" in _addendum_for_section(blob, "site")
    assert "predominant" in _addendum_for_section(blob, "sales_comparison")


def test_addendum_without_headers_falls_back_to_head():
    from app.language.packet_v2 import _addendum_for_section
    blob = "One long unstructured addendum with no section markers at all."
    assert "unstructured" in _addendum_for_section(blob, "site")
