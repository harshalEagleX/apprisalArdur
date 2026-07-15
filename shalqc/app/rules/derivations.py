"""
rules.derivations (drv-1.0.0) — computed fields for field-resolution.

Some rule needs[] are not stored anywhere as a single value; they are a
composition of other extracted values (property_type = dwelling_type + units,
appliances = the set that are present, etc.). field_resolution.yaml `derive:`
maps a rule name to one of these functions. Each takes a `get(name) -> value`
closure (raw same-document lookup, no alias recursion) and returns a string
value or None when the inputs to compute it are themselves absent.

Kept pure and tiny — no I/O, no LLM. A None return means "cannot derive",
which flows on as a genuine missing field (real VERIFY), never a fabricated one.
"""
from __future__ import annotations

import re
from typing import Callable, Optional

__version__ = "drv-1.0.0"

# USPAP reporting-option text sources, in priority order. The USPAP addendum is a
# late, mostly-text page; MISMO has no native field for the Appraisal-vs-Restricted
# choice, and its checkbox mark is not reliably readable — so we recover it from
# the prose the extractor already captured for that section.
_REPORT_TYPE_TEXT_SOURCES = (
    "appraisal_report_type",       # verbatim, if some extractor ever populates it
    "addendum_text",               # concatenated AppraisalAddendumText (uspap page)
    "intended_use_statement",
    "intended_user_statement",
    "scope_of_work",
    "certification_text",
)

# Positive ASSERTION sentences — "this ... is a[n] (Restricted) Appraisal Report".
# These name exactly one type, so they survive a page that merely LISTS both
# options (where both labels appear regardless of which box is checked). Matching
# the assertion, not the bare label, is what makes this high-precision.
_ASSERT_RESTRICTED = re.compile(
    r"\b(?:is|as)\s+(?:a|an)\s+restricted\s+appraisal\s+report\b", re.I)
_ASSERT_APPRAISAL = re.compile(
    r"\b(?:is|as)\s+(?:a|an)\s+appraisal\s+report\b", re.I)

_APPLIANCE_KEYS = (
    "appliance_refrigerator", "appliance_range_oven", "appliance_range",
    "appliance_oven", "appliance_dishwasher", "appliance_disposal",
    "appliance_microwave", "appliance_washer_dryer", "appliance_washer",
    "appliance_dryer", "appliance_hood_fan",
)

_MCA_SALES_KEYS = (
    "mca_total_sales_current_3", "mca_total_sales_prior_4_6",
    "mca_total_sales_prior_7_12",
)


def _truthy_yes(v) -> bool:
    return v is not None and str(v).strip().lower() in ("yes", "y", "true", "1")


def property_type_compose(get: Callable[[str], Optional[str]]) -> Optional[str]:
    """dwelling_type + units_count -> e.g. 'Detached, 1 unit'."""
    dwelling = get("dwelling_type")
    units = get("units_count")
    if not dwelling and not units:
        return None
    parts = []
    if dwelling:
        parts.append(str(dwelling).strip())
    if units:
        u = str(units).strip()
        parts.append(f"{u} unit" + ("" if u == "1" else "s"))
    return ", ".join(parts) if parts else None


def appliances_join(get: Callable[[str], Optional[str]]) -> Optional[str]:
    """Join the appliance_* fields that are marked present into one list."""
    present = []
    for k in _APPLIANCE_KEYS:
        if _truthy_yes(get(k)):
            present.append(k.replace("appliance_", "").replace("_", " "))
    if not present:
        # no appliance_* field was populated at all -> cannot derive
        if all(get(k) is None for k in _APPLIANCE_KEYS):
            return None
        return "none marked"
    return ", ".join(present)


def housing_trends_present(get: Callable[[str], Optional[str]]) -> Optional[str]:
    """Housing-trends box is 'present' when any of the three trend cells is."""
    cells = {
        "growth": get("growth"),
        "demand_supply": get("demand_supply"),
        "marketing_time": get("marketing_time"),
    }
    filled = {k: v for k, v in cells.items() if v is not None and str(v).strip()}
    if not filled:
        return None
    return "; ".join(f"{k}={v}" for k, v in filled.items())


def mca_total_sales_sum(get: Callable[[str], Optional[str]]) -> Optional[str]:
    """Sum the three MCA settled-sales buckets into a single count."""
    total = 0
    seen = False
    for k in _MCA_SALES_KEYS:
        v = get(k)
        if v is None:
            continue
        try:
            total += int(float(str(v).replace(",", "").strip()))
            seen = True
        except (ValueError, TypeError):
            continue
    return str(total) if seen else None


def comp_count_present(get: Callable[[str], Optional[str]]) -> Optional[str]:
    """Number of comparables actually present in the grid (has a sale price).
    Mirrors app/language/hints.py's comp_count_present so both the v1 rules
    engine (needs[] -> field_resolution derive) and the v2 packet builder
    (DocView.field() falls through to the same resolver) see one real value
    instead of a label that is never a stored field (was landing in every
    packet's absent_labels while computed_hints separately reported a count —
    a packet contradicting itself)."""
    n = 0
    for i in range(1, 13):
        if get(f"comp_{i}_sale_price") is not None:
            n += 1
    return str(n)


def appraisal_report_type_from_text(get: Callable[[str], Optional[str]]) -> Optional[str]:
    """USPAP reporting option: 'Appraisal Report' vs 'Restricted Appraisal Report'.

    HIGH-PRECISION by design, not high-recall. Returns the enum ONLY when the
    captured USPAP prose ASSERTS a single type ("... is an Appraisal Report as
    defined by ...", "... a Restricted Appraisal Report ..."). A page that merely
    LISTS both checkbox options — where both labels appear no matter which box is
    ticked — yields None, because text extraction drops the check mark and a
    guessed enum would be a confident wrong verdict. None flows on as a genuine
    absent field: the judge doctrine (rule 3/3a) caps such a check at REVIEW
    rather than inventing a violation. 'Restricted' is checked FIRST so the more
    specific type wins the shared 'appraisal report' substring."""
    direct = get("appraisal_report_type")
    if direct and str(direct).strip():
        return str(direct).strip()

    blob = "\n".join(str(get(k)) for k in _REPORT_TYPE_TEXT_SOURCES if get(k))
    if not blob:
        return None
    if _ASSERT_RESTRICTED.search(blob):
        return "Restricted Appraisal Report"
    # "Appraisal Report" only when NO restricted assertion is present anywhere —
    # never emit the plain type off a page that also asserts the restricted one.
    if _ASSERT_APPRAISAL.search(blob) and not _ASSERT_RESTRICTED.search(blob):
        return "Appraisal Report"
    return None


DERIVERS = {
    "property_type_compose": property_type_compose,
    "appliances_join": appliances_join,
    "housing_trends_present": housing_trends_present,
    "mca_total_sales_sum": mca_total_sales_sum,
    "comp_count_present": comp_count_present,
    "appraisal_report_type_from_text": appraisal_report_type_from_text,
}
