"""
extraction.vision.checklist_vision (ckv-1.0.0) — answer the checklist by LOOKING.

The 2.6 path extracts fields, then compares them to the checklist. On a UAD 3.6
report that intermediate step is where the accuracy goes. This document has
**zero characters and zero fonts across all 40 pages** — it was printed to PDF
and every glyph is a vector outline — so every value has to be read off pixels
anyway. Extracting 283 fields first and then asking 90 questions of those fields
means each question inherits every extraction loss along its path, and a field
that failed to read becomes a VERIFY on a question the page answers plainly.

So for 3.6 the checklist is asked DIRECTLY against the page images. The model
that would have transcribed the field looks at the same pixels and answers the
actual question instead. Fewer steps, fewer places to lose the answer.

**Grouped by section, one call per page-set.** Questions that share a page share
a call: the images are uploaded once, the model reads the page once, and it
answers that section's questions together. That is both cheaper and more accurate
than 90 separate calls, because the model sees each question in the context of
the whole page rather than being asked to re-derive the layout ninety times.

What does NOT change from the field path, because these are what make it
trustworthy:

  * **The model observes; code decides.** It answers `yes` / `no` / `unclear`
    and cites what it saw. PASS / FAIL / VERIFY is computed here from the
    observation and the question's polarity. A model asked for a verdict will
    produce one whether or not the page supports it.
  * **`unclear` is a real answer and becomes VERIFY**, as does any answer that
    cites no visible evidence. A claim that cannot point at something on the page
    is the shape of a confabulation, however confident it sounds.
  * **Page selection is structural.** Sections are located by page kind and the
    positional window `sections.py` already computes, never by hardcoded page
    numbers, so another vendor's 3.6 moves page numbers without breaking this.

The field path is still run: its values are the evidence a reviewer sees on the
card, and its arithmetic checksums catch what no amount of looking can. This
answers the checklist; it does not replace verification.
"""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from app.extraction.vision.provider import VisionProvider
from app.extraction.vision.render import render_page

__version__ = "ckv-1.0.0"

logger = logging.getLogger(__name__)

# Questions per call. Small enough that the model answers each one properly
# rather than skimming, large enough to amortise the page upload. The sales
# comparison section alone has 23 questions and is split across several calls.
_QUESTIONS_PER_CALL = 6
_MAX_PAGES_PER_CALL = 4
_DPI = 110
# ~180 output tokens per question plus room to describe what was seen.
_TOKENS_PER_QUESTION = 320
_BASE_TOKENS = 900

PASS, FAIL, VERIFY = "PASS", "FAIL", "VERIFY"
# Distinct from VERIFY on purpose. VERIFY says "we looked and could not settle
# it" — a reviewer opens the page. CANNOT_EVALUATE says "this question compares
# the report to a document we were not given" — nobody can settle it until that
# document arrives, and no amount of re-reading the PDF will help. Collapsing the
# two makes a data-intake gap look like a reader defect, and buries six genuinely
# actionable items in a pile of maybes.
CANNOT_EVALUATE = "CANNOT_EVALUATE"

# POLARITY: does a clean report answer this question "yes" or "no"?
#
# Getting this wrong does not produce a near-miss, it produces the exact
# opposite verdict — and in the direction that rejects a good appraisal. The
# first run proved it: "Do any exterior features have a condition status of
# damaged?" was answered `no` (everything Typical Wear and Tear, i.e. a clean
# report) and scored FAIL, along with "Is marketing time more than 6 months?"
# answered `no` at 63 days. Four of six FAILs were the checklist working
# correctly and this mapping inverting it.
#
# So polarity is now three-valued, and UNKNOWN never fails. A FAIL has to be
# earned: confident answer + cited evidence + polarity we actually know.
# Anything else is a reviewer's call, which costs a look; a false rejection
# costs the appraiser a rewrite and the AMC its credibility.
ADVERSE, REQUIRED, UNKNOWN = "no", "yes", "unknown"

# A clean report answers NO: the question asks whether a PROBLEM exists.
_ADVERSE_MARKERS = (
    "any adverse", "any defect", "any damage", "any deficien", "damaged",
    "non-functional", "non-residential", "illegal", "any large", "multi-parcel",
    "legal non-conforming", "functional defic", "any special assessments",
    "more than 6 months", "any inconsisten", "any discrepan", "work/live",
    "across-the-board", "exceed", "any concern",
)
# A clean report answers YES: the question asks whether something REQUIRED is
# present, consistent, confirmed or provided.
_REQUIRED_MARKERS = (
    "are the required", "is the required", "can you confirm", "have you confirmed",
    "does the sketch include", "are the room labels", "was the ansi",
    "is the property address consistent", "are all rights", "does the appraiser provide",
    "did the appraiser provide", "is the sale price of the subject bracketed",
    "bracketed by the comparable", "are at least", "has the appraiser provided",
    "are the photographs", "does the sales comparison map",
)


def polarity_of(question: str, item: Optional[Dict[str, Any]] = None) -> str:
    """ADVERSE / REQUIRED / UNKNOWN for a checklist question.

    **The catalog is the authority.** `tools/classify_checklist.py` classifies
    each item once, per AMC, and stores the answer as data — because polarity is
    a property of the WORDING, and every AMC words its checklist differently.
    Baking one AMC's phrasing into this module made the next AMC's checklist
    silently mis-lane, which is the failure this indirection exists to prevent.

    The keyword tables below survive only as a fallback for a catalog that has
    not been classified yet, and they resolve to UNKNOWN rather than guessing
    when they do not recognise the phrasing. UNKNOWN can never produce a FAIL, so
    an unclassified checklist degrades to reviewer looks, never to false
    rejections.
    """
    if item:
        declared = (item.get("polarity") or "").strip().lower()
        if declared in (ADVERSE, REQUIRED, UNKNOWN):
            return declared
    q = " ".join(question.lower().split())
    if any(m in q for m in _ADVERSE_MARKERS):
        return ADVERSE
    if any(m in q for m in _REQUIRED_MARKERS):
        return REQUIRED
    return UNKNOWN


@dataclass
class ChecklistAnswer:
    rule_id: str
    checklist_number: int
    section: str
    question: str
    status: str = VERIFY
    answer: Optional[str] = None
    observed: str = ""
    evidence: List[str] = field(default_factory=list)
    pages: List[int] = field(default_factory=list)
    reason: str = ""

    def as_dict(self) -> Dict[str, Any]:
        return {"rule_id": self.rule_id, "checklist_number": self.checklist_number,
                "section": self.section, "question": self.question,
                "status": self.status, "answer": self.answer,
                "observed": self.observed, "evidence": self.evidence,
                "pages": self.pages, "reason": self.reason}


def _schema(n: int) -> Dict[str, Any]:
    return {
        "type": "object", "additionalProperties": False, "required": ["answers"],
        "properties": {"answers": {
            "type": "array",
            "description": f"Exactly {n} entries, one per question, in the same order.",
            "items": {
                "type": "object", "additionalProperties": False,
                "required": ["number", "answer", "observed", "evidence"],
                "properties": {
                    "number": {"type": ["integer", "null"],
                               "description": "The question number it answers."},
                    "answer": {"type": ["string", "null"],
                               "enum": ["yes", "no", "unclear", None],
                               "description": "As the images actually show it. "
                                              "'unclear' when they do not settle it — "
                                              "that is a correct answer, not a failure."},
                    "observed": {"type": ["string", "null"],
                                 "description": "One or two sentences on what is visible."},
                    "evidence": {"type": ["array", "null"], "items": {"type": "string"},
                                 "description": "Specific things seen — printed values, "
                                                "photo captions, labels, dimensions."},
                },
            },
        }},
    }


def decide(answer: Optional[str], evidence: List[str], expect: str) -> tuple:
    """Observation -> verdict. The model never sees this mapping.

    Only ever returns FAIL when all three conditions hold: the model answered
    decisively, it cited something visible, and the question's polarity is known.
    Every other combination is a reviewer's call.
    """
    a = (answer or "").strip().lower()
    if a not in ("yes", "no"):
        return VERIFY, "the page did not settle the question"
    if not evidence:
        return VERIFY, "answered without citing anything visible on the page"

    if expect == UNKNOWN:
        # We know what the page says; we do not know whether that is compliant.
        return VERIFY, (f"page answers '{a}', but whether that satisfies this item "
                        f"is a reviewer's call")
    if expect == REQUIRED:
        return (PASS, "required content is present") if a == "yes" \
            else (FAIL, "required content is not present")
    # ADVERSE: 'no' is a clean report. 'yes' is a disclosed problem — a finding
    # for a reviewer, never an automatic failure, because correctly disclosing a
    # defect is the appraiser doing their job.
    return (PASS, "no adverse condition visible") if a == "no" \
        else (VERIFY, "an adverse condition is indicated — reviewer must assess")


def _chunk(seq: List[Any], size: int) -> List[List[Any]]:
    return [seq[i:i + size] for i in range(0, len(seq), size)]


def run_checklist_vision(pdf_path, items: List[Dict[str, Any]], profiles: List[Any],
                         provider: VisionProvider,
                         section_pages: Dict[str, List[int]],
                         concurrency: int = 20, dpi: int = _DPI
                         ) -> List[ChecklistAnswer]:
    """Answer every checklist item by looking at the pages that carry it."""
    photo_pages = [p.page for p in profiles if getattr(p, "kind", "") == "photo_grid"]

    # Items needing a document we were not given are settled here, before any
    # call. Sending them to the model wastes the call AND invites a confident
    # answer to a question the images cannot possibly address — the model has no
    # way to know the loan file exists, so asked "does this match the loan file?"
    # it will answer about the page in front of it.
    results: List[ChecklistAnswer] = []
    answerable: List[Dict[str, Any]] = []
    for it in items:
        needs = it.get("requires_documents") or []
        if needs:
            results.append(ChecklistAnswer(
                rule_id=it.get("rule_id", "?"),
                checklist_number=it.get("checklist_number", 0),
                section=it.get("section", "other"),
                question=it.get("requirement", ""),
                status=CANNOT_EVALUATE,
                reason=("requires " + ", ".join(needs).replace("_", " ") +
                        " — not part of the appraisal PDF"),
            ))
        else:
            answerable.append(it)

    by_section: Dict[str, List[Dict[str, Any]]] = {}
    for it in answerable:
        by_section.setdefault(it.get("section", "other"), []).append(it)

    jobs = []
    for section, sec_items in by_section.items():
        pages = list(section_pages.get(section) or [])
        # A question whose evidence is a photograph needs the photo sheets, which
        # are not where the section's text lives.
        if any(i.get("binding") == "visual" for i in sec_items) and photo_pages:
            pages = (pages + photo_pages)[:_MAX_PAGES_PER_CALL]
        pages = sorted(set(pages))[:_MAX_PAGES_PER_CALL]
        if not pages:
            continue
        for group in _chunk(sec_items, _QUESTIONS_PER_CALL):
            jobs.append((section, pages, group))

    cache: Dict[int, Any] = {}

    def _one(section, pages, group):  # noqa: D401 - closure over cache/provider
        images = []
        for p in pages:
            if p not in cache:
                cache[p] = render_page(pdf_path, p, dpi=dpi)
            if cache[p] is not None:
                images.append(cache[p])
        if not images:
            return section, group, None
        numbered = "\n".join(
            f"  {i.get('checklist_number')}. {i.get('requirement')}" for i in group)
        instruction = (
            f"These are page(s) {', '.join(str(p) for p in pages)} of an appraisal "
            f"report, section: {section.replace('_', ' ')}.\n\n"
            f"Answer each question below from what the images SHOW:\n{numbered}\n\n"
            "Answer only from what is visible. If the images do not settle a "
            "question, answer 'unclear' — that is correct, not a failure. For each "
            "answer list the specific things you saw that justify it (printed "
            "values, labels, photo captions, dimensions). Do not judge whether the "
            "report is acceptable; report only what is there."
        )
        resp = provider.transcribe(
            images, instruction, _schema(len(group)),
            max_tokens=_BASE_TOKENS + _TOKENS_PER_QUESTION * len(group), effort="low")
        return section, group, resp

    with ThreadPoolExecutor(max_workers=max(1, min(concurrency, len(jobs) or 1))) as pool:
        futures = {pool.submit(_one, s, p, g): p for s, p, g in jobs}
        for fut in as_completed(futures):
            pages_used = futures[fut]
            try:
                section, group, resp = fut.result()
            except Exception as exc:                     # pragma: no cover
                logger.warning("checklist vision: call raised: %s", exc)
                continue
            by_number = {}
            if resp is not None and resp.ok and resp.data:
                for a in (resp.data.get("answers") or []):
                    if isinstance(a, dict) and a.get("number") is not None:
                        by_number[a["number"]] = a
            for it in group:
                num = it.get("checklist_number")
                ans = ChecklistAnswer(
                    rule_id=it.get("rule_id", "?"), checklist_number=num,
                    section=section, question=it.get("requirement", ""),
                    pages=list(pages_used))
                got = by_number.get(num)
                if got is None:
                    ans.reason = ("no answer returned for this question"
                                  if resp is None or resp.ok
                                  else f"call failed: {resp.error}")
                    results.append(ans)
                    continue
                ans.answer = (got.get("answer") or "").strip().lower() or None
                ans.observed = (got.get("observed") or "").strip()
                ans.evidence = [e for e in (got.get("evidence") or []) if str(e).strip()]
                ans.status, ans.reason = decide(
                    ans.answer, ans.evidence, polarity_of(ans.question, it))
                results.append(ans)

    results.sort(key=lambda a: a.checklist_number or 0)
    return results
