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
    return RuleResult(rule_id="SCA-NET", checklist_num="77", section="sales_comparison",
                      status=RuleStatus.VERIFY,
                      message=qc_config.template("SCA-net15", value=", ".join(map(str, over))),
                      fields_involved=["comp_N_net_adjustment"], template_id="SCA-net15",
                      evidence=ev, confidence=0.65)


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
    return RuleResult(rule_id="SCA-GROSS", checklist_num="77b", section="sales_comparison",
                      status=RuleStatus.VERIFY,
                      message=qc_config.template("SCA-gross25", value=", ".join(map(str, over))),
                      fields_involved=["comp_N_gross_adj_pct"], template_id="SCA-gross25",
                      evidence=ev, confidence=0.7)


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


@rule(id="SCA-9", num="61", section="sales_comparison", phase=3, name="Comp location UAD format")
def sca9_location(ctx: QCContext):
    return _per_comp_field(ctx, "SCA-9", "61", "location_rating", "SCA-9-loc",
                           lambda v: ";" in v and bool(re.match(r"[A-Za-z]", v)))


@rule(id="SCA-11", num="63", section="sales_comparison", phase=3, name="Comp site size has unit")
def sca11_site(ctx: QCContext):
    return _per_comp_field(ctx, "SCA-11", "63", "site_size", "SCA-11-site",
                           lambda v: bool(re.search(r"\d", v)) and bool(re.search(r"(sf|ac|acre|sq)", v.lower())))


@rule(id="SCA-12", num="64", section="sales_comparison", phase=3, name="Comp view UAD format")
def sca12_view(ctx: QCContext):
    return _per_comp_field(ctx, "SCA-12", "64", "view", "SCA-12-view",
                           lambda v: ";" in v and bool(re.match(r"[A-Za-z]", v)))


@rule(id="SCA-14", num="66", section="sales_comparison", phase=3, name="Comp quality UAD rating + zero-adj")
def sca14_quality(ctx: QCContext):
    return _grade_consistency_rule(ctx, "SCA-14", "66", "quality_rating", "Q", "quality", "SCA-14-qual")


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
    """Each comp should have sold within 12 months of the effective date; older
    sales require commentary (VERIFY)."""
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
            out.append(RuleResult(rule_id="SCA-DC", checklist_num="60b", section="sales_comparison",
                                  status=RuleStatus.VERIFY,
                                  message=qc_config.template("SCA-DC-old", comp=i, months=months),
                                  fields_involved=[f"comp_{i}_sale_date"], template_id="SCA-DC-old",
                                  evidence=ev, confidence=0.7))
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
            out.append(RuleResult(rule_id="SCA-PR", checklist_num="79", section="sales_comparison",
                                  status=RuleStatus.VERIFY,
                                  message=qc_config.template("SCA-PR-bracket", comp=i, a=int(sp), b=int(val)),
                                  fields_involved=[f"comp_{i}_sale_price"], template_id="SCA-PR-bracket",
                                  evidence=ev, confidence=0.6))
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
            out.append(RuleResult(rule_id="SCA-7", checklist_num="59", section="sales_comparison",
                                  status=RuleStatus.VERIFY,
                                  message=qc_config.template("SCA-7-conc", comp=i, a=conc),
                                  fields_involved=[f"comp_{i}_sale_financing"], template_id="SCA-7-conc",
                                  evidence=ev, confidence=0.65))
        else:
            out.append(RuleResult(rule_id="SCA-7", checklist_num="59", section="sales_comparison",
                                  status=RuleStatus.PASS, fields_involved=[f"comp_{i}_sale_financing"], evidence=ev))
    return out


@rule(id="SCA-17", num="69", section="sales_comparison", phase=3,
      name="Subject grid matches improvements (GLA/condition/quality)")
def sca17_subject_consistency(ctx: QCContext):
    """The subject column of the sales grid must agree with the dedicated sections
    (a transcription discrepancy between the grid and Improvements/Site)."""
    out = []
    checks = [("subject_grid_gla", "gla", "GLA", True),
              ("subject_grid_condition_rating", "condition_rating", "Condition", False),
              ("subject_grid_quality_rating", "quality_rating", "Quality", False)]
    for gfield, sfield, label, numeric in checks:
        g = ctx.appraisal.value(gfield)
        s = ctx.appraisal.value(sfield)
        ev = [ctx.appraisal.evidence(gfield), ctx.appraisal.evidence(sfield)]
        if not g or not s:
            continue  # can only compare when both sides are present
        if numeric:
            gv, sv = normalize_currency(g), normalize_currency(s)
            same = gv is not None and sv is not None and sv > 0 and abs(gv - sv) / sv <= 0.01
        else:
            same = str(g).strip().upper() == str(s).strip().upper()
        if same:
            out.append(RuleResult(rule_id="SCA-17", checklist_num="69", section="sales_comparison",
                                  status=RuleStatus.PASS, fields_involved=[gfield, sfield], evidence=ev))
        else:
            out.append(RuleResult(rule_id="SCA-17", checklist_num="69", section="sales_comparison",
                                  status=RuleStatus.VERIFY,
                                  message=qc_config.template("SCA-17-consist", field=label, a=g, b=s),
                                  fields_involved=[gfield, sfield], template_id="SCA-17-consist",
                                  evidence=ev, confidence=0.7))
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
    recent prior transfer near the effective date is a value-support red flag."""
    window = int(qc_config.semantic("comp_resale_window_months", 36))
    eff = _effective_ym(ctx)
    d = _parse_full_date(ctx.appraisal.value("subject_grid_prior_sale_date"))
    ev = [ctx.appraisal.evidence("subject_grid_prior_sale_date"), ctx.appraisal.evidence("effective_date")]
    if d is None:
        # No prior sale/transfer recorded → nothing to reconcile (clean).
        return RuleResult(rule_id="SCA-PSH", checklist_num="80", section="sales_comparison",
                          status=RuleStatus.PASS, fields_involved=["subject_grid_prior_sale_date"], evidence=ev)
    if eff is None:
        return RuleResult(rule_id="SCA-PSH", checklist_num="80", section="sales_comparison",
                          status=RuleStatus.VERIFY,
                          message="The effective date could not be read to age the subject's prior sale; please verify the prior-sale recency.",
                          fields_involved=["subject_grid_prior_sale_date", "effective_date"], evidence=ev, confidence=0.5)
    months = (eff[0] - d[0]) * 12 + (eff[1] - d[1])
    if 0 <= months <= window:
        return RuleResult(rule_id="SCA-PSH", checklist_num="80", section="sales_comparison",
                          status=RuleStatus.VERIFY,
                          message=qc_config.template("SCA-PSH-subj", months=months),
                          fields_involved=["subject_grid_prior_sale_date"], template_id="SCA-PSH-subj",
                          evidence=ev, confidence=0.7)
    return RuleResult(rule_id="SCA-PSH", checklist_num="80", section="sales_comparison",
                      status=RuleStatus.PASS, fields_involved=["subject_grid_prior_sale_date"], evidence=ev)


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
            out.append(RuleResult(rule_id="SCA-FLIP", checklist_num="80b", section="sales_comparison",
                                  status=RuleStatus.VERIFY,
                                  message=qc_config.template("SCA-FLIP-comp", comp=i, months=months),
                                  fields_involved=[f"comp_{i}_prior_sale_date"], template_id="SCA-FLIP-comp",
                                  evidence=ev, confidence=0.7))
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
    return RuleResult(rule_id="SCA-26", checklist_num="82", section="sales_comparison",
                      status=RuleStatus.VERIFY,
                      message=qc_config.template("SCA-26-gla", subj=int(subj),
                                                 lo=int(min(glas)), hi=int(max(glas))),
                      fields_involved=["gla", "comp_N_gla"], template_id="SCA-26-gla",
                      evidence=ev, confidence=0.6)


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
                out.append(RuleResult(rule_id="SCA-ZF", checklist_num="76b", section="sales_comparison",
                                      status=RuleStatus.VERIFY,
                                      message=qc_config.template("SCA-zf-same", comp=i, field=label, a=int(adj)),
                                      fields_involved=[f"comp_{i}_{field}", f"comp_{i}_{field}_adjustment"],
                                      template_id="SCA-zf-same", evidence=ev, confidence=0.6))
    if checked and not out:
        out.append(RuleResult(rule_id="SCA-ZF", checklist_num="76b", section="sales_comparison",
                              status=RuleStatus.PASS, fields_involved=["comp_N_*_adjustment"]))
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
