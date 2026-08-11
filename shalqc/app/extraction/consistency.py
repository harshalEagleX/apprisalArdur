"""
extraction.consistency (cns-1.0.0) — the report as its own answer key.

A UAD 3.6 report states the same fact in several places, and those pages are
already being read, so confirming a fact from N independent sources costs
**nothing extra**. Gross living area appears six times: the sketch total, the
sketch line-item sum, the sketch commentary, the interior finished-above-grade
row, the level-and-room detail, and the subject column of the sales grid.

One mechanism, three outcomes:

  CONFIRMED  every source agrees. Some checklist items are then answered
             DETERMINISTICALLY with no judge call — item 34 ("is the square
             footage consistent with the sketch?") IS this comparison.
  REPAIR     one source disagrees with the majority. That is an extraction
             defect, not a report defect: re-read THAT ONE PAGE, with the
             expected value already known so the fix verifies instantly.
  CONFLICT   sources genuinely disagree in the document. Not an extraction bug —
             a FINDING, routed to the judge with every witness attached.

Two properties make this worth more than a second extraction pass:

  * It is FREE. No extra model call, no ground truth, no API key.
  * It localises. A whole-order re-run tells you something is wrong; an
    n-source vote tells you WHICH PAGE is wrong, which is the difference
    between a $0.10 retry and a $0.005 one.

This REPLACES the "two-pass on numerics" idea (independently re-extract every
number, then compare). That pass costs a second full extraction to obtain what
the document already contains for nothing.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from app.extraction.verify import to_number

__version__ = "cns-1.0.0"

logger = logging.getLogger(__name__)

CONFIRMED, REPAIR, CONFLICT, SINGLE, ABSENT = (
    "confirmed", "repair", "conflict", "single_source", "absent")

# Relative tolerance for "the same number". Appraisers round areas to whole feet
# and money to whole dollars; a 0.5% drift is rounding, a 10% drift is a misread.
_REL_TOL = 0.005
_ABS_TOL = 1.0


@dataclass
class Observation:
    """One source's reading of one canonical fact."""

    source: str          # canonical field name it came from
    value: Any
    page: int = 0
    origin: str = "vision"

    @property
    def number(self) -> Optional[float]:
        return to_number(self.value)


@dataclass
class FactConsensus:
    """The verdict across every source for one canonical fact."""

    fact: str
    status: str
    value: Any = None
    observations: List[Observation] = field(default_factory=list)
    agreeing: List[str] = field(default_factory=list)
    dissenting: List[str] = field(default_factory=list)
    # Pages worth re-reading, when status is REPAIR.
    repair_pages: List[int] = field(default_factory=list)
    note: str = ""

    @property
    def sources(self) -> int:
        return len(self.observations)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "fact": self.fact, "status": self.status, "value": self.value,
            "sources": self.sources, "agreeing": self.agreeing,
            "dissenting": self.dissenting, "repair_pages": self.repair_pages,
            "note": self.note,
            "observations": [{"source": o.source, "value": o.value, "page": o.page}
                             for o in self.observations],
        }


# ── the redundancy map ────────────────────────────────────────────────────────
#
# Canonical fact -> the field names that independently state it. DATA, not code:
# a new restatement is a list entry. Derived from reading the 2026-08-03 sample
# page by page.
#
# NOTE (§9 caveat): this map is drawn from ONE report. Validate that the same
# redundancy holds across the three-order fixture set before relying on
# majority-vote repair — a vendor template change can move where facts restate.
REDUNDANCY: Dict[str, List[str]] = {
    "gla": [
        "gla",                       # improvements / interior finished above grade
        "total_living_area",         # sketch stated total
        "_sketch_line_sum",          # derived: sum of sketch line items
        "subject_grid_gla",          # subject column of the sales grid
    ],
    "site_area": ["site_area", "subject_grid_site_size"],
    "bedrooms": ["bedrooms", "_room_summary_bedrooms"],
    "baths": ["baths", "_room_summary_baths_full"],
    "year_built": ["year_built", "subject_grid_year_built"],
    "quality_rating": ["quality_rating", "subject_grid_quality"],
    "condition_rating": ["condition_rating", "subject_grid_condition"],
    "appraised_value": ["appraised_value", "indicated_value_sca", "_weighted_value_sum"],
    "contract_price": ["contract_price", "subject_grid_contract_price"],
    "effective_date": ["effective_date", "_value_reconciliation_effective_date"],
    "property_address": ["property_address", "subject_grid_address"],
}


def _agree(a: Any, b: Any) -> bool:
    """Do two observations state the same fact?"""
    na, nb = to_number(a), to_number(b)
    if na is not None and nb is not None:
        if abs(na - nb) <= _ABS_TOL:
            return True
        scale = max(abs(na), abs(nb), 1.0)
        return abs(na - nb) / scale <= _REL_TOL
    sa, sb = str(a or "").strip().lower(), str(b or "").strip().lower()
    if not sa or not sb:
        return False
    return sa == sb or sa in sb or sb in sa


def reconcile(fact: str, observations: List[Observation]) -> FactConsensus:
    """Vote across every source for one fact."""
    obs = [o for o in observations if o.value not in (None, "")]
    if not obs:
        return FactConsensus(fact=fact, status=ABSENT, note="no source stated this fact")
    if len(obs) == 1:
        return FactConsensus(fact=fact, status=SINGLE, value=obs[0].value,
                             observations=obs, agreeing=[obs[0].source],
                             note="only one source — no cross-check available")

    # Cluster observations that agree with each other.
    clusters: List[List[Observation]] = []
    for o in obs:
        for cluster in clusters:
            if _agree(cluster[0].value, o.value):
                cluster.append(o)
                break
        else:
            clusters.append([o])

    clusters.sort(key=len, reverse=True)
    biggest = clusters[0]

    if len(clusters) == 1:
        return FactConsensus(fact=fact, status=CONFIRMED, value=biggest[0].value,
                             observations=obs, agreeing=[o.source for o in biggest],
                             note=f"all {len(obs)} sources agree")

    minority = [o for c in clusters[1:] for o in c]
    # A clear majority means the outliers are misreads -> repair. A tie (or a
    # near-tie) means the DOCUMENT disagrees with itself, which is a finding and
    # must not be silently "repaired" into agreement.
    if len(biggest) > len(minority):
        return FactConsensus(
            fact=fact, status=REPAIR, value=biggest[0].value, observations=obs,
            agreeing=[o.source for o in biggest],
            dissenting=[o.source for o in minority],
            repair_pages=sorted({o.page for o in minority if o.page}),
            note=(f"{len(biggest)} of {len(obs)} sources agree on "
                  f"{biggest[0].value!r}; re-read "
                  f"{', '.join(o.source for o in minority)}"))
    return FactConsensus(
        fact=fact, status=CONFLICT, value=None, observations=obs,
        agreeing=[o.source for o in biggest],
        dissenting=[o.source for o in minority],
        note=("the report states this fact inconsistently — "
              + " vs ".join(sorted({str(c[0].value) for c in clusters}))
              + " — this is a FINDING, not a misread"))


def _derived(values: Dict[str, Any]) -> Dict[str, Tuple[Any, int]]:
    """Facts the report implies but never prints, computed from what it does.

    These are extra INDEPENDENT witnesses, which is the point: a sum of sketch
    line items is arrived at by a different route than the printed total, so
    agreement between them is real corroboration rather than an echo.
    """
    out: Dict[str, Tuple[Any, int]] = {}

    def _val(name: str) -> Any:
        entry = values.get(name)
        return entry.get("value") if isinstance(entry, dict) else entry

    def _page(name: str) -> int:
        entry = values.get(name)
        return int(entry.get("page") or 0) if isinstance(entry, dict) else 0

    items = _val("living_area_calcs")
    if isinstance(items, str):
        items = [p for p in items.split(";") if p.strip()]
    if isinstance(items, list) and items:
        nums = [to_number(x) for x in items]
        nums = [n for n in nums if n is not None]
        if nums:
            out["_sketch_line_sum"] = (round(sum(nums)), _page("living_area_calcs"))
    return out


def check_order(values: Dict[str, Any],
                grid: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Cross-verify every redundantly-stated fact in one order.

    `values` is the section extractor's output ({name: {value, page, ...}}).
    Returns a report plus the pages worth re-reading.
    """
    derived = _derived(values)
    consensus: List[FactConsensus] = []

    for fact, sources in REDUNDANCY.items():
        observations: List[Observation] = []
        for source in sources:
            if source in derived:
                val, page = derived[source]
                observations.append(Observation(source=source, value=val,
                                                page=page, origin="derived"))
                continue
            entry = values.get(source)
            if entry is None:
                continue
            if isinstance(entry, dict):
                observations.append(Observation(source=source, value=entry.get("value"),
                                                page=int(entry.get("page") or 0)))
            else:
                observations.append(Observation(source=source, value=entry))
        consensus.append(reconcile(fact, observations))

    by_status: Dict[str, List[str]] = defaultdict(list)
    for c in consensus:
        by_status[c.status].append(c.fact)

    repair_pages = sorted({p for c in consensus for p in c.repair_pages})
    return {
        "facts": [c.as_dict() for c in consensus],
        "summary": {s: by_status.get(s, []) for s in
                    (CONFIRMED, REPAIR, CONFLICT, SINGLE, ABSENT)},
        "repair_pages": repair_pages,
        "cross_checked": sum(1 for c in consensus if c.sources > 1),
        "total_observations": sum(c.sources for c in consensus),
    }


# ── the grid's independent answer key ─────────────────────────────────────────

def cross_check_grid(comparables: List[Dict[str, Any]],
                     reconciliation_rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Validate the sales grid against the Value Reconciliation table.

    **This is the highest-value link in the whole graph.** The grid spans four
    pages and a column shift there produces individually plausible numbers that
    nothing downstream can detect. The Value Reconciliation table — on a
    completely unrelated page, produced by a different part of the vendor's
    software — restates every comparable's adjusted price. Agreement between
    them is genuine corroboration; disagreement localises the fault to one
    comparable.

    Verified on the 2026-08-03 sample, comp 1:
        grid:  320,000 + (-1,700) = 318,300
        table: 318,300                        MATCH
        weights 20+15+25+15+25+0 = 100%
        318,300 x 0.20 = 63,660               MATCH

    `reconciliation_rows`: [{address, weight, adjusted_price, weighted_contribution}]
    """
    result: Dict[str, Any] = {"checked": 0, "matched": [], "mismatched": [],
                              "weights_sum": None, "weights_ok": None,
                              "contributions_ok": [], "notes": []}
    if not comparables or not reconciliation_rows:
        result["notes"].append(
            "no Value Reconciliation table extracted — the grid has no independent "
            "cross-check on this order")
        return result

    weights = [to_number(r.get("weight")) for r in reconciliation_rows]
    weights = [w for w in weights if w is not None]
    if weights:
        total = sum(weights)
        result["weights_sum"] = total
        # Weights may be printed as 20.0 or 0.20 depending on the vendor.
        result["weights_ok"] = abs(total - 100.0) <= 0.5 or abs(total - 1.0) <= 0.005
        if not result["weights_ok"]:
            result["notes"].append(
                f"comparable weights sum to {total:g}, not 100% — either a misread "
                f"or the appraiser's weighting does not close")

    by_addr = {}
    for row in reconciliation_rows:
        key = str(row.get("address") or "").strip().lower()[:24]
        if key:
            by_addr[key] = row

    for comp in comparables:
        n = comp.get("comp_number")
        grid_adj = to_number(comp.get("adjusted_price"))
        addr = str(comp.get("address") or "").strip().lower()[:24]
        row = by_addr.get(addr)
        if row is None and len(reconciliation_rows) >= (n or 0) > 0:
            row = reconciliation_rows[n - 1]      # fall back to position
        if row is None or grid_adj is None:
            continue
        table_adj = to_number(row.get("adjusted_price"))
        if table_adj is None:
            continue
        result["checked"] += 1
        if abs(grid_adj - table_adj) <= _ABS_TOL:
            result["matched"].append(n)
        else:
            result["mismatched"].append({
                "comp": n, "grid": grid_adj, "value_reconciliation": table_adj,
                "note": (f"comparable {n}: the sales grid gives an adjusted price of "
                         f"{grid_adj:,.0f} but the Value Reconciliation table states "
                         f"{table_adj:,.0f} — re-read this column")})

        w = to_number(row.get("weight"))
        contrib = to_number(row.get("weighted_contribution"))
        if None not in (w, contrib) and table_adj:
            frac = w / 100.0 if w > 1.5 else w
            expected = table_adj * frac
            result["contributions_ok"].append({
                "comp": n, "ok": abs(expected - contrib) <= max(1.0, abs(expected) * 0.01),
                "expected": round(expected), "printed": contrib})
    return result


def summarize(report: Dict[str, Any]) -> str:
    """One line for the run log."""
    s = report.get("summary", {})
    return (f"consistency: {len(s.get(CONFIRMED, []))} confirmed, "
            f"{len(s.get(REPAIR, []))} repairable, {len(s.get(CONFLICT, []))} conflicting, "
            f"{report.get('cross_checked', 0)} facts cross-checked across "
            f"{report.get('total_observations', 0)} observations")
