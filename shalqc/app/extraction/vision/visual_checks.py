"""
extraction.vision.visual_checks (vck-1.0.0) — checklist items answered by LOOKING.

Fourteen of the UAD 3.6 checklist's ninety questions have no textual answer.
"Are the required photos included: front, back and street scene?", "Does the
sketch include legible exterior dimensions reported to the nearest tenth of a
foot?", "Does the Sales Comparison Map show the subject and the comparables?" —
no field in any schema answers these, and transcribing the page cannot either.

The field-extraction path therefore had to route them all to VERIFY, which is
honest but wastes the fact that **the model reading these pages is a vision
model**. The evidence is not text, but it is visible, and gemma can see it.

Three rules make this trustworthy rather than a confident guess:

  1. **The model OBSERVES; it never renders the verdict.** It answers a factual
     question about what is on the page and lists what it saw. Mapping that to
     PASS / FAIL / VERIFY happens here, in code, from the observation — the same
     separation the narrative path uses, and for the same reason: a model asked
     for a verdict will produce one whether or not the evidence supports it.
  2. **`unclear` is a first-class answer and becomes VERIFY.** An item a reviewer
     must look at is a correct outcome. An item silently passed is not.
  3. **Every answer must cite what it saw.** An observation with no cited
     evidence is downgraded to VERIFY regardless of how confident it sounds,
     because a claim that cannot point at anything on the page is exactly the
     shape of a confabulation.

Page selection is structural, never a hardcoded page number: photo questions go
to the pages `page_map` classified as photo grids, sketch questions to the pages
carrying the sketch, map questions to the pages carrying a map. A 3.6 report from
a different vendor moves the page numbers, not the page kinds.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from app.extraction.vision.provider import VisionProvider
from app.extraction.vision.render import render_page

__version__ = "vck-1.0.0"

logger = logging.getLogger(__name__)

# Small on purpose. One question, one short structured answer — this is the
# accuracy lever: a call asked a single factual question about a single page set
# outperforms one asked to adjudicate six questions at once, and it costs a
# fraction of the output.
_MAX_TOKENS = 1_200
_MAX_PAGES_PER_CHECK = 6
# Photo sheets are dense; they need enough resolution for a caption to be legible
# but not enough to blow the payload.
_DPI = 110

PASS, FAIL, VERIFY = "PASS", "FAIL", "VERIFY"


@dataclass
class VisualVerdict:
    """One checklist item decided (or explicitly not decided) by looking."""

    rule_id: str
    checklist_number: int
    question: str
    status: str = VERIFY
    answer: Optional[str] = None          # yes | no | unclear, as observed
    observed: str = ""                    # what the model says it saw
    evidence: List[str] = field(default_factory=list)
    pages: List[int] = field(default_factory=list)
    reason: str = ""

    def as_dict(self) -> Dict[str, Any]:
        return {
            "rule_id": self.rule_id, "checklist_number": self.checklist_number,
            "question": self.question, "status": self.status, "answer": self.answer,
            "observed": self.observed, "evidence": self.evidence,
            "pages": self.pages, "reason": self.reason,
        }


def _schema() -> Dict[str, Any]:
    return {
        "type": "object", "additionalProperties": False,
        "required": ["answer", "observed", "evidence"],
        "properties": {
            "answer": {
                "type": ["string", "null"],
                "enum": ["yes", "no", "unclear", None],
                "description": "yes / no as the images actually show it. "
                               "'unclear' if the images do not settle it — that is "
                               "a correct answer, not a failure.",
            },
            "observed": {
                "type": ["string", "null"],
                "description": "One or two sentences describing only what is visible.",
            },
            "evidence": {
                "type": ["array", "null"],
                "items": {"type": "string"},
                "description": "Specific things seen that justify the answer — photo "
                               "captions, printed dimensions, labels. Empty if none.",
            },
        },
    }


def _pages_for(evidence_kind: str, profiles: List[Any],
               section_pages: Optional[List[int]] = None) -> List[int]:
    """Pages that could answer this question, chosen by page KIND.

    Structural rather than positional so a different vendor's 3.6 — which moves
    the page numbers but not the page types — still lands on the right pages.
    """
    photo = [p.page for p in profiles if getattr(p, "kind", "") == "photo_grid"]
    if evidence_kind == "photos":
        return photo[:_MAX_PAGES_PER_CHECK]
    if evidence_kind in ("sketch", "map"):
        # The sketch and the location/comparable map are drawing-heavy pages that
        # are NOT photo grids. Prefer the section's own pages when triage found
        # them; fall back to the densest non-photo pages.
        if section_pages:
            return sorted(section_pages)[:_MAX_PAGES_PER_CHECK]
        cand = [p for p in profiles if getattr(p, "kind", "") != "photo_grid"]
        cand.sort(key=lambda p: getattr(p, "drawings", 0), reverse=True)
        return sorted(p.page for p in cand[:_MAX_PAGES_PER_CHECK])
    return (section_pages or [])[:_MAX_PAGES_PER_CHECK]


def _decide(answer: Optional[str], evidence: List[str], expect: str) -> tuple:
    """Observation -> verdict. The model never sees this mapping.

    `expect` is what a compliant report looks like: "yes" when the question asks
    whether something REQUIRED is present ("are the required photos included?"),
    "no" when it asks whether something ADVERSE is present ("are there any
    defects?"). A 'yes' to a defects question is not a failed check — it is a
    finding that needs a reviewer, so it becomes VERIFY rather than FAIL.
    """
    a = (answer or "").strip().lower()
    if a not in ("yes", "no"):
        return VERIFY, "the images did not settle the question"
    if not evidence:
        return VERIFY, "answered without citing anything visible on the page"
    if expect == "yes":
        return (PASS, "required content is present") if a == "yes" \
            else (FAIL, "required content is not present in the images")
    # Adverse-condition questions: 'no' is clean, 'yes' needs a human.
    return (PASS, "no adverse condition visible") if a == "no" \
        else (VERIFY, "an adverse condition appears in the images — reviewer must assess")


def run_visual_checks(pdf_path, items: List[Dict[str, Any]], profiles: List[Any],
                      provider: VisionProvider,
                      section_pages: Optional[Dict[str, List[int]]] = None,
                      dpi: int = _DPI) -> List[VisualVerdict]:
    """Answer every `binding: visual` checklist item by looking at the pages."""
    out: List[VisualVerdict] = []
    cache: Dict[int, Any] = {}

    for item in items:
        v = VisualVerdict(rule_id=item.get("rule_id", "?"),
                          checklist_number=item.get("checklist_number", 0),
                          question=item.get("requirement", ""))
        kind = item.get("visual_evidence") or "photos"
        pages = _pages_for(kind, profiles,
                           (section_pages or {}).get(item.get("section", "")))
        v.pages = pages
        if not pages:
            v.reason = "no page of the required kind was found in this document"
            out.append(v)
            continue

        images = []
        for p in pages:
            if p not in cache:
                cache[p] = render_page(pdf_path, p, dpi=dpi)
            if cache[p] is not None:
                images.append(cache[p])
        if not images:
            v.reason = "pages could not be rendered"
            out.append(v)
            continue

        instruction = (
            f"These are page(s) {', '.join(str(p) for p in pages)} of an appraisal "
            f"report.\n\nAnswer this question about what the images SHOW:\n"
            f"  {v.question}\n\n"
            "Answer only from what is visible. If the images do not settle it, "
            "answer 'unclear' — that is a correct answer. List the specific things "
            "you saw that justify your answer (photo captions, printed dimensions, "
            "labels). Do not judge whether the report is acceptable; only report "
            "what is there."
        )
        resp = provider.transcribe(images, instruction, _schema(),
                                   max_tokens=_MAX_TOKENS, effort="low")
        if not resp.ok or not resp.data:
            v.reason = f"visual check call failed: {resp.error}"
            out.append(v)
            continue

        v.answer = (resp.data.get("answer") or "").strip().lower() or None
        v.observed = (resp.data.get("observed") or "").strip()
        v.evidence = [e for e in (resp.data.get("evidence") or []) if str(e).strip()]
        v.status, v.reason = _decide(v.answer, v.evidence,
                                     item.get("expect_answer", "yes"))
        out.append(v)
        logger.info("visual check %s (#%s): %s — %s", v.rule_id,
                    v.checklist_number, v.status, v.reason)
    return out
