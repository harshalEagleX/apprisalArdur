"""
Confidence router tests (crt-1.0.0) — SHALqc.md §7 / §12 DoD #4.

The load-bearing guarantee: a field read below its `review` threshold is
suppressed to MISSING before rules run, so a rule literally CANNOT FAIL on it.
"""

from app.extraction.result import ExtractedField, ExtractedFieldSet, Source
from app.routing.router import router


def _fs(name, value, conf):
    fs = ExtractedFieldSet()
    fs.add(ExtractedField(canonical_name=name, value=value, raw_value=value,
                          source=Source.PDF_DIGITAL, confidence=conf, page=1))
    return fs


def test_route_decisions():
    assert router.route("neighborhood_name", 0.95) == "auto_accept"
    assert router.route("neighborhood_name", 0.75) == "review"
    assert router.route("neighborhood_name", 0.40) == "reject"


def test_money_is_stricter_via_wildcard():
    # comp_*_sale_price has auto_accept 0.95 → 0.92 is only "review", not accept
    assert router.route("comp_3_sale_price", 0.92) == "review"
    assert router.route("neighborhood_name", 0.92) == "auto_accept"  # default 0.90


def test_apply_suppresses_below_review_to_missing():
    fs = _fs("city", "Humble", 0.40)   # below default review 0.70
    n = router.apply(fs)
    assert n == 1
    ef = fs.get("city")
    assert ef.found is False              # → MISSING for the rules
    assert ef.raw_value == "Humble"       # raw preserved (P2)
    assert "below routing review threshold" in ef.suppression_reason


def test_apply_keeps_above_review():
    fs = _fs("city", "Humble", 0.92)
    assert router.apply(fs) == 0
    assert fs.get("city").found is True
