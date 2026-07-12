"""
llm.verify_pass (lvf-1.1.0) — SHALqc.md §5 Tier-3 / SHALqc-CORE §4.4.

Second opinion behind PASS verdicts only (FAIL/VERIFY already go to humans). The
LLM re-reads the extracted values + page snippet vs the PASS decision; if it
does not clearly support PASS with a grounded quote, the engine ADDS one VERIFY
finding (CAT-<rule_id>). It can NEVER flip or remove the PASS — add-only, which
is why it is first on the cut list (SHALqc.md §11) if time runs out.
"""

from __future__ import annotations

import json
import logging
from typing import List, Optional

from app.llm.grounding import is_grounded
from app.rules.verdict import Status, Verdict

__version__ = "lvf-1.1.0"

logger = logging.getLogger(__name__)

_SYSTEM = (
    "You are auditing a PASS decision from an appraisal QC engine. If the evidence "
    "does NOT clearly support PASS, flag it. You cannot change the verdict — only flag. "
    'Reply JSON only: {"agree": true|false, "concern": "<one short sentence>", '
    '"quote": "<verbatim substring of the evidence or null>"}.'
)


def verify_pass(client, verdict: Verdict, snippet: str = "") -> Optional[Verdict]:
    """Audit one PASS verdict. Returns a NEW VERIFY finding to ADD when the LLM
    disagrees with a grounded concern, else None. Never mutates `verdict`."""
    if client is None or not getattr(client, "available", False):
        return None
    if verdict.status != Status.PASS:
        return None
    evidence_text = " | ".join(f"{e.field}={e.value}" for e in verdict.evidence)
    user = json.dumps({"rule_id": verdict.rule_id, "evidence": evidence_text, "snippet": snippet[:2000]})
    data = client.classify(_SYSTEM, user)
    if not isinstance(data, dict) or data.get("agree") is not False:
        return None
    quote = data.get("quote") or ""
    if quote and not is_grounded(quote, evidence_text, snippet):
        return None  # ungrounded concern → drop (CORE §4.5)
    return Verdict(
        rule_id=f"CAT-{verdict.rule_id}", status=Status.VERIFY, section=verdict.section,
        tier=3, confidence=0.5,
        message=(data.get("concern") or "Automated second-opinion flagged this PASS for review."),
        evidence=list(verdict.evidence), fields_involved=list(verdict.fields_involved),
        degraded_reason="verify_pass_flag",
    )
