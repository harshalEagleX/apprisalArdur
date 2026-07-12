"""
extraction.contract (contract-1.0.0) — SHALqc-CORE §11 purchase-contract read.

Contracts have NO fixed layout, so template anchoring doesn't apply. Contract
fields are read by a dedicated C1-variant LLM call over the full contract text
(chunked ≥1 chunk / 4 pages), verbatim-or-discard, at a FIXED confidence of
**0.75** — below auto-accept, above unusable. That cap is deliberate: contract
reads are the least trustworthy input in the system, so every contract-dependent
rule structurally lands at VERIFY-max unless the appraisal side independently
corroborates (enforced by `contract_cap` in the rules layer).

Back-locator for contract evidence is text-search (L2-style) against the
contract PDF, else page-level — same honesty rules as everywhere else.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Dict, List, Optional

from app.extraction.result import ExtractedField, ExtractedFieldSet, Source

__version__ = "contract-1.0.0"

logger = logging.getLogger(__name__)

_CONF = 0.75  # CORE §11 fixed cap

# canonical contract fields + plain descriptions for the LLM
_FIELDS = {
    "contract_price": "the purchase/sale price (a dollar amount)",
    "contract_date": "the date the contract was signed/executed",
    "seller_name": "the seller/grantor name(s)",
    "buyer_names": "the buyer/purchaser name(s)",
    "concessions_amount": "seller-paid concessions/credits amount, if any",
    "financing_type": "the financing type (cash, conventional, FHA, VA, ...)",
}

_SYS = (
    "Read the purchase contract text and return the VERBATIM value of each requested "
    "field. If a field is not present, return null. Never compose, summarize, or fix text. "
    'Reply JSON only: {"fields": {"<field_id>": "<verbatim or null>"}}.'
)


def _contract_text(pdf_path) -> str:
    import fitz
    doc = fitz.open(str(pdf_path))
    try:
        return "\n".join(doc[i].get_text("text") for i in range(len(doc)))
    finally:
        doc.close()


def _locate(pdf_path, value: str) -> Dict[str, object]:
    """Text-search the contract PDF for `value`; return {page, bbox, loc}."""
    import re

    import fitz
    norm = re.sub(r"\s+", " ", value).strip()
    doc = fitz.open(str(pdf_path))
    try:
        for i in range(len(doc)):
            rects = doc[i].search_for(norm[:60]) if norm else []
            if rects:
                r = rects[0]
                pw, ph = float(doc[i].rect.width), float(doc[i].rect.height)
                return {"page": i + 1,
                        "bbox": {"x": round(r.x0 / pw, 5), "y": round(r.y0 / ph, 5),
                                 "w": round((r.x1 - r.x0) / pw, 5), "h": round((r.y1 - r.y0) / ph, 5)},
                        "loc": "exact"}
        return {"page": 1, "bbox": None, "loc": "page"}
    finally:
        doc.close()


def extract_contract(pdf_path, llm_client=None) -> ExtractedFieldSet:
    """Read contract fields via the LLM (verbatim-or-discard, conf 0.75). Empty
    set when no LLM is configured (contract stays unread → contract rules VERIFY)."""
    fs = ExtractedFieldSet()
    if not pdf_path or llm_client is None or not getattr(llm_client, "available", False):
        return fs
    text = _contract_text(pdf_path)
    if not text.strip():
        return fs

    user = json.dumps({"fields": [{"field_id": k, "description": d} for k, d in _FIELDS.items()],
                       "contract_text": text[:12000]})
    res = llm_client.complete("contract_read", _SYS, user, max_tokens=800)
    if not res.ok:
        return fs
    got = (res.data or {}).get("fields", {}) or {}
    tnorm = " ".join(text.split()).lower()
    for fid, val in got.items():
        if fid not in _FIELDS or not val:
            continue
        # verbatim-or-discard: value must appear in the contract text
        if " ".join(str(val).split()).lower() not in tnorm:
            logger.info("contract: dropped ungrounded '%s' for %s", val, fid)
            continue
        loc = _locate(pdf_path, str(val))
        fs.add(ExtractedField(
            canonical_name=fid, value=str(val), raw_value=str(val),
            source=Source.CONTRACT, confidence=_CONF,
            page=loc["page"], bbox=loc["bbox"], location_quality=loc["loc"]))
    if len(list(fs)):
        logger.info("contract: read %d field(s) at conf %.2f", len(list(fs)), _CONF)
    return fs
