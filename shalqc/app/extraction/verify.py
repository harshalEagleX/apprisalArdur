"""
extraction.verify (vfy-1.0.0) — self-verifying arithmetic checksums.

**These test whether EXTRACTION faithfully reproduced the page. They do NOT test
whether the appraiser complied with anything.** That distinction is the whole
reason this module is allowed to exist alongside the "LLM judges, no hardcode"
doctrine: compliance is interpretive and belongs to the judge; "does 320,000 +
(-1,700) equal the 318,300 printed two cells to the right" is closed-form and
belongs to code.

Concretely, this module will tell you a comp column was mis-read. It will never
tell you a 29.3% gross adjustment breaches a 25% guideline — that is a judge
finding, and hardcoding it here would be exactly the over-check the severity
gate exists to prevent.

Why it matters more than anything else in the 3.6 path: a VLM's output is
unverifiable by construction. You cannot diff it against ground truth you don't
have. But an appraisal report is dense with closed-form arithmetic, and every
instance is a free correctness oracle that needs no ground truth, no API key,
and no human. When the arithmetic closes, the extraction is almost certainly
right. When it doesn't, you re-extract instead of shipping.

This is the difference between "LLM extraction" and "LLM extraction you can
trust", and it is why this module was built before the extractor that feeds it.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

__version__ = "vfy-1.0.0"

logger = logging.getLogger(__name__)

# Money tolerance. Appraisers round; a $1 drift is rounding, a $100 drift is a
# misread digit. Kept tight deliberately — this is a mis-READ detector, and a
# loose tolerance turns it into a rubber stamp.
_MONEY_TOL = 1.0
# Area tolerance in sq ft: sketch line items are reported to a tenth and summed
# to a whole number, so 2137.36 -> 2137 must pass.
_AREA_TOL = 2.0


@dataclass
class VerifyResult:
    """Outcome of checking one region (a comp column, the sketch, the room grid)."""

    region: str
    errors: List[str] = field(default_factory=list)
    checks_run: int = 0
    # Checks that could not run because a required input was absent. NOT failures
    # — an honest null from the extractor lands here, and conflating the two would
    # punish exactly the abstention behavior we want.
    skipped: List[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors

    @property
    def verified(self) -> bool:
        """At least one check actually ran AND nothing failed. A region where
        every check was skipped is NOT verified — it is unproven, and calling it
        verified is how an empty extraction passes as a clean one."""
        return self.checks_run > 0 and not self.errors

    def as_dict(self) -> Dict[str, Any]:
        return {"region": self.region, "ok": self.ok, "verified": self.verified,
                "checks_run": self.checks_run, "errors": self.errors,
                "skipped": self.skipped}


# ── coercion ──────────────────────────────────────────────────────────────────

_NUM_RX = re.compile(r"[\d,]+(?:\.\d+)?")
# A parenthesized amount: `(12,000)`, `($12,000)`, `$(12,000)`. The currency
# symbol may sit INSIDE or OUTSIDE the parens depending on the form vendor,
# which is why a naive `startswith("(")` misses the common `$(12,000)` case.
_PAREN_NEG_RX = re.compile(r"\(\s*[^\d()]*[\d,]+(?:\.\d+)?\s*\)")
# A leading minus, with an optional currency symbol between it and the digits:
# `-1,700`, `-$1,700`, `- $1,700`.
_LEAD_NEG_RX = re.compile(r"^\s*[-−]\s*[^\d(]*[\d(]")
# A trailing minus, as some grids print it: `1,700-`.
_TRAIL_NEG_RX = re.compile(r"\d\s*[-−]\s*$")


def to_number(value: Any) -> Optional[float]:
    """'$(1,700)' -> -1700.0, '2,137 sf' -> 2137.0, None/'' -> None.

    **Negative notation is the trap, and it is a silent one.** Appraisal forms
    print a downward adjustment three different ways — `$(12,000)`, `(12,000)`,
    `-$12,000` — and every one of them defeats a naive parse: `float()` raises,
    while stripping non-digits returns +12,000. A sign inversion here does not
    error, it just makes the net adjustment reconcile against the wrong number,
    so the checksum this module exists to provide would pass on a grid it should
    have rejected. Unicode minus (U+2212) is included because it is what a PDF
    text layer often actually carries.
    """
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip()
    if not text:
        return None

    negative = bool(
        _PAREN_NEG_RX.search(text)
        or _LEAD_NEG_RX.match(text)
        or _TRAIL_NEG_RX.search(text)
    )
    m = _NUM_RX.search(text)
    if not m:
        return None
    try:
        n = float(m.group(0).replace(",", ""))
    except ValueError:
        return None
    return -n if negative else n


def _pair_adjustment(cell: Any) -> Optional[float]:
    """Adjustment out of a `{"value": ..., "adjustment": ...}` grid cell."""
    if isinstance(cell, dict):
        return to_number(cell.get("adjustment"))
    return None


# ── comp column ───────────────────────────────────────────────────────────────

def verify_comp_column(comp: Dict[str, Any], comp_no: Any = "?") -> VerifyResult:
    """The most valuable check in the file.

    Two independent identities hold in every sales grid:
        sum(line adjustments)            == net adjustment total
        sale price + net adjustment      == adjusted sale price

    A column shifted by one cell, a dropped row, a sign flip, or a transposed
    digit breaks at least one of them. Because the two identities share the net
    total, a misread that satisfies both is vanishingly unlikely.
    """
    res = VerifyResult(region=f"comp_{comp_no}")

    lines = [adj for adj in (_pair_adjustment(v) for v in comp.values())
             if adj is not None]
    net = to_number(comp.get("net_adjustment_total"))

    if net is not None and lines:
        res.checks_run += 1
        total = sum(lines)
        if abs(total - net) > _MONEY_TOL:
            res.errors.append(
                f"net adjustment {net:,.0f} does not equal the sum of the "
                f"{len(lines)} line adjustments ({total:,.0f}) — the column is "
                f"misaligned or a row was missed")
    else:
        res.skipped.append("net_vs_line_sum")

    sale = to_number(comp.get("sale_price"))
    adjusted = to_number(comp.get("adjusted_price"))
    if None not in (sale, net, adjusted):
        res.checks_run += 1
        if abs(sale + net - adjusted) > _MONEY_TOL:
            res.errors.append(
                f"adjusted price {adjusted:,.0f} does not equal sale price "
                f"{sale:,.0f} + net adjustment {net:,.0f} "
                f"(= {sale + net:,.0f})")
    else:
        res.skipped.append("adjusted_vs_sale_plus_net")

    return res


# ── partial-credit reconciliation ─────────────────────────────────────────────

CERTIFIED, PARTIAL, CONFLICT, UNREAD = "CERTIFIED", "PARTIAL", "CONFLICT", "UNREAD"


@dataclass
class CompReconciliation:
    """What can be PROVEN about one comparable from the fragments that landed.

    `verify_comp_column` answers one question — does everything reconcile? — and
    treats "I have three of seven rows" identically to "these seven rows are
    wrong". That conflation is expensive: run 16 read comparable 1's page 22
    correctly and reported `net -1,700 does not equal the sum of the 3 line
    adjustments (-2,000)` as a FAILURE, when -2,000 was the right answer for the
    half that had landed and the other half simply never arrived.

    Reconciling instead of gating turns the same evidence into three useful facts:

      * the net is derivable WITHOUT the page that carries it — page 33 restates
        every comparable's adjusted price, and `net = adjusted - sale`;
      * the identities that only need the fragments in hand can be certified now;
      * whatever is missing has an EXACT required value, so a retry is checked
        against a known target instead of merely hoped for.

    On run 16's actual state (page 21 failed, pages 22 and 33 landed) that yields
    "page 21 must contribute +300" — and the page really does sum to +300.
    """

    comp_no: Any
    status: str = UNREAD
    sale: Optional[float] = None
    adjusted: Optional[float] = None
    net_printed: Optional[float] = None
    net_derived: Optional[float] = None
    line_sum_read: Optional[float] = None
    # The exact figure the unread fragment(s) must contribute. This is the whole
    # point of reconciling: it makes the retry falsifiable.
    required_from_missing: Optional[float] = None
    pages_expected: List[int] = field(default_factory=list)
    pages_read: List[int] = field(default_factory=list)
    pages_missing: List[int] = field(default_factory=list)
    proven: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)

    @property
    def net(self) -> Optional[float]:
        """Printed net if read, else the value derived from the answer key."""
        return self.net_printed if self.net_printed is not None else self.net_derived

    def as_dict(self) -> Dict[str, Any]:
        return {
            "region": f"comp_{self.comp_no}", "status": self.status,
            "proven": self.proven, "errors": self.errors,
            "net": self.net, "net_printed": self.net_printed,
            "net_derived": self.net_derived, "line_sum_read": self.line_sum_read,
            "required_from_missing": self.required_from_missing,
            "pages_expected": self.pages_expected, "pages_read": self.pages_read,
            "pages_missing": self.pages_missing,
            "retry": [f"comp{self.comp_no}_page{p}" for p in self.pages_missing],
        }


def reconcile_comp(comp: Dict[str, Any], comp_no: Any = "?",
                   pages_expected: Optional[List[int]] = None,
                   answer_key: Optional[Dict[str, Any]] = None,
                   expected_rows: Optional[List[str]] = None) -> CompReconciliation:
    """Reconcile one comparable from whatever fragments landed.

    `answer_key` is page 33's Value Reconciliation row for this comparable
    ({"adjusted_price": ...}); it removes the page carrying the summary block
    from the critical path, because the net can then be derived from the adjusted
    price and the sale price instead of read.
    """
    rec = CompReconciliation(comp_no=comp_no)
    rec.pages_expected = sorted(pages_expected or [])
    rec.pages_read = sorted(p for p in (comp.get("_pages") or []) if p is not None)
    rec.pages_missing = [p for p in rec.pages_expected if p not in rec.pages_read]

    rec.sale = to_number(comp.get("sale_price"))
    rec.adjusted = to_number(comp.get("adjusted_price"))
    if rec.adjusted is None and answer_key:
        rec.adjusted = to_number(answer_key.get("adjusted_price"))
        if rec.adjusted is not None:
            rec.proven.append(f"adjusted price {rec.adjusted:,.0f} taken from the "
                              f"page-33 reconciliation table")
    rec.net_printed = to_number(comp.get("net_adjustment_total"))

    if rec.sale is not None and rec.adjusted is not None:
        rec.net_derived = rec.adjusted - rec.sale

    # Identity 1: sale + net == adjusted. Needs no line items at all, so it can
    # certify while the line-item pages are still missing.
    if rec.net_printed is not None and rec.net_derived is not None:
        if abs(rec.net_printed - rec.net_derived) <= _MONEY_TOL:
            rec.proven.append(
                f"adjusted price {rec.adjusted:,.0f} = sale {rec.sale:,.0f} + net "
                f"{rec.net_printed:,.0f}")
        else:
            rec.errors.append(
                f"printed net {rec.net_printed:,.0f} disagrees with adjusted price "
                f"minus sale price ({rec.net_derived:,.0f})")

    lines = [adj for adj in (_pair_adjustment(v) for v in comp.values())
             if adj is not None]
    rec.line_sum_read = sum(lines) if lines else None

    # ROW BINDING — arithmetic proves the sum, not the assignment.
    #
    # Comparable 4 came back CERTIFIED on run 18 while carrying a one-row shift:
    # the contract-date adjustment of $(4,300) was filed under
    # `sales_concessions`, and `contract_date_adjustment` was absent entirely.
    # The checksum could not see it, because a sum is invariant to which label
    # each addend is filed under — reorder the rows and it still closes.
    #
    # So a certified column must ALSO have every adjustment attached to a row the
    # form actually prints. A value under a label whose neighbour is missing is
    # the signature of a shift, and it changes what the adjustment MEANS even
    # though the total is right.
    labelled = {k for k, v in comp.items()
                if _pair_adjustment(v) is not None}
    expected = set(expected_rows or ())
    if expected and labelled:
        unknown = sorted(labelled - expected)
        if unknown:
            rec.errors.append(
                f"adjustment(s) filed under row label(s) this form does not print: "
                f"{', '.join(unknown)} — the column is shifted, so the totals can "
                f"still add up while individual adjustments mean the wrong thing")

    net = rec.net
    # Identity 2: sum(lines) == net. Only a CONFLICT when the read is COMPLETE —
    # otherwise the shortfall is the missing fragment's required contribution,
    # which is information rather than a failure.
    if net is not None and rec.line_sum_read is not None:
        shortfall = net - rec.line_sum_read
        if not rec.pages_missing:
            if abs(shortfall) <= _MONEY_TOL:
                rec.proven.append(
                    f"all {len(lines)} line adjustments sum to the net {net:,.0f}")
            else:
                rec.errors.append(
                    f"net {net:,.0f} does not equal the sum of the {len(lines)} line "
                    f"adjustments ({rec.line_sum_read:,.0f}) — the column is "
                    f"misaligned, a sign is inverted, or a row was misread")
        else:
            rec.required_from_missing = shortfall
            rec.proven.append(
                f"{len(lines)} line adjustments read sum to {rec.line_sum_read:,.0f}; "
                f"page(s) {', '.join(str(p) for p in rec.pages_missing)} must "
                f"contribute exactly {shortfall:,.0f}")

    if rec.errors:
        rec.status = CONFLICT
    elif rec.pages_missing:
        rec.status = PARTIAL if rec.proven else UNREAD
    elif rec.proven:
        rec.status = CERTIFIED
    return rec


def verify_comp_set(comps: List[Dict[str, Any]], expected: Optional[int] = None) -> VerifyResult:
    """Completeness gate for the whole grid.

    **Partial coverage does not degrade gracefully; it manufactures findings.**
    During the manual audit, reading only the first page-pair produced a
    confident false positive — "the $310,000 opinion sits below the adjusted
    range (min $311,000)". The next page held comps 4-6, the true range was
    $277,400-$341,700, and the finding evaporated.

    So an incomplete comp set is an ERROR here, and the caller must refuse to run
    range/bracketing checks until every column is in hand.
    """
    res = VerifyResult(region="comp_set")
    res.checks_run += 1
    if not comps:
        res.errors.append("no comparables extracted — the sales grid was not read")
        return res

    numbers = sorted({int(n) for n in (to_number(c.get("comp_number")) for c in comps)
                      if n is not None})
    if expected and len(numbers) < expected:
        res.errors.append(
            f"only {len(numbers)} of {expected} comparables extracted "
            f"(have {numbers}) — range and bracketing checks must not run on a "
            f"partial grid")
    if numbers and numbers != list(range(1, len(numbers) + 1)):
        res.errors.append(f"comparable numbering is not contiguous: {numbers}")
    return res


# ── sketch / area ─────────────────────────────────────────────────────────────

def verify_area(sketch: Dict[str, Any], interior: Optional[Dict[str, Any]] = None) -> VerifyResult:
    """Sketch line items must sum to the reported total, and that total must
    equal the finished-above-grade figure reported in the interior section.

    Two independent transcriptions of the same number, on different pages —
    which makes disagreement a strong misread signal rather than a judgment
    call. On the sample: 128.38 + 1018.58 + 892.53 + 97.87 = 2,137.36 -> 2,137,
    matching the interior's Finished Above Grade of 2,137.
    """
    res = VerifyResult(region="sketch")

    items = [to_number(x) for x in (sketch.get("living_area_calcs") or [])]
    items = [x for x in items if x is not None]
    total = to_number(sketch.get("total_living_area"))

    if items and total is not None:
        res.checks_run += 1
        calc = sum(items)
        if abs(calc - total) > _AREA_TOL:
            res.errors.append(
                f"sketch line items sum to {calc:,.1f} sf but the reported total "
                f"is {total:,.0f} sf")
    else:
        res.skipped.append("sketch_items_vs_total")

    above = to_number((interior or {}).get("finished_above_grade"))
    if total is not None and above is not None:
        res.checks_run += 1
        if abs(total - above) > _AREA_TOL:
            res.errors.append(
                f"sketch total {total:,.0f} sf disagrees with finished above "
                f"grade {above:,.0f} sf")
    else:
        res.skipped.append("sketch_total_vs_finished_above_grade")

    return res


# ── room counts ───────────────────────────────────────────────────────────────

def verify_rooms(room_summary: Dict[str, Any], totals: Dict[str, Any]) -> VerifyResult:
    """The per-level room breakdown must agree with the reported totals — again
    two transcriptions of one fact, so a mismatch means a misread."""
    res = VerifyResult(region="rooms")
    for label, total_key, pretty in (
        ("Bedroom", "total_bedrooms", "bedrooms"),
        ("Bath - Full", "total_bathrooms_full", "full baths"),
        ("Bath - Half", "total_bathrooms_half", "half baths"),
    ):
        a = to_number(room_summary.get(label))
        b = to_number(totals.get(total_key))
        if a is None or b is None:
            res.skipped.append(total_key)
            continue
        res.checks_run += 1
        if abs(a - b) > 0:
            res.errors.append(
                f"room summary shows {a:g} {pretty} but the totals row reports {b:g}")
    return res


# ── driver ────────────────────────────────────────────────────────────────────

def verify_all(extracted: Dict[str, Any], expected_comps: Optional[int] = None) -> List[VerifyResult]:
    """Run every applicable check over one order's vision output.

    Absent regions are skipped silently rather than reported as failures —
    a 1073 condo has no site line, a refinance has no contract, and inventing
    an error for a section the form does not contain is the false-positive
    pattern this codebase keeps having to unlearn.
    """
    results: List[VerifyResult] = []

    comps = extracted.get("comparables") or []
    if comps:
        results.append(verify_comp_set(comps, expected=expected_comps))
        for comp in comps:
            results.append(verify_comp_column(comp, comp.get("comp_number", "?")))

    sketch = extracted.get("sketch")
    if sketch:
        results.append(verify_area(sketch, extracted.get("unit_interior")))

    rooms = extracted.get("room_summary")
    totals = extracted.get("room_totals")
    if rooms and totals:
        results.append(verify_rooms(rooms, totals))

    return results


def summarize(results: List[VerifyResult]) -> Dict[str, Any]:
    """One line for the run log and the reviewer's degradation list."""
    failed = [r for r in results if r.errors]
    return {
        "regions": len(results),
        "verified": sum(1 for r in results if r.verified),
        "failed": len(failed),
        "checks_run": sum(r.checks_run for r in results),
        "failures": {r.region: r.errors for r in failed},
    }
