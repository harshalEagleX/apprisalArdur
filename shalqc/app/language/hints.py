"""
language.hints — the ~8 generic computed-hint functions (§4.1).

"computed_hints are the surviving useful part of machine observations — generic
arithmetic the code can always do without per-rule logic." There is NO per-rule
hint code, ever: these functions work over any set of bound labels, so a
count/sum/min/max/%/date-diff/equality check compiles for free for every AMC.

Each hint is `{hint, value, labels}` — the judge is told (prompt rule 4) to trust
these and only contradict one by quoting packet values.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from app.normalize import dates as _dates
from app.normalize.normalizer import match_band as _match_band

_NUMERIC_TYPES = frozenset({"integer", "number", "currency", "percent", "float"})

# PART 1.3: values that LOOK present but carry no positive/triggering content. A
# "field must not be blank" check is satisfied by any of these ONLY if the check
# wants mere presence; a "field triggers X" check must treat them as absent
# ($0 HOA dues is NOT "HOA dues present"). Surfaced to the judge as a hint.
_NULLISH = frozenset({
    "", "0", "0.0", "0.00", "$0", "$0.00", "n/a", "na", "none", "--", "-", "0%", "tbd"})


# A prior-sale / transfer AMOUNT of $0 is a LEGITIMATE value, not "missing": a
# gift, inheritance, or grant-deed transfer between owners closes at $0 by UAD
# convention (the appraiser states it and explains it in the prior-sale comment).
# So these labels are exempted from the nullish "treat $0 as absent" rule — a
# "price of prior sale is missing" check must not fire on an honest $0 transfer.
# Generic canonical-label pattern (any AMC), never a per-item pin.
_TRANSFER_AMOUNT_RX = re.compile(r"prior_sale_price|prior_transfer_price|_transfer_amount")


def _is_nullish(v: Any) -> bool:
    if v is None:
        return True
    s = re.sub(r"\s+", " ", str(v)).strip().lower()
    if s in _NULLISH:
        return True
    num = re.sub(r"[,$%\s]", "", s)          # a currency/number that reduces to zero
    try:
        return float(num) == 0.0
    except ValueError:
        return False


# P3(b) / F9: a comp that is an ACTIVE/PENDING listing (not a settled sale) carries
# no settlement date by UAD convention — so a "sale date present for every comp"
# check must EXEMPT it. Detected generically from listing_status / sale_type / the
# sale_date marker itself, for any AMC, no per-item config.
_LISTING_RX = re.compile(r"\b(active|pending|listing|under\s*contract|offered|for\s*sale)\b", re.I)
_COMP_IDX_RX = re.compile(r"^comp_(\d+)_")


# UAD date-of-sale grammar: a SETTLED sale carries an "s" component ("s06/26"); a
# pending/contract carries only "c" ("c06/26"); an active listing shows "Active".
# A comp with a contract component but NO settlement component has not closed →
# no settlement date → exempt (this is F9's comp_6="c06/26", verified on 445 Sparrow).
_UAD_SETTLED_RX = re.compile(r"s\d", re.I)
_UAD_CONTRACT_RX = re.compile(r"c\d", re.I)


def _no_settlement_date(sale_date: Any) -> bool:
    sd = str(sale_date or "")
    if not sd:
        return False
    # a contract-only date (has "c", lacks "s") → not settled
    if _UAD_CONTRACT_RX.search(sd) and not _UAD_SETTLED_RX.search(sd):
        return True
    return False


def _listing_comps(values: Dict[str, Any]) -> List[int]:
    """Indices of present comps that are listings / not-yet-settled (no settlement
    date expected). Detected from a listing WORD (Active/Pending/…) OR the UAD
    date grammar (a contract-only "cMM/YY" with no settlement "sMM/YY")."""
    idxs: set = set()
    for lbl in values:
        m = _COMP_IDX_RX.match(lbl)
        if m:
            idxs.add(int(m.group(1)))
    out: List[int] = []
    for i in sorted(idxs):
        status = values.get(f"comp_{i}_listing_status")
        sale_type = values.get(f"comp_{i}_sale_type")
        sale_date = values.get(f"comp_{i}_sale_date")
        blob = " ".join(str(x) for x in (status, sale_type, sale_date) if x)
        if _LISTING_RX.search(blob) or _no_settlement_date(sale_date):
            out.append(i)
    return out


_NBHD_PRICE_RX = re.compile(r"(?:^|_)(price_low|price_high|predominant_price|median_price)$")


def _price_scale_hint(values: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """F11: when neighborhood price fields (price_low/high/predominant/median) read
    like $(000) — i.e. they are <10k while comp sale prices are >100k — surface the
    ×1000 scaled dollar values so a "price range brackets the comps" check doesn't
    see a spurious 1000x mismatch. Purely magnitude+shape inferred; fires only when
    BOTH a small-magnitude price field AND dollar-scale comp prices are present."""
    nbhd = {lbl: _num(values.get(lbl)) for lbl in values if _NBHD_PRICE_RX.search(lbl)}
    nbhd = {k: v for k, v in nbhd.items() if v is not None and v > 0}
    if not nbhd:
        return None
    comp_prices = [v for lbl in values if re.match(r"^comp_\d+_sale_price$", lbl)
                   for v in (_num(values.get(lbl)),) if v is not None and v > 0]
    if not comp_prices:
        return None
    max_nbhd = max(nbhd.values())
    min_comp = min(comp_prices)
    # neighborhood prices look like thousands (<10k) while comps are dollar-scale (>100k)
    if max_nbhd < 10_000 and min_comp > 100_000:
        scaled = {k: round(v * 1000.0, 2) for k, v in nbhd.items()}
        return {"hint": "price_scale_000 (neighborhood prices are $(000); ×1000 shown to "
                        "compare with comp sale prices)",
                "value": scaled, "labels": list(nbhd.keys())}
    return None


def _xdoc_kind(label: str) -> str:
    """PART 1.2: the comparison kind for a cross-document label (its
    engagement./contract. prefix stripped), so match_band normalizes correctly."""
    n = label.split(".", 1)[-1].lower()
    if "address" in n or "street" in n or n in ("city", "state", "zip", "zip_code"):
        return "address"
    if "phone" in n:
        return "phone"
    if "email" in n:
        return "email"
    if "company" in n or "lender" in n or "client" in n or "amc" in n:
        return "company"
    if "borrower" in n or "seller" in n or "owner" in n or n in ("appraiser_name",):
        return "person"
    if "transaction_type" in n or "loan_program" in n or "assignment" in n or "purpose" in n:
        return "enum"
    if "form" in n or "product" in n:
        return "form"
    return "generic"


def _num(v: Any) -> Optional[float]:
    if v is None:
        return None
    m = re.search(r"-?\d[\d,]*\.?\d*", str(v))
    if not m:
        return None
    try:
        return float(m.group(0).replace(",", ""))
    except ValueError:
        return None


def _nums(values: Dict[str, Any], labels: List[str]) -> List[float]:
    out = []
    for lbl in labels:
        n = _num(values.get(lbl))
        if n is not None:
            out.append(n)
    return out


# ── the generic hint functions ───────────────────────────────────────────────

def count_present(values: Dict[str, Any], labels: List[str]) -> int:
    return sum(1 for lbl in labels if values.get(lbl) not in (None, ""))


def comp_count_present(values: Dict[str, Any]) -> int:
    """Number of comparables actually present — the anchor for count-style checks
    at any N (§7 S-10). A comp is 'present' if it has a sale price."""
    n = 0
    for i in range(1, 13):
        if values.get(f"comp_{i}_sale_price") not in (None, ""):
            n += 1
    return n


def sum_of(values: Dict[str, Any], labels: List[str]) -> Optional[float]:
    ns = _nums(values, labels)
    return round(sum(ns), 4) if ns else None


def min_of(values: Dict[str, Any], labels: List[str]) -> Optional[float]:
    ns = _nums(values, labels)
    return min(ns) if ns else None


def max_of(values: Dict[str, Any], labels: List[str]) -> Optional[float]:
    ns = _nums(values, labels)
    return max(ns) if ns else None


def pct_of(values: Dict[str, Any], numer: str, denom: str) -> Optional[float]:
    a, b = _num(values.get(numer)), _num(values.get(denom))
    if a is None or not b:
        return None
    return round(a / b * 100.0, 3)


def date_diff_days(values: Dict[str, Any], a: str, b: str) -> Optional[int]:
    da, db = _dates.parse_date(str(values.get(a) or "")), _dates.parse_date(str(values.get(b) or ""))
    if not da or not db:
        return None
    return abs((da - db).days)


def _numeric_family(label: str) -> Optional[str]:
    """The comp_N-collapsed schema attribute this label is, iff the schema says
    it is actually numeric-typed — None otherwise (excludes it from sum/min/max
    entirely). Two labels are commensurable (safe to sum/min/max together) only
    when they reduce to the SAME family: comp_1_sale_price..comp_7_sale_price
    are the same attribute repeated across comps (the intended §7 S-10 use);
    contract_price + year_built, or a quality-rating code + a dollar
    adjustment, are not — they only look numeric because a regex found digits
    somewhere in the string (2026-07-13 dry-run cause #5: sums that silently
    added quality-rating codes to dollar adjustments, and street numbers to
    census tracts, then had the validator penalize a correct judge answer for
    disagreeing with the resulting nonsense)."""
    from app.extraction.schema import schema_loader
    from app.language.label_dictionary import canonical_label

    family = canonical_label(label)
    fd = schema_loader.get_field(family)
    if fd is None or fd.data_type not in _NUMERIC_TYPES:
        return None
    return family


def equal_after_norm(values: Dict[str, Any], a: str, b: str) -> Optional[bool]:
    va, vb = values.get(a), values.get(b)
    if va is None or vb is None:
        return None
    na = re.sub(r"[^a-z0-9]+", "", str(va).lower())
    nb = re.sub(r"[^a-z0-9]+", "", str(vb).lower())
    if not na or not nb:
        return None
    return na == nb or na in nb or nb in na


# ── driver: compute the always-safe hint set for a packet ────────────────────

def _heat_family(s: Any) -> str:
    """Map a heating token to a canonical HEAT FAMILY, absorbing every vendor spelling.
    Subject enums ("ForcedWarmAir") and grid abbreviations ("FA/CENT", "F/AIR/CAC",
    "HP", "EBB") must land on the same family so a comparison is meaningful. Cooling
    tokens (CENT/CAC/AC/None) are irrelevant to the HEAT family and ignored."""
    t = re.sub(r"[^a-z]", " ", str(s or "").lower())
    if "radiant" in t or re.search(r"\brad\b", t):
        return "radiant"
    if "heat pump" in t or "heatpump" in t or "htpump" in t or re.search(r"\bhp\b", t):
        return "heat_pump"
    if ("baseboard" in t or re.search(r"\be?bb\b", t) or re.search(r"\bhwbb\b", t)
            or re.search(r"\bebb\b", t)):
        return "baseboard"
    if ("forced" in t or "warm air" in t or "warmair" in t or re.search(r"\bf\s*air\b", t)
            or re.search(r"\bfwa\b", t) or re.search(r"\bfa\b", t) or re.search(r"\bfau\b", t)):
        return "forced_air"
    if re.search(r"\bwall\b", t) or "wall furnace" in t or "space heat" in t or "ductless" in t or "mini split" in t:
        return "other_fixed"
    if not t.strip() or re.search(r"\bnone\b", t) or re.search(r"\bother\b", t):
        return "none"
    return "unknown"


# The families whose UAD rule requires ≥1 matching comp (EQ-72's own text: FWA/FWBB/Radiant).
_HEAT_MATCH_REQUIRED = frozenset({"forced_air", "baseboard", "radiant"})


def _car_storage_hint(values: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """DETERMINISTIC car-storage presence for EQ-74. A non-zero subject car count
    (number_of_cars / parking_space_number / garage_spaces) means the subject HAS a
    garage/carport, so the check APPLIES — it must not be N/A'd as "no garage". Tells
    the judge the subject's storage and each comp's grid cell so a "2ga2dw" match is
    obvious, since the judge otherwise reads a bare count as "garage not marked"."""
    subj = None
    for k in ("number_of_cars", "parking_space_number", "garage_spaces"):
        v = values.get(k)
        if v not in (None, ""):
            n = _num(v)
            subj = n if n is not None else v
            break
    if subj in (None, "") or (isinstance(subj, (int, float)) and subj == 0):
        return None
    comps = {i: values.get(f"comp_{i}_garage_carport")
             for i in range(1, 13) if values.get(f"comp_{i}_garage_carport") not in (None, "")}
    return {
        "hint": (f"subject_car_storage={subj} (non-zero → subject HAS a garage/carport, so this "
                 f"check APPLIES, not N/A); comp_garage_cells={comps} "
                 f"(a cell like '2ga2dw' = 2-car garage + 2 driveway = reflects garage with driveway)"),
        "value": {"subject_car_storage": subj, "applies": True, "comp_cells": comps},
        "labels": ["number_of_cars"] + [f"comp_{i}_garage_carport" for i in comps],
    }


def _heating_match_hint(values: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """DETERMINISTIC heat-family reconciliation for EQ-72. The judge cannot be trusted
    to equate the subject enum "ForcedWarmAir" with grid tokens "FA"/"F/AIR", so compute
    it: subject family, each comp's family, which comps share it, and whether the
    "≥1 matching comp" requirement (only for FWA/FWBB/Radiant subjects) is met."""
    subj = values.get("heating") or values.get("heating_description")
    subj_fam = _heat_family(subj) if subj else None
    if not subj_fam or subj_fam in ("none", "unknown"):
        return None
    comp_fams: Dict[int, str] = {}
    for i in range(1, 13):
        v = values.get(f"comp_{i}_heating_cooling")
        if v not in (None, ""):
            comp_fams[i] = _heat_family(v)
    if not comp_fams:
        return None
    matches = [i for i, f in comp_fams.items() if f == subj_fam]
    required = subj_fam in _HEAT_MATCH_REQUIRED
    met = (not required) or bool(matches)
    return {
        "hint": (f"heating_family_match: subject={subj_fam}; per_comp={comp_fams}; "
                 f"matching_comps={matches}; requirement_applies={required}; requirement_met={met} "
                 f"(FA/F-AIR/ForcedWarmAir are all forced_air — treat as MATCH)"),
        "value": {"subject_family": subj_fam, "matching_comps": matches, "requirement_met": met},
        "labels": ["heating"] + [f"comp_{i}_heating_cooling" for i in comp_fams],
    }


def compute_hints(values: Dict[str, Any], bound_labels: List[str],
                  expects: str = "", comp_count: Optional[int] = None) -> List[Dict[str, Any]]:
    """Every hint we can safely derive for this item. `comp_count_present` is
    ALWAYS included so count-style checks work at any N. Numeric aggregates are
    added when ≥2 bound labels carry numbers; a date-diff when exactly two bound
    labels are dates; an equality when `expects` hints at a comparison.

    `comp_count` overrides the comp tally when the caller knows it from the full
    report (the packet's bound labels may not include comp_*_sale_price)."""
    present = [lbl for lbl in bound_labels if values.get(lbl) not in (None, "")]
    cc = comp_count if comp_count is not None else comp_count_present(values)
    hints: List[Dict[str, Any]] = [
        {"hint": "comp_count_present", "value": cc, "labels": []},
        {"hint": "count(bound labels present)", "value": len(present), "labels": present},
    ]

    # sum/min/max: only across labels that are (a) schema-numeric-typed, not
    # just regex-parseable, and (b) all the SAME attribute (e.g. every present
    # comp's sale price) — see _numeric_family. One aggregate block per family
    # that actually has 2+ members; unrelated numeric fields never mix.
    families: Dict[str, List[str]] = {}
    for lbl in bound_labels:
        if _num(values.get(lbl)) is None:
            continue
        fam = _numeric_family(lbl)
        if fam is not None:
            families.setdefault(fam, []).append(lbl)
    for fam, numeric_labels in families.items():
        if len(numeric_labels) < 2:
            continue
        suffix = f" ({fam})" if len(families) > 1 else ""
        hints.append({"hint": f"sum{suffix}", "value": sum_of(values, numeric_labels), "labels": numeric_labels})
        hints.append({"hint": f"min{suffix}", "value": min_of(values, numeric_labels), "labels": numeric_labels})
        hints.append({"hint": f"max{suffix}", "value": max_of(values, numeric_labels), "labels": numeric_labels})

    date_labels = [lbl for lbl in bound_labels
                   if _dates.parse_date(str(values.get(lbl) or ""))]
    if len(date_labels) == 2:
        dd = date_diff_days(values, date_labels[0], date_labels[1])
        if dd is not None:
            hints.append({"hint": "date_diff_days", "value": dd, "labels": date_labels})

    # PART 1.3: present-looking values that are actually nullish ($0/N/A/blank).
    # The judge is told (doctrine) to treat these as NOT present for a presence
    # check — the fix for EQ-11 ("hoa_dues $0" was read as "HOA present").
    nullish = [lbl for lbl in present
               if _is_nullish(values.get(lbl)) and not _TRANSFER_AMOUNT_RX.search(lbl)]
    if nullish:
        hints.append({"hint": "nullish_values (present but $0/N/A/blank)",
                      "value": nullish, "labels": nullish})

    # P3(b) / F9: comps that are active/pending listings carry no settlement date —
    # a "sale date present for every comp" check must exempt them (UAD convention).
    listings = _listing_comps(values)
    if listings:
        hints.append({"hint": "listing_comps (no settlement/sale date expected — UAD listing)",
                      "value": listings,
                      "labels": [f"comp_{i}_listing_status" for i in listings]})

    # P8 / F11: the 1004MC neighborhood price columns are in $(000) per the URAR form,
    # but comp sale prices are whole dollars — comparing 1450 to 1,260,000 is a false
    # 1000x gap. Detected by SHAPE (price_low/high/predominant) + MAGNITUDE (looks like
    # thousands next to dollar-scale comp prices), never a hardcoded label pin.
    scale = _price_scale_hint(values)
    if scale:
        hints.append(scale)

    # EQ-72: deterministic heat-family match so "ForcedWarmAir" vs grid "FA"/"F/AIR" is
    # resolved in code, not left to the judge (which false-rejected it on the held-out set).
    heat = _heating_match_hint(values)
    if heat:
        hints.append(heat)

    # EQ-74: deterministic car-storage presence so a non-zero subject car count is not
    # mis-read as "no garage" and N/A'd.
    car = _car_storage_hint(values)
    if car:
        hints.append(car)

    # PART 1.2: a NORMALIZED cross-document comparison, so a trailing comma, a
    # corporate suffix, ZIP+4, or "Refinance Transaction" vs "Refinance" can no
    # longer read as a mismatch. Fires ONLY for a genuine cross-document PAIR — an
    # engagement./contract.-prefixed label AND its same-named appraisal counterpart.
    # (It must never compare two unrelated same-document fields, e.g. heating vs
    # air_conditioning — that produced a false "mismatch" reject on EQ-72.)
    for lbl in present:
        if not lbl.startswith(("engagement.", "contract.")):
            continue
        base = lbl.split(".", 1)[1]
        if base not in values or values.get(base) is None:
            continue
        kind = _xdoc_kind(base)
        band = _match_band(values.get(base), values.get(lbl), kind)
        hints.append({"hint": f"normalized_match ({kind}): {band}",
                      "value": band, "labels": [base, lbl]})

    return hints
