"""Regression: the row-bleed heuristic must not nuke long free narrative.

A grid cell (or its cross-comp bleed) is short; free prose (AppraisalAddendumText,
long comments) repeats common words by nature. ESMI-0049134 shipped a 40 KB
AppraisalAddendumText that `_repeated_grid_cell` mistook for row bleed and
suppressed, punting ~12 narrative checks (EQ-14/25/72/86/87/118/120 …) to REVIEW
and hiding the EQ-21 predominant-value comment and EQ-30 legal-nonconforming text.
"""
from app.extraction.plausibility import _repeated_grid_cell


def test_short_grid_bleed_still_detected():
    # the shapes the guard exists for — unchanged behavior
    assert _repeated_grid_cell("Porch/Patio Porch/Deck Porch/Pat/Deck") is True
    assert _repeated_grid_cell("2Balcony 2Balcony 2Balcony") is True


def test_legit_single_cell_not_flagged():
    assert _repeated_grid_cell("Concrete Slab Foundation") is False
    assert _repeated_grid_cell("Prch/Patio/Deck") is False


def test_long_narrative_is_never_grid_bleed():
    prose = (
        "The highest and best use of the subject property is its current use as a "
        "multi family home. To estimate the highest and best use of a site, the "
        "appraiser utilizes the four tests of highest and best use. The subject is "
        "legal non-conforming. The subject property can be rebuilt as long as it is "
        "in the correct zoning and using the original foundation. " * 4
    )
    assert len(prose) > 300
    assert _repeated_grid_cell(prose) is False
