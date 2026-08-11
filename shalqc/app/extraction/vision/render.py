"""
extraction.vision.render (rnd-1.0.0) — PDF page -> PNG bytes the model can read,
plus the token arithmetic that makes the cost of doing so predictable.

Rendering is where cost is decided. An image's price is set entirely by its
pixel count, so DPI is the single most powerful cost lever in the 3.6 path and
the one most likely to be picked by feel. This module makes it arithmetic:
`image_tokens()` is the same formula the API bills on, so the budget governor
can refuse a call BEFORE it is made rather than discovering the overrun after.
"""

from __future__ import annotations

import base64
import logging
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

__version__ = "rnd-1.0.0"

logger = logging.getLogger(__name__)

# Anthropic bills images at roughly (width x height) / 750 tokens.
_PX_PER_TOKEN = 750

# High-resolution tier (Claude Sonnet 5, Opus 4.7+): images are downscaled to fit
# a 2576px long edge, and a single image costs at most ~4,784 tokens. Older tiers
# (Haiku 4.5) downscale to 1568px instead — encoded here rather than assumed,
# because getting it wrong silently doubles or halves every cost projection.
_HIRES_MAX_EDGE, _HIRES_MAX_TOKENS = 2576, 4784
_LORES_MAX_EDGE, _LORES_MAX_TOKENS = 1568, 1600

_HIRES_MODELS = ("claude-sonnet-5", "claude-opus-5", "claude-opus-4-8",
                 "claude-opus-4-7", "claude-fable-5", "claude-mythos-5")


@dataclass
class RenderedPage:
    """A page image plus everything needed to price and locate it."""

    page: int
    b64: str
    media_type: str
    width: int
    height: int
    dpi: int
    # Fractional clip region of the source page, when this is a crop rather than
    # a whole page: {x, y, w, h} in 0..1, top-left origin — the same convention
    # ExtractedField.bbox uses, so a crop-relative box can be mapped back to the
    # full page for the reviewer's click-to-scroll.
    clip: Optional[Dict[str, float]] = None

    @property
    def tokens(self) -> int:
        return image_tokens(self.width, self.height)


def image_tokens(width: int, height: int, model: str = "claude-sonnet-5") -> int:
    """Billable image tokens, accounting for the tier's downscale and ceiling."""
    max_edge, max_tokens = (
        (_HIRES_MAX_EDGE, _HIRES_MAX_TOKENS)
        if any(m in model for m in _HIRES_MODELS)
        else (_LORES_MAX_EDGE, _LORES_MAX_TOKENS)
    )
    long_edge = max(width, height)
    if long_edge > max_edge:
        scale = max_edge / long_edge
        width, height = int(width * scale), int(height * scale)
    return min(int(width * height / _PX_PER_TOKEN), max_tokens)


def page_pixels(width_pt: float, height_pt: float, dpi: int) -> Tuple[int, int]:
    """PDF points (72/inch) -> pixels at the given DPI. Pure arithmetic, so a
    cost projection can be computed from page_map alone without rendering."""
    return int(round(width_pt * dpi / 72.0)), int(round(height_pt * dpi / 72.0))


def render_page(pdf_path, page_no: int, dpi: int = 150) -> Optional[RenderedPage]:
    """Render one 1-indexed page to a PNG. None on failure — never raises, so a
    single bad page degrades that page rather than the order."""
    return render_region(pdf_path, page_no, dpi=dpi, clip=None)


def render_region(pdf_path, page_no: int, dpi: int = 150,
                  clip: Optional[Dict[str, float]] = None) -> Optional[RenderedPage]:
    """Render a page, or a fractional sub-rectangle of it.

    `clip` is the mitigation for dense grids: cropping to one comparable's column
    and rendering THAT at high DPI puts far more pixels on the cells that matter
    than raising DPI over the whole page ever could, at a fraction of the tokens.
    It is also the defense against a column-shift misread — a crop that contains
    exactly one comparable cannot be read one column to the right.
    """
    import fitz

    try:
        doc = fitz.open(str(pdf_path))
    except Exception as exc:
        logger.warning("render: cannot open %s: %s", pdf_path, exc)
        return None
    try:
        if not (1 <= page_no <= len(doc)):
            logger.warning("render: page %d out of range (1..%d)", page_no, len(doc))
            return None
        page = doc[page_no - 1]
        rect = page.rect

        clip_rect = None
        if clip:
            clip_rect = fitz.Rect(
                rect.x0 + clip["x"] * rect.width,
                rect.y0 + clip["y"] * rect.height,
                rect.x0 + (clip["x"] + clip["w"]) * rect.width,
                rect.y0 + (clip["y"] + clip["h"]) * rect.height,
            )

        pix = page.get_pixmap(dpi=dpi, clip=clip_rect)
        png = pix.tobytes("png")
        return RenderedPage(
            page=page_no, b64=base64.b64encode(png).decode("ascii"),
            media_type="image/png", width=pix.width, height=pix.height,
            dpi=dpi, clip=clip,
        )
    except Exception as exc:
        logger.warning("render: page %d failed: %s", page_no, exc)
        return None
    finally:
        doc.close()


def label_and_column_clips(comp_index: int, n_columns: int,
                           label_width: float = 0.28) -> Tuple[Dict[str, float], Dict[str, float]]:
    """(label strip, one comparable's column strip) as two fractional clips.

    Sent as two images in one call, this gives the model the row labels at full
    resolution AND a single comparable's values at full resolution, with no
    neighbouring column in frame to shift into.
    """
    col_width = (1.0 - label_width) / max(n_columns, 1)
    x = label_width + comp_index * col_width
    # Padding is a measured trade between two real failures, not a guess:
    #
    #   4%  — text that overflows its cell gets sliced. A comparable's address
    #         read as "4 Floyd Springs Rd NE, Buchee" instead of "2324 Floyd
    #         Springs Rd NE, Armuchee". Every NUMBER was still correct.
    #   22% — the neighbouring column becomes visible and the model reads it too.
    #         Comparable 1 came back with 14 line adjustments instead of 7 and
    #         its checksum failed.
    #
    # 8% sits between them, and the tie-breaks toward the tighter side because
    # the failures are not equally bad: a clipped address is one wrong string
    # that the checksum cannot catch but a reviewer can see, whereas a bled
    # column corrupts the adjustment set and takes the whole comparable's
    # verification down with it. Numbers are load-bearing; the address is not.
    pad = col_width * 0.08
    labels = {"x": 0.0, "y": 0.0, "w": min(label_width + pad, 1.0), "h": 1.0}
    left = max(x - pad, 0.0)
    column = {"x": left, "y": 0.0,
              "w": min(col_width + 2 * pad, 1.0 - left), "h": 1.0}
    return labels, column


def detect_grid_columns(pdf_path, page_no: int,
                        tol: float = 0.004) -> Optional[List[float]]:
    """Fractional x boundaries of the sales grid, MEASURED from the page's rules.

    `label_and_column_clips` assumes the grid spans the full page width and that
    the label column is 28% of it. On the sample report neither is true: the grid
    occupies x ∈ [0.153, 0.847] in five equal columns of 0.1385 (label, subject,
    then the comparables). The assumed geometry therefore puts comparable 1's crop
    at [0.446, 0.655] where the column actually lives at [0.431, 0.569] — which
    simultaneously **clips 1.5% off the left of its own cell** and **includes 62%
    of the neighbouring comparable**.

    That single error produced both halves of what the problem log recorded as an
    unavoidable padding trade-off (P11): the clipped address ("24 Floyd Springs
    Rd NE" for "2324 Floyd Springs Rd NE" — values are right-aligned, so overflow
    runs off the LEFT edge) and the bled neighbouring column. It is not a
    trade-off between two failures, it is one wrong assumption causing both, and
    measuring the page removes them together.

    The boundaries are recovered as the longest arithmetic progression among the
    x-coordinates where the page's horizontal rules start and stop — the grid's
    columns are uniform, so they are exactly a progression, while the
    value/adjustment sub-dividers inside each column are not. Returns None when
    no such structure is found, and the caller falls back to the proportional
    estimate.
    """
    import collections

    import fitz

    try:
        doc = fitz.open(str(pdf_path))
    except Exception as exc:
        logger.warning("render: cannot open %s: %s", pdf_path, exc)
        return None
    try:
        if not (1 <= page_no <= len(doc)):
            return None
        page = doc[page_no - 1]
        width = page.rect.width or 1.0
        weights: "collections.Counter[float]" = collections.Counter()
        for item in page.get_drawings():
            for op in item.get("items", ()):
                if op[0] == "l":
                    p1, p2 = op[1], op[2]
                    if abs(p1.y - p2.y) < 0.6 and abs(p1.x - p2.x) > 40:
                        weights[round(p1.x / width, 3)] += 1
                        weights[round(p2.x / width, 3)] += 1
                elif op[0] == "re":
                    rect = op[1]
                    if rect.width > 20 and rect.height > 3:
                        weights[round(rect.x0 / width, 3)] += 1
                        weights[round(rect.x1 / width, 3)] += 1
    except Exception as exc:
        logger.warning("render: column detection failed on page %d: %s", page_no, exc)
        return None
    finally:
        doc.close()

    if not weights:
        return None

    # Merge near-duplicate x (the same rule drawn at 0.511 and 0.512) and keep
    # only edges the page draws repeatedly — a table boundary is restated on
    # every row, an incidental line is not.
    merged: Dict[float, int] = {}
    for x in sorted(weights):
        for seen in merged:
            if abs(x - seen) <= tol:
                merged[seen] += weights[x]
                break
        else:
            merged[x] = weights[x]
    strong = sorted(x for x, n in merged.items() if n >= 6)
    if len(strong) < 4:
        return None

    # Longest arithmetic progression: the columns are uniform, so they fit one;
    # sub-dividers and stray rules do not.
    #
    # The match tolerance is deliberately looser than the merge tolerance. A step
    # is measured from the first two boundaries and then extrapolated, so tiny
    # rounding differences ACCUMULATE — on this page the true step is 0.1385 and
    # the measured one 0.138, which by the sixth boundary has drifted 0.0025 and
    # silently dropped the last comparable off the end of the grid.
    reach = max(tol * 2.0, 0.008)
    best: Tuple[int, float, float] = (0, 0.0, 0.0)
    for i, start in enumerate(strong):
        for j in range(i + 1, len(strong)):
            step = strong[j] - start
            if step < 0.05:
                continue
            count = 0
            while any(abs(x - (start + count * step)) <= reach for x in strong):
                count += 1
            if count > best[0]:
                best = (count, start, step)

    count, start, step = best
    # 4 boundaries = label + subject + one comparable. Fewer is not a grid.
    if count < 4:
        return None
    # Snap each predicted boundary back onto the coordinate the page actually
    # drew, so the crop uses measured edges rather than extrapolated ones.
    bounds: List[float] = []
    for k in range(count):
        predicted = start + k * step
        bounds.append(round(min(strong, key=lambda x: abs(x - predicted)), 4))
    return bounds


def grid_column_clips(pdf_path, page_no: int, comp_index: int, n_columns: int,
                      label_width: float = 0.28
                      ) -> Tuple[Dict[str, float], Dict[str, float]]:
    """(label strip, one comparable's column) using MEASURED boundaries if the
    page yields them, and the proportional estimate if it does not.

    `comp_index` counts data columns from the subject: 0 = subject, 1 = the first
    comparable — the same convention `label_and_column_clips` uses.
    """
    bounds = detect_grid_columns(pdf_path, page_no)
    # bounds[0]..bounds[1] is the label column; each subsequent pair is a data
    # column. comp_index 1 therefore needs bounds[2]..bounds[3] to exist.
    if not bounds or len(bounds) < comp_index + 3:
        return label_and_column_clips(comp_index, n_columns, label_width)

    col_w = bounds[1] - bounds[0]
    # A hair of padding so the boundary rule itself is not sliced; far smaller
    # than the 8% needed when the edges were being guessed.
    pad = col_w * 0.02
    left = max(bounds[0] - pad, 0.0)
    labels = {"x": left, "y": 0.0, "w": min(bounds[1] + pad - left, 1.0 - left), "h": 1.0}
    c0 = max(bounds[comp_index + 1] - pad, 0.0)
    c1 = min(bounds[comp_index + 2] + pad, 1.0)
    column = {"x": c0, "y": 0.0, "w": c1 - c0, "h": 1.0}
    return labels, column


def render_label_value_composite(pdf_path, page_no: int, comp_index: int,
                                 n_columns: int, dpi: int = 150,
                                 label_width: float = 0.28) -> Optional[RenderedPage]:
    """The label strip and one comparable's column, JOINED INTO ONE IMAGE.

    Sending the two crops as two images requires the model to correlate them by
    ORDINAL POSITION — "row N of image 2 belongs to row N's label in image 1" —
    and that assumption breaks on this form, because the grid's rows are not
    uniform: photo rows are enormous, band headers interrupt the sequence, and
    several value cells are merged across rows.

    Measured on comparable 1 of the sample report, the two-image form produced
    two silent errors on one column:

      * `site_size` came back **$0** where the page prints **$(23,800)** — the
        largest adjustment in the column, and the one whose sign matters most.
        A $0 is entirely plausible, so nothing downstream could doubt it.
      * the porch/patio row's **$5,000** was dropped outright.

    Together those are exactly the 18,800 by which that column's checksum failed
    to close. Both are alignment failures, not reading failures — every figure
    was legible.

    Compositing removes the correlation step: the label sits physically beside
    its own value at the same vertical offset, so a row cannot be read against a
    neighbour's label without the model ignoring what is in front of it. Both
    crops span the full page height, so their pixel rows correspond exactly.
    """
    labels_clip, column_clip = grid_column_clips(pdf_path, page_no, comp_index,
                                                 n_columns, label_width)
    left = render_region(pdf_path, page_no, dpi=dpi, clip=labels_clip)
    right = render_region(pdf_path, page_no, dpi=dpi, clip=column_clip)
    if left is None or right is None:
        return None

    try:
        import io
        from PIL import Image
    except ImportError:  # pragma: no cover - dependency guard
        logger.warning("render: Pillow unavailable — falling back to the "
                       "two-image label/value form, which mis-aligns rows")
        return None

    try:
        li = Image.open(io.BytesIO(base64.b64decode(left.b64)))
        ri = Image.open(io.BytesIO(base64.b64decode(right.b64)))
        # A visible rule between the strips. Without it the label column and the
        # value column read as one wide cell and the model re-introduces the very
        # ambiguity this is meant to remove.
        gap = 6
        height = max(li.height, ri.height)
        canvas = Image.new("RGB", (li.width + gap + ri.width, height), "white")
        canvas.paste(li, (0, 0))
        for dx in range(gap // 2 - 1, gap // 2 + 1):
            for y in range(height):
                canvas.putpixel((li.width + dx, y), (0, 0, 0))
        canvas.paste(ri, (li.width + gap, 0))

        buf = io.BytesIO()
        canvas.save(buf, format="PNG", optimize=True)
        png = buf.getvalue()
    except Exception as exc:
        logger.warning("render: composite for page %d comp %d failed: %s",
                       page_no, comp_index, exc)
        return None

    return RenderedPage(
        page=page_no, b64=base64.b64encode(png).decode("ascii"),
        media_type="image/png", width=canvas.width, height=canvas.height,
        dpi=dpi,
        # The VALUE column's clip, not the composite's footprint: `clip` exists so
        # a field's box can be mapped back to the full page for the reviewer's
        # click-to-scroll, and every extracted value comes from the right-hand
        # strip. The label strip is context, not a source of values.
        clip=column_clip,
    )
