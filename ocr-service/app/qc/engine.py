"""
QC engine — run every applicable rule against a transaction context.

Outcome model (3 states only, SKIPPED reserved for crashes):
  PASS           — rule evaluated, condition satisfied
  FAIL/VERIFY/HOLD — rule evaluated, issue found
  NOT_APPLICABLE — business condition does not apply to this assignment
  SKIPPED        — rule crashed (exception); never produced for missing policy/data

Rules must never return SKIPPED for missing policy or missing extraction data.
Policy always resolves from AMC base → engagement overlay → UAD/GSE default.
Missing extraction data → VERIFY (reviewer confirms) or NOT_APPLICABLE.

Responsibilities:
  * applicability gating — rules whose applies_when is False become NOT_APPLICABLE
  * normalize each rule's output to a list of RuleResult and tag section/num
  * coerce any rule-returned SKIPPED(reason=policy/data) to VERIFY in post-processing
  * roll up to a QCReport; persist to adaptive_validation_results
"""

from __future__ import annotations

import logging
from time import perf_counter
from typing import List, Optional

from app.qc.context import QCContext
from app.qc.registry import RuleSpec, all_rules
from app.qc.result import QCReport, RuleResult, RuleStatus, RuleTiming

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


# Sections that only exist on certain report forms. A 1004D Appraisal Update /
# Completion report has NO sales-comparison grid, so every SCA rule is genuinely
# Not Applicable rather than a "couldn't find comps" VERIFY. The predicate
# defaults to True (normal full appraisal) and only an explicit no-grid form turns
# it off — so a normal 1004 whose comp extraction failed still runs SCA and flags
# the gap, never silently hides it.
_SECTION_GATE = {
    "sales_comparison": lambda ctx: ctx.has_sca_grid,
}


def run_qc(ctx: QCContext, only_phase: Optional[int] = None,
           min_phase: Optional[int] = None) -> QCReport:
    """Run all registered rules (optionally filtered by phase) on the context."""
    report = QCReport(transaction_id=ctx.transaction_id)

    # ---- Zero-comps blocking gate ------------------------------------------
    # When the SCA grid is expected (normal full appraisal) but no comparable
    # sale prices were extracted, every SCA rule would evaluate against empty
    # data and produce phantom PASSes or misleading VERIFYs. Detect this up
    # front, emit a single HOLD (SCA-ZERO-COMPS) so the reviewer sees one clear
    # root cause, and skip all other SCA rules for this run (they will be
    # re-evaluated once extraction is confirmed and the job is re-run).
    _zero_comps = (
        ctx.has_sca_grid
        and not any(ctx.appraisal.value(f"comp_{i}_sale_price") for i in range(1, 10))
    )
    if _zero_comps:
        report.results.append(RuleResult(
            rule_id="SCA-ZERO-COMPS",
            checklist_num="SCA-zero",
            section="sales_comparison",
            status=RuleStatus.HOLD,
            message=(
                "No comparable sales were extracted from the report. "
                "All sales comparison approach rules are suspended until the comparable "
                "grid can be confirmed. Please verify the extraction succeeded and re-run."
            ),
            confidence=0.9,
        ))
        logger.warning(
            "QC %s: zero comps extracted — SCA rules suspended (SCA-ZERO-COMPS HOLD)",
            ctx.transaction_id,
        )

    for spec in all_rules():
        if only_phase is not None and spec.phase != only_phase:
            continue
        if min_phase is not None and spec.phase > min_phase:
            continue
        # Time the actual evaluation of this rule — gate/applicability checks plus
        # the rule function. This is the real per-rule cost, measured every run.
        started = perf_counter()
        gate = _SECTION_GATE.get(spec.section)
        if gate is not None and not gate(ctx):
            report.results.append(RuleResult(
                rule_id=spec.rule_id, checklist_num=spec.checklist_num,
                section=spec.section, status=RuleStatus.NOT_APPLICABLE,
                message="No sales-comparison grid on this report form (e.g. appraisal update / completion report).",
            ))
            _record_timing(report, spec, RuleStatus.NOT_APPLICABLE, started)
            continue
        # Zero-comps gate: SCA rules are NOT_APPLICABLE when no grid was extracted.
        # Using NOT_APPLICABLE (not SKIPPED) because the rule genuinely cannot evaluate
        # on an empty grid — this is a form/data condition, not a system failure.
        if _zero_comps and spec.section == "sales_comparison":
            report.results.append(RuleResult(
                rule_id=spec.rule_id, checklist_num=spec.checklist_num,
                section=spec.section, status=RuleStatus.NOT_APPLICABLE,
                message="No comparable sales extracted from this report; rule cannot evaluate (see SCA-ZERO-COMPS HOLD).",
            ))
            _record_timing(report, spec, RuleStatus.NOT_APPLICABLE, started)
            continue
        if not spec.applicable(ctx):
            report.results.append(RuleResult(
                rule_id=spec.rule_id, checklist_num=spec.checklist_num,
                section=spec.section, status=RuleStatus.NOT_APPLICABLE,
                message="Not applicable to this loan/transaction/form type.",
            ))
            _record_timing(report, spec, RuleStatus.NOT_APPLICABLE, started)
            continue
        try:
            # attribute any Groq calls this rule makes to the rule (LLM telemetry)
            from app.extraction import llm_telemetry
            _span = llm_telemetry.set_span(spec.rule_id)
            try:
                out = spec.fn(ctx)
            finally:
                llm_telemetry.reset_span(_span)
            results = _normalize(out, spec)
            report.results.extend(results)
            # the rule's headline status (worst of any sub-results) labels the
            # timing; its confidence rides along for the confidence-vs-time view
            status = _worst_status(results)
            conf = next((r.confidence for r in results if r.status == status), 1.0)
            _record_timing(report, spec, status, started, conf)
        except Exception as exc:
            logger.error("QC rule %s crashed: %s", spec.rule_id, exc)
            report.results.append(RuleResult(
                rule_id=spec.rule_id, checklist_num=spec.checklist_num,
                section=spec.section, status=RuleStatus.SKIPPED,
                message=f"Rule execution error: {exc}",
            ))
            _record_timing(report, spec, RuleStatus.SKIPPED, started)
    _escalate_sections(report)
    _coerce_data_skipped_to_verify(report)
    _dedup_findings(report)
    return report


def _coerce_data_skipped_to_verify(report: QCReport) -> None:
    """
    Enforce the 3-outcome model: SKIPPED is only for rule crashes.
    Any SKIPPED returned for a data/policy reason becomes VERIFY so the reviewer
    sees it rather than it silently disappearing.

    Crash SKIPPED (message starts with 'Rule execution error') is preserved —
    it represents a genuine system failure, not a data gap.
    """
    coerced = 0
    for r in report.results:
        if r.status != RuleStatus.SKIPPED:
            continue
        if r.message and r.message.startswith("Rule execution error"):
            continue  # genuine crash — keep SKIPPED
        r.status = RuleStatus.VERIFY
        if r.message and not r.message.endswith("(manual review required)"):
            r.message = r.message.rstrip(". ") + " — manual review required."
        r.confidence = min(r.confidence or 0.5, 0.5)
        coerced += 1
    if coerced:
        logger.debug("Coerced %d data-SKIPPED findings to VERIFY", coerced)


# Worst-first precedence so a rule that emits several sub-results is labelled by
# its most severe outcome (matches the report-level overall() ordering).
_STATUS_RANK = {RuleStatus.HOLD: 5, RuleStatus.FAIL: 4, RuleStatus.VERIFY: 3,
                RuleStatus.SKIPPED: 2, RuleStatus.PASS: 1, RuleStatus.NOT_APPLICABLE: 0}


def _worst_status(results: List[RuleResult]) -> RuleStatus:
    if not results:
        return RuleStatus.SKIPPED
    return max((r.status for r in results), key=lambda s: _STATUS_RANK.get(s, 0))


def _record_timing(report: QCReport, spec: RuleSpec, status: RuleStatus,
                   started: float, confidence: float = 1.0) -> None:
    report.rule_timings.append(RuleTiming(
        rule_id=spec.rule_id, section=spec.section,
        status=status.value, ms=(perf_counter() - started) * 1000.0,
        confidence=confidence,
    ))


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


def _dedup_findings(report: QCReport) -> None:
    """Merge findings that point to the same root business issue.

    Grouping key = (section, entity_id, issue_category).

    The highest-severity finding in each group is kept; lower-severity duplicates
    are removed and their evidence is merged into the keeper so no source citation
    is lost. PASS / NOT_APPLICABLE / SKIPPED findings are never deduplicated —
    only actionable (HOLD / FAIL / VERIFY) results are candidates.

    This prevents the reviewer from seeing the same root problem described twice
    in different words because two rules fired on the same underlying data gap.
    """
    from collections import defaultdict

    def _group_key(r: RuleResult) -> str:
        # Entity: which comparable, the subject, or a document-level entity.
        entity = "subject"
        for f in r.fields_involved:
            if f.startswith("comp_") and "_" in f[5:]:
                n = f[5:].split("_")[0]
                if n.isdigit():
                    entity = f"comp_{n}"
                    break
        # Issue category: first six chars of rule_id (e.g. "SCA-17" → "SCA-17")
        # combined with the section name to ensure cross-section collisions can't happen.
        category = r.section or "general"
        # Use template_id when available for a more precise dedup key; fall back
        # to the first 6 characters of rule_id.
        issue = r.template_id or r.rule_id[:6]
        return f"{category}|{entity}|{issue}"

    groups: dict = defaultdict(list)
    for r in report.results:
        if r.status in (RuleStatus.PASS, RuleStatus.NOT_APPLICABLE, RuleStatus.SKIPPED):
            continue  # only dedup actionable findings
        groups[_group_key(r)].append(r)

    to_remove: set = set()
    _severity_order = {
        RuleStatus.HOLD: 4,
        RuleStatus.FAIL: 3,
        RuleStatus.VERIFY: 2,
        RuleStatus.SKIPPED: 1,
        RuleStatus.PASS: 0,
        RuleStatus.NOT_APPLICABLE: 0,
    }
    for key, group in groups.items():
        if len(group) < 2:
            continue
        # Sort worst-first so the most severe finding is the keeper.
        group.sort(key=lambda r: -_severity_order.get(r.status, 0))
        keeper = group[0]
        for dup in group[1:]:
            # Merge evidence from the duplicate into the keeper, avoiding duplicates
            # on the same canonical field (one citation per field is enough).
            existing_fields = {e.field for e in keeper.evidence}
            for ev in dup.evidence:
                if ev.field not in existing_fields:
                    keeper.evidence.append(ev)
                    existing_fields.add(ev.field)
            to_remove.add(id(dup))

    if to_remove:
        before = len(report.results)
        report.results = [r for r in report.results if id(r) not in to_remove]
        logger.debug(
            "QC dedup: removed %d duplicate findings (from %d → %d results)",
            before - len(report.results), before, len(report.results),
        )


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
