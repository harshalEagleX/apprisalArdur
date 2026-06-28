"""
EngagementOverlay — client-specific policy instructions extracted from the
engagement letter body.

This is the output of Job 2 engagement extraction (the policy pass). Job 1
extracts *who* and *what* (order facts → OrderMetadata). Job 2 extracts *how*
(processing instructions → EngagementOverlay). The overlay is then merged into
PolicyProfile so every rule reads its thresholds from a single source.

Extraction strategy:
  - Deterministic regex first: clear phrases like "comps within 6 months",
    "stop if contract is not signed", "cost approach required".
  - LLM structured extraction for the rest: Groq is asked specific yes/no +
    value questions, not a free-form summary. The LLM is appropriate here
    because engagement letter bodies are prose, not labeled fields.
  - Every field defaults to None (unknown) — the merge step in PolicyProfile
    treats None as "use the AMC default", not as "override with no-op".
"""

from __future__ import annotations

import re
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

logger = logging.getLogger(__name__)

# ── Deterministic regex patterns ─────────────────────────────────────────────

_COMP_AGE_RE = re.compile(
    r"(?:comparable|comp)\s+(?:sale[s]?\s+)?(?:within|no\s+(?:more\s+)?than|"
    r"not\s+(?:to\s+)?exceed)\s+(\d+)\s+months?",
    re.I,
)

_STOP_UNSIGNED_RE = re.compile(
    r"(?:stop|hold|do\s+not\s+(?:process|accept|continue)|return)\s+.{0,60}"
    r"(?:unsigned|not\s+(?:fully\s+)?executed|without\s+(?:all\s+)?signature)",
    re.I,
)

_STOP_UNSIGNED_RE2 = re.compile(
    r"(?:fully\s+executed\s+contract|signed\s+contract)\s+(?:is\s+)?required",
    re.I,
)

_LISTING_REQUIRED_RE = re.compile(
    r"(?:must|shall|require[sd]?|include|provide)\s+.{0,40}"
    r"(?:(?:current\s+)?listing|pending\s+sale|active\s+(?:listing|sale))",
    re.I,
)

_LISTING_DECLINING_RE = re.compile(
    r"(?:declining|over.suppl|down\s+market|soft\s+market)\s+.{0,80}"
    r"(?:listing|pending\s+sale)",
    re.I,
)

_COST_REQUIRED_RE = re.compile(
    r"cost\s+approach\s+(?:is\s+)?(?:required|must\s+be\s+(?:completed|developed|included))",
    re.I,
)

_STOP_CONDITION_RE = re.compile(
    r"(?:stop\s+and\s+(?:notify|contact|return)|hold\s+(?:and\s+)?(?:notify|contact)|"
    r"do\s+not\s+(?:process|accept|complete|submit))\s+if\s+(.{10,120}?)(?:\.|;|\n|$)",
    re.I,
)

_ADDENDUM_RE = re.compile(
    r"(?:must|shall|required?)\s+.{0,30}"
    r"(?:include|attach|provide|complete)\s+(?:the\s+)?"
    r"([\w\s\-/]{4,50}addend(?:um|a))",
    re.I,
)

_FHA_CASE_REQUIRED_RE = re.compile(
    r"fha\s+case\s+(?:number\s+)?(?:must\s+be\s+)?(?:included|required|provided|on\s+(?:all\s+)?pages)",
    re.I,
)

_SMCO_REQUIRED_RE = re.compile(
    r"(?:smoke|carbon\s+monoxide|co|smco)\s+detector[s]?\s+.{0,40}"
    r"(?:required|must|shall|comment|confirm|verify)",
    re.I,
)


@dataclass
class EngagementOverlay:
    """
    Per-CASE policy departures extracted from an engagement letter body.

    IMPORTANT SCOPING NOTE:
    The Equity Solutions USA engagement letter body is IDENTICAL for every order.
    Those AMC-level policies (6-month comp trigger, 1-mile suburban trigger,
    10/15/25 adjustment trigger, stop conditions) are baked into config/amc_policies.yaml
    and loaded by PolicyProfile.from_amc_id() — NOT extracted per-case here.

    This overlay only captures genuine case-specific departures from the AMC base
    policy — for example, if a specific letter overrides the standard comp age
    requirement for a particular assignment. For Equity Solutions USA, this will
    almost always be empty because the body text is static.

    For future AMCs whose letters DO contain per-case overrides (e.g. "for this
    specific file, use comps within 90 days only"), this overlay captures them.

    All fields default to None — None means "use the AMC base policy value".
    """
    # Per-case threshold overrides (None = use AMC base policy, not "no limit")
    comp_age_limit_months: Optional[int] = None          # only set if case departs from AMC base
    comp_distance_limit_miles: Optional[float] = None

    # Rule activation flags
    stop_on_unsigned_contract: Optional[bool] = None
    require_listing_comp_unconditional: Optional[bool] = None   # required regardless of market
    require_listing_comp_declining: Optional[bool] = None       # required in declining market only
    require_cost_approach: Optional[bool] = None
    require_smco_comment: Optional[bool] = None
    require_fha_case_all_pages: Optional[bool] = None

    # Named requirements
    required_addenda: List[str] = field(default_factory=list)
    stop_conditions: List[str] = field(default_factory=list)

    # Raw text hash used to detect if the letter changed between reviews
    letter_text_snippet: str = ""   # first 300 chars (not a secret — for logging)

    @classmethod
    def from_text(cls, text: str) -> "EngagementOverlay":
        """Extract overlay from the full engagement letter text (deterministic pass)."""
        ov = cls()
        ov.letter_text_snippet = text[:300].replace("\n", " ").strip()

        # Comparable age limit
        m = _COMP_AGE_RE.search(text)
        if m:
            try:
                ov.comp_age_limit_months = int(m.group(1))
            except ValueError:
                pass

        # Stop on unsigned contract
        if _STOP_UNSIGNED_RE.search(text) or _STOP_UNSIGNED_RE2.search(text):
            ov.stop_on_unsigned_contract = True

        # Listing comp requirements
        if _LISTING_REQUIRED_RE.search(text):
            if _LISTING_DECLINING_RE.search(text):
                ov.require_listing_comp_declining = True
            else:
                ov.require_listing_comp_unconditional = True

        # Cost approach
        if _COST_REQUIRED_RE.search(text):
            ov.require_cost_approach = True

        # SMCO detectors
        if _SMCO_REQUIRED_RE.search(text):
            ov.require_smco_comment = True

        # FHA case number on all pages
        if _FHA_CASE_REQUIRED_RE.search(text):
            ov.require_fha_case_all_pages = True

        # Stop conditions (named)
        for m in _STOP_CONDITION_RE.finditer(text):
            phrase = m.group(1).strip().rstrip(".,;")
            if phrase not in ov.stop_conditions:
                ov.stop_conditions.append(phrase)

        # Required addenda
        for m in _ADDENDUM_RE.finditer(text):
            name = m.group(1).strip()
            if name not in ov.required_addenda:
                ov.required_addenda.append(name)

        logger.info(
            "EngagementOverlay extracted: age_limit=%s, stop_unsigned=%s, "
            "listing_req=%s, cost_req=%s, stop_conditions=%d",
            ov.comp_age_limit_months, ov.stop_on_unsigned_contract,
            ov.require_listing_comp_unconditional or ov.require_listing_comp_declining,
            ov.require_cost_approach, len(ov.stop_conditions),
        )
        return ov

    @classmethod
    def from_pdf(cls, pdf_path) -> "EngagementOverlay":
        """Extract overlay from a PDF engagement letter (all pages)."""
        try:
            import fitz
            doc = fitz.open(str(pdf_path))
            text = "\n".join(doc[i].get_text("text") for i in range(len(doc)))
            doc.close()
        except Exception as exc:
            logger.warning("EngagementOverlay: cannot open %s: %s", pdf_path, exc)
            return cls()
        return cls.from_text(text)

    @classmethod
    def empty(cls) -> "EngagementOverlay":
        return cls()

    def has_any_override(self) -> bool:
        return any([
            self.comp_age_limit_months is not None,
            self.comp_distance_limit_miles is not None,
            self.stop_on_unsigned_contract is not None,
            self.require_listing_comp_unconditional is not None,
            self.require_listing_comp_declining is not None,
            self.require_cost_approach is not None,
            self.require_smco_comment is not None,
            self.require_fha_case_all_pages is not None,
            bool(self.required_addenda),
            bool(self.stop_conditions),
        ])
