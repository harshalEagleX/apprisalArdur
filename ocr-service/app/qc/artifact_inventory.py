"""
ArtifactInventory — pre-QC check of what documents are present vs expected.

Runs before any extraction or rule. Generates pre-run warnings for missing
documents so the reviewer knows immediately what's missing rather than
discovering it when individual rules fail.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import List, Optional

logger = logging.getLogger(__name__)


@dataclass
class ArtifactItem:
    name: str               # human-readable document name
    expected: bool          # was this document expected for this case type?
    present: bool           # was it provided?
    warning: Optional[str] = None   # human-readable warning if missing+expected


@dataclass
class ArtifactInventory:
    items: List[ArtifactItem] = field(default_factory=list)

    @property
    def all_present(self) -> bool:
        """True when every expected document is present."""
        return all(i.present for i in self.items if i.expected)

    @property
    def warnings(self) -> List[str]:
        """Warning messages for expected-but-missing documents."""
        return [i.warning for i in self.items
                if i.warning and not i.present and i.expected]

    @property
    def missing_required(self) -> List[str]:
        """Document names that are expected but not present."""
        return [i.name for i in self.items if i.expected and not i.present]

    @classmethod
    def build(
        cls,
        *,
        has_appraisal_pdf: bool,
        has_appraisal_xml: bool,
        has_engagement: bool,
        has_contract: bool,
        transaction_type: str,      # "purchase" | "refinance" | "other" | "unknown"
        engagement_status: Optional[str] = None,
    ) -> "ArtifactInventory":
        """Build an inventory by checking which documents are present vs expected
        for the given transaction type.

        Args:
            has_appraisal_pdf: True when an appraisal PDF was provided.
            has_appraisal_xml: True when a MISMO 2.6 XML was provided.
            has_engagement: True when an engagement/order letter was provided.
            has_contract: True when a purchase contract was provided.
            transaction_type: Loan transaction type string (purchase/refinance/other/unknown).
            engagement_status: Optional status string forwarded from the Java backend
                (e.g. "NOT_PROVIDED", "PENDING", "EXTRACTION_FAILED"). When the
                status is NOT_PROVIDED the engagement letter is intentionally absent
                and its missing-document warning is suppressed.

        Returns:
            A populated ArtifactInventory.
        """
        items = []

        # Appraisal PDF — always required; QC cannot run without it.
        items.append(ArtifactItem(
            name="Appraisal Report PDF",
            expected=True,
            present=has_appraisal_pdf,
            warning=(
                "Appraisal PDF is missing; QC cannot proceed without the report."
            ),
        ))

        # Appraisal XML — strongly recommended but not hard-required; QC degrades
        # gracefully without it (confidence on structured fields is lower).
        items.append(ArtifactItem(
            name="Appraisal XML (MISMO 2.6)",
            expected=False,    # advisory only — absence doesn't block QC
            present=has_appraisal_xml,
            warning=None,
        ))

        # Engagement letter — required unless the caller explicitly flagged it as
        # NOT_PROVIDED (the lender chose not to upload an order form).
        eng_required = engagement_status not in (
            "NOT_PROVIDED", "not_provided", "__NOT_PROVIDED__",
        )
        items.append(ArtifactItem(
            name="Engagement Letter / Order Form",
            expected=eng_required,
            present=has_engagement,
            warning=(
                "Engagement letter is missing; cross-document rules (address, borrower, "
                "lender) cannot be evaluated and QC accuracy will be reduced."
            ) if eng_required else None,
        ))

        # Purchase contract — required for purchase transactions only.
        contract_required = transaction_type == "purchase"
        items.append(ArtifactItem(
            name="Purchase Contract",
            expected=contract_required,
            present=has_contract,
            warning=(
                "Purchase contract is required for a purchase transaction but was not "
                "provided. Contract comparison rules cannot run. Please obtain and "
                "include the contract."
            ) if contract_required else None,
        ))

        return cls(items=items)
