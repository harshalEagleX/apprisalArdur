"""Cross-document comparison checks: detection, and the availability hint that
tells the judge when a comparison is structurally impossible.

2026-07-18 investigation. Across the 7 test orders the engagement letter states
the appraiser's NAME in 6/6 cases but their phone/email in 0/6 — those letters
carry only the AMC's own letterhead contact and the borrower's. So EQ-99/EQ-100
("Telephone number / Email Address — should match the engagement letter") could
never be satisfied by any extraction improvement, and hedged to REVIEW on every
order forever. The packet now says so explicitly and the judge answers
NOT_APPLICABLE instead of renting a reviewer's attention.

Deterministic — no LLM involved.
"""

import pytest

from app.language.packet_v2 import (_cross_doc_availability, _is_cross_doc_check,
                                    _relevant_docs)


class _Item:
    """Minimal CompiledItem duck-type — only the fields the detectors read."""
    def __init__(self, check_text="", expects="", scope="subject", judgeable="text"):
        self.check_text = check_text
        self.expects = expects
        self.scope = scope
        self.judgeable = judgeable


class _Doc:
    def __init__(self, present=True):
        self.present = present


class _Src:
    def __init__(self, engagement=None, contract=None):
        self.engagement = engagement
        self.contract = contract


# ── detection ────────────────────────────────────────────────────────────────

def test_detects_explicit_compile_time_signals():
    assert _is_cross_doc_check(_Item(judgeable="needs_engagement"))
    assert _is_cross_doc_check(_Item(scope="cross_document"))


def test_detects_comparison_from_check_text_alone():
    """EQ-107 is compiled scope=subject/judgeable=text yet plainly asks for a
    match against the engagement letter — the engagement side must be attached."""
    item = _Item(check_text="ADDRESS OF PROPERTY APPRAISED — Subject property "
                            "address same as engagement letter or Subject section")
    assert _is_cross_doc_check(item)


def test_document_mention_alone_is_not_a_comparison():
    """The guard that keeps this narrow: 'Contract Price & Date of Contract' asks
    about the report's own contract section. Treating it as a cross-document
    comparison would wrongly excuse it whenever no contract PDF was supplied."""
    assert not _is_cross_doc_check(
        _Item(check_text="Contract Price & Date of Contract — must be provided"))


def test_relevant_docs_follow_the_check_text():
    assert _relevant_docs(_Item(check_text="must match the engagement letter")) == ["engagement"]
    assert _relevant_docs(_Item(check_text="must match the purchase contract")) == ["contract"]
    # names neither → the engagement letter is the universal order-form counterpart
    assert _relevant_docs(_Item(scope="cross_document")) == ["engagement"]


# ── availability ─────────────────────────────────────────────────────────────

def test_document_present_and_states_value_yields_no_hint():
    """A comparison that CAN be made must stay a real comparison."""
    src = _Src(engagement=_Doc())
    values = {"appraiser_name": {"v": "X"}, "engagement.appraiser_name": {"v": "X"}}
    assert _cross_doc_availability(src, ["appraiser_name"], values, ["engagement"]) == []


def test_document_present_but_silent_is_does_not_state():
    """EQ-99/EQ-100: the letter was read and simply has no appraiser phone."""
    src = _Src(engagement=_Doc())
    values = {"appraiser_phone": {"v": "555-1212"}}          # no engagement.* counterpart
    hints = _cross_doc_availability(src, ["appraiser_phone"], values, ["engagement"])
    assert len(hints) == 1
    assert hints[0]["value"]["status"] == "does_not_state"
    assert hints[0]["labels"] == ["appraiser_phone"]


def test_document_absent_is_not_supplied():
    src = _Src(engagement=None)
    hints = _cross_doc_availability(src, ["appraiser_name"], {}, ["engagement"])
    assert len(hints) == 1
    assert hints[0]["value"]["status"] == "not_supplied"


def test_irrelevant_absent_document_never_excuses_the_check():
    """Regression: EQ-C compares the address to the ENGAGEMENT LETTER, but a
    blanket 'no purchase contract was supplied' hint made the judge answer
    NOT_APPLICABLE citing the contract — on an order whose engagement letter was
    present and matched. Only documents the check names may excuse it."""
    src = _Src(engagement=_Doc(), contract=None)
    values = {"property_address": {"v": "1 Main"},
              "engagement.property_address": {"v": "1 Main"}}
    assert _cross_doc_availability(src, ["property_address"], values, ["engagement"]) == []


def test_one_silent_document_does_not_excuse_what_another_answers():
    """Both documents relevant, contract missing, engagement supplies the value →
    the comparison is possible, so no excuse is offered."""
    src = _Src(engagement=_Doc(), contract=None)
    values = {"lender_name": {"v": "Acme"}, "engagement.lender_name": {"v": "Acme"}}
    hints = _cross_doc_availability(src, ["lender_name"], values,
                                    ["engagement", "contract"])
    assert hints == []


# ── intake: recognising the letter in the first place ────────────────────────

def test_order_form_token_floor_recognises_an_untitled_letter():
    """ESNC-0006152's 5-page EngagementLetter.pdf classified as "unknown": too
    long for the `pages <= 3` fallback and titled "STANDARDS OF ENGAGEMENT",
    matching no phrase marker. The whole engagement comparison then degraded
    silently for that order. A short PDF dense in order-form fields is an order
    form — measured 9 tokens on every letter vs 0-4 on contracts."""
    from app.pipeline.intake import (_ORDER_FORM_TOKENS, _ORDER_FORM_TOKEN_FLOOR,
                                     _ENGAGEMENT_MARKERS)
    letter = ("APPRAISER CERTIFICATION OF TERMS AND STANDARDS OF ENGAGEMENT. "
              "Borrower: David Austin. Lender: Cake Mortgage. Loan number 2607064750. "
              "Property address: 1043 Valley Dr. Due date. Client point of contact. "
              "The appraiser must accept the order and complete the inspection.")
    assert sum(1 for t in _ORDER_FORM_TOKENS if t in letter.lower()) >= _ORDER_FORM_TOKEN_FLOOR
    # and the added phrase marker catches it directly too
    assert any(m in letter.lower() for m in _ENGAGEMENT_MARKERS)


def test_contract_text_stays_below_the_order_form_floor():
    """The floor must not sweep in purchase contracts (measured 0-4 tokens)."""
    from app.pipeline.intake import _ORDER_FORM_TOKENS, _ORDER_FORM_TOKEN_FLOOR
    contract = ("PURCHASE AGREEMENT. Seller agrees to sell and buyer agrees to "
                "purchase the real property described herein for the sum stated, "
                "subject to the terms and conditions of this agreement.")
    assert sum(1 for t in _ORDER_FORM_TOKENS if t in contract.lower()) < _ORDER_FORM_TOKEN_FLOOR


# ── photo aspect: multi-scope checks (user directive 2026-07-18) ─────────────

def test_photo_aspect_detected_in_main_text_and_in_trigger_clause():
    """A check can name photos in its requirement OR only in a Triggers: clause —
    both mean a human must look."""
    from app.language.packet_v2 import _has_photo_aspect
    assert _has_photo_aspect(_Item(check_text="Verify condition rating matches with "
                                              "the photos provided in the report."))
    assert _has_photo_aspect(_Item(check_text="Attic — at least 1 checkbox should be "
                                              "checked | Triggers: if photo is provided "
                                              "of attic and None is marked, reject"))
    assert _has_photo_aspect(_Item(check_text="all rooms and GLA must match Sketch"))


def test_map_reference_field_is_not_a_photo_check():
    """The guard that keeps this honest: 'Map Reference' is a form FIELD the
    appraiser types, and 'Proximity to Subject' is a numeric distance. Both are
    machine-checkable and must not be pushed at a human. The real map checks
    (EQ-130..133) are already compiled judgeable=visual."""
    from app.language.packet_v2 import _has_photo_aspect
    assert not _has_photo_aspect(
        _Item(check_text="Map Reference — Provided by the appraiser and must be current"))
    assert not _has_photo_aspect(
        _Item(check_text="Proximity to Subject — Must be provided as at least 0.01 "
                         "miles. If blank, verify that the location Map is provided."))


def test_text_verdict_survives_and_gains_a_manual_photo_note():
    """The point of the multi-scope design: the text part is still judged and
    reported (not collapsed to REVIEW), and the photo note rides alongside."""
    from app.language.run import _mark_photo_verification, _PHOTO_NOTE
    from app.language.verdict_v2 import JudgeVerdict, StatusV2

    jv = JudgeVerdict(item_id="EQ-68", status=StatusV2.SATISFIED,
                      reviewer_line="Condition rating C3 is consistent across comps.")
    out = _mark_photo_verification(
        jv, _Item(check_text="Verify condition rating matches with the photos"))
    assert out.status == StatusV2.SATISFIED          # text verdict preserved
    assert out.photo_verification_required is True
    assert _PHOTO_NOTE in out.reviewer_line
    assert len(out.reviewer_line) <= 240             # validator contract


def test_already_visual_items_are_left_alone():
    """A wholly-visual card IS the instruction; it must not be double-noted."""
    from app.language.run import _mark_photo_verification
    from app.language.verdict_v2 import JudgeVerdict, StatusV2

    jv = JudgeVerdict(item_id="EQ-128", status=StatusV2.REVIEW,
                      judgeable="visual", reviewer_line="Manual visual check: Sketch")
    out = _mark_photo_verification(jv, _Item(check_text="Sketch must have all floors",
                                             judgeable="visual"))
    assert out.photo_verification_required is False


def test_the_word_description_is_recognised_as_a_prose_check():
    """Regression: the pattern was `describ(e|ed|ption)`, which can never match
    "description" — that word is spelt descriP-tion, not descriB-tion. Three checks
    explicitly about a DESCRIPTION (EQ-2 Legal Description, EQ-22 Present Land Use,
    EQ-36 General description) were judged with NO prose attached — asked whether a
    description was provided while the text carrying it was withheld. EQ-22 alone
    hedged on 6 of 15 orders."""
    from app.language.packet_v2 import _COMMENT_REQUIRING_RX
    for word in ("description", "Legal Description", "descriptive",
                 "describe", "described", "summary of the sales comparison"):
        assert _COMMENT_REQUIRING_RX.search(word), word
