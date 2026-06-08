"""Comparable-photo signals — locate the comp-photo addendum page(s), render them,
and (when Google Cloud Vision is configured) derive QC signals from the imagery.

This is an EXTRACTION component (P-3): it returns flat pseudo-fields that the SCA-27 /
SCA-16V rules read. It never decides PASS/FAIL — it reports what the photos show.

Fields produced (all optional — absent means "unknown", the rule then VERIFYs):
  comp_photo_pages        int   number of comparable-photo addendum pages found
  vision_enabled          bool  was Cloud Vision actually used
  comp_photo_building     bool  the photos depict buildings/houses (exterior)
  comp_photo_mls_text     bool  MLS/realtor watermark text detected on the photos
  comp_photo_distress     bool  distress labels detected (ruins/boarded-up/tarp/…)

Without Cloud Vision only comp_photo_pages + vision_enabled=false are produced — enough
for SCA-27 to confirm a photo page exists and route the image-quality judgement to a
reviewer (VERIFY), never a false PASS.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

# Captions/headers that mark a comparable-photo addendum page. (The per-image label
# vocabularies live in the analyzer backends — this module only locates + renders.)
_COMP_PAGE_MARKERS = (
    "comparable photo", "comparable sale photo", "photograph addendum",
    "comparable 1", "comparable 2", "comparable 3", "comp 1", "comp 2", "comp 3",
    "comparable sale 1", "comparable sale 2", "comparable sale 3",
)


def _comp_photo_pages(pdf) -> List[int]:
    """0-indexed pages whose text marks them as a comparable-photo addendum."""
    pages = []
    for i in range(pdf.page_count):
        try:
            txt = pdf.load_page(i).get_text("text").lower()
        except Exception:
            continue
        if any(m in txt for m in _COMP_PAGE_MARKERS) and "comparable" in txt:
            pages.append(i)
    return pages


def extract_comp_photo_signals(pdf_path) -> Dict[str, str]:
    """Return the comparable-photo pseudo-fields (see module docstring)."""
    import fitz

    from app import config
    from app.vision import analyzer_available, get_photo_analyzer

    out: Dict[str, str] = {}
    try:
        pdf = fitz.open(str(Path(pdf_path)))
    except Exception as exc:
        logger.warning("Comp-photo open failed for %s: %s", pdf_path, exc)
        return out
    try:
        pages = _comp_photo_pages(pdf)
        out["comp_photo_pages"] = str(len(pages))
        analyzer = get_photo_analyzer() if analyzer_available() else None
        out["vision_enabled"] = str(bool(analyzer))
        if not analyzer or not pages:
            return out

        # COST GUARD: cap pages analyzed; MLS text only when the operator opted in
        # (Cloud Vision bills per feature — Gemini returns all signals in one call).
        want_text = config.VISION_DETECT_MLS
        pages = pages[: max(0, config.VISION_MAX_PAGES)]
        analyzed = 0
        building = distress = False
        mls: Optional[bool] = None
        worst_cond = 0
        for pi in pages:
            try:
                img_bytes = pdf.load_page(pi).get_pixmap(dpi=150).tobytes("png")
            except Exception as exc:
                logger.debug("render comp-photo page %d failed: %s", pi, exc)
                continue
            sig = analyzer.analyze(img_bytes, want_text=want_text)
            if sig is None:
                continue  # transient API failure — don't let it imply "not a building"
            analyzed += 1
            building = building or sig.building
            distress = distress or sig.distress
            if sig.mls_text:
                mls = True
            elif mls is None and sig.mls_text is not None:
                mls = False
            if sig.condition and sig.condition[1:].isdigit():
                worst_cond = max(worst_cond, int(sig.condition[1:]))  # keep the worst (highest C#)
        out["comp_photo_analyzed"] = str(analyzed)
        # Only ASSERT the visual signals when at least one page was actually analyzed,
        # so a vision outage degrades to "could not verify" (VERIFY) rather than a
        # false "not a building" negative.
        if analyzed == 0:
            out["comp_photo_vision_error"] = "True"
            return out
        out["comp_photo_building"] = str(building)
        out["comp_photo_distress"] = str(distress)
        if mls is not None:
            out["comp_photo_mls_text"] = str(mls)
        if worst_cond:
            out["comp_photo_condition"] = f"C{worst_cond}"
    finally:
        pdf.close()
    return out
