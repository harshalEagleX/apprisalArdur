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

from app.qc.config import qc_config
from app.qc.context import QCContext
from app.qc.matching import normalize_currency
from app.qc.registry import rule
from app.qc.result import RuleResult, RuleStatus

_MAX_COMPS = 6


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
        rows.append({
            "i": i,
            "sale_price": sp,
            "net": normalize_currency(ctx.appraisal.value(f"comp_{i}_net_adjustment")),
            "adjusted": normalize_currency(ctx.appraisal.value(f"comp_{i}_adjusted_sale_price")),
            "is_listing": str(ctx.appraisal.value(f"comp_{i}_is_listing") or "").lower()
                          in {"true", "yes", "1"},
        })
    return rows


# ---- SCA-2 comparables required -------------------------------------------

@rule(id="SCA-2", num="54", section="sales_comparison", phase=3, name="Minimum comparable sales")
def sca2_required(ctx: QCContext):
    rows = _comp_rows(ctx)
    sales = [r for r in rows if not r["is_listing"]]
    val = normalize_currency(ctx.appraisal.value("appraised_value")) or 0
    required = 4 if val >= 1_000_000 else 3
    ev = [ctx.appraisal.evidence(f"comp_{i}_sale_price") for i in range(1, 4)]
    if len(sales) >= required:
        return RuleResult(rule_id="SCA-2", checklist_num="54", section="sales_comparison",
                          status=RuleStatus.PASS, fields_involved=["comp_N_sale_price"], evidence=ev)
    # extraction may miss comps → VERIFY, not hard FAIL
    return RuleResult(rule_id="SCA-2", checklist_num="54", section="sales_comparison",
                      status=RuleStatus.VERIFY,
                      message=qc_config.template("SCA-2-count", value=len(sales)),
                      fields_involved=["comp_N_sale_price"], template_id="SCA-2-count",
                      evidence=ev, confidence=0.6)


# ---- SCA-NET net adjustment <= 15% of sale price --------------------------

@rule(id="SCA-NET", num="77", section="sales_comparison", phase=3, name="Net adjustment within 15%")
def sca_net_adjustment(ctx: QCContext):
    rows = _comp_rows(ctx)
    cap = qc_config.semantic("net_adjustment_pct", 15.0)
    over = []
    for r in rows:
        if r["net"] is None or not r["sale_price"]:
            continue
        pct = abs(r["net"]) / r["sale_price"] * 100.0
        if pct > cap:
            over.append(r["i"])
    ev = [ctx.appraisal.evidence(f"comp_{i}_net_adjustment") for i in range(1, 4)]
    if not rows:
        return RuleResult(rule_id="SCA-NET", checklist_num="77", section="sales_comparison",
                          status=RuleStatus.SKIPPED, message="comp adjustments not extracted", evidence=ev)
    if not over:
        return RuleResult(rule_id="SCA-NET", checklist_num="77", section="sales_comparison",
                          status=RuleStatus.PASS, fields_involved=["comp_N_net_adjustment"], evidence=ev)
    return RuleResult(rule_id="SCA-NET", checklist_num="77", section="sales_comparison",
                      status=RuleStatus.VERIFY,
                      message=qc_config.template("SCA-net15", value=", ".join(map(str, over))),
                      fields_involved=["comp_N_net_adjustment"], template_id="SCA-net15",
                      evidence=ev, confidence=0.65)


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

@rule(id="SCA-5", num="57", section="sales_comparison", phase=3, name="Comp data source present")
def sca5_data_source(ctx: QCContext):
    out = []
    for i in _comp_indices(ctx):
        val = ctx.appraisal.value(f"comp_{i}_data_source")
        ev = [ctx.appraisal.evidence(f"comp_{i}_data_source")]
        if val and re.search(r"(mls|#|dom|\d)", val.lower()):
            out.append(RuleResult(rule_id="SCA-5", checklist_num="57", section="sales_comparison",
                                  status=RuleStatus.PASS, fields_involved=[f"comp_{i}_data_source"], evidence=ev))
        else:
            out.append(RuleResult(rule_id="SCA-5", checklist_num="57", section="sales_comparison",
                                  status=RuleStatus.VERIFY,
                                  message=qc_config.template("SCA-5-ds", comp=i),
                                  fields_involved=[f"comp_{i}_data_source"], template_id="SCA-5-ds",
                                  evidence=ev, confidence=0.6))
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

@rule(id="SCA-16", num="68", section="sales_comparison", phase=3, name="Comp condition UAD rating")
def sca16_condition(ctx: QCContext):
    out = []
    subj = (ctx.appraisal.value("condition_rating") or "").upper()
    subj_n = int(subj[1]) if re.fullmatch(r"C[1-6]", subj) else None
    for i in _comp_indices(ctx):
        val = (ctx.appraisal.value(f"comp_{i}_condition_rating") or "").upper()
        ev = [ctx.appraisal.evidence(f"comp_{i}_condition_rating")]
        if not re.fullmatch(r"C[1-6]", val):
            out.append(RuleResult(rule_id="SCA-16", checklist_num="68", section="sales_comparison",
                                  status=RuleStatus.VERIFY,
                                  message=qc_config.template("SCA-16-cond", comp=i),
                                  fields_involved=[f"comp_{i}_condition_rating"], template_id="SCA-16-cond",
                                  evidence=ev, confidence=0.65))
            continue
        # present + valid format → check consistency against the subject. A gap of
        # 2+ UAD grades (e.g. subject C3 vs comp C5) should carry a condition adjustment.
        comp_n = int(val[1])
        if subj_n is not None and abs(comp_n - subj_n) >= 2:
            ev = ev + [ctx.appraisal.evidence("condition_rating")]
            out.append(RuleResult(rule_id="SCA-16", checklist_num="68", section="sales_comparison",
                                  status=RuleStatus.VERIFY,
                                  message=qc_config.template("SCA-16-consist", comp=i,
                                                             comp_c=val, subj_c=subj, delta=abs(comp_n - subj_n)),
                                  fields_involved=[f"comp_{i}_condition_rating", "condition_rating"],
                                  template_id="SCA-16-consist", evidence=ev, confidence=0.7))
        else:
            out.append(RuleResult(rule_id="SCA-16", checklist_num="68", section="sales_comparison",
                                  status=RuleStatus.PASS, fields_involved=[f"comp_{i}_condition_rating"], evidence=ev))
    return out


# ---- SCA-BR market value bracketed by adjusted sale prices ----------------

@rule(id="SCA-BR", num="78", section="sales_comparison", phase=3, name="Value bracketed by adjusted prices")
def sca_bracket(ctx: QCContext):
    rows = _comp_rows(ctx)
    adj = [r["adjusted"] for r in rows if r["adjusted"] is not None]
    val = normalize_currency(ctx.appraisal.value("appraised_value"))
    ev = [ctx.appraisal.evidence("appraised_value")] + \
         [ctx.appraisal.evidence(f"comp_{i}_adjusted_sale_price") for i in range(1, 4)]
    if val is None or len(adj) < 2:
        return RuleResult(rule_id="SCA-BR", checklist_num="78", section="sales_comparison",
                          status=RuleStatus.SKIPPED,
                          message="insufficient adjusted prices to test bracketing", evidence=ev)
    if min(adj) <= val <= max(adj):
        return RuleResult(rule_id="SCA-BR", checklist_num="78", section="sales_comparison",
                          status=RuleStatus.PASS, fields_involved=["appraised_value"], evidence=ev)
    # bracketing failures are often partial-extraction artifacts → VERIFY
    return RuleResult(rule_id="SCA-BR", checklist_num="78", section="sales_comparison",
                      status=RuleStatus.VERIFY, message=qc_config.template("SCA-bracket"),
                      fields_involved=["appraised_value", "comp_N_adjusted_sale_price"],
                      template_id="SCA-bracket", evidence=ev, confidence=0.6)
