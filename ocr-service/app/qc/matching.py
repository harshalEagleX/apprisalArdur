"""
String / value matching for cross-document QC rules.

Cross-document rules (address, borrower, lender, price) must never use raw
string equality — the same fact is written differently across documents
("123 Main St" vs "123 Main Street", "Anton Deineko" vs "DEINEKO, ANTON").
This module normalizes first, then scores similarity with Jaro-Winkler, and
returns a three-band verdict (match / review / mismatch) per the agreed
tolerance: >= 0.88 match, 0.75-0.87 review, < 0.75 mismatch.

Pure standard library — no third-party fuzzy dependency.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

# Tolerance bands (overridable via qc_thresholds.yaml at the call site).
MATCH_THRESHOLD = 0.88
REVIEW_THRESHOLD = 0.75

_STREET_ABBR = {
    "st": "street", "str": "street", "ave": "avenue", "av": "avenue",
    "blvd": "boulevard", "rd": "road", "dr": "drive", "ln": "lane",
    "ct": "court", "cir": "circle", "pl": "place", "pkwy": "parkway",
    "hwy": "highway", "ter": "terrace", "trl": "trail", "sq": "square",
    "n": "north", "s": "south", "e": "east", "w": "west",
    "ne": "northeast", "nw": "northwest", "se": "southeast", "sw": "southwest",
    "apt": "apartment", "ste": "suite", "unit": "unit", "#": "unit",
}

_NAME_NOISE = {"jr", "sr", "ii", "iii", "iv", "mr", "mrs", "ms", "dr"}


def _collapse_ws(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def normalize_basic(text: str) -> str:
    """Lowercase, strip punctuation to spaces, collapse whitespace."""
    text = (text or "").lower()
    text = re.sub(r"[^\w\s]", " ", text)
    return _collapse_ws(text)


def normalize_address(text: str) -> str:
    """Normalize an address: basic clean + expand street/direction abbreviations."""
    tokens = normalize_basic(text).split()
    out = [_STREET_ABBR.get(t, t) for t in tokens]
    return " ".join(out)


def normalize_name(text: str) -> str:
    """Normalize a person name: drop suffixes/titles and single-letter MIDDLE
    INITIALS, then sort tokens (order-insensitive). Dropping initials makes
    "Riley C Freese" == "Riley Freese" — the same party is routinely recorded
    with/without a middle initial across documents (two different people sharing
    a first+last name within one transaction is not a realistic case here)."""
    tokens = [t for t in normalize_basic(text).split()
              if t not in _NAME_NOISE and len(t) > 1]
    return " ".join(sorted(tokens))


def normalize_currency(text) -> Optional[float]:
    """Parse a currency/number string to float; None if not parseable."""
    if text is None:
        return None
    s = re.sub(r"[^\d.\-]", "", str(text))
    if s in ("", "-", "."):
        return None
    try:
        return float(s)
    except ValueError:
        return None


def jaro(s1: str, s2: str) -> float:
    """Jaro similarity in [0,1]."""
    if s1 == s2:
        return 1.0
    if not s1 or not s2:
        return 0.0
    match_dist = max(len(s1), len(s2)) // 2 - 1
    match_dist = max(match_dist, 0)
    s1_matches = [False] * len(s1)
    s2_matches = [False] * len(s2)
    matches = 0
    for i, c in enumerate(s1):
        lo = max(0, i - match_dist)
        hi = min(i + match_dist + 1, len(s2))
        for j in range(lo, hi):
            if not s2_matches[j] and s2[j] == c:
                s1_matches[i] = s2_matches[j] = True
                matches += 1
                break
    if matches == 0:
        return 0.0
    # transpositions
    t = 0
    k = 0
    for i in range(len(s1)):
        if s1_matches[i]:
            while not s2_matches[k]:
                k += 1
            if s1[i] != s2[k]:
                t += 1
            k += 1
    t //= 2
    m = matches
    return (m / len(s1) + m / len(s2) + (m - t) / m) / 3.0


def jaro_winkler(s1: str, s2: str, p: float = 0.1, max_prefix: int = 4) -> float:
    """Jaro-Winkler similarity in [0,1] (rewards common prefix)."""
    j = jaro(s1, s2)
    prefix = 0
    for c1, c2 in zip(s1, s2):
        if c1 == c2:
            prefix += 1
        else:
            break
        if prefix == max_prefix:
            break
    return j + prefix * p * (1 - j)


@dataclass
class MatchResult:
    score: float
    verdict: str          # "match" | "review" | "mismatch"
    norm_a: str
    norm_b: str


def _verdict(score: float, match_th: float, review_th: float) -> str:
    if score >= match_th:
        return "match"
    if score >= review_th:
        return "review"
    return "mismatch"


def match_text(
    a: str, b: str, kind: str = "generic",
    match_th: float = MATCH_THRESHOLD, review_th: float = REVIEW_THRESHOLD,
) -> MatchResult:
    """
    Compare two text values for cross-document equivalence.
    kind: "address" | "name" | "generic" selects the normalizer.
    """
    if kind == "address":
        na, nb = normalize_address(a), normalize_address(b)
    elif kind == "name":
        na, nb = normalize_name(a), normalize_name(b)
    else:
        na, nb = normalize_basic(a), normalize_basic(b)
    if not na or not nb:
        # Missing on one side is not a mismatch the matcher can judge.
        return MatchResult(0.0, "review", na, nb)
    score = jaro_winkler(na, nb)
    return MatchResult(round(score, 4), _verdict(score, match_th, review_th), na, nb)


def match_currency(a, b, tolerance: float = 0.0) -> MatchResult:
    """Numeric match after stripping $ and commas. Exact unless tolerance given."""
    va, vb = normalize_currency(a), normalize_currency(b)
    if va is None or vb is None:
        return MatchResult(0.0, "review", str(a), str(b))
    if vb == 0:
        ok = va == vb
    else:
        ok = abs(va - vb) <= tolerance
    return MatchResult(1.0 if ok else 0.0, "match" if ok else "mismatch", str(va), str(vb))
