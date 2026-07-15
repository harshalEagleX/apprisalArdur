"""
The over-checking fixes (VERIFY_ITEMS_ESNV_ESTX PART 1) — all DYNAMIC, no per-item
or per-AMC hardcoding:

  1.1 severity gate  — only reject-authority items reach the reviewer queue;
                       everything else is demoted (informational), never a VERIFY.
  1.2 normalized cross-document match — a comma / corporate suffix / ZIP+4 / enum
                       spelling no longer reads as a mismatch (killed the false rejects).
  1.3 nullish        — $0 / N/A / blank is surfaced so the judge treats it as absent.
"""

from __future__ import annotations

from app.language.hints import compute_hints
from app.language.packet_v2 import Packet, _stamp_compare_forms
from app.language.run import build_language_report
from app.language.spec import CompiledItem, derive_severity
from app.language.verdict_v2 import JudgeVerdict, StatusV2
from app.normalize.normalizer import canonicalize, match_band


# ── 1.1 severity is derived dynamically from the checklist text ───────────────

def test_severity_from_reject_text():
    assert derive_severity("Property rights not provided.", "anything") == "rejectable"


def test_severity_from_reject_language_in_check_text():
    assert derive_severity(None, "Highest and Best use | if no, then Hold") == "rejectable"
    assert derive_severity(None, "Actual Age — if different add rejection") == "rejectable"
    assert derive_severity(None, "Neighborhood Name — N/A not allowed") == "rejectable"


def test_severity_default_informational():
    assert derive_severity(None, "Design (Style): Structural build type") == "informational"


def test_compiled_item_derives_severity_in_post_init():
    # a direct build (no compiler) still gets the right answer — severity is intrinsic.
    rej = CompiledItem(item_id="X", check_text="c", reject_text="reject please")
    inf = CompiledItem(item_id="Y", check_text="just describe the field")
    assert rej.severity == "rejectable" and inf.severity == "informational"
    # an explicit pin is respected (override use-case)
    pinned = CompiledItem(item_id="Z", check_text="c", severity="rejectable")
    assert pinned.severity == "rejectable"


# ── 1.1 the gate: same verdict, different routing by severity ─────────────────

def _v(sev: str, status=StatusV2.NOT_SATISFIED) -> JudgeVerdict:
    return JudgeVerdict(item_id="i", status=status, check_text="c", section="s",
                        severity=sev, judgeable="text")


def test_informational_verdict_is_demoted_not_a_reviewer_card():
    assert _v("rejectable").card_group() == "recommended_reject"
    assert _v("informational").card_group() == "informational"
    assert _v("informational", StatusV2.REVIEW).card_group() == "informational"
    # a harmless SATISFIED informational item is not noise — stays looks_good
    assert _v("informational", StatusV2.SATISFIED).card_group() == "looks_good"


def test_build_report_excludes_informational_from_the_queue():
    rep = build_language_report(
        "O", "AMC", {"a": _v("rejectable"), "b": _v("informational")}, None, gaps=[])
    assert len(rep["cards"]) == 1                      # only the rejectable item
    assert len(rep["informational_cards"]) == 1
    assert rep["summary"]["not_satisfied"] == 1        # counts reflect the queue only
    assert rep["summary"]["informational"] == 1


# ── 1.2 normalized cross-document comparison ──────────────────────────────────

def test_match_band_neutralizes_formatting():
    assert match_band("Cardinal Financial Company", "Cardinal Financial Company, LP", "company") == "match"
    assert match_band("(702) 419-2298", "702-419-2298", "phone") == "match"
    assert match_band("Refinance Transaction", "Refinance", "enum") == "match"
    assert match_band("3530 Toringdon Way, Suite 200, Charlotte, NC 28277-1234",
                      "3530 Toringdon Way Ste 200 Charlotte NC 28277", "address") == "match"
    assert match_band("1004 FHA", "1004", "form") == "match"


def test_normalized_match_hint_fires_for_crossdoc_pair():
    h = compute_hints(
        {"lender_name": "Cardinal Financial Company",
         "engagement.lender_name": "Cardinal Financial Company, LP"},
        ["lender_name", "engagement.lender_name"], expects="must match")
    assert any(x["hint"].startswith("normalized_match") and x["value"] == "match" for x in h)


def test_normalized_match_never_compares_two_same_document_fields():
    # regression: heating vs air_conditioning are two DIFFERENT fields, not a
    # cross-doc pair — the hint must NOT compare them (caused a false EQ-72 reject).
    h = compute_hints({"heating": "GFWA", "air_conditioning_type": "Central"},
                      ["heating", "air_conditioning_type"], expects="both must match")
    assert not any(x["hint"].startswith("normalized_match") for x in h)


# ── 1.3 nullish ($0 is not "present") ─────────────────────────────────────────

def test_nullish_hint_flags_zero_currency():
    h = compute_hints({"hoa_dues": "$ 0", "is_pud_checked": "No"},
                      ["hoa_dues", "is_pud_checked"])
    flagged = [x for x in h if x["hint"].startswith("nullish_values")]
    assert flagged and "hoa_dues" in flagged[0]["value"]
    assert "is_pud_checked" not in flagged[0]["value"]


# ── PART: pre-normalization — the judge sees byte-identical strings on a match ──
# (a hint alone lets a nondeterministic judge still reject on a comma; this makes
#  the formatting difference structurally invisible to the judge).

def _xdoc_packet(vals) -> Packet:
    p = Packet(item_id="i", check_text="match", reject_text=None, values=vals,
               absent_labels=[], computed_hints=[], section_snapshot=None,
               source_notes={}, scope="cross_document")
    _stamp_compare_forms(p.values)
    return p


def test_matching_crossdoc_values_are_byte_identical_to_the_judge():
    p = _xdoc_packet({
        "lender_name": {"v": "Cardinal Financial Company"},
        "engagement.lender_name": {"v": "Cardinal Financial Company, LP"},
    })
    jv = p.to_json()["values"]
    assert jv["lender_name"]["v"] == jv["engagement.lender_name"]["v"]   # judge: identical
    assert p.raw_values()["lender_name"] == "Cardinal Financial Company"  # reviewer: original


def test_real_crossdoc_mismatch_stays_different():
    p = _xdoc_packet({
        "lender_name": {"v": "Cardinal Financial"},
        "engagement.lender_name": {"v": "Wells Fargo Bank"},
    })
    jv = p.to_json()["values"]
    assert jv["lender_name"]["v"] != jv["engagement.lender_name"]["v"]   # genuine mismatch survives


def test_canonicalize_kinds():
    assert canonicalize("(702) 419-2298", "phone") == "7024192298"
    assert canonicalize("Refinance Transaction", "enum") == "REFINANCE"
    assert canonicalize("1004 FHA", "form") == "1004"
    assert (canonicalize("Cardinal Financial Company, LP", "company")
            == canonicalize("Cardinal Financial Company", "company"))
