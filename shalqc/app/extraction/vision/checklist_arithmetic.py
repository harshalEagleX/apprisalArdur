"""
extraction.vision.checklist_arithmetic (cka-1.0.0) — the answers that are PROVED.

Seventeen of the UAD 3.6 checklist's ninety questions are not observations, they
are computations: is the subject's sale price bracketed by the comparables, is
the bedroom count bracketed, is the square footage consistent with the sketch, do
the adjustments sum to the stated net. A vision model can offer an opinion on
each; none of those opinions can be checked.

That distinction is the whole reason the extractor still exists. The `$(23,800)`
site-size adjustment misread as `$0` looked entirely plausible on the page — a
model asked "do these adjustments look right?" says yes. What caught it was
`sum(lines) != net`, arithmetic nobody asked the model to perform. Run 18 then
closed five of six comparables to the cent, which is a proof, not a judgement.

So this module answers only questions that arithmetic can SETTLE, and abstains
loudly everywhere else:

  * a computed answer is returned with the numbers that produced it, so a
    reviewer can re-derive it without trusting this code;
  * a missing input yields VERIFY naming the input, never a default;
  * where the vision pass also answered, the two are compared — agreement raises
    confidence, disagreement is surfaced as VERIFY with both positions stated,
    because two methods disagreeing is exactly when a human should look.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from app.extraction.verify import to_number

__version__ = "cka-1.0.0"

logger = logging.getLogger(__name__)

PASS, FAIL, VERIFY = "PASS", "FAIL", "VERIFY"
_MAX_COMPS = 6


@dataclass
class ProvedAnswer:
    checklist_number: int
    question: str
    status: str = VERIFY
    reason: str = ""
    computation: str = ""
    inputs: Dict[str, Any] = field(default_factory=dict)
    missing: List[str] = field(default_factory=list)

    def as_dict(self) -> Dict[str, Any]:
        return {"checklist_number": self.checklist_number, "question": self.question,
                "status": self.status, "reason": self.reason,
                "computation": self.computation, "inputs": self.inputs,
                "missing": self.missing}


def _val(fields: Dict[str, Any], name: str) -> Optional[str]:
    v = fields.get(name)
    if isinstance(v, dict):
        return v.get("value")
    return v


def _num(fields: Dict[str, Any], name: str) -> Optional[float]:
    return to_number(_val(fields, name))


def _comp_numbers(fields: Dict[str, Any], suffix: str) -> Dict[int, float]:
    out: Dict[int, float] = {}
    for i in range(1, _MAX_COMPS + 1):
        n = _num(fields, f"comp_{i}_{suffix}")
        if n is not None:
            out[i] = n
    return out


def _bracket(subject: Optional[float], comps: Dict[int, float], label: str,
             number: int, question: str) -> ProvedAnswer:
    """Bracketing: the subject's value must lie within the comparables' range.

    Requires at least two comparables — a "range" of one value is not a bracket,
    and treating it as one would pass a check that was never really performed.
    """
    a = ProvedAnswer(checklist_number=number, question=question)
    if subject is None:
        a.missing = [f"subject {label}"]
        a.reason = f"subject {label} was not read — cannot compute bracketing"
        return a
    if len(comps) < 2:
        a.missing = [f"comparable {label} (have {len(comps)}, need 2+)"]
        a.reason = (f"only {len(comps)} comparable {label} value(s) read — a bracket "
                    f"needs at least two")
        return a
    lo, hi = min(comps.values()), max(comps.values())
    a.inputs = {"subject": subject, "comps": comps, "low": lo, "high": hi}
    a.computation = f"{lo:,.0f} <= {subject:,.0f} <= {hi:,.0f}"
    if lo <= subject <= hi:
        a.status, a.reason = PASS, f"subject {label} {subject:,.0f} is bracketed by {lo:,.0f}-{hi:,.0f}"
    else:
        a.status, a.reason = FAIL, (
            f"subject {label} {subject:,.0f} falls OUTSIDE the comparable range "
            f"{lo:,.0f}-{hi:,.0f}")
    return a


_COMP_RX = re.compile(r"^comp_(\d+)_(.+)$")


def _split_bindings(names: List[str]) -> tuple:
    """(subject field, comparable suffix) from an item's bound field names.

    Derived from the SHAPE of the names — `comp_<n>_<thing>` is a comparable
    column, anything else is the subject — rather than from the checklist number.
    That is what lets another AMC's checklist, with different numbering and
    different wording, drive the same proof without touching this file.
    """
    subject = next((n for n in names if not _COMP_RX.match(n)), None)
    suffixes = [m.group(2) for m in (_COMP_RX.match(n) for n in names) if m]
    return subject, (suffixes[0] if suffixes else None)


def prove(fields: Dict[str, Any],
          reconciliation: Optional[Dict[str, Any]] = None,
          catalog_items: Optional[List[Dict[str, Any]]] = None) -> List[ProvedAnswer]:
    """Answer every checklist item arithmetic can settle.

    Driven by each item's declared `proof` (set once per AMC by
    tools/classify_checklist.py) and its bound field names. The first version
    keyed these to checklist numbers 74/86/87/34 — which silently misfires the
    moment an AMC numbers its checklist differently, and every AMC does.
    """
    out: List[ProvedAnswer] = []
    for item in (catalog_items or []):
        proof = (item.get("proof") or "none").strip().lower()
        if proof in ("none", ""):
            continue
        number = item.get("checklist_number", 0)
        question = item.get("requirement", "")
        names = (item.get("sources") or [{}])[0].get("fields") or []

        if proof == "bracketing":
            subject_field, suffix = _split_bindings(names)
            if not subject_field or not suffix:
                a = ProvedAnswer(checklist_number=number, question=question)
                a.reason = "bracketing declared but the item has no subject/comparable binding"
                a.missing = ["binding"]
                out.append(a)
                continue
            out.append(_bracket(_num(fields, subject_field),
                                _comp_numbers(fields, suffix),
                                subject_field.replace("_", " "), number, question))

        elif proof == "consistency":
            # Two independent statements of one fact must agree. Which two comes
            # from the binding, so "square footage vs the sketch" and any other
            # AMC's equivalent both work without naming either here.
            pair = [n for n in names if not _COMP_RX.match(n)][:2]
            a = ProvedAnswer(checklist_number=number, question=question)
            if len(pair) < 2:
                a.reason = "consistency declared but fewer than two fields are bound"
                a.missing = ["binding"]
                out.append(a)
                continue
            x, y = _num(fields, pair[0]), _num(fields, pair[1])
            if x is None or y is None:
                a.missing = [n for n, v in zip(pair, (x, y)) if v is None]
                a.reason = f"cannot compare — missing {', '.join(a.missing)}"
            else:
                a.inputs = {pair[0]: x, pair[1]: y}
                a.computation = f"|{x:,.0f} - {y:,.0f}| = {abs(x - y):,.0f}"
                # Areas are summed from tenths and printed rounded, so a couple of
                # units apart is rounding rather than a discrepancy.
                if abs(x - y) <= 2.0:
                    a.status, a.reason = PASS, f"{pair[0]} and {pair[1]} both state {x:,.0f}"
                else:
                    a.status, a.reason = FAIL, (
                        f"{pair[0]} states {x:,.0f} but {pair[1]} states {y:,.0f}")
            out.append(a)

    # ── order-level findings ──────────────────────────────────────────────────
    #
    # These two are NOT tied to a checklist number, because they are facts about
    # the report rather than answers to one AMC's phrasing of one question. Every
    # AMC asks about adjustment direction and about the As-Is condition somewhere,
    # under its own numbering; binding them to 91 and 95 was the same mistake as
    # the bracketing rules. They are emitted as findings a reviewer sees, and the
    # card layer attaches them to whichever items reference adjustments or
    # condition — a lookup by meaning, not by number.
    a = ProvedAnswer(checklist_number=0,
                     question="Adjustments: are they applied and in the proper direction?")
    comps = (reconciliation or {}).get("comparables") or []
    if not comps:
        a.reason = "no comparable reconciliation available"
        a.missing = ["grid_reconciliation"]
    else:
        certified = [c for c in comps if c.get("status") == "CERTIFIED"]
        conflicted = [c for c in comps if c.get("status") == "CONFLICT"]
        a.inputs = {"certified": [c["region"] for c in certified],
                    "conflict": [c["region"] for c in conflicted],
                    "other": [c["region"] for c in comps
                              if c.get("status") not in ("CERTIFIED", "CONFLICT")]}
        a.computation = f"{len(certified)}/{len(comps)} comparables reconcile to their printed net"
        if conflicted:
            a.status, a.reason = FAIL, (
                f"{len(conflicted)} comparable(s) do not reconcile — a sign or a row "
                f"is wrong: {', '.join(c['region'] for c in conflicted)}")
        elif len(certified) == len(comps):
            a.status, a.reason = PASS, "every comparable's adjustments sum to its printed net"
        else:
            a.reason = (f"{len(certified)} of {len(comps)} comparables proved; the rest "
                        f"were not fully read")
    out.append(a)

    # #95 / #98 — a contract-mandated repair against an "As Is" opinion.
    #
    # Found by reading the sample report: the contract analysis states "the seller
    # is required to repair the septic system to proper working order prior to
    # closing", while the Market Value Condition is "As Is". Those two can both be
    # correct — the repair may be the contract's business and not the appraisal's —
    # but the combination is precisely what a reviewer is paid to look at, and it
    # is invisible to any single-field check because neither value is wrong on its
    # own. It only appears when you read them together.
    #
    # Deliberately VERIFY, never FAIL: whether an As-Is opinion must be reconciled
    # against a contract repair is the AMC's policy, not an arithmetic fact.
    a = ProvedAnswer(checklist_number=0,
                     question=("Is the stated market value condition consistent with any "
                               "repair the contract requires?"))
    condition = (_val(fields, "market_value_condition") or
                 _val(fields, "appraisal_subject_to") or "")
    contract_text = " ".join(str(_val(fields, n) or "") for n in
                             ("sales_contract_analysis", "contract_analysis_comment",
                              "final_reconciliation_comment"))
    repair_words = ("required to repair", "must repair", "repair the", "prior to closing",
                    "subject to repair", "must be repaired")
    hit = [w for w in repair_words if w in contract_text.lower()]
    a.inputs = {"market_value_condition": condition, "repair_language": hit}
    if not condition:
        a.reason = "market value condition was not read"
        a.missing = ["market_value_condition"]
    elif hit and "as is" in condition.lower():
        a.status = VERIFY
        a.computation = f"condition='{condition}' AND contract requires a repair"
        a.reason = ("the report is 'As Is' but the contract requires a repair before "
                    "closing — reviewer must confirm the condition is stated correctly")
    else:
        a.status = PASS
        a.computation = f"condition='{condition}'"
        a.reason = f"report completed '{condition}' with no conflicting repair requirement"
    out.append(a)
    return out


def cross_check(proved: List[ProvedAnswer],
                vision_answers: List[Any]) -> List[Dict[str, Any]]:
    """Compare the proved answers with what the vision pass said about the same items.

    Agreement is worth recording — two independent methods reaching the same
    verdict is far stronger evidence than either alone. Disagreement is worth more:
    it is the cheapest possible signal that one of them is wrong, and it costs a
    reviewer one look to find out which.
    """
    by_number = {getattr(v, "checklist_number", None): v for v in vision_answers}
    rows: List[Dict[str, Any]] = []
    for p in proved:
        v = by_number.get(p.checklist_number)
        vstatus = getattr(v, "status", None)
        if v is None or p.status == VERIFY or vstatus == VERIFY:
            agree = None
        else:
            agree = (p.status == vstatus)
        rows.append({
            "checklist_number": p.checklist_number,
            "question": p.question,
            "proved": p.status, "computation": p.computation, "reason": p.reason,
            "vision": vstatus, "vision_observed": getattr(v, "observed", ""),
            "agree": agree,
            # Arithmetic wins on the numbers; it either closes or it does not.
            # But a disagreement is never silently resolved — it goes to a human.
            "final": (p.status if agree is not False else VERIFY),
            "final_reason": (p.reason if agree is not False else
                             f"arithmetic says {p.status} but the page reads {vstatus} — "
                             f"reviewer must settle it"),
        })
    return rows
