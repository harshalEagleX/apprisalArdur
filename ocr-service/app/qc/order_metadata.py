"""
OrderMetadata — the authoritative order-level facts for one QC case.

In this system the engagement letter IS the order. There is no external LOS or
AMS feeding data. Every field here is extracted from the engagement letter
(primary) or cross-referenced against the appraisal XML (fallback / conflict
detection). No field is guessed or inferred from a source that does not actually
state it — absent = None, not a fabricated value.

Priority:
  1. Engagement letter (confidence ~0.92, label-anchored clean digital text)
  2. Appraisal XML (confidence 0.97, MISMO structured — used as fallback when EL
     is silent, and as a cross-check when EL has a value)
  3. Contract (buyer names only)

When both engagement letter and XML have a value for the same field and they
disagree beyond a trivial formatting difference, an OrderConflict is recorded.
Cross-document rules read ctx.order.conflicts to surface these findings.
"""

from __future__ import annotations

import hashlib
import re
import datetime
import logging
from dataclasses import dataclass, field
from typing import List, Optional

logger = logging.getLogger(__name__)


@dataclass
class OrderConflict:
    """A disagreement between the engagement letter and the XML for the same fact."""
    field_name: str
    engagement_value: Optional[str]
    xml_value: Optional[str]
    note: str = ""


@dataclass
class OrderMetadata:
    """
    Complete order-level facts derived from the engagement letter + XML.
    Rules read from this object — never from scattered DocView lookups — so
    every fact has one authoritative location (P-12).
    """
    # ── Identity ────────────────────────────────────────────────────────────
    borrower_name: Optional[str] = None
    co_borrower_name: Optional[str] = None
    property_address: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    zip_code: Optional[str] = None
    county: Optional[str] = None
    lender_name: Optional[str] = None
    lender_address: Optional[str] = None
    amc_name: Optional[str] = None
    amc_id: Optional[str] = None

    # ── Assignment ──────────────────────────────────────────────────────────
    assignment_type: Optional[str] = None       # "purchase" | "refinance" | ...
    loan_type: Optional[str] = None             # "conventional" | "fha" | "usda" | "va"
    fha_case_number: Optional[str] = None
    required_form_type: Optional[str] = None    # "1004" | "1073" | "1025" | ...
    ordered_inspection_type: Optional[str] = None  # "full_interior" | "exterior_only" | "desktop"

    # ── Reference ──────────────────────────────────────────────────────────
    file_reference: Optional[str] = None        # AMC file / order number
    loan_number: Optional[str] = None

    # ── Dates ───────────────────────────────────────────────────────────────
    engagement_date: Optional[datetime.date] = None

    # ── Source tracking ─────────────────────────────────────────────────────
    # True when the engagement letter was actually present and extracted
    from_engagement: bool = False
    # True when XML was present and used as fallback for any field
    xml_fallback_used: bool = False
    # Engagement letter content hash — for detecting policy changes between reviews
    engagement_hash: Optional[str] = None

    # ── Cross-document conflicts ─────────────────────────────────────────────
    conflicts: List[OrderConflict] = field(default_factory=list)

    # ── Helpers ─────────────────────────────────────────────────────────────
    @property
    def is_purchase(self) -> bool:
        return (self.assignment_type or "").lower() == "purchase"

    @property
    def is_fha(self) -> bool:
        return (self.loan_type or "").lower() == "fha"

    @property
    def is_usda(self) -> bool:
        return (self.loan_type or "").lower() == "usda"

    @property
    def is_va(self) -> bool:
        return (self.loan_type or "").lower() == "va"

    @property
    def has_conflicts(self) -> bool:
        return bool(self.conflicts)

    @classmethod
    def from_extraction(
        cls,
        engagement_fields: dict,          # raw dict from extract_engagement_fields()
        xml_result_set,                   # ExtractionResultSet or None
        contract_fields: Optional[dict] = None,
        engagement_raw_text: str = "",
    ) -> "OrderMetadata":
        """
        Build OrderMetadata by merging engagement letter (primary) + XML (fallback).

        engagement_fields: {canonical: value} from engagement_extractor.
        xml_result_set: ExtractionResultSet from xml_extractor (or None).
        contract_fields: optional raw dict from contract_extractor (buyer names).
        engagement_raw_text: full text of engagement letter for hash + overlay.
        """
        order = cls()
        order.from_engagement = bool(engagement_fields)

        # Hash the engagement letter text so we can detect policy changes
        if engagement_raw_text:
            order.engagement_hash = hashlib.sha256(
                engagement_raw_text.encode("utf-8", errors="replace")
            ).hexdigest()[:16]

        def _eng(key: str) -> Optional[str]:
            v = engagement_fields.get(key)
            return v.strip() if v and str(v).strip() else None

        def _xml(key: str) -> Optional[str]:
            if xml_result_set is None:
                return None
            # ExtractionResultSet supports iteration; DocView not needed here
            try:
                r = xml_result_set.get(key)
                return r.value if r and r.found else None
            except Exception:
                return None

        def _resolve(field_name: str, eng_key: str, xml_key: Optional[str] = None,
                     normalizer=None) -> Optional[str]:
            """Take engagement primary; XML fallback; record conflict if both present."""
            ev = _eng(eng_key)
            xv = _xml(xml_key or eng_key)
            if normalizer:
                ev = normalizer(ev) if ev else ev
                xv = normalizer(xv) if xv else xv

            if ev and xv:
                # Both present — check for conflict
                if not _values_agree(ev, xv):
                    order.conflicts.append(OrderConflict(
                        field_name=field_name,
                        engagement_value=ev,
                        xml_value=xv,
                        note=f"Engagement says '{ev}'; XML says '{xv}'",
                    ))
                return ev  # engagement is authoritative

            if ev:
                return ev
            if xv:
                order.xml_fallback_used = True
                return xv
            return None

        # ── Identity ────────────────────────────────────────────────────────
        order.borrower_name       = _resolve("borrower_name", "borrower_name")
        order.co_borrower_name    = _resolve("co_borrower_name", "co_borrower_name")
        order.property_address    = _resolve("property_address", "property_address")
        order.city                = _resolve("city", "city")
        order.state               = _resolve("state", "state", normalizer=lambda v: v.upper()[:2] if v else v)
        order.zip_code            = _resolve("zip_code", "zip_code", normalizer=lambda v: v[:5] if v else v)
        order.county              = _resolve("county", "county")
        order.lender_name         = _resolve("lender_name", "lender_name")
        order.lender_address      = _resolve("lender_address", "lender_address")

        # AMC identity comes from engagement letter classifier (amc_id in eng fields)
        order.amc_name = _eng("amc_name") or _eng("amc_reg_number")
        order.amc_id   = _eng("amc_id")

        # ── Assignment ──────────────────────────────────────────────────────
        order.assignment_type  = _resolve("assignment_type", "assignment_type",
                                          normalizer=_normalize_assignment)
        order.loan_type        = _resolve("loan_type", "loan_type",
                                          normalizer=_normalize_loan_type)
        order.fha_case_number  = _resolve("fha_case_number", "fha_case_number")

        # Required form type from engagement letter
        order.required_form_type = _normalize_form_type(_eng("form_type"))
        order.ordered_inspection_type = _infer_inspection_type(
            _eng("form_type") or "", _eng("assignment_type") or ""
        )

        # ── Reference ──────────────────────────────────────────────────────
        order.file_reference = _eng("file_id") or _eng("amc_order_number")
        order.loan_number    = _eng("loan_number")

        # ── Dates ───────────────────────────────────────────────────────────
        order.engagement_date = _parse_eng_date(engagement_raw_text)

        # ── Contract cross-ref (buyer names) ────────────────────────────────
        if contract_fields and order.borrower_name is None:
            bn = contract_fields.get("buyer_names") or contract_fields.get("borrower_name")
            if bn:
                order.borrower_name = str(bn).strip()

        if order.conflicts:
            logger.info(
                "OrderMetadata: %d cross-document conflict(s) detected: %s",
                len(order.conflicts),
                ", ".join(c.field_name for c in order.conflicts),
            )

        return order

    @classmethod
    def empty(cls) -> "OrderMetadata":
        """Minimal safe object — all None, no conflicts. Used when no EL is present."""
        return cls()


# ── Private helpers ──────────────────────────────────────────────────────────

def _values_agree(a: str, b: str) -> bool:
    """Fuzzy compare — strips punctuation, lowercase, first 5 zip chars."""
    def _norm(v: str) -> str:
        v = v.lower().strip()
        v = re.sub(r"[,\.\-\s]+", " ", v).strip()
        return v
    na, nb = _norm(a), _norm(b)
    # substring match covers "Garden Grove" vs "Garden Grove CA 92845"
    return na == nb or na in nb or nb in na


def _normalize_assignment(v: Optional[str]) -> Optional[str]:
    if not v:
        return None
    # Strip hyphens and spaces so "Re-Finance" and "re finance" both match "refinance"
    t = re.sub(r"[-\s]+", "", v.lower())
    if "purchase" in t:
        return "purchase"
    if "refinance" in t or "refi" in t:
        return "refinance"
    if "cash" in t and "out" in t:
        return "cash_out_refinance"
    return v.strip()


def _normalize_loan_type(v: Optional[str]) -> Optional[str]:
    if not v:
        return None
    t = v.lower()
    for key in ("fha", "usda", "va", "conventional", "jumbo", "portfolio"):
        if key in t:
            return key
    return v.strip().lower()


_FORM_RE = re.compile(r"\b(1004mc|1004d|1004|1073|1025|1007|216|2055)\b", re.I)


def _normalize_form_type(v: Optional[str]) -> Optional[str]:
    if not v:
        return None
    m = _FORM_RE.search(v)
    return m.group(1).lower() if m else None


def _infer_inspection_type(form_text: str, assignment_text: str) -> Optional[str]:
    """Infer ordered inspection type from form or assignment text."""
    combined = (form_text + " " + assignment_text).lower()
    if re.search(r"\bdesktop\b", combined):
        return "desktop"
    if re.search(r"\bexterior[\s\-]?only\b|\bdrive[\s\-]?by\b|\b1075\b", combined):
        return "exterior_only"
    if re.search(r"\binterior\b|\bfull\b.*\binspect|\b1004\b", combined):
        return "full_interior"
    return None


_DATE_FMTS = ["%m/%d/%Y", "%Y-%m-%d", "%m-%d-%Y", "%B %d, %Y", "%b %d, %Y",
              "%m/%d/%y", "%d %B %Y"]

_DATE_RE = re.compile(
    r"\b(?:(?:January|February|March|April|May|June|July|August|September|"
    r"October|November|December)\s+\d{1,2},?\s+\d{4}|\d{1,2}/\d{1,2}/\d{2,4}"
    r"|\d{4}-\d{2}-\d{2})\b",
    re.I,
)

# Labels searched in priority order. "Assigned On:" is the Equity Solutions USA /
# ValueLink platform label for the order-placed timestamp. Fallbacks cover other
# common AMC portal labels. We NEVER fall back to "grab first date in header"
# because that reliably hits "Order Due Date" before the actual assignment date.
_ENG_DATE_LABELS = [
    "Assigned On:",
    "Order Date:",
    "Date Ordered:",
    "Received:",
    "Assignment Date:",
    "Order Placed:",
]


def _parse_eng_date(text: str) -> Optional[datetime.date]:
    """Extract the engagement date by searching for a recognized AMC platform label.

    Searches _ENG_DATE_LABELS in priority order and returns the date found
    immediately after the first matching label. Returns None if no label is found
    rather than falling back to the first date in the header, which would
    incorrectly capture Order Due Date or other deadline fields.
    """
    if not text:
        return None
    for label in _ENG_DATE_LABELS:
        idx = text.find(label)
        if idx == -1:
            continue
        snippet = text[idx + len(label): idx + len(label) + 80]
        for m in _DATE_RE.finditer(snippet):
            raw = m.group(0)
            for fmt in _DATE_FMTS:
                try:
                    result = datetime.datetime.strptime(raw.strip(), fmt).date()
                    logger.debug("ORD-ENG-DATE: matched label=%r date=%s", label, result)
                    return result
                except ValueError:
                    continue
    logger.debug("ORD-ENG-DATE: no labeled date found in engagement letter text")
    return None
