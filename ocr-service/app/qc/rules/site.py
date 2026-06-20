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
