"""
Tests for per-comparable coordinate capture in the comp-grid extractor — the fix
that lets SCA (sales-comparison) review rules scroll to the exact comparable cell.
These are pure (no PDF): they exercise the token→bbox and normalize helpers that
the extractor uses to record each cell's location.
"""

from app.extraction.comp_grid_extractor import _value_in_band, _norm_box


def _w(text, x0, top, x1, bottom):
    return {"text": text, "x0": x0, "top": top, "x1": x1, "bottom": bottom}


def test_value_in_band_returns_text_and_token_bbox():
    # Two tokens of one comparable cell on the same row, inside the band.
    words = [_w("N;Res;", 300, 410, 340, 420), _w("Pool", 342, 410, 370, 420),
             _w("OTHER", 500, 410, 540, 420)]  # outside the band → excluded
    text, bbox = _value_in_band(words, y=410, lo=295, hi=400)
    assert text == "N;Res; Pool"
    assert bbox == (300, 410, 370, 420)        # spans both in-band tokens only


def test_value_in_band_empty_band_has_no_bbox():
    words = [_w("x", 10, 10, 20, 20)]
    text, bbox = _value_in_band(words, y=400, lo=295, hi=400)
    assert text == "" and bbox is None


def test_norm_box_normalizes_to_fractions_top_left():
    # 612x792 US-Letter page; a token box at x0=306 (mid), top=396 (mid).
    box = _norm_box((306, 396, 366, 408), page_w=612, page_h=792, pad=0.0)
    assert abs(box["x"] - 0.5) < 1e-3
    assert abs(box["y"] - 0.5) < 1e-3
    assert box["w"] > 0 and box["h"] > 0
    assert 0 <= box["x"] <= 1 and box["y"] + box["h"] <= 1


def test_norm_box_none_for_empty_or_zero_page():
    assert _norm_box(None, 612, 792) is None
    assert _norm_box((0, 0, 10, 10), 0, 0) is None
