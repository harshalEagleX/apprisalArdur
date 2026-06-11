"""
Improvement section rules (I-1 .. I-12 / checklist 40-52).
Presence/format/consistency (Phase 1/3); the photo cross-checks (I-9 vision,
I-13 security bars) stay in the vision layer.
"""

from __future__ import annotations

import re

from app.qc import helpers as H
from app.qc.config import qc_config
from app.qc.context import QCContext
from app.qc.registry import rule
from app.qc.result import RuleResult, RuleStatus


def _res(rule_id, num, status, message="", fields=None, evidence=None,
         template_id=None, confidence=1.0) -> RuleResult:
    return RuleResult(rule_id=rule_id, checklist_num=num, section="improvements",
                      status=status, message=message, fields_involved=fields or [],
                      evidence=evidence or [], template_id=template_id,
                      confidence=confidence)


def _year_of(text) -> int:
    m = re.search(r"\b(18|19|20)\d{2}\b", str(text or ""))
    return int(m.group(0)) if m else 0


def _int_of(text):
    m = re.search(r"\d{1,3}", str(text or ""))
    return int(m.group(0)) if m else None


# ---- I-1 general description complete + age consistency --------------------

_GEN_FIELDS = {
    "units_count": "Units", "stories": "Stories", "dwelling_type": "Type",
    "design_style": "Design (Style)", "year_built": "Year Built",
    "effective_age": "Effective Age",
}


@rule(id="I-1", num="40", section="improvements", phase=1, name="General description complete")
def i1_general(ctx: QCContext):
    missing = [label for f, label in _GEN_FIELDS.items() if not ctx.appraisal.value(f)]
    ev = [ctx.appraisal.evidence(f) for f in _GEN_FIELDS]
    out = []
    if not missing:
        out.append(_res("I-1", "40", RuleStatus.PASS, fields=list(_GEN_FIELDS), evidence=ev))
    elif len(missing) >= len(_GEN_FIELDS) - 1:
        # essentially nothing extracted → the classic gendesc finding
        out.append(_res("I-1", "40", RuleStatus.FAIL,
                        message=qc_config.template("I-1-gendesc"),
                        fields=list(_GEN_FIELDS), template_id="I-1-gendesc", evidence=ev))
    else:
        out.append(_res("I-1", "40", RuleStatus.VERIFY,
                        message=qc_config.template("I-1-fields", value=", ".join(missing)),
                        fields=list(_GEN_FIELDS), template_id="I-1-fields",
                        evidence=ev, confidence=0.6))

    # year built plausibility + effective age <= actual age
    yb = _year_of(ctx.appraisal.value("year_built"))
    eff_year = _year_of(ctx.appraisal.value("effective_date"))
    eff_age = _int_of(ctx.appraisal.value("effective_age"))
    if yb and eff_year and eff_age is not None:
        actual = eff_year - yb
        if 0 <= actual < 250 and eff_age > actual:
            ev2 = [ctx.appraisal.evidence("effective_age"), ctx.appraisal.evidence("year_built")]
            status = RuleStatus.FAIL
            if min(ctx.appraisal.confidence("effective_age"),
                   ctx.appraisal.confidence("year_built")) < ctx.structured_conf:
                status = RuleStatus.VERIFY
            out.append(_res("I-1", "40", status,
                            message=qc_config.template("I-1-age", a=eff_age, b=actual),
                            fields=["effective_age", "year_built"],
                            template_id="I-1-age", evidence=ev2, confidence=0.7))
    return out


# ---- I-2 foundation description present ------------------------------------

@rule(id="I-2", num="41", section="improvements", phase=1, name="Foundation described")
def i2_foundation(ctx: QCContext):
    val = ctx.appraisal.value("foundation_type")
    ev = [ctx.appraisal.evidence("foundation_type")]
    if val and str(val).strip():
        return _res("I-2", "41", RuleStatus.PASS, fields=["foundation_type"], evidence=ev)
    return _res("I-2", "41", RuleStatus.VERIFY,
                message=qc_config.template("I-2-foundation"),
                fields=["foundation_type"], template_id="I-2-foundation",
                evidence=ev, confidence=0.6)


# ---- I-3/I-4 exterior + interior materials present ---------------------------

_MATERIAL_FIELDS = {
    "exterior_walls": "Exterior Walls", "roof_surface": "Roof Surface",
    "heating": "Heating", "floor_material": "Floors",
    "walls_material": "Walls", "trim_finish_material": "Trim/Finish",
}


@rule(id="I-34", num="42", section="improvements", phase=1, name="Materials/condition described")
def i34_materials(ctx: QCContext):
    missing = [label for f, label in _MATERIAL_FIELDS.items() if not ctx.appraisal.value(f)]
    ev = [ctx.appraisal.evidence(f) for f in _MATERIAL_FIELDS]
    if not missing:
        return _res("I-34", "42", RuleStatus.PASS, fields=list(_MATERIAL_FIELDS), evidence=ev)
    return _res("I-34", "42", RuleStatus.VERIFY,
                message=qc_config.template("I-34-materials", value=", ".join(missing)),
                fields=list(_MATERIAL_FIELDS), template_id="I-34-materials",
                evidence=ev, confidence=0.6)


# ---- I-7 above-grade room count present ------------------------------------

@rule(id="I-7", num="48", section="improvements", phase=1, name="Above-grade room count present")
def i7_rooms(ctx: QCContext):
    fields = ["total_rooms", "bedrooms", "baths", "gla"]
    missing = [f for f in fields if not ctx.appraisal.value(f)]
    ev = [ctx.appraisal.evidence(f) for f in fields]
    if not missing:
        return _res("I-7", "48", RuleStatus.PASS, fields=fields, evidence=ev)
    status = RuleStatus.VERIFY if len(missing) < len(fields) else RuleStatus.FAIL
    return _res("I-7", "48", status, message=qc_config.template("I-7-roomcount"),
                fields=missing, template_id="I-7-roomcount", evidence=ev, confidence=0.7)


# ---- I-9 condition rating: UAD format + grid consistency + effective age ----

@rule(id="I-9", num="50", section="improvements", phase=1, name="Condition rating UAD and consistent")
def i9_condition(ctx: QCContext):
    out = [H.format_regex(ctx, "I-9", "50", "improvements", "condition_rating",
                          r"^C[1-6]$", "I-9-condition", label="Condition")]
    cond = (ctx.appraisal.value("condition_rating") or "").strip().upper()
    grid = (ctx.appraisal.value("subject_grid_condition_rating") or "").strip().upper()
    if cond and grid and re.fullmatch(r"C[1-6]", cond) and re.fullmatch(r"C[1-6]", grid) \
            and cond != grid:
        # the same property cannot be two conditions in one report
        out.append(_res("I-9", "50", RuleStatus.FAIL,
                        message=qc_config.template("I-9-grid", a=cond, b=grid),
                        fields=["condition_rating", "subject_grid_condition_rating"],
                        template_id="I-9-grid", confidence=0.8,
                        evidence=[ctx.appraisal.evidence("condition_rating"),
                                  ctx.appraisal.evidence("subject_grid_condition_rating")]))
    # a C1-C3 (good condition) property whose effective age EQUALS its actual
    # age is internally inconsistent — good condition implies a lower effective age
    yb = _year_of(ctx.appraisal.value("year_built"))
    eff_year = _year_of(ctx.appraisal.value("effective_date"))
    eff_age = _int_of(ctx.appraisal.value("effective_age"))
    if cond in {"C1", "C2", "C3"} and yb and eff_year and eff_age is not None:
        actual = eff_year - yb
        if actual > 5 and eff_age >= actual:
            out.append(_res("I-9", "50", RuleStatus.VERIFY,
                            message=qc_config.template("I-9-effage", value=cond),
                            fields=["condition_rating", "effective_age"],
                            template_id="I-9-effage", confidence=0.6,
                            evidence=[ctx.appraisal.evidence("condition_rating"),
                                      ctx.appraisal.evidence("effective_age")]))
    return out


# ---- I-Q quality rating UAD format (Q1-Q6) --------------------------------

@rule(id="I-Q", num="66", section="improvements", phase=1, name="Quality rating UAD format")
def iq_quality(ctx: QCContext):
    return H.format_regex(ctx, "I-Q", "66", "improvements", "quality_rating",
                          r"^Q[1-6]$", "I-Q-quality", label="Quality")


# ---- I-10 adverse conditions affecting livability ----------------------------

@rule(id="I-10", num="51", section="improvements", phase=3, name="Adverse livability conditions addressed")
def i10_adverse(ctx: QCContext):
    val = str(ctx.appraisal.value("adverse_conditions") or "").strip().lower()
    ev = [ctx.appraisal.evidence("adverse_conditions")]
    if not val:
        return _res("I-10", "51", RuleStatus.VERIFY,
                    message="The adverse conditions answer could not be extracted; manual review required.",
                    fields=["adverse_conditions"], evidence=ev, confidence=0.5)
    if val in {"false", "no", "0"}:
        return _res("I-10", "51", RuleStatus.PASS, fields=["adverse_conditions"], evidence=ev)
    return _res("I-10", "51", RuleStatus.VERIFY,
                message=qc_config.template("I-10-adverse"),
                fields=["adverse_conditions"], template_id="I-10-adverse",
                evidence=ev, confidence=0.6)


# ---- I-11 conformity to neighborhood (No → commentary) --------------------

@rule(id="I-11", num="52", section="improvements", phase=3, name="Conforms to neighborhood")
def i11_conform(ctx: QCContext):
    val = ctx.appraisal.value("conforms_to_neighborhood")
    ev = [ctx.appraisal.evidence("conforms_to_neighborhood")]
    if val is None:
        return _res("I-11", "52", RuleStatus.VERIFY,
                    message="Conformity to the neighborhood could not be read; please verify the improvements conform.",
                    fields=["conforms_to_neighborhood"], evidence=ev, confidence=0.5)
    truthy = str(val).strip().lower() in {"true", "yes", "1", "x"}
    if truthy:
        return _res("I-11", "52", RuleStatus.PASS,
                    fields=["conforms_to_neighborhood"], evidence=ev)
    return _res("I-11", "52", RuleStatus.VERIFY, message=qc_config.template("I-11-conform"),
                fields=["conforms_to_neighborhood"],
                template_id="I-11-conform", evidence=ev, confidence=0.7)


# ---- I-12 additions / conversions referenced in commentary -------------------

_ADDITION = re.compile(r"\b(addition|converted garage|garage conversion|bonus room"
                       r"|added (?:square footage|sq\.? ?ft|living area)|enclosed (?:porch|patio))\b", re.I)

_NARRATIVE_FIELDS = ("sales_comparison_summary", "final_reconciliation_comment",
                     "neighborhood_description", "contract_analysis_comment")


@rule(id="I-12", num="53", section="improvements", phase=3, name="Additions addressed")
def i12_additions(ctx: QCContext):
    # advisory: fires only when the extracted narrative actually references an
    # addition/conversion — silence (no keyword) is a PASS, not a gap
    for f in _NARRATIVE_FIELDS:
        text = ctx.appraisal.value(f) or ""
        m = _ADDITION.search(text)
        if m:
            return _res("I-12", "53", RuleStatus.VERIFY,
                        message=qc_config.template("I-12-addition", value=m.group(0)),
                        fields=[f], template_id="I-12-addition",
                        evidence=[ctx.appraisal.evidence(f)], confidence=0.6)
    return _res("I-12", "53", RuleStatus.PASS,
                message="", fields=list(_NARRATIVE_FIELDS))
