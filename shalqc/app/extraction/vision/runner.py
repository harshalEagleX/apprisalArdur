"""
extraction.vision.runner (vrn-1.0.0) — the UAD 3.6 extraction path, end to end.

    structural probe (free)
        -> triage: which page holds which section (layout-independent)
        -> section transcription (one call per section, abstention required)
        -> grid transcription (all columns, then checksum-gated per column)
        -> deterministic verification
        -> ExtractedFieldSet, shared with the 2.6 path from here on

Everything downstream — plausibility, normalizer, back-locator, merge, judge,
severity gate, persistence, reviewer UI — is version-agnostic and untouched.

The contract that makes the output safe to trust: a value whose region's
arithmetic CLOSED is emitted at `Source.VISION` (0.93); a value from a region
that could not be verified is emitted at `Source.VISION_UNVERIFIED` (0.55) so it
can never outrank a deterministic witness and lands in front of a reviewer. An
unverified read is never silently promoted to a pass.
"""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, List, Optional, Tuple

from app.extraction import page_map, verify as V
from app.extraction.result import ExtractedField, ExtractedFieldSet, Source
from app.extraction.vision.budget import BudgetExceeded, BudgetGovernor, project_order_cost
from app.extraction.vision.grid import extract_grid, grid_row_vocabulary
from app.extraction.vision.provider import VisionProvider, get_vision_provider
from app.extraction.vision.sections import extract_sections

__version__ = "vrn-1.0.0"

logger = logging.getLogger(__name__)

# Verified by arithmetic, or from a region with no checksum available.
_CONF_VERIFIED = 0.93
# Region failed its checksum, or no check could run. Deliberately below
# pdf_digital (0.92) and pdf_scanned so a deterministic witness always wins.
_CONF_UNVERIFIED = 0.55


def run_vision_extraction(appraisal_pdf, schema=None,
                          provider: Optional[VisionProvider] = None,
                          expected_comps: Optional[int] = None
                          ) -> Tuple[ExtractedFieldSet, Dict[str, Any]]:
    """Extract a UAD 3.6 report. Returns `(fields, report)`.

    Never raises: every failure mode — no provider, budget exhausted, a page
    that will not render, a model that refuses — degrades to fewer fields plus
    a recorded degradation. A 3.6 order must never fail closed on a vision
    problem; it must arrive at a reviewer with what was read and an honest
    account of what was not.
    """
    from app import runtime_config as rc
    from app.config import settings

    report: Dict[str, Any] = {"version": __version__, "degradations": [],
                              "uad_version": "3.6"}

    profiles = page_map.profile(appraisal_pdf)
    if not profiles:
        report["degradations"].append("PDF could not be opened or has no pages")
        return ExtractedFieldSet(), report

    plan = page_map.extraction_plan(profiles)
    report["page_map"] = plan
    report["document_class"] = plan["document_class"]

    provider = provider or get_vision_provider()
    if provider is None:
        report["degradations"].append(
            "no vision provider configured — UAD 3.6 fields cannot be extracted; "
            "every 3.6 checklist item will need a reviewer")
        return ExtractedFieldSet(), report

    cap = float(rc.get("vision_budget_usd_per_order", settings.vision_budget_usd_per_order))
    governor = BudgetGovernor(cap_usd=cap, model=provider.model)

    projection = project_order_cost(
        page_count=len(profiles), extractable_pages=len(plan["extractable_pages"]),
        comp_count=expected_comps or 6, model=provider.model)
    report["cost_projection"] = projection
    logger.info("vision: %s — %d/%d pages extractable, ~%d calls, projected $%.4f "
                "(cap $%.2f)", provider.model, len(plan["extractable_pages"]),
                len(profiles), projection["calls"], projection["usd_with_retries"], cap)
    if projection["usd_with_retries"] > cap:
        report["degradations"].append(
            f"projected cost ${projection['usd_with_retries']:.2f} exceeds the "
            f"${cap:.2f}/order cap — extraction will stop early and unread "
            f"regions will need a reviewer")

    dpi_section = int(rc.get("vision_dpi_section", settings.vision_dpi_section))
    dpi_grid = int(rc.get("vision_dpi_grid", settings.vision_dpi_grid))
    dpi_retry = int(rc.get("vision_dpi_retry", settings.vision_dpi_retry))
    retries = int(rc.get("vision_max_retries", settings.vision_max_retries))
    effort_sec = str(rc.get("vision_effort_section", settings.vision_effort_section))
    effort_grid = str(rc.get("vision_effort_grid", settings.vision_effort_grid))

    use_triage = bool(rc.get("vision_use_triage", settings.vision_use_triage))
    # Concurrency is derived from the KEY POOL, not set as an absolute. Each key
    # serves a fixed total throughput, so what matters is calls-per-key: run wide
    # and every call is starved to a fraction of the rate, which is what produced
    # the "25 tok/s floor" and the timeouts that killed two whole sections.
    keys = getattr(provider, "key_count", 1) or 1
    concurrency = min(keys * int(rc.get("vision_calls_per_key",
                                        settings.vision_calls_per_key)),
                      int(rc.get("vision_concurrency", settings.vision_concurrency)))
    logger.info("vision: %d key(s) x %s calls/key -> concurrency %d",
                keys, rc.get("vision_calls_per_key", settings.vision_calls_per_key),
                concurrency)
    mt_section = int(rc.get("vision_max_tokens_section", settings.vision_max_tokens_section))
    mt_grid = int(rc.get("vision_max_tokens_grid", settings.vision_max_tokens_grid))

    # Grid pages, found structurally — no model call and no latency. A sales-grid
    # page is uniquely dense in vector rules (table borders): measured on this
    # form, grid pages carry ~2,400 drawings against ~300-1,700 elsewhere. When
    # triage is enabled it refines this; the structural guess is the default so
    # nothing sits in front of the first extraction call.
    grid_pages = page_map.likely_grid_pages(profiles)
    report["grid_pages_structural"] = grid_pages

    # ── sections + grid, ONE parallel wave ────────────────────────────────────
    # Per-call latency is ~40s and irreducible (it is reasoning time — measured
    # identical for a value-only schema), so a 60s/order target is only reachable
    # if the calls overlap rather than queue. Sections and grid pages are
    # independent, so they run together.
    with ThreadPoolExecutor(max_workers=2) as pool:
        f_sections = pool.submit(
            _safe_sections, appraisal_pdf, profiles, provider, governor,
            dpi_section, effort_sec, use_triage, mt_section, concurrency)
        f_grid = pool.submit(
            _safe_grid, appraisal_pdf, grid_pages, provider, governor, dpi_grid,
            dpi_retry, effort_grid, retries, expected_comps, mt_grid, concurrency)
        values, sec_meta = f_sections.result()
        grid, grid_meta = f_grid.result()

    report["sections"] = sec_meta
    report["degradations"].extend(sec_meta.get("degradations", []))
    report["grid"] = grid_meta
    report["degradations"].extend(grid_meta.get("degradations", []))

    # ── cross-verification: the report checking itself, for free ──────────────
    # Runs BEFORE the arithmetic checks are reported, because it can settle
    # things they cannot: a comparable whose line items failed to reconcile may
    # still have its adjusted price independently confirmed by the Value
    # Reconciliation table on a different page. It also localises misreads to a
    # single page, turning a whole-order re-run into a one-page re-read.
    try:
        from app.extraction import consistency as CN
        cross = CN.check_order(values)
        cross["grid_cross_check"] = CN.cross_check_grid(
            grid.get("comparables") or [], _reconciliation_rows(values))
        report["consistency"] = cross
        logger.info("vision: %s", CN.summarize(cross))
        if cross.get("repair_pages"):
            report["degradations"].append(
                f"pages {cross['repair_pages']} disagree with the majority of "
                f"sources and are worth re-reading")
        for bad in (cross["grid_cross_check"].get("mismatched") or []):
            report["degradations"].append(bad["note"])
    except Exception as exc:
        logger.warning("vision: consistency pass failed: %s", exc)
        report["consistency"] = {"error": str(exc)}

    # ── narrative blocks, verbatim ────────────────────────────────────────────
    # Kept as prose because the findings that matter most are not field-shaped.
    # The contract-analysis paragraph on this order states a required septic
    # repair while the report is dated As Is — a contradiction that exists only
    # when both statements survive, and one of them is a sentence.
    try:
        from app.extraction.vision.narrative import (extract_narratives,
                                                     find_contradictions)
        blocks = _narrative_pages(sec_meta, plan["extractable_pages"])
        if blocks:
            narratives = extract_narratives(appraisal_pdf, blocks, provider,
                                            concurrency=concurrency)
            report["narratives"] = {n: b.as_dict() for n, b in narratives.items()}
            conflicts = find_contradictions(narratives, values)
            report["narrative_conflicts"] = conflicts
            for c in conflicts:
                report["degradations"].append(
                    f"{c['detail']} (page {', '.join(str(p) for p in c['pages'])})")
            unread = [n for n, b in narratives.items() if not b.read]
            if unread:
                report["degradations"].append(
                    f"narrative block(s) not read: {', '.join(unread)} — any finding "
                    f"that lives in that prose cannot be raised")
    except Exception as exc:
        logger.warning("vision: narrative pass failed: %s", exc)
        report["narratives"] = {"error": str(exc)}

    # ── completeness gate ─────────────────────────────────────────────────────
    #
    # A section that returned NOTHING is not a section with no findings — it is a
    # section nobody read. Run 18 lost `market` and `contract_history` entirely
    # (41 fields, including the contract-analysis sentence carrying the biggest
    # finding on the order) and still printed DONE with "coverage 125.7%",
    # because coverage counted comparable columns against a subject-field
    # denominator. A health metric that reads green on an unreviewable run is
    # worse than no metric: it converts a loud failure into a silent one.
    #
    # So the run is marked INCOMPLETE and the caller must not publish verdicts
    # from it. Whatever WAS read is still returned — a reviewer re-running one
    # section beats re-running the order — but it is labelled.
    resilience = (sec_meta.get("resilience") or {})
    empty_sections = sorted(name for name, m in resilience.items()
                            if not (m or {}).get("fields"))
    attempted = sec_meta.get("sections_attempted") or []
    if empty_sections:
        report["status"] = "INCOMPLETE"
        report["incomplete_reason"] = (
            f"{len(empty_sections)} of {len(attempted)} section(s) returned no "
            f"fields and were not read: {', '.join(empty_sections)}. Verdicts from "
            f"this run would be based on evidence nobody saw.")
        report["empty_sections"] = empty_sections
        report["degradations"].append(report["incomplete_reason"])
        logger.error("vision: RUN INCOMPLETE — %s", report["incomplete_reason"])
    else:
        report["status"] = "COMPLETE"

    # ── partial-credit reconciliation of the comparable grid ──────────────────
    # Runs before the pass/fail checks because it answers a different and more
    # useful question. `verify_comp_column` asks "does everything reconcile?",
    # which forces a comparable whose second page never arrived to be reported as
    # a FAILURE — run 16 read comp 1's page 22 correctly and called it a defect.
    #
    # Reconciling instead extracts three things from the same fragments: the
    # identities that can be proven now, an exact required value for whatever is
    # missing, and the name of the single call to retry. The net does not depend
    # on the page that prints it — page 33 restates every adjusted price, and
    # net = adjusted - sale — so a missing summary page is recoverable.
    report["grid_reconciliation"] = _reconcile_grid(
        grid.get("comparables") or [], grid_meta, _reconciliation_rows(values))

    # ── deterministic verification over everything read ───────────────────────
    checks = V.verify_all(
        {"comparables": grid.get("comparables") or [],
         "sketch": _sketch_view(values),
         "unit_interior": {"finished_above_grade": _plain(values.get("gla"))}},
        expected_comps=expected_comps)
    report["verification"] = V.summarize(checks)
    verified_regions = {c.region for c in checks if c.verified}

    # ── to ExtractedFields ────────────────────────────────────────────────────
    fs = ExtractedFieldSet()
    _emit_section_fields(fs, values, verified_regions)
    _emit_grid_fields(fs, grid, grid_meta)

    report["budget"] = governor.summary()
    report["timeline"] = governor.timeline()
    report["fields_extracted"] = len(fs.found_fields())
    if schema is not None:
        total = len(schema.all_fields())
        # Coverage counted EVERY extracted field — including six comparable
        # columns' worth of rows — against a denominator of subject fields only,
        # and so reported 125.7% on a run that had lost two whole sections. A
        # percentage above 100 is a metric describing itself, not the work.
        #
        # Comparable rows are counted separately because they answer different
        # questions and fail independently.
        found = fs.found_fields()
        comp_fields = [f for f in found if str(f.canonical_name).startswith("comp_")]
        subject_fields = [f for f in found if not str(f.canonical_name).startswith("comp_")]
        report["schema_fields"] = total
        report["coverage_pct"] = round(
            100.0 * min(len(subject_fields), total) / max(total, 1), 1)
        report["coverage_detail"] = {
            "subject_fields_read": len(subject_fields),
            "subject_fields_in_schema": total,
            "comparable_fields_read": len(comp_fields),
            # The number that actually decides whether this run is usable.
            "sections_empty": report.get("empty_sections") or [],
        }

    logger.info("vision: %d fields, %d/%d regions verified, $%.4f spent",
                len(fs.found_fields()), report["verification"]["verified"],
                report["verification"]["regions"], governor.spent_usd)
    return fs, report


# ── helpers ───────────────────────────────────────────────────────────────────

def _safe_sections(pdf, profiles, provider, governor, dpi, effort, use_triage,
                   max_tokens, concurrency):
    try:
        return extract_sections(pdf, profiles, provider, governor, dpi=dpi,
                                effort=effort, use_triage=use_triage,
                                max_tokens=max_tokens, concurrency=concurrency)
    except BudgetExceeded as exc:
        return {}, {"degradations": [str(exc)]}
    except Exception as exc:
        logger.warning("vision: section pass failed: %s", exc)
        return {}, {"degradations": [f"section pass failed: {exc}"]}


def _safe_grid(pdf, grid_pages, provider, governor, dpi, dpi_retry, effort,
               retries, expected_comps, max_tokens, concurrency):
    empty = {"comparables": [], "complete": False, "subject": {}}
    try:
        return extract_grid(pdf, grid_pages, provider, governor, dpi=dpi,
                            dpi_retry=dpi_retry, effort=effort, max_retries=retries,
                            expected_comps=expected_comps, max_tokens=max_tokens,
                            concurrency=concurrency)
    except BudgetExceeded as exc:
        return empty, {"degradations": [str(exc)]}
    except Exception as exc:
        logger.warning("vision: grid pass failed: %s", exc)
        return empty, {"degradations": [f"grid pass failed: {exc}"]}



def _plain(entry: Any) -> Any:
    return entry.get("value") if isinstance(entry, dict) else entry


def _reconciliation_rows(values: Dict[str, Any]) -> List[Dict[str, Any]]:
    """The Value Reconciliation table, if the reconciliation section captured it.

    Absent is a normal outcome, not an error — not every vendor prints one. The
    grid simply loses its independent cross-check for that order, which the
    caller records rather than treating as a failure.
    """
    rows = _plain(values.get("value_reconciliation"))
    if isinstance(rows, list):
        return [r for r in rows if isinstance(r, dict)]
    return []


def _reconcile_grid(comps: List[Dict[str, Any]], grid_meta: Dict[str, Any],
                    recon_rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Per-comparable CERTIFIED / PARTIAL / CONFLICT, with the retry named.

    The pages a comparable was SUPPOSED to cover come from the call log, not from
    what landed — that difference is the whole point. A comparable that returned
    three rows because its other call timed out is incomplete, not wrong, and
    only the call log knows which of those two it is.
    """
    expected: Dict[Any, set] = {}
    for call in (grid_meta.get("calls") or []):
        comp_no = call.get("comp")
        if comp_no is None:
            continue
        expected.setdefault(comp_no, set()).update(call.get("pages") or [])

    key_by_comp: Dict[Any, Dict[str, Any]] = {}
    for row in recon_rows:
        num = row.get("comp_number") or row.get("comparable") or row.get("comp")
        try:
            key_by_comp[int(str(num).strip())] = row
        except (TypeError, ValueError):
            continue

    out: List[Dict[str, Any]] = []
    for comp in comps:
        num = comp.get("comp_number")
        rec = V.reconcile_comp(comp, num,
                               pages_expected=sorted(expected.get(num, set())),
                               answer_key=key_by_comp.get(num),
                               # The grid's canonical row vocabulary, so an
                               # adjustment filed under a row this form does not
                               # print is caught as the column shift it is.
                               expected_rows=grid_row_vocabulary())
        out.append(rec.as_dict())

    tally: Dict[str, int] = {}
    for r in out:
        tally[r["status"]] = tally.get(r["status"], 0) + 1
    retries = [name for r in out for name in r["retry"]
               if r["status"] in (V.PARTIAL, V.UNREAD)]
    logger.info("vision: grid reconciliation — %s; retry %d call(s): %s",
                ", ".join(f"{v} {k}" for k, v in sorted(tally.items())) or "nothing read",
                len(retries), ", ".join(retries) or "none")
    return {"comparables": out, "tally": tally, "retry_calls": retries}


def _sketch_view(values: Dict[str, Any]) -> Dict[str, Any]:
    """Reshape the sketch section's output into what verify_area expects."""
    calcs = _plain(values.get("living_area_calcs")) or []
    return {"living_area_calcs": calcs if isinstance(calcs, list) else [],
            "total_living_area": _plain(values.get("total_living_area"))}


def _emit_section_fields(fs: ExtractedFieldSet, values: Dict[str, Any],
                         verified_regions: set) -> None:
    sketch_ok = "sketch" in verified_regions
    for name, payload in values.items():
        value = _plain(payload)
        if value in (None, "", []):
            continue
        if isinstance(value, list):
            # A list field (area calcs, listing history, trend matrix) is joined
            # for the scalar field contract; the structured form stays in the
            # run report for the judge's packet.
            value = "; ".join(str(v.get("value") if isinstance(v, dict) else v)
                              for v in value)
            if not value:
                continue
        # Only the sketch has a checksum at section level. Everything else has
        # no arithmetic to check, which is NOT the same as failing one — those
        # fields keep the verified confidence and rely on abstention plus
        # provenance instead of pretending a check ran.
        unverified = name in ("total_living_area", "living_area_calcs") and not sketch_ok
        fs.add(ExtractedField(
            canonical_name=name, value=str(value), raw_value=str(value),
            source=Source.VISION_UNVERIFIED if unverified else Source.VISION,
            confidence=_CONF_UNVERIFIED if unverified else _CONF_VERIFIED,
            page=int(payload.get("page") or 0) if isinstance(payload, dict) else 0,
            # No bbox: the page has no text layer to locate against, so the
            # back-locator cannot refine this. "page" is honest — the reviewer
            # gets scroll-to-page rather than a box drawn in the wrong place.
            location_quality="page",
        ))


def _emit_grid_fields(fs: ExtractedFieldSet, grid: Dict[str, Any],
                      grid_meta: Dict[str, Any]) -> None:
    """Emit comp_<n>_<suffix> fields — the naming the rest of the stack speaks."""
    verification = grid_meta.get("verification") or {}
    comps = grid.get("comparables") or []

    for comp in comps:
        n = comp.get("comp_number")
        if n is None:
            continue
        ok = bool(verification.get(f"comp_{n}", {}).get("verified"))
        src = Source.VISION if ok else Source.VISION_UNVERIFIED
        conf = _CONF_VERIFIED if ok else _CONF_UNVERIFIED
        page = int(comp.get("_page") or 0)

        for key, raw in comp.items():
            if key.startswith("_") or key == "comp_number" or raw in (None, ""):
                continue
            if isinstance(raw, dict):
                value, adjustment = raw.get("value"), raw.get("adjustment")
                if value not in (None, ""):
                    _add(fs, f"comp_{n}_{key}", value, src, conf, page)
                # The adjustment is emitted as its own field, and a literal "0"
                # is emitted rather than skipped: "adjusted by zero" and "no
                # adjustment shown" are different facts, and the difference is
                # exactly the concessions finding this grid exists to surface.
                if adjustment not in (None, ""):
                    _add(fs, f"comp_{n}_{key}_adjustment", adjustment, src, conf, page)
            else:
                _add(fs, f"comp_{n}_{key}", raw, src, conf, page)

    if comps:
        _add(fs, "comparable_count", str(len(comps)),
             Source.VISION if grid.get("complete") else Source.VISION_UNVERIFIED,
             _CONF_VERIFIED if grid.get("complete") else _CONF_UNVERIFIED, 0)
    subject = grid.get("subject") or {}
    for key, value in subject.items():
        if value:
            _add(fs, f"subject_grid_{key}", value, Source.VISION, _CONF_VERIFIED, 0)


def _add(fs: ExtractedFieldSet, name: str, value: Any, source: str,
         confidence: float, page: int) -> None:
    fs.add(ExtractedField(
        canonical_name=name, value=str(value), raw_value=str(value),
        source=source, confidence=confidence, page=page, location_quality="page"))


def _narrative_pages(sec_meta: Dict[str, Any],
                     extractable: List[int]) -> Dict[str, List[int]]:
    """Which pages carry each free-text region.

    Taken from the pages the section pass ACTUALLY read, not from a positional
    guess — the sections already located themselves, and reusing that costs
    nothing and cannot drift from it.
    """
    read_pages = (sec_meta.get("section_pages") or {})
    wanted = {
        # The paragraph carrying the biggest finding on the sample order.
        "contract_analysis": "contract_history",
        "listing_history": "contract_history",
        "reconciliation_comment": "reconciliation",
        "sketch_commentary": "sketch",
        "market_commentary": "market",
    }
    out: Dict[str, List[int]] = {}
    for block, section in wanted.items():
        pages = read_pages.get(section)
        if pages:
            out[block] = list(pages)
    return out
