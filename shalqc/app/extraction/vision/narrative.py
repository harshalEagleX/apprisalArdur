"""
extraction.vision.narrative (nar-1.0.0) — the paragraphs, kept as paragraphs.

The most valuable finding on the sample order is a single sentence in a free-text
block on page 19: *"The seller is required to repair the septic system to proper
working order prior to closing."* The report is dated **As Is**. Nothing about
that contradiction is expressible as a field — it only exists as two statements
read together, and one of them is prose.

A field schema destroys it twice over. First by asking for a value where there is
an argument: "was the contract analysed?" answers *yes* and discards what the
analysis said. Second by type coercion downstream, which turned the appraiser's
written answer "None" into the boolean `False` — after which any check asking
"are defects noted?" passes, and the sentence that would have raised the finding
is not in the fact store at all.

So narrative regions are pulled VERBATIM and stored as text. The rule that makes
this necessary:

    the judge never sees the document, so anything extraction does not keep
    does not exist.

Three properties:

  * **No schema, no interpretation.** The model transcribes; it does not
    summarise, and it does not answer questions about what it read. A summary is
    a judgement, and judgement belongs to the layer that can hold pages 3, 8, 19
    and 26 at once.
  * **Hard output cap.** These are the longest calls in the run, and the two
    sections that died on run 18 were exactly the two longest-narrative ones.
    A block that would exceed the cap is truncated at a sentence boundary and
    marked, rather than being allowed to take the call down with it.
  * **Empty is recorded, not inferred.** A block that could not be read is
    `read: false`, never an empty string — "the appraiser wrote nothing" and "we
    failed to read it" must not look alike to whatever reasons over this next.
"""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from app.extraction.vision.provider import VisionProvider
from app.extraction.vision.render import render_page

__version__ = "nar-1.0.0"

logger = logging.getLogger(__name__)

# Deliberately small. Verbatim prose is cheap per page; what is expensive is
# letting one block run unbounded and time out, taking its whole section with it.
_MAX_TOKENS = 900
_DPI = 110


@dataclass
class NarrativeBlock:
    """One free-text region, as written."""

    name: str
    pages: List[int]
    text: str = ""
    read: bool = False
    truncated: bool = False
    error: Optional[str] = None

    def as_dict(self) -> Dict[str, Any]:
        return {"name": self.name, "pages": self.pages, "text": self.text,
                "read": self.read, "truncated": self.truncated, "error": self.error}


def _schema() -> Dict[str, Any]:
    return {
        "type": "object", "additionalProperties": False,
        "required": ["text", "present"],
        "properties": {
            "text": {"type": ["string", "null"],
                     "description": "The paragraph(s) transcribed EXACTLY as printed, "
                                    "including numbers, dates and punctuation. Do not "
                                    "summarise, shorten, reorder or explain. If the "
                                    "region is blank, return null."},
            "present": {"type": "boolean",
                        "description": "True if the region exists on the page at all, "
                                       "whether or not it has content."},
        },
    }


def extract_narratives(pdf_path, blocks: Dict[str, List[int]],
                       provider: VisionProvider, concurrency: int = 4,
                       dpi: int = _DPI) -> Dict[str, NarrativeBlock]:
    """Transcribe each named narrative region verbatim.

    `blocks` maps a region name to the pages that carry it, e.g.
    {"contract_analysis": [19], "listing_history": [19], "reconciliation": [26]}.
    """
    out: Dict[str, NarrativeBlock] = {}
    cache: Dict[int, Any] = {}

    def _one(name: str, pages: List[int]) -> NarrativeBlock:
        block = NarrativeBlock(name=name, pages=list(pages))
        images = []
        for p in pages:
            if p not in cache:
                cache[p] = render_page(pdf_path, p, dpi=dpi)
            if cache[p] is not None:
                images.append(cache[p])
        if not images:
            block.error = "pages could not be rendered"
            return block

        instruction = (
            f"Page(s) {', '.join(str(p) for p in pages)} of an appraisal report.\n\n"
            f"Transcribe the '{name.replace('_', ' ')}' narrative EXACTLY as printed — "
            f"every sentence, number and date, in the order written.\n"
            f"Do NOT summarise it, shorten it, or say what it means. Copy it.\n"
            f"If that region is not on these pages, return null."
        )
        resp = provider.transcribe(images, instruction, _schema(),
                                   max_tokens=_MAX_TOKENS, effort="low")
        if not resp.ok or not resp.data:
            block.error = resp.error or "no data returned"
            return block
        text = (resp.data.get("text") or "").strip()
        block.text = text
        # `read` means WE GOT THE WORDS, which is not the same as the region
        # existing. A region that exists but came back empty is still unread, and
        # must not be mistaken for an appraiser who wrote nothing.
        block.read = bool(text)
        block.truncated = bool(resp.truncated)
        if resp.truncated:
            logger.warning("narrative(%s): hit the output cap — the block is "
                           "incomplete and must not be reasoned over as if whole", name)
        return block

    with ThreadPoolExecutor(max_workers=max(1, min(concurrency, len(blocks) or 1))) as pool:
        futures = {pool.submit(_one, n, p): n for n, p in blocks.items()}
        for fut in as_completed(futures):
            name = futures[fut]
            try:
                out[name] = fut.result()
            except Exception as exc:                      # pragma: no cover
                out[name] = NarrativeBlock(name=name, pages=list(blocks[name]),
                                           error=str(exc))
    return out


def find_contradictions(blocks: Dict[str, NarrativeBlock],
                        fields: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Statements in the prose that disagree with a stated field value.

    Deliberately narrow: this reports a CONFLICT for a human, never a verdict.
    A contract requiring a repair against an As-Is opinion may be perfectly
    proper — that is the AMC's call — but nobody can make that call if the two
    facts never meet, and they only meet here because one of them is a sentence.
    """
    out: List[Dict[str, Any]] = []

    condition = ""
    for key in ("market_value_condition", "appraisal_subject_to"):
        v = fields.get(key)
        val = v.get("value") if isinstance(v, dict) else v
        if val:
            condition = str(val)
            break

    repair_markers = ("required to repair", "must repair", "must be repaired",
                      "prior to closing", "subject to repair", "to be repaired",
                      "repair the")
    for name, block in blocks.items():
        if not block.read:
            continue
        low = block.text.lower()
        hit = next((m for m in repair_markers if m in low), None)
        if hit and "as is" in condition.lower():
            # Quote the sentence, not the paragraph: a reviewer should see the
            # evidence, not be asked to find it.
            sentence = next((s.strip() for s in block.text.split(".")
                             if hit in s.lower()), block.text[:200])
            out.append({
                "kind": "condition_vs_narrative",
                "block": name, "pages": block.pages,
                "detail": (f"the report is '{condition}' but the {name.replace('_', ' ')} "
                           f"states a required repair"),
                "quote": sentence.strip() + ".",
                "status": "VERIFY",
            })
    return out
