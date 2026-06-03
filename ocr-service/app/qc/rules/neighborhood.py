"""
Neighborhood section rules (N-3 .. N-5 / checklist 21-23).
Deterministic numeric/format checks (Phase 1/3).
"""

from __future__ import annotations

from app.qc.config import qc_config
from app.qc.context import QCContext
from app.qc.matching import normalize_currency
from app.qc.registry import rule
from app.qc.result import RuleResult, RuleStatus

_LAND_USE_FIELDS = [
    "land_use_one_unit", "land_use_2_4_unit", "land_use_multi_family",
    "land_use_commercial", "land_use_other",
]
_BOUNDARIES = ["North", "South", "East", "West"]
_CHARACTERISTICS = {
    "location": "Location", "built_up": "Built-Up", "growth_rate": "Growth",
    "property_values": "Property Values", "demand_supply": "Demand/Supply",
    "marketing_time": "Marketing Time",
}


# ---- N-1 neighborhood characteristics / trends: each must be marked --------

@rule(id="N-1", num="19", section="neighborhood", phase=4, name="Neighborhood characteristics marked")
def n1_characteristics(ctx: QCContext):
    out = []
    for field, label in _CHARACTERISTICS.items():
        val = ctx.appraisal.value(field)
        ev = [ctx.appraisal.evidence(field)]
        if val and str(val).strip():
            out.append(RuleResult(rule_id="N-1", checklist_num="19", section="neighborhood",
                                  status=RuleStatus.PASS, fields_involved=[field], evidence=ev))
        else:
            out.append(RuleResult(rule_id="N-1", checklist_num="19", section="neighborhood",
                                  status=RuleStatus.VERIFY,
                                  message=qc_config.template("N-1-checkbox", field=label),
                                  fields_involved=[field], template_id="N-1-checkbox",
                                  evidence=ev, confidence=0.6))
    return out


# ---- N-3 one-unit housing price range Low <= High -------------------------

@rule(id="N-3", num="21", section="neighborhood", phase=3, name="Price range low <= high")
def n3_range(ctx: QCContext):
    lo = normalize_currency(ctx.appraisal.value("price_low"))
    hi = normalize_currency(ctx.appraisal.value("price_high"))
    ev = [ctx.appraisal.evidence("price_low"), ctx.appraisal.evidence("price_high")]
    if lo is None or hi is None:
        return RuleResult(rule_id="N-3", checklist_num="21", section="neighborhood",
                          status=RuleStatus.SKIPPED, message="price range not extracted",
                          fields_involved=["price_low", "price_high"], evidence=ev)
    if lo <= hi:
        return RuleResult(rule_id="N-3", checklist_num="21", section="neighborhood",
                          status=RuleStatus.PASS, fields_involved=["price_low", "price_high"], evidence=ev)
    return RuleResult(rule_id="N-3", checklist_num="21", section="neighborhood",
                      status=RuleStatus.VERIFY, message=qc_config.template("N-3-range"),
                      fields_involved=["price_low", "price_high"], template_id="N-3-range",
                      evidence=ev, confidence=0.7)


# ---- N-4 present land use sums to 100% ------------------------------------

@rule(id="N-4", num="22", section="neighborhood", phase=3, name="Present land use sums to 100%")
def n4_landuse(ctx: QCContext):
    vals = {f: normalize_currency(ctx.appraisal.value(f)) for f in _LAND_USE_FIELDS}
    present = {f: v for f, v in vals.items() if v is not None}
    ev = [ctx.appraisal.evidence(f) for f in present]
    if len(present) < 2:
        return RuleResult(rule_id="N-4", checklist_num="22", section="neighborhood",
                          status=RuleStatus.SKIPPED, message="land-use percentages not extracted",
                          fields_involved=list(present), evidence=ev)
    total = sum(present.values())
    if abs(total - 100.0) <= 1.0:
        return RuleResult(rule_id="N-4", checklist_num="22", section="neighborhood",
                          status=RuleStatus.PASS, fields_involved=list(present), evidence=ev)
    # land-use reads are error-prone → VERIFY rather than hard FAIL
    return RuleResult(rule_id="N-4", checklist_num="22", section="neighborhood",
                      status=RuleStatus.VERIFY,
                      message=qc_config.template("N-4-landuse") + f" (extracted total: {total:.0f}%)",
                      fields_involved=list(present), template_id="N-4-landuse",
                      evidence=ev, confidence=0.6)


# ---- N-5 neighborhood boundaries: all four present ------------------------

@rule(id="N-5", num="23", section="neighborhood", phase=1, name="All four boundaries delineated")
def n5_boundaries(ctx: QCContext):
    text = (ctx.appraisal.value("neighborhood_boundaries") or "")
    ev = [ctx.appraisal.evidence("neighborhood_boundaries")]
    if not text.strip():
        return RuleResult(rule_id="N-5", checklist_num="23", section="neighborhood",
                          status=RuleStatus.FAIL,
                          message=qc_config.template("N-5-delineation"),
                          fields_involved=["neighborhood_boundaries"],
                          template_id="N-5-delineation", evidence=ev)
    low = text.lower()
    missing = [d for d in _BOUNDARIES if d.lower() not in low]
    if not missing:
        return RuleResult(rule_id="N-5", checklist_num="23", section="neighborhood",
                          status=RuleStatus.PASS, fields_involved=["neighborhood_boundaries"], evidence=ev)
    return RuleResult(rule_id="N-5", checklist_num="23", section="neighborhood",
                      status=RuleStatus.VERIFY,
                      message=qc_config.template("N-5-boundary", field="/".join(missing)),
                      fields_involved=["neighborhood_boundaries"],
                      template_id="N-5-boundary", evidence=ev, confidence=0.7)
