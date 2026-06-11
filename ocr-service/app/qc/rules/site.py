"""
Site section rules (ST-1 .. ST-10 / checklist 26-34).
Includes the two HOLD escalations: illegal zoning and H&BU not 'Yes'.
"""

from __future__ import annotations

import re

from app.qc.config import qc_config
from app.qc.context import QCContext
from app.qc.matching import normalize_currency
from app.qc.registry import rule
from app.qc.result import RuleResult, RuleStatus

_TRUTHY = {"true", "yes", "1", "x"}
_SQFT_PER_ACRE = 43_560


def _has_site_detail(ctx: QCContext) -> bool:
    """Dimensions/Shape exist on the 1004-family site section; the condo (1073)
    and multi-unit (1025) forms describe the project site instead."""
    return ctx.form_type not in ("1073", "1025")


def _res(rule_id, num, status, message="", fields=None, evidence=None,
         template_id=None, confidence=1.0) -> RuleResult:
    return RuleResult(rule_id=rule_id, checklist_num=num, section="site",
                      status=status, message=message, fields_involved=fields or [],
                      evidence=evidence or [], template_id=template_id,
                      confidence=confidence)


# ---- ST-1 site dimensions: real measurements or irregular+plat -------------

_DIMS = re.compile(r"\d+\.?\d*\s*(?:x|by|\*|×)\s*\d+", re.I)
_IRREGULAR = re.compile(r"(irregular|irr\b|see\s+plat|see\s+survey)", re.I)


@rule(id="ST-1", num="26", section="site", phase=1, applies_when=_has_site_detail,
      name="Site dimensions provided")
def st1_dimensions(ctx: QCContext):
    val = (ctx.appraisal.value("site_dimensions") or "").strip()
    ev = [ctx.appraisal.evidence("site_dimensions")]
    if not val:
        return _res("ST-1", "26", RuleStatus.VERIFY,
                    message="Site Dimensions could not be extracted from the document; manual review required.",
                    fields=["site_dimensions"], evidence=ev, confidence=0.5)
    if _DIMS.search(val):
        return _res("ST-1", "26", RuleStatus.PASS, fields=["site_dimensions"], evidence=ev)
    if _IRREGULAR.search(val):
        # an irregular site is fine only with a plat map (no plat-page classifier
        # field yet, so the reviewer confirms the plat is attached)
        return _res("ST-1", "26", RuleStatus.VERIFY,
                    message=qc_config.template("ST-1-dims"),
                    fields=["site_dimensions"], template_id="ST-1-dims",
                    evidence=ev, confidence=0.6)
    return _res("ST-1", "26", RuleStatus.VERIFY,
                message=qc_config.template("ST-1-dims"),
                fields=["site_dimensions"], template_id="ST-1-dims",
                evidence=ev, confidence=0.6)


# ---- ST-2 site area must carry the CORRECT unit (sf < 1 acre <= ac) --------

@rule(id="ST-2", num="27", section="site", phase=1, name="Site area has correct unit")
def st2_area(ctx: QCContext):
    area = ctx.appraisal.value("site_area")
    unit = ctx.appraisal.value("site_area_unit")
    ev = [ctx.appraisal.evidence("site_area"), ctx.appraisal.evidence("site_area_unit")]
    fields = ["site_area", "site_area_unit"]
    if not area:
        return _res("ST-2", "27", RuleStatus.VERIFY,
                    message="The site area could not be read; please verify the site size and unit in the report.",
                    fields=fields, evidence=ev, confidence=0.5)
    blob = f"{area} {unit or ''}".lower()
    is_sf = "sf" in blob or "sq" in blob
    is_ac = re.search(r"\bac\b|acre", blob) is not None
    if not (is_sf or is_ac):
        return _res("ST-2", "27", RuleStatus.VERIFY, message=qc_config.template("ST-2-area"),
                    fields=fields, template_id="ST-2-area", evidence=ev, confidence=0.7)
    # unit correctness: under one acre must be sf, one acre or more must be ac
    num = normalize_currency(area)
    if num is not None:
        wrong = (
            # an sf value at/over 43,560 should be expressed in acres
            (is_sf and num >= _SQFT_PER_ACRE)
            # an "ac" value under 1 should be sf; one in the tens of thousands
            # is an sf magnitude with an acre unit (typo either way)
            or (is_ac and (num < 1.0 or num >= _SQFT_PER_ACRE))
        )
        if wrong:
            return _res("ST-2", "27", RuleStatus.VERIFY,
                        message=qc_config.template("ST-2-area"),
                        fields=fields, template_id="ST-2-area",
                        evidence=ev, confidence=0.7)
    return _res("ST-2", "27", RuleStatus.PASS, fields=fields, evidence=ev)


# ---- ST-3 site shape (irregular → plat) -------------------------------------

@rule(id="ST-3", num="28", section="site", phase=1, applies_when=_has_site_detail,
      name="Site shape provided")
def st3_shape(ctx: QCContext):
    val = (ctx.appraisal.value("site_shape") or "").strip()
    ev = [ctx.appraisal.evidence("site_shape")]
    if not val:
        return _res("ST-3", "28", RuleStatus.VERIFY,
                    message="Site Shape could not be extracted from the document; manual review required.",
                    fields=["site_shape"], evidence=ev, confidence=0.5)
    if _IRREGULAR.search(val) or val.strip().upper() == "I":
        return _res("ST-3", "28", RuleStatus.VERIFY,
                    message=qc_config.template("ST-3-shape"),
                    fields=["site_shape"], template_id="ST-3-shape",
                    evidence=ev, confidence=0.6)
    return _res("ST-3", "28", RuleStatus.PASS, fields=["site_shape"], evidence=ev)


# ---- ST-4 view: UAD format + sales-grid subject consistency ------------------

_UAD_VIEW = re.compile(r"^[NBA]\s*;\s*\w", re.I)


@rule(id="ST-4", num="29", section="site", phase=1, name="View UAD compliant and consistent")
def st4_view(ctx: QCContext):
    val = (ctx.appraisal.value("site_view") or "").strip()
    ev = [ctx.appraisal.evidence("site_view")]
    out = []
    if not val:
        return [_res("ST-4", "29", RuleStatus.VERIFY,
                     message="The subject View could not be extracted from the site section; manual review required.",
                     fields=["site_view"], evidence=ev, confidence=0.5)]
    if _UAD_VIEW.match(val):
        out.append(_res("ST-4", "29", RuleStatus.PASS, fields=["site_view"], evidence=ev))
    else:
        out.append(_res("ST-4", "29", RuleStatus.VERIFY,
                        message=qc_config.template("ST-4-view"),
                        fields=["site_view"], template_id="ST-4-view",
                        evidence=ev, confidence=0.7))
    # the same view must appear in the SCA grid subject column
    grid = (ctx.appraisal.value("subject_grid_view") or "").strip()
    if grid and val and grid.replace(" ", "").lower() != val.replace(" ", "").lower():
        out.append(_res("ST-4", "29", RuleStatus.VERIFY,
                        message=qc_config.template("ST-4-grid", a=val, b=grid),
                        fields=["site_view", "subject_grid_view"],
                        template_id="ST-4-grid", confidence=0.6,
                        evidence=[ctx.appraisal.evidence("site_view"),
                                  ctx.appraisal.evidence("subject_grid_view")]))
    return out


# ---- ST-7 utilities: electricity + gas marked, private well/septic ----------

@rule(id="ST-7", num="32", section="site", phase=4, name="Utilities marked; private systems addressed")
def st7_utilities(ctx: QCContext):
    elec = str(ctx.appraisal.value("utilities_electricity") or "").lower() in _TRUTHY | {"public"}
    gas = str(ctx.appraisal.value("utilities_gas") or "").lower() in _TRUTHY | {"public"}
    ev = [ctx.appraisal.evidence("utilities_electricity"), ctx.appraisal.evidence("utilities_gas")]
    out = []
    if elec and gas:
        out.append(_res("ST-7", "32", RuleStatus.PASS,
                        fields=["utilities_electricity", "utilities_gas"], evidence=ev))
    else:
        out.append(_res("ST-7", "32", RuleStatus.VERIFY,
                        message=qc_config.template("ST-7-utilities"),
                        fields=["utilities_electricity", "utilities_gas"],
                        template_id="ST-7-utilities", evidence=ev, confidence=0.6))
    # private well / septic must be addressed (typical for area + marketability)
    water = str(ctx.appraisal.value("utilities_water") or "").lower()
    sewer = str(ctx.appraisal.value("utilities_sewer") or "").lower()
    if "private" in water or "private" in sewer or "septic" in sewer or "well" in water:
        out.append(_res("ST-7", "32", RuleStatus.VERIFY,
                        message=qc_config.template("ST-7-wellseptic"),
                        fields=["utilities_water", "utilities_sewer"],
                        template_id="ST-7-wellseptic", confidence=0.6,
                        evidence=[ctx.appraisal.evidence("utilities_water"),
                                  ctx.appraisal.evidence("utilities_sewer")]))
    return out


# ---- ST-5 zoning compliance ------------------------------------------------

@rule(id="ST-5", num="30", section="site", phase=3, name="Zoning compliance")
def st5_zoning(ctx: QCContext):
    comp = (ctx.appraisal.value("zoning_compliance") or "").lower()
    ev = [ctx.appraisal.evidence("zoning_compliance")]
    if not comp:
        return _res("ST-5", "30", RuleStatus.VERIFY,
                    message="Zoning compliance could not be read; please verify the zoning classification and compliance in the report.",
                    fields=["zoning_compliance"], evidence=ev, confidence=0.5)
    if "illegal" in comp:
        return _res("ST-5", "30", RuleStatus.HOLD,
                    message=qc_config.template("ST-5-illegal-hold"),
                    fields=["zoning_compliance"], template_id="ST-5-illegal-hold", evidence=ev)
    if "non" in comp and "conform" in comp:
        return _res("ST-5", "30", RuleStatus.VERIFY,
                    message=qc_config.template("ST-5-nonconforming"),
                    fields=["zoning_compliance"], template_id="ST-5-nonconforming",
                    evidence=ev, confidence=0.8)
    if "no zoning" in comp:
        return _res("ST-5", "30", RuleStatus.VERIFY,
                    message=qc_config.template("ST-5-nozoning"),
                    fields=["zoning_compliance"], template_id="ST-5-nozoning",
                    evidence=ev, confidence=0.8)
    return _res("ST-5", "30", RuleStatus.PASS, fields=["zoning_compliance"], evidence=ev)


# ---- ST-6 highest & best use must be 'Yes' (else HOLD) --------------------

@rule(id="ST-6", num="31", section="site", phase=3, name="Highest & best use is Yes")
def st6_hbu(ctx: QCContext):
    val = str(ctx.appraisal.value("highest_and_best_use") or "").lower()
    ev = [ctx.appraisal.evidence("highest_and_best_use")]
    if not val:
        return _res("ST-6", "31", RuleStatus.VERIFY,
                    message="Highest & best use could not be read; please verify it is marked Yes (as-improved).",
                    fields=["highest_and_best_use"], evidence=ev, confidence=0.5)
    if "yes" in val or val in {"true", "1", "x"}:
        return _res("ST-6", "31", RuleStatus.PASS,
                    fields=["highest_and_best_use"], evidence=ev)
    return _res("ST-6", "31", RuleStatus.HOLD,
                message=qc_config.template("ST-6-hbu-hold"),
                fields=["highest_and_best_use"], template_id="ST-6-hbu-hold", evidence=ev)


# ---- ST-8 FEMA flood data complete + flood-zone marketability ----------------

@rule(id="ST-8", num="33", section="site", phase=3, name="FEMA flood data complete; zone addressed")
def st8_flood(ctx: QCContext):
    in_flood = str(ctx.appraisal.value("fema_flood_hazard") or "").lower() in _TRUTHY
    zone = (ctx.appraisal.value("fema_flood_zone") or "").upper()
    map_date = ctx.appraisal.value("fema_map_date")
    ev = [ctx.appraisal.evidence("fema_flood_hazard"), ctx.appraisal.evidence("fema_flood_zone"),
          ctx.appraisal.evidence("fema_map_date")]
    out = []
    # zone + map date must be completed regardless of flood-zone status
    if not zone or not map_date:
        out.append(_res("ST-8", "33", RuleStatus.VERIFY,
                        message=qc_config.template("ST-8-femadata"),
                        fields=["fema_flood_zone", "fema_map_date"],
                        template_id="ST-8-femadata", evidence=ev, confidence=0.6))
    # Zones A/V (and subtypes) are special flood hazard areas
    special = bool(zone) and zone[0] in {"A", "V"}
    if in_flood or special:
        out.append(_res("ST-8", "33", RuleStatus.VERIFY,
                        message=qc_config.template("ST-8-flood"),
                        fields=["fema_flood_hazard", "fema_flood_zone"],
                        template_id="ST-8-flood", evidence=ev, confidence=0.7))
    if not out:
        out.append(_res("ST-8", "33", RuleStatus.PASS,
                        fields=["fema_flood_hazard", "fema_flood_zone"], evidence=ev))
    return out


# ---- ST-10 adverse site conditions → commentary ------------------------------

@rule(id="ST-10", num="34", section="site", phase=3, name="Adverse site conditions addressed")
def st10_adverse(ctx: QCContext):
    val = str(ctx.appraisal.value("adverse_site_conditions") or "").strip().lower()
    ev = [ctx.appraisal.evidence("adverse_site_conditions")]
    if not val:
        return _res("ST-10", "34", RuleStatus.VERIFY,
                    message="The adverse site conditions answer could not be extracted; manual review required.",
                    fields=["adverse_site_conditions"], evidence=ev, confidence=0.5)
    if val in {"false", "no", "0"}:
        return _res("ST-10", "34", RuleStatus.PASS,
                    fields=["adverse_site_conditions"], evidence=ev)
    # Yes (or a described condition) → the condition and its market impact need
    # commentary; no commentary field is extracted, so the reviewer confirms
    return _res("ST-10", "34", RuleStatus.VERIFY,
                message=qc_config.template("ST-10-adverse"),
                fields=["adverse_site_conditions"], template_id="ST-10-adverse",
                evidence=ev, confidence=0.6)
