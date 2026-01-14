import re
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import fitz
import numpy as np


@dataclass(frozen=True)
class Word:
    x0: float
    y0: float
    x1: float
    y1: float
    text: str

    @property
    def cx(self) -> float:
        return (self.x0 + self.x1) / 2

    @property
    def cy(self) -> float:
        return (self.y0 + self.y1) / 2


def _page_words(page: fitz.Page) -> List[Word]:
    raw = page.get_text("words")
    words: List[Word] = []
    for w in raw:
        if len(w) < 5:
            continue
        txt = (w[4] or "").strip()
        if not txt:
            continue
        words.append(Word(x0=w[0], y0=w[1], x1=w[2], y1=w[3], text=txt))
    return words


def _find_page_index(doc: fitz.Document, patterns: List[str], max_pages: int = 6) -> Optional[int]:
    page_count = min(len(doc), max_pages)
    compiled = [re.compile(p, re.IGNORECASE) for p in patterns]
    for i in range(page_count):
        t = doc[i].get_text("text")
        if not t:
            continue
        if all(c.search(t) for c in compiled):
            return i
    return None


def _find_best_page_index(
    doc: fitz.Document,
    must_patterns: List[str],
    score_patterns: List[str],
    max_pages: int = 8,
) -> Optional[int]:
    must = [re.compile(p, re.IGNORECASE) for p in must_patterns]
    score = [re.compile(p, re.IGNORECASE) for p in score_patterns]
    page_count = min(len(doc), max_pages)

    best_idx = None
    best_score = -1
    for i in range(page_count):
        t = doc[i].get_text("text") or ""
        if not t:
            continue
        if any(not m.search(t) for m in must):
            continue
        s = 0
        for c in score:
            if c.search(t):
                s += 1
        if s > best_score:
            best_idx = i
            best_score = s

    return best_idx


def _find_word(words: List[Word], needle: str) -> Optional[Word]:
    n = needle.lower()
    for w in words:
        if n == w.text.lower():
            return w
    return None


def _find_words(words: List[Word], needle: str) -> List[Word]:
    n = needle.lower()
    return [w for w in words if w.text.lower() == n]


def _find_anchor_word(words: List[Word], pattern: str) -> Optional[Word]:
    r = re.compile(pattern, re.IGNORECASE)
    for w in words:
        if r.search(w.text):
            return w
    return None


def _x_marks(words: List[Word]) -> List[Word]:
    marks: List[Word] = []
    for w in words:
        t = w.text.strip()
        if t.lower() == "x" or t == "X" or t == "XX" or t == "><":
            marks.append(w)
    return marks


@dataclass
class _RasterPage:
    scale: float
    width: int
    height: int
    gray: np.ndarray


def _rasterize_page(page: fitz.Page, scale: float = 3.0) -> _RasterPage:
    mat = fitz.Matrix(scale, scale)
    pix = page.get_pixmap(matrix=mat, colorspace=fitz.csGRAY, alpha=False)
    arr = np.frombuffer(pix.samples, dtype=np.uint8)
    gray = arr.reshape(pix.height, pix.width)
    return _RasterPage(scale=scale, width=pix.width, height=pix.height, gray=gray)


def _ink_ratio(rp: _RasterPage, rect: fitz.Rect, dark_threshold: int = 200) -> float:
    x0 = max(int(rect.x0 * rp.scale), 0)
    y0 = max(int(rect.y0 * rp.scale), 0)
    x1 = min(int(rect.x1 * rp.scale), rp.width)
    y1 = min(int(rect.y1 * rp.scale), rp.height)
    if x1 <= x0 or y1 <= y0:
        return 0.0
    crop = rp.gray[y0:y1, x0:x1]
    if crop.size == 0:
        return 0.0
    return float((crop < dark_threshold).sum()) / float(crop.size)


def _checkbox_rect_left_of_word(word: Word, gap: float = 8.0, box_w: float = 14.0, min_h: float = 10.0) -> fitz.Rect:
    h = max(word.y1 - word.y0, min_h)
    cy = word.cy
    y0 = cy - h / 2
    y1 = cy + h / 2
    return fitz.Rect(word.x0 - gap - box_w, y0, word.x0 - gap, y1)


def _nearest_word_matching(words: List[Word], pattern: str, y_hint: float, y_window: float = 60.0) -> Optional[Word]:
    r = re.compile(pattern, re.IGNORECASE)
    candidates = [w for w in words if r.fullmatch(w.text) or r.search(w.text)]
    candidates = [w for w in candidates if abs(w.cy - y_hint) <= y_window]
    if not candidates:
        return None
    candidates.sort(key=lambda w: abs(w.cy - y_hint))
    return candidates[0]


def _resolve_choice_by_pixel_ink(
    words: List[Word],
    rp: _RasterPage,
    anchor_pattern: str,
    options: List[Tuple[str, str]],
    y_window: float = 80.0,
    min_delta: float = 0.04,
) -> Optional[str]:
    anchor = _find_anchor_word(words, anchor_pattern)
    if not anchor:
        return None

    scores: List[Tuple[str, float]] = []
    for label, pat in options:
        w = _nearest_word_matching(words, pat, y_hint=anchor.cy, y_window=y_window)
        if not w:
            continue
        rect = _checkbox_rect_left_of_word(w)
        score = _ink_ratio(rp, rect)
        scores.append((label, score))

    if not scores:
        return None

    scores.sort(key=lambda x: x[1], reverse=True)
    best_label, best_score = scores[0]
    baseline = min(s for _, s in scores)
    if (best_score - baseline) < min_delta:
        return None
    return best_label


def _resolve_group_by_pixel_ink(
    words: List[Word],
    rp: _RasterPage,
    options: List[str],
    min_delta: float = 0.04,
) -> Optional[str]:
    """Resolve a mutually exclusive checkbox group by comparing ink left of each option label.

    This avoids relying on an anchor word (which can appear elsewhere on the page).
    """
    scores: List[Tuple[str, float]] = []
    for label in options:
        label_words = [w for w in words if w.text.lower() == label.lower()]
        if not label_words:
            continue
        best = 0.0
        for w in label_words:
            rect = _checkbox_rect_left_of_word(w)
            best = max(best, _ink_ratio(rp, rect))
        scores.append((label, best))

    if len(scores) < 2:
        return None

    scores.sort(key=lambda x: x[1], reverse=True)
    best_label, best_score = scores[0]
    baseline = min(s for _, s in scores)
    if (best_score - baseline) < min_delta:
        return None
    return best_label


def _resolve_yes_no_by_pixel_ink(
    words: List[Word],
    rp: _RasterPage,
    anchor_pattern: str,
    y_window: float = 80.0,
    min_delta: float = 0.03,
) -> Optional[bool]:
    r = re.compile(anchor_pattern, re.IGNORECASE)
    anchors = [w for w in words if r.search(w.text)]
    if not anchors:
        return None

    best_value: Optional[bool] = None
    best_delta = 0.0
    best_best_score = 0.0

    for anchor in anchors:
        scope = [w for w in words if abs(w.cy - anchor.cy) <= y_window]
        yes_candidates = [w for w in _find_words(scope, "Yes") if w.x0 > anchor.x0]
        no_candidates = [w for w in _find_words(scope, "No") if w.x0 > anchor.x0]
        if not yes_candidates or not no_candidates:
            continue

        yes_candidates.sort(key=lambda w: abs(w.cy - anchor.cy))
        no_candidates.sort(key=lambda w: abs(w.cy - anchor.cy))

        yes = yes_candidates[0]
        no = no_candidates[0]

        yes_score = _ink_ratio(rp, _checkbox_rect_left_of_word(yes))
        no_score = _ink_ratio(rp, _checkbox_rect_left_of_word(no))

        best_score = max(yes_score, no_score)
        baseline = min(yes_score, no_score)
        delta = best_score - baseline
        if delta < min_delta:
            continue

        if delta > best_delta or (delta == best_delta and best_score > best_best_score):
            best_delta = delta
            best_best_score = best_score
            best_value = True if yes_score > no_score else False

    return best_value


def _cluster_words_into_lines(words: List[Word], y_tol: float = 2.5) -> List[List[Word]]:
    """Cluster words into lines based on y0 proximity."""
    if not words:
        return []
    sorted_words = sorted(words, key=lambda w: (w.y0, w.x0))
    lines: List[List[Word]] = []
    cur: List[Word] = [sorted_words[0]]
    base_y = sorted_words[0].y0
    for w in sorted_words[1:]:
        if abs(w.y0 - base_y) <= y_tol:
            cur.append(w)
        else:
            cur.sort(key=lambda x: x.x0)
            lines.append(cur)
            cur = [w]
            base_y = w.y0
    cur.sort(key=lambda x: x.x0)
    lines.append(cur)
    return lines


def _resolve_did_analyze_by_pixel_ink(words: List[Word], rp: _RasterPage, min_delta: float = 0.03) -> Optional[bool]:
    """Resolve the 'Did analyze' vs 'Did not analyze' checkbox by pixel ink.

    Returns:
        True if 'Did analyze' is checked.
        False if 'Did not analyze' is checked.
        None if unclear.
    """
    lines = _cluster_words_into_lines(words)
    did_lines: List[Tuple[bool, Word]] = []  # (is_not, did_word)
    for line in lines:
        text = " ".join([w.text for w in line]).lower()
        if "did" not in text or "analy" not in text:
            continue
        is_not = "did not" in text or "not analyze" in text
        did_word = next((w for w in line if w.text.lower() == "did"), None)
        if did_word:
            did_lines.append((is_not, did_word))

    if not did_lines:
        return None

    analyze_score = None
    not_score = None

    for is_not, did_word in did_lines:
        score = _ink_ratio(rp, _checkbox_rect_left_of_word(did_word))
        if is_not:
            not_score = max(not_score or 0.0, score)
        else:
            analyze_score = max(analyze_score or 0.0, score)

    if analyze_score is None or not_score is None:
        return None

    best = max(analyze_score, not_score)
    baseline = min(analyze_score, not_score)
    if (best - baseline) < min_delta:
        return None

    return True if analyze_score > not_score else False


def _nearest_left_mark(label_word: Word, marks: List[Word], y_slack: float = 10.0, min_dx: float = -5.0, max_dx: float = 60.0) -> Optional[Word]:
    best = None
    best_dx = float("inf")
    for m in marks:
        if abs(label_word.cy - m.cy) > y_slack:
            continue
        dx = label_word.x0 - m.x1
        if min_dx <= dx <= max_dx and dx < best_dx:
            best_dx = dx
            best = m
    return best


def _resolve_yes_no(words: List[Word], y_slack: float = 12.0) -> Optional[bool]:
    yes = _find_word(words, "Yes")
    no = _find_word(words, "No")
    if not yes or not no:
        return None

    marks = _x_marks(words)
    if not marks:
        return None

    yes_m = _nearest_left_mark(yes, marks, y_slack=y_slack)
    no_m = _nearest_left_mark(no, marks, y_slack=y_slack)

    if yes_m and not no_m:
        return True
    if no_m and not yes_m:
        return False
    return None


def _resolve_yes_no_near_anchor(
    words: List[Word],
    anchor: Word,
    y_window: float = 45.0,
) -> Optional[bool]:
    """Resolve a Yes/No selection near a specific anchor word.

    We find Yes/No tokens closest (by |dy|) to the anchor and then apply the
    left-mark proximity logic.
    """
    scope = [w for w in words if abs(w.cy - anchor.cy) <= y_window]
    yes_candidates = _find_words(scope, "Yes")
    no_candidates = _find_words(scope, "No")
    marks = _x_marks(scope)
    if not yes_candidates or not no_candidates or not marks:
        return None

    yes_candidates.sort(key=lambda w: abs(w.cy - anchor.cy))
    no_candidates.sort(key=lambda w: abs(w.cy - anchor.cy))

    yes = yes_candidates[0]
    no = no_candidates[0]

    yes_m = _nearest_left_mark(yes, marks, y_slack=14.0)
    no_m = _nearest_left_mark(no, marks, y_slack=14.0)

    if yes_m and not no_m:
        return True
    if no_m and not yes_m:
        return False
    return None


def _extract_right_of_label(words: List[Word], label: str, max_dx: float = 220.0, y_slack: float = 6.0) -> Optional[str]:
    label_words = label.split()
    if not label_words:
        return None

    label_first = _find_word(words, label_words[0])
    if not label_first:
        return None

    candidates: List[Word] = []
    base_y = label_first.cy
    base_x = label_first.x1

    for w in words:
        if abs(w.cy - base_y) > y_slack:
            continue
        if w.x0 <= base_x:
            continue
        if (w.x0 - base_x) > max_dx:
            continue
        candidates.append(w)

    if not candidates:
        return None

    candidates.sort(key=lambda w: w.x0)
    out: List[str] = []
    for w in candidates:
        if w.text in {"Yes", "No"}:
            break
        out.append(w.text)
    val = " ".join(out).strip()
    return val or None


def extract_urar_improvements(pdf_path: str) -> Dict[str, object]:
    data: Dict[str, object] = {}
    doc = fitz.open(pdf_path)

    try:
        idx = _find_best_page_index(
            doc,
            must_patterns=[r"Improvements"],
            score_patterns=[r"General Description", r"Year Built", r"Effective Age", r"Design"],
            max_pages=12,
        )
        if idx is None:
            idx = _find_page_index(doc, [r"Freddie Mac Form 70"], max_pages=12)

        if idx is None:
            return data

        page = doc[idx]
        words = _page_words(page)
        rp = _rasterize_page(page)

        yn = _resolve_yes_no_by_pixel_ink(words, rp, anchor_pattern=r"conform")
        if yn is None:
            conf_anchor = _find_anchor_word(words, r"conform")
            if conf_anchor:
                yn = _resolve_yes_no_near_anchor(words, conf_anchor)
        if yn is not None:
            data["conformsToNeighborhood"] = yn

        adv = _resolve_yes_no_by_pixel_ink(words, rp, anchor_pattern=r"livability|deficien|adverse")
        if adv is None:
            adv_anchor = _find_anchor_word(words, r"livability|deficien|adverse")
            if adv_anchor:
                adv = _resolve_yes_no_near_anchor(words, adv_anchor)
        if adv is not None:
            data["adverseConditionsAffectingLivability"] = adv

        txt = page.get_text("text") or ""
        units_match = re.search(r"\bUnits\b.*?(One|Two|Three|Four|\d{1,2})", txt, re.IGNORECASE)
        if units_match:
            raw = units_match.group(1).strip().lower()
            word_map = {"one": 1, "two": 2, "three": 3, "four": 4}
            data["unitsCount"] = word_map.get(raw, int(raw) if raw.isdigit() else None)

        # Year Built / Effective Age often appear on the next line in the extracted text stream.
        yb_m = re.search(r"(?mi)Year\s+Built\s*(?:\n|\r|\s)+\s*(\d{4})\b", txt)
        if not yb_m:
            yb_m = re.search(r"(?mi)Year\s+Built\s*[:\.]?\s*(\d{4})\b", txt)
        if yb_m:
            data["yearBuilt"] = int(yb_m.group(1))
        else:
            # Layout fallback: pick the nearest 4-digit year to the "Built" header.
            lines2 = _cluster_words_into_lines(words, y_tol=2.8)
            for ln in lines2:
                built_w = next((w for w in ln if w.text.strip().lower() == "built"), None)
                if not built_w:
                    continue
                year_cands = [
                    w
                    for w in ln
                    if re.fullmatch(r"\d{4}", w.text.strip()) and 0 < (w.x0 - built_w.x1) <= 260.0
                ]
                if not year_cands:
                    continue
                year_cands.sort(key=lambda w: (w.x0 - built_w.x1))
                data["yearBuilt"] = int(year_cands[0].text.strip())
                break

        ea_m = re.search(r"(?mi)Effective\s+Age(?:\s*\(Yrs\)|\s*\(Years\))?\s*(?:\n|\r|\s)+\s*(\d{1,3})\b", txt)
        if not ea_m:
            ea_m = re.search(r"(?mi)Effective\s+Age\s*[:\.]?\s*(\d{1,3})\b", txt)
        if ea_m:
            data["effectiveAge"] = int(ea_m.group(1))
        else:
            # Layout fallback: nearest 1-3 digit value to the "Age" header on the Effective Age line.
            lines2 = _cluster_words_into_lines(words, y_tol=2.8)
            for ln in lines2:
                if not any(w.text.strip().lower() == "effective" for w in ln):
                    continue
                age_w = next((w for w in ln if w.text.strip().lower() == "age"), None)
                if not age_w:
                    continue
                age_cands = [
                    w
                    for w in ln
                    if re.fullmatch(r"\d{1,3}", w.text.strip()) and 0 < (w.x0 - age_w.x1) <= 260.0
                ]
                if not age_cands:
                    continue
                age_cands.sort(key=lambda w: (w.x0 - age_w.x1))
                data["effectiveAge"] = int(age_cands[0].text.strip())
                break

        # Foundation selection + evidence flags live in the same block; use pixel ink.
        foundation_anchor = next(
            (
                w
                for w in words
                if w.text.strip().lower() == "foundation" and w.cy < 700.0
            ),
            None,
        )
        if foundation_anchor:
            scores = []
            for label, pat in [
                ("Concrete Slab", r"Concrete"),
                ("Crawl Space", r"Crawl"),
                ("Full Basement", r"Full"),
                ("Partial Basement", r"Partial"),
            ]:
                w = _nearest_word_matching(words, pat, y_hint=foundation_anchor.cy, y_window=55.0)
                if not w:
                    continue
                rect = _checkbox_rect_left_of_word(w)
                score = _ink_ratio(rp, rect)
                scores.append((label, score))
            if scores:
                scores.sort(key=lambda x: x[1], reverse=True)
                best_label, best_score = scores[0]
                baseline = min(s for _, s in scores)
                if (best_score - baseline) >= 0.05:
                    data["foundation"] = best_label

        evidence_anchor = _find_anchor_word(words, r"Evidence")
        if evidence_anchor:
            for key, pat in [
                ("evidenceDampness", r"Dampness|Moisture"),
                ("evidenceSettlement", r"Settlement"),
                ("evidenceInfestation", r"Infestation"),
            ]:
                w = _nearest_word_matching(words, pat, y_hint=evidence_anchor.cy, y_window=70.0)
                if not w:
                    continue
                score = _ink_ratio(rp, _checkbox_rect_left_of_word(w))
                data[key] = bool(score >= 0.075)

        # I-8: Additional features free-text box.
        af_m = re.search(
            r"(?is)Additional\s+features[^\n]{0,140}(?:\n|\r|\s)+([\s\S]{0,800}?)(?=\s*Describe\s+the\s+condition|\s*Are\s+there\s+any\s+physical\s+deficiencies|\Z)",
            txt,
        )
        if af_m:
            val = re.sub(r"\s+", " ", af_m.group(1)).strip()
            low = val.lower()
            if val and not low.startswith("describe the condition") and not low.startswith("are there any physical"):
                if "uniform residential appraisal report" not in low and "form 1004" not in low:
                    if re.search(r"\bno\s+additional\s+features\b", low):
                        data["additionalFeatures"] = "NONE"
                    else:
                        data["additionalFeatures"] = val[:800]
        if "additionalFeatures" not in data:
            # If the form field is present but blank, the extracted text usually shows the next label immediately.
            m = re.search(
                r"(?is)Additional\s+features[^\n]{0,140}(?:\n|\r|\s)+(.*?)(?=\s*Describe\s+the\s+condition|\s*Are\s+there\s+any\s+physical\s+deficiencies|\Z)",
                txt,
            )
            if m:
                between = re.sub(r"\s+", " ", m.group(1)).strip()
                if not between:
                    data["additionalFeatures"] = "NONE"

        cond = None
        for w in words:
            if re.fullmatch(r"C[1-6]", w.text.strip()):
                cond = w.text.strip()
                break
        if cond:
            data["conditionRating"] = cond

        for label, key in [
            ("Design", "designStyle"),
            ("Stories", "stories"),
        ]:
            v = _extract_right_of_label(words, label)
            if v:
                data[key] = v

        rooms = _extract_number_below_label(words, r"^Rooms$") or _extract_number_left_of_label(words, r"^Rooms$")
        if rooms and rooms.replace(",", "").isdigit():
            data["totalRooms"] = int(rooms.replace(",", ""))

        beds = _extract_number_below_label(words, r"^Bedrooms$") or _extract_number_left_of_label(words, r"^Bedrooms$")
        if beds and beds.replace(",", "").isdigit():
            data["bedrooms"] = int(beds.replace(",", ""))

        baths = _extract_number_below_label(words, r"^Bath\(s\)$|^Baths$") or _extract_number_left_of_label(words, r"^Bath\(s\)$|^Baths$")
        if baths and re.fullmatch(r"\d+(?:\.\d+)?", baths.replace(",", "")):
            data["baths"] = float(baths.replace(",", ""))

        gla = _extract_number_below_label(words, r"^Square$") or _extract_number_below_label(words, r"^Feet$")
        if not gla:
            gla = _extract_number_left_of_label(words, r"^Square$")
        if not gla:
            gla = _extract_number_left_of_label(words, r"^Feet$")
        if gla and gla.replace(",", "").isdigit():
            data["gla"] = float(gla.replace(",", ""))

        for label, key in [
            ("Floors", "floors"),
            ("Walls", "walls"),
            ("Trim/Finish", "trimFinish"),
            ("Bath", "bathFloor"),
            ("Car", "carStorage"),
            ("Driveway", "drivewaySurface"),
        ]:
            v = _extract_right_of_label(words, label)
            if v and key not in data:
                data[key] = v

    finally:
        doc.close()

    return data


def _extract_line_after_header(lines: List[str], header: str, invalid_headers: List[str], max_lookahead: int = 6) -> Optional[str]:
    invalid = {h.strip().lower() for h in invalid_headers}
    header_l = header.strip().lower()
    for i, line in enumerate(lines):
        if line.strip().lower() != header_l:
            continue
        for j in range(i + 1, min(i + 1 + max_lookahead, len(lines))):
            v = lines[j].strip()
            if not v:
                continue
            if v.lower() in invalid:
                break
            return v
    return None


def _extract_block_after_header_regex(text: str, header: str, until_headers: List[str], max_chars: int = 1500) -> Optional[str]:
    until = "|".join([re.escape(h) for h in until_headers])
    pattern = rf"(?is){re.escape(header)}\s*\n(.*?)(?=\n(?:{until})\s*$)"
    m = re.search(pattern, text, re.MULTILINE)
    if not m:
        return None
    block = m.group(1)
    block = re.sub(r"\s+", " ", block).strip()
    if not block:
        return None
    return block[:max_chars]


def _is_addenda_reference(text: Optional[str]) -> bool:
    if not text:
        return False
    low = text.lower()
    return bool(re.search(r"see\s+(?:attached\s+)?addend[au]", low) or re.search(r"see\s+attached", low))


def _extract_urar_addendum_section(full_text: str, header_pattern: str, max_chars: int = 3000) -> Optional[str]:
    if not full_text:
        return None
    m = re.search(
        rf"(?is)(?:^|\n)\s*(?:[\-\*\u2022•]\s*)?{header_pattern}\s*\n+([\s\S]+?)(?=\n\s*(?:[\-\*\u2022•]\s*)?URAR:|\n\s*$)",
        full_text,
        re.IGNORECASE | re.MULTILINE,
    )
    if not m:
        return None
    out = re.sub(r"\s+", " ", m.group(1)).strip()
    return out[:max_chars] if out else None


def _extract_market_conditions_from_addendum(full_text: str, max_chars: int = 2200) -> Optional[str]:
    if not full_text:
        return None

    # Many reports include a Market Conditions Addendum (1004MC narrative).
    start_m = re.search(r"(?mi)^\s*MARKET\s+CONDITIONS\s*$", full_text)
    if start_m:
        tail = full_text[start_m.end() : start_m.end() + max_chars * 2]
        stop_m = re.search(r"(?mi)^\s*(?:MARKET\s+RESEARCH\s*&\s*ANALYSIS|INVENTORY\s+ANALYSIS|TREND\s+CHARTS?)\b", tail)
        if stop_m:
            tail = tail[: stop_m.start()]
        out = re.sub(r"\s+", " ", tail).strip()
        return out[:max_chars] if out else None

    # Alternative title where the addendum begins with a fixed heading.
    start_m = re.search(r"(?mi)^\s*Market\s+Conditions\s+Addendum\s+to\s+the\s+Appraisal\s+Report\s*$", full_text)
    if start_m:
        tail = full_text[start_m.end() : start_m.end() + max_chars * 2]
        out = re.sub(r"\s+", " ", tail).strip()
        return out[:max_chars] if out else None

    return None


def _extract_market_conditions_inline(full_text: str, max_chars: int = 600) -> Optional[str]:
    if not full_text:
        return None
    m = re.search(
        r"(?is)(Current\s+single\s+family\s+market\s+trends[^\n]{0,200}(?:\n[^\n]{0,200}){0,2})",
        full_text,
        re.IGNORECASE,
    )
    if not m:
        m = re.search(
            r"(?is)(market\s+trends[^\n]{0,200}(?:\n[^\n]{0,200}){0,2})",
            full_text,
            re.IGNORECASE,
        )
    if not m:
        return None
    out = re.sub(r"\s+", " ", m.group(1)).strip()
    return out[:max_chars] if out else None


def _guess_urar_region(full_text: str, max_chars: int = 9000) -> str:
    if not full_text:
        return ""

    # Prefer a window around key form markers when available (text extraction order can be non-spatial).
    # This is used only to scope regex searches; it should be broad enough to include the whole grid row.
    for marker in [
        r"See\s+(?:Plat|Site)\s+Map",
        r"Neighborhood\s+Boundaries",
        r"\bBound\s+to\s+the\s+north\b",
        r"\bbounded\s+by\b",
        r"\bNORTH\s*[:\-]",
        r"Finished\s+area\s+above\s+grade\s+contains",
        r"\bDimensions\b",
    ]:
        mm = re.search(marker, full_text, re.IGNORECASE)
        if mm:
            start = max(mm.start() - 2500, 0)
            end = min(start + max_chars + 2500, len(full_text))
            return full_text[start:end]

    start_m = re.search(r"Uniform Residential Appraisal Report", full_text, re.IGNORECASE)
    if start_m:
        s = start_m.start()
        return full_text[s : s + max_chars]
    return full_text[:max_chars]


def _extract_neighborhood_boundaries_anywhere(text: str) -> Optional[str]:
    if not text:
        return None

    m = re.search(
        r"(?is)\bNORTH\s*[:\-]\s*[\s\S]{1,200}?\bSOUTH\s*[:\-]\s*[\s\S]{1,200}?\bEAST\s*[:\-]\s*[\s\S]{1,200}?\bWEST\s*[:\-]\s*[\s\S]{1,200}?(?=\n|\r|\.|$)",
        text,
        re.IGNORECASE,
    )
    if m:
        return re.sub(r"\s+", " ", m.group(0)).strip()

    m = re.search(
        r"(?is)\b(?:bounded\s+by|bound\s+to\s+the\s+north)\b[\s\S]{0,300}\bNorth\b[\s\S]{0,300}\bSouth\b[\s\S]{0,300}\bEast\b[\s\S]{0,300}\bWest\b",
        text,
        re.IGNORECASE,
    )
    if m:
        return re.sub(r"\s+", " ", m.group(0)).strip()

    m = re.search(
        r"(?is)\bbound\s+to\s+the\s+north\b[\s\S]{0,300}\bto\s+the\s+east\b[\s\S]{0,300}\bto\s+the\s+south\b[\s\S]{0,300}\bto\s+the\s+west\b[\s\S]{0,300}",
        text,
        re.IGNORECASE,
    )
    if m:
        return re.sub(r"\s+", " ", m.group(0)).strip()

    return None


def _clean_neighborhood_boundaries(text: str) -> str:
    if not text:
        return text
    t = re.sub(r"\s+", " ", text).strip()
    # Strip common follow-on headers/values that can get pulled in by non-spatial text ordering.
    stop_markers = [
        " Neighborhood Description",
        " Market Conditions",
        " Dimensions",
        " Area",
        " Shape",
        " View",
        " Specific Zoning",
        " Zoning",
        " Utilities",
    ]
    for marker in stop_markers:
        idx = t.lower().find(marker.strip().lower())
        if idx != -1:
            t = t[:idx].strip()
    # If we have a clean 'bound to the north ... west ...' sentence, truncate at the period.
    if re.search(r"\bbound\s+to\s+the\s+north\b", t, re.IGNORECASE) and "." in t:
        t = t.split(".", 1)[0].strip() + "."
    return t


def _extract_site_fields_anywhere(text: str) -> Dict[str, object]:
    out: Dict[str, object] = {}
    if not text:
        return out

    dims_match = re.search(
        r"(?is)See\s+(?:Plat|Site)\s+Map\s*(?:\([\s\S]{0,200}?\))?(?:\s+For\s+Area\s+Calculation)?",
        text,
        re.IGNORECASE,
    )
    if not dims_match:
        dims_match = re.search(r"\b\d{1,4}\s*[xX*]\s*\d{1,4}\b", text)
    if dims_match:
        dims = re.sub(r"\s+", " ", dims_match.group(0)).strip()
        if dims.upper().startswith("SEE SITE MAP"):
            dims = re.sub(r"(?i)^See\s+Site\s+Map", "See Plat Map", dims)
        # Guard against garbage partial captures
        if len(dims) >= 6 and dims.lower() not in {"listed)", "listed", ")"}:
            out["siteDimensions"] = dims
        start = max(dims_match.start() - 250, 0)
        end = min(dims_match.end() + 600, len(text))
        window = text[start:end]
    else:
        window = text

    area_match = re.search(r"\b([\d,.]+)\s*(ac|sf|sq\s*ft|sqft)\b", window, re.IGNORECASE)
    if area_match:
        try:
            out["siteArea"] = float(area_match.group(1).replace(",", ""))
            out["siteAreaUnit"] = area_match.group(2).lower().replace("sq ft", "sf").replace("sqft", "sf")
        except ValueError:
            pass

    shape_match = re.search(r"\b(Rectangular|Irregular|Triangular|Square)\b", window, re.IGNORECASE)
    if shape_match:
        out["siteShape"] = shape_match.group(1).title()

    view_match = re.search(r"\b[AN];[A-Za-z]+;(?:[A-Za-z]+;)?\b", window)
    if view_match:
        out["siteView"] = view_match.group(0)

    return out


def _extract_number_left_of_label(words: List[Word], label_pattern: str, max_dx: float = 65.0, y_slack: float = 6.0) -> Optional[str]:
    r = re.compile(label_pattern, re.IGNORECASE)
    labels = [w for w in words if r.search(w.text)]
    if not labels:
        return None

    best_val = None
    best_dx = float("inf")
    for label in labels:
        for w in words:
            if abs(w.cy - label.cy) > y_slack:
                continue
            if w.x1 >= label.x0:
                continue
            dx = label.x0 - w.x1
            if dx > max_dx:
                continue
            if not re.fullmatch(r"[\d,.]+", w.text.strip()):
                continue
            if dx < best_dx:
                best_dx = dx
                best_val = w.text.strip()

    return best_val


def _extract_number_below_label(words: List[Word], label_pattern: str, max_dy: float = 24.0, max_dx: float = 55.0) -> Optional[str]:
    r = re.compile(label_pattern, re.IGNORECASE)
    labels = [w for w in words if r.search(w.text)]
    if not labels:
        return None

    best_val = None
    best_score = float("inf")
    for label in labels:
        for w in words:
            if w.cy <= label.cy:
                continue
            dy = w.cy - label.cy
            if dy > max_dy:
                continue
            dx = abs(w.cx - label.cx)
            if dx > max_dx:
                continue
            token = w.text.strip()
            if not re.fullmatch(r"[\d,.]+", token):
                continue
            score = dy * 10.0 + dx
            if score < best_score:
                best_score = score
                best_val = token

    return best_val


def extract_urar_text_fields(full_text: str) -> Dict[str, object]:
    """Extract fields that are present in the URAR text stream but not reliably captured by regex or bbox logic.

    This is intentionally lightweight and relies on label-following-line semantics.
    """
    data: Dict[str, object] = {}
    if not full_text:
        return data

    lines = [ln.rstrip() for ln in full_text.splitlines()]
    invalid_site_headers = [
        "Area",
        "Shape",
        "View",
        "Specific Zoning Classification",
        "Zoning Description",
        "Zoning Compliance",
        "Neighborhood Boundaries",
        "Neighborhood Description",
        "Market Conditions (including support for the above conclusions)",
    ]

    region = _guess_urar_region(full_text)
    data.update(_extract_site_fields_anywhere(region))
    if "siteDimensions" not in data:
        data.update(_extract_site_fields_anywhere(full_text))
    if "siteDimensions" not in data:
        dims = _extract_line_after_header(lines, "Dimensions", invalid_headers=invalid_site_headers)
        if dims and dims.lower() not in {"of", "shape", "view", "area"}:
            data["siteDimensions"] = dims

    if "siteArea" not in data or "siteAreaUnit" not in data:
        area_line = _extract_line_after_header(lines, "Area", invalid_headers=invalid_site_headers)
        if area_line:
            m = re.search(r"([\d,.]+)\s*(ac|sf|sq\s*ft|sqft)", area_line, re.IGNORECASE)
            if m:
                try:
                    num = float(m.group(1).replace(",", ""))
                    unit = m.group(2).lower().replace("sq ft", "sf").replace("sqft", "sf")
                    data["siteArea"] = num
                    data["siteAreaUnit"] = unit
                except ValueError:
                    pass

    if "siteShape" not in data:
        shape = _extract_line_after_header(lines, "Shape", invalid_headers=invalid_site_headers)
        if shape and shape.lower() not in {"view", "area"}:
            data["siteShape"] = shape

    if "siteView" not in data:
        view = _extract_line_after_header(lines, "View", invalid_headers=invalid_site_headers)
        if view and view.lower() not in {"design (style)", "design", "style"}:
            data["siteView"] = view

    # Specific Zoning Classification (e.g., AL-5)
    zoning_match = re.search(r"\b[A-Z]{1,4}-\d{1,3}\b", full_text)
    if zoning_match:
        data["zoningClassification"] = zoning_match.group(0)
    else:
        zoning_class = _extract_line_after_header(lines, "Specific Zoning Classification", invalid_headers=invalid_site_headers)
        if zoning_class:
            data["zoningClassification"] = zoning_class

    try:
        start_idx = next(i for i, ln in enumerate(lines) if ln.strip().lower() == "neighborhood boundaries")
        end_headers = {
            "neighborhood description",
            "market conditions (including support for the above conclusions)",
            "dimensions",
        }
        collected = []
        for j in range(start_idx + 1, min(start_idx + 40, len(lines))):
            v = lines[j].strip()
            if not v:
                continue
            if v.lower() in end_headers:
                break
            collected.append(v)
        nb = " ".join(collected).strip()
        if nb:
            data["neighborhoodBoundaries"] = nb
    except StopIteration:
        pass

    if not data.get("neighborhoodBoundaries"):
        nb_any = _extract_neighborhood_boundaries_anywhere(region)
        if nb_any:
            data["neighborhoodBoundaries"] = _clean_neighborhood_boundaries(nb_any)

    if not data.get("neighborhoodBoundaries"):
        nb_any = _extract_neighborhood_boundaries_anywhere(full_text)
        if nb_any:
            data["neighborhoodBoundaries"] = _clean_neighborhood_boundaries(nb_any)

    if data.get("neighborhoodBoundaries"):
        data["neighborhoodBoundaries"] = _clean_neighborhood_boundaries(str(data["neighborhoodBoundaries"]))

    nd = _extract_line_after_header(
        lines,
        "Neighborhood Description",
        invalid_headers=["Market Conditions (including support for the above conclusions)", "Dimensions"],
    )
    if nd:
        data["neighborhoodDescription"] = nd

    if (not data.get("neighborhoodDescription")) or _is_addenda_reference(data.get("neighborhoodDescription")):
        add_nd = _extract_urar_addendum_section(full_text, r"URAR:\s*Neighborhood\s*-\s*Description")
        if add_nd:
            data["neighborhoodDescription"] = add_nd

    mc = _extract_line_after_header(
        lines,
        "Market Conditions (including support for the above conclusions)",
        invalid_headers=["Dimensions"],
    )
    if mc:
        data["marketConditions"] = mc

    if (not data.get("marketConditions")) or _is_addenda_reference(data.get("marketConditions")):
        add_mc = _extract_urar_addendum_section(full_text, r"URAR:\s*Neighborhood\s*-\s*Market\s*Conditions")
        if add_mc:
            data["marketConditions"] = add_mc

    if not data.get("marketConditions"):
        add_mc2 = _extract_market_conditions_from_addendum(full_text)
        if add_mc2:
            data["marketConditions"] = add_mc2

    if not data.get("marketConditions"):
        inline_mc = _extract_market_conditions_inline(full_text)
        if inline_mc:
            data["marketConditions"] = inline_mc

    return data


def extract_urar_site(pdf_path: str) -> Dict[str, object]:
    data: Dict[str, object] = {}
    doc = fitz.open(pdf_path)
    try:
        idx = _find_best_page_index(
            doc,
            must_patterns=[r"Zoning"],
            score_patterns=[r"FEMA", r"Flood", r"Utilities", r"Adverse", r"Highest"],
            max_pages=12,
        )
        if idx is None:
            return data

        page = doc[idx]
        words = _page_words(page)
        rp = _rasterize_page(page)

        view = _extract_right_of_label(words, "View", max_dx=140.0)
        if view and re.match(r"^[AN];[A-Za-z]+;", view):
            data["siteView"] = view
        else:
            # Avoid capturing unrelated tokens (e.g., photo captions like "Archer Map").
            txt = page.get_text("text") or ""
            m = re.search(r"\b[AN];[A-Za-z]+;[A-Za-z]*\b", txt)
            if m:
                data["siteView"] = m.group(0).strip()

        fema = _resolve_yes_no_by_pixel_ink(words, rp, anchor_pattern=r"FEMA\s+Special|FEMA|Flood", y_window=200.0)
        if fema is not None:
            data["femaFloodHazard"] = fema

        # FEMA details can be blank on the form if "No" is selected; only required when Yes.
        # Extract from the page text stream (more stable than bbox parsing for this block).
        txt = page.get_text("text") or ""
        zone_m = re.search(r"(?mi)FEMA\s+Flood\s+Zone\s*\n*\s*([A-Za-z0-9\-]+)", txt)
        if zone_m:
            data["femaFloodZone"] = zone_m.group(1).strip()

        map_m = re.search(r"(?mi)FEMA\s+Map\s*#\s*\n*\s*([A-Za-z0-9\-]+)", txt)
        if map_m:
            data["femaMapNumber"] = map_m.group(1).strip()

        date_m = re.search(r"(?mi)FEMA\s+Map\s+Date\s*\n*\s*([0-9]{1,2}[\/\-][0-9]{1,2}[\/\-][0-9]{2,4}|[A-Za-z]{3,9}\s+\d{1,2},\s+\d{4})", txt)
        if date_m:
            data["femaMapDate"] = date_m.group(1).strip()

        util_typ = _resolve_yes_no_by_pixel_ink(words, rp, anchor_pattern=r"utilities.*typical|typical", y_window=220.0)
        if util_typ is not None:
            data["utilitiesTypical"] = util_typ

        adverse = _resolve_yes_no_by_pixel_ink(words, rp, anchor_pattern=r"Adverse\s+Site\s+Conditions|Adverse|site conditions", y_window=240.0)
        if adverse is not None:
            data["adverseSiteConditions"] = adverse

        hbu = _resolve_yes_no_by_pixel_ink(words, rp, anchor_pattern=r"highest\s+and\s+best\s+use|highest", y_window=240.0)
        if hbu is not None:
            data["highestAndBestUse"] = hbu

    finally:
        doc.close()

    return data


def extract_urar_neighborhood(pdf_path: str) -> Dict[str, object]:
    data: Dict[str, object] = {}
    doc = fitz.open(pdf_path)
    try:
        idx = _find_best_page_index(
            doc,
            must_patterns=[r"Neighborhood"],
            score_patterns=[r"Characteristics", r"Urban", r"Built-Up", r"Growth", r"Trends"],
            max_pages=12,
        )
        if idx is None:
            return data

        page = doc[idx]
        words = _page_words(page)
        rp = _rasterize_page(page)

        loc = _resolve_group_by_pixel_ink(words, rp, ["Urban", "Suburban", "Rural"])
        if loc:
            data["location"] = loc

        built_up = _resolve_choice_by_pixel_ink(
            words,
            rp,
            anchor_pattern=r"Built-?Up",
            options=[
                ("Over 75%", r"Over"),
                ("25-75%", r"25-75%"),
                ("Under 25%", r"Under"),
            ],
        )
        if built_up:
            data["builtUp"] = built_up

        growth = _resolve_group_by_pixel_ink(words, rp, ["Rapid", "Stable", "Slow"])
        if growth:
            data["growthRate"] = growth

        prop_values = _resolve_group_by_pixel_ink(words, rp, ["Increasing", "Stable", "Declining"])
        if prop_values:
            data["propertyValues"] = prop_values

        demand_supply = _resolve_choice_by_pixel_ink(
            words,
            rp,
            anchor_pattern=r"Demand/Supply|Demand",
            options=[("Shortage", r"Shortage"), ("In Balance", r"Balance"), ("Over Supply", r"Supply")],
        )
        if demand_supply:
            data["demandSupply"] = demand_supply

        marketing_time = _resolve_choice_by_pixel_ink(
            words,
            rp,
            anchor_pattern=r"Marketing",
            options=[("Under 3", r"Under"), ("3-6", r"3-6"), ("Over 6", r"Over")],
        )
        if marketing_time:
            data["marketingTime"] = marketing_time

        # N-3 (Price/Age ranges) and N-4 (Present Land Use %) are numeric grid values.
        lines = _cluster_words_into_lines(words, y_tol=2.8)
        line_texts = [" ".join([w.text for w in ln]) for ln in lines]

        def _parse_price_000(raw: str) -> Optional[float]:
            try:
                n = float(raw.replace(",", ""))
            except Exception:
                return None
            # URAR grid uses $ (000) for neighborhood price range.
            if n >= 100000:
                return float(n)
            return float(n * 1000.0)

        for kind, p_key, a_key in [
            ("Low", "priceLow", "ageLow"),
            ("High", "priceHigh", "ageHigh"),
            ("Pred", "predominantPrice", "predominantAge"),
        ]:
            pat = rf"\b(\d{{2,4}}(?:,\d{{3}})?)\s+{kind}\.?(?:\b|\s)\s*(\d{{1,3}})\b"
            for lt in line_texts:
                m = re.search(pat, lt, re.IGNORECASE)
                if not m:
                    continue
                p = _parse_price_000(m.group(1))
                a = int(m.group(2)) if m.group(2).isdigit() else None
                if p is not None:
                    data[p_key] = p
                if a is not None:
                    data[a_key] = a
                break

        land_map = [
            (r"One-Unit", "landUseOneUnit"),
            (r"2-4\s+Unit", "landUse2_4Family"),
            (r"Multi-Family", "landUseMultiFamily"),
            (r"Commercial", "landUseCommercial"),
            (r"Industrial", "landUseIndustrial"),
            (r"Other", "landUseOther"),
        ]
        for lt in line_texts:
            if "%" not in lt:
                continue
            for label_pat, key in land_map:
                m = re.search(rf"\b{label_pat}\b\s+(\d+(?:\.\d+)?)\s*%", lt, re.IGNORECASE)
                if not m:
                    continue
                try:
                    data[key] = float(m.group(1))
                except Exception:
                    pass

    finally:
        doc.close()

    return data


def extract_urar_layout_fields(pdf_path: str, full_text: Optional[str] = None) -> Dict[str, object]:
    out: Dict[str, object] = {}
    if full_text:
        out.update(extract_urar_text_fields(full_text))
    out.update(extract_urar_neighborhood(pdf_path))
    out.update(extract_urar_site(pdf_path))
    out.update(extract_urar_improvements(pdf_path))
    return out
