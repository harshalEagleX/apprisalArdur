"""
Day 11 — Fuzzy Label Matching

Replaces exact label matching with approximate matching to handle OCR errors
and label wording variants not in the synonym list.

Similarity: SequenceMatcher (stdlib, no extra deps) — fast enough for our
field count (132 fields × synonyms per field).

Confidence mapping:
  similarity >= 0.98 → EXACT_LABEL_MATCH (0.95 base)
  similarity >= 0.90 → SYNONYM_MATCH (0.85 base)
  similarity >= 0.85 → FUZZY_LABEL_MATCH (0.72 base)
  below 0.85 → no match

The similarity threshold of 0.85 was chosen conservatively to avoid false
positives (OCR words like "Borrower" and "Borrowers" score 0.94 — correct;
"Borrower" and "Barrel" score 0.67 — rejected).
"""

from __future__ import annotations

import re
from difflib import SequenceMatcher
from typing import List, Optional, Tuple

from app.core.result import ExtractionMethod

_FUZZY_THRESHOLD = 0.85
_SYNONYM_THRESHOLD = 0.90
_EXACT_THRESHOLD = 0.98


def _normalize_label(label: str) -> str:
    """Normalize a label for similarity comparison: lowercase, no punctuation."""
    return re.sub(r"[^a-z0-9 ]", "", label.lower().strip())


def fuzzy_label_score(candidate: str, known_label: str) -> float:
    """Return 0.0-1.0 similarity between candidate and known_label."""
    a = _normalize_label(candidate)
    b = _normalize_label(known_label)
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, a, b).ratio()


def find_best_label_match(
    text: str,
    synonyms: List[str],
    value_pattern: str,
    threshold: float = _FUZZY_THRESHOLD,
) -> Optional[Tuple[str, str, int, str]]:
    """
    Search text for the best fuzzy match to any synonym.
    Returns (raw_value, snippet, char_pos, method) or None.

    Strategy:
    1. Exact match first (fastest, highest confidence)
    2. Fuzzy match on each word-length window in text that looks like a label
    """
    import re

    # Pass 1: exact (already done in tier3, but include here for completeness)
    for idx, syn in enumerate(synonyms):
        escaped = re.escape(syn)
        pattern = rf"(?:{escaped})\s*[:\-/]?\s*({value_pattern})"
        m = re.search(pattern, text, re.IGNORECASE)
        if m:
            raw = m.group(1).strip()
            snippet = text[max(0, m.start() - 20): m.end() + 40].replace("\n", " ")
            method = (
                ExtractionMethod.EXACT_LABEL_MATCH if idx == 0
                else ExtractionMethod.SYNONYM_MATCH
            )
            return raw, snippet, m.start(), method

    # Pass 2: fuzzy — find candidate label tokens in text, score against synonyms
    # Look for potential label regions (text before : or \n that looks like a label)
    label_candidates = re.finditer(
        r"([A-Za-z][A-Za-z\s/\(\)\.#&]{3,40})\s*[:\n]",
        text,
    )
    best_score = 0.0
    best_match = None

    for label_m in label_candidates:
        candidate_label = label_m.group(1).strip()
        for idx, syn in enumerate(synonyms):
            score = fuzzy_label_score(candidate_label, syn)
            if score >= threshold and score > best_score:
                # Found a fuzzy match — now extract the value after the label
                after_label = text[label_m.end():]
                val_m = re.match(rf"\s*({value_pattern})", after_label, re.IGNORECASE)
                if val_m:
                    raw = val_m.group(1).strip()
                    if raw:
                        best_score = score
                        pos = label_m.start()
                        snippet = text[max(0, pos - 10): label_m.end() + 60].replace("\n", " ")
                        method = (
                            ExtractionMethod.EXACT_LABEL_MATCH if score >= _EXACT_THRESHOLD
                            else ExtractionMethod.SYNONYM_MATCH if score >= _SYNONYM_THRESHOLD
                            else ExtractionMethod.FUZZY_LABEL_MATCH
                        )
                        best_match = (raw, snippet, pos, method)

    return best_match


def base_confidence_from_similarity(score: float) -> float:
    """Map fuzzy similarity score to base confidence value."""
    if score >= _EXACT_THRESHOLD:
        return 0.95
    elif score >= _SYNONYM_THRESHOLD:
        return 0.85
    elif score >= _FUZZY_THRESHOLD:
        # Linear interpolation from 0.72 to 0.85
        t = (score - _FUZZY_THRESHOLD) / (_SYNONYM_THRESHOLD - _FUZZY_THRESHOLD)
        return 0.72 + t * (0.85 - 0.72)
    return 0.0
