"""
Comparable Grid supplemental QC rules (CG-* series).

These rules complement the sales_comparison.py rules (SCA-*) with deeper
per-comparable checks: distance thresholds by area type, GLA bracketing,
net-adjustment directional bias, concession-adjustment direction, condition-
adjustment consistency, time-adjustment rate consistency, non-arms-length
sale detection, and comp prior-sale rapid-appreciation flags.

All rules:
  - are gated on ctx.has_sca_grid
  - return SKIPPED (not VERIFY, not PASS) when required fields are missing
  - never call the LLM for arithmetic decisions (judgment calls use layer_b.assess)
  - read all thresholds from qc_config.semantic() (P-4)
"""

from __future__ import annotations

import re
from typing import List, Optional

from app.qc import layer_b
from app.qc.config import qc_config
from app.qc.context import QCContext
from app.qc.registry import rule
from app.qc.result import RuleResult, RuleStatus

_MAX_COMPS = 9


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _comp_indices(ctx: QCContext) -> List[int]:
    """Return comp indices 1..N that have a sale_price (real comps, not blank slots)."""
    idx = []
    for i in range(1, _MAX_COMPS + 1):
        if ctx.appraisal.value(f"comp_{i}_sale_price"):
            idx.append(i)
    return idx


def _parse_num(val) -> Optional[float]:
    """Parse numeric string to float, return None if fails.

    Preserves a leading negative sign. Grid adjustment columns (net adjustment,
    financing/date-of-sale adjustment, condition adjustment) are signed — a comp
    adjusted DOWN toward the subject carries a negative value. The previous
    ``[\\d.]+`` pattern silently dropped the '-', so every adjustment read as
    positive and CG-NET-BIAS reported a false "all comps positive" directional
    bias (and CG-CONC-DIR mis-fired on correctly-negative concession adjustments).
    Normalises the UAD/typographic minus glyphs (‑ – −) to ASCII '-' first.
    """
    if val is None:
        return None
    s = (str(val).replace(",", "").replace("$", "")
         .replace("‐", "-").replace("‑", "-").replace("‒", "-")
         .replace("–", "-").replace("—", "-").replace("−", "-"))
    m = re.search(r"-?\d[\d.]*", s)
    try:
        return float(m.group(0)) if m else None
    except (ValueError, AttributeError):
        return None


def _parse_proximity_miles(prox_str) -> Optional[float]:
    """Extract distance in miles from proximity string like '1.48 miles NW'."""
    if not prox_str:
        return None
    m = re.search(r"([\d.]+)\s*miles?", str(prox_str), re.I)
    return float(m.group(1)) if m else None


def _parse_uad_date_ym(tok: str) -> Optional[tuple]:
    """Extract the sale date (s-token) from a UAD date string like 's05/26;c04/26'.
    Returns (year, month) as integers, 20xx for two-digit years. Returns None if
    neither s- nor c-token is parseable."""
    if not tok:
        return None
    m = re.search(r"s\s*(\d{1,2})/(\d{2,4})", tok or "", re.I)
    if not m:
        # Fallback: try c-token (contract/closed date)
        m = re.search(r"c\s*(\d{1,2})/(\d{2,4})", tok or "", re.I)
    if not m:
        return None
    mm, yy = int(m.group(1)), int(m.group(2))
    if yy < 100:
        yy += 2000
    return (yy, mm)


def _parse_full_date_ym(val) -> Optional[tuple]:
    """'02/09/2026' → (2026, 2) as (year, month). Two-digit years → 20xx."""
    m = re.search(r"(\d{1,2})/(\d{1,2})/(\d{2,4})", str(val or ""))
    if not m:
        return None
    mm, _dd, yy = int(m.group(1)), int(m.group(2)), int(m.group(3))
    if yy < 100:
        yy += 2000
    return (yy, mm)


def _months_between(earlier: tuple, later: tuple) -> int:
    """Compute months from earlier (year, month) to later (year, month).
    Returns a positive integer when later > earlier, negative when later < earlier."""
    return (later[0] - earlier[0]) * 12 + (later[1] - earlier[1])


def _effective_ym(ctx: QCContext) -> Optional[tuple]:
    """Return (year, month) for the appraisal effective date, or None."""
    import datetime as _dt
    s = str(ctx.appraisal.value("effective_date") or "").strip()
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%m-%d-%Y"):
        try:
            d = _dt.datetime.strptime(s, fmt)
            return (d.year, d.month)
        except ValueError:
            continue
    return None


# ---------------------------------------------------------------------------
# CG-DIST — Comp distance threshold by area type
# ---------------------------------------------------------------------------

@rule(id="CG-DIST", num="CG-dist", section="sales_comparison", phase=3,
      applies_when=lambda ctx: ctx.has_sca_grid,
      name="Comp distance threshold by area type")
def cg_dist_threshold(ctx: QCContext):
    """Flag comps whose distance to subject exceeds the typical threshold for the
    area type (Urban 1 mi / Suburban 5 mi / Rural 10 mi). Distance issues are
    judgment calls — confirmed violations route to layer_b for VERIFY."""
    location_type = str(ctx.appraisal.value("location_type") or "").strip().lower()
    # Read from PolicyProfile (sourced from amc_policies.yaml engagement-letter body).
    # Equity Solutions USA says: urban > 0.5 mi → comment; suburban > 1 mi → comment.
    # These are COMMENTARY TRIGGERS not hard limits — CG-DIST raises VERIFY if exceeded.
    # Order matters: test "suburban" BEFORE "urban" — the substring "urban" is
    # contained in "suburban", so a naive `"urban" in location_type` misclassifies
    # every Suburban property as Urban and applies the tighter urban threshold
    # (this false-flagged suburban comps at ~1.2 mi against a 1.0 mi urban trigger).
    if "suburban" in location_type:
        threshold = ctx.policy.distance_commentary_trigger_suburban_miles or \
                    float(qc_config.semantic("comp_distance_suburban_miles", 5.0))
        area_label = "Suburban"
    elif "rural" in location_type:
        threshold = ctx.policy.distance_commentary_trigger_rural_miles or \
                    float(qc_config.semantic("comp_distance_rural_miles", 10.0))
        area_label = "Rural"
    elif "urban" in location_type:
        threshold = ctx.policy.distance_commentary_trigger_urban_miles or \
                    float(qc_config.semantic("comp_distance_urban_miles", 1.0))
        area_label = "Urban"
    else:
        threshold = ctx.policy.distance_commentary_trigger_suburban_miles or \
                    float(qc_config.semantic("comp_distance_suburban_miles", 5.0))
        area_label = "Suburban"

    idx = _comp_indices(ctx)
    if not idx:
        return RuleResult(
            rule_id="CG-DIST", checklist_num="CG-dist", section="sales_comparison",
            status=RuleStatus.SKIPPED,
            message="No comparable sale prices found; distance check skipped.",
            fields_involved=["comp_N_sale_price"],
        )

    violations = []
    details_parts = []
    evidence = []
    for i in idx:
        prox_raw = ctx.appraisal.value(f"comp_{i}_proximity")
        ev = ctx.appraisal.evidence(f"comp_{i}_proximity")
        evidence.append(ev)
        if prox_raw is None:
            continue
        dist = _parse_proximity_miles(prox_raw)
        if dist is None:
            continue
        if dist > threshold:
            violations.append(str(i))
            details_parts.append(f"Comp {i}: {dist:.2f} mi")

    if not violations:
        ev_list = [ctx.appraisal.evidence(f"comp_{i}_proximity") for i in idx[:3]]
        return RuleResult(
            rule_id="CG-DIST", checklist_num="CG-dist", section="sales_comparison",
            status=RuleStatus.PASS,
            fields_involved=["comp_N_proximity", "location_type"],
            evidence=ev_list,
        )

    comps_str = ", ".join(violations)
    details_str = "; ".join(details_parts)
    base_message = qc_config.template(
        "CG-dist-exceed",
        comps=comps_str, area_type=area_label,
        threshold=threshold, details=details_str,
    )
    v = layer_b.assess(
        ctx, concern="comp_selection",
        base_message=base_message,
        facts=f"comp(s) {comps_str} exceed the {area_label.lower()} distance threshold of {threshold} miles",
    )
    return RuleResult(
        rule_id="CG-DIST", checklist_num="CG-dist", section="sales_comparison",
        status=v.status, message=v.message, reasoning=v.reasoning,
        fields_involved=["comp_N_proximity", "location_type"],
        template_id="CG-dist-exceed",
        evidence=evidence[:6],
        confidence=v.confidence,
    )


# ---------------------------------------------------------------------------
# CG-GLA-BRACKET — GLA bracketing check
# ---------------------------------------------------------------------------

@rule(id="CG-GLA-BRACKET", num="CG-gla-brk", section="sales_comparison", phase=3,
      applies_when=lambda ctx: ctx.has_sca_grid,
      name="Subject GLA bracketed by comp GLAs")
def cg_gla_bracket(ctx: QCContext):
    """Sound square-footage methodology requires at least one comp GLA < subject
    and at least one > subject. Uses SCA-26-gla template (already in templates.yaml).

    NOTE: SCA-26 in sales_comparison.py runs the identical bracketing check;
    CG-GLA-BRACKET groups it under the CG- rule set so reviewers see it in the
    comparable-grid section without duplicating logic."""
    # Subject GLA: prefer grid column, fall back to improvements section
    subj_raw = ctx.appraisal.value("subject_grid_gla") or ctx.appraisal.value("gla")
    subj_ev = [ctx.appraisal.evidence("subject_grid_gla"), ctx.appraisal.evidence("gla")]

    if subj_raw is None:
        return RuleResult(
            rule_id="CG-GLA-BRACKET", checklist_num="CG-gla-brk", section="sales_comparison",
            status=RuleStatus.SKIPPED,
            message="Subject GLA could not be read; GLA bracketing check skipped.",
            fields_involved=["subject_grid_gla", "gla"],
            evidence=subj_ev,
        )
    subj = _parse_num(subj_raw)
    if subj is None or subj <= 0:
        return RuleResult(
            rule_id="CG-GLA-BRACKET", checklist_num="CG-gla-brk", section="sales_comparison",
            status=RuleStatus.SKIPPED,
            message="Subject GLA value is not parseable; GLA bracketing check skipped.",
            fields_involved=["subject_grid_gla", "gla"],
            evidence=subj_ev,
        )

    idx = _comp_indices(ctx)
    comp_glas = []
    comp_evidences = []
    for i in idx:
        g = _parse_num(ctx.appraisal.value(f"comp_{i}_gla"))
        comp_evidences.append(ctx.appraisal.evidence(f"comp_{i}_gla"))
        if g is not None and g > 0:
            comp_glas.append(g)

    evidence = subj_ev + comp_evidences[:3]

    if len(comp_glas) < 2:
        return RuleResult(
            rule_id="CG-GLA-BRACKET", checklist_num="CG-gla-brk", section="sales_comparison",
            status=RuleStatus.SKIPPED,
            message="Fewer than 2 comparable GLAs available; GLA bracketing check skipped.",
            fields_involved=["subject_grid_gla", "comp_N_gla"],
            evidence=evidence,
        )

    has_below = any(g < subj for g in comp_glas)
    has_above = any(g > subj for g in comp_glas)
    if has_below and has_above:
        return RuleResult(
            rule_id="CG-GLA-BRACKET", checklist_num="CG-gla-brk", section="sales_comparison",
            status=RuleStatus.PASS,
            fields_involved=["subject_grid_gla", "comp_N_gla"],
            evidence=evidence,
        )

    lo, hi = int(min(comp_glas)), int(max(comp_glas))
    v = layer_b.assess(
        ctx, concern="comp_selection",
        base_message=qc_config.template("SCA-26-gla", subj=int(subj), lo=lo, hi=hi),
        facts=f"the subject GLA ({int(subj)} sf) is not bracketed by comp GLAs ({lo}-{hi} sf)",
    )
    return RuleResult(
        rule_id="CG-GLA-BRACKET", checklist_num="CG-gla-brk", section="sales_comparison",
        status=v.status, message=v.message, reasoning=v.reasoning,
        fields_involved=["subject_grid_gla", "comp_N_gla"],
        template_id="SCA-26-gla",
        evidence=evidence,
        confidence=v.confidence,
    )


# ---------------------------------------------------------------------------
# CG-NET-BIAS — Net adjustment directional bias
# ---------------------------------------------------------------------------

@rule(id="CG-NET-BIAS", num="CG-net-bias", section="sales_comparison", phase=3,
      applies_when=lambda ctx: ctx.has_sca_grid, severity="advisory",
      name="Net adjustment directional bias")
def cg_net_bias(ctx: QCContext):
    """When ALL comps' net adjustments are the same sign (all positive = comps
    adjusted up toward subject value, or all negative = comps adjusted down), a
    directional bias may indicate the comps do not bracket the subject.
    Requires >= 3 comps with readable net adjustment data."""
    idx = _comp_indices(ctx)
    nets = []
    evidence = []
    for i in idx:
        evidence.append(ctx.appraisal.evidence(f"comp_{i}_net_adjustment"))
        # Prefer the explicit UAD sign indicator (Y=positive, N=negative) — it is
        # authoritative and immune to the amount-parsing sign loss. Fall back to the
        # sign of the parsed amount only when the indicator wasn't extracted.
        pos = str(ctx.appraisal.value(f"comp_{i}_net_adj_positive") or "").strip().upper()
        if pos in ("Y", "N"):
            nets.append(1.0 if pos == "Y" else -1.0)
            continue
        val = _parse_num(ctx.appraisal.value(f"comp_{i}_net_adjustment"))
        if val is not None and val != 0:
            nets.append(val)

    if len(nets) < 3:
        return RuleResult(
            rule_id="CG-NET-BIAS", checklist_num="CG-net-bias", section="sales_comparison",
            status=RuleStatus.SKIPPED,
            message="Fewer than 3 comparable net adjustments readable; directional bias check skipped.",
            fields_involved=["comp_N_net_adjustment"],
            evidence=evidence,
        )

    all_positive = all(n > 0 for n in nets)
    all_negative = all(n < 0 for n in nets)

    if not (all_positive or all_negative):
        return RuleResult(
            rule_id="CG-NET-BIAS", checklist_num="CG-net-bias", section="sales_comparison",
            status=RuleStatus.PASS,
            fields_involved=["comp_N_net_adjustment"],
            evidence=evidence[:3],
        )

    direction = "positive" if all_positive else "negative"
    v = layer_b.assess(
        ctx, concern="comp_selection",
        base_message=qc_config.template("CG-net-bias", direction=direction),
        facts=f"all {len(nets)} comparable net adjustments are {direction}",
    )
    return RuleResult(
        rule_id="CG-NET-BIAS", checklist_num="CG-net-bias", section="sales_comparison",
        status=v.status, message=v.message, reasoning=v.reasoning,
        fields_involved=["comp_N_net_adjustment"],
        template_id="CG-net-bias",
        evidence=evidence[:3],
        confidence=v.confidence,
    )


# ---------------------------------------------------------------------------
# CG-CONC-DIR — Concession adjustment wrong direction
# ---------------------------------------------------------------------------

@rule(id="CG-CONC-DIR", num="CG-conc-dir", section="sales_comparison", phase=3,
      applies_when=lambda ctx: ctx.has_sca_grid,
      name="Concession adjustment wrong direction")
def cg_concession_direction(ctx: QCContext):
    """When a comp has a seller concession (not 'ArmLth', not blank), the financing
    adjustment must be NEGATIVE (concessions inflate the sale price; the adjustment
    corrects downward). A positive or zero financing adjustment → FAIL.

    Uses the existing SCA-7-conc template."""
    out = []
    idx = _comp_indices(ctx)
    any_checked = False

    for i in idx:
        concession = str(ctx.appraisal.value(f"comp_{i}_concessions") or "").strip()
        # ArmLth = arm's-length, no concession; blank = nothing disclosed → skip
        if not concession or concession.lower() in (
            "armlth", "arm's length", "arms length", "armlgth",
        ):
            continue
        # A dollar concession or distressed concession code is noted
        any_checked = True
        fin_raw = ctx.appraisal.value(f"comp_{i}_financing_adj")
        fin_adj = _parse_num(fin_raw)
        ev = [
            ctx.appraisal.evidence(f"comp_{i}_sale_price"),
            ctx.appraisal.evidence(f"comp_{i}_concessions"),
            ctx.appraisal.evidence(f"comp_{i}_financing_adj"),
        ]
        if fin_adj is not None and fin_adj > 0:
            # Wrong direction: concession present but adjustment is upward
            conc_num = _parse_num(concession)
            amount = int(conc_num) if conc_num is not None else 0
            out.append(RuleResult(
                rule_id="CG-CONC-DIR", checklist_num="CG-conc-dir", section="sales_comparison",
                status=RuleStatus.FAIL,
                message=qc_config.template("SCA-7-conc", comp=i, a=amount),
                fields_involved=[f"comp_{i}_concessions", f"comp_{i}_financing_adj"],
                template_id="SCA-7-conc",
                evidence=ev,
                confidence=0.85,
            ))
        else:
            out.append(RuleResult(
                rule_id="CG-CONC-DIR", checklist_num="CG-conc-dir", section="sales_comparison",
                status=RuleStatus.PASS,
                fields_involved=[f"comp_{i}_concessions", f"comp_{i}_financing_adj"],
                evidence=ev,
            ))

    if not any_checked:
        return RuleResult(
            rule_id="CG-CONC-DIR", checklist_num="CG-conc-dir", section="sales_comparison",
            status=RuleStatus.NOT_APPLICABLE,
            message="No seller concessions noted across comparables; concession-direction check not applicable.",
        )
    return out


# ---------------------------------------------------------------------------
# CG-COND-CONSIST — Same condition rating but different adjustment amounts
# ---------------------------------------------------------------------------

@rule(id="CG-COND-CONSIST", num="CG-cond-cons", section="sales_comparison", phase=4,
      applies_when=lambda ctx: ctx.has_sca_grid,
      name="Condition adjustment consistency across comps")
def cg_condition_consistency(ctx: QCContext):
    """Comps sharing the same UAD condition rating should receive consistent condition
    adjustments. When comps in the same rating group differ by > $5,000 (configurable)
    in their condition adjustment amounts, flag for VERIFY.

    Uses the existing SCA-ac-inconsistent template."""
    tolerance = float(qc_config.semantic("comp_cond_adj_tolerance", 5000))
    idx = _comp_indices(ctx)

    # Build a mapping: condition_rating → list of (comp_index, adj_amount)
    groups: dict = {}
    for i in idx:
        rating = str(ctx.appraisal.value(f"comp_{i}_condition_rating") or "").strip().upper()
        if not rating:
            continue
        adj_raw = ctx.appraisal.value(f"comp_{i}_condition_adj")
        adj = _parse_num(adj_raw)
        if adj is None:
            adj = 0.0
        groups.setdefault(rating, []).append((i, adj))

    out = []
    for rating, members in groups.items():
        if len(members) < 2:
            continue
        amounts = [adj for _, adj in members]
        spread = max(amounts) - min(amounts)
        if spread <= tolerance:
            continue
        # Inconsistency detected within this condition group
        comp_ids = ", ".join(str(c) for c, _ in members)
        amounts_str = ", ".join(f"${int(a):,}" for _, a in members)
        facts = (
            f"Comp {comp_ids} share condition rating {rating} but have "
            f"different condition adjustments ({amounts_str})"
        )
        # Peer adjustment amount: the non-zero adjustment from the first adjusted member
        peer_adj = next((int(a) for _, a in members if a != 0), 0)
        for i, adj in members:
            ev = [
                ctx.appraisal.evidence(f"comp_{i}_condition_rating"),
                ctx.appraisal.evidence(f"comp_{i}_condition_adj"),
            ]
            _av = layer_b.assess(
                ctx, concern="adjustment_consistency",
                base_message=qc_config.template(
                    "SCA-ac-inconsistent",
                    comp=i,
                    field="condition",
                    value=rating,
                    a=peer_adj,
                ),
                facts=facts,
            )
            out.append(RuleResult(
                rule_id="CG-COND-CONSIST", checklist_num="CG-cond-cons", section="sales_comparison",
                status=_av.status, message=_av.message, reasoning=_av.reasoning,
                fields_involved=[f"comp_{i}_condition_rating", f"comp_{i}_condition_adj"],
                template_id="SCA-ac-inconsistent",
                evidence=ev,
                confidence=_av.confidence,
            ))

    if not out:
        ev_sample = [ctx.appraisal.evidence(f"comp_{i}_condition_adj") for i in idx[:3]]
        return RuleResult(
            rule_id="CG-COND-CONSIST", checklist_num="CG-cond-cons", section="sales_comparison",
            status=RuleStatus.PASS,
            fields_involved=["comp_N_condition_rating", "comp_N_condition_adj"],
            evidence=ev_sample,
        )
    return out


# ---------------------------------------------------------------------------
# CG-TIME-CONSIST — Time adjustment rate consistency
# ---------------------------------------------------------------------------

@rule(id="CG-TIME-CONSIST", num="CG-time-cons", section="sales_comparison", phase=4,
      applies_when=lambda ctx: ctx.has_sca_grid,
      name="Time/market adjustment rate consistency")
def cg_time_consistency(ctx: QCContext):
    """When multiple comps carry a non-zero financing_adj that approximates a
    date-of-sale/time-market adjustment, compute the rate per month for each
    (financing_adj / months_elapsed_from_sale_to_effective_date). If rates vary
    by more than 50% (configurable) across comps → VERIFY."""
    variance_pct = float(qc_config.semantic("comp_time_adj_variance_pct", 50.0))
    eff = _effective_ym(ctx)

    # Collect (comp_index, adj_per_month) for comps with measurable time adjustments
    time_adj_rates = []
    evidence = []

    idx = _comp_indices(ctx)
    for i in idx:
        fin_raw = ctx.appraisal.value(f"comp_{i}_financing_adj")
        fin_adj = _parse_num(fin_raw)
        if fin_adj is None or fin_adj == 0:
            continue  # No financing/time adjustment for this comp

        sp_raw = ctx.appraisal.value(f"comp_{i}_sale_price")
        sp = _parse_num(sp_raw)
        if sp is None or sp <= 0:
            continue

        sale_date_raw = ctx.appraisal.value(f"comp_{i}_sale_date")
        sale_ym = _parse_uad_date_ym(str(sale_date_raw or ""))
        if sale_ym is None:
            continue  # Can't compute elapsed months without a parseable sale date

        if eff is None:
            continue  # No effective date → skip

        months = _months_between(sale_ym, eff)
        if months <= 0:
            continue  # Sale is same month or after effective date → no elapsed time

        rate_per_month = fin_adj / months
        time_adj_rates.append((i, rate_per_month))
        evidence.append(ctx.appraisal.evidence(f"comp_{i}_financing_adj"))
        evidence.append(ctx.appraisal.evidence(f"comp_{i}_sale_date"))

    if len(time_adj_rates) < 2:
        return RuleResult(
            rule_id="CG-TIME-CONSIST", checklist_num="CG-time-cons", section="sales_comparison",
            status=RuleStatus.SKIPPED,
            message="Fewer than 2 comps with measurable time adjustments; rate consistency check skipped.",
            fields_involved=["comp_N_financing_adj", "comp_N_sale_date"],
            evidence=evidence,
        )

    rates = [r for _, r in time_adj_rates]
    abs_rates = [abs(r) for r in rates]
    rate_min, rate_max = min(abs_rates), max(abs_rates)

    # Variance as percentage of the lower rate (avoids division by zero check below)
    if rate_min == 0:
        # One rate is zero, another is not → definitely inconsistent
        variance = 100.0
    else:
        variance = (rate_max - rate_min) / rate_min * 100.0

    if variance <= variance_pct:
        return RuleResult(
            rule_id="CG-TIME-CONSIST", checklist_num="CG-time-cons", section="sales_comparison",
            status=RuleStatus.PASS,
            fields_involved=["comp_N_financing_adj", "comp_N_sale_date"],
            evidence=evidence[:4],
        )

    low_str = f"${rate_min:,.0f}"
    high_str = f"${rate_max:,.0f}"
    v = layer_b.assess(
        ctx, concern="large_adjustment",
        base_message=qc_config.template("CG-time-consist", low=low_str, high=high_str),
        facts=(
            f"time adjustment rates range from {low_str}/mo to {high_str}/mo across "
            f"comp(s) {', '.join(str(i) for i, _ in time_adj_rates)}"
        ),
    )
    return RuleResult(
        rule_id="CG-TIME-CONSIST", checklist_num="CG-time-cons", section="sales_comparison",
        status=v.status, message=v.message, reasoning=v.reasoning,
        fields_involved=["comp_N_financing_adj", "comp_N_sale_date"],
        template_id="CG-time-consist",
        evidence=evidence[:4],
        confidence=v.confidence,
    )


# ---------------------------------------------------------------------------
# CG-NONARMS — Non-arms-length comp without commentary
# ---------------------------------------------------------------------------

# UAD distress / non-arms-length indicator codes that may appear in concessions
# or data_source fields. Match is case-insensitive.
_DISTRESS_PATTERNS = re.compile(
    r"\b(REO|ShrtSal[e]?|ShortSal[e]?|foreclosur[e]?|non[- ]?arm[' ]?s?[- ]?length|"
    r"non[- ]?arm|bank[- ]?owned|distress|delinquent|court[- ]?ordered)\b",
    re.I,
)


@rule(id="CG-NONARMS", num="CG-nonarms", section="sales_comparison", phase=3,
      applies_when=lambda ctx: ctx.has_sca_grid,
      name="Non-arms-length comp without commentary")
def cg_nonarms_commentary(ctx: QCContext):
    """When a comp shows UAD distress indicators (REO, ShrtSale, foreclosure, etc.)
    in concessions or data_source, the addendum must address the comp by number
    with an explanation. If no explanation is found → VERIFY (via layer_b)."""
    addendum = str(ctx.appraisal.value("addendum_text") or "").lower()
    idx = _comp_indices(ctx)
    out = []
    any_distress = False

    for i in idx:
        concession = str(ctx.appraisal.value(f"comp_{i}_concessions") or "")
        data_source = str(ctx.appraisal.value(f"comp_{i}_data_source") or "")
        combined = f"{concession} {data_source}"

        m = _DISTRESS_PATTERNS.search(combined)
        if not m:
            continue

        any_distress = True
        indicator = m.group(0)
        ev = [
            ctx.appraisal.evidence(f"comp_{i}_concessions"),
            ctx.appraisal.evidence(f"comp_{i}_data_source"),
            ctx.appraisal.evidence("addendum_text"),
        ]

        # Check if addendum references this comp and provides an explanation
        comp_mentioned = bool(
            re.search(
                rf"\bcomp(arable)?\s*{i}\b|\b{i}(st|nd|rd|th)?\s+comp",
                addendum, re.I,
            )
        )
        has_explanation = comp_mentioned and bool(
            re.search(
                r"(arm|distress|reo|short\s*sale?|foreclos|non[- ]arm|"
                r"explain|confirm|typical|market|bank[- ]owned)",
                addendum, re.I,
            )
        )

        if not has_explanation:
            _av = layer_b.assess(
                ctx, concern="comp_selection",
                base_message=qc_config.template(
                    "CG-nonarms-nocomment", comp=i, indicator=indicator,
                ),
                facts=f"comp {i} shows distress indicator '{indicator}' with no addendum commentary",
            )
            out.append(RuleResult(
                rule_id="CG-NONARMS", checklist_num="CG-nonarms", section="sales_comparison",
                status=_av.status, message=_av.message, reasoning=_av.reasoning,
                fields_involved=[
                    f"comp_{i}_concessions",
                    f"comp_{i}_data_source",
                    "addendum_text",
                ],
                template_id="CG-nonarms-nocomment",
                evidence=ev,
                confidence=_av.confidence,
            ))
        else:
            out.append(RuleResult(
                rule_id="CG-NONARMS", checklist_num="CG-nonarms", section="sales_comparison",
                status=RuleStatus.PASS,
                fields_involved=[f"comp_{i}_concessions", f"comp_{i}_data_source"],
                evidence=ev,
            ))

    if not any_distress:
        return RuleResult(
            rule_id="CG-NONARMS", checklist_num="CG-nonarms", section="sales_comparison",
            status=RuleStatus.NOT_APPLICABLE,
            message="No non-arms-length distress indicators found in comparables.",
        )
    return out


# ---------------------------------------------------------------------------
# CG-PRIOR-SALE — Comp had recent prior sale at materially different price
# ---------------------------------------------------------------------------

@rule(id="CG-PRIOR-SALE", num="CG-prior-sale", section="sales_comparison", phase=4,
      applies_when=lambda ctx: ctx.has_sca_grid,
      name="Comp prior sale rapid appreciation flag")
def cg_prior_sale_change(ctx: QCContext):
    """A comp that had a prior sale within 36 months (configurable) at a price more
    than 25% (configurable) different from its current sale price may be a flip or
    non-arm's-length transaction and warrants explanation (VERIFY via layer_b)."""
    window = int(qc_config.semantic("comp_prior_sale_window_months", 36))
    change_threshold = float(qc_config.semantic("comp_prior_sale_change_pct", 25.0))

    idx = _comp_indices(ctx)
    out = []
    any_prior = False

    for i in idx:
        prior_price_raw = ctx.appraisal.value(f"comp_{i}_prior_sale_price")
        prior_date_raw = ctx.appraisal.value(f"comp_{i}_prior_sale_date")
        current_price_raw = ctx.appraisal.value(f"comp_{i}_sale_price")

        prior_price = _parse_num(prior_price_raw)
        current_price = _parse_num(current_price_raw)

        if prior_price is None or prior_price <= 0:
            continue
        if current_price is None or current_price <= 0:
            continue

        ev = [
            ctx.appraisal.evidence(f"comp_{i}_prior_sale_date"),
            ctx.appraisal.evidence(f"comp_{i}_prior_sale_price"),
            ctx.appraisal.evidence(f"comp_{i}_sale_price"),
            ctx.appraisal.evidence(f"comp_{i}_sale_date"),
        ]

        # Parse prior sale date — try full MM/DD/YYYY first, then UAD s-token
        prior_ym = _parse_full_date_ym(prior_date_raw)
        if prior_ym is None:
            prior_ym = _parse_uad_date_ym(str(prior_date_raw or ""))
        if prior_ym is None:
            continue  # Can't compute elapsed months without a parseable prior date

        # Parse current sale date — try UAD s-token first, then full date format
        sale_date_raw = ctx.appraisal.value(f"comp_{i}_sale_date")
        sale_ym = _parse_uad_date_ym(str(sale_date_raw or ""))
        if sale_ym is None:
            sale_ym = _parse_full_date_ym(str(sale_date_raw or ""))
        if sale_ym is None:
            # Last resort: use effective date as reference
            sale_ym = _effective_ym(ctx)
        if sale_ym is None:
            continue

        months = _months_between(prior_ym, sale_ym)
        if months < 0 or months > window:
            continue  # Prior sale outside the look-back window → not flagged

        any_prior = True
        price_change_pct = abs(current_price - prior_price) / prior_price * 100.0

        # SCA-FLIP covers all rapid resales within its window (same 36-month default).
        # When a comp falls inside that window, SCA-FLIP already surfaces it for review
        # regardless of price change — avoid double-counting the same finding here.
        flip_window = int(qc_config.semantic("comp_resale_window_months", 36))
        if months <= flip_window:
            out.append(RuleResult(
                rule_id="CG-PRIOR-SALE", checklist_num="CG-prior-sale",
                section="sales_comparison", status=RuleStatus.PASS,
                fields_involved=[f"comp_{i}_prior_sale_date", f"comp_{i}_prior_sale_price"],
                evidence=ev,
            ))
            continue

        if price_change_pct <= change_threshold:
            out.append(RuleResult(
                rule_id="CG-PRIOR-SALE", checklist_num="CG-prior-sale", section="sales_comparison",
                status=RuleStatus.PASS,
                fields_involved=[f"comp_{i}_prior_sale_price", f"comp_{i}_sale_price"],
                evidence=ev,
            ))
            continue

        # Significant price change within the look-back window: flag for VERIFY
        v = layer_b.assess(
            ctx, concern="comp_selection",
            base_message=qc_config.template(
                "CG-prior-sale-comp",
                comp=i,
                months=months,
                prior=int(prior_price),
                current=int(current_price),
                pct=round(price_change_pct, 1),
            ),
            facts=(
                f"comp {i} prior sale was ${int(prior_price):,} ({months} months before "
                f"current sale); current sale price ${int(current_price):,} is a "
                f"{price_change_pct:.1f}% change"
            ),
        )
        out.append(RuleResult(
            rule_id="CG-PRIOR-SALE", checklist_num="CG-prior-sale", section="sales_comparison",
            status=v.status, message=v.message, reasoning=v.reasoning,
            fields_involved=[
                f"comp_{i}_prior_sale_date",
                f"comp_{i}_prior_sale_price",
                f"comp_{i}_sale_price",
            ],
            template_id="CG-prior-sale-comp",
            evidence=ev,
            confidence=v.confidence,
        ))

    if not any_prior:
        ev_sample = [ctx.appraisal.evidence(f"comp_{i}_prior_sale_date") for i in idx[:3]]
        return RuleResult(
            rule_id="CG-PRIOR-SALE", checklist_num="CG-prior-sale", section="sales_comparison",
            status=RuleStatus.PASS,
            message="No comparable prior sales within the look-back window with material price changes.",
            fields_involved=["comp_N_prior_sale_date", "comp_N_prior_sale_price"],
            evidence=ev_sample,
        )

    return out
