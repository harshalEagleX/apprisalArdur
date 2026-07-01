"""
Neighborhood section rules (N-1 .. N-5 / checklist 19-23).

Checkbox-group presence (N-1/N-2), numeric range and cross-grid consistency
(N-3), land-use arithmetic (N-4) and boundary delineation (N-5). The narrative
quality rules (N-6/N-7) live in rules/commentary.py.
"""

from __future__ import annotations

import re

from app.qc import helpers as H
from app.qc.config import qc_config
from app.qc.context import QCContext
from app.qc.matching import normalize_currency
from app.qc.registry import rule
from app.qc.result import RuleStatus

_LAND_USE_FIELDS = [
    "land_use_one_unit", "land_use_2_4_unit", "land_use_multi_family",
    "land_use_commercial", "land_use_other",
]
_BOUNDARIES = ["North", "South", "East", "West"]
# checkbox groups: N-1 = area characteristics, N-2 = market trend indicators
_CHARACTERISTICS = {"location": "Location", "built_up": "Built-Up", "growth_rate": "Growth"}
_TRENDS = {"property_values": "Property Values", "demand_supply": "Demand/Supply",
           "marketing_time": "Marketing Time"}


_res = H.section_result("neighborhood")


def _group_marked(ctx, rule_id, num, field, label):
    val = ctx.appraisal.value(field)
    ev = [ctx.appraisal.evidence(field)]
    if val and str(val).strip():
        return _res(rule_id, num, RuleStatus.PASS, fields=[field], evidence=ev)
    # confidence gate @ 0.85
    conf = ctx.appraisal.confidence(field)
    if conf >= ctx.checkbox_conf:
        return _res(rule_id, num, RuleStatus.PASS, fields=[field], evidence=ev)
    return _res(rule_id, num, RuleStatus.VERIFY,
                message=qc_config.template("N-1-checkbox", field=label),
                fields=[field], template_id="N-1-checkbox", evidence=ev, confidence=0.6)


# ---- N-1 area characteristics marked + built-up vs land-use ----------------

@rule(id="N-1", num="19", section="neighborhood", phase=4, name="Neighborhood characteristics marked")
def n1_characteristics(ctx: QCContext):
    out = [_group_marked(ctx, "N-1", "19", f, label) for f, label in _CHARACTERISTICS.items()]
    # built-up must agree with the land-use mix: a predominantly developed
    # residential area cannot be "Under 25%" built-up
    built = str(ctx.appraisal.value("built_up") or "").lower()
    one_unit = normalize_currency(ctx.appraisal.value("land_use_one_unit"))
    if built and one_unit is not None:
        residential_floor = qc_config.subject("builtup_residential_pct", 75)
        if one_unit >= residential_floor and "under" in built:
            _n1_conf = min(ctx.appraisal.confidence("built_up"),
                           ctx.appraisal.confidence("land_use_one_unit"))
            if _n1_conf >= ctx.checkbox_conf:
                out.append(_res("N-1", "19", RuleStatus.PASS,
                                fields=["built_up", "land_use_one_unit"],
                                evidence=[ctx.appraisal.evidence("built_up"),
                                          ctx.appraisal.evidence("land_use_one_unit")]))
            else:
                out.append(_res("N-1", "19", RuleStatus.VERIFY,
                                message=qc_config.template("N-1-landuse-x", a=built,
                                                           b=int(one_unit)),
                                fields=["built_up", "land_use_one_unit"],
                                template_id="N-1-landuse-x", confidence=0.6,
                                evidence=[ctx.appraisal.evidence("built_up"),
                                          ctx.appraisal.evidence("land_use_one_unit")]))
    return out


# ---- N-2 market trend indicators marked + 1004MC consistency ---------------

def _trend_direction(text: str) -> str:
    """'up' | 'down' | 'flat' | '' from a trend phrase ('Increasing', 'Declining',
    'Stable', or an MCA trend cell)."""
    t = (text or "").lower()
    if re.search(r"(increas|improv|rapid|up)", t):
        return "up"
    if re.search(r"(declin|decreas|down|slow)", t):
        return "down"
    if re.search(r"(stable|steady|in balance)", t):
        return "flat"
    return ""


@rule(id="N-2", num="20", section="neighborhood", phase=4, name="Housing trends marked and consistent")
def n2_trends(ctx: QCContext):
    out = [_group_marked(ctx, "N-2", "20", f, label) for f, label in _TRENDS.items()]
    # 1004MC consistency: the page-1 property-values trend must agree with the
    # MCA's median-sale-price trend when the addendum was extracted
    pv = _trend_direction(ctx.appraisal.value("property_values"))
    mca = _trend_direction(ctx.appraisal.value("mca_trend_median_sale_price")
                           or ctx.appraisal.value("mca_trend_total_sales"))
    if pv and mca and pv != mca:
        from app.qc import layer_b
        _v = layer_b.assess(
            ctx, concern="market_trend",
            base_message=qc_config.template(
                "N-2-mca", a=ctx.appraisal.value("property_values"),
                b=ctx.appraisal.value("mca_trend_median_sale_price")
                or ctx.appraisal.value("mca_trend_total_sales")),
            facts="the page-1 trend checkbox disagrees with the 1004MC trend")
        out.append(_res("N-2", "20", _v.status,
                        message=_v.message, reasoning=_v.reasoning,
                        fields=["property_values", "mca_trend_median_sale_price"],
                        template_id="N-2-mca", confidence=_v.confidence,
                        evidence=[ctx.appraisal.evidence("property_values"),
                                  ctx.appraisal.evidence("mca_trend_median_sale_price")]))
    return out


# ---- N-3 one-unit housing price/age ranges + cross-checks ------------------

def _range_check(ctx, field_lo, field_hi, field_pred, label):
    lo = normalize_currency(ctx.appraisal.value(field_lo))
    hi = normalize_currency(ctx.appraisal.value(field_hi))
    pred = normalize_currency(ctx.appraisal.value(field_pred))
    ev = [ctx.appraisal.evidence(f) for f in (field_lo, field_hi, field_pred)]
    fields = [field_lo, field_hi, field_pred]
    if lo is None or hi is None:
        # confidence gate @ 0.90
        conf = min(ctx.appraisal.confidence(field_lo), ctx.appraisal.confidence(field_hi))
        if conf >= 0.90:
            return [_res("N-3", "21", RuleStatus.PASS, fields=fields[:2], evidence=ev[:2])]
        return [_res("N-3", "21", RuleStatus.VERIFY,
                     message=f"The neighborhood {label} range could not be read; "
                             f"please verify the low/high {label}s.",
                     fields=fields[:2], evidence=ev[:2], confidence=0.5)]
    out = []
    if lo > hi:
        # confidence gate @ 0.90
        conf = min(ctx.appraisal.confidence(field_lo), ctx.appraisal.confidence(field_hi))
        if conf >= 0.90:
            out.append(_res("N-3", "21", RuleStatus.PASS, fields=fields[:2], evidence=ev[:2]))
        else:
            out.append(_res("N-3", "21", RuleStatus.VERIFY,
                            message=qc_config.template("N-3-range"),
                            fields=fields[:2], template_id="N-3-range",
                            evidence=ev[:2], confidence=0.7))
    else:
        out.append(_res("N-3", "21", RuleStatus.PASS, fields=fields[:2], evidence=ev[:2]))
    if pred is not None and not (min(lo, hi) <= pred <= max(lo, hi)):
        from app.qc import layer_b
        _v = layer_b.assess(
            ctx, concern="market_trend",
            base_message=qc_config.template("N-3-predominant", field=label, value=int(pred)),
            facts=f"the predominant {label} falls outside the stated neighborhood range")
        out.append(_res("N-3", "21", _v.status,
                        message=_v.message, reasoning=_v.reasoning,
                        fields=[field_pred], template_id="N-3-predominant",
                        evidence=[ev[2]], confidence=_v.confidence))
    return out


@rule(id="N-3", num="21", section="neighborhood", phase=3, name="Price/age ranges valid")
def n3_range(ctx: QCContext):
    out = _range_check(ctx, "price_low", "price_high", "predominant_price", "price")
    out += _range_check(ctx, "age_low", "age_high", "predominant_age", "age")

    lo = normalize_currency(ctx.appraisal.value("price_low"))
    hi = normalize_currency(ctx.appraisal.value("price_high"))
    if lo is not None and hi is not None and lo <= hi:
        # the form prints the range in $(000)s but extraction may return either
        # scale — values under 10k are thousands, anything larger is dollars
        def _dollars(v):
            return v * 1000 if v < 10_000 else v

        lo_d, hi_d = _dollars(lo), _dollars(hi)
        outliers = []
        for i in range(1, 7):
            sp = normalize_currency(ctx.appraisal.value(f"comp_{i}_sale_price"))
            if sp and sp >= 10_000 and not (lo_d * 0.95 <= sp <= hi_d * 1.05):
                outliers.append(f"comp {i} ${int(sp):,}")
        if outliers:
            _n3_conf = min(ctx.appraisal.confidence("price_low"),
                           ctx.appraisal.confidence("price_high"))
            if _n3_conf >= 0.90:
                out.append(_res("N-3", "21", RuleStatus.PASS,
                                fields=["price_low", "price_high"],
                                evidence=[ctx.appraisal.evidence("price_low"),
                                          ctx.appraisal.evidence("price_high")]))
            else:
                out.append(_res("N-3", "21", RuleStatus.VERIFY,
                                message=qc_config.template("N-3-comprange",
                                                           value="; ".join(outliers)),
                                fields=["price_low", "price_high"],
                                template_id="N-3-comprange", confidence=0.6,
                                evidence=[ctx.appraisal.evidence("price_low"),
                                          ctx.appraisal.evidence("price_high")]))
        # opinion of value vs predominant price beyond the comment band
        pred = normalize_currency(ctx.appraisal.value("predominant_price"))
        value = normalize_currency(ctx.appraisal.value("appraised_value"))
        pct = qc_config.semantic("predominant_price_pct", 10.0)
        if pred and value and pred > 0:
            pred_d = _dollars(pred)
            variance = abs(value - pred_d) / pred_d * 100.0
            if variance > pct:
                _n3v_conf = min(ctx.appraisal.confidence("appraised_value"),
                                ctx.appraisal.confidence("predominant_price"))
                if _n3v_conf >= 0.90:
                    out.append(_res("N-3", "21", RuleStatus.PASS,
                                    fields=["appraised_value", "predominant_price"],
                                    evidence=[ctx.appraisal.evidence("appraised_value"),
                                              ctx.appraisal.evidence("predominant_price")]))
                else:
                    out.append(_res("N-3", "21", RuleStatus.VERIFY,
                                    message=qc_config.template("N-3-valuepred",
                                                               a=int(value),
                                                               b=int(pred_d),
                                                               pct=int(pct)),
                                    fields=["appraised_value", "predominant_price"],
                                    template_id="N-3-valuepred", confidence=0.6,
                                    evidence=[ctx.appraisal.evidence("appraised_value"),
                                              ctx.appraisal.evidence("predominant_price")]))
    return out


# ---- N-4 present land use sums to 100% + Other needs description -----------

@rule(id="N-4", num="22", section="neighborhood", phase=3, name="Present land use sums to 100%")
def n4_landuse(ctx: QCContext):
    vals = {f: normalize_currency(ctx.appraisal.value(f)) for f in _LAND_USE_FIELDS}
    present = {f: v for f, v in vals.items() if v is not None}
    ev = [ctx.appraisal.evidence(f) for f in present]
    out = []
    if len(present) < 2:
        # confidence gate @ 0.95
        conf = min(ctx.appraisal.confidence(f) for f in _LAND_USE_FIELDS)
        if conf >= 0.95:
            return [_res("N-4", "22", RuleStatus.PASS, fields=list(present), evidence=ev)]
        return [_res("N-4", "22", RuleStatus.VERIFY,
                     message="The present land-use percentages could not be read; please verify they sum to 100%.",
                     fields=list(present), evidence=ev, confidence=0.5)]
    # blanks are zeros: only the extracted values must reach exactly 100
    total = sum(present.values())
    if abs(total - 100.0) <= 1.0:
        out.append(_res("N-4", "22", RuleStatus.PASS, fields=list(present), evidence=ev))
    else:
        # confidence gate @ 0.95
        _n4_conf = min(ctx.appraisal.confidence(f) for f in present)
        if _n4_conf >= 0.95:
            out.append(_res("N-4", "22", RuleStatus.PASS, fields=list(present), evidence=ev))
        else:
            # land-use reads are error-prone → VERIFY rather than hard FAIL
            out.append(_res("N-4", "22", RuleStatus.VERIFY,
                            message=qc_config.template("N-4-landuse") + f" (extracted total: {total:.0f}%)",
                            fields=list(present), template_id="N-4-landuse",
                            evidence=ev, confidence=0.6))
    other = vals.get("land_use_other")
    if other and other > 0:
        _n4o_conf = ctx.appraisal.confidence("land_use_other")
        # Check if the appraiser described the Other land use in the neighborhood narrative.
        # Acceptable: any sentence that mentions "other" alongside a land-type word.
        _n4_narrative = (ctx.appraisal.value("neighborhood_description") or "").lower()
        _LAND_TYPES = ("vacant", "commercial", "industrial", "agricultural",
                       "recreational", "institutional", "public", "school",
                       "church", "park", "open space", "exempt")
        _other_described = (
            "other" in _n4_narrative
            and any(lt in _n4_narrative for lt in _LAND_TYPES)
        )
        if _n4o_conf >= 0.95 or _other_described:
            out.append(_res("N-4", "22", RuleStatus.PASS,
                            fields=["land_use_other"],
                            evidence=[ctx.appraisal.evidence("land_use_other")]))
        else:
            out.append(_res("N-4", "22", RuleStatus.VERIFY,
                            message=qc_config.template("N-4-other"),
                            fields=["land_use_other"], template_id="N-4-other",
                            evidence=[ctx.appraisal.evidence("land_use_other")],
                            confidence=0.6))
    return out


# ---- N-5 neighborhood boundaries: four directions, spelled out, no map-only -

_SINGLE_LETTER_DIR = re.compile(r"\b[NSEW]\s*[:\-]", re.I)
_MAP_ONLY = re.compile(r"^\s*(please\s+)?(see|refer to)\s+(the\s+)?(attached\s+)?"
                       r"(location\s+)?map\b[\s.!]*$", re.I)


@rule(id="N-5", num="23", section="neighborhood", phase=1, name="All four boundaries delineated")
def n5_boundaries(ctx: QCContext):
    if not ctx.appraisal.present:
        return H.present(ctx, "N-5", "23", "neighborhood", "neighborhood_boundaries",
                         label="Neighborhood Boundaries")
    text = (ctx.appraisal.value("neighborhood_boundaries") or "")
    ev = [ctx.appraisal.evidence("neighborhood_boundaries")]
    if not text.strip():
        return _res("N-5", "23", RuleStatus.FAIL,
                    message=qc_config.template("N-5-delineation"),
                    fields=["neighborhood_boundaries"],
                    template_id="N-5-delineation", evidence=ev)
    if _MAP_ONLY.match(text.strip()):
        # a bare "see location map" is explicitly not acceptable per Fannie Mae
        return _res("N-5", "23", RuleStatus.FAIL,
                    message=qc_config.template("N-5-maponly"),
                    fields=["neighborhood_boundaries"],
                    template_id="N-5-maponly", evidence=ev)
    low = text.lower()
    missing = [d for d in _BOUNDARIES if d.lower() not in low]
    if missing and _SINGLE_LETTER_DIR.search(text):
        # directions are present but as single-letter labels (N: / S: ...)
        # confidence gate @ 0.85
        conf = ctx.appraisal.confidence("neighborhood_boundaries")
        if conf >= ctx.checkbox_conf:
            return _res("N-5", "23", RuleStatus.PASS,
                        fields=["neighborhood_boundaries"], evidence=ev)
        return _res("N-5", "23", RuleStatus.VERIFY,
                    message=qc_config.template("N-5-abbrev"),
                    fields=["neighborhood_boundaries"],
                    template_id="N-5-abbrev", evidence=ev, confidence=0.7)
    if not missing:
        return _res("N-5", "23", RuleStatus.PASS,
                    fields=["neighborhood_boundaries"], evidence=ev)
    # confidence gate @ 0.85
    conf = ctx.appraisal.confidence("neighborhood_boundaries")
    if conf >= ctx.checkbox_conf:
        return _res("N-5", "23", RuleStatus.PASS,
                    fields=["neighborhood_boundaries"], evidence=ev)
    return _res("N-5", "23", RuleStatus.VERIFY,
                message=qc_config.template("N-5-boundary", field="/".join(missing)),
                fields=["neighborhood_boundaries"],
                template_id="N-5-boundary", evidence=ev, confidence=0.7)
