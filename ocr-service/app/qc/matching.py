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

# Generational suffixes are special: omitting one across documents is routine
# appraiser practice, not a different party — token matching treats a
# suffix-only difference as "review", never "mismatch".
_NAME_SUFFIXES = {"jr", "sr", "ii", "iii", "iv"}

# Corporate designators that vary freely across documents ("Champions Funding"
# vs "Champions Funding, LLC") — stripped before comparing lender/client names.
_COMPANY_NOISE = {"inc", "llc", "corp", "corporation", "co", "company", "na",
                  "lp", "llp", "ltd", "pllc", "pc", "fsb", "isaoa", "atima"}


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


STATE_CODES = {
    "alabama": "AL", "alaska": "AK", "arizona": "AZ", "arkansas": "AR",
    "california": "CA", "colorado": "CO", "connecticut": "CT", "delaware": "DE",
    "florida": "FL", "georgia": "GA", "hawaii": "HI", "idaho": "ID",
    "illinois": "IL", "indiana": "IN", "iowa": "IA", "kansas": "KS",
    "kentucky": "KY", "louisiana": "LA", "maine": "ME", "maryland": "MD",
    "massachusetts": "MA", "michigan": "MI", "minnesota": "MN", "mississippi": "MS",
    "missouri": "MO", "montana": "MT", "nebraska": "NE", "nevada": "NV",
    "new hampshire": "NH", "new jersey": "NJ", "new mexico": "NM", "new york": "NY",
    "north carolina": "NC", "north dakota": "ND", "ohio": "OH", "oklahoma": "OK",
    "oregon": "OR", "pennsylvania": "PA", "rhode island": "RI", "south carolina": "SC",
    "south dakota": "SD", "tennessee": "TN", "texas": "TX", "utah": "UT",
    "vermont": "VT", "virginia": "VA", "washington": "WA", "west virginia": "WV",
    "wisconsin": "WI", "wyoming": "WY", "district of columbia": "DC",
}


def normalize_state(text: str) -> str:
    """Two-letter state code from either a code or a full state name; ''
    when unrecognizable."""
    s = normalize_basic(text)
    if len(s) == 2 and s.upper() in STATE_CODES.values():
        return s.upper()
    return STATE_CODES.get(s, "")


def normalize_company(text: str) -> str:
    """Normalize an organization name: basic clean + drop corporate designators,
    so "Champions Funding, LLC" == "Champions Funding"."""
    tokens = [t for t in normalize_basic(text).split() if t not in _COMPANY_NOISE]
    return " ".join(tokens)


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
    elif kind == "company":
        na, nb = normalize_company(a), normalize_company(b)
    else:
        na, nb = normalize_basic(a), normalize_basic(b)
    if not na or not nb:
        # Missing on one side is not a mismatch the matcher can judge.
        return MatchResult(0.0, "review", na, nb)
    score = jaro_winkler(na, nb)
    return MatchResult(round(score, 4), _verdict(score, match_th, review_th), na, nb)


def name_tokens(text: str) -> list:
    """Individual name tokens from any format ("DEINEKO, ANTON", "A & B Smith"):
    split on commas/ampersands/'and'/semicolons + whitespace, drop titles and
    single-letter initials, keep generational suffixes (handled separately)."""
    s = re.sub(r"[&;]|\band\b", " ", (text or "").lower())
    s = re.sub(r"[^\w\s]", " ", s)
    return [t for t in s.split()
            if (t in _NAME_SUFFIXES) or (t not in _NAME_NOISE and len(t) > 1)]


def match_name_containment(
    required: str, candidate: str,
    match_th: float = MATCH_THRESHOLD, review_th: float = REVIEW_THRESHOLD,
) -> MatchResult:
    """Does `candidate` contain every name token of `required`?

    The engagement letter is the lender-accepted borrower identity: every token
    it carries must appear in the appraisal's borrower field (the reverse is not
    required — the appraisal may list extra parties). Per-token Jaro-Winkler
    absorbs OCR noise; a missing generational suffix alone is "review" (commonly
    omitted by appraisers), any other missing token is "mismatch".
    """
    req, cand = name_tokens(required), name_tokens(candidate)
    if not req or not cand:
        return MatchResult(0.0, "review", " ".join(req), " ".join(cand))
    missing, suffix_only = [], True
    scores = []
    for t in req:
        best = max((jaro_winkler(t, c) for c in cand), default=0.0)
        scores.append(best)
        if best < match_th:
            missing.append(t)
            if t not in _NAME_SUFFIXES:
                suffix_only = False
    score = round(sum(scores) / len(scores), 4)
    if not missing:
        return MatchResult(score, "match", " ".join(req), " ".join(cand))
    if suffix_only:
        return MatchResult(score, "review", " ".join(req), " ".join(cand))
    return MatchResult(score, "mismatch", " ".join(req), " ".join(cand))


_DATE_RE = re.compile(r"(\d{1,2})[/\-.](\d{1,2})[/\-.](\d{2,4})")


def parse_date_tuple(text) -> Optional[tuple]:
    """(year, month, day) from a M/D/Y-style string; None when unparseable."""
    m = _DATE_RE.search(str(text or ""))
    if not m:
        return None
    mm, dd, yy = (int(x) for x in m.groups())
    if yy < 100:
        yy += 2000
    if not (1 <= mm <= 12 and 1 <= dd <= 31 and 1900 <= yy <= 2099):
        return None
    return (yy, mm, dd)


def year_of(text) -> int:
    """First plausible 4-digit year in the text; 0 when none. Shared by the
    tax-year / year-built / effective-date arithmetic rules."""
    m = re.search(r"\b(18|19|20)\d{2}\b", str(text or ""))
    return int(m.group(0)) if m else 0


def match_date(a, b) -> MatchResult:
    """Exact-day date equality. Dates are identifiers, not fuzzy strings —
    Jaro-Winkler would call 04/27/2026 and 04/29/2026 a match. Unparseable on
    either side → review (the matcher cannot judge)."""
    ta, tb = parse_date_tuple(a), parse_date_tuple(b)
    if ta is None or tb is None:
        return MatchResult(0.0, "review", str(a), str(b))
    ok = ta == tb
    return MatchResult(1.0 if ok else 0.0, "match" if ok else "mismatch", str(a), str(b))


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
