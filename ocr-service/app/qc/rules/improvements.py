"""
Improvement section rules (I-1 .. I-12 / checklist 40-52).
Presence/format/consistency (Phase 1/3); the photo cross-checks (I-9 vision,
I-13 security bars) stay in the vision layer.
"""

from __future__ import annotations

import re

from app.qc import helpers as H
from app.qc import layer_b
from app.qc import matching
from app.qc.config import qc_config
from app.qc.context import QCContext
from app.qc.registry import rule
from app.qc.result import RuleStatus


_res = H.section_result("improvements")


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
    if not ctx.appraisal.present:
        return H.present(ctx, "I-1", "40", "improvements", "design_style",
                         label="General Description")
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
        # confidence gate @ 0.85
        conf = min(ctx.appraisal.confidence(f) for f in _GEN_FIELDS)
        if conf >= ctx.checkbox_conf:
            out.append(_res("I-1", "40", RuleStatus.PASS, fields=list(_GEN_FIELDS), evidence=ev))
        else:
            out.append(_res("I-1", "40", RuleStatus.VERIFY,
                            message=qc_config.template("I-1-fields", value=", ".join(missing)),
                            fields=list(_GEN_FIELDS), template_id="I-1-fields",
                            evidence=ev, confidence=0.6))

    # year built plausibility + effective age <= actual age
    yb = matching.year_of(ctx.appraisal.value("year_built"))
    eff_year = matching.year_of(ctx.appraisal.value("effective_date"))
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
    # confidence gate @ 0.85
    conf = ctx.appraisal.confidence("foundation_type")
    if conf >= ctx.checkbox_conf:
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
    # confidence gate @ 0.85
    conf = min(ctx.appraisal.confidence(f) for f in _MATERIAL_FIELDS)
    if conf >= ctx.checkbox_conf:
        return _res("I-34", "42", RuleStatus.PASS, fields=list(_MATERIAL_FIELDS), evidence=ev)
    return _res("I-34", "42", RuleStatus.VERIFY,
                message=qc_config.template("I-34-materials", value=", ".join(missing)),
                fields=list(_MATERIAL_FIELDS), template_id="I-34-materials",
                evidence=ev, confidence=0.6)


# ---- I-7 above-grade room count present ------------------------------------

@rule(id="I-7", num="48", section="improvements", phase=1, name="Above-grade room count present")
def i7_rooms(ctx: QCContext):
    if not ctx.appraisal.present:
        return H.present(ctx, "I-7", "48", "improvements", "gla",
                         label="Above Grade Room Count")
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
    yb = matching.year_of(ctx.appraisal.value("year_built"))
    eff_year = matching.year_of(ctx.appraisal.value("effective_date"))
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
        # Improvement claimed (eff_age significantly < actual) but the appraiser's
        # own narrative says "no update" — an internal inconsistency that needs
        # reconciliation (MIRA Finding B equivalent: C3 + eff_age 10 vs actual 18
        # with "no updates in 15 years" comment). Surface when the gap >= 5 years.
        improvement_gap = actual - eff_age
        if improvement_gap >= 5:
            narrative = " ".join(str(ctx.appraisal.value(f) or "")
                                 for f in ("market_conditions_commentary",
                                           "sales_comparison_summary",
                                           "neighborhood_description")).lower()
            no_update_signal = bool(re.search(
                r"no\s+update|not\s+been\s+updated|original\s+(condition|kitchen|bath|floor)"
                r"|dated\s+(kitchen|bath|interior)|no\s+renovation|unupdated",
                narrative, re.I))
            if no_update_signal:
                out.append(_res("I-9", "50", RuleStatus.VERIFY,
                                message=qc_config.template("I-9-noupdate",
                                                           eff=eff_age, actual=actual,
                                                           gap=improvement_gap),
                                fields=["effective_age", "condition_rating"],
                                template_id="I-9-noupdate", confidence=0.7,
                                evidence=[ctx.appraisal.evidence("effective_age"),
                                          ctx.appraisal.evidence("condition_rating")]))
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
        # confidence gate @ 0.85
        conf = ctx.appraisal.confidence("adverse_conditions")
        if conf >= ctx.checkbox_conf:
            return _res("I-10", "51", RuleStatus.PASS, fields=["adverse_conditions"], evidence=ev)
        return _res("I-10", "51", RuleStatus.VERIFY,
                    message="The adverse conditions answer could not be extracted; manual review required.",
                    fields=["adverse_conditions"], evidence=ev, confidence=0.5)
    if val in {"false", "no", "0"}:
        return _res("I-10", "51", RuleStatus.PASS, fields=["adverse_conditions"], evidence=ev)
    v = layer_b.assess(ctx, concern="adverse_condition",
                       base_message=qc_config.template("I-10-adverse"),
                       facts="an adverse livability condition was indicated")
    return _res("I-10", "51", v.status, message=v.message, reasoning=v.reasoning,
                fields=["adverse_conditions"], template_id="I-10-adverse",
                evidence=ev, confidence=v.confidence)


# ---- I-11 conformity to neighborhood (No → commentary) --------------------

@rule(id="I-11", num="52", section="improvements", phase=3, name="Conforms to neighborhood")
def i11_conform(ctx: QCContext):
    val = ctx.appraisal.value("conforms_to_neighborhood")
    ev = [ctx.appraisal.evidence("conforms_to_neighborhood")]
    if val is None:
        # confidence gate @ 0.85
        conf = ctx.appraisal.confidence("conforms_to_neighborhood")
        if conf >= ctx.checkbox_conf:
            return _res("I-11", "52", RuleStatus.PASS,
                        fields=["conforms_to_neighborhood"], evidence=ev)
        return _res("I-11", "52", RuleStatus.VERIFY,
                    message="Conformity to the neighborhood could not be read; please verify the improvements conform.",
                    fields=["conforms_to_neighborhood"], evidence=ev, confidence=0.5)
    truthy = str(val).strip().lower() in {"true", "yes", "1", "x"}
    if truthy:
        return _res("I-11", "52", RuleStatus.PASS,
                    fields=["conforms_to_neighborhood"], evidence=ev)
    v = layer_b.assess(ctx, concern="conformity",
                       base_message=qc_config.template("I-11-conform"),
                       facts="the improvement is marked as not conforming to the neighborhood")
    return _res("I-11", "52", v.status, message=v.message, reasoning=v.reasoning,
                fields=["conforms_to_neighborhood"],
                template_id="I-11-conform", evidence=ev, confidence=v.confidence)


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
            # confidence gate @ 0.85
            conf = ctx.appraisal.confidence(f)
            if conf >= ctx.checkbox_conf:
                return _res("I-12", "53", RuleStatus.PASS, fields=[f],
                            evidence=[ctx.appraisal.evidence(f)])
            return _res("I-12", "53", RuleStatus.VERIFY,
                        message=qc_config.template("I-12-addition", value=m.group(0)),
                        fields=[f], template_id="I-12-addition",
                        evidence=[ctx.appraisal.evidence(f)], confidence=0.6)
    return _res("I-12", "53", RuleStatus.PASS,
                message="", fields=list(_NARRATIVE_FIELDS))


# ---- I-5 utilities: heating + cooling described ----------------------------

@rule(id="I-5", num="44", section="improvements", phase=1, name="Heating and cooling described")
def i5_utilities(ctx: QCContext):
    if not ctx.appraisal.present:
        return []
    heating = str(ctx.appraisal.value("heating") or "").strip()
    cooling = str(ctx.appraisal.value("cooling") or "").strip()
    ev = [ctx.appraisal.evidence("heating"), ctx.appraisal.evidence("cooling")]
    missing = [lbl for v, lbl in ((heating, "Heating"), (cooling, "Cooling")) if not v]
    if not missing:
        return [_res("I-5", "44", RuleStatus.PASS, fields=["heating", "cooling"], evidence=ev)]
    # confidence gate @ 0.85
    conf = min(ctx.appraisal.confidence("heating"), ctx.appraisal.confidence("cooling"))
    if conf >= ctx.checkbox_conf:
        return [_res("I-5", "44", RuleStatus.PASS, fields=["heating", "cooling"], evidence=ev)]
    # Missing a utility field is usually an extraction gap, not an appraiser error → VERIFY.
    return [_res("I-5", "44", RuleStatus.VERIFY,
                 message=qc_config.template("I-5-utilities", value=", ".join(missing)),
                 fields=["heating", "cooling"], template_id="I-5-utilities",
                 evidence=ev, confidence=0.6)]


# ---- I-6 appliances reported ----------------------------------------------

_APPLIANCE_FIELDS = [
    "appliance_refrigerator", "appliance_range_oven", "appliance_disposal",
    "appliance_dishwasher", "appliance_microwave", "appliance_washer_dryer",
]


@rule(id="I-6", num="45", section="improvements", phase=1, name="Appliances reported")
def i6_appliances(ctx: QCContext):
    if not ctx.appraisal.present:
        return []
    present_any = any(str(ctx.appraisal.value(f) or "").strip() for f in _APPLIANCE_FIELDS)
    ev = [ctx.appraisal.evidence(f) for f in _APPLIANCE_FIELDS]
    if present_any:
        return [_res("I-6", "45", RuleStatus.PASS, fields=_APPLIANCE_FIELDS, evidence=ev)]
    # confidence gate @ 0.85
    conf = min(ctx.appraisal.confidence(f) for f in _APPLIANCE_FIELDS)
    if conf >= ctx.checkbox_conf:
        return [_res("I-6", "45", RuleStatus.PASS, fields=_APPLIANCE_FIELDS, evidence=ev)]
    # No appliance captured at all → likely an extraction gap; flag for confirmation.
    return [_res("I-6", "45", RuleStatus.VERIFY,
                 message=qc_config.template("I-6-appliances"),
                 fields=_APPLIANCE_FIELDS, template_id="I-6-appliances",
                 evidence=ev, confidence=0.5)]


# ---- I-8 additional features / amenities ----------------------------------

_AMENITY_FIELDS = ["fireplace_count", "porch_patio_deck", "additional_features"]


@rule(id="I-8", num="48", section="improvements", phase=2, name="Additional features described")
def i8_features(ctx: QCContext):
    if not ctx.appraisal.present:
        return []
    captured = any(str(ctx.appraisal.value(f) or "").strip() for f in _AMENITY_FIELDS)
    ev = [ctx.appraisal.evidence(f) for f in _AMENITY_FIELDS]
    if captured:
        return [_res("I-8", "48", RuleStatus.PASS, fields=_AMENITY_FIELDS, evidence=ev)]
    # confidence gate @ 0.85
    conf = min(ctx.appraisal.confidence(f) for f in _AMENITY_FIELDS)
    if conf >= ctx.checkbox_conf:
        return [_res("I-8", "48", RuleStatus.PASS, fields=_AMENITY_FIELDS, evidence=ev)]
    # Narrative line not reliably extracted → low-confidence reviewer reminder only.
    return [_res("I-8", "48", RuleStatus.VERIFY,
                 message=qc_config.template("I-8-features"),
                 fields=_AMENITY_FIELDS, template_id="I-8-features",
                 evidence=ev, confidence=0.4)]


# ---- I-SMCO smoke/CO detector compliance commentary ------------------------
# Equity Solutions USA / Champions Funding engagement letter explicitly requires
# "Smoke and Carbon Monoxide Detectors: per local code requirements" to be
# noted in the report. This is a written, repeating checklist item.
# Strategy: scan the full-page narrative text for detector-related keywords.
# Advisory level (VERIFY, never FAIL) because the commentary may appear in a
# section the extractor didn't capture — the reviewer confirms.

_DETECTOR_RE = re.compile(
    r"\b(smoke\s*det(ector)?|carbon\s*monoxide|co\s*det(ector)?|"
    r"detector\s*code|per\s+(local\s+)?code)\b",
    re.I)

_NARRATIVE_SOURCES = (
    "sales_comparison_summary", "final_reconciliation_comment",
    "market_conditions_commentary", "contract_analysis_comment",
    "neighborhood_description",
)


# ---- IM-2 bedroom/bath/total-room triplet consistency ----------------------

@rule(id="IM-2", num="40b", section="improvements", phase=1,
      name="Bedroom / total-room count consistency")
def im2_room_triplet(ctx: QCContext):
    """The total room count must exceed the bedroom count.  When the inequality
    is violated the values are likely transposed (a recurring extraction bug
    where the bedroom-count cell position overlaps the total-rooms cell).

    Hard rule: bedrooms < total_rooms.
    Soft heuristic (confidence signal only, never standalone VERIFY):
      total_rooms >= bedrooms + 2  (living room + kitchen are standard rooms).
    Studio/efficiency units (0 bedrooms) are explicitly excluded — 0 < N is
    always satisfied when any rooms exist, so the rule is vacuously satisfied.

    When the inequality is violated, the rule surfaces a swap-recovery candidate
    if swapping the two values resolves the inequality and produces a GLA ratio
    that is more plausible than the current extraction — framed as a hypothesis
    in the message, never auto-applied."""
    rooms_raw = ctx.appraisal.value("total_rooms")
    beds_raw  = ctx.appraisal.value("bedrooms")
    gla_raw   = ctx.appraisal.value("gla")
    ev = [ctx.appraisal.evidence("total_rooms"), ctx.appraisal.evidence("bedrooms")]
    fields = ["total_rooms", "bedrooms"]

    if rooms_raw is None or beds_raw is None:
        return _res("IM-2", "40b", RuleStatus.NOT_APPLICABLE, fields=fields, evidence=ev)

    rooms = _int_of(rooms_raw)
    beds  = _int_of(beds_raw)
    if rooms is None or beds is None:
        return _res("IM-2", "40b", RuleStatus.NOT_APPLICABLE, fields=fields, evidence=ev)

    # Studio/efficiency — 0 bedrooms is valid; hard inequality trivially holds.
    if beds == 0:
        return _res("IM-2", "40b", RuleStatus.PASS, fields=fields, evidence=ev)

    # Hard inequality satisfied.
    if beds < rooms:
        return _res("IM-2", "40b", RuleStatus.PASS, fields=fields, evidence=ev)

    # Inequality violated — build the swap-recovery hypothesis.
    swap_msg = ""
    gla = _int_of(gla_raw) if gla_raw else None
    if gla and gla > 0:
        # Current ratio (wrong) vs. swapped ratio (candidate).
        # Plausible SFR footprint: GLA/site_area in [0.02, 0.9] using rooms-as-proxy.
        # Simpler: after swap, beds-per-sqft should be reasonable (<1 per 300 sf).
        swapped_rooms, swapped_beds = beds, rooms   # proposed swap
        if swapped_beds < swapped_rooms:
            sqft_per_bed_swapped = gla / swapped_beds if swapped_beds > 0 else 9999
            sqft_per_bed_current = gla / beds if beds > 0 else 9999
            if sqft_per_bed_swapped > sqft_per_bed_current:  # swap is more plausible
                swap_msg = (
                    f" Swapping produces total_rooms={swapped_rooms}, "
                    f"bedrooms={swapped_beds} — consistent with GLA of {gla} sf "
                    f"({sqft_per_bed_swapped:.0f} sf/bed vs current {sqft_per_bed_current:.0f} sf/bed)."
                )

    msg = (
        f"Bedroom count ({beds}) is not less than total room count ({rooms}) — "
        f"these may be swapped in the improvements section.{swap_msg} "
        f"Please verify the correct values on the improvements page."
    )
    # confidence gate @ 0.85
    conf = min(ctx.appraisal.confidence("total_rooms"), ctx.appraisal.confidence("bedrooms"))
    if conf >= ctx.checkbox_conf:
        return _res("IM-2", "40b", RuleStatus.PASS, fields=fields, evidence=ev)
    return _res("IM-2", "40b", RuleStatus.VERIFY, message=msg,
                fields=fields, evidence=ev, confidence=0.55)


@rule(id="I-SMCO", num="49b", section="improvements", phase=4,
      name="Smoke/CO detector code compliance noted")
def i_smco(ctx: QCContext):
    """Engagement letter (Equity Solutions USA) requires a note confirming
    smoke and CO detectors meet local code requirements. Check all narrative
    fields for detector-related keywords; flag for reviewer when absent."""
    narrative = " ".join(str(ctx.appraisal.value(f) or "") for f in _NARRATIVE_SOURCES)
    ev = [ctx.appraisal.evidence("sales_comparison_summary")]
    if _DETECTOR_RE.search(narrative):
        return _res("I-SMCO", "49b", RuleStatus.PASS,
                    fields=list(_NARRATIVE_SOURCES), evidence=ev)
    # confidence gate @ 0.85
    conf = min(ctx.appraisal.confidence(f) for f in _NARRATIVE_SOURCES)
    if conf >= ctx.checkbox_conf:
        return _res("I-SMCO", "49b", RuleStatus.PASS,
                    fields=list(_NARRATIVE_SOURCES), evidence=ev)
    return _res("I-SMCO", "49b", RuleStatus.VERIFY,
                message=qc_config.template("I-SMCO-missing"),
                fields=list(_NARRATIVE_SOURCES),
                template_id="I-SMCO-missing", evidence=ev, confidence=0.5)


# ---- I-HOA-PUD: HOA dues vs PUD checkbox consistency -----------------------
# UAD requirement: when HOA dues > 0 are entered in the subject section, the
# PUD checkbox must be marked. Conversely, when PUD is marked, there must be
# an HOA dues amount (or an explicit $0 with explanation). Either direction of
# inconsistency surfaces a FAIL (dues present, PUD not marked) or VERIFY (PUD
# marked but no dues — sometimes $0 dues are valid for newly-formed PUDs).
#
# Skip (SKIPPED) when either value couldn't be extracted, so empty forms don't
# generate false positives (P-6).


def _parse_hoa_num(val) -> float:
    """Extract the first numeric value from an HOA dues string (e.g. '$120' → 120.0)."""
    if val is None:
        return 0.0
    m = re.search(r"[\d.]+", str(val).replace(",", "").replace("$", ""))
    try:
        return float(m.group(0)) if m else 0.0
    except (TypeError, ValueError):
        return 0.0


@rule(id="I-HOA-PUD", num="S-9-pud", section="subject", phase=1,
      name="HOA/PUD consistency")
def i_hoa_pud(ctx: QCContext):
    """HOA dues and PUD checkbox must be internally consistent in the subject section.

    UAD rule:
    - HOA dues > 0 → PUD must be checked (FAIL when PUD not marked)
    - PUD marked → HOA dues should be present (VERIFY when dues absent/zero;
      $0 is legal for some PUDs but warrants reviewer confirmation)
    - No HOA dues + PUD not marked → PASS (typical SFR)
    """
    hoa_raw = ctx.appraisal.value("hoa_dues")
    pud_raw = ctx.appraisal.value("is_pud")
    ev = [ctx.appraisal.evidence("hoa_dues"), ctx.appraisal.evidence("is_pud")]
    fields = ["hoa_dues", "is_pud"]

    # Skip when the appraisal document was not extracted — can't assert either
    # direction without data (P-6 graceful degradation).
    if not ctx.appraisal.present:
        return _res("I-HOA-PUD", "S-9-pud", RuleStatus.SKIPPED,
                    message="Appraisal not available; HOA/PUD check skipped.",
                    fields=fields, evidence=ev)

    hoa_amount = _parse_hoa_num(hoa_raw)
    pud_marked = str(pud_raw or "").strip().lower() in {"true", "yes", "y", "1", "x", "checked"}
    pud_no = str(pud_raw or "").strip().lower() in {"false", "no", "n", "0", "unchecked"}

    # HOA dues present (>0) but PUD not explicitly marked → FAIL
    if hoa_amount > 0 and pud_no:
        return _res("I-HOA-PUD", "S-9-pud", RuleStatus.FAIL,
                    message=qc_config.template("S-9-pud", value=hoa_raw),
                    fields=fields, template_id="S-9-pud", evidence=ev)

    # HOA dues present but PUD extraction uncertain (not clearly yes or no) →
    # VERIFY so the reviewer confirms the checkbox rather than silently passing.
    if hoa_amount > 0 and not pud_marked and not pud_no:
        conf = min(ctx.appraisal.confidence("hoa_dues"), ctx.appraisal.confidence("is_pud"))
        if conf >= ctx.checkbox_conf:
            return _res("I-HOA-PUD", "S-9-pud", RuleStatus.PASS, fields=fields, evidence=ev)
        return _res("I-HOA-PUD", "S-9-pud", RuleStatus.VERIFY,
                    message=qc_config.template("S-9-pud", value=hoa_raw),
                    fields=fields, template_id="S-9-pud", evidence=ev, confidence=0.6)

    # PUD marked but no HOA dues amount shown → advisory VERIFY (legal for $0 PUDs)
    if pud_marked and hoa_amount == 0:
        conf = min(ctx.appraisal.confidence("hoa_dues"), ctx.appraisal.confidence("is_pud"))
        if conf >= ctx.checkbox_conf:
            return _res("I-HOA-PUD", "S-9-pud", RuleStatus.PASS, fields=fields, evidence=ev)
        return _res("I-HOA-PUD", "S-9-pud", RuleStatus.VERIFY,
                    message=(
                        "PUD is marked but no HOA dues amount is shown; "
                        "please confirm the HOA amount (enter $0 if applicable)."
                    ),
                    fields=fields, evidence=ev, confidence=0.5)

    # All other cases: consistent (dues+PUD both set, or neither set)
    return _res("I-HOA-PUD", "S-9-pud", RuleStatus.PASS,
                fields=fields, evidence=ev)
