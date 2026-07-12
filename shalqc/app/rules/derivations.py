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

from typing import Callable, Optional

__version__ = "drv-1.0.0"

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


DERIVERS = {
    "property_type_compose": property_type_compose,
    "appliances_join": appliances_join,
    "housing_trends_present": housing_trends_present,
    "mca_total_sales_sum": mca_total_sales_sum,
}
