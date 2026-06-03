"""
Site section rules (ST-5, ST-6, ST-8 / checklist 30,31,33).
Includes the two HOLD escalations: illegal zoning and H&BU not 'Yes'.
"""

from __future__ import annotations

from app.qc.config import qc_config
from app.qc.context import QCContext
from app.qc.registry import rule
from app.qc.result import RuleResult, RuleStatus


# ---- ST-2 site area must carry a unit (sf / ac) ---------------------------

@rule(id="ST-2", num="27", section="site", phase=1, name="Site area has unit")
def st2_area(ctx: QCContext):
    area = ctx.appraisal.value("site_area")
    unit = ctx.appraisal.value("site_area_unit")
    ev = [ctx.appraisal.evidence("site_area"), ctx.appraisal.evidence("site_area_unit")]
    if not area:
        return RuleResult(rule_id="ST-2", checklist_num="27", section="site",
                          status=RuleStatus.SKIPPED, message="site area not extracted", evidence=ev)
    blob = f"{area} {unit or ''}".lower()
    if "sf" in blob or "ac" in blob or "sq" in blob or "acre" in blob:
        return RuleResult(rule_id="ST-2", checklist_num="27", section="site",
                          status=RuleStatus.PASS, fields_involved=["site_area", "site_area_unit"], evidence=ev)
    return RuleResult(rule_id="ST-2", checklist_num="27", section="site",
                      status=RuleStatus.VERIFY, message=qc_config.template("ST-2-area"),
                      fields_involved=["site_area", "site_area_unit"], template_id="ST-2-area",
                      evidence=ev, confidence=0.7)


# ---- ST-7 utilities: electricity + gas marked -----------------------------

@rule(id="ST-7", num="32", section="site", phase=4, name="Utilities electricity+gas marked")
def st7_utilities(ctx: QCContext):
    elec = str(ctx.appraisal.value("utilities_electricity") or "").lower() in {"true", "yes", "1", "x", "public"}
    gas = str(ctx.appraisal.value("utilities_gas") or "").lower() in {"true", "yes", "1", "x", "public"}
    ev = [ctx.appraisal.evidence("utilities_electricity"), ctx.appraisal.evidence("utilities_gas")]
    if elec and gas:
        return RuleResult(rule_id="ST-7", checklist_num="32", section="site",
                          status=RuleStatus.PASS,
                          fields_involved=["utilities_electricity", "utilities_gas"], evidence=ev)
    return RuleResult(rule_id="ST-7", checklist_num="32", section="site",
                      status=RuleStatus.VERIFY, message=qc_config.template("ST-7-utilities"),
                      fields_involved=["utilities_electricity", "utilities_gas"],
                      template_id="ST-7-utilities", evidence=ev, confidence=0.6)


# ---- ST-5 zoning compliance ------------------------------------------------

@rule(id="ST-5", num="30", section="site", phase=3, name="Zoning compliance")
def st5_zoning(ctx: QCContext):
    comp = (ctx.appraisal.value("zoning_compliance") or "").lower()
    ev = [ctx.appraisal.evidence("zoning_compliance")]
    if not comp:
        return RuleResult(rule_id="ST-5", checklist_num="30", section="site",
                          status=RuleStatus.SKIPPED, message="zoning compliance not extracted", evidence=ev)
    if "illegal" in comp:
        return RuleResult(rule_id="ST-5", checklist_num="30", section="site",
                          status=RuleStatus.HOLD,
                          message=qc_config.template("ST-5-illegal-hold"),
                          fields_involved=["zoning_compliance"], template_id="ST-5-illegal-hold", evidence=ev)
    if "non" in comp and "conform" in comp:
        return RuleResult(rule_id="ST-5", checklist_num="30", section="site",
                          status=RuleStatus.VERIFY,
                          message=qc_config.template("ST-5-nonconforming"),
                          fields_involved=["zoning_compliance"], template_id="ST-5-nonconforming",
                          evidence=ev, confidence=0.8)
    if "no zoning" in comp:
        return RuleResult(rule_id="ST-5", checklist_num="30", section="site",
                          status=RuleStatus.VERIFY,
                          message=qc_config.template("ST-5-nozoning"),
                          fields_involved=["zoning_compliance"], template_id="ST-5-nozoning",
                          evidence=ev, confidence=0.8)
    return RuleResult(rule_id="ST-5", checklist_num="30", section="site",
                      status=RuleStatus.PASS, fields_involved=["zoning_compliance"], evidence=ev)


# ---- ST-6 highest & best use must be 'Yes' (else HOLD) --------------------

@rule(id="ST-6", num="31", section="site", phase=3, name="Highest & best use is Yes")
def st6_hbu(ctx: QCContext):
    val = str(ctx.appraisal.value("highest_and_best_use") or "").lower()
    ev = [ctx.appraisal.evidence("highest_and_best_use")]
    if not val:
        return RuleResult(rule_id="ST-6", checklist_num="31", section="site",
                          status=RuleStatus.SKIPPED, message="H&BU not extracted", evidence=ev)
    if "yes" in val or val in {"true", "1", "x"}:
        return RuleResult(rule_id="ST-6", checklist_num="31", section="site",
                          status=RuleStatus.PASS, fields_involved=["highest_and_best_use"], evidence=ev)
    return RuleResult(rule_id="ST-6", checklist_num="31", section="site",
                      status=RuleStatus.HOLD,
                      message=qc_config.template("ST-6-hbu-hold"),
                      fields_involved=["highest_and_best_use"], template_id="ST-6-hbu-hold", evidence=ev)


# ---- ST-8 FEMA flood zone → marketability comment -------------------------

@rule(id="ST-8", num="33", section="site", phase=3, name="FEMA flood zone marketability comment")
def st8_flood(ctx: QCContext):
    in_flood = str(ctx.appraisal.value("fema_flood_hazard") or "").lower() in {"true", "yes", "1", "x"}
    zone = (ctx.appraisal.value("fema_flood_zone") or "").upper()
    ev = [ctx.appraisal.evidence("fema_flood_hazard"), ctx.appraisal.evidence("fema_flood_zone")]
    # Zones A/V (and subtypes) are special flood hazard areas
    special = bool(zone) and zone[0] in {"A", "V"}
    if in_flood or special:
        return RuleResult(rule_id="ST-8", checklist_num="33", section="site",
                          status=RuleStatus.VERIFY,
                          message=qc_config.template("ST-8-flood"),
                          fields_involved=["fema_flood_hazard", "fema_flood_zone"],
                          template_id="ST-8-flood", evidence=ev, confidence=0.7)
    return RuleResult(rule_id="ST-8", checklist_num="33", section="site",
                      status=RuleStatus.PASS,
                      fields_involved=["fema_flood_hazard", "fema_flood_zone"], evidence=ev)
