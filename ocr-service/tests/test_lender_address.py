"""Unit tests for appraisal lender-address positional capture (S-10b)."""

from app.extraction.layers.l5_uad_template import _lender_address_after


def _w(x0, x1, t):
    # PyMuPDF word tuple: (x0, y0, x1, y1, text, block, line, word)
    return (x0, 100.0, x1, 110.0, t, 0, 0, 0)


def test_lender_address_after_captures_full_address():
    words = [
        _w(10, 60, "Lender/Client"), _w(65, 140, "Champions"), _w(142, 175, "Funding,"),
        _w(177, 200, "LLC"), _w(205, 250, "Address"), _w(255, 290, "365"),
        _w(295, 330, "East"), _w(335, 420, "Germann"), _w(425, 470, "Road,"),
        _w(475, 520, "Suite"), _w(525, 545, "140,"), _w(550, 610, "Gilbert,"),
        _w(615, 640, "AZ"), _w(645, 700, "85297"),
    ]
    assert _lender_address_after(words, words[0]) == \
        "365 East Germann Road, Suite 140, Gilbert, AZ 85297"


def test_no_address_label_returns_none():
    words = [_w(10, 60, "Lender/Client"), _w(65, 140, "Champions"), _w(142, 175, "Funding")]
    assert _lender_address_after(words, words[0]) is None


def test_address_without_digits_rejected():
    # A trailing prose word after "Address" with no street number/zip is not an address.
    words = [_w(10, 60, "Lender/Client"), _w(65, 140, "Name"),
             _w(205, 250, "Address"), _w(255, 320, "Unknown")]
    assert _lender_address_after(words, words[0]) is None
