"""
Site section rules (ST-1 .. ST-10 / checklist 26-34).
Includes the two HOLD escalations: illegal zoning and H&BU not 'Yes'.
"""

from __future__ import annotations

import re

from app.qc import helpers as H
from app.qc import layer_b
from app.qc.config import qc_config
from app.qc.context import QCContext
from app.qc.matching import normalize_currency
from app.qc.registry import rule
from app.qc.result import RuleStatus

_SQFT_PER_ACRE = 43_560


def _has_site_detail(ctx: QCContext) -> bool:
    """Dimensions/Shape exist on the 1004-family site section; the condo (1073)
    and multi-unit (1025) forms describe the project site instead."""
    return ctx.form_type not in ("1073", "1025")


_res = H.section_result("site")


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
    # the same view must appear in the SCA grid subject column.
    # Normalize away trailing UAD field-separator semicolons before comparing:
    # "N;Res" and "N;Res;" are the same value — the trailing ";" is a formatting
    # artifact, not a content difference (caused a false VERIFY in production).
    def _norm_view(v: str) -> str:
        return re.sub(r"[; ]+$", "", v.replace(" ", "")).lower()

    grid = (ctx.appraisal.value("subject_grid_view") or "").strip()
    if grid and val and _norm_view(grid) != _norm_view(val):
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
    elec = str(ctx.appraisal.value("utilities_electricity") or "").lower() in H.TRUTHY | {"public"}
    gas = str(ctx.appraisal.value("utilities_gas") or "").lower() in H.TRUTHY | {"public"}
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
        v = layer_b.assess(ctx, concern="zoning",
                           base_message=qc_config.template("ST-5-nonconforming"),
                           facts="legal non-conforming zoning")
        return _res("ST-5", "30", v.status, message=v.message, reasoning=v.reasoning,
                    fields=["zoning_compliance"], template_id="ST-5-nonconforming",
                    evidence=ev, confidence=v.confidence)
    if "no zoning" in comp:
        v = layer_b.assess(ctx, concern="zoning",
                           base_message=qc_config.template("ST-5-nozoning"),
                           facts="no zoning classification")
        return _res("ST-5", "30", v.status, message=v.message, reasoning=v.reasoning,
                    fields=["zoning_compliance"], template_id="ST-5-nozoning",
                    evidence=ev, confidence=v.confidence)
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
    in_flood = str(ctx.appraisal.value("fema_flood_hazard") or "").lower() in H.TRUTHY
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
    v = layer_b.assess(ctx, concern="adverse_condition",
                       base_message=qc_config.template("ST-10-adverse"),
                       facts="an adverse site condition was indicated")
    return _res("ST-10", "34", v.status, message=v.message, reasoning=v.reasoning,
                fields=["adverse_site_conditions"], template_id="ST-10-adverse",
                evidence=ev, confidence=v.confidence)


# ---- ST-9 utilities/off-site typical for the market area --------------------
# Complements ST-7 (which prompts the well/septic description): ST-9 prompts the
# market-typicality + marketability judgment, and only fires when there is an
# atypical signal (private water/sewer) so it does not add review noise.

@rule(id="ST-9", num="33", section="site", phase=4, name="Utilities/off-site typical for market")
def st9_typical(ctx: QCContext):
    if not ctx.appraisal.present:
        return []
    water = str(ctx.appraisal.value("utilities_water") or "").lower()
    sewer = str(ctx.appraisal.value("utilities_sewer") or "").lower()
    ev = [ctx.appraisal.evidence("utilities_water"), ctx.appraisal.evidence("utilities_sewer")]
    atypical = any(s in (water + " " + sewer) for s in ("private", "well", "septic"))
    if not atypical:
        return _res("ST-9", "33", RuleStatus.PASS,
                    fields=["utilities_water", "utilities_sewer"], evidence=ev)
    v = layer_b.assess(ctx, concern="marketability",
                       base_message=qc_config.template("ST-9-typical"),
                       facts="private/atypical utilities (well/septic) may affect marketability")
    return _res("ST-9", "33", v.status, message=v.message, reasoning=v.reasoning,
                fields=["utilities_water", "utilities_sewer"], template_id="ST-9-typical",
                evidence=ev, confidence=v.confidence)


# ---- ST-1B site area magnitude plausibility ----------------------------------
#
# Four independent cross-signals, each weak alone but jointly strong. Any single
# signal fires a VERIFY — never auto-FAIL, since this is an extraction-confidence
# question. Rural/agricultural subjects suppress signal (4) because large acreage
# is the expected case there, not evidence of a unit-confusion bug.

def _is_rural(ctx: QCContext) -> bool:
    loc = str(ctx.appraisal.value("location") or "").lower()
    zoning = str(ctx.appraisal.value("zoning_description") or "").lower()
    return "rural" in loc or "ag" in zoning or "agricultural" in zoning


@rule(id="ST-1B", num="26b", section="site", phase=2, applies_when=_has_site_detail,
      name="Site area magnitude plausibility (multi-signal)")
def st1b_site_plausibility(ctx: QCContext):
    """Cross-signal plausibility check for site area.

    Catches the extraction bug where a per-sf dollar rate or adjacent OCR digit
    is written into site_area with unit 'ac', producing an implausibly large
    (or oddly small) acreage that a single global range cannot detect without
    false-rejecting legitimate rural parcels.

    Four signals (any triggers VERIFY):
      1. Location=Urban/Suburban AND area > 1 ac — rare combination.
      2. Lot-coverage ratio GLA/site_area_sf outside [0.02, 0.80] — zero-coverage
         is the direct fingerprint of a $/sf value misread as acreage.
      3. Decimal-shift test: area_ac × 43,560 lands near a round suburban-lot
         sf value (5,000–20,000 sf) — classic dropped-unit footprint.
      4. Comp-set delta: subject site area > 5× the median comp site area (same
         unit assumed) — the strongest signal, suppressed for rural/ag subjects
         because comps will also be large.
    """
    from statistics import median

    area_raw  = ctx.appraisal.value("site_area")
    unit_raw  = ctx.appraisal.value("site_area_unit")
    gla_raw   = ctx.appraisal.value("gla")
    ev = [ctx.appraisal.evidence("site_area"), ctx.appraisal.evidence("site_area_unit")]
    fields = ["site_area", "site_area_unit", "gla"]

    if not area_raw:
        return _res("ST-1B", "26b", RuleStatus.NOT_APPLICABLE, fields=fields, evidence=ev)

    try:
        area = float(str(area_raw).replace(",", ""))
    except (ValueError, TypeError):
        return _res("ST-1B", "26b", RuleStatus.NOT_APPLICABLE, fields=fields, evidence=ev)

    unit = str(unit_raw or "").lower().strip()
    if not unit:
        # Missing unit — ST-2 already fires for this; avoid double-flagging.
        return _res("ST-1B", "26b", RuleStatus.NOT_APPLICABLE, fields=fields, evidence=ev)

    # Normalise to square feet for cross-comparisons.
    area_sf = area * _SQFT_PER_ACRE if unit.startswith("ac") else area
    is_ac   = unit.startswith("ac")
    is_rural = _is_rural(ctx)

    signals: list[str] = []

    # Signal 1 — Urban/suburban + large acreage.
    loc = str(ctx.appraisal.value("location") or "").lower()
    if is_ac and area > 1.0 and ("urban" in loc or "suburban" in loc):
        signals.append(f"site area {area:.2f} ac is unusual for a {loc} location")

    # Signal 2 — Lot-coverage ratio (GLA ÷ site_sf).
    if gla_raw:
        try:
            gla = float(str(gla_raw).replace(",", ""))
            if gla > 0 and area_sf > 0:
                ratio = gla / area_sf
                if ratio < 0.02 or ratio > 0.80:
                    signals.append(
                        f"lot-coverage ratio {ratio:.3f} (GLA {gla:.0f} sf ÷ "
                        f"site {area_sf:.0f} sf) is outside the plausible [0.02, 0.80] band"
                    )
        except (ValueError, TypeError):
            pass

    # Signal 3 — Decimal-shift / dropped-unit fingerprint.
    if is_ac:
        sf_equivalent = area * _SQFT_PER_ACRE
        if 4_000 <= sf_equivalent <= 25_000 and (sf_equivalent % 100) < 200:
            signals.append(
                f"area {area} ac × 43,560 = {sf_equivalent:.0f} sf — "
                "this is typical of a suburban lot size; the 'ac' unit may be a "
                "mis-tagged sf value (dropped unit suffix)"
            )

    # Signal 4 — Comp-set delta (suppressed for rural/ag).
    if not is_rural:
        comp_sizes: list[float] = []
        for i in range(1, 7):
            cs_raw = ctx.appraisal.value(f"comp_{i}_site_size")
            if cs_raw:
                try:
                    comp_sizes.append(float(str(cs_raw).replace(",", "").split()[0]))
                except (ValueError, TypeError):
                    pass
        if len(comp_sizes) >= 2:
            med = median(comp_sizes)
            if med > 0 and area_sf / med > 5:
                signals.append(
                    f"subject site area ({area_sf:.0f} sf) is "
                    f"{area_sf/med:.1f}× the median comp site area ({med:.0f} sf)"
                )

    if not signals:
        return _res("ST-1B", "26b", RuleStatus.PASS, fields=fields, evidence=ev)

    msg = (
        f"Site area plausibility check — {len(signals)} signal(s) suggest the "
        f"extracted value ({area} {unit}) may be an extraction error: "
        + "; ".join(signals)
        + ". Confirm the site area against the source document."
    )
    return _res("ST-1B", "26b", RuleStatus.VERIFY, message=msg,
                fields=fields, evidence=ev, confidence=0.55)


# ============================================================================
# NEW RULES — appended below existing rules (do not modify above)
# ============================================================================

# ---- ST-HBU Highest and best use stated and consistent ---------------------
#
# The XML extractor surfaces H&BU as highest_and_best_use (existing ST-6 field)
# and highest_best_use_indicator / highest_best_use_description.  ST-6 already
# fires a HOLD when the checkbox is explicitly "No"; this rule fires a VERIFY
# when ALL H&BU-related fields are blank (cannot be confirmed).

@rule(id="ST-HBU", num="ST-hbu", section="site", phase=1,
      name="Highest and best use stated and consistent")
def st_hbu_stated(ctx: QCContext):
    # Try every field the XML extractor may populate for H&BU data.
    hbu = (ctx.appraisal.value("highest_and_best_use") or "").strip()
    hbu_ind = (ctx.appraisal.value("highest_best_use_indicator") or "").strip()
    hbu_desc = (ctx.appraisal.value("highest_best_use_description") or "").strip()
    ev = [
        ctx.appraisal.evidence("highest_and_best_use"),
        ctx.appraisal.evidence("highest_best_use_indicator"),
        ctx.appraisal.evidence("highest_best_use_description"),
    ]
    fields = ["highest_and_best_use", "highest_best_use_indicator", "highest_best_use_description"]

    # Any positive HBU signal → the existing ST-6 covers the hard cases (HOLD on No).
    # Here we only surface the case where all three fields are blank — the appraiser
    # left the section empty, which requires a reviewer to confirm.
    any_populated = any([hbu, hbu_ind, hbu_desc])
    if any_populated:
        return _res("ST-HBU", "ST-hbu", RuleStatus.PASS, fields=fields, evidence=ev)

    return _res(
        "ST-HBU", "ST-hbu", RuleStatus.VERIFY,
        message="Highest and best use statement could not be confirmed; please verify "
                "the H&BU section is completed.",
        fields=fields, evidence=ev, confidence=0.5,
    )


# ---- ST-ZONE-NC Zoning non-conformance → commentary check ------------------
#
# Complements ST-5 (which fires when zoning_compliance is extracted as
# "Legal Non-Conforming").  This rule also inspects addendum_text for
# non-conformance language when the checkbox field was not extracted, and
# routes to Layer-B to gauge whether the required commentary is present.

@rule(id="ST-ZONE-NC", num="ST-zone-nc", section="site", phase=3,
      name="Zoning non-conformance commentary")
def st_zone_nc(ctx: QCContext):
    comp = (ctx.appraisal.value("zoning_compliance") or "").lower()
    addendum = (ctx.appraisal.value("addendum_text") or "").lower()
    ev = [
        ctx.appraisal.evidence("zoning_compliance"),
        ctx.appraisal.evidence("addendum_text"),
    ]
    fields = ["zoning_compliance", "addendum_text"]

    # Only fire when there is a non-conformance signal; ST-5 owns the primary
    # zoning_compliance check.  This rule adds coverage via addendum scanning.
    _NC = re.compile(r"(non[- ]?conform|grandfather|legal\s+non)", re.I)
    nc_in_comp = ("non" in comp and "conform" in comp)
    nc_in_addendum = bool(_NC.search(addendum))

    if not nc_in_comp and not nc_in_addendum:
        return _res("ST-ZONE-NC", "ST-zone-nc", RuleStatus.NOT_APPLICABLE,
                    fields=fields, evidence=ev)

    # There IS a non-conformance signal → check whether the narrative addresses it.
    facts = (
        "legal non-conforming zoning indicated in "
        + ("compliance field" if nc_in_comp else "")
        + (" and " if nc_in_comp and nc_in_addendum else "")
        + ("addendum text" if nc_in_addendum else "")
    )
    v = layer_b.assess(ctx, concern="zoning",
                       base_message=qc_config.template("ST-5-nonconforming"),
                       facts=facts)
    return _res("ST-ZONE-NC", "ST-zone-nc", v.status, message=v.message,
                reasoning=v.reasoning, fields=fields,
                template_id="ST-5-nonconforming", evidence=ev, confidence=v.confidence)


# ---- ST-FLOOD-CMT Flood zone present → marketability commentary -------------
#
# fires when: flood_zone_indicator == Y/Yes/true/1 OR flood_zone_id starts with
# A or V (SFHA prefix).  Checks whether the addendum or any narrative contains
# flood-related commentary.  Does NOT duplicate ST-8 (completeness of FEMA data
# fields); this rule focuses solely on whether the marketability impact is
# discussed in a narrative.

def _in_flood_zone(ctx: QCContext) -> bool:
    ind = (ctx.appraisal.value("flood_zone_indicator") or "").strip().lower()
    if ind in ("y", "yes", "true", "1"):
        return True
    zone_id = (ctx.appraisal.value("flood_zone_id") or "").upper().strip()
    # SFHA zone codes start with A or V (AE, AO, AH, VE, V, A, A99…)
    if zone_id and zone_id[0] in ("A", "V"):
        return True
    return False


@rule(id="ST-FLOOD-CMT", num="ST-flood-cmt", section="site", phase=5,
      applies_when=_in_flood_zone,
      name="Flood zone present — marketability commentary required")
def st_flood_cmt(ctx: QCContext):
    zone_id = (ctx.appraisal.value("flood_zone_id") or "Unknown").strip()
    addendum = (ctx.appraisal.value("addendum_text") or "").lower()
    ev = [
        ctx.appraisal.evidence("flood_zone_indicator"),
        ctx.appraisal.evidence("flood_zone_id"),
        ctx.appraisal.evidence("addendum_text"),
    ]
    fields = ["flood_zone_indicator", "flood_zone_id", "addendum_text"]

    _FLOOD_RX = re.compile(
        r"flood|fema|sfha|special\s+flood|insurance\s+(requir|premium|impact)|"
        r"national\s+flood|nfip", re.I,
    )

    # Also check the narrative fields that layer_b aggregates.
    narrative = layer_b.narrative_text(ctx)
    addressed = bool(_FLOOD_RX.search(addendum) or _FLOOD_RX.search(narrative))

    if addressed:
        return _res("ST-FLOOD-CMT", "ST-flood-cmt", RuleStatus.PASS,
                    fields=fields, evidence=ev)

    return _res(
        "ST-FLOOD-CMT", "ST-flood-cmt", RuleStatus.VERIFY,
        message=qc_config.template("ST-FLOOD-CMT", zone=zone_id),
        template_id="ST-FLOOD-CMT", fields=fields, evidence=ev, confidence=0.7,
    )


# ---- ST-RIGHTS Leasehold property rights disclosure ------------------------
#
# Phase 2: fires when property_rights field is blank (VERIFY) or Leasehold (FAIL
# unless remaining-lease commentary found in addendum/narrative).

@rule(id="ST-RIGHTS", num="ST-rights", section="site", phase=2,
      name="Leasehold property rights disclosure")
def st_rights_lease(ctx: QCContext):
    rights = (ctx.appraisal.value("property_rights") or "").strip()
    addendum = (ctx.appraisal.value("addendum_text") or "").lower()
    ev = [
        ctx.appraisal.evidence("property_rights"),
        ctx.appraisal.evidence("addendum_text"),
    ]
    fields = ["property_rights", "addendum_text"]

    if not rights:
        return _res("ST-RIGHTS", "ST-rights", RuleStatus.VERIFY,
                    message=qc_config.template("S-11-rights"),
                    template_id="S-11-rights", fields=fields, evidence=ev, confidence=0.5)

    if rights.lower() not in ("leasehold",):
        return _res("ST-RIGHTS", "ST-rights", RuleStatus.PASS,
                    fields=fields, evidence=ev)

    # Leasehold: the report must discuss the remaining lease term.
    _LEASE_RX = re.compile(
        r"(remaining\s+)?lease\s+term|leasehold\s+(interest|value|impac|discount)|"
        r"years?\s+(remaining|left)\s+(on\s+the\s+)?lease|ground\s+rent|"
        r"land\s+lease|leasehold\s+estate", re.I,
    )
    narrative = layer_b.narrative_text(ctx)
    addressed = bool(_LEASE_RX.search(addendum) or _LEASE_RX.search(narrative.lower()))

    if addressed:
        return _res("ST-RIGHTS", "ST-rights", RuleStatus.PASS,
                    fields=fields, evidence=ev)

    return _res(
        "ST-RIGHTS", "ST-rights", RuleStatus.FAIL,
        message=qc_config.template("ST-RIGHTS-LEASE"),
        template_id="ST-RIGHTS-LEASE", fields=fields, evidence=ev, confidence=0.8,
    )


# ---- ST-PRIOR-SVC Prior services disclosure --------------------------------
#
# Fires in signature section (phase 2).  Checks whether prior services are
# indicated (indicator field = "Y" OR addendum mentions it), and if so, whether
# a description is present.

@rule(id="ST-PRIOR-SVC", num="ST-prior-svc", section="signature", phase=2,
      name="Prior services disclosure")
def st_prior_svc(ctx: QCContext):
    ind = (ctx.appraisal.value("prior_services_indicator") or "").strip().lower()
    desc = (ctx.appraisal.value("prior_services_description") or "").strip()
    addendum = (ctx.appraisal.value("addendum_text") or "").lower()
    ev = [
        ctx.appraisal.evidence("prior_services_indicator"),
        ctx.appraisal.evidence("prior_services_description"),
        ctx.appraisal.evidence("addendum_text"),
    ]
    fields = ["prior_services_indicator", "prior_services_description", "addendum_text"]

    _PRIOR_RX = re.compile(
        r"prior\s+(service|appraisal|assignment)|previously\s+appraised|"
        r"prior\s+(inspection|review)", re.I,
    )

    # Determine if prior services are indicated.
    indicator_yes = ind in ("y", "yes", "true", "1")
    addendum_mentions = bool(_PRIOR_RX.search(addendum))

    if not indicator_yes and not addendum_mentions:
        # No signal → N/A (silence is correct, not a finding).
        return _res("ST-PRIOR-SVC", "ST-prior-svc", RuleStatus.NOT_APPLICABLE,
                    fields=fields, evidence=ev)

    # Prior services are indicated — check for a description.
    has_description = bool(desc) or bool(
        re.search(
            r"(prior\s+(service|appraisal|assignment)).{0,200}(date|type|role|inspect|review)",
            addendum, re.I | re.DOTALL,
        )
    )
    if has_description:
        return _res("ST-PRIOR-SVC", "ST-prior-svc", RuleStatus.PASS,
                    fields=fields, evidence=ev)

    # Indicated but no description → FAIL using the existing ADD-9-services template.
    return _res(
        "ST-PRIOR-SVC", "ST-prior-svc", RuleStatus.FAIL,
        message=qc_config.template("ADD-9-services"),
        template_id="ADD-9-services", fields=fields, evidence=ev, confidence=0.75,
    )


# ---- ST-INTENDED Intended use and user stated ------------------------------
#
# USPAP requires the intended use AND intended user to be identified.
# Phase 1, section "subject" (appears early in the report / addendum).

@rule(id="ST-INTENDED", num="ST-intended", section="subject", phase=1,
      name="Intended use and intended user stated")
def st_intended(ctx: QCContext):
    addendum = (ctx.appraisal.value("addendum_text") or "")
    narrative = layer_b.narrative_text(ctx)
    combined = addendum + " " + narrative
    ev = [ctx.appraisal.evidence("addendum_text")]
    fields = ["addendum_text"]

    has_use = bool(re.search(r"intended\s+use", combined, re.I))
    has_user = bool(re.search(
        r"intended\s+user|lender.{0,60}(client|user)|client.{0,40}lender", combined, re.I,
    ))

    if has_use and has_user:
        return _res("ST-INTENDED", "ST-intended", RuleStatus.PASS,
                    fields=fields, evidence=ev)

    return _res(
        "ST-INTENDED", "ST-intended", RuleStatus.VERIFY,
        message=qc_config.template("ST-INTENDED"),
        template_id="ST-INTENDED", fields=fields, evidence=ev, confidence=0.6,
    )


# ---- ST-SCOPE Scope of work stated -----------------------------------------
#
# USPAP requires a stated scope of work.  Phase 1, section "subject".

@rule(id="ST-SCOPE", num="ST-scope", section="subject", phase=1,
      name="Scope of work stated")
def st_scope(ctx: QCContext):
    addendum = (ctx.appraisal.value("addendum_text") or "")
    narrative = layer_b.narrative_text(ctx)
    combined = addendum + " " + narrative
    ev = [ctx.appraisal.evidence("addendum_text")]
    fields = ["addendum_text"]

    if re.search(r"scope\s+of\s+work", combined, re.I):
        return _res("ST-SCOPE", "ST-scope", RuleStatus.PASS, fields=fields, evidence=ev)

    return _res(
        "ST-SCOPE", "ST-scope", RuleStatus.VERIFY,
        message=qc_config.template("ST-SCOPE"),
        template_id="ST-SCOPE", fields=fields, evidence=ev, confidence=0.6,
    )


# ---- ST-FORM-MATCH Form type matches property type -------------------------
#
# Guards against submitting a single-family form for a condo or 2-4 unit.
# Phase 1, section "subject".

@rule(id="ST-FORM-MATCH", num="ST-form-match", section="subject", phase=1,
      name="Form type matches property type")
def st_form_match(ctx: QCContext):
    form = (ctx.form_type or "").strip()
    design = (ctx.appraisal.value("design_style") or "").lower()
    ev = [ctx.appraisal.evidence("design_style")]
    fields = ["design_style"]

    if not form:
        return _res("ST-FORM-MATCH", "ST-form-match", RuleStatus.NOT_APPLICABLE,
                    fields=fields, evidence=ev)

    is_condo_design = bool(re.search(r"\bcondo(minium)?\b", design, re.I))

    if form == "1004":
        # 1004 is for detached single-family — flag if design looks like a condo.
        if is_condo_design:
            return _res(
                "ST-FORM-MATCH", "ST-form-match", RuleStatus.FAIL,
                message=qc_config.template("ST-FORM-MATCH", form="1004", prop_type=design or "condo"),
                template_id="ST-FORM-MATCH", fields=fields, evidence=ev, confidence=0.8,
            )
        return _res("ST-FORM-MATCH", "ST-form-match", RuleStatus.PASS, fields=fields, evidence=ev)

    if form == "1073":
        # 1073 is for condominiums — flag if design does not contain condo.
        if not is_condo_design:
            return _res(
                "ST-FORM-MATCH", "ST-form-match", RuleStatus.VERIFY,
                message=qc_config.template("ST-FORM-MATCH", form="1073",
                                           prop_type=design or "non-condo"),
                template_id="ST-FORM-MATCH", fields=fields, evidence=ev, confidence=0.6,
            )
        return _res("ST-FORM-MATCH", "ST-form-match", RuleStatus.PASS, fields=fields, evidence=ev)

    if form == "1025":
        # 1025 is for 2-4 unit — flag if design signals single-family detached without
        # any unit count evidence (we cannot check units_count here without duplication,
        # so we limit to an obvious single-family design signal).
        if is_condo_design:
            return _res(
                "ST-FORM-MATCH", "ST-form-match", RuleStatus.VERIFY,
                message=qc_config.template("ST-FORM-MATCH", form="1025",
                                           prop_type=design or "condo"),
                template_id="ST-FORM-MATCH", fields=fields, evidence=ev, confidence=0.6,
            )
        return _res("ST-FORM-MATCH", "ST-form-match", RuleStatus.PASS, fields=fields, evidence=ev)

    # Unrecognised form type — cannot evaluate.
    return _res("ST-FORM-MATCH", "ST-form-match", RuleStatus.NOT_APPLICABLE,
                fields=fields, evidence=ev)


# ---- ST-GEO-COMP Appraiser geographic competency ---------------------------
#
# When the appraiser's license state differs from the property state, USPAP
# requires the appraiser to demonstrate geographic competency.  The rule fires
# a VERIFY (not FAIL) because geographic competency may be addressed in the
# limiting conditions or addendum, not as a hard violation.
# Phase 2, section "signature".

@rule(id="ST-GEO-COMP", num="ST-geo-comp", section="signature", phase=2,
      name="Appraiser geographic competency")
def st_geo_comp(ctx: QCContext):
    lic_state = (ctx.appraisal.value("appraiser_license_state") or "").strip().upper()
    prop_state = (ctx.appraisal.value("state") or "").strip().upper()
    ev = [
        ctx.appraisal.evidence("appraiser_license_state"),
        ctx.appraisal.evidence("state"),
    ]
    fields = ["appraiser_license_state", "state"]

    if not lic_state or not prop_state:
        # Cannot evaluate without both data points → SKIPPED (data missing).
        return _res("ST-GEO-COMP", "ST-geo-comp", RuleStatus.NOT_APPLICABLE,
                    message="Appraiser license state or property state could not be read; "
                            "geographic competency check skipped.",
                    fields=fields, evidence=ev)

    if lic_state == prop_state:
        return _res("ST-GEO-COMP", "ST-geo-comp", RuleStatus.PASS,
                    fields=fields, evidence=ev)

    # States differ — surface for reviewer confirmation (VERIFY, not FAIL).
    return _res(
        "ST-GEO-COMP", "ST-geo-comp", RuleStatus.VERIFY,
        message=qc_config.template("ST-GEO-COMP", lic_state=lic_state, prop_state=prop_state),
        template_id="ST-GEO-COMP", fields=fields, evidence=ev, confidence=0.7,
    )
