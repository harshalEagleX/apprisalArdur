"""Unit tests for the sales-comparison narrative prose filter.

These lock in which page-3 text blocks count as the appraiser's own commentary
vs the blank-form boilerplate / UAD grid cells that a naive label match grabs.
"""

from app.extraction.narrative_extractor import _is_prose


# --- real appraiser narrative (must be kept) ---------------------------------

def test_keeps_real_summary_sentence():
    txt = ("Most of the emphasis was placed upon the Sales Comparison Approach as it "
           "most accurately reflects the actions of buyers and sellers in the market place.")
    assert _is_prose(txt) is True


def test_keeps_adjustment_reasoning():
    txt = ("GLA adjustments are not deemed necessary for those different by less than "
           "100 sf and age adjustments are calculated with paired sales.")
    assert _is_prose(txt) is True


# --- boilerplate / template / grid (must be dropped) -------------------------

def test_drops_software_footer():
    txt = 'Form 1004UAD - "TOTAL" appraisal software by a la mode, inc. - 1-800-ALAMODE'
    assert _is_prose(txt) is False


def test_drops_form_identifier_line():
    txt = "Freddie Mac Form 70 March 2005 UAD Version 9/2011 Page 2 of 6 Fannie Mae Form 1004"
    assert _is_prose(txt) is False


def test_drops_blank_template_sentence():
    txt = ("There are comparable sales in the subject neighborhood within the past twelve "
           "months ranging in sale price from $ to $ .")
    assert _is_prose(txt) is False


def test_drops_fixed_hypothetical_template():
    txt = ('This appraisal is made "as is", subject to completion per plans and '
           "specifications on the basis of a hypothetical condition that the improvements")
    assert _is_prose(txt) is False


def test_drops_uad_grid_cell_leakage():
    txt = ("ArmLth Conv;0 s05/26;Unk N;Res; Fee Simple 635 As listed On page 2 11th Floor 0 "
           "ArmLth Conv;0 s04/26;Unk N;Res; Fee Simple 635 As listed On page 2")
    assert _is_prose(txt) is False


def test_drops_grid_header_fragment():
    txt = ("Proximity to Subject Sale Price $ $ $ $ Sale Price/Gross Liv. Area $ sq.ft. "
           "Data Source(s) Verification Source")
    assert _is_prose(txt) is False


def test_drops_short_fragment():
    assert _is_prose("Indicated Value by Sales Comparison Approach") is False
