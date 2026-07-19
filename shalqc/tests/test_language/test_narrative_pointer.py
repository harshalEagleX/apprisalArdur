"""A "pointer" narrative is text that stands IN PLACE OF the narrative — not a
complete narrative that happens to cite an addendum.

2026-07-18: `_POINTER_RX` matched anywhere in the value, so an appraiser's normal
closing courtesy ("…analyzed in the report. See attached addendum.") turned a full
narrative into a pointer. run._narrative_pointer_card then short-circuited the
check BEFORE the judge and told the reviewer "The form points to an addendum for
this narrative but I could not find the matching text" — about 1093 characters
sitting right in front of them.

Measured on ESMD-0002883: sales_comparison_summary was 1093 chars of real prose and
market_conditions_commentary 264 chars. EQ-87 / EQ-118 / EQ-120 hedged on 12/15,
9/15 and 9/15 orders respectively — one of the largest single sources of false
REVIEW in the queue.
"""

from app.language import narrative as NAR


REAL_SCA_SUMMARY = (
    "The appraiser considered all comparable sales in the final value reconciliation, "
    "with the greatest weight placed on Comparable Sales 1 and 2. These sales are the "
    "most proximate to the subject property and represent the most recent market "
    "activity. Comparable Sale 2 required the least net and gross adjustments. "
    "See attached addendum.")

REAL_MC_COMMENTARY = (
    "The subject's reasonable exposure time is estimated to be the same as the "
    "marketing time reported for the neighborhood. Agents in the area indicate "
    "properties priced correctly contract quickly and many have multiple contract "
    "offers. See attached addendum.")


def test_full_narrative_ending_in_a_crossreference_is_prose():
    assert NAR.classify(REAL_SCA_SUMMARY) == "prose"
    assert NAR.is_usable_prose(REAL_SCA_SUMMARY)


def test_shorter_but_still_substantial_commentary_is_prose():
    assert NAR.classify(REAL_MC_COMMENTARY) == "prose"


def test_a_bare_pointer_is_still_a_pointer():
    for text in ("See attached addendum.", "See addendum",
                 "Continued on addendum page 3.", "See comment addendum for details.",
                 "Refer to addendum."):
        assert NAR.classify(text) == "pointer", text


def test_pointer_labels_no_longer_flags_a_real_narrative():
    values = {"sales_comparison_summary": REAL_SCA_SUMMARY,
              "market_conditions_commentary": "See attached addendum."}
    flagged = NAR.pointer_labels(values, list(values))
    assert "sales_comparison_summary" not in flagged      # real prose survives
    assert "market_conditions_commentary" in flagged      # bare pointer still caught


# ── absence is never evidence of a violation ────────────────────────────────

def _packet(absent=None):
    from app.language.packet_v2 import Packet
    return Packet(item_id="X", check_text="c", reject_text=None, values={},
                  absent_labels=list(absent or []), computed_hints=[],
                  section_snapshot=None, source_notes={}, scope="subject")


def test_reject_justified_by_missing_data_is_capped_at_review():
    """2026-07-18: the guard used to require `absent_labels` to be non-empty, so it
    missed the commonest case — the judge rejecting over data that was never BOUND
    at all. On the 7-order baseline, rejects rose 3.7 → 5.1/order once previously
    unjudged items began being judged, and the repeat offenders were exactly this:

        EQ-22  "land_use_other=5 (no comment field supplied)"
        EQ-75  "Porch is marked ... but no corresponding grid entry is present"

    Neither shows the report is wrong; both show we did not read something. A false
    rejection sent back to an appraiser costs far more than a VERIFY."""
    from app.language.validate_v2 import _leans_on_absent
    for found in ("land_use_other=5 (no comment field supplied)",
                  "Porch is marked in improvements, but no corresponding grid entry is present",
                  "the required commentary is missing",
                  "field is blank"):
        assert _leans_on_absent(found, "", _packet()), found


def test_a_substantive_contradiction_still_rejects():
    """The guard must not swallow a REAL finding — a value that contradicts the
    requirement is still a reject."""
    from app.language.validate_v2 import _leans_on_absent
    for found in ("net adjustment is 28% which exceeds the 25% limit",
                  "comp 3 sale date 2019-04-02 is outside the 12 month window",
                  "subject GLA 1,850 does not match the sketch total of 2,140"):
        assert not _leans_on_absent(found, "", _packet()), found
