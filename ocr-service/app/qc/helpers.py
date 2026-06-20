"""
Rule helper builders.

Common rule shapes (presence, format, cross-document match, checkbox) are built
here so each rule stays one or two lines and the confidence→VERIFY downgrade is
applied consistently in one place (P-3). Rules import these and return the
RuleResult(s) they produce.

Downgrade policy (per agreed thresholds):
  * A deterministic FAIL becomes VERIFY when the underlying extraction
    confidence is below the structured/checkbox cutoff — we don't auto-reject
    on a value we're unsure we read correctly.
  * A PASS on a low-confidence read also becomes VERIFY (silent wrong-pass is
    worse than asking).
"""

from __future__ import annotations

import re
from typing import List, Optional

from app.qc import matching
from app.qc.config import qc_config
from app.qc.context import QCContext
from app.qc.result import Evidence, RuleResult, RuleStatus

# Canonical interpretations of checkbox/boolean extraction values, shared by
# every rule module (DRY) — extend here, never per-module.
TRUTHY = {"true", "yes", "1", "x", "checked"}
FALSY = {"false", "no", "0", "unchecked"}


def _conf_floor(ctx: QCContext, doc: str, field: str) -> float:
    return ctx.checkbox_conf if ctx.doc(doc).is_checkbox(field) else ctx.structured_conf


def _mk(rule_id, num, section, status, message="", fields=None,
        evidence=None, confidence=1.0, template_id=None, reasoning=None) -> RuleResult:
    return RuleResult(
        rule_id=rule_id, checklist_num=num, section=section, status=status,
        message=message, fields_involved=fields or [], evidence=evidence or [],
        confidence=confidence, template_id=template_id, reasoning=reasoning,
    )


# public RuleResult builders — rule modules use these instead of redefining
# their own constructors (DRY)
make_result = _mk


def section_result(section: str):
    """A RuleResult builder bound to one section: the shape every rule module
    was re-implementing as a private `_res`."""
    def _res(rule_id, num, status, message="", fields=None, evidence=None,
             template_id=None, confidence=1.0, reasoning=None) -> RuleResult:
        return _mk(rule_id, num, section, status, message=message, fields=fields,
                   evidence=evidence, confidence=confidence, template_id=template_id,
                   reasoning=reasoning)
    return _res


def _gate(ctx: QCContext, doc: str, field: str, status: RuleStatus,
          want_status: RuleStatus) -> RuleStatus:
    """Downgrade an asserted PASS/FAIL to VERIFY when the read is low-confidence."""
    conf = ctx.doc(doc).confidence(field)
    if conf < _conf_floor(ctx, doc, field):
        return RuleStatus.VERIFY
    return status


# ---------------------------------------------------------------------------
# Presence / blank checks (Phase 1)
# ---------------------------------------------------------------------------

def present(ctx, rule_id, num, section, field, doc="appraisal",
            template_id="S-3-blank", label=None) -> RuleResult:
    """Field must be non-blank on `doc`. FAIL (or VERIFY if unsure) when blank."""
    view = ctx.doc(doc)
    val = view.value(field)
    ev = [view.evidence(field)]
    label = label or field.replace("_", " ").title()
    if val and str(val).strip():
        return _mk(rule_id, num, section, RuleStatus.PASS, fields=[field], evidence=ev)
    # blank — but if the doc itself is absent we can't assert FAIL. Never a
    # silent SKIPPED (invisible to the reviewer): surface it for manual review.
    if not view.present:
        return _mk(rule_id, num, section, RuleStatus.VERIFY,
                   message=f"The {doc} document was not available; please verify {label} manually.",
                   fields=[field], evidence=ev, confidence=0.5)
    msg = qc_config.template(template_id, field=label)
    return _mk(rule_id, num, section, RuleStatus.FAIL, message=msg,
               fields=[field], evidence=ev, template_id=template_id)


# ---------------------------------------------------------------------------
# Format checks (Phase 1)
# ---------------------------------------------------------------------------

def format_regex(ctx, rule_id, num, section, field, pattern, template_id,
                 doc="appraisal", label=None) -> RuleResult:
    view = ctx.doc(doc)
    val = view.value(field)
    ev = [view.evidence(field)]
    if not val:
        # extraction gap — a reviewer must look; SKIPPED would be invisible
        return _mk(rule_id, num, section, RuleStatus.VERIFY,
                   message=f"{label or field} could not be extracted from the document; "
                           "manual review required.",
                   fields=[field], evidence=ev, confidence=0.5)
    status = RuleStatus.PASS if re.search(pattern, str(val)) else RuleStatus.FAIL
    status = _gate(ctx, doc, field, status, RuleStatus.FAIL)
    msg = "" if status == RuleStatus.PASS else qc_config.template(template_id, field=label or field, value=val)
    return _mk(rule_id, num, section, status, message=msg, fields=[field],
               evidence=ev, template_id=template_id if status != RuleStatus.PASS else None)


# ---------------------------------------------------------------------------
# Cross-document match (Phase 2)
# ---------------------------------------------------------------------------

def cross_doc_match(ctx, rule_id, num, section, field, template_id,
                    authority="engagement", subject_doc="appraisal",
                    kind="generic", label=None) -> RuleResult:
    """
    Compare subject_doc's value against the authority document's value using
    normalized fuzzy match. match→PASS, review→VERIFY, mismatch→FAIL.
    Low extraction confidence on either side forces VERIFY.
    """
    sub = ctx.doc(subject_doc)
    auth = ctx.doc(authority)
    sv, av = sub.value(field), auth.value(field)
    ev = [sub.evidence(field), auth.evidence(field)]
    fields = [field]
    if not auth.present:
        # missing engagement letter → the rule genuinely cannot evaluate (N/A);
        # missing purchase contract → the reviewer must compare manually (VERIFY)
        if authority == "engagement":
            return _mk(rule_id, num, section, RuleStatus.NOT_APPLICABLE,
                       message="Engagement letter / order form not available.",
                       fields=fields, evidence=ev)
        return _mk(rule_id, num, section, RuleStatus.VERIFY,
                   message=f"The {authority} document was not provided; please verify "
                           f"the {label or field} manually.",
                   fields=fields, evidence=ev, confidence=0.5)
    if sv is None or av is None:
        # one side missing → cannot assert match; surface for review
        return _mk(rule_id, num, section, RuleStatus.VERIFY,
                   message=qc_config.template(template_id, value=av or sv or "",
                                              a=sv or "", b=av or "", field=label or field),
                   fields=fields, evidence=ev, template_id=template_id, confidence=0.5)

    if kind == "currency":
        mr = matching.match_currency(sv, av, tolerance=qc_config.semantic("currency_tolerance", 0.0))
    elif kind == "date":
        mr = matching.match_date(sv, av)
    else:
        mr = matching.match_text(sv, av, kind=kind,
                                 match_th=qc_config.match_threshold,
                                 review_th=qc_config.review_threshold)
    status = {"match": RuleStatus.PASS, "review": RuleStatus.VERIFY,
              "mismatch": RuleStatus.FAIL}[mr.verdict]
    # confidence gate: low read on either side → VERIFY
    if min(sub.confidence(field), auth.confidence(field)) < _conf_floor(ctx, subject_doc, field):
        if status == RuleStatus.FAIL:
            status = RuleStatus.VERIFY
    msg = "" if status == RuleStatus.PASS else qc_config.template(
        template_id, value=av, a=sv, b=av, field=label or field)
    return _mk(rule_id, num, section, status, message=msg, fields=fields,
               evidence=ev, confidence=mr.score or 0.5,
               template_id=template_id if status != RuleStatus.PASS else None)


# ---------------------------------------------------------------------------
# Checkbox / boolean (Phase 4 building block, usable now)
# ---------------------------------------------------------------------------

def boolean_is(ctx, rule_id, num, section, field, expected: bool,
               template_id, doc="appraisal", label=None) -> RuleResult:
    view = ctx.doc(doc)
    val = view.value(field)
    ev = [view.evidence(field)]
    truthy = str(val).strip().lower() in {"true", "yes", "1", "x", "checked"}
    if val is None:
        return _mk(rule_id, num, section, RuleStatus.VERIFY,
                   message=qc_config.template(template_id, field=label or field),
                   fields=[field], evidence=ev, template_id=template_id, confidence=0.5)
    status = RuleStatus.PASS if truthy == expected else RuleStatus.FAIL
    status = _gate(ctx, doc, field, status, RuleStatus.FAIL)
    msg = "" if status == RuleStatus.PASS else qc_config.template(template_id, field=label or field, value=val)
    return _mk(rule_id, num, section, status, message=msg, fields=[field],
               evidence=ev, template_id=template_id if status != RuleStatus.PASS else None)
