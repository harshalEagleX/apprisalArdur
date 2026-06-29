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
from typing import TYPE_CHECKING, Dict, Optional

from app.core.result import ExtractionResult, ExtractionResultSet
from app.qc.result import Evidence

if TYPE_CHECKING:
    from app.qc.policy_profile import PolicyProfile
    from app.qc.artifact_inventory import ArtifactInventory
    from app.qc.order_metadata import OrderMetadata

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
        policy: Optional["PolicyProfile"] = None,
        artifact_inventory: Optional["ArtifactInventory"] = None,
        contract_package: Optional[object] = None,
        order_metadata: Optional["OrderMetadata"] = None,
        contract_provided: bool = False,
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
        # Per-case policy: AMC threshold overrides and rule activation flags.
        # Falls back to global defaults when None (safe for callers that haven't
        # been updated to pass a policy yet — P-6).
        if policy is None:
            from app.qc.policy_profile import PolicyProfile as _PP
            policy = _PP.default()
        self.policy: "PolicyProfile" = policy
        # Pre-QC artifact inventory: which documents are present vs expected.
        # Populated before the rule engine runs so rules can inspect it without
        # touching the file system (P-3).
        self.artifact_inventory: Optional["ArtifactInventory"] = artifact_inventory
        # Whether a purchase contract document was supplied for the transaction.
        # This is distinct from whether contract extraction results exist, because
        # the QC pipeline intentionally avoids OCR-ing contract documents.
        self.contract_provided = contract_provided
        # Raw contract package object forwarded from the extraction pipeline
        # (may carry execution-status metadata such as resolved_execution_status).
        # None when no contract was provided.
        self.contract_package: Optional[object] = contract_package
        # OrderMetadata: extracted from the engagement letter (primary) + XML cross-ref.
        # The engagement letter IS the order in this system — no external LOS/AMS.
        # None when engagement letter was absent; rules that need order facts must
        # gate on ctx.order is not None (or ctx.has_engagement).
        if order_metadata is None:
            from app.qc.order_metadata import OrderMetadata as _OM
            order_metadata = _OM.empty()
        self.order: "OrderMetadata" = order_metadata

    # -- document access --------------------------------------------------
    def doc(self, label: str) -> DocView:
        return {"appraisal": self.appraisal, "engagement": self.engagement,
                "contract": self.contract}[label]

    @property
    def has_contract(self) -> bool:
        return self.contract.present or self.contract_provided

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

    @property
    def has_unexecuted_contract(self) -> bool:
        """True when a contract package is present but its execution status indicates
        the contract has NOT been fully signed by all parties.

        Rules that implement the stop-on-unsigned-contract policy (e.g. C-EXEC) read
        this property so the check is expressed once and stays consistent (P-3).

        Returns False (safe/pass-through) when:
          - No contract package is attached (contract_package is None)
          - The package has no resolved_execution_status attribute
          - The status is truthy (contract IS executed)
        """
        if self.contract_package is None:
            return False
        status = getattr(self.contract_package, "resolved_execution_status", None)
        # A falsy status (None, False, empty string, 0) means not executed.
        # A truthy status ("executed", True, "YES", etc.) means it is executed.
        return not bool(status)
