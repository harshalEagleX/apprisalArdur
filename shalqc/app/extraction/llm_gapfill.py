"""
extractor.llm_gapfill (lgf-1.0.0) — LLM fills blanks; verbatim-validated or discarded.

SHALqc.md §3.2 step 7: "Only fields still blank after 1–6. Batch one call per
section. Returned value must appear verbatim on the page or it is discarded."

The LLM subsystem itself (2-key failover client, Redis content-hash cache,
grounding — SHALqc.md §10) is Part 10 and is out of scope for this build. This
module defines the gap-fill CONTRACT that extraction/merge.py calls: a
`GapfillClient` protocol any future `app/llm/client.py` implementation can
satisfy, plus the verbatim-or-discard validator, which is the one piece of
this step that is a hard extraction-layer invariant (not an LLM concern) and
so belongs here regardless of which client backs it.

With no client wired in (the default), `gapfill()` returns an empty set —
missing fields stay MISSING and the rules that need them degrade to VERIFY
(SHALqc.md §3.3), never a crash and never a silent guess.
"""

from __future__ import annotations

import logging
from typing import Callable, Dict, List, Optional, Protocol

from app.extraction.result import ExtractedField, ExtractedFieldSet, Source

__version__ = "lgf-1.0.0"

logger = logging.getLogger(__name__)

# SHALqc.md §3.2 step 7 lists this extractor's confidence only as "grounded",
# not a fixed number. 0.75 is used here as a conservative default: above the
# MISSING floor, always below auto_accept (routing.yaml default 0.90, §7) so a
# gap-filled value can never itself push a rule to auto-accept-and-FAIL — it
# can only ever route to VERIFY until Part 7's router assigns a real per-field
# threshold. Never let this drift up without routing.yaml driving it (P4).
_GAPFILL_CONFIDENCE = 0.75


class GapfillClient(Protocol):
    """Contract a Part-10 `app.llm.client` implementation must satisfy.

    `ask(section, fields, page_text) -> {field_id: verbatim_value | None}`.
    The client is responsible only for the model call; verbatim-or-discard
    validation always happens here, never inside the client.
    """

    def ask(self, section: str, fields: List[str], page_text: str) -> Dict[str, Optional[str]]: ...


def _verbatim_ok(value: str, page_text: str) -> bool:
    """SHALqc.md §3.2 step 7 / §3.3: a gap-fill value not found verbatim on the
    page is discarded silently — the field stays MISSING, never a guess."""
    if not value or not page_text:
        return False
    norm_value = " ".join(value.split())
    norm_page = " ".join(page_text.split())
    return norm_value in norm_page


def gapfill(
    missing_fields_by_section: Dict[str, List[str]],
    page_text_by_section: Dict[str, str],
    client: Optional[GapfillClient] = None,
) -> ExtractedFieldSet:
    """Fill still-blank fields via the LLM, one batched call per section.

    `missing_fields_by_section`: {section_name: [canonical_field_name, ...]}
    `page_text_by_section`: {section_name: page_text} — the section's own
    page(s) only, never the whole document (SHALqc-CORE §13 anti-drift note;
    honored here even though the caller isn't CORE-scoped).

    Returns an ExtractedFieldSet containing only the fields the client
    returned AND that passed verbatim grounding. Everything else is left for
    the caller to treat as still-MISSING.
    """
    fs = ExtractedFieldSet()
    if client is None:
        logger.info("llm_gapfill: no client configured — %d field(s) stay MISSING",
                    sum(len(v) for v in missing_fields_by_section.values()))
        return fs

    for section, fields in missing_fields_by_section.items():
        if not fields:
            continue
        page_text = page_text_by_section.get(section, "")
        if not page_text:
            # Nothing to ground a verbatim value against ⇒ any LLM reply would be
            # discarded anyway. Skip the call entirely (SHALqc.md §10 budget /
            # "keep it optimised"): don't spend a call that cannot produce an
            # accepted value. Until merge.py assembles per-section page text,
            # this makes gap-fill a no-op rather than N wasted calls.
            continue
        try:
            reply = client.ask(section, fields, page_text)
        except Exception as exc:  # LLM failure never blocks the pipeline (P6)
            logger.warning("llm_gapfill: call failed for section %s: %s", section, exc)
            continue
        for field_name, value in (reply or {}).items():
            if not value:
                continue
            if not _verbatim_ok(value, page_text):
                logger.info("llm_gapfill: discarding ungrounded value for %s", field_name)
                continue
            fs.add(ExtractedField(
                canonical_name=field_name,
                value=value,
                raw_value=value,
                source=Source.LLM_GAPFILL,
                confidence=_GAPFILL_CONFIDENCE,
            ))
    return fs
