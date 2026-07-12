"""
language.response_model (resp-1.0.0) — the TYPED reviewer response contract.

This is the single specified shape the QC pipeline produces and the Java reviewer
UI consumes. It documents (and validates) every field the frontend needs to render
the two-pane reviewer — checklist cards on one side, the appraisal on the other —
and to AUTO-SCROLL the document when a card is clicked:

  * status/description → what the card shows (pass/fail/verify + the AMC's words)
  * evidence[].page/bbox + primary_location → where to scroll the document
  * bound_by/binder_confidence/decided_by → how the check was judged (trust)
  * llm_interaction_id → drill into the stored raw model exchange

`build_language_report` emits plain dicts (the wire format); this model validates
them (`OrderQCResponse.model_validate(report)`), so the contract can never drift
silently. `model_config` allows extra keys so additive report fields don't break
validation.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict

__version__ = "resp-1.0.0"


# bbox is normalized page coordinates {x, y, w, h} in 0..1 (fractions of page
# width/height) — the frontend maps it to a highlight rectangle for auto-scroll.
BBox = Dict[str, float]


class Evidence(BaseModel):
    """One located value backing a card. page+bbox drive the document auto-scroll."""
    model_config = ConfigDict(extra="allow")
    label: str
    value: Any = None
    quote: Optional[str] = None
    page: Optional[int] = None
    bbox: Optional[BBox] = None
    location_quality: str = "none"
    source: Optional[str] = None
    source_badge: str = ""
    confidence: float = 0.0


class PrimaryLocation(BaseModel):
    model_config = ConfigDict(extra="allow")
    page: Optional[int] = None
    bbox: Optional[BBox] = None
    label: Optional[str] = None
    location_quality: Optional[str] = None


class ReviewerCard(BaseModel):
    """One checklist item as the reviewer sees it."""
    model_config = ConfigDict(extra="allow")
    item_id: str
    group: str                       # recommended_reject | please_verify | looks_good | manual_visual | not_applicable
    section: str = ""
    status: str                      # SATISFIED | NOT_SATISFIED | REVIEW | NOT_APPLICABLE | CANNOT_EVALUATE
    item_name: str = ""              # checklist short name (title)
    check_text: str = ""             # the AMC's check, verbatim
    description: str = ""            # alias of check_text for the UI
    reject_text: Optional[str] = None
    headline: str = ""
    expected: str = ""
    found: str = ""
    reviewer_line: str = ""
    evidence: List[Evidence] = []
    primary_location: Optional[PrimaryLocation] = None
    values: Dict[str, Any] = {}
    suggested_wording: Optional[str] = None
    confidence: float = 0.0
    judgeable: str = "text"
    guardrails: List[str] = []
    decided_by: str = ""
    bound_by: str = ""
    binder_confidence: float = 0.0
    bound_labels: List[str] = []
    llm_interaction_id: Optional[str] = None


class LLMInteractionRecord(BaseModel):
    """The stored raw exchange for one item — everything needed to replay/audit."""
    model_config = ConfigDict(extra="allow")
    id: str
    item_id: str
    call_type: str = ""
    prompt_version: str = ""
    batch_id: str = ""
    provider: str = ""
    model: str = ""
    ms: float = 0.0
    cached: bool = False
    request: Optional[Dict[str, Any]] = None
    response: Optional[Dict[str, Any]] = None
    raw_response: Optional[str] = None
    error: Optional[str] = None


class OrderQCResponse(BaseModel):
    """The full QC response for one order — the Java contract."""
    model_config = ConfigDict(extra="allow")
    order_id: str
    amc_code: str = ""
    status: str = "OK"
    verdict_vocab: str = "v2"
    summary: Dict[str, Any] = {}
    cards: List[ReviewerCard] = []
    extraction_gaps: List[Dict[str, Any]] = []
    llm_interactions: List[LLMInteractionRecord] = []
    location_metric: Dict[str, Any] = {}
    degradations: List[str] = []
    versions: Dict[str, Any] = {}


def validate_report(report: Dict[str, Any]) -> OrderQCResponse:
    """Validate a built report dict against the contract (raises on drift)."""
    return OrderQCResponse.model_validate(report)
