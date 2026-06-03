"""
Sales Comparison Approach rules (SCA / checklist 53-88).

Scope note: the per-comparable GRID CELLS (address, proximity, data source,
date-of-sale, the "0 if no adjustment" line items) are not yet extracted
reliably (comp_N_* template fields are noisy; comp_N_gla currently holds the
adjustment, not GLA). So the grid-cell rules (SCA-3/4/5/6/7/8/9/11/12/...) are
DEFERRED until comp-grid extraction improves — see TASK_HISTORY.txt.

Implemented here are the SCA checks supported by the reliable Camelot indexed
fields comp_{1..6}_sale_price / _net_adjustment / _adjusted_sale_price:
  SCA-2  comparables required (count + value threshold)
  SCA-NET  net adjustment must not exceed 15% of the comp sale price
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
    """'s12/25;c11/25' → {'s': (25,12), 'c': (25,11)} as (yy, mm) for ordering."""
    res = {}
    for kind, mm, yy in re.findall(r"([sc])\s*(\d{1,2})/(\d{2,4})", tok or "", re.I):
        res[kind.lower()] = (int(yy), int(mm))
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


# ---- SCA-16 condition rating present + UAD format (per comp) --------------

@rule(id="SCA-16", num="68", section="sales_comparison", phase=3, name="Comp condition UAD rating")
def sca16_condition(ctx: QCContext):
    out = []
    for i in _comp_indices(ctx):
        val = (ctx.appraisal.value(f"comp_{i}_condition_rating") or "").upper()
        ev = [ctx.appraisal.evidence(f"comp_{i}_condition_rating")]
        if re.fullmatch(r"C[1-6]", val):
            out.append(RuleResult(rule_id="SCA-16", checklist_num="68", section="sales_comparison",
                                  status=RuleStatus.PASS, fields_involved=[f"comp_{i}_condition_rating"], evidence=ev))
        else:
            out.append(RuleResult(rule_id="SCA-16", checklist_num="68", section="sales_comparison",
                                  status=RuleStatus.VERIFY,
                                  message=qc_config.template("SCA-16-cond", comp=i),
                                  fields_involved=[f"comp_{i}_condition_rating"], template_id="SCA-16-cond",
                                  evidence=ev, confidence=0.65))
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
