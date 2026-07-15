"""
pipeline.orchestrator — SHALqc.md §2. The synchronous QC pipeline:

  intake(+gates) → [G-3 cache] → extract → route → rules → profile-bind → report → persist

Covers SHALqc.md §1-10 + the §14 gates, §15 persistence, and the §16 partial-
failure contract. NOT wired here: the async Celery path (§9 async half — see
worker/tasks.py which reuses this same function).

§16 partial-failure contract: any stage-level exception is caught at THIS
boundary; the affected stage yields empty/degraded output, the run COMPLETES,
and report.degradations[] lists what broke. Java never receives a 5xx for a
processable order.
"""

from __future__ import annotations

import logging
import time
from typing import List, Optional

from app.extraction.engagement import extract_engagement
from app.extraction.merge import run_extraction
from app.extraction.result import ExtractedFieldSet
from app.pipeline.intake import assemble_order
from app.profiles.engine_binding import active_rules, apply_severity
from app.profiles.loader import load_profile
from app.report.builder import build_report
from app.report.versions import fingerprint, report_versions
from app.routing.router import router
from app.rules.context import QCContext
from app.rules.engine import run_rules
from app.rules.registry import all_rules
from app.rules.verdict import Verdict

logger = logging.getLogger(__name__)

__version__ = "api-1.0.0"


def _rule_names() -> dict:
    return {r.rule_id: r.name for r in all_rules()}


def _blocked_report(order, profile) -> dict:
    return {
        "order_id": order.order_id, "amc_code": profile.amc_code, "status": "BLOCKED",
        "summary": {"passed": 0, "failed": 0, "hold": 1, "to_verify": 0, "not_applicable": 0},
        "cards": [], "hold_reasons": [order.hold_reason], "degradations": [],
        "versions": report_versions(profile),
    }


def run_qc(order_dir, llm_client=None, persist: bool = True, judge_mode: bool = False,
           mode: Optional[str] = None, amc_code: Optional[str] = None) -> dict:
    """Run the full synchronous pipeline for one order folder → reviewer report.

    Honors §14 G-0..G-3 (block / cache / XML-overlay-disable), §16 partial-
    failure (never a 5xx), and §15 persistence + revision numbering.

    `mode` (final_shalqccore.md §9) selects the judgment path: "language" runs the
    v1.0.69 language-driven judge; anything else keeps the legacy rule engine.
    Defaults to settings.judge_mode (env JUDGE_MODE). Both paths share
    extraction/locate/report and never 5xx.
    """
    from app.config import settings
    from app.persistence import repo

    mode = (mode or settings.judge_mode or "legacy").lower()

    order = assemble_order(order_dir)
    # Caller-supplied amc_code (e.g. Java passes the client's AMC code on
    # /qc/process) wins over engagement/order-id resolution — a co-located temp
    # order dir has no matching order-id prefix, so without this it silently falls
    # back to the _base catalog instead of the AMC's own compiled bundle.
    if amc_code and amc_code.strip():
        order.amc_code = amc_code.strip()
    profile = load_profile(order.amc_code)

    if order.status == "BLOCKED":
        return _blocked_report(order, profile)

    # §14 G-3 idempotency: identical package already processed ⇒ return stored run.
    if persist and order.package_hash:
        cached = repo.get_cached_run(order.order_id, order.package_hash)
        if cached is not None:
            logger.info("run_qc %s: G-3 cache hit — returning stored run", order.order_id)
            return cached

    degradations: List[str] = []

    # 2026-07-13 timing ledger (perf work order): wall-clock the stages that
    # actually cost time, so speed is a monitored property, not something
    # re-diagnosed from scratch every time it regresses.
    _t_extract0 = time.perf_counter()

    # §16 partial-failure: each stage is wrapped; a stage crash degrades, never 5xxs.
    appraisal_fs = _safe_stage(
        "extraction", degradations, ExtractedFieldSet(),
        lambda: run_extraction(
            appraisal_pdf=order.appraisal_pdf,
            # §14 G-2: a wrong-order XML has its overlay disabled → PDF-only.
            xml_path=None if order.xml_overlay_disabled else order.xml,
            engagement_letter=None, llm_client=llm_client,
        ),
    )
    if order.xml_overlay_disabled:
        degradations.append("xml_document_mismatch: XML overlay disabled (PDF-only mode)")

    engagement_fs = None
    if order.engagement_letter:
        # CORE §12: the active AMC's engagement_hints override the label set.
        hints = getattr(profile, "engagement_hints", None) or None
        engagement_fs = _safe_stage("engagement", degradations, None,
                                    lambda: extract_engagement(order.engagement_letter, hints=hints))

    # CORE §11: purchase contract read (LLM, conf 0.75). Only when a contract
    # doc is present AND an LLM is configured (else contract rules stay VERIFY).
    contract_fs = None
    if getattr(order, "contract", None):
        from app.extraction.contract import extract_contract
        contract_fs = _safe_stage("contract", degradations, None,
                                  lambda: extract_contract(order.contract, llm_client=llm_client))

    # §7 routing: suppress sub-threshold reads → MISSING before rules run.
    n = router.apply(appraisal_fs)
    if engagement_fs is not None:
        n += router.apply(engagement_fs)
    if n:
        degradations.append(f"{n} field(s) suppressed below routing threshold (MISSING)")

    if contract_fs is not None:
        router.apply(contract_fs)

    extract_s = time.perf_counter() - _t_extract0

    # final_shalqccore.md §2/§9: the language-driven judgment path. Shares the
    # extraction/locate above; replaces rules+report with the compiled-checklist
    # judge. Wrapped in §16 partial-failure so a language-path crash still returns.
    if mode == "language":
        report = _safe_stage(
            "language_judge", degradations, None,
            lambda: _run_language(order, profile, appraisal_fs, engagement_fs,
                                  contract_fs, llm_client, degradations))
        if report is not None:
            timings = report.setdefault("timings", {})
            timings["extract_s"] = round(extract_s, 2)
            timings["total_s"] = round(extract_s + timings.get("judge_and_packet_s", 0.0), 2)
            return _finalize(report, order, profile, persist, repo)
        # a total language-path failure degrades to the legacy path rather than 5xx.
        degradations.append("language_path_failed: fell back to legacy engine")

    ctx = QCContext(order_id=order.order_id, appraisal=appraisal_fs, engagement=engagement_fs,
                    contract=contract_fs, profile=profile,
                    review_conf=router.thresholds_for("__default__").review,
                    llm_client=llm_client)

    verdicts: List[Verdict] = _safe_stage(
        "rules", degradations, [],
        lambda: run_rules(ctx, rules=active_rules(profile), llm_client=llm_client,
                          judge_mode=judge_mode))
    # CORE §11: cap contract-backed FAILs at VERIFY unless corroborated (least
    # trustworthy input); then apply the AMC severity remaps.
    from app.rules.verdict import contract_cap
    contract_cap(verdicts)
    apply_severity(profile, verdicts)

    hold_reasons: List[str] = []
    if profile.is_fallback:
        hold_reasons.append(f"AMC profile not found for '{order.amc_code}' — using base profile.")

    report = build_report(order_id=order.order_id, verdicts=verdicts, rule_names=_rule_names(),
                          profile=profile, amc_code=profile.amc_code,
                          hold_reasons=hold_reasons, degradations=degradations)
    report["status"] = "OK"

    # §15 persistence + revision numbering + §1 fingerprint.
    fp = fingerprint(profile, order.package_hash or "")
    report["fingerprint"] = fp
    revision_no = repo.next_revision_no(order.order_id) if persist else 0
    report["revision_no"] = revision_no
    if persist:
        run_id = repo.save_run(order.order_id, profile.amc_code, order.package_hash or "",
                               fp, revision_no, report)
        if run_id:
            report["run_id"] = run_id

    logger.info("run_qc %s (rev %d): %s", order.order_id, revision_no, report["summary"])
    return report


def _run_language(order, profile, appraisal_fs, engagement_fs, contract_fs,
                  llm_client, degradations: List[str]) -> dict:
    """final_shalqccore.md §2: compile the AMC checklist (cached by hash) then run
    the language judge over the already-extracted+located field sets."""
    from app.language import compiler as C
    from app.language.compiler import BINDER_PROMPT_VERSION, compile_checklist
    from app.language.judge_v2 import PROMPT_VERSION as JUDGE_V2
    from app.language.run import run_language
    from app.config import settings

    # Step 1 sign-off gate: only an approved (status=active) bundle may run a live
    # order. An unsigned bundle either hard-stops (require_signed_bundle) or runs
    # with a loud degradation so the false-reject risk is never silent.
    bundle = C.compiled_path(profile.amc_code)
    status = C.bundle_status(bundle)
    if status != C.STATUS_ACTIVE:
        msg = (f"bundle_not_signed_off:{profile.amc_code}:{status}")
        if settings.require_signed_bundle:
            raise RuntimeError(
                f"AMC {profile.amc_code} checklist bundle is '{status}', not active. "
                f"Compile + approve it first (tools/compile_amc.py --approve).")
        degradations.append(msg)
        logger.warning("run_language: %s — running an unsigned bundle (degraded).", msg)

    compiled = compile_checklist(profile.amc_code, client=llm_client)
    versions = dict(report_versions(profile))
    versions.update({"judge_mode": "language", "binder_prompt": BINDER_PROMPT_VERSION,
                     "judge_prompt": JUDGE_V2, "packet_builder": "pkt-2.0.0"})
    return run_language(order.order_id, profile.amc_code, appraisal_fs, engagement_fs,
                        contract_fs, compiled, llm_client,
                        degradations=degradations, versions=versions)


def _finalize(report: dict, order, profile, persist: bool, repo) -> dict:
    """§15 persistence + revision numbering + §1 fingerprint (shared by both paths)."""
    fp = fingerprint(profile, order.package_hash or "")
    report["fingerprint"] = fp
    revision_no = repo.next_revision_no(order.order_id) if persist else 0
    report["revision_no"] = revision_no
    if persist:
        run_id = repo.save_run(order.order_id, profile.amc_code, order.package_hash or "",
                               fp, revision_no, report)
        if run_id:
            report["run_id"] = run_id
    logger.info("run_qc %s (rev %d, language): %s", order.order_id, revision_no,
                report.get("summary"))
    return report


def _safe_stage(name: str, degradations: List[str], fallback, fn):
    """Run one pipeline stage; on exception record a degradation and return the
    fallback so the run completes (§16). Extractors already catch internally
    (P6); this is the last-resort boundary for a whole-stage failure."""
    try:
        return fn()
    except Exception as exc:
        logger.warning("stage %s failed: %s", name, exc)
        degradations.append(f"stage_failed:{name}: {exc}")
        return fallback
