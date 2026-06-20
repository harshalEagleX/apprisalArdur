"""
QCContext — the transaction-level view the rule engine evaluates against.

One QC case spans up to three documents (appraisal, engagement letter,
sales contract). The context indexes each document's extraction results by
canonical field name and exposes typed accessors plus derived transaction
attributes (loan type, transaction type, form type) that gate which rules fire.

Rules never touch ExtractionResultSet internals — they ask the context for a
field value + its evidence (value, confidence, page). This keeps the rule code
declarative and the extraction contract stable (P-12).
"""

from __future__ import annotations

import re
from typing import Dict, Optional

from app.core.result import ExtractionResult, ExtractionResultSet
from app.qc.result import Evidence

# Confidence below which a structured-field value is "uncertain" → rule downgraded
# to VERIFY rather than asserted PASS/FAIL. Overridden from qc_thresholds.yaml.
DEFAULT_STRUCTURED_CONF = 0.75
DEFAULT_CHECKBOX_CONF = 0.85

_CHECKBOX_METHODS = {"visual_checkbox", "drawing_checkbox", "uad_template"}


class DocView:
    """Indexed, by-field-name view of one document's extraction results."""

    def __init__(self, doc_label: str, result_set: Optional[ExtractionResultSet]):
        self.label = doc_label
        self._by_name: Dict[str, ExtractionResult] = {}
        self.present = result_set is not None
        if result_set is not None:
            for name, r in result_set:
                # keep the highest-confidence result per field name
                cur = self._by_name.get(name)
                if cur is None or r.effective_confidence > cur.effective_confidence:
                    self._by_name[name] = r

    def result(self, field_name: str) -> Optional[ExtractionResult]:
        r = self._by_name.get(field_name)
        return r if (r is not None and r.found) else None

    def value(self, field_name: str) -> Optional[str]:
        r = self.result(field_name)
        return r.value if r else None

    def confidence(self, field_name: str) -> float:
        r = self.result(field_name)
        return r.effective_confidence if r else 0.0

    def is_checkbox(self, field_name: str) -> bool:
        r = self.result(field_name)
        return bool(r and r.extraction_method in _CHECKBOX_METHODS)

    def evidence(self, field_name: str) -> Evidence:
        r = self.result(field_name)
        if not r:
            return Evidence(document=self.label, value=None, confidence=0.0, field=field_name)
        return Evidence(
            document=self.label,
            value=r.value,
            confidence=r.effective_confidence,
            page=r.source_page,
            bbox=r.bbox,            # normalized [0,1] field box for click-to-scroll (None if unlocated)
            method=r.extraction_method,
            field=field_name,
        )


class QCContext:
    def __init__(
        self,
        transaction_id: str,
        appraisal: Optional[ExtractionResultSet] = None,
        engagement: Optional[ExtractionResultSet] = None,
        contract: Optional[ExtractionResultSet] = None,
        structured_conf: float = DEFAULT_STRUCTURED_CONF,
        checkbox_conf: float = DEFAULT_CHECKBOX_CONF,
        engagement_status: Optional[str] = None,
    ):
        self.transaction_id = transaction_id
        self.appraisal = DocView("appraisal", appraisal)
        self.engagement = DocView("engagement", engagement)
        self.contract = DocView("contract", contract)
        self.structured_conf = structured_conf
        self.checkbox_conf = checkbox_conf
        # Per-document ingestion status forwarded by the Java/batch matcher.
        # Distinguishes a genuinely-absent engagement (NOT_PROVIDED) from one that
        # exists but failed/awaits extraction (PENDING / EXTRACTION_FAILED) so the
        # G-0 gate can NOT_APPLICABLE the former and HOLD the latter. None = the
        # caller did not forward a status → treat absence as blocking (safe default).
        self.engagement_status = (engagement_status or "").strip().upper() or None

    # -- document access --------------------------------------------------
    def doc(self, label: str) -> DocView:
        return {"appraisal": self.appraisal, "engagement": self.engagement,
                "contract": self.contract}[label]

    @property
    def has_contract(self) -> bool:
        return self.contract.present

    @property
    def has_engagement(self) -> bool:
        return self.engagement.present

    # -- derived transaction attributes (gate which rules fire) -----------
    @property
    def transaction_type(self) -> str:
        """purchase | refinance | other | unknown."""
        raw = (self.appraisal.value("assignment_type")
               or self.engagement.value("assignment_type")
               or self.engagement.value("intended_use") or "")
        t = raw.lower()
        if "purchase" in t:
            return "purchase"
        if "refinance" in t or "refi" in t:
            return "refinance"
        return "other" if t else "unknown"

    @property
    def loan_type(self) -> str:
        """conventional | fha | usda | va | unknown — engagement letter is authority."""
        raw = (self.engagement.value("loan_type")
               or self.engagement.value("form_type")
               or self.appraisal.value("loan_type") or "")
        t = raw.lower()
        for key in ("fha", "usda", "va", "conventional"):
            if key in t:
                return key
        return "unknown"

    @property
    def form_type(self) -> str:
        """1004 | 1073 | 1025 | unknown — from engagement form or appraisal."""
        raw = (self.engagement.value("form_type")
               or self.appraisal.value("form_type") or "")
        m = re.search(r"\b(1004mc|1004|1073|1025|1007|216)\b", raw.lower())
        return m.group(1) if m else "unknown"

    @property
    def is_update_report(self) -> bool:
        """True for a 1004D Appraisal Update / Completion report (no sales grid),
        set by the form-type overlay from the report's first-page markers."""
        return str(self.appraisal.value("is_update_report") or "").lower() in ("true", "1", "yes")

    @property
    def has_sca_grid(self) -> bool:
        """Whether this report form has a sales-comparison grid. Defaults True;
        only an explicit no-grid form (update/completion) turns it off — so a
        normal 1004 with a comp-extraction failure still runs SCA and flags it."""
        return not self.is_update_report
