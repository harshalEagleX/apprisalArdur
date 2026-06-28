"""
ContractPackage — resolved transaction state from one or more contract documents.

When a purchase has both a base contract and one or more amendments, the controlling
state (price, concessions, execution status) comes from the latest effective document.
This model resolves that state so all contract rules compare against a single truth.
"""
from __future__ import annotations

import re
import datetime
from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class ContractDocument:
    """One contract document — either the base agreement or an amendment."""
    path: str                           # file path on disk
    doc_type: str                       # "base" | "amendment"
    sequence: int                       # 0=base, 1,2...=amendments in date order
    document_date: Optional[datetime.date]  # extracted date of this document
    purchase_price: Optional[float]     # extracted dollar amount
    concessions_amount: Optional[float]
    concessions_description: Optional[str]
    buyer_names: List[str]
    is_executed: bool                   # all required parties signed
    raw_extracted: dict                 # all raw extracted fields


@dataclass
class ContractPackage:
    """
    The complete contract package for a purchase transaction.
    Resolved = values from the latest controlling document.
    """
    documents: List[ContractDocument] = field(default_factory=list)

    @property
    def has_base(self) -> bool:
        return any(d.doc_type == "base" for d in self.documents)

    @property
    def resolved_document(self) -> Optional[ContractDocument]:
        """Latest document (highest sequence) is controlling."""
        if not self.documents:
            return None
        return max(self.documents, key=lambda d: d.sequence)

    @property
    def resolved_price(self) -> Optional[float]:
        for doc in sorted(self.documents, key=lambda d: -d.sequence):
            if doc.purchase_price:
                return doc.purchase_price
        return None

    @property
    def resolved_concessions(self) -> Optional[float]:
        """Sum concessions across all docs (amendments ADD to base)."""
        total = 0.0
        found = False
        for doc in self.documents:
            if doc.concessions_amount is not None:
                total += doc.concessions_amount
                found = True
        return total if found else None

    @property
    def resolved_execution_status(self) -> bool:
        """Package is executed only when ALL documents are executed."""
        if not self.documents:
            return False
        return all(d.is_executed for d in self.documents)

    @property
    def resolved_buyer_names(self) -> List[str]:
        """Names from the base contract."""
        base = next((d for d in self.documents if d.doc_type == "base"), None)
        return base.buyer_names if base else []

    @property
    def base_date(self) -> Optional[datetime.date]:
        base = next((d for d in self.documents if d.doc_type == "base"), None)
        return base.document_date if base else None

    @classmethod
    def from_single_path(cls, contract_extractor_result: dict) -> "ContractPackage":
        """
        Build a ContractPackage from the result of extract_contract_fields().
        Used when only one contract file is in the case (no amendment handling needed).
        """
        price = _parse_currency(contract_extractor_result.get("contract_price"))
        conc = _parse_currency(contract_extractor_result.get("concessions_amount"))
        date_str = contract_extractor_result.get("contract_date") or ""
        doc_date = _parse_date(date_str)
        buyers = _extract_buyer_names(contract_extractor_result)
        executed = _infer_executed(contract_extractor_result)
        doc_type = _classify_doc_type(contract_extractor_result.get("_raw_text", ""))

        doc = ContractDocument(
            path=contract_extractor_result.get("_path", ""),
            doc_type=doc_type,
            sequence=0,
            document_date=doc_date,
            purchase_price=price,
            concessions_amount=conc,
            concessions_description=contract_extractor_result.get("concessions_description"),
            buyer_names=buyers,
            is_executed=executed,
            raw_extracted=contract_extractor_result,
        )
        return cls(documents=[doc])


# ---------------------------------------------------------------------------
# Internal parsing helpers
# ---------------------------------------------------------------------------

def _parse_currency(val) -> Optional[float]:
    if val is None:
        return None
    clean = re.sub(r"[$,\s]", "", str(val))
    try:
        return float(clean)
    except (ValueError, TypeError):
        return None


def _parse_date(s: str) -> Optional[datetime.date]:
    if not s:
        return None
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%m-%d-%Y", "%m/%d/%y"):
        try:
            return datetime.datetime.strptime(s.strip(), fmt).date()
        except (ValueError, AttributeError):
            continue
    return None


_AMENDMENT_PHRASES = re.compile(
    r"(amendment|addendum\s+to\s+(purchase|contract)|change\s+in\s+terms|"
    r"revised\s+(purchase|contract)|modification\s+of\s+(purchase|agreement)|"
    r"counter\s*offer|counter-?offer|backup\s+offer)",
    re.I,
)


def _classify_doc_type(text: str) -> str:
    return "amendment" if _AMENDMENT_PHRASES.search(text) else "base"


_BUYER_BLOCK = re.compile(
    r"(?:buyer|purchaser|applicant)[\s:]+([A-Z][a-zA-Z\s,&.'-]{3,60})", re.I
)


def _extract_buyer_names(result: dict) -> List[str]:
    raw = result.get("buyer_names") or result.get("borrower_name") or ""
    if raw:
        return [n.strip() for n in re.split(r"\s*[,&]\s*", str(raw)) if n.strip()]
    text = result.get("_raw_text", "")
    names: List[str] = []
    for m in _BUYER_BLOCK.finditer(text[:3000]):
        name = m.group(1).strip().rstrip(",.")
        if 3 < len(name) < 60 and name not in names:
            names.append(name)
    return names[:4]


_SIGNATURE_BLOCK = re.compile(
    r"(x___|_{4,}|signed[\s:]*([A-Z][a-z]+\s+[A-Z][a-z]+)|"
    r"buyer\s+signature|seller\s+signature|by:\s*/s/)",
    re.I,
)
_UNSIGNED_BLOCK = re.compile(
    r"(not\s+(signed|executed)|unsigned|awaiting\s+signature|"
    r"will\s+be\s+executed|executed\s+at\s+closing)",
    re.I,
)


def _infer_executed(result: dict) -> bool:
    text = result.get("_raw_text", "")[-3000:]  # check last pages
    if _UNSIGNED_BLOCK.search(text):
        return False
    # Simple heuristic: if signature blocks appear with filled content → executed
    sig_matches = _SIGNATURE_BLOCK.findall(text)
    return len(sig_matches) >= 2  # buyer + seller signature blocks found
