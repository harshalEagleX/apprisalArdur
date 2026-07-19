"""Document-wide narrative sweep — finding a statement wherever the appraiser put it.

2026-07-18: EQ-122 "Reasonable Exposure Time" reported `reasonable_exposure_time
absent` on 11 of 15 orders while the statement is present in almost every report:

    ESMD-0002883  "…is deemed to be 0-90 days similar to the marketing time…"  → 0-90 days
    ESNC-0006153  "Exposure Time: The estimated exposure time is 6-12 weeks."  → 6-12 weeks
    ESTX-0007568  "…proved a range of exposure time … to be 0-3 months."       → 0-3 months
    ESCA-0019968  "…in this report is: Additional Certifications"              → genuinely BLANK

Telling a reviewer to go find something the report plainly states is the worst kind
of queue noise. Narrative has no fixed home — USPAP addendum, a certification page,
loose commentary — so the sweep reads the WHOLE document (OCR'ing image-only pages),
anchored on the field's schema synonyms, and returns page + bbox so the card can
scroll to the sentence.

The ESCA case is the one that proves the sweep is honest rather than eager: it must
still find nothing when the answer really is missing.
"""

import re

import pytest

from app.extraction.sweep import _usable_value, _first_sentence


DURATION = re.compile(r"\d+\s*(?:-|–|to|\+)?\s*\d*\s*(?:day|week|month|year)s?", re.I)


# ── pulling the answer out of the prose it is wrapped in ────────────────────

@pytest.mark.parametrize("span,expected", [
    ("A reasonable exposure time for the subject is deemed to be 0-90 days "
     "similar to the marketing time referenced in the neighborhood section.", "0-90 days"),
    ("Exposure Time: The estimated exposure time is 6-12 weeks. Exposure Time is "
     "the presumed length of time that the subject would have been offered.", "6-12 weeks"),
    ("an analysis of the historical sales over the past 12 months proved a range "
     "of exposure time, at a market price, to be 0-3 months.", "12 months"),
])
def test_value_pattern_finds_the_duration_inside_prose(span, expected):
    assert _usable_value(span, DURATION) == expected


def test_definition_boilerplate_is_never_captured_as_the_value():
    """Forms restate the USPAP definition right beside the appraiser's answer.
    Capturing that would be worse than finding nothing."""
    span = ("Reasonable Exposure Time (USPAP defines Exposure Time as the estimated "
            "length of time that the property interest being appraised would have "
            "been offered on the market prior to a hypothetical sale)")
    assert _usable_value(span, DURATION) is None


def test_definition_marker_after_the_value_does_not_reject_it():
    """Only a definition marker BEFORE the match invalidates it — otherwise the
    trailing USPAP sentence would suppress a perfectly good answer."""
    span = ("The estimated exposure time is 6-12 weeks. Exposure Time is the "
            "presumed length of time that the subject would have been offered.")
    assert _usable_value(span, DURATION) == "6-12 weeks"


def test_blank_form_line_yields_nothing():
    """ESCA-0019968: the appraiser left the certification line empty. The sweep
    must NOT invent a value from the following section header — a genuinely
    missing USPAP field is a real finding the reviewer should see."""
    span = ("My opinion of a reasonable exposure time for the subject property at "
            "the market value stated in this report is: Additional Certifications "
            "I have performed NO services, as an appraiser")
    assert _usable_value(span, DURATION) is None


def test_without_a_pattern_the_first_sentence_is_used():
    span = "Neighborhood Boundaries are the river to the north and Route 9 south. Next thing."
    assert _usable_value(span, None) == (
        "Neighborhood Boundaries are the river to the north and Route 9 south.")


def test_first_sentence_stops_at_the_sentence_boundary():
    assert _first_sentence("Alpha beta. Gamma delta.") == "Alpha beta."


# ── the sweep must never outrank a structured witness ───────────────────────

def test_sweep_is_skipped_when_nothing_is_missing():
    from app.extraction.sweep import extract_sweep
    from app.extraction.schema import schema_loader
    assert list(extract_sweep("does-not-matter.pdf", schema_loader, set())) == []


def test_sweep_confidence_sits_below_structured_extractors():
    """XML .97 / AcroForm .95 / template .90 must all beat a prose read."""
    from app.extraction.sweep import _CONF
    assert _CONF < 0.90


# ── the box must cover the VALUE, not just the label ────────────────────────

def test_located_box_spans_label_and_value():
    """User directive 2026-07-18: highlighting only the anchor word makes the
    reviewer hunt for the answer the card exists to show. The box must cover the
    area the check is about — label AND value found."""
    from app.extraction.sweep import _locate

    class _R:
        def __init__(s, x0, y0, x1, y1):
            s.x0, s.y0, s.x1, s.y1 = x0, y0, x1, y1
            s.width, s.height = x1 - x0, y1 - y0

    class _Page:
        rect = _R(0, 0, 100.0, 100.0)
        def search_for(self, needle):
            return {"Exposure Time": [_R(10, 50, 30, 54)],
                    "0-90 days": [_R(35, 50, 50, 54)]}.get(needle, [])

    box = _locate(_Page(), "Exposure Time", "0-90 days")
    assert box["x"] == pytest.approx(0.10)          # starts at the label
    assert box["w"] == pytest.approx(0.40)          # ...and runs through the value


def test_far_away_value_match_does_not_stretch_the_box():
    """A coincidental hit elsewhere on the page would produce a box spanning half
    the document — keep the label box instead."""
    from app.extraction.sweep import _locate

    class _R:
        def __init__(s, x0, y0, x1, y1):
            s.x0, s.y0, s.x1, s.y1 = x0, y0, x1, y1
            s.width, s.height = x1 - x0, y1 - y0

    class _Page:
        rect = _R(0, 0, 100.0, 100.0)
        def search_for(self, needle):
            return {"Exposure Time": [_R(10, 10, 30, 14)],
                    "0-90 days": [_R(35, 900, 50, 904)]}.get(needle, [])

    box = _locate(_Page(), "Exposure Time", "0-90 days")
    assert box["h"] == pytest.approx(0.04)          # label height only


# ── opt-in only: guessing is worse than finding nothing ─────────────────────

def test_sweep_ignores_fields_that_declare_no_value_pattern():
    """Caught before shipping 2026-07-18. Without a pattern the fallback was "the
    first sentence after the synonym" — but on a URAR the field LABELS are printed
    on the blank form, so every synonym matched a label with no value after it. A
    real run injected 13 fields of pure form furniture at confidence 0.70
    (comp_N_proximity = "Proximity to Subject Sale Price $ $ $ $", cooling =
    "Air Conditioning Individual Other Amenities…") which the judge would have
    treated as extracted values.

    A wrong value produces a confident wrong verdict; a missing one produces an
    honest VERIFY. So the sweep is OPT-IN: a field must declare what a real answer
    looks like, or the sweep leaves it alone."""
    from app.extraction.schema import schema_loader

    opted_in = {f.canonical_name for f in schema_loader.all_fields()
                if getattr(f, "value_pattern", "")}
    assert "reasonable_exposure_time" in opted_in
    # the fields that produced form furniture must NOT be opted in
    for name in ("comp_N_proximity", "cooling", "comp_N_address",
                 "comp_N_location_rating", "comp_N_data_source"):
        assert name not in opted_in, name


def test_ocr_budget_is_bounded():
    """A 300dpi render + Tesseract pass is ~1-2s/page; an uncapped sweep over a
    scanned report would add minutes to every run."""
    from app.extraction.sweep import _OCR_PAGE_BUDGET
    assert 0 < _OCR_PAGE_BUDGET <= 12


def test_page_text_is_lazy_and_memoized():
    """Finding the answer on page 1 must not pay for reading page 40."""
    from app.extraction.sweep import _PageText

    reads = []

    class _P:
        def __init__(self, n): self.n = n
        def get_text(self):
            reads.append(self.n)
            return "x" * 100

    pages = _PageText([(1, _P(1)), (2, _P(2)), (3, _P(3))])
    pages.text(1, pages._pages[0][1])
    pages.text(1, pages._pages[0][1])          # cached, not re-read
    assert reads == [1]


def test_sweep_runs_after_plausibility_not_before():
    """ORDERING BUG, caught by end-to-end wiring verification 2026-07-19.

    The sweep first ran at step 6b, BEFORE plausibility, keyed on "field not in
    merged". It was therefore dead for exactly the case it exists to fix: a spatial
    reader had already dropped the label fragment "of" into
    `reasonable_exposure_time`, so the field was not "missing", the sweep skipped
    it — and plausibility then suppressed the junk, leaving nothing behind. The
    unit tests passed because they named the field explicitly and never exercised
    the `still_missing` computation.

    "Missing" must mean NO USABLE VALUE (`not ef.found`, which is False once
    suppressed), not "no key present"."""
    import inspect
    from app.extraction import merge

    src = inspect.getsource(merge.run_extraction)
    i_plaus = src.index("plausibility.validate_fields")
    i_sweep = src.index("extract_sweep")
    assert i_sweep > i_plaus, "the sweep must run after plausibility"
    assert 'getattr(merged.get(fd.canonical_name), "found", False)' in src, (
        "still_missing must be computed from .found, not from key presence")
