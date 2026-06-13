"""
Tests for the reviewer click-to-scroll location pipeline:

  SpatialWordMap.locate_value  — find a value's box among page words
  field_locator._locate_one    — page/ambiguity precision gating + normalization
  python_response._rule_to_json — emits source_page + bbox_{x,y,w,h} from evidence

These cover the previously-missing producing end of the coordinate feature
(everything downstream — Java DTO/entity/mapper and the PDF viewer — was already
wired for source_page + bbox_*).
"""

from app.ocr.spatial_extractor import SpatialWord, SpatialWordMap
from app.extraction import field_locator
from app.core.result import ExtractionResult
from app.qc.result import Evidence, RuleResult, RuleStatus
from app.qc.python_response import _rule_to_json


def _word(x0, text, y=100.0, w=20.0):
    return SpatialWord(x0=x0, y0=y, x1=x0 + w, y1=y + 12.0, text=text, page_number=1)


# ── SpatialWordMap.locate_value ────────────────────────────────────────────────

def test_locate_value_multiword_address():
    wm = SpatialWordMap([
        _word(10, "90"), _word(40, "NE"), _word(70, "32nd", w=30), _word(110, "St"),
    ])
    boxes = wm.locate_value("90 NE 32nd St")
    assert len(boxes) == 1
    x0, y0, x1, y1 = boxes[0]
    assert x0 == 10 and x1 == 130          # spans first word's left to last word's right
    assert y0 == 100.0 and y1 == 112.0


def test_locate_value_ignores_punctuation_and_currency():
    wm = SpatialWordMap([_word(200, "$1,450", w=60)])
    assert wm.locate_value("1450")          # normalized match
    assert wm.locate_value("1,450")
    assert wm.locate_value("$1,450")


def test_locate_value_reports_every_occurrence_for_ambiguity():
    wm = SpatialWordMap([
        _word(10, "C3", y=100.0), _word(10, "C3", y=200.0), _word(10, "C3", y=300.0),
    ])
    assert len(wm.locate_value("C3")) == 3   # caller uses the count to reject ambiguity


def test_locate_value_no_match_returns_empty():
    wm = SpatialWordMap([_word(10, "hello")])
    assert wm.locate_value("world") == []


# ── field_locator._locate_one (precision gating) ───────────────────────────────

def _page_lookup(words, w=600.0, h=800.0):
    wm = SpatialWordMap(words)
    return lambda pno: (wm, w, h)


def test_locate_one_known_page_unique_long_value():
    r = ExtractionResult(canonical_name="property_address", document_type="appraisal_report",
                         value="90 NE 32nd St", source_page=1)
    page = _page_lookup([_word(10, "90"), _word(40, "NE"), _word(70, "32nd", w=30), _word(110, "St")])
    located = field_locator._locate_one(r, page_count=1, page=page)
    assert located is not None
    pno, box = located
    assert pno == 1
    # normalized to fractions of the 600x800 page, with pad applied
    assert 0.0 <= box["x"] < box["x"] + box["w"] <= 1.0
    assert abs(box["x"] - (10 / 600 - field_locator.config.FIELD_LOCATOR_PAD)) < 1e-4


def test_locate_one_known_page_short_ambiguous_is_rejected():
    # "C3" is below MIN_LEN and occurs twice on the page → page-level only.
    r = ExtractionResult(canonical_name="comp_1_condition", document_type="appraisal_report",
                         value="C3", source_page=1)
    page = _page_lookup([_word(10, "C3", y=100.0), _word(10, "C3", y=300.0)])
    assert field_locator._locate_one(r, page_count=1, page=page) is None


def test_locate_one_unknown_page_accepts_unique_match_and_infers_page():
    r = ExtractionResult(canonical_name="lender_name", document_type="appraisal_report",
                         value="Acme Mortgage", source_page=0)
    page = _page_lookup([_word(10, "Acme"), _word(60, "Mortgage", w=70)])
    located = field_locator._locate_one(r, page_count=1, page=page)
    assert located is not None
    pno, _box = located
    assert pno == 1                          # page inferred from the unique hit


def test_locate_one_unknown_page_rejects_ambiguous_match():
    r = ExtractionResult(canonical_name="x", document_type="appraisal_report",
                         value="Smith", source_page=0)
    # Same value on two pages → ambiguous → no box, no page guess.
    wm1 = SpatialWordMap([_word(10, "Smith")])
    wm2 = SpatialWordMap([_word(10, "Smith")])
    pages = {1: (wm1, 600.0, 800.0), 2: (wm2, 600.0, 800.0)}
    located = field_locator._locate_one(r, page_count=2, page=lambda pno: pages[pno])
    assert located is None


# ── python_response emits the location to the Java contract ────────────────────

def test_rule_to_json_emits_bbox_from_appraisal_evidence():
    box = {"x": 0.1, "y": 0.2, "w": 0.3, "h": 0.04}
    r = RuleResult(
        rule_id="S-1", checklist_num="1", section="subject", status=RuleStatus.FAIL,
        message="mismatch", fields_involved=["property_address"],
        evidence=[
            Evidence(document="engagement", value="123 Main St", confidence=0.9, page=1),
            Evidence(document="appraisal", value="90 NE 32nd St", confidence=0.95,
                     page=3, bbox=box, field="property_address"),
        ],
    )
    out = _rule_to_json(r)
    assert out["source_page"] == 3           # appraisal-with-box wins over the engagement page
    assert out["bbox_x"] == 0.1 and out["bbox_y"] == 0.2
    assert out["bbox_w"] == 0.3 and out["bbox_h"] == 0.04
    # per-evidence bbox preserved for future multi-field clicking
    appraisal_ev = next(e for e in out["evidence"] if e["document"] == "appraisal")
    assert appraisal_ev["bbox"] == box


def test_rule_to_json_page_level_only_when_no_box():
    r = RuleResult(
        rule_id="S-2", checklist_num="2", section="subject", status=RuleStatus.VERIFY,
        message="check", fields_involved=["gla"],
        evidence=[Evidence(document="appraisal", value="1450", confidence=0.8, page=2)],
    )
    out = _rule_to_json(r)
    assert out["source_page"] == 2
    assert out["bbox_x"] is None and out["bbox_h"] is None
