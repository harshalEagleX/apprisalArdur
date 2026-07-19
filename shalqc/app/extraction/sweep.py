"""
extraction.sweep (sweep-1.0.0) — last-resort DOCUMENT-WIDE capture for narrative
and free-text fields, with coordinates.

Why this exists (2026-07-18). EQ-122 "Reasonable Exposure Time" hedged to REVIEW
on 11 of 15 orders with `reasonable_exposure_time absent`, yet the statement is
present in EVERY report we checked:

    ESMD-0002883  "A reasonable exposure time for the subject is deemed to be
                   0-90 days similar to the marketing time…"
    ESNC-0006153  "Exposure Time: The estimated exposure time is 6-12 weeks."
    ESTX-0007568  "…proved a range of exposure time … to be 0-3 months."

Flagging a reviewer to go find something the report plainly states is the worst
kind of queue noise — it teaches them the tool is unreliable. The cause is that
narrative statements do not live at a fixed place: they land in the USPAP
addendum, a certification page, or loose commentary, so a section-scoped reader
misses them. Prose can be anywhere in the report, so search the whole report.

Design:
  * runs ONLY for schema fields still missing after every other extractor, so it
    can never outrank a structured witness (XML/AcroForm/template/grid);
  * anchors on the field's own schema synonyms — no per-item code, works for any
    field the schema describes, for any AMC;
  * DEFINITION-AWARE: appraisal forms restate the USPAP definition of a term
    right next to the appraiser's actual answer ("Exposure Time (USPAP defines
    Exposure Time as the estimated length of time…)"). Capturing that boilerplate
    as the value would be worse than finding nothing, so definitional spans are
    rejected and the search continues.
  * a field may declare `value_pattern` in field_schema.yaml; when present, the
    captured span MUST contain a match, and the match is preferred as the value.
    That keeps the "what does a real answer look like" knowledge in config, not
    in code.
  * every hit carries page + bbox so the reviewer card can auto-scroll to the
    sentence (SHALqc-CORE §3 back-locator contract).
"""

from __future__ import annotations

import logging
import re
from typing import Dict, Iterable, List, Optional, Set

from app.extraction.result import ExtractedField, ExtractedFieldSet, Source

__version__ = "sweep-1.0.0"

logger = logging.getLogger(__name__)

# Below the structured witnesses (XML .97 / AcroForm .95 / template .90) — this is
# a prose read, so it should lose any structured disagreement.
_CONF = 0.70

# The span captured after an anchor. Long enough for a full sentence, short
# enough that it cannot swallow the next unrelated paragraph.
_SPAN_CHARS = 240

# Below this many characters a page is treated as image-only and sent to OCR
# (mirrors pdf_digital.is_digital_page's intent, without importing its threshold).
_DIGITAL_TEXT_FLOOR = 40
_TESSERACT_CONFIG = "--psm 6 --oem 3"

# Hard ceiling on pages sent to OCR by the sweep. A 300dpi render + Tesseract pass
# is ~1-2s per page, so an uncapped sweep over a 40-page scanned report would add
# minutes to EVERY run — the opposite of what this pipeline needs. Digital pages
# (the overwhelming majority) are free and are never counted against this budget;
# extraction/pdf_scanned applies the same discipline with its own max_pages=8.
_OCR_PAGE_BUDGET = 8

# A form restates the USPAP definition of a term beside the appraiser's answer.
# These markers identify the DEFINITION, never the answer.
_DEFINITION_RX = re.compile(
    r"\b(is\s+defined\s+as|defines?\b|definition\s+of|is\s+the\s+estimated\s+length"
    r"|is\s+the\s+presumed\s+length|means\s+the\s+|shall\s+mean\b"
    r"|retrospective\s+opinion|USPAP\s+defines)", re.I)

# Sentence end, so a captured value stops where the thought does.
_SENTENCE_END_RX = re.compile(r"(?<=[.;])\s+(?=[A-Z(])")


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def _first_sentence(span: str) -> str:
    parts = _SENTENCE_END_RX.split(span, maxsplit=1)
    return _clean(parts[0]) if parts else _clean(span)


def _candidate_spans(page_text: str, synonym: str) -> Iterable[str]:
    """Every span following an occurrence of `synonym` on this page."""
    for m in re.finditer(re.escape(synonym), page_text, re.I):
        yield page_text[m.start(): m.start() + _SPAN_CHARS]


def _usable_value(span: str, value_rx: Optional[re.Pattern]) -> Optional[str]:
    """The answer inside `span`, or None when the span is boilerplate.

    With a `value_pattern` the field tells us what a real answer looks like, so
    the pattern match IS the value — that survives prose the appraiser wrapped it
    in ("…is deemed to be 0-90 days similar to the marketing time…"). Without
    one, fall back to the first sentence, rejecting definitional text."""
    if value_rx is not None:
        m = value_rx.search(span)
        if not m:
            return None
        # a definition can still quote a duration ("estimated length of time");
        # only reject when the DEFINITION marker precedes the match.
        if _DEFINITION_RX.search(span[:m.start()]):
            return None
        return _clean(m.group(0))
    if _DEFINITION_RX.search(span):
        return None
    sentence = _first_sentence(span)
    return sentence or None


class _PageText:
    """Lazy, memoized page text with a bounded OCR budget.

    Two properties that matter for cost. LAZY: a page is only read when a field
    actually needs to be searched on it, so finding the answer on page 1 never
    pays for page 40. BUDGETED: OCR is capped (_OCR_PAGE_BUDGET) because a 300dpi
    render + Tesseract pass costs ~1-2s/page, and an uncapped sweep over a scanned
    report would add minutes to every run. Digital pages are free and never
    counted. OCR failure degrades to the digital text — never raises.
    """

    def __init__(self, pages) -> None:
        self._pages = pages                 # [(page_no, page_obj), …]
        self._cache: Dict[int, str] = {}
        self._ocr_used = 0

    def __iter__(self):
        for page_no, page in self._pages:
            yield page_no, page, self.text(page_no, page)

    def text(self, page_no: int, page) -> str:
        if page_no in self._cache:
            return self._cache[page_no]
        try:
            text = page.get_text() or ""
        except Exception:
            text = ""
        if len(text.strip()) < _DIGITAL_TEXT_FLOOR and self._ocr_used < _OCR_PAGE_BUDGET:
            self._ocr_used += 1
            text = self._ocr(page) or text
        self._cache[page_no] = text
        return text

    @staticmethod
    def _ocr(page) -> str:
        try:
            import pytesseract
            from app.extraction.pdf_scanned import _pixmap_to_pil, _render_grayscale

            pix, _scale = _render_grayscale(page)
            return pytesseract.image_to_string(_pixmap_to_pil(pix),
                                               config=_TESSERACT_CONFIG) or ""
        except Exception as exc:
            logger.debug("sweep: OCR unavailable (%s)", exc)
            return ""


def _search(page, needle: str):
    """Rects for `needle` on this page, tolerating the line breaks PyMuPDF keeps
    in its text layer but drops from search (hyphenation/word-wrap)."""
    if not needle or len(needle) < 3:
        return []
    try:
        rects = page.search_for(needle)
        if rects:
            return rects
        # a wrapped phrase won't match whole — anchor on its longest run of words
        words = needle.split()
        for n in (4, 3, 2):
            if len(words) >= n:
                rects = page.search_for(" ".join(words[:n]))
                if rects:
                    return rects
    except Exception:
        return []
    return []


def _locate(page, synonym: str, value: Optional[str] = None) -> Optional[Dict[str, float]]:
    """Fractional {x,y,w,h} covering the LABEL and the VALUE it introduces.

    2026-07-18 (user directive): highlighting only the anchor word makes the
    reviewer hunt for the answer that was the whole point of the card. The box
    must cover the area the check is actually about — the label AND the value
    found — so clicking the card lands on the statement itself.

    The union is taken only when both fall on the same page and are vertically
    close (within a few lines); a value matched somewhere far down the page is a
    coincidental hit and would produce a box spanning half the document, so the
    label box is kept instead.
    """
    pw, ph = page.rect.width or 1.0, page.rect.height or 1.0
    anchors = _search(page, synonym)
    if not anchors:
        return None
    r = anchors[0]
    x0, y0, x1, y1 = r.x0, r.y0, r.x1, r.y1

    if value:
        for vr in _search(page, value):
            # same statement ⇒ within ~4 lines of the label
            if abs(vr.y0 - r.y0) <= max(4.0 * (r.y1 - r.y0), 48.0):
                x0, y0 = min(x0, vr.x0), min(y0, vr.y0)
                x1, y1 = max(x1, vr.x1), max(y1, vr.y1)
                break
    return {"x": x0 / pw, "y": y0 / ph,
            "w": (x1 - x0) / pw, "h": (y1 - y0) / ph}


def extract_sweep(pdf_path, schema, missing: Optional[Set[str]] = None) -> ExtractedFieldSet:
    """Document-wide anchored capture for the still-missing fields in `missing`.

    Never raises — a failure here must leave the run exactly as it was (§16).
    """
    fs = ExtractedFieldSet()
    if not pdf_path or missing is None or not missing:
        return fs
    try:
        import fitz
    except Exception as exc:                                   # pragma: no cover
        logger.info("sweep: PyMuPDF unavailable (%s) — skipped", exc)
        return fs

    wanted = []
    for name in missing:
        fd = _field_def(schema, name)
        if fd is None:
            continue
        synonyms = [s for s in (_attr(fd, "synonyms") or []) if s and len(str(s)) > 3]
        if not synonyms:
            continue
        # Only free-text fields — a number/date/enum has a structured reader that
        # should own it, and a prose grab would be a worse witness.
        if str(_attr(fd, "data_type") or "string").lower() not in ("string", "text"):
            continue
        # OPT-IN ONLY. A field must declare `value_pattern` — what a real ANSWER
        # looks like — or the sweep will not touch it.
        #
        # 2026-07-18, caught before shipping: without a pattern the fallback was
        # "the first sentence after the synonym", and on a URAR the field LABELS
        # are pre-printed on the blank form, so every synonym matched a label with
        # no value after it. A real run injected 13 fields of pure form furniture
        # at confidence 0.70 — comp_N_proximity = "Proximity to Subject Sale Price
        # $ $ $ $", cooling = "Air Conditioning Individual Other Amenities…" —
        # which the judge would then have treated as extracted values. Guessing is
        # worse than finding nothing: a wrong value produces a confident wrong
        # verdict, while a missing one produces an honest VERIFY.
        raw_pattern = _attr(fd, "value_pattern")
        if not raw_pattern:
            continue
        try:
            value_rx = re.compile(str(raw_pattern), re.I)
        except re.error as exc:
            logger.warning("sweep: bad value_pattern for %s (%s) — skipped", name, exc)
            continue
        # longest synonyms first: the most specific anchor wins
        wanted.append((name, sorted(synonyms, key=len, reverse=True), value_rx))
    if not wanted:
        return fs

    try:
        doc = fitz.open(str(pdf_path))
    except Exception as exc:
        logger.warning("sweep: cannot open %s (%s)", pdf_path, exc)
        return fs

    try:
        pages = _PageText([(i + 1, p) for i, p in enumerate(doc)])
        for name, synonyms, value_rx in wanted:
            hit = _sweep_field(pages, synonyms, value_rx)
            if hit is None:
                continue
            value, page_no, page_obj, synonym = hit
            fs.add(ExtractedField(
                canonical_name=name, value=value, raw_value=value,
                source=Source.PDF_DIGITAL, confidence=_CONF, page=page_no,
                bbox=_locate(page_obj, synonym, value), location_quality="region",
            ))
            logger.info("sweep: %s found on page %d via %r → %r",
                        name, page_no, synonym, value[:60])
    finally:
        doc.close()
    return fs


def _sweep_field(pages, synonyms: List[str], value_rx: Optional[re.Pattern]):
    """First usable (value, page_no, page, synonym) across the whole document."""
    for synonym in synonyms:
        for page_no, page, text in pages:
            if not text:
                continue
            for span in _candidate_spans(text, synonym):
                value = _usable_value(span, value_rx)
                if value:
                    return value, page_no, page, synonym
    return None


# ── schema access (the loader exposes objects OR dicts depending on caller) ───

def _attr(fd, key: str):
    if isinstance(fd, dict):
        return fd.get(key)
    return getattr(fd, key, None)


def _field_def(schema, name: str):
    for getter in ("field", "get", "get_field"):
        fn = getattr(schema, getter, None)
        if callable(fn):
            try:
                fd = fn(name)
                if fd is not None:
                    return fd
            except Exception:
                pass
    try:
        for fd in schema.all_fields():
            if _attr(fd, "canonical_name") == name:
                return fd
    except Exception:
        pass
    return None
