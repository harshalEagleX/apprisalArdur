"""
rules.checklist_source (cks-1.0.0) — where a checklist comes from.

The checklist is DATA, not code, and it is on its way to becoming data the user
edits. Today it lives in YAML generated from an AMC's spreadsheet; the target is
a frontend form writing rows to the database, with no YAML at all. Everything
between those two states has to keep working, which means no module may open a
checklist file itself. They ask this loader, and the backend changes underneath
them.

Two rules make the system stable across edits — and edits WILL happen, because
the whole point is that an AMC can add or remove a question without a release:

  1. **Nothing keys on item count, numbering, or a specific id.** An AMC that
     deletes question 47 or inserts 47a must not break a rule that assumed 90
     items or hardcoded `#74`. Items are addressed by their declared capability
     (`proof`, `polarity`, `requires_documents`, bound `fields`), never by
     position. Earlier versions of the arithmetic checks keyed on checklist
     numbers and would have silently misfired on any renumbering.
  2. **An unclassified item degrades, it does not fail.** A question added from
     the frontend arrives with no classification until the classifier runs, so
     it defaults to `polarity: unknown`, which can produce VERIFY but never FAIL.
     A brand-new question can therefore never reject an appraisal before anyone
     has reviewed what it means.

`ChecklistItem.raw` keeps the untouched source row, so a field this code does not
know about yet — added by a future frontend — survives a round trip instead of
being dropped on load.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

__version__ = "cks-1.0.0"

logger = logging.getLogger(__name__)

_CONFIG_DIR = Path(__file__).resolve().parent.parent.parent / "config"

# Fail-safe defaults for anything the source did not state. Chosen so a missing
# value costs a reviewer a look and never causes a rejection.
_DEFAULT_POLARITY = "unknown"
_DEFAULT_EVIDENCE = "text"
_DEFAULT_PROOF = "none"


@dataclass
class ChecklistItem:
    """One question, however it was authored."""

    item_id: str
    number: Optional[int]
    section: str
    question: str
    polarity: str = _DEFAULT_POLARITY
    evidence_kind: str = _DEFAULT_EVIDENCE
    proof: str = _DEFAULT_PROOF
    requires_documents: List[str] = field(default_factory=list)
    fields: List[str] = field(default_factory=list)
    reject_text: Optional[str] = None
    classified: bool = False
    raw: Dict[str, Any] = field(default_factory=dict)

    @property
    def rejectable(self) -> bool:
        """Only an item the AMC wrote rejection wording for may recommend one."""
        return bool(self.reject_text)

    @property
    def answerable_from_report(self) -> bool:
        return not self.requires_documents

    def as_dict(self) -> Dict[str, Any]:
        return {**self.raw, "item_id": self.item_id, "checklist_number": self.number,
                "section": self.section, "requirement": self.question,
                "polarity": self.polarity, "evidence_kind": self.evidence_kind,
                "proof": self.proof, "requires_documents": self.requires_documents,
                "sources": [{"doc": "appraisal", "fields": self.fields}],
                "classified": self.classified}


def _coerce(row: Dict[str, Any]) -> ChecklistItem:
    """One source row -> ChecklistItem, tolerating absent keys.

    Deliberately forgiving: a row written by a future frontend will not have the
    same shape as one generated from a spreadsheet, and refusing to load it would
    take the whole checklist down rather than the one item.
    """
    sources = row.get("sources") or [{}]
    fields = (sources[0] or {}).get("fields") or []
    reject = row.get("reject_text")
    if not reject:
        rejects = row.get("reject_as") or []
        reject = rejects[0] if rejects else None
    return ChecklistItem(
        item_id=str(row.get("rule_id") or row.get("item_id") or row.get("id") or "?"),
        number=row.get("checklist_number") if isinstance(
            row.get("checklist_number"), int) else None,
        section=str(row.get("section") or "other"),
        question=str(row.get("requirement") or row.get("check_text") or
                     row.get("item") or "").strip(),
        polarity=str(row.get("polarity") or _DEFAULT_POLARITY).strip().lower(),
        evidence_kind=str(row.get("evidence_kind") or _DEFAULT_EVIDENCE).strip().lower(),
        proof=str(row.get("proof") or _DEFAULT_PROOF).strip().lower(),
        requires_documents=[str(d) for d in (row.get("requires_documents") or []) if d],
        fields=[str(f) for f in fields if f],
        reject_text=reject,
        classified=bool(row.get("classified")),
        raw=dict(row),
    )


class ChecklistSource:
    """Interface. Implementations: YAML today, database next."""

    def load(self, amc_code: Optional[str], uad_version: Optional[str]
             ) -> List[ChecklistItem]:
        raise NotImplementedError


class YamlChecklistSource(ChecklistSource):
    """Reads the generated catalogs under config/.

    Selected by form version, because 3.6 and 2.6 are two different documents
    with different wording and numbering, not two revisions of one.
    """

    _BY_VERSION = {"3.6": "qc_catalog_uad36.yaml"}
    _FALLBACK = Path(__file__).resolve().parent.parent.parent / \
        "readme" / "exampleAMC" / "qc_rejection_catalog.yaml"

    def path_for(self, uad_version: Optional[str]) -> Path:
        name = self._BY_VERSION.get(str(uad_version or "").strip())
        return (_CONFIG_DIR / name) if name else self._FALLBACK

    def load(self, amc_code: Optional[str], uad_version: Optional[str]
             ) -> List[ChecklistItem]:
        path = self.path_for(uad_version)
        if not path.exists():
            logger.warning("checklist: %s not present — no items loaded", path)
            return []
        doc = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        return [_coerce(r) for r in (doc.get("items") or []) if isinstance(r, dict)]


class DbChecklistSource(ChecklistSource):
    """Reads checklists authored in the frontend and stored in Postgres.

    Not wired yet — the table does not exist. It is declared here so the seam is
    visible and so the swap is a one-line change of `_SOURCE` rather than a hunt
    for every module that opened a YAML file. `_coerce` already tolerates rows
    whose shape differs from the generated YAML, which is what a form-authored
    row will look like.
    """

    def load(self, amc_code: Optional[str], uad_version: Optional[str]
             ) -> List[ChecklistItem]:
        raise NotImplementedError(
            "database-backed checklists are not wired yet; set _SOURCE once the "
            "checklist table exists")


_SOURCE: ChecklistSource = YamlChecklistSource()


def set_source(source: ChecklistSource) -> None:
    """Swap the backend — for the DB migration, and for tests."""
    global _SOURCE
    _SOURCE = source


def load_checklist(amc_code: Optional[str] = None,
                   uad_version: Optional[str] = None) -> List[ChecklistItem]:
    """Every checklist consumer goes through here."""
    items = _SOURCE.load(amc_code, uad_version)
    unclassified = [i.item_id for i in items if not i.classified]
    if unclassified:
        logger.info("checklist: %d of %d item(s) unclassified — they can VERIFY but "
                    "never FAIL until the classifier runs: %s",
                    len(unclassified), len(items), ", ".join(unclassified[:6]))
    return items


def items_with_proof(items: List[ChecklistItem], proof: str) -> List[ChecklistItem]:
    """Address items by CAPABILITY, never by number — the whole point of the
    classification. An AMC renumbering its checklist must not move any rule."""
    want = proof.strip().lower()
    return [i for i in items if i.proof == want]
