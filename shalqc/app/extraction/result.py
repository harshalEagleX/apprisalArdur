"""
extraction/result.py — the ExtractedField contract (SHALqc.md §3.2 P2).

"Every extracted value carries {value, source, confidence, page, bbox}. Never
a bare value." Every extractor in this package returns ExtractedField records
(or an ExtractedFieldSet of them) — nothing downstream ever sees a raw string.

Losing witnesses are never discarded (P3): they land in `conflicts[]` on the
winning field, so a genuine cross-source disagreement survives the merge for a
reviewer to see instead of being silently laundered away.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, Iterator, List, Optional, Tuple

__version__ = "res-1.0.0"


class Source(str, Enum):
    XML = "xml"
    PDF_DIGITAL = "pdf_digital"
    PDF_SCANNED = "pdf_scanned"
    GRID = "grid"
    CHECKBOX = "checkbox"
    ENGAGEMENT = "engagement"
    LLM_GAPFILL = "llm"
    ACROFORM = "acroform"      # SHALqc-CORE §10: embedded PDF form widget (bbox = widget rect)
    CONTRACT = "contract"      # SHALqc-CORE §11: purchase-contract LLM read (conf capped 0.75)
    # UAD 3.6: a VLM transcribed the rendered page (app/extraction/vision/). Confidence
    # sits ABOVE pdf_digital (0.92) — a vision read of a flattened page beats a spatial
    # read that had no text to work with — and BELOW xml (0.97), so _merge_field's
    # XML-priority rule keeps working untouched and vision correctly loses the day a
    # MISMO 3.6 XML shows up. Only ever assigned to a CHECKSUM-VERIFIED value; an
    # unverified read is emitted at VISION_UNVERIFIED so it can never win a merge
    # against a deterministic witness.
    VISION = "vision"
    VISION_UNVERIFIED = "vision_unverified"
    NOT_FOUND = "not_found"


@dataclass
class Conflict:
    """A losing witness for a field, retained rather than discarded (§3.2 step 9)."""

    source: str
    value: str
    confidence: float
    page: int = 0
    bbox: Optional[Dict[str, float]] = None


@dataclass
class ExtractedField:
    """
    The atomic, always-complete output of one field's extraction.

    found=False still produces a complete record — never None, never a bare
    value. `conflicts` accumulates every losing witness seen during merge so
    disagreements are auditable instead of silently dropped.
    """

    canonical_name: str
    value: Optional[str] = None
    source: str = Source.NOT_FOUND
    confidence: float = 0.0
    page: int = 0                              # 1-indexed; 0 = unknown/unlocated
    bbox: Optional[Dict[str, float]] = None    # {x,y,w,h} fractions, top-left origin
    # SHALqc-CORE §3 Back-Locator output: how well this field is pinpointed on
    # the PDF for the reviewer's click-to-scroll. exact (tight box) | region
    # (soft box) | page (scroll only) | none (XML badge, no scroll). None until
    # the back-locator runs; a PDF/grid/checkbox witness with its own bbox is
    # "exact" by construction.
    location_quality: Optional[str] = None

    raw_value: Optional[str] = None            # verbatim text before normalization
    conflicts: List[Conflict] = field(default_factory=list)

    # Stamped by extraction/plausibility.py (§3.3) when a winning value is
    # rejected: value stays visible in raw_value, `value` reads None downstream.
    suppressed: bool = False
    suppression_reason: Optional[str] = None

    # "True"/"False" derived from a boolean-typed field's LITERAL answer, set
    # ALONGSIDE it rather than replacing it.
    #
    # Overwriting was deleting findings: the appraiser answers "Apparent Defects,
    # Damages, Deficiencies" in prose, and rewriting that to "False" made every
    # check asking "are defects noted?" pass while erasing the sentence that
    # would have raised the finding. The judge never sees the document, so
    # anything extraction discards cannot be recovered downstream — the words
    # have to survive, and the flag rides beside them.
    derived_boolean: Optional[str] = None

    @property
    def found(self) -> bool:
        return self.value is not None and not self.suppressed

    def add_conflict(
        self,
        source: str,
        value: str,
        confidence: float,
        page: int = 0,
        bbox: Optional[Dict[str, float]] = None,
    ) -> None:
        self.conflicts.append(
            Conflict(source=source, value=value, confidence=confidence, page=page, bbox=bbox)
        )

    def __repr__(self) -> str:  # pragma: no cover - debug aid
        status = f"'{self.value}' @{self.confidence:.2f} src={self.source}" if self.found else "NOT_FOUND"
        return f"ExtractedField({self.canonical_name}={status} p{self.page})"


class ExtractedFieldSet:
    """One per order/run — every schema field has an entry here, found or not."""

    def __init__(self) -> None:
        self._fields: Dict[str, ExtractedField] = {}

    def add(self, f: ExtractedField) -> None:
        self._fields[f.canonical_name] = f

    def get(self, canonical_name: str) -> Optional[ExtractedField]:
        return self._fields.get(canonical_name)

    def value(self, canonical_name: str) -> Optional[str]:
        f = self._fields.get(canonical_name)
        return f.value if f else None

    def all_fields(self) -> List[ExtractedField]:
        return list(self._fields.values())

    def found_fields(self) -> List[ExtractedField]:
        return [f for f in self._fields.values() if f.found]

    def by_section(self, section: str, schema) -> Dict[str, ExtractedField]:
        section_fields = {fd.canonical_name for fd in schema.fields_for_section(section)}
        return {k: v for k, v in self._fields.items() if k in section_fields}

    def __iter__(self) -> Iterator[Tuple[str, ExtractedField]]:
        return iter(self._fields.items())

    def __len__(self) -> int:
        return len(self._fields)

    def __repr__(self) -> str:  # pragma: no cover - debug aid
        found = len(self.found_fields())
        return f"ExtractedFieldSet({found}/{len(self._fields)} found)"
