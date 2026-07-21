"""
locate.back_locator (loc-2.0.0) — SHALqc-CORE §3 "solving XML has no coordinates".

A value taken from XML has no page/bbox, so a reviewer clicking the finding
can't be scrolled to it. After merge, every field whose winning witness lacks a
bbox is located ON THE PDF and stamped with a `location_quality`:

  L1 exact  — the field already carries a bbox (a PDF/grid/checkbox witness)   → reuse
  L2 exact  — the value is found on a page AND the match is CORROBORATED       → tight box
  L3 region — value not matched; the field's label anchor is → soft region box
  L4 page   — value not matched but a page is known          → scroll-to-page only
  L5 none   — value not matched and no page                  → XML badge

loc-2.0.0 (2026-07-20): "exact" now means the RIGHT occurrence, not the first
one. The 1.0 first-match-wins scan located 480/546 fields "exact" on a real
order — but 400 of those values occur more than once in the report, and the box
routinely landed on the wrong instance (a date matched by its bare year token, a
street address by its house number, a room count by any equal digit anywhere).
The rules now are:

  * A value that appears ONCE is exact — nothing to disambiguate.
  * A value that appears MORE than once must be corroborated: by its template
    label anchor (config/template_positions.yaml) found near the candidate, or
    by tokens of its own canonical field name printed on/above the candidate's
    row. Corroborated → exact at that instance.
  * Numeric-token matching applies ONLY when the whole value is a number
    ("$250,000.00" ↔ 250000) — never to a number merely inside a date/address.
  * A short number (1-2 digits) is too ambiguous to trust without
    corroboration; an uncorroborated multi-match degrades honestly
    (all-on-one-page → L4 page; else L3 region → L4 → L5) instead of guessing.
  * ISO dates ("2026-07-18") also try their printed renderings (07/18/2026,
    7/18/2026, July 18, 2026) before giving up.

Matching stays punctuation/whitespace-insensitive. No fabricated boxes, honest
downgrades — a box the reviewer lands on is either the only instance of the
value or an instance sitting next to its own label.
"""

from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional, Tuple

from app.extraction.result import ExtractedField, ExtractedFieldSet

__version__ = "loc-2.1.0"

logger = logging.getLogger(__name__)

_NON_ALNUM = re.compile(r"[^a-z0-9]+")
_ROW_TOL = 4.0
_MAX_CANDIDATES = 8       # stop collecting once a value is clearly multi-instance
_MAX_PAGES_DEFAULT = 60   # appraisal packages run 40+ pages; word-scan is cheap
_ISO_DATE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})$")
_FULL_NUMERIC = re.compile(r"^-?\$?\s?\d[\d,]*(\.\d+)?%?$")
_MONTHS = ("january", "february", "march", "april", "may", "june", "july",
           "august", "september", "october", "november", "december")


def _norm(text: str) -> str:
    return _NON_ALNUM.sub("", (text or "").lower())


def _numeric(text: str) -> Optional[float]:
    m = re.search(r"-?\d[\d,]*\.?\d*", text or "")
    if not m:
        return None
    try:
        return float(m.group(0).replace(",", ""))
    except ValueError:
        return None


def _box(span: List[dict], pw: float, ph: float) -> Dict[str, float]:
    x0 = min(w["x0"] for w in span); y0 = min(w["y0"] for w in span)
    x1 = max(w["x1"] for w in span); y1 = max(w["y1"] for w in span)
    return {"x": round(x0 / pw, 5), "y": round(y0 / ph, 5),
            "w": round((x1 - x0) / pw, 5), "h": round((y1 - y0) / ph, 5)}


# ── per-page index, built once and reused for every field ─────────────────────

class _Row:
    __slots__ = ("words", "concat", "text")

    def __init__(self, words: List[dict]):
        self.words = words
        self.concat = "".join(w["norm"] for w in words)
        self.text = " ".join(w["text"] for w in words)


class _PageIndex:
    __slots__ = ("no", "pw", "ph", "rows")

    def __init__(self, page):
        self.no = page.number + 1
        self.pw = float(page.rect.width)
        self.ph = float(page.rect.height)
        rows: Dict[int, List[dict]] = {}
        for w in page.get_text("words"):
            text = w[4].strip()
            if not text:
                continue
            word = {"x0": w[0], "y0": w[1], "x1": w[2], "y1": w[3],
                    "text": text, "norm": _norm(text), "num": _numeric(text)}
            rows.setdefault(round(w[1] / _ROW_TOL), []).append(word)
        ordered = sorted(rows.items())
        for _k, row in ordered:
            row.sort(key=lambda w: w["x0"])
        self.rows = [_Row(row) for _k, row in ordered]


class _Candidate:
    __slots__ = ("page", "bbox", "row_i", "y", "x", "index")

    def __init__(self, index: _PageIndex, row_i: int, span: List[dict]):
        self.index = index
        self.page = index.no
        self.bbox = _box(span, index.pw, index.ph)
        self.row_i = row_i
        self.y = min(w["y0"] for w in span)
        self.x = min(w["x0"] for w in span)


# ── matching ──────────────────────────────────────────────────────────────────

def _string_targets(value: str) -> List[str]:
    """Normalized render variants of the value worth searching for. An ISO date
    is stored normalized but printed as 07/18/2026 / July 18, 2026 on the form."""
    targets = []
    base = _norm(value)
    if base:
        targets.append(base)
    m = _ISO_DATE.match(value.strip())
    if m:
        y, mo, d = m.group(1), int(m.group(2)), int(m.group(3))
        targets.append(f"{mo:02d}{d:02d}{y}")            # 07/18/2026
        targets.append(f"{mo}{d}{y}")                    # 7/18/2026
        if 1 <= mo <= 12:
            name = _MONTHS[mo - 1]
            targets.append(f"{name}{d}{y}")              # July 18, 2026
            targets.append(f"{name[:3]}{d}{y}")          # Jul 18, 2026
    # de-dup, keep order
    seen: set = set()
    return [t for t in targets if t and not (t in seen or seen.add(t))]


def _numeric_target(value: str) -> Optional[float]:
    """A numeric-equality target ONLY when the WHOLE value is a number — a date
    or an address also contains digits but must never match by them."""
    if _FULL_NUMERIC.match(value.strip()):
        return _numeric(value)
    return None


def _row_matches(row: _Row, target: str, target_num: Optional[float]) -> List[List[dict]]:
    """All spans in one row matching the target (string run or numeric token)."""
    out: List[List[dict]] = []
    if target_num is not None:
        for w in row.words:
            wn = w["num"]
            if wn is not None and (wn == target_num or
                                   (target_num and abs(wn - target_num) / abs(target_num) < 1e-6)):
                out.append([w])
    if target and target in row.concat:
        n = len(row.words)
        for i in range(n):
            acc = ""
            for j in range(i, n):
                acc += row.words[j]["norm"]
                if len(acc) > len(target):
                    break
                if acc == target:
                    out.append(row.words[i:j + 1])
                    break
    return out


def _span_covering(row: "_Row", start: int, length: int) -> Optional[List[dict]]:
    """The words of `row` that cover the normalized-char range [start, start+length).
    `row.concat` is the words' norms joined, so walk the same order counting lengths."""
    end = start + length
    pos = 0
    lo = hi = None
    for i, w in enumerate(row.words):
        wl = len(w["norm"])
        if lo is None and pos + wl > start:
            lo = i
        if pos < end <= pos + wl:
            hi = i
            break
        pos += wl
    if lo is None:
        return None
    if hi is None:
        hi = len(row.words) - 1
    return row.words[lo:hi + 1]


def _prose_box(pages: List[_PageIndex], value: str) -> Optional[_Candidate]:
    """Locate the START of a long, multi-row narrative (condition/site/addendum
    comment, reconciliation) by its first distinctive phrase. Verbatim whole-value
    matching can't place these — they wrap across rows — so they were landing at
    `none` (no jump target at all). Matching the first ~30-48 normalized chars on a
    single row finds where the prose begins, which is exactly what a reviewer wants
    to click to. The longest prefix that hits is tried first (most distinctive), so
    a shared opener ("The subject property…") does not collide."""
    nv = _norm(value)
    if len(nv) < 30:
        return None
    for plen in (48, 40, 32):
        if len(nv) < plen:
            continue
        pre = nv[:plen]
        for index in pages:
            for row_i, row in enumerate(index.rows):
                pos = row.concat.find(pre)
                if pos >= 0:
                    span = _span_covering(row, pos, len(pre))
                    if span:
                        return _Candidate(index, row_i, span)
    return None


def _collect_candidates(pages: List[_PageIndex], targets: List[str],
                        target_num: Optional[float]) -> List[_Candidate]:
    cands: List[_Candidate] = []
    for index in pages:
        for row_i, row in enumerate(index.rows):
            spans: List[List[dict]] = []
            for t in targets:
                spans.extend(_row_matches(row, t, None))
            if target_num is not None:
                spans.extend(_row_matches(row, "", target_num))
            # de-dup spans that start at the same word (string + numeric overlap)
            seen_start = set()
            for span in spans:
                key = id(span[0])
                if key in seen_start:
                    continue
                seen_start.add(key)
                cands.append(_Candidate(index, row_i, span))
                if len(cands) >= _MAX_CANDIDATES:
                    return cands
    return cands


# ── corroboration ─────────────────────────────────────────────────────────────

_SCHEMA_TOKENS: Optional[Dict[str, List[str]]] = None


def _schema_note_tokens() -> Dict[str, List[str]]:
    """canonical_name → distinctive words from the schema's own field note (e.g.
    gla → ["gross", "living", "area"]). The note describes the field in the
    words the FORM prints, so it corroborates a candidate the raw field name
    cannot. Built once; empty map when the schema is unavailable."""
    global _SCHEMA_TOKENS
    if _SCHEMA_TOKENS is None:
        out: Dict[str, List[str]] = {}
        try:
            from app.extraction.schema import schema_loader
            for fd in schema_loader.all_fields():
                note = (getattr(fd, "notes", "") or "").lower()
                toks = [t for t in _NON_ALNUM.split(note) if len(t) >= 4][:6]
                if toks:
                    out[fd.canonical_name] = toks
        except Exception:
            pass
        _SCHEMA_TOKENS = out
    return _SCHEMA_TOKENS


def _label_tokens(canonical_name: str) -> List[str]:
    """Distinctive tokens of the field's own name plus its schema note — used to
    check whether a candidate sits next to text that looks like this field's
    printed label."""
    toks = [t for t in (canonical_name or "").lower().split("_")
            if len(t) >= 3 and not t.isdigit() and t != "comp"]
    for t in _schema_note_tokens().get(canonical_name, []):
        if t not in toks:
            toks.append(t)
    return toks


def _label_score(cand: _Candidate, tokens: List[str]) -> int:
    """How many field-name tokens appear on the candidate's row or the row just
    above it (URAR labels sit left of / above their value)."""
    if not tokens:
        return 0
    ctx = cand.index.rows[cand.row_i].concat
    if cand.row_i > 0:
        ctx += cand.index.rows[cand.row_i - 1].concat
    return sum(1 for t in tokens if t in ctx)


def _anchor_rects(doc, anchor_text: str, max_pages: int) -> List[Tuple[int, Any]]:
    """(page_no, rect) of every occurrence of the template label anchor."""
    out: List[Tuple[int, Any]] = []
    for pno in range(1, min(max_pages, len(doc)) + 1):
        for r in doc[pno - 1].search_for(anchor_text):
            out.append((pno, r))
    return out


def _near_anchor(cand: _Candidate, anchors: List[Tuple[int, Any]]) -> bool:
    """True when the candidate sits close to its label anchor: same page,
    vertically within ~5% of the page (same field line or the line below)."""
    for pno, rect in anchors:
        if pno != cand.page:
            continue
        if abs(cand.y - float(rect.y0)) <= 0.05 * cand.index.ph:
            return True
    return False


def _anchor_region(doc, page_no: int, anchor_text: str, max_pages: int) -> Optional[Tuple[int, Dict[str, float]]]:
    """Find a label anchor on its mapped page; return (page, soft region box)
    just to the RIGHT of the label (where the URAR value sits). CORE §3 L3."""
    pages_to_try = [page_no] if 1 <= page_no <= len(doc) else range(1, min(max_pages, len(doc)) + 1)
    for pno in pages_to_try:
        page = doc[pno - 1]
        rects = page.search_for(anchor_text)
        if not rects:
            continue
        r = rects[0]
        pw, ph = float(page.rect.width), float(page.rect.height)
        x0 = r.x1 + 2
        y0 = r.y0
        x1 = min(r.x1 + 0.40 * pw, pw)
        y1 = r.y1
        return pno, {"x": round(x0 / pw, 5), "y": round(y0 / ph, 5),
                     "w": round(max(x1 - x0, 10) / pw, 5), "h": round((y1 - y0) / ph, 5)}
    return None


# ── resolution ladder ─────────────────────────────────────────────────────────

def _resolve(cands: List[_Candidate], ef: ExtractedField, doc, anchor: Optional[Dict[str, Any]],
             max_pages: int, anchor_cache: Dict[str, List[Tuple[int, Any]]]) -> Optional[_Candidate]:
    """Pick the ONE candidate the reviewer should land on, or None when no
    honest choice exists (caller degrades to L3/L4/L5)."""
    if not cands:
        return None
    if len(cands) == 1:
        return cands[0]

    # template label anchor beats everything — the value next to its own label.
    if anchor and anchor.get("anchor"):
        text = str(anchor["anchor"])
        if text not in anchor_cache:
            anchor_cache[text] = _anchor_rects(doc, text, max_pages)
        near = [c for c in cands if _near_anchor(c, anchor_cache[text])]
        if near:
            return near[0]

    # field-name / schema-note tokens printed on/above the candidate's row. Any
    # top-scored candidate sits next to text naming this field — when several
    # instances qualify (a value printed beside its label in two sections), the
    # first in page order is the form's primary statement of it.
    tokens = _label_tokens(ef.canonical_name)
    scored = [(c, _label_score(c, tokens)) for c in cands]
    best = max(s for _c, s in scored)
    if best > 0:
        return next(c for c, s in scored if s == best)

    # a short number with no corroboration is a guess, not a location.
    norm_val = _norm(str(ef.value))
    if norm_val.isdigit() and len(norm_val) <= 2:
        return None

    # a handful of uncorroborated true instances: the first one still IS the
    # value (license # printed in two sections). Many instances = generic text
    # ("Appraisal Report" x104) — no honest single box exists.
    if len(cands) <= 3:
        return cands[0]
    return None


# ── grid/section reconciliation (loc-2.1.0) ───────────────────────────────────
#
# The independent per-field pass above is blind to STRUCTURE. Two failure shapes
# it cannot fix alone, both reported from real orders:
#   * a value that repeats across comps (0sf, None, ArmLth) lands on the wrong
#     comp column — clicking "Comp 3" highlights Comp 2's identical cell;
#   * a common value (land_use_total="100") matches a look-alike on a far page
#     (a "Total" in the rent schedule on p10) instead of its own section (p3).
# The cure is sibling agreement: comp columns and report sections each occupy a
# consistent (page, x) region, learned from the fields that DID place cleanly,
# then used to pull outliers back — or, when the value is not in that region at
# all, to degrade to a scroll-to-the-right-page (never a confident wrong box).

_COMP_IDX_RE = re.compile(r"^comp_(\d+)_")
_COL_TOL = 0.11          # a grid column is ~0.17 wide; same-column x tolerance
_SCHEMA_SECTIONS: Optional[Dict[str, str]] = None


def _comp_index(name: str) -> Optional[int]:
    m = _COMP_IDX_RE.match(name or "")
    return int(m.group(1)) if m else None


def _field_section(name: str) -> Optional[str]:
    """The field's report section (schema `sections`, comp_N-collapsed). Cached.
    Used only to group SIBLINGS for the page-consensus reconciliation."""
    global _SCHEMA_SECTIONS
    if _SCHEMA_SECTIONS is None:
        out: Dict[str, str] = {}
        try:
            from app.extraction.schema import schema_loader
            for fd in schema_loader.all_fields():
                secs = getattr(fd, "sections", None) or []
                if secs:
                    out[fd.canonical_name] = secs[0]
        except Exception:
            pass
        _SCHEMA_SECTIONS = out
    key = _COMP_IDX_RE.sub("comp_N_", name or "")
    return _SCHEMA_SECTIONS.get(key)


def _x_center(bbox: Optional[Dict[str, float]]) -> Optional[float]:
    return (bbox["x"] + bbox["w"] / 2.0) if bbox else None


def _mode(values: List[int]) -> Optional[int]:
    if not values:
        return None
    from collections import Counter
    return Counter(values).most_common(1)[0][0]


def _median(values: List[float]) -> float:
    s = sorted(values)
    n = len(s)
    return s[n // 2] if n % 2 else (s[n // 2 - 1] + s[n // 2]) / 2.0


def _page_matches(index: _PageIndex, targets: List[str],
                  target_num: Optional[float]) -> List[_Candidate]:
    """Every matching span on ONE page (targeted re-scan for reconciliation —
    precise, not subject to the global candidate cap)."""
    out: List[_Candidate] = []
    for row_i, row in enumerate(index.rows):
        spans: List[List[dict]] = []
        for t in targets:
            spans.extend(_row_matches(row, t, None))
        if target_num is not None:
            spans.extend(_row_matches(row, "", target_num))
        seen = set()
        for span in spans:
            if id(span[0]) in seen:
                continue
            seen.add(id(span[0]))
            out.append(_Candidate(index, row_i, span))
    return out


class _Placement:
    __slots__ = ("ef", "section", "comp_idx", "targets", "target_num",
                 "anchor", "page", "bbox", "quality", "n_cands")

    def __init__(self, ef: ExtractedField):
        self.ef = ef
        self.section = _field_section(ef.canonical_name)
        self.comp_idx = _comp_index(ef.canonical_name)
        self.targets: List[str] = []
        self.target_num: Optional[float] = None
        self.anchor: Optional[Dict[str, Any]] = None
        self.page = 0
        self.bbox: Optional[Dict[str, float]] = None
        self.quality = "none"
        self.n_cands = 0          # how many matches the value had (1 = unique = trustworthy anchor)


def _find_comp_headers(index: _PageIndex) -> List[float]:
    """The LEFT edges (x-fraction) of the sales-grid comparable column headers on
    this page, left→right. The URAR grid prints "COMPARABLE SALE # N" across the
    top of the columns; the header row is the row that carries the MOST
    "comparable" tokens (prose mentions it only once per line). Left edges are
    used (not centers) because a column's cell starts at its header's left edge —
    so a right-aligned number and a left-aligned word in the same cell both fall
    inside the same [left_i, left_{i+1}) band. Empty when no grid header found."""
    best_row: Optional[Tuple[int, List[float]]] = None   # (count, left-edges)
    for row in index.rows:
        xs = [w["x0"] / index.pw
              for w in row.words if "comparable" in w["norm"] or w["norm"] == "comp"]
        if len(xs) >= 2 and (best_row is None or len(xs) > best_row[0]):
            best_row = (len(xs), sorted(xs))
    return best_row[1] if best_row else []


def _column_bands(lefts: List[float]) -> List[Tuple[float, float]]:
    """Turn sorted header LEFT edges into [lo, hi) column bands. Boundary between
    column i and i+1 is the next header's left edge (the cell's right edge sits
    just before it), with a small left margin so a value flush-left of its header
    still lands in-column. Works for both left-aligned text and right-aligned
    numbers."""
    if not lefts:
        return []
    m = 0.03
    if len(lefts) == 1:
        return [(lefts[0] - m, lefts[0] + 0.20)]
    gaps = [lefts[i + 1] - lefts[i] for i in range(len(lefts) - 1)]
    w = _median(gaps)
    bands = []
    for i, L in enumerate(lefts):
        lo = L - m
        hi = (lefts[i + 1] - m) if i < len(lefts) - 1 else (L + w)
        bands.append((lo, hi))
    return bands


def _band_for(bands: List[Tuple[float, float]], x: float) -> Optional[Tuple[float, float]]:
    """The band containing x (the comp column an anchor value sits in)."""
    for lo, hi in bands:
        if lo <= x < hi:
            return (lo, hi)
    return None


def _reconcile(placements: List[_Placement], pages: List[_PageIndex]) -> None:
    """Second pass: use comp-column (grid header) and section-page consensus to
    correct outliers in place. Conservative — only moves a field when the
    structural evidence is strong, and prefers an honest page-level scroll over a
    wrong box."""
    page_by_no = {p.no: p for p in pages}
    from collections import Counter, defaultdict

    # ── comp columns, anchored on each comp's most DISTINCTIVE field ──────────
    # A comp's page + column are fixed by its most uniquely-located value (a
    # unique sale price / address locates on exactly one page in one column, so it
    # is immune to the repeated-value collisions we are trying to fix). The grid
    # header row on that page then gives the column BAND (alignment-robust), into
    # which the comp's ambiguous values (0sf, None, ArmLth, N;Res) are placed.
    by_comp: Dict[int, List[_Placement]] = defaultdict(list)
    for pl in placements:
        if pl.comp_idx is not None:
            by_comp[pl.comp_idx].append(pl)

    header_cache: Dict[int, List[Tuple[float, float]]] = {}

    def _bands_for_page(page: int) -> List[Tuple[float, float]]:
        if page not in header_cache:
            idx = page_by_no.get(page)
            header_cache[page] = _column_bands(_find_comp_headers(idx)) if idx else []
        return header_cache[page]

    comp_band: Dict[int, Tuple[int, float, float]] = {}
    for idx, group in by_comp.items():
        anchored = [p for p in group if p.quality == "exact" and p.page and p.bbox
                    and _x_center(p.bbox) is not None]
        if not anchored:
            continue
        # most trustworthy = fewest matches (most unique), then longest value.
        anchor = min(anchored, key=lambda p: (p.n_cands or 99, -len(str(p.ef.value))))
        if (anchor.n_cands or 99) > 3:        # even the best anchor is ambiguous → don't guess this comp
            continue
        ax = _x_center(anchor.bbox)
        band = _band_for(_bands_for_page(anchor.page), ax)
        if band is None:                      # no grid header → a window around the anchor column
            band = (ax - 0.09, ax + 0.12)
        comp_band[idx] = (anchor.page, band[0], band[1])

    for pl in placements:
        if pl.comp_idx is None or pl.comp_idx not in comp_band:
            continue
        page, lo, hi = comp_band[pl.comp_idx]
        cx = _x_center(pl.bbox)
        if pl.quality == "exact" and pl.page == page and cx is not None and lo <= cx < hi:
            continue                          # already in the right column band
        index = page_by_no.get(page)
        if index is None:
            continue
        matches = _page_matches(index, pl.targets, pl.target_num)
        in_band = [c for c in matches if lo <= (_x_center(c.bbox) or -9) < hi]
        if in_band:                           # the value IS in this comp's column
            center = (lo + hi) / 2.0
            best = min(in_band, key=lambda c: abs((_x_center(c.bbox) or 9) - center))
            pl.page, pl.bbox, pl.quality = best.page, best.bbox, "exact"
        else:                                 # value not in the grid here → scroll to the grid page, no box
            pl.page, pl.bbox, pl.quality = page, None, "page"

    # ── section pages: the page most of a (non-comp) section's fields sit on ──
    by_sec: Dict[str, List[_Placement]] = defaultdict(list)
    for pl in placements:
        if pl.comp_idx is None and pl.section:
            by_sec[pl.section].append(pl)

    sec_page: Dict[str, int] = {}
    for sec, group in by_sec.items():
        located = [p.page for p in group if p.quality == "exact" and p.page]
        if len(located) < 3:                  # need a solid consensus to move an outlier
            continue
        m = _mode(located)
        if m is not None and located.count(m) >= max(3, 0.5 * len(located)):
            sec_page[sec] = m

    # Pages that carry ≥1 exact member of each section — used to tell a lone
    # outlier ("100" alone on the rent-schedule page) from a section that
    # legitimately spans pages.
    section_pages: Dict[str, Counter] = defaultdict(Counter)
    for pl in placements:
        if pl.comp_idx is None and pl.section and pl.quality == "exact" and pl.page:
            section_pages[pl.section][pl.page] += 1

    for pl in placements:
        if pl.comp_idx is not None or not pl.section:
            continue
        want = sec_page.get(pl.section)
        if want is None or pl.page == want:
            continue                          # already on the section's page (or no consensus)
        index = page_by_no.get(want)
        if index is None:
            continue
        matches = _page_matches(index, pl.targets, pl.target_num)
        if matches:
            tokens = _label_tokens(pl.ef.canonical_name)
            scored = [(c, _label_score(c, tokens)) for c in matches]
            best_score = max(s for _c, s in scored)
            if best_score > 0:                # the instance printed next to this field's own label
                pl.page, pl.bbox, pl.quality = next(
                    (c.page, c.bbox, "exact") for c, s in scored if s == best_score)
            elif len(matches) == 1:           # the only instance on the section page
                pl.page, pl.bbox, pl.quality = matches[0].page, matches[0].bbox, "exact"
            else:                             # ambiguous on the section page → scroll there, no box
                pl.page, pl.bbox, pl.quality = want, None, "page"
            continue
        # Value not printed on the section page (e.g. a total the form omits).
        # If this field is the ONLY section member on its current page, that box
        # is a look-alike on the wrong page — drop it and scroll to the section
        # page (a wrong-page box wastes the reviewer's time; page-level is honest).
        others_here = section_pages[pl.section][pl.page] - (1 if pl.quality == "exact" else 0)
        if others_here <= 0:
            pl.page, pl.bbox, pl.quality = want, None, "page"


def locate_fields(field_set: ExtractedFieldSet, pdf_path,
                  max_pages: int = _MAX_PAGES_DEFAULT) -> Dict[str, int]:
    """Stamp page/bbox/location_quality on every located-poorly field in place.
    Returns a small histogram {exact, region, page, none} for the run log / the
    CORE §3 golden test."""
    import fitz

    hist = {"exact": 0, "region": 0, "page": 0, "none": 0}

    # L1: fields that already carry a bbox are exact by construction.
    to_locate: List[ExtractedField] = []
    for _name, ef in field_set:
        if not ef.found:
            continue
        if ef.bbox is not None:
            ef.location_quality = "exact"
            hist["exact"] += 1
        else:
            to_locate.append(ef)

    if not to_locate:
        return hist

    try:
        doc = fitz.open(str(pdf_path))
    except Exception as exc:
        logger.warning("back_locator: cannot open %s: %s — leaving fields unlocated", pdf_path, exc)
        for ef in to_locate:
            ef.location_quality = "none" if ef.page == 0 else "page"
            hist["none" if ef.page == 0 else "page"] += 1
        return hist

    try:
        from app.extraction.template_positions import field_anchor
    except Exception:
        field_anchor = lambda *a, **k: None  # noqa: E731

    try:
        n_pages = min(max_pages, len(doc))
        pages = [_PageIndex(doc[i]) for i in range(n_pages)]
        anchor_cache: Dict[str, List[Tuple[int, Any]]] = {}

        # ── Pass 1: place each field independently (into a record, not stamped). ──
        placements: List[_Placement] = []
        for ef in to_locate:
            pl = _Placement(ef)
            value = str(ef.value)
            pl.targets = _string_targets(value)
            pl.target_num = _numeric_target(value)
            # Short non-numeric tokens (<3 chars) are too ambiguous to place —
            # skip to avoid a wrong box (P4 spirit).
            if pl.target_num is None:
                pl.targets = [t for t in pl.targets if len(t) >= 3]
            pl.anchor = field_anchor(ef.canonical_name)

            chosen = None
            cands: List[_Candidate] = []
            if pl.targets or pl.target_num is not None:
                cands = _collect_candidates(pages, pl.targets, pl.target_num)
                pl.n_cands = len(cands)
                chosen = _resolve(cands, ef, doc, pl.anchor, n_pages, anchor_cache)

            # Long narrative that didn't match verbatim (it wraps across rows) →
            # locate its first distinctive phrase so the reviewer can jump to where
            # the comment BEGINS instead of getting no target at all.
            if chosen is None and pl.target_num is None:
                chosen = _prose_box(pages, value)

            if chosen is not None:                 # L2 exact (corroborated)
                pl.page, pl.bbox, pl.quality = chosen.page, chosen.bbox, "exact"
            elif pl.anchor and pl.anchor.get("anchor"):
                a_page = int(pl.anchor.get("page", 1))
                region = _anchor_region(doc, a_page, pl.anchor["anchor"], n_pages)
                if region is not None:             # L3 region box
                    pl.page, pl.bbox, pl.quality = region[0], region[1], "region"
                elif 1 <= a_page <= len(doc):      # L4 mapped page, anchor missing
                    pl.page, pl.quality = a_page, "page"
                else:
                    pl.quality = "none"
            elif not (ef.page and ef.page > 0) and cands and all(c.page == cands[0].page for c in cands):
                # uncorroborated but all matches agree on one page → scroll-to-page.
                pl.page, pl.quality = cands[0].page, "page"
            elif ef.page and ef.page > 0:          # L4 page-only (had a page already)
                pl.page, pl.quality = ef.page, "page"
            else:                                  # L5 none (XML badge)
                pl.quality = "none"
            placements.append(pl)

        # ── Pass 2: comp-column + section-page consensus fixes cross-column /
        #    wrong-page picks (loc-2.1.0). ──
        _reconcile(placements, pages)

        # ── Stamp results + count the histogram once, post-reconciliation. ──
        for pl in placements:
            pl.ef.page = pl.page
            pl.ef.bbox = pl.bbox
            pl.ef.location_quality = pl.quality
            hist[pl.quality] = hist.get(pl.quality, 0) + 1
    finally:
        doc.close()

    logger.info("back_locator: %s", hist)
    return hist
