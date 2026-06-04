"""Unit tests for checkbox mark detection (tolerance clustering)."""

import fitz

from app.ocr.checkbox_extractor import _checked_from_drawings


def _rect(x0, y0):
    r = fitz.Rect(x0, y0, x0 + 8.4, y0 + 8.4)
    return {'rect': r, 'items': [('re', r)], 'fill': None, 'type': 's'}


def _diag_line(x0, y0):
    r = fitz.Rect(x0, y0, x0 + 8.4, y0 + 8.4)
    return {'rect': r, 'items': [('l', fitz.Point(x0, y0), fitz.Point(x0 + 8, y0 + 8))],
            'fill': None, 'type': 's'}


def test_split_rect_and_xmark_is_checked():
    # The real bug: border rect at x0=145.4, its two X lines at x0=145.3.
    # 1dp rounding split them apart; tolerance clustering keeps them together.
    draws = [_rect(145.4, 130.0), _diag_line(145.3, 130.0), _diag_line(145.3, 130.0)]
    assert len(_checked_from_drawings(draws)) == 1


def test_bare_rect_is_unchecked():
    assert _checked_from_drawings([_rect(65.0, 130.0)]) == []


def test_filled_box_is_checked():
    r = fitz.Rect(10, 10, 18.4, 18.4)
    draws = [{'rect': r, 'items': [('re', r)], 'fill': (0, 0, 0), 'type': 'f'}]
    assert len(_checked_from_drawings(draws)) == 1


def test_adjacent_boxes_not_merged():
    # Two distinct option boxes ~39px apart: one checked (X), one empty.
    draws = [_rect(65.0, 130.0),                                   # empty
             _rect(104.4, 130.0), _diag_line(104.3, 130.0), _diag_line(104.3, 130.0)]
    checked = _checked_from_drawings(draws)
    assert len(checked) == 1
    assert abs(checked[0]['x'] - 104.4) < 1.0
