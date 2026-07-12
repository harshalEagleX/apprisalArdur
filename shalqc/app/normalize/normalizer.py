"""
normalize.normalizer (nrm-1.0.0) — SHALqc.md §4: "Fix false FAILs here, once."

THE single comparison-prep function: `normalize(field_def, raw) -> canonical`,
applied to BOTH sides of every comparison. No rule does its own string cleanup
(P6). Config-driven from `config/normalizer.yaml` (hot-reloadable), so a new
enum synonym or street suffix is a YAML edit, never a code change (P7).

Two public surfaces:
  * normalize(field_def, raw) -> canonical string (or None)
      Data-type-aware canonicalization: dates → ISO, currency/number → bare
      number string, state → 2-letter, zip → 5-digit, boolean/enum → canonical
      token, address → USPS-expanded, name → order-insensitive token string.
  * compare(field_def, a, b, kind=None) -> MatchResult{score, verdict, ...}
      Normalizes both sides, then bands the similarity: match / review /
      mismatch. Names use Jaro-Winkler ≥ auto_pass → match; below → never a
      mismatch that can auto-FAIL, only review (SHALqc.md §4 name rule / P4).

The false-FAIL classes SHALqc.md §4 names ("Mdw Ct"=="Meadow Ct", True==Public,
"4800 sf"==4800, Owner==OwnerOccupied) are all resolved by normalize() before
any rule sees the values — that is the entire point of this module.
"""

from __future__ import annotations

import logging
import re
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

from app.normalize import dates as _dates

__version__ = "nrm-1.0.0"

logger = logging.getLogger(__name__)

_CONFIG_PATH = Path(__file__).parent.parent.parent / "config" / "normalizer.yaml"

# Numeric-ish data types get currency/number canonicalization.
_NUMERIC_TYPES = {"currency", "integer", "numeric", "percent", "year"}
# Field-name heuristics for string fields whose comparison needs a specialized
# normalizer (the schema doesn't carry an explicit "kind", so we infer it —
# a single place to infer, not scattered across rules).
_ADDRESS_HINT = re.compile(r"address|location", re.I)
_NAME_HINT = re.compile(r"borrower|owner|appraiser_name|seller|buyer|supervis", re.I)
_COMPANY_HINT = re.compile(r"lender|company|amc", re.I)
_COUNTY_HINT = re.compile(r"county", re.I)


@dataclass
class MatchResult:
    score: float
    verdict: str          # "match" | "review" | "mismatch"
    norm_a: str
    norm_b: str


class Normalizer:
    """Thread-safe, hot-reloadable normalizer backed by normalizer.yaml."""

    def __init__(self, path: Path = _CONFIG_PATH) -> None:
        self._path = path
        self._lock = threading.RLock()
        self._raw: Dict[str, Any] = {}
        self.reload()

    # ------------------------------------------------------------------
    def reload(self) -> None:
        with self._lock:
            self._raw = yaml.safe_load(self._path.read_text(encoding="utf-8")) or {}
            self._street = {k.lower(): v.lower() for k, v in (self._raw.get("usps_street_suffixes") or {}).items()}
            self._street.update({k.lower(): v.lower() for k, v in (self._raw.get("usps_directionals") or {}).items()})
            self._units = {k.lower(): v.lower() for k, v in (self._raw.get("usps_secondary_units") or {}).items()}
            # enum synonyms: build raw_variant(lower) -> canonical
            self._enum_map: Dict[str, str] = {}
            for canonical, variants in (self._raw.get("enum_synonyms") or {}).items():
                for v in variants:
                    self._enum_map[_basic(str(v))] = canonical
            self._bool_true = {_basic(str(x)) for x in (self._raw.get("boolean_true") or [])}
            self._bool_false = {_basic(str(x)) for x in (self._raw.get("boolean_false") or [])}
            self._number_words = {k.lower(): v for k, v in (self._raw.get("number_words") or {}).items()}
            names = self._raw.get("names") or {}
            self._name_noise = {str(x).lower() for x in names.get("noise_tokens", [])}
            self._name_suffixes = {str(x).lower() for x in names.get("suffix_tokens", [])}
            self._company_noise = {str(x).lower() for x in names.get("company_noise", [])}
            self._county_suffixes = {str(x).lower() for x in names.get("county_suffixes", [])}
            self._jw_auto_pass = float(names.get("jaro_winkler_auto_pass", 0.90))
            bands = self._raw.get("match_bands") or {}
            self._match_th = float(bands.get("match", 0.88))
            self._review_th = float(bands.get("review", 0.75))
            dcfg = self._raw.get("dates") or {}
            _dates.set_pivot(int(dcfg.get("two_digit_year_pivot", 50)))
            logger.info("Normalizer loaded (%s): %d enum synonyms, %d street tokens",
                        self.version, len(self._enum_map), len(self._street))

    @property
    def version(self) -> str:
        return (self._raw.get("meta") or {}).get("version", "unknown")

    @property
    def name_auto_pass(self) -> float:
        return self._jw_auto_pass

    def street_suffixes(self) -> set:
        """USPS street-suffix vocabulary (both abbreviations and full forms),
        from the config table — used to find the street/city boundary in a
        comma-less address blob (engagement.parse_address). One source of
        truth: the same table that normalizes 'Mdw'↔'Meadow'."""
        return set(self._street.keys()) | set(self._street.values())

    # ------------------------------------------------------------------
    # normalize()
    # ------------------------------------------------------------------
    def normalize(self, field_def, raw) -> Optional[str]:
        """Canonicalize `raw` for `field_def`. `field_def` may be a
        FieldDefinition, a plain data_type string, or None (→ generic string)."""
        if raw is None:
            return None
        s = str(raw).strip()
        if not s:
            return None

        data_type, canonical_name = _field_meta(field_def)

        if data_type == "date":
            return _dates.to_iso(s) or _basic(s)
        if data_type in _NUMERIC_TYPES:
            return self._normalize_number(s)
        if data_type in ("state_code",):
            return self._normalize_state(s)
        if data_type == "zip5":
            m = re.search(r"\b(\d{5})\b", s)
            return m.group(1) if m else None
        if data_type == "boolean":
            b = self._normalize_boolean(s)
            return b if b is not None else None
        if data_type in ("uad_condition", "uad_quality"):
            m = re.search(r"[QC][1-6]", s.upper())
            return m.group(0) if m else _basic(s)
        if data_type == "enum":
            return self._normalize_enum(s)

        # string-ish: infer a specialized normalizer from the field name
        kind = self._infer_kind(canonical_name)
        return self._normalize_string(s, kind)

    def _normalize_number(self, s: str) -> Optional[str]:
        # unit-bearing area ("12,197 sf", "0.25 ac") → bare number; acres kept as-is
        cleaned = re.sub(r"[,$%]", "", s)
        m = re.search(r"-?\d+(?:\.\d+)?", cleaned)
        if not m:
            # maybe a number word ("One")
            w = self._number_words.get(s.lower())
            return str(w) if w is not None else None
        num = m.group(0)
        # normalize 055 -> 55, 4800.0 -> 4800
        try:
            f = float(num)
            return str(int(f)) if f == int(f) else str(f)
        except ValueError:
            return num

    def _normalize_state(self, s: str) -> Optional[str]:
        from app.normalize._states import STATE_CODES
        b = _basic(s)
        if len(b) == 2 and b.upper() in STATE_CODES.values():
            return b.upper()
        return STATE_CODES.get(b)

    def _normalize_boolean(self, s: str) -> Optional[str]:
        b = _basic(s)
        if b in self._bool_true:
            return "True"
        if b in self._bool_false:
            return "False"
        return None

    def _normalize_enum(self, s: str) -> str:
        b = _basic(s)
        return self._enum_map.get(b, b)

    def _infer_kind(self, canonical_name: str) -> str:
        n = canonical_name or ""
        if _COUNTY_HINT.search(n):
            return "county"
        if _ADDRESS_HINT.search(n):
            return "address"
        if _COMPANY_HINT.search(n):
            return "company"
        if _NAME_HINT.search(n):
            return "name"
        return "generic"

    def _normalize_string(self, s: str, kind: str) -> str:
        # enum synonym wins first (Owner<->OwnerOccupied etc.) even for plain strings
        b = _basic(s)
        if b in self._enum_map:
            return self._enum_map[b]
        if kind == "address":
            return self._normalize_address(s)
        if kind == "name":
            return self._normalize_name(s)
        if kind == "company":
            return self._normalize_company(s)
        if kind == "county":
            return self._normalize_county(s)
        return b

    def _normalize_address(self, s: str) -> str:
        tokens = _basic(s).split()
        out = [self._street.get(t, self._units.get(t, t)) for t in tokens]
        return " ".join(out)

    def _normalize_name(self, s: str) -> str:
        tokens = [t for t in _basic(s).split() if t not in self._name_noise and len(t) > 1]
        return " ".join(sorted(tokens))

    def _normalize_company(self, s: str) -> str:
        tokens = [t for t in _basic(s).split() if t not in self._company_noise]
        return " ".join(tokens)

    def _normalize_county(self, s: str) -> str:
        b = _basic(s)
        for suffix in sorted(self._county_suffixes, key=len, reverse=True):
            if b.endswith(" " + suffix):
                return b[: -(len(suffix) + 1)].strip()
        return b

    # ------------------------------------------------------------------
    # compare()
    # ------------------------------------------------------------------
    def compare(self, field_def, a, b, kind: Optional[str] = None) -> MatchResult:
        """Normalize both sides for `field_def`, then band the similarity.

        `kind` overrides the inferred normalizer for special cases
        ("name_containment", "date", "currency"); otherwise the field's own
        data-type/name-inferred normalization is used on both sides.
        """
        data_type, canonical_name = _field_meta(field_def)

        if kind == "date" or data_type == "date":
            return self._compare_date(a, b)
        if kind == "currency" or data_type in _NUMERIC_TYPES:
            return self._compare_number(a, b)
        if kind == "name_containment":
            return self._match_name_containment(a, b)

        na, nb = self.normalize(field_def, a), self.normalize(field_def, b)
        na, nb = na or "", nb or ""
        if not na or not nb:
            return MatchResult(0.0, "review", na, nb)
        if na == nb:
            return MatchResult(1.0, "match", na, nb)

        # company names: any residual token difference is review, never a fuzzy match
        if (kind == "company") or (kind is None and self._infer_kind(canonical_name) == "company"):
            return MatchResult(round(jaro_winkler(na, nb), 4), "review", na, nb)

        score = jaro_winkler(na, nb)
        return MatchResult(round(score, 4), self._band(score), na, nb)

    def _band(self, score: float) -> str:
        if score >= self._match_th:
            return "match"
        if score >= self._review_th:
            return "review"
        return "mismatch"

    def _compare_date(self, a, b) -> MatchResult:
        ia, ib = _dates.to_iso(a), _dates.to_iso(b)
        if ia is None or ib is None:
            return MatchResult(0.0, "review", str(a), str(b))
        ok = ia == ib
        return MatchResult(1.0 if ok else 0.0, "match" if ok else "mismatch", ia, ib)

    def _compare_number(self, a, b) -> MatchResult:
        na, nb = self._normalize_number(str(a) if a is not None else ""), \
                 self._normalize_number(str(b) if b is not None else "")
        if na is None or nb is None:
            return MatchResult(0.0, "review", str(na), str(nb))
        ok = float(na) == float(nb)
        return MatchResult(1.0 if ok else 0.0, "match" if ok else "mismatch", na, nb)

    def _match_name_containment(self, required, candidate) -> MatchResult:
        """Every name token of `required` must appear in `candidate`
        (Jaro-Winkler per token). A missing generational suffix alone is
        "review"; any other missing token is "mismatch" (SHALqc.md §4 names)."""
        req, cand = self._name_tokens(required), self._name_tokens(candidate)
        if not req or not cand:
            return MatchResult(0.0, "review", " ".join(req), " ".join(cand))
        missing, suffix_only, scores = [], True, []
        for t in req:
            best = max((jaro_winkler(t, c) for c in cand), default=0.0)
            scores.append(best)
            if best < self._match_th:
                missing.append(t)
                if t not in self._name_suffixes:
                    suffix_only = False
        score = round(sum(scores) / len(scores), 4)
        if not missing:
            return MatchResult(score, "match", " ".join(req), " ".join(cand))
        return MatchResult(score, "review" if suffix_only else "mismatch",
                           " ".join(req), " ".join(cand))

    def _name_tokens(self, text) -> List[str]:
        s = re.sub(r"[&;]|\band\b", " ", str(text or "").lower())
        s = re.sub(r"[^\w\s]", " ", s)
        return [t for t in s.split()
                if (t in self._name_suffixes) or (t not in self._name_noise and len(t) > 1)]


# ── module-level helpers (pure) ─────────────────────────────────────────────

def _basic(text: str) -> str:
    """Lowercase, punctuation→space, collapse whitespace."""
    text = (text or "").lower()
    text = re.sub(r"[^\w\s]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _field_meta(field_def):
    """Return (data_type, canonical_name) from a FieldDefinition, a data_type
    string, or None."""
    if field_def is None:
        return "string", ""
    if isinstance(field_def, str):
        return field_def, ""
    return getattr(field_def, "data_type", "string"), getattr(field_def, "canonical_name", "")


def jaro(s1: str, s2: str) -> float:
    if s1 == s2:
        return 1.0
    if not s1 or not s2:
        return 0.0
    match_dist = max(max(len(s1), len(s2)) // 2 - 1, 0)
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
    t = k = 0
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


# Singleton — import this everywhere (P6: one normalizer)
normalizer = Normalizer()


def normalize(field_def, raw) -> Optional[str]:
    """Module-level convenience delegating to the singleton."""
    return normalizer.normalize(field_def, raw)


def compare(field_def, a, b, kind: Optional[str] = None) -> MatchResult:
    return normalizer.compare(field_def, a, b, kind=kind)
