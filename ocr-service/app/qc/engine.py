"""
QC engine — run every applicable rule against a transaction context.

Responsibilities:
  * applicability gating — rules whose applies_when is False become
    NOT_APPLICABLE (still recorded, so FHA rules show as N/A on a conventional
    file rather than vanishing).
  * normalize each rule's output to a list of RuleResult and tag section/num.
  * roll up to a QCReport; persist every result to adaptive_validation_results.

Each rule runs in isolation — one rule raising never blocks the others (P-6).
"""

from __future__ import annotations

import logging
from typing import List, Optional

from app.qc.context import QCContext
from app.qc.registry import RuleSpec, all_rules
from app.qc.result import QCReport, RuleResult, RuleStatus

logger = logging.getLogger(__name__)


def _normalize(out, spec: RuleSpec) -> List[RuleResult]:
    if out is None:
        return []
    results = out if isinstance(out, list) else [out]
    for r in results:
        # backfill metadata if the rule used a bare constructor
        if not r.rule_id:
            r.rule_id = spec.rule_id
        if not r.checklist_num:
            r.checklist_num = spec.checklist_num
        if not r.section:
            r.section = spec.section
    return results


def run_qc(ctx: QCContext, only_phase: Optional[int] = None,
           min_phase: Optional[int] = None) -> QCReport:
    """Run all registered rules (optionally filtered by phase) on the context."""
    report = QCReport(transaction_id=ctx.transaction_id)
    for spec in all_rules():
        if only_phase is not None and spec.phase != only_phase:
            continue
        if min_phase is not None and spec.phase > min_phase:
            continue
        if not spec.applicable(ctx):
            report.results.append(RuleResult(
                rule_id=spec.rule_id, checklist_num=spec.checklist_num,
                section=spec.section, status=RuleStatus.NOT_APPLICABLE,
                message="Not applicable to this loan/transaction/form type.",
            ))
            continue
        try:
            out = spec.fn(ctx)
            report.results.extend(_normalize(out, spec))
        except Exception as exc:
            logger.error("QC rule %s crashed: %s", spec.rule_id, exc)
            report.results.append(RuleResult(
                rule_id=spec.rule_id, checklist_num=spec.checklist_num,
                section=spec.section, status=RuleStatus.SKIPPED,
                message=f"Rule execution error: {exc}",
            ))
    _escalate_sections(report)
    return report


# Sections that warrant a systematic-failure HOLD (data-grid heavy sections where
# a cluster of failures signals a pattern, not isolated errors — MIRA's logic).
_HOLD_FAIL_THRESHOLD = 2


def _escalate_sections(report: QCReport) -> None:
    """Section-level risk: when a section accumulates more than _HOLD_FAIL_THRESHOLD
    FAILs, the section has systematic problems rather than isolated errors — add a
    section-level HOLD so the whole section is routed to a full manual review."""
    from collections import Counter
    fails = Counter(r.section for r in report.results
                    if r.status == RuleStatus.FAIL and r.section)
    for section, n in fails.items():
        if n > _HOLD_FAIL_THRESHOLD:
            report.results.append(RuleResult(
                rule_id=f"{section.upper()}-HOLD", checklist_num="",
                section=section, status=RuleStatus.HOLD,
                message=(f"{n} failures in the {section.replace('_', ' ')} section indicate "
                         "systematic problems (not isolated errors); the section is placed on "
                         "HOLD for a full manual review."),
            ))


def persist_report(report: QCReport, document_id: str) -> int:
    """Write every rule result to adaptive_validation_results. Returns rows written."""
    try:
        from app.database import get_db
        from app.models.db_models import ValidationResultRow
    except Exception as exc:
        logger.warning("QC persist unavailable: %s", exc)
        return 0
    written = 0
    try:
        with get_db() as session:
            for r in report.results:
                session.add(ValidationResultRow(**r.to_db_dict(
                    document_id=document_id, transaction_id=report.transaction_id)))
                written += 1
    except Exception as exc:
        logger.error("QC persist failed: %s", exc)
        return 0
    return written
