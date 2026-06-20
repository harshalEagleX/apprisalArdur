"""
Sales Comparison Approach rules (SCA / checklist 53-88).

Two extraction sources feed these rules:
  • Camelot indexed numeric columns — comp_{1..6}_sale_price / _net_adjustment /
    _adjusted_sale_price (reliable, right-aligned currency).
  • comp_grid_extractor descriptive cells — address, proximity, data/verification
    source, date of sale, condition rating. The full-cell-width fix + positional
    date handling made these reliable (corpus coverage ≥90%), so the per-comp
    grid-cell rules below are now ACTIVE (see TASK_HISTORY.txt, SCA grid track).

Rules:
  SCA-2   comparables required (count + value threshold)
  SCA-3   comp address present              SCA-4   comp proximity present
  SCA-5   comp data source present          SCA-8   date-of-sale sequencing (c≤s)
  SCA-16  comp condition UAD rating + consistency vs subject
  SCA-NET net adjustment ≤ 15% of comp sale price
  SCA-BR  market value bracketed by adjusted sale prices
"""

from __future__ import annotations

import re
from typing import Dict, List

from app.qc import layer_b
from app.qc.config import qc_config
from app.qc.context import QCContext
from app.qc.matching import normalize_currency
from app.qc.registry import rule
from app.qc.result import RuleResult, RuleStatus

_MAX_COMPS = 6


def _pct(val) -> "float | None":
    """Parse a printed reconciliation percentage ('38.6', '14.1') to a float."""
    if val is None:
        return None
    m = re.search(r"\d+(?:\.\d+)?", str(val))
    return float(m.group(0)) if m else None


def _parse_full_date(val) -> "tuple | None":
    """'02/09/2026' → (2026, 2) as (year, month). Two-digit years → 20xx."""
    m = re.search(r"(\d{1,2})/(\d{1,2})/(\d{2,4})", str(val or ""))
    if not m:
        return None
    mm, _dd, yy = int(m.group(1)), int(m.group(2)), int(m.group(3))
    if yy < 100:
        yy += 2000
    return (yy, mm)


def _comp_indices(ctx: QCContext) -> List[int]:
    """Real comparable columns — gated on the Camelot sale_price (reliable), so
    blank grid-template columns (comps 4-6 on an unused second page) don't
    generate phantom findings."""
    idx = []
    for i in range(1, _MAX_COMPS + 1):
        if normalize_currency(ctx.appraisal.value(f"comp_{i}_sale_price")):
            idx.append(i)
    return idx


def _comp_rows(ctx: QCContext) -> List[Dict[str, float]]:
    """Collect per-comparable {sale_price, net_adjustment, adjusted} for comps 1..6."""
    rows = []
    for i in range(1, _MAX_COMPS + 1):
        sp = normalize_currency(ctx.appraisal.value(f"comp_{i}_sale_price"))
        if sp is None:
            continue
        sale_date = str(ctx.appraisal.value(f"comp_{i}_sale_date") or "").lower()
        financing = str(ctx.appraisal.value(f"comp_{i}_sale_financing") or "").lower()
        explicit_flag = str(ctx.appraisal.value(f"comp_{i}_is_listing") or "").lower()
        # Three independent classification signals — any one being True makes this
        # a listing/active comp.  Cross-signal disagreement is tracked separately
        # so SCA-2 can emit VERIFY instead of silently trusting Tier-1 alone.
        #
        # Tier 1 (keyword — existing): UAD Date of Sale "active" OR financing cell
        #   "listing" OR explicit extraction flag.
        t1 = (
            "active" in sale_date
            or "listing" in financing
            or explicit_flag in {"true", "yes", "1"}
        )
        # Tier 2 (settlement-date structural): a settled/closed comp must have a
        #   past sale date.  If the settlement field is blank or "N/A" the comp
        #   is structurally inconsistent with "closed".
        settle_raw = str(ctx.appraisal.value(f"comp_{i}_settlement_date") or "").strip()
        t2_blank   = bool(not settle_raw or settle_raw.lower() in {"n/a", "na", "pending", "active"})
        # Tier 3 (MLS status code in data-source citation — ACT / PEND / SLD).
        datasrc = str(ctx.appraisal.value(f"comp_{i}_data_source") or "").lower()
        t3_active  = bool("act;" in datasrc or ";act" in datasrc or "act)" in datasrc
                         or "pend" in datasrc)
        t3_closed  = bool("sld" in datasrc or "sold" in datasrc)

        # Final classification: T1 says closed but T2 or T3 disagrees → ambiguous.
        is_listing = t1
        status_conflict = (not t1) and (t2_blank or t3_active)  # T1 says closed but structure says otherwise
        rows.append({
            "i": i,
            "sale_price": sp,
            "net": normalize_currency(ctx.appraisal.value(f"comp_{i}_net_adjustment")),
            "adjusted": normalize_currency(ctx.appraisal.value(f"comp_{i}_adjusted_sale_price")),
            "is_listing": is_listing,
            "status_conflict": status_conflict,
            "t2_blank": t2_blank,
            "t3_active": t3_active,
        })
    return rows


# ---- SCA-2 comparables required -------------------------------------------

def _market_is_declining(ctx: QCContext) -> bool:
    """True when the neighborhood/market indicators suggest a declining or
    over-supplied market — the engagement letter's declining-market clause then
    makes a listing/pending comp MANDATORY (not just best-practice)."""
    ds = str(ctx.appraisal.value("demand_supply") or "").lower()
    pv = str(ctx.appraisal.value("property_values") or "").lower()
    return "over" in ds or "declin" in pv


@rule(id="SCA-2", num="54", section="sales_comparison", phase=3, name="Minimum comparable sales")
def sca2_required(ctx: QCContext):
    rows = _comp_rows(ctx)
    sales = [r for r in rows if not r["is_listing"]]
    listings = [r for r in rows if r["is_listing"]]
    val = normalize_currency(ctx.appraisal.value("appraised_value")) or 0
    required = 4 if val >= 1_000_000 else 3
    min_listings = int(qc_config.semantic("sca2_min_listings", 1))
    ev = [ctx.appraisal.evidence(f"comp_{i}_sale_price") for i in range(1, 4)]

    # Cross-signal conflicts: T1 classified a comp as "closed" but the settlement-date
    # or MLS-status signal disagrees. Surface these before the count-based FAIL so the
    # reviewer can confirm classification before we assert a comp-count deficiency.
    conflicts = [r for r in rows if r.get("status_conflict")]
    if conflicts:
        comp_ids = ", ".join(f"Comp {r['i']}" for r in conflicts)
        reasons = []
        for r in conflicts:
            parts = []
            if r.get("t2_blank"):
                parts.append("settlement date blank/N/A")
            if r.get("t3_active"):
                parts.append("MLS status code suggests active/pending")
            reasons.append(f"Comp {r['i']}: {'; '.join(parts)}")
        return RuleResult(rule_id="SCA-2", checklist_num="54", section="sales_comparison",
                          status=RuleStatus.VERIFY,
                          message=(
                              f"{comp_ids} classified as closed sale(s) by cell text, "
                              f"but structural signals disagree — {'; '.join(reasons)}. "
                              "Confirm comp status from MLS source sheet before relying "
                              "on the closed-sale count."
                          ),
                          fields_involved=["comp_N_sale_price", "comp_N_settlement_date"],
                          evidence=ev, confidence=0.55)

    # Too few closed sales — extraction may have missed comps, so VERIFY not FAIL.
    if len(sales) < required:
        return RuleResult(rule_id="SCA-2", checklist_num="54", section="sales_comparison",
                          status=RuleStatus.VERIFY,
                          message=qc_config.template("SCA-2-count", value=len(sales), required=required),
                          fields_involved=["comp_N_sale_price"], template_id="SCA-2-count",
                          evidence=ev, confidence=0.6)
    # Enough closed sales but too few active/listing comparables. Layer C: the
    # engagement letter requires a listing, so an UNEXPLAINED shortfall is a FAIL;
    # but "document why none are available" is the letter's own escape hatch, so an
    # EXPLAINED shortfall is a VERIFY (confirm the explanation), not a FAIL.
    if min_listings > 0 and len(listings) < min_listings:
        declining = _market_is_declining(ctx)
        template_id = "SCA-2-listings-decl" if declining else "SCA-2-listings"
        v = layer_b.assess(
            ctx, concern="comp_selection",
            base_message=qc_config.template(template_id, have=len(listings),
                                            need=min_listings, sales=len(sales)),
            facts="no current listing/pending comparable was included",
            explained_status=RuleStatus.VERIFY, unexplained_status=RuleStatus.FAIL)
        return RuleResult(rule_id="SCA-2", checklist_num="54", section="sales_comparison",
                          status=v.status, message=v.message, reasoning=v.reasoning,
                          fields_involved=["comp_N_sale_price", "demand_supply"],
                          template_id=template_id, evidence=ev, confidence=v.confidence)
    return RuleResult(rule_id="SCA-2", checklist_num="54", section="sales_comparison",
                      status=RuleStatus.PASS, fields_involved=["comp_N_sale_price"], evidence=ev)


# ---- SCA-NET net adjustment <= 15% of sale price --------------------------

@rule(id="SCA-NET", num="77", section="sales_comparison", phase=3, name="Net adjustment within 15%")
def sca_net_adjustment(ctx: QCContext):
    rows = _comp_rows(ctx)
    cap = qc_config.semantic("net_adjustment_pct", 15.0)
    over = []
    for r in rows:
        # Prefer the appraiser's PRINTED "Net Adj. %" (authoritative — it is the
        # ratio over ALL line adjustments); fall back to the dollar-derived estimate
        # (net total / sale price) only when the printed value was not extracted.
        printed = _pct(ctx.appraisal.value(f"comp_{r['i']}_net_adj_pct"))
        if printed is not None:
            pct = printed
        elif r["net"] is not None and r["sale_price"]:
            pct = abs(r["net"]) / r["sale_price"] * 100.0
        else:
            continue
        if pct > cap:
            over.append(r["i"])
    ev = [ctx.appraisal.evidence(f"comp_{i}_net_adjustment") for i in range(1, 4)]
    if not rows:
        # Couldn't read the net-adjustment row → don't SKIP (reads as a pass); verify.
        return RuleResult(rule_id="SCA-NET", checklist_num="77", section="sales_comparison",
                          status=RuleStatus.VERIFY,
                          message="Net adjustment values could not be read from the grid; please verify the comparable net adjustments.",
                          fields_involved=["comp_N_net_adjustment"], evidence=ev, confidence=0.5)
    if not over:
        return RuleResult(rule_id="SCA-NET", checklist_num="77", section="sales_comparison",
                          status=RuleStatus.PASS, fields_involved=["comp_N_net_adjustment"], evidence=ev)
    v = layer_b.assess(
        ctx, concern="large_adjustment",
        base_message=qc_config.template("SCA-net15", value=", ".join(map(str, over))),
        facts=f"comp(s) {', '.join(map(str, over))} with net adjustment over the 15% cap")
    return RuleResult(rule_id="SCA-NET", checklist_num="77", section="sales_comparison",
                      status=v.status, message=v.message, reasoning=v.reasoning,
                      fields_involved=["comp_N_net_adjustment"], template_id="SCA-net15",
                      evidence=ev, confidence=v.confidence)


# ---- SCA-GROSS gross adjustment <= 25% of sale price ----------------------

@rule(id="SCA-GROSS", num="77b", section="sales_comparison", phase=3, name="Gross adjustment within 25%")
def sca_gross_adjustment(ctx: QCContext):
    """Industry-standard comp-reliability gate: a comparable whose GROSS adjustment
    (sum of the absolute value of every line adjustment, as the appraiser's printed
    "Gross Adj. %") exceeds 25% of its sale price is a weak comparable and should
    carry commentary. Uses the authoritative printed percentage from the grid."""
    cap = qc_config.semantic("gross_adjustment_pct", 25.0)
    over = []
    seen = []
    for i in _comp_indices(ctx):
        gross = _pct(ctx.appraisal.value(f"comp_{i}_gross_adj_pct"))
        if gross is None:
            continue
        seen.append(i)
        if gross > cap:
            over.append(i)
    ev = [ctx.appraisal.evidence(f"comp_{i}_gross_adj_pct") for i in seen[:3]]
    if not seen:
        return RuleResult(rule_id="SCA-GROSS", checklist_num="77b", section="sales_comparison",
                          status=RuleStatus.VERIFY,
                          message="Gross adjustment % could not be read from the grid; please verify the comparable gross adjustments.",
                          fields_involved=["comp_N_gross_adj_pct"], evidence=ev, confidence=0.5)
    if not over:
        return RuleResult(rule_id="SCA-GROSS", checklist_num="77b", section="sales_comparison",
                          status=RuleStatus.PASS, fields_involved=["comp_N_gross_adj_pct"], evidence=ev)
    v = layer_b.assess(
        ctx, concern="large_adjustment",
        base_message=qc_config.template("SCA-gross25", value=", ".join(map(str, over))),
        facts=f"comp(s) {', '.join(map(str, over))} with gross adjustment over the 25% cap")
    return RuleResult(rule_id="SCA-GROSS", checklist_num="77b", section="sales_comparison",
                      status=v.status, message=v.message, reasoning=v.reasoning,
                      fields_involved=["comp_N_gross_adj_pct"], template_id="SCA-gross25",
                      evidence=ev, confidence=v.confidence)


# ---- SCA-3 address present (per comp, grid extractor) ---------------------

@rule(id="SCA-3", num="55", section="sales_comparison", phase=3, name="Comp address present")
def sca3_address(ctx: QCContext):
    out = []
    for i in _comp_indices(ctx):
        val = str(ctx.appraisal.value(f"comp_{i}_address") or "").strip()
        ev = [ctx.appraisal.evidence(f"comp_{i}_address")]
        if len(val) > 3:
            out.append(RuleResult(rule_id="SCA-3", checklist_num="55", section="sales_comparison",
                                  status=RuleStatus.PASS, fields_involved=[f"comp_{i}_address"], evidence=ev))
        else:
            out.append(RuleResult(rule_id="SCA-3", checklist_num="55", section="sales_comparison",
                                  status=RuleStatus.VERIFY,
                                  message=qc_config.template("SCA-3-addr", comp=i),
                                  fields_involved=[f"comp_{i}_address"], template_id="SCA-3-addr",
                                  evidence=ev, confidence=0.7))
    return out


# ---- SCA-4 proximity present (per comp, grid extractor) -------------------

@rule(id="SCA-4", num="56", section="sales_comparison", phase=3, name="Comp proximity present")
def sca4_proximity(ctx: QCContext):
    out = []
    for i in _comp_indices(ctx):
        val = ctx.appraisal.value(f"comp_{i}_proximity")
        ev = [ctx.appraisal.evidence(f"comp_{i}_proximity")]
        ok = bool(val) and re.search(r"\d", val or "") and re.search(r"\b[NSEW]{1,2}\b", (val or "").upper())
        if ok:
            out.append(RuleResult(rule_id="SCA-4", checklist_num="56", section="sales_comparison",
                                  status=RuleStatus.PASS, fields_involved=[f"comp_{i}_proximity"], evidence=ev))
        else:
            out.append(RuleResult(rule_id="SCA-4", checklist_num="56", section="sales_comparison",
                                  status=RuleStatus.VERIFY,
                                  message=qc_config.template("SCA-4-prox", comp=i),
                                  fields_involved=[f"comp_{i}_proximity"], template_id="SCA-4-prox",
                                  evidence=ev, confidence=0.65))
    return out


# ---- SCA-5 data source present (per comp) ---------------------------------

def _marketing_time_days(value) -> Optional[int]:
    """Upper-bound days for the UAD neighborhood Marketing Time enum. None when
    not stated or 'Over 6 mths' (no enforceable upper bound)."""
    s = str(value or "").lower()
    if not s:
        return None
    if "under 3" in s or "less than 3" in s or "<3" in s or "< 3" in s:
        return 90
    if "3-6" in s or "3 - 6" in s or "3–6" in s:
        return 180
    return None


@rule(id="SCA-5", num="57", section="sales_comparison", phase=3, name="Comp data source present")
def sca5_data_source(ctx: QCContext):
    mt = ctx.appraisal.value("marketing_time")
    mt_days = _marketing_time_days(mt)
    out = []
    for i in _comp_indices(ctx):
        val = ctx.appraisal.value(f"comp_{i}_data_source")
        ev = [ctx.appraisal.evidence(f"comp_{i}_data_source")]
        # presence/format check
        if not (val and re.search(r"(mls|#|dom|\d)", val.lower())):
            out.append(RuleResult(rule_id="SCA-5", checklist_num="57", section="sales_comparison",
                                  status=RuleStatus.VERIFY,
                                  message=qc_config.template("SCA-5-ds", comp=i),
                                  fields_involved=[f"comp_{i}_data_source"], template_id="SCA-5-ds",
                                  evidence=ev, confidence=0.6))
            continue
        # DOM vs the neighborhood's stated marketing time — a comp that took longer
        # to sell than the typical marketing time is an outlier needing commentary.
        m = re.search(r"dom\s*(\d+)", val.lower())
        if mt_days is not None and m and int(m.group(1)) > mt_days:
            out.append(RuleResult(rule_id="SCA-5", checklist_num="57", section="sales_comparison",
                                  status=RuleStatus.VERIFY,
                                  message=qc_config.template("SCA-5-dom", comp=i, dom=int(m.group(1)), mt=mt),
                                  fields_involved=[f"comp_{i}_data_source", "marketing_time"],
                                  template_id="SCA-5-dom", evidence=ev, confidence=0.6))
            continue
        out.append(RuleResult(rule_id="SCA-5", checklist_num="57", section="sales_comparison",
                              status=RuleStatus.PASS, fields_involved=[f"comp_{i}_data_source"], evidence=ev))
    return out


# ---- SCA-8 date of sale: contract (c) before sale (s) ---------------------

def _parse_uad_date(tok: str):
    """'s06/14;c11/13' → {'s': (2014, 6), 'c': (2013, 11)} as (year, month) for
    ordering. Two-digit years are normalized to 20xx."""
    res = {}
    for kind, mm, yy in re.findall(r"([sc])\s*(\d{1,2})/(\d{2,4})", tok or "", re.I):
        year = int(yy)
        if year < 100:
            year += 2000
        res[kind.lower()] = (year, int(mm))
    return res


@rule(id="SCA-8", num="60", section="sales_comparison", phase=3, name="Comp date of sale sequencing")
def sca8_date_sequence(ctx: QCContext):
    out = []
    for i in _comp_indices(ctx):
        tok = ctx.appraisal.value(f"comp_{i}_sale_date")
        ev = [ctx.appraisal.evidence(f"comp_{i}_sale_date")]
        d = _parse_uad_date(tok or "")
        if "s" not in d or "c" not in d:
            continue  # need both sale and contract dates to check ordering
        if d["c"] <= d["s"]:
            out.append(RuleResult(rule_id="SCA-8", checklist_num="60", section="sales_comparison",
                                  status=RuleStatus.PASS, fields_involved=[f"comp_{i}_sale_date"], evidence=ev))
        else:
            out.append(RuleResult(rule_id="SCA-8", checklist_num="60", section="sales_comparison",
                                  status=RuleStatus.VERIFY,
                                  message=qc_config.template("SCA-8-datesale", comp=i),
                                  fields_involved=[f"comp_{i}_sale_date"], template_id="SCA-8-datesale",
                                  evidence=ev, confidence=0.7))
    return out


# ---- SCA-16 condition rating present + UAD format + consistency vs subject -

def _grade(val, letter: str) -> "int | None":
    m = re.fullmatch(rf"{letter}([1-6])", str(val or "").strip().upper())
    return int(m.group(1)) if m else None


def _grade_consistency_rule(ctx, rule_id, num, field, letter, label, fmt_template):
    """Format check + zero-adjustment consistency for a discrete UAD-grade row
    (condition C1-6 / quality Q1-6). MIRA's core cross-check: if the comp matches the
    subject grade, no adjustment should be applied; if it differs, an adjustment (or
    commentary) is expected. Reliable because the grade codes and the per-field
    adjustment column both extract cleanly."""
    subj_n = _grade(ctx.appraisal.value(field) or ctx.appraisal.value(f"subject_grid_{field}"), letter)
    out = []
    for i in _comp_indices(ctx):
        val = (ctx.appraisal.value(f"comp_{i}_{field}") or "").upper()
        adj = normalize_currency(ctx.appraisal.value(f"comp_{i}_{field}_adjustment"))
        ev = [ctx.appraisal.evidence(f"comp_{i}_{field}")]
        comp_n = _grade(val, letter)
        if comp_n is None:
            out.append(RuleResult(rule_id=rule_id, checklist_num=num, section="sales_comparison",
                                  status=RuleStatus.VERIFY, message=qc_config.template(fmt_template, comp=i),
                                  fields_involved=[f"comp_{i}_{field}"], template_id=fmt_template,
                                  evidence=ev, confidence=0.65))
            continue
        if subj_n is None:
            out.append(RuleResult(rule_id=rule_id, checklist_num=num, section="sales_comparison",
                                  status=RuleStatus.PASS, fields_involved=[f"comp_{i}_{field}"], evidence=ev))
            continue
        ev = ev + [ctx.appraisal.evidence(field), ctx.appraisal.evidence(f"comp_{i}_{field}_adjustment")]
        if comp_n == subj_n and adj not in (None, 0):
            out.append(RuleResult(rule_id=rule_id, checklist_num=num, section="sales_comparison",
                                  status=RuleStatus.VERIFY,
                                  message=qc_config.template("SCA-zadj-same", comp=i, field=label,
                                                             v=f"{letter}{comp_n}", a=int(adj)),
                                  fields_involved=[f"comp_{i}_{field}", f"comp_{i}_{field}_adjustment"],
                                  template_id="SCA-zadj-same", evidence=ev, confidence=0.65))
        elif comp_n != subj_n and (adj is None or adj == 0):
            out.append(RuleResult(rule_id=rule_id, checklist_num=num, section="sales_comparison",
                                  status=RuleStatus.VERIFY,
                                  message=qc_config.template("SCA-zadj-diff", comp=i, field=label,
                                                             cv=f"{letter}{comp_n}", sv=f"{letter}{subj_n}"),
                                  fields_involved=[f"comp_{i}_{field}", f"comp_{i}_{field}_adjustment"],
                                  template_id="SCA-zadj-diff", evidence=ev, confidence=0.6))
        else:
            out.append(RuleResult(rule_id=rule_id, checklist_num=num, section="sales_comparison",
                                  status=RuleStatus.PASS, fields_involved=[f"comp_{i}_{field}"], evidence=ev))
    return out


@rule(id="SCA-16", num="68", section="sales_comparison", phase=3, name="Comp condition UAD rating + zero-adj")
def sca16_condition(ctx: QCContext):
    return _grade_consistency_rule(ctx, "SCA-16", "68", "condition_rating", "C", "condition", "SCA-16-cond")


# ---- SCA-BR market value bracketed by adjusted sale prices ----------------

@rule(id="SCA-BR", num="78", section="sales_comparison", phase=3, name="Value bracketed by adjusted prices")
def sca_bracket(ctx: QCContext):
    rows = _comp_rows(ctx)
    adj = [r["adjusted"] for r in rows if r["adjusted"] is not None]
    val = normalize_currency(ctx.appraisal.value("appraised_value"))
    ev = [ctx.appraisal.evidence("appraised_value")] + \
         [ctx.appraisal.evidence(f"comp_{i}_adjusted_sale_price") for i in _comp_indices(ctx)]
    if val is None or len(adj) < 2:
        # Cannot run the check — the "Adjusted Sale Price of Comparable" grid row
        # was not read reliably (fewer than two adjusted prices). Do NOT SKIP:
        # SKIPPED renders as a benign pass and hides the extraction gap. Route to
        # VERIFY so a reviewer confirms bracketing from the grid manually.
        return RuleResult(rule_id="SCA-BR", checklist_num="78", section="sales_comparison",
                          status=RuleStatus.VERIFY, message=qc_config.template("SCA-bracket-na"),
                          fields_involved=["appraised_value", "comp_N_adjusted_sale_price"],
                          template_id="SCA-bracket-na", evidence=ev, confidence=0.5)
    if min(adj) <= val <= max(adj):
        return RuleResult(rule_id="SCA-BR", checklist_num="78", section="sales_comparison",
                          status=RuleStatus.PASS, fields_involved=["appraised_value"], evidence=ev)
    # bracketing failures are often partial-extraction artifacts → VERIFY
    return RuleResult(rule_id="SCA-BR", checklist_num="78", section="sales_comparison",
                      status=RuleStatus.VERIFY, message=qc_config.template("SCA-bracket"),
                      fields_involved=["appraised_value", "comp_N_adjusted_sale_price"],
                      template_id="SCA-bracket", evidence=ev, confidence=0.6)


# ---- SCA-BR2 Champions Funding: ≥2 adjusted prices at/above final value ----
# Champions Funding's engagement letter adds a SEPARATE, STRICTER bracketing
# test: at least 2 of the comparable adjusted sale prices must be equal to or
# greater than the final opinion of value. This is distinct from SCA-BR (which
# only verifies the value falls BETWEEN the min and max adjusted price).
# Config key: sca_br2_min_above (default 2) — the minimum count.

@rule(id="SCA-BR2", num="78b", section="sales_comparison", phase=3,
      name="Min comps with adjusted value at/above final opinion (lender overlay)")
def sca_bracket_above(ctx: QCContext):
    rows = _comp_rows(ctx)
    val = normalize_currency(ctx.appraisal.value("appraised_value"))
    ev = [ctx.appraisal.evidence("appraised_value")] + \
         [ctx.appraisal.evidence(f"comp_{i}_adjusted_sale_price") for i in _comp_indices(ctx)]
    adj = [r["adjusted"] for r in rows if r["adjusted"] is not None and not r["is_listing"]]
    if val is None or len(adj) < 2:
        return RuleResult(rule_id="SCA-BR2", checklist_num="78b", section="sales_comparison",
                          status=RuleStatus.VERIFY,
                          message="Adjusted sale prices could not be read to test the lender's "
                                  "bracketing requirement; please verify at least 2 comps have "
                                  "adjusted prices at or above the final value.",
                          fields_involved=["appraised_value", "comp_N_adjusted_sale_price"],
                          evidence=ev, confidence=0.5)
    min_above = int(qc_config.semantic("sca_br2_min_above", 2))
    above = [a for a in adj if a >= val]
    if len(above) >= min_above:
        return RuleResult(rule_id="SCA-BR2", checklist_num="78b", section="sales_comparison",
                          status=RuleStatus.PASS, fields_involved=["appraised_value"], evidence=ev)
    return RuleResult(rule_id="SCA-BR2", checklist_num="78b", section="sales_comparison",
                      status=RuleStatus.FAIL,
                      message=qc_config.template("SCA-BR2-below",
                                                 have=len(above), need=min_above,
                                                 value=int(val)),
                      fields_involved=["appraised_value", "comp_N_adjusted_sale_price"],
                      template_id="SCA-BR2-below", evidence=ev)


# ---------------------------------------------------------------------------
# Per-comp presence / UAD-format rules (same PASS/VERIFY convention as SCA-4/5/16:
# extraction may legitimately miss a cell, so a blank/invalid is VERIFY not FAIL).
# ---------------------------------------------------------------------------

def _per_comp_field(ctx, rule_id, num, field, template_id, ok_fn):
    out = []
    for i in _comp_indices(ctx):
        val = str(ctx.appraisal.value(f"comp_{i}_{field}") or "").strip()
        ev = [ctx.appraisal.evidence(f"comp_{i}_{field}")]
        if ok_fn(val):
            out.append(RuleResult(rule_id=rule_id, checklist_num=num, section="sales_comparison",
                                  status=RuleStatus.PASS, fields_involved=[f"comp_{i}_{field}"], evidence=ev))
        else:
            out.append(RuleResult(rule_id=rule_id, checklist_num=num, section="sales_comparison",
                                  status=RuleStatus.VERIFY, message=qc_config.template(template_id, comp=i),
                                  fields_involved=[f"comp_{i}_{field}"], template_id=template_id,
                                  evidence=ev, confidence=0.6))
    return out


_VAGUE_SOURCES = {"public records", "public record", "county records", "county record",
                  "public", "records", "tax records", "assessor", "appraisal files", "mls"}


@rule(id="SCA-6", num="58", section="sales_comparison", phase=3, name="Comp verification source specific")
def sca6_verification(ctx: QCContext):
    """Presence + SPECIFICITY (MIRA): UAD wants a named source (e.g. 'Orange County
    Assessor', 'MIRMLS sale data'), not a bare 'public records'. Vague sources VERIFY."""
    out = []
    for i in _comp_indices(ctx):
        val = str(ctx.appraisal.value(f"comp_{i}_verification_source") or "").strip()
        ev = [ctx.appraisal.evidence(f"comp_{i}_verification_source")]
        low = re.sub(r"[^a-z ]", "", val.lower()).strip()
        if len(val) <= 2 or low in _VAGUE_SOURCES:
            out.append(RuleResult(rule_id="SCA-6", checklist_num="58", section="sales_comparison",
                                  status=RuleStatus.VERIFY, message=qc_config.template("SCA-6-verif", comp=i),
                                  fields_involved=[f"comp_{i}_verification_source"], template_id="SCA-6-verif",
                                  evidence=ev, confidence=0.6))
        else:
            out.append(RuleResult(rule_id="SCA-6", checklist_num="58", section="sales_comparison",
                                  status=RuleStatus.PASS, fields_involved=[f"comp_{i}_verification_source"], evidence=ev))
    return out


def _uad_factors(value) -> set:
    """UAD location/view qualifier tokens beyond the rating + land-use type
    (tokens at index >= 2). 'N;Res;Corner' -> {'corner'}; 'N;Res;' -> set().
    These are the factors (Corner, Busy road, Power lines, water view, ...) that
    should drive an adjustment when the subject has one a comp lacks."""
    toks = [t.strip().lower() for t in str(value or "").split(";") if t.strip()]
    return set(toks[2:])


def _per_comp_descriptor_zeroadj(ctx, rule_id, num, field, subj_field,
                                 fmt_template, zeroadj_template):
    """Per-comp UAD format check PLUS a zero-adjustment check: when the subject
    carries a location/view factor (e.g. Corner) that a comp lacks, yet that
    comp shows no adjustment for the field, surface VERIFY (either no market
    premium — needs commentary — or the adjustment was missed). High precision:
    only fires on subject factors the comp is missing, never the reverse (P-6)."""
    subj_factors = _uad_factors(ctx.appraisal.value(subj_field))
    out = []
    for i in _comp_indices(ctx):
        val = str(ctx.appraisal.value(f"comp_{i}_{field}") or "").strip()
        ev = [ctx.appraisal.evidence(f"comp_{i}_{field}")]
        if not (";" in val and re.match(r"[A-Za-z]", val)):
            out.append(RuleResult(rule_id=rule_id, checklist_num=num, section="sales_comparison",
                                  status=RuleStatus.VERIFY, message=qc_config.template(fmt_template, comp=i),
                                  fields_involved=[f"comp_{i}_{field}"], template_id=fmt_template,
                                  evidence=ev, confidence=0.6))
            continue
        missing = subj_factors - _uad_factors(val)
        adj = normalize_currency(ctx.appraisal.value(f"comp_{i}_{field}_adjustment"))
        if subj_factors and missing and not adj:
            desc = ", ".join(sorted(missing)).title()
            out.append(RuleResult(rule_id=rule_id, checklist_num=num, section="sales_comparison",
                                  status=RuleStatus.VERIFY,
                                  message=qc_config.template(zeroadj_template, comp=i, desc=desc),
                                  fields_involved=[f"comp_{i}_{field}", f"comp_{i}_{field}_adjustment"],
                                  template_id=zeroadj_template, evidence=ev, confidence=0.6))
            continue
        out.append(RuleResult(rule_id=rule_id, checklist_num=num, section="sales_comparison",
                              status=RuleStatus.PASS, fields_involved=[f"comp_{i}_{field}"], evidence=ev))
    return out


@rule(id="SCA-9", num="61", section="sales_comparison", phase=3, name="Comp location UAD format")
def sca9_location(ctx: QCContext):
    return _per_comp_descriptor_zeroadj(ctx, "SCA-9", "61", "location_rating",
                                        "subject_grid_location_rating", "SCA-9-loc", "SCA-9-zeroadj")


@rule(id="SCA-11", num="63", section="sales_comparison", phase=3, name="Comp site size has unit")
def sca11_site(ctx: QCContext):
    return _per_comp_field(ctx, "SCA-11", "63", "site_size", "SCA-11-site",
                           lambda v: bool(re.search(r"\d", v)) and bool(re.search(r"(sf|ac|acre|sq)", v.lower())))


@rule(id="SCA-12", num="64", section="sales_comparison", phase=3, name="Comp view UAD format")
def sca12_view(ctx: QCContext):
    return _per_comp_descriptor_zeroadj(ctx, "SCA-12", "64", "view",
                                        "subject_grid_view", "SCA-12-view", "SCA-12-zeroadj")


@rule(id="SCA-14", num="66", section="sales_comparison", phase=3, name="Comp quality UAD rating + zero-adj")
def sca14_quality(ctx: QCContext):
    out = _grade_consistency_rule(ctx, "SCA-14", "66", "quality_rating", "Q", "quality", "SCA-14-qual")
    # Commentary safeguard: when quality matches across every comp with no quality
    # adjustment (all per-comp checks passed), USPAP expects the report commentary
    # to support the equivalent quality. Confirm it does — keyword fast-path, then
    # an LLM evaluative read (a missing/silent commentary is a VERIFY, not a pass).
    if out and all(r.status == RuleStatus.PASS for r in out):
        from app.qc import commentary as _com
        text = " ".join(
            s for s in (
                str(ctx.appraisal.value("sales_comparison_summary") or ""),
                str(ctx.appraisal.value("final_reconciliation_comment") or ""),
            ) if s
        ).strip()
        ev = [ctx.appraisal.evidence("sales_comparison_summary")]
        addressed = _com.quality_addressed(text)
        # None = no substantive commentary extracted to judge → skip (don't emit a
        # noise VERIFY for what is really a commentary-extraction gap).
        if addressed is True:
            out.append(RuleResult(rule_id="SCA-14", checklist_num="66", section="sales_comparison",
                                  status=RuleStatus.PASS, fields_involved=["sales_comparison_summary"], evidence=ev))
        elif addressed is False:
            out.append(RuleResult(rule_id="SCA-14", checklist_num="66", section="sales_comparison",
                                  status=RuleStatus.VERIFY,
                                  message=qc_config.template("SCA-14-comment"),
                                  fields_involved=["sales_comparison_summary"], template_id="SCA-14-comment",
                                  evidence=ev, confidence=0.5))
    return out


def _effective_ym(ctx):
    import datetime as _dt
    s = str(ctx.appraisal.value("effective_date") or "").strip()
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%m-%d-%Y"):
        try:
            d = _dt.datetime.strptime(s, fmt)
            return (d.year, d.month)
        except ValueError:
            continue
    return None


@rule(id="SCA-DC", num="60b", section="sales_comparison", phase=3, name="Comp sale within date currency window")
def sca_date_currency(ctx: QCContext):
    """Each comp should have sold within 12 months of the effective date.

    Three-layer evaluation (MIRA A/B/C) via the shared layer_b engine:
      Layer A — a parseable sale date must exist (else skip the comp).
      Layer B — layer_b detects whether the narrative explains the use of an
                older comp (limited inventory, best available, expanded search).
      Layer C — explained → lower-severity confirm; unexplained → full VERIFY.
    Never auto-FAIL — comp age is a judgment matter.
    """
    eff = _effective_ym(ctx)
    out = []
    if eff is None:
        return out
    for i in _comp_indices(ctx):
        d = _parse_uad_date(ctx.appraisal.value(f"comp_{i}_sale_date") or "")
        ym = d.get("s") or d.get("c")
        ev = [ctx.appraisal.evidence(f"comp_{i}_sale_date")]
        if not ym:
            continue
        months = (eff[0] - ym[0]) * 12 + (eff[1] - ym[1])
        if months > 12:
            v = layer_b.assess(
                ctx, concern="dated_comp",
                base_message=qc_config.template("SCA-DC-old", comp=i, months=months),
                facts=f"comp {i} sold {months} months before the effective date")
            out.append(RuleResult(
                rule_id="SCA-DC", checklist_num="60b", section="sales_comparison",
                status=v.status, message=v.message, reasoning=v.reasoning,
                fields_involved=[f"comp_{i}_sale_date", "sales_comparison_summary"],
                template_id="SCA-DC-old", evidence=ev, confidence=v.confidence))
        else:
            out.append(RuleResult(rule_id="SCA-DC", checklist_num="60b", section="sales_comparison",
                                  status=RuleStatus.PASS, fields_involved=[f"comp_{i}_sale_date"], evidence=ev))
    return out


@rule(id="SCA-PR", num="79", section="sales_comparison", phase=3, name="Comp sale price bracket vs subject value")
def sca_price_bracket(ctx: QCContext):
    """A comp whose (pre-adjustment) sale price is >25% above/below the subject's
    opinion of value is a weak comparable regardless of adjustments."""
    val = normalize_currency(ctx.appraisal.value("appraised_value"))
    out = []
    if not val or val <= 0:
        return out
    for i in _comp_indices(ctx):
        sp = normalize_currency(ctx.appraisal.value(f"comp_{i}_sale_price"))
        ev = [ctx.appraisal.evidence(f"comp_{i}_sale_price"), ctx.appraisal.evidence("appraised_value")]
        if sp is None:
            continue
        if 0.75 <= sp / val <= 1.25:
            out.append(RuleResult(rule_id="SCA-PR", checklist_num="79", section="sales_comparison",
                                  status=RuleStatus.PASS, fields_involved=[f"comp_{i}_sale_price"], evidence=ev))
        else:
            _pv = layer_b.assess(
                ctx, concern="comp_selection",
                base_message=qc_config.template("SCA-PR-bracket", comp=i, a=int(sp), b=int(val)),
                facts=f"comp {i} priced outside a reasonable bracket of the subject value")
            out.append(RuleResult(rule_id="SCA-PR", checklist_num="79", section="sales_comparison",
                                  status=_pv.status, reasoning=_pv.reasoning, confidence=_pv.confidence,
                                  message=_pv.message,
                                  fields_involved=[f"comp_{i}_sale_price"], template_id="SCA-PR-bracket",
                                  evidence=ev))
    return out


@rule(id="SCA-7", num="59", section="sales_comparison", phase=3, name="Concession adjustment direction")
def sca7_concessions(ctx: QCContext):
    """If a comp reports seller concessions (>0), the financing adjustment should be
    negative (concessions inflate the sale price; the adjustment corrects downward)."""
    out = []
    for i in _comp_indices(ctx):
        fin = str(ctx.appraisal.value(f"comp_{i}_sale_financing") or "")
        ev = [ctx.appraisal.evidence(f"comp_{i}_sale_financing")]
        m = re.search(r";\s*([\d,]+)\s*$", fin.strip())
        if not m:
            continue
        conc = int(m.group(1).replace(",", ""))
        adj = normalize_currency(ctx.appraisal.value(f"comp_{i}_sale_financing_adjustment"))
        if conc > 0 and (adj is None or adj >= 0):
            _cv = layer_b.assess(
                ctx, concern="concession",
                base_message=qc_config.template("SCA-7-conc", comp=i, a=conc),
                facts=f"comp {i} shows a ${conc} concession with no offsetting adjustment")
            out.append(RuleResult(rule_id="SCA-7", checklist_num="59", section="sales_comparison",
                                  status=_cv.status, reasoning=_cv.reasoning, confidence=_cv.confidence,
                                  message=_cv.message,
                                  fields_involved=[f"comp_{i}_sale_financing"], template_id="SCA-7-conc",
                                  evidence=ev))
        else:
            out.append(RuleResult(rule_id="SCA-7", checklist_num="59", section="sales_comparison",
                                  status=RuleStatus.PASS, fields_involved=[f"comp_{i}_sale_financing"], evidence=ev))
    return out


@rule(id="SCA-17", num="69", section="sales_comparison", phase=3,
      name="Above-grade GLA matches grid, improvements & sketch")
def sca17_subject_consistency(ctx: QCContext):
    """Subject above-grade GLA must agree across the three sources that report it:
    the SCA grid subject column, the Improvements section, and the Building Sketch
    total living area. Condition and quality consistency are SCA-16 and SCA-14's
    job, not this rule's. Also verifies each comparable's GLA is present and
    plausible (no external source exists to cross-check comp GLA against)."""
    out = []
    grid = normalize_currency(ctx.appraisal.value("subject_grid_gla"))
    impr = normalize_currency(ctx.appraisal.value("gla"))
    sketch = normalize_currency(ctx.appraisal.value("sketch_living_area"))
    ev = [ctx.appraisal.evidence("subject_grid_gla"),
          ctx.appraisal.evidence("gla"),
          ctx.appraisal.evidence("sketch_living_area")]
    present = [v for v in (grid, impr, sketch) if v is not None]

    def _fmt(v):
        return str(int(v)) if v is not None else "n/a"

    srcs = f"SCA grid {_fmt(grid)}, improvements {_fmt(impr)}, sketch {_fmt(sketch)} sf"
    gla_fields = ["subject_grid_gla", "gla", "sketch_living_area"]

    if len(present) >= 2:
        delta = max(present) - min(present)
        if delta > 50:        # always an error, never rounding
            out.append(RuleResult(rule_id="SCA-17", checklist_num="69", section="sales_comparison",
                                  status=RuleStatus.FAIL,
                                  message=qc_config.template("SCA-17-gla", srcs=srcs, delta=int(delta)),
                                  fields_involved=gla_fields, template_id="SCA-17-gla", evidence=ev))
        elif delta > 1:
            out.append(RuleResult(rule_id="SCA-17", checklist_num="69", section="sales_comparison",
                                  status=RuleStatus.VERIFY,
                                  message=qc_config.template("SCA-17-gla", srcs=srcs, delta=int(delta)),
                                  fields_involved=gla_fields, template_id="SCA-17-gla",
                                  evidence=ev, confidence=0.6))
        elif sketch is None:  # grid & improvements agree, but the sketch wasn't read
            out.append(RuleResult(rule_id="SCA-17", checklist_num="69", section="sales_comparison",
                                  status=RuleStatus.VERIFY,
                                  message=qc_config.template("SCA-17-nosketch", srcs=srcs),
                                  fields_involved=gla_fields, template_id="SCA-17-nosketch",
                                  evidence=ev, confidence=0.5))
        else:                 # all available sources agree within 1 sf
            out.append(RuleResult(rule_id="SCA-17", checklist_num="69", section="sales_comparison",
                                  status=RuleStatus.PASS, fields_involved=gla_fields, evidence=ev))
    elif len(present) == 1:
        # only one GLA source — can't cross-check; surface rather than silently pass.
        out.append(RuleResult(rule_id="SCA-17", checklist_num="69", section="sales_comparison",
                              status=RuleStatus.VERIFY,
                              message=qc_config.template("SCA-17-nosketch", srcs=srcs),
                              fields_involved=gla_fields, template_id="SCA-17-nosketch",
                              evidence=ev, confidence=0.5))

    # Per-comp GLA presence + plausibility (one result per comp; UI groups them).
    for i in _comp_indices(ctx):
        g = normalize_currency(ctx.appraisal.value(f"comp_{i}_gla"))
        cev = [ctx.appraisal.evidence(f"comp_{i}_gla")]
        if g is not None and 200 <= g <= 20000:
            out.append(RuleResult(rule_id="SCA-17", checklist_num="69", section="sales_comparison",
                                  status=RuleStatus.PASS, fields_involved=[f"comp_{i}_gla"], evidence=cev))
        else:
            out.append(RuleResult(rule_id="SCA-17", checklist_num="69", section="sales_comparison",
                                  status=RuleStatus.VERIFY,
                                  message=qc_config.template("SCA-17-comp-gla", comp=i),
                                  fields_involved=[f"comp_{i}_gla"], template_id="SCA-17-comp-gla",
                                  evidence=cev, confidence=0.6))
    return out


@rule(id="SCA-13", num="65", section="sales_comparison", phase=3, name="Comp design present")
def sca13_design(ctx: QCContext):
    return _per_comp_field(ctx, "SCA-13", "65", "design", "SCA-13-design", lambda v: len(v) > 1)


@rule(id="SCA-19", num="71", section="sales_comparison", phase=3, name="Comp functional utility present")
def sca19_functional(ctx: QCContext):
    return _per_comp_field(ctx, "SCA-19", "71", "functional_utility", "SCA-19-func", lambda v: len(v) > 1)


@rule(id="SCA-20", num="72", section="sales_comparison", phase=3, name="Comp heating/cooling present")
def sca20_heating(ctx: QCContext):
    return _per_comp_field(ctx, "SCA-20", "72", "heating_cooling", "SCA-20-heat", lambda v: len(v) > 1)


@rule(id="SCA-21", num="74", section="sales_comparison", phase=3, name="Comp garage/carport present")
def sca21_garage(ctx: QCContext):
    return _per_comp_field(ctx, "SCA-21", "74", "garage_carport", "SCA-21-garage", lambda v: len(v) > 1)


@rule(id="SCA-22", num="75", section="sales_comparison", phase=3, name="Comp porch/patio/deck present")
def sca22_porch(ctx: QCContext):
    return _per_comp_field(ctx, "SCA-22", "75", "porch_patio_deck", "SCA-22-porch", lambda v: len(v) > 1)


@rule(id="SCA-10", num="62", section="sales_comparison", phase=3, name="Comp property rights present + consistent")
def sca10_rights(ctx: QCContext):
    subj = str(ctx.appraisal.value("property_rights") or "").lower()
    subj_lease = "lease" in subj
    out = []
    for i in _comp_indices(ctx):
        val = str(ctx.appraisal.value(f"comp_{i}_leasehold") or "").strip()
        ev = [ctx.appraisal.evidence(f"comp_{i}_leasehold")]
        if not val:
            out.append(RuleResult(rule_id="SCA-10", checklist_num="62", section="sales_comparison",
                                  status=RuleStatus.VERIFY, message=qc_config.template("SCA-10-rights", comp=i),
                                  fields_involved=[f"comp_{i}_leasehold"], template_id="SCA-10-rights",
                                  evidence=ev, confidence=0.6))
        elif subj_lease and "fee" in val.lower():
            out.append(RuleResult(rule_id="SCA-10", checklist_num="62", section="sales_comparison",
                                  status=RuleStatus.VERIFY, message=qc_config.template("SCA-10-lease", comp=i),
                                  fields_involved=[f"comp_{i}_leasehold", "property_rights"],
                                  template_id="SCA-10-lease", evidence=ev, confidence=0.7))
        else:
            out.append(RuleResult(rule_id="SCA-10", checklist_num="62", section="sales_comparison",
                                  status=RuleStatus.PASS, fields_involved=[f"comp_{i}_leasehold"], evidence=ev))
    return out


# ---- SCA-PSH subject prior sale/transfer must be analyzed -----------------

@rule(id="SCA-PSH", num="80", section="sales_comparison", phase=3, name="Subject prior sale analyzed")
def sca_subject_prior_sale(ctx: QCContext):
    """A prior sale/transfer of the SUBJECT within the look-back window (36 months)
    must be analyzed and reconciled with the opinion of value (UAD/Fannie/FHA). A
    recent prior transfer near the effective date is a value-support red flag.

    When the prior sale price is known and the implied value increase is large
    (≥ sca_psh_large_gain_pct, default 30%), the message is escalated to make the
    magnitude explicit — a 60%+ increase in ~13 months (as observed in Sebring FL)
    is not the same risk level as a 10% appreciation over 3 years."""
    window = int(qc_config.semantic("comp_resale_window_months", 36))
    eff = _effective_ym(ctx)
    d = _parse_full_date(ctx.appraisal.value("subject_grid_prior_sale_date"))
    ev = [ctx.appraisal.evidence("subject_grid_prior_sale_date"), ctx.appraisal.evidence("effective_date")]
    if d is None:
        return RuleResult(rule_id="SCA-PSH", checklist_num="80", section="sales_comparison",
                          status=RuleStatus.PASS, fields_involved=["subject_grid_prior_sale_date"], evidence=ev)
    if eff is None:
        return RuleResult(rule_id="SCA-PSH", checklist_num="80", section="sales_comparison",
                          status=RuleStatus.VERIFY,
                          message="The effective date could not be read to age the subject's prior sale; please verify the prior-sale recency.",
                          fields_involved=["subject_grid_prior_sale_date", "effective_date"], evidence=ev, confidence=0.5)
    months = (eff[0] - d[0]) * 12 + (eff[1] - d[1])
    if 0 <= months <= window:
        # Check for a large implied value gain — escalate with gain magnitude
        prior_price = normalize_currency(ctx.appraisal.value("subject_grid_prior_sale_price"))
        current_val = normalize_currency(ctx.appraisal.value("appraised_value"))
        gain_threshold = float(qc_config.semantic("sca_psh_large_gain_pct", 30.0))
        ev2 = ev + [ctx.appraisal.evidence("appraised_value"),
                    ctx.appraisal.evidence("subject_grid_prior_sale_price")]
        if prior_price and current_val and prior_price > 0:
            gain_pct = (current_val - prior_price) / prior_price * 100.0
            if gain_pct >= gain_threshold:
                return RuleResult(rule_id="SCA-PSH", checklist_num="80", section="sales_comparison",
                                  status=RuleStatus.VERIFY,
                                  message=qc_config.template("SCA-PSH-largegain",
                                                             months=months,
                                                             gain=int(gain_pct),
                                                             prior=int(prior_price),
                                                             current=int(current_val)),
                                  fields_involved=["subject_grid_prior_sale_date",
                                                   "subject_grid_prior_sale_price",
                                                   "appraised_value"],
                                  template_id="SCA-PSH-largegain", evidence=ev2, confidence=0.9)
        return RuleResult(rule_id="SCA-PSH", checklist_num="80", section="sales_comparison",
                          status=RuleStatus.VERIFY,
                          message=qc_config.template("SCA-PSH-subj", months=months),
                          fields_involved=["subject_grid_prior_sale_date"], template_id="SCA-PSH-subj",
                          evidence=ev, confidence=0.7)
    return RuleResult(rule_id="SCA-PSH", checklist_num="80", section="sales_comparison",
                      status=RuleStatus.PASS, fields_involved=["subject_grid_prior_sale_date"], evidence=ev)


# ---- SCA-PSH-Q subject sale/listing history analysis quality ----------------
# Engagement letter: "Simply typing dates and amounts does not meet USPAP
# requirements. Explain how the listings, contracts, and sales relate to each
# other and to the opinion of value."
# Fire only when a prior sale exists within the window (otherwise not applicable).

_PSH_ANALYSIS_TERMS = re.compile(
    r"(below\s+(list|asking)|above\s+(list|asking)|days?\s+on\s+market|dom\b|"
    r"indicat(es?|ive)|reflect(s|ing)|consistent\s+with|supports?|"
    r"compet(itive|ition)|market(ing)?\s+(time|condition)|"
    r"list[\s-]*to[\s-]*(sale|contract)|gap\s+between|percent|%)",
    re.I)


@rule(id="SCA-PSH-Q", num="80b2", section="sales_comparison", phase=5,
      name="Subject sale history analysis is substantive")
def sca_subject_prior_sale_quality(ctx: QCContext):
    """When a prior sale/listing exists within the look-back window, the analysis
    must go beyond bare dates and amounts — the engagement letter (Equity Solutions
    USA / Champions Funding) explicitly warns that 'simply typing dates and amounts
    does not meet USPAP requirements.' Check the sales-comparison or reconciliation
    narrative for substantive analysis keywords."""
    window = int(qc_config.semantic("comp_resale_window_months", 36))
    eff = _effective_ym(ctx)
    d = _parse_full_date(ctx.appraisal.value("subject_grid_prior_sale_date"))
    if d is None or eff is None:
        return RuleResult(rule_id="SCA-PSH-Q", checklist_num="80b2", section="sales_comparison",
                          status=RuleStatus.NOT_APPLICABLE,
                          message="No prior sale/transfer within the look-back window; quality check not applicable.")
    months = (eff[0] - d[0]) * 12 + (eff[1] - d[1])
    if months < 0 or months > window:
        return RuleResult(rule_id="SCA-PSH-Q", checklist_num="80b2", section="sales_comparison",
                          status=RuleStatus.NOT_APPLICABLE,
                          message="No prior sale/transfer within the look-back window; quality check not applicable.")
    # Prior sale IS within the window — check narrative quality.
    narrative = " ".join(str(ctx.appraisal.value(f) or "") for f in (
        "sales_comparison_summary", "final_reconciliation_comment",
        "contract_analysis_comment", "market_conditions_commentary"))
    ev = [ctx.appraisal.evidence("sales_comparison_summary"),
          ctx.appraisal.evidence("subject_grid_prior_sale_date")]
    if _PSH_ANALYSIS_TERMS.search(narrative):
        return RuleResult(rule_id="SCA-PSH-Q", checklist_num="80b2", section="sales_comparison",
                          status=RuleStatus.PASS,
                          fields_involved=["sales_comparison_summary"], evidence=ev)
    return RuleResult(rule_id="SCA-PSH-Q", checklist_num="80b2", section="sales_comparison",
                      status=RuleStatus.VERIFY,
                      message=qc_config.template("SCA-PSH-Q-quality"),
                      fields_involved=["sales_comparison_summary", "subject_grid_prior_sale_date"],
                      template_id="SCA-PSH-Q-quality", evidence=ev, confidence=0.6)


# ---- SCA-FLIP comparable resale within 36 months (non-arm's-length flag) ---

@rule(id="SCA-FLIP", num="80b", section="sales_comparison", phase=3, name="Comp rapid resale flag")
def sca_comp_resale(ctx: QCContext):
    """A comparable that itself resold within 36 months of its own sale date may be a
    flip / non-arm's-length transaction and warrants explanation (MIRA gap)."""
    window = int(qc_config.semantic("comp_resale_window_months", 36))
    flagged = []
    out = []
    idx = _comp_indices(ctx)
    for i in idx:
        prior = _parse_full_date(ctx.appraisal.value(f"comp_{i}_prior_sale_date"))
        if prior is None:
            continue  # no prior sale → arm's-length, fine
        sd = _parse_uad_date(ctx.appraisal.value(f"comp_{i}_sale_date") or "")
        cur = sd.get("s") or sd.get("c") or _effective_ym(ctx)
        if cur is None:
            continue
        months = (cur[0] - prior[0]) * 12 + (cur[1] - prior[1])
        if 0 <= months <= window:
            ev = [ctx.appraisal.evidence(f"comp_{i}_prior_sale_date"),
                  ctx.appraisal.evidence(f"comp_{i}_sale_date")]
            flagged.append(i)
            _fv = layer_b.assess(
                ctx, concern="comp_selection",
                base_message=qc_config.template("SCA-FLIP-comp", comp=i, months=months),
                facts=f"comp {i} resold within {window} months (possible flip)")
            out.append(RuleResult(rule_id="SCA-FLIP", checklist_num="80b", section="sales_comparison",
                                  status=_fv.status, reasoning=_fv.reasoning, confidence=_fv.confidence,
                                  message=_fv.message,
                                  fields_involved=[f"comp_{i}_prior_sale_date"], template_id="SCA-FLIP-comp",
                                  evidence=ev))
    # One PASS for observability when comps exist and none resold within the window.
    if idx and not flagged:
        out.append(RuleResult(rule_id="SCA-FLIP", checklist_num="80b", section="sales_comparison",
                              status=RuleStatus.PASS, fields_involved=["comp_N_prior_sale_date"],
                              evidence=[ctx.appraisal.evidence(f"comp_{idx[0]}_prior_sale_date")]))
    return out


# ---- SCA-25 new construction needs a competing-development comp -----------

def _is_new_construction(ctx: QCContext) -> bool:
    """Subject reads as new construction: year built within 1 year of the effective
    date, OR a C1 (new) condition rating, OR an explicit Proposed/Under Const status."""
    status = str(ctx.appraisal.value("property_status") or ctx.appraisal.value("status") or "").lower()
    if "proposed" in status or "under const" in status or "new const" in status:
        return True
    if str(ctx.appraisal.value("condition_rating") or "").upper() == "C1":
        return True
    eff = _effective_ym(ctx)
    yb = normalize_currency(ctx.appraisal.value("year_built"))
    if eff and yb and 0 <= eff[0] - int(yb) <= 1:
        return True
    return False


@rule(id="SCA-25", num="81", section="sales_comparison", phase=3, name="New construction competing comp")
def sca25_new_construction(ctx: QCContext):
    """When the subject is new construction, at least one comparable should come from a
    competing development. Subdivision identity cannot be matched deterministically from
    the grid, so a confirmed new-construction subject routes to VERIFY for the reviewer
    to confirm a competing-development comp (or the dated-sale exception)."""
    if not _is_new_construction(ctx):
        return RuleResult(rule_id="SCA-25", checklist_num="81", section="sales_comparison",
                          status=RuleStatus.NOT_APPLICABLE,
                          message="subject is not new construction", fields_involved=["year_built"])
    ev = [ctx.appraisal.evidence("year_built"), ctx.appraisal.evidence("condition_rating")]
    return RuleResult(rule_id="SCA-25", checklist_num="81", section="sales_comparison",
                      status=RuleStatus.VERIFY, message=qc_config.template("SCA-25-newconst"),
                      fields_involved=["year_built", "condition_rating"],
                      template_id="SCA-25-newconst", evidence=ev, confidence=0.6)


# ---- SCA-26 subject GLA bracketed by the comparable GLAs ------------------

def _subject_gla(ctx: QCContext):
    return normalize_currency(ctx.appraisal.value("subject_grid_gla") or ctx.appraisal.value("gla"))


@rule(id="SCA-26", num="82", section="sales_comparison", phase=3, name="Subject GLA bracketed by comps")
def sca26_gla_bracket(ctx: QCContext):
    """Sound square-footage methodology brackets the subject's GLA with comparables of
    both larger and smaller GLA. A subject GLA outside the comps' GLA range signals the
    comps may not support the size (or a below-grade/area methodology issue) — VERIFY."""
    subj = _subject_gla(ctx)
    glas = [normalize_currency(ctx.appraisal.value(f"comp_{i}_gla")) for i in _comp_indices(ctx)]
    glas = [g for g in glas if g and g > 0]
    ev = [ctx.appraisal.evidence("gla")] + \
         [ctx.appraisal.evidence(f"comp_{i}_gla") for i in _comp_indices(ctx)[:3]]
    if subj is None or len(glas) < 2:
        # Same rationale as SCA-BR: can't test bracketing without the grid GLAs.
        return RuleResult(rule_id="SCA-26", checklist_num="82", section="sales_comparison",
                          status=RuleStatus.VERIFY,
                          message="Comparable GLA values could not be read to test bracketing; please verify the subject GLA falls within the range of the comparable GLAs.",
                          fields_involved=["gla", "comp_N_gla"], evidence=ev, confidence=0.5)
    if min(glas) <= subj <= max(glas):
        return RuleResult(rule_id="SCA-26", checklist_num="82", section="sales_comparison",
                          status=RuleStatus.PASS, fields_involved=["gla", "comp_N_gla"], evidence=ev)
    v = layer_b.assess(
        ctx, concern="comp_selection",
        base_message=qc_config.template("SCA-26-gla", subj=int(subj),
                                        lo=int(min(glas)), hi=int(max(glas))),
        facts="the subject GLA is not bracketed by the comparable GLAs")
    return RuleResult(rule_id="SCA-26", checklist_num="82", section="sales_comparison",
                      status=v.status, message=v.message, reasoning=v.reasoning,
                      fields_involved=["gla", "comp_N_gla"], template_id="SCA-26-gla",
                      evidence=ev, confidence=v.confidence)


# ---- SCA-23 listing comparables should carry a list-to-sale adjustment -----

@rule(id="SCA-23", num="83", section="sales_comparison", phase=3, name="Listing comp adjustment")
def sca23_listing_adjustment(ctx: QCContext):
    """A listing/active comparable (UAD 'Active' in Date of Sale) is priced at LIST,
    which typically exceeds the eventual sale price — so it should carry a downward
    adjustment (or commentary). A listing comp with no net adjustment -> VERIFY."""
    out = []
    any_listing = False
    for i in _comp_indices(ctx):
        sd = str(ctx.appraisal.value(f"comp_{i}_sale_date") or "")
        if "active" not in sd.lower():
            continue  # closed sale — not a listing
        any_listing = True
        net = normalize_currency(ctx.appraisal.value(f"comp_{i}_net_adjustment"))
        ev = [ctx.appraisal.evidence(f"comp_{i}_sale_date"),
              ctx.appraisal.evidence(f"comp_{i}_net_adjustment")]
        if net is None or net == 0:
            out.append(RuleResult(rule_id="SCA-23", checklist_num="83", section="sales_comparison",
                                  status=RuleStatus.VERIFY, message=qc_config.template("SCA-23-listing", comp=i),
                                  fields_involved=[f"comp_{i}_net_adjustment"], template_id="SCA-23-listing",
                                  evidence=ev, confidence=0.6))
        else:
            out.append(RuleResult(rule_id="SCA-23", checklist_num="83", section="sales_comparison",
                                  status=RuleStatus.PASS, fields_involved=[f"comp_{i}_net_adjustment"], evidence=ev))
    if not any_listing:
        return RuleResult(rule_id="SCA-23", checklist_num="83", section="sales_comparison",
                          status=RuleStatus.NOT_APPLICABLE, message="no listing/active comparables")
    return out


# ---- SCA-18 basement present (per comp, UAD format) ------------------------

@rule(id="SCA-18", num="70", section="sales_comparison", phase=3, name="Comp basement present")
def sca18_basement(ctx: QCContext):
    """The Basement & Finished Rooms Below Grade row must be populated for each comp
    (UAD: finished sqft + components, or '0sf'/'None'). Blank -> VERIFY."""
    return _per_comp_field(ctx, "SCA-18", "70", "basement", "SCA-18-bsmt",
                           lambda v: bool(re.search(r"\d", v)) or v.lower() in ("none", "0", "nobsmt"))


# ---- SCA-15 subject actual age consistent with year built -----------------

@rule(id="SCA-15", num="67", section="sales_comparison", phase=3, name="Subject actual age vs year built")
def sca15_actual_age(ctx: QCContext):
    """The subject's Actual Age in the grid must agree with (effective year - year
    built), within a 2-year tolerance for mid-year effective dates. A large gap is a
    data-entry/OCR error (MIRA SCA-15). Comp year-built is not on the URAR grid, so
    this is a subject-level check."""
    age = normalize_currency(ctx.appraisal.value("subject_grid_actual_age"))
    yb = normalize_currency(ctx.appraisal.value("year_built"))
    eff = _effective_ym(ctx)
    ev = [ctx.appraisal.evidence("subject_grid_actual_age"), ctx.appraisal.evidence("year_built")]
    if age is None or yb is None or eff is None or yb < 1700:
        return RuleResult(rule_id="SCA-15", checklist_num="67", section="sales_comparison",
                          status=RuleStatus.VERIFY,
                          message="Actual age, year built, or effective date could not all be read; please verify the subject age against the year built.",
                          fields_involved=["subject_grid_actual_age", "year_built"], evidence=ev, confidence=0.5)
    expected = eff[0] - int(yb)
    if abs(int(age) - expected) <= 2:
        return RuleResult(rule_id="SCA-15", checklist_num="67", section="sales_comparison",
                          status=RuleStatus.PASS, fields_involved=["subject_grid_actual_age", "year_built"], evidence=ev)
    return RuleResult(rule_id="SCA-15", checklist_num="67", section="sales_comparison",
                      status=RuleStatus.VERIFY,
                      message=qc_config.template("SCA-15-age", age=int(age), exp=expected, yb=int(yb)),
                      fields_involved=["subject_grid_actual_age", "year_built"],
                      template_id="SCA-15-age", evidence=ev, confidence=0.7)


# ---- SCA-ZF free-text grid feature: adjustment without a difference --------

# (field suffix, display label) for the adjustable descriptive rows. The discrete
# graded rows (condition/quality) are handled by SCA-16/SCA-14; here we only flag the
# HIGH-PRECISION direction — comp value identical to the subject (or "Similar") yet a
# non-zero adjustment was applied. The opposite direction (different + no adjustment)
# is intentionally NOT flagged: free-text equality is too fuzzy to assert safely (P-6).
_ZF_FIELDS = [("location_rating", "Location"), ("site_size", "Site"), ("view", "View"),
              ("design", "Design"), ("heating_cooling", "Heating/Cooling"),
              ("garage_carport", "Garage"), ("porch_patio_deck", "Porch/Patio")]


def _norm_feat(v) -> str:
    return re.sub(r"[^a-z0-9]", "", str(v or "").lower())


@rule(id="SCA-ZF", num="76b", section="sales_comparison", phase=3, name="Feature adjustment without difference")
def sca_zf_consistency(ctx: QCContext):
    """Zero-adjustment consistency for the free-text grid rows (MIRA): when a comp's
    feature is identical to the subject (or marked 'Similar') yet a dollar adjustment
    was applied, surface it for review. High-precision (exact match only)."""
    out = []
    checked = False
    for field, label in _ZF_FIELDS:
        subj = _norm_feat(ctx.appraisal.value(f"subject_grid_{field}"))
        if not subj:
            continue
        for i in _comp_indices(ctx):
            cv = _norm_feat(ctx.appraisal.value(f"comp_{i}_{field}"))
            adj = normalize_currency(ctx.appraisal.value(f"comp_{i}_{field}_adjustment"))
            if not cv or adj is None or adj == 0:
                continue
            checked = True
            if cv == subj or cv in ("similar", "sim"):
                ev = [ctx.appraisal.evidence(f"comp_{i}_{field}"),
                      ctx.appraisal.evidence(f"comp_{i}_{field}_adjustment")]
                _zv = layer_b.assess(
                    ctx, concern="adjustment_consistency",
                    base_message=qc_config.template("SCA-zf-same", comp=i, field=label, a=int(adj)),
                    facts=f"comp {i} received a ${int(adj)} {label} adjustment despite matching the subject")
                out.append(RuleResult(rule_id="SCA-ZF", checklist_num="76b", section="sales_comparison",
                                      status=_zv.status, reasoning=_zv.reasoning, confidence=_zv.confidence,
                                      message=_zv.message,
                                      fields_involved=[f"comp_{i}_{field}", f"comp_{i}_{field}_adjustment"],
                                      template_id="SCA-zf-same", evidence=ev))
    if checked and not out:
        out.append(RuleResult(rule_id="SCA-ZF", checklist_num="76b", section="sales_comparison",
                              status=RuleStatus.PASS, fields_involved=["comp_N_*_adjustment"]))
    return out


# ---- SCA-AC adjustment applied consistently across comparables -------------

@rule(id="SCA-AC", num="76c", section="sales_comparison", phase=3,
      name="Adjustment applied consistently across comps")
def sca_adjustment_consistency(ctx: QCContext):
    """Cross-comp consistency (the inverse of SCA-ZF): when several comparables
    share the SAME value for a feature but a dollar adjustment was applied to some
    and not others, flag the comps that are MISSING the adjustment — the appraiser
    must apply adjustments consistently or explain the difference. High precision:
    only same-value groups where at least one peer carries a non-zero adjustment."""
    out = []
    for field, label in _ZF_FIELDS:
        groups: Dict[str, list] = {}
        for i in _comp_indices(ctx):
            cv = _norm_feat(ctx.appraisal.value(f"comp_{i}_{field}"))
            if not cv:
                continue
            adj = normalize_currency(ctx.appraisal.value(f"comp_{i}_{field}_adjustment"))
            groups.setdefault(cv, []).append((i, adj))
        for members in groups.values():
            if len(members) < 2:
                continue
            adjusted = [(i, a) for i, a in members if a]   # carries a non-zero adjustment
            unadjusted = [i for i, a in members if not a]  # zero / not applied
            if not adjusted or not unadjusted:
                continue
            peer_adj = int(adjusted[0][1])
            for i in unadjusted:
                ev = [ctx.appraisal.evidence(f"comp_{i}_{field}"),
                      ctx.appraisal.evidence(f"comp_{i}_{field}_adjustment")]
                _av = layer_b.assess(
                    ctx, concern="adjustment_consistency",
                    base_message=qc_config.template("SCA-ac-inconsistent", comp=i, field=label,
                                                    value=ctx.appraisal.value(f"comp_{i}_{field}"),
                                                    a=peer_adj),
                    facts=f"comp {i} got no {label} adjustment while peers received ${peer_adj}")
                out.append(RuleResult(rule_id="SCA-AC", checklist_num="76c", section="sales_comparison",
                                      status=_av.status, reasoning=_av.reasoning, confidence=_av.confidence,
                                      message=_av.message,
                                      fields_involved=[f"comp_{i}_{field}", f"comp_{i}_{field}_adjustment"],
                                      template_id="SCA-ac-inconsistent", evidence=ev))
    return out


# ---------------------------------------------------------------------------
# Vision-backed comparable-photo rules (Google Cloud Vision). The imagery is
# annotated in extraction (_overlay_comp_photos) into pseudo-fields; these rules
# only read them (P-3). When vision is not configured they degrade to VERIFY/
# SKIPPED — never a false PASS (P-6).
# ---------------------------------------------------------------------------

def _flag(ctx: QCContext, name: str) -> bool:
    return str(ctx.appraisal.value(name) or "").strip().lower() in ("true", "yes", "1")


@rule(id="SCA-27", num="126", section="sales_comparison", phase=3, name="Comparable photos present + type")
def sca27_comp_photos(ctx: QCContext):
    """Comparable photos must be present; for FHA they must be the appraiser's own
    drive-by photos (not MLS listing photos). With Cloud Vision we confirm the page
    depicts buildings and detect MLS/realtor watermark text on FHA loans."""
    try:
        pages = int(str(ctx.appraisal.value("comp_photo_pages") or "0").strip() or "0")
    except ValueError:
        pages = 0
    ev = [ctx.appraisal.evidence("comp_photo_pages")]
    if pages == 0:
        return RuleResult(rule_id="SCA-27", checklist_num="126", section="sales_comparison",
                          status=RuleStatus.VERIFY, message=qc_config.template("SCA-27-missing"),
                          fields_involved=["comp_photo_pages"], template_id="SCA-27-missing",
                          evidence=ev, confidence=0.55)
    if not _flag(ctx, "vision_enabled") or _flag(ctx, "comp_photo_vision_error"):
        # Photos exist but the imagery could not be analyzed (vision off or a
        # transient outage) — route the drive-by/MLS/building judgement to a reviewer.
        return RuleResult(rule_id="SCA-27", checklist_num="126", section="sales_comparison",
                          status=RuleStatus.VERIFY, message=qc_config.template("SCA-27-defer", pages=pages),
                          fields_involved=["comp_photo_pages"], template_id="SCA-27-defer",
                          evidence=ev, confidence=0.5)
    if not _flag(ctx, "comp_photo_building"):
        return RuleResult(rule_id="SCA-27", checklist_num="126", section="sales_comparison",
                          status=RuleStatus.VERIFY, message=qc_config.template("SCA-27-nobuilding"),
                          fields_involved=["comp_photo_building"], template_id="SCA-27-nobuilding",
                          evidence=ev, confidence=0.6)
    if ctx.loan_type == "fha" and _flag(ctx, "comp_photo_mls_text"):
        return RuleResult(rule_id="SCA-27", checklist_num="126", section="sales_comparison",
                          status=RuleStatus.VERIFY, message=qc_config.template("SCA-27-mls"),
                          fields_involved=["comp_photo_mls_text"], template_id="SCA-27-mls",
                          evidence=[ctx.appraisal.evidence("comp_photo_mls_text")], confidence=0.65)
    return RuleResult(rule_id="SCA-27", checklist_num="126", section="sales_comparison",
                      status=RuleStatus.PASS, fields_involved=["comp_photo_pages", "comp_photo_building"],
                      evidence=ev)


def _cond_num(v) -> "int | None":
    m = re.fullmatch(r"C([1-6])", str(v or "").strip().upper())
    return int(m.group(1)) if m else None


@rule(id="SCA-16V", num="68b", section="sales_comparison", phase=3, name="Comp photo condition cross-check")
def sca16v_photo_condition(ctx: QCContext):
    """Vision cross-check on the comparable photos (MIRA SCA-16 image layer):
      • distress imagery (boarded-up, tarped, derelict, demolition) -> VERIFY;
      • the apparent condition read from the photos materially WORSE (>=2 UAD grades)
        than every reported grid condition -> VERIFY (the imagery contradicts the
        ratings).
    SKIPPED when vision is off or the imagery could not be analyzed (the grid SCA-16
    still covers the UAD rating)."""
    if not _flag(ctx, "vision_enabled") or _flag(ctx, "comp_photo_vision_error"):
        return RuleResult(rule_id="SCA-16V", checklist_num="68b", section="sales_comparison",
                          status=RuleStatus.SKIPPED, message="vision unavailable for photo condition")
    ev = [ctx.appraisal.evidence("comp_photo_distress"), ctx.appraisal.evidence("comp_photo_condition")]
    if _flag(ctx, "comp_photo_distress"):
        return RuleResult(rule_id="SCA-16V", checklist_num="68b", section="sales_comparison",
                          status=RuleStatus.VERIFY, message=qc_config.template("SCA-16V-distress"),
                          fields_involved=["comp_photo_distress"], template_id="SCA-16V-distress",
                          evidence=ev, confidence=0.6)
    vis = _cond_num(ctx.appraisal.value("comp_photo_condition"))
    if vis is not None:
        rated = [_cond_num(ctx.appraisal.value(f"comp_{i}_condition_rating")) for i in _comp_indices(ctx)]
        rated.append(_cond_num(ctx.appraisal.value("condition_rating")))
        rated = [c for c in rated if c is not None]
        # vision condition is the WORST seen on the page; flag only if it is worse than
        # the worst RATED condition by >=2 grades (a real imagery-vs-rating conflict).
        if rated and vis - max(rated) >= 2:
            return RuleResult(rule_id="SCA-16V", checklist_num="68b", section="sales_comparison",
                              status=RuleStatus.VERIFY,
                              message=qc_config.template("SCA-16V-cond", vis=f"C{vis}", rated=f"C{max(rated)}"),
                              fields_involved=["comp_photo_condition", "comp_N_condition_rating"],
                              template_id="SCA-16V-cond", evidence=ev, confidence=0.6)
    return RuleResult(rule_id="SCA-16V", checklist_num="68b", section="sales_comparison",
                      status=RuleStatus.PASS, fields_involved=["comp_photo_distress", "comp_photo_condition"],
                      evidence=ev)
