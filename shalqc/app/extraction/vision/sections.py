"""
extraction.vision.sections (vsc-1.0.0) — section-scoped transcription.

Two passes, and the first one exists to avoid hardcoding page numbers.

**Pass 1 — triage.** One call carrying every extractable page as a cheap 72-DPI
thumbnail, returning which sections appear on which page. This is deliberate:
the appraisal PDF layout is NOT reliably fixed across vendors, form variants or
even revisions of the same form, so a table that says "the sales grid is on
pages 21-24" is a template anchor that will be wrong on the next file. Asking
costs ~$0.01 and is correct on files nobody has seen.

**Pass 2 — extraction.** One call per section, carrying only that section's
pages at working DPI and only that section's fields. Narrow scope is what
suppresses cross-section hallucination: a model shown one page and asked for
nine fields it can actually see will abstain on the rest; the same model shown
forty pages and asked for two hundred fields will confabulate.

Every emitted value carries `source_text` and `label_text`. If the model cannot
name the printed label it matched, the value is a guess by definition and the
prompt requires a null instead.
"""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import yaml

from app.extraction.page_map import PageProfile
from app.extraction.vision.budget import BudgetExceeded, BudgetGovernor
from app.extraction.vision.provider import VisionProvider
from app.extraction.vision.resilient import transcribe_complete
from app.extraction.vision.render import image_tokens, page_pixels, render_page

__version__ = "vsc-1.0.0"

logger = logging.getLogger(__name__)

_SECTIONS_DIR = Path(__file__).parent.parent.parent.parent / "config" / "vision_sections"

# Thumbnails for the triage pass. Low enough to be nearly free, high enough for
# section HEADINGS to be legible — triage only has to read headings, not values.
_TRIAGE_DPI = 72
# Pages per extraction call. More pages per call is cheaper but widens scope,
# and scope is what abstention depends on.
_MAX_PAGES_PER_CALL = 3
# Concurrent section calls. Together's limits are PER KEY, so this is bounded by
# one key's capacity — the measured lesson on the judge side was that raising
# in-flight requests past a low number produced 429 retry storms that made runs
# both slower AND lossier. Vision has its own key (TOGETHER_API_GEMMA), so it
# gets its own budget rather than competing with the judge for this one.
_MAX_CONCURRENCY = 6
# Images per triage call. A single call carrying all 24 pages made the model
# reason for over three minutes and return nothing; smaller batches are faster,
# run in parallel, and fail in isolation.
_TRIAGE_BATCH = 6
# Output-token allowance for ONE list field, versus 200 for a plain field.
# A list is one entry in the schema and a dozen-plus entries in the answer:
# `sketch`'s area calculations emit one object per line item, which is why the
# only section to truncate in run 14 was also the one with the fewest fields.
# Sized from that call's measured need (5,836 tokens against a 3,200 ceiling)
# with headroom, since an unused ceiling costs nothing and an exhausted one
# costs the entire call.
_LIST_TOKEN_WEIGHT = 2_000


@dataclass
class SectionSpec:
    """One section's extraction contract, loaded from YAML."""

    section: str
    title: str
    instruction: str
    fields: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    lists: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    match_sections: List[str] = field(default_factory=list)
    uad_version: str = "3.6"
    doc_order: int = 99
    # Position through the document as a fraction of the extractable pages.
    # Section ORDER is stable across URAR variants even where page NUMBERS are
    # not, so a proportional window is layout-tolerant in a way a page table is
    # not — and unlike triage it costs nothing and adds no latency.
    page_hint: Optional[float] = None


def load_sections(uad_version: str = "3.6") -> List[SectionSpec]:
    """Load every section spec for a UAD version.

    These are data, not code, precisely so they can move behind the frontend
    later: adding a field to a 3.6 section must never require a deploy.
    """
    folder = _SECTIONS_DIR / f"uad{uad_version.replace('.', '')}"
    specs: List[SectionSpec] = []
    if not folder.exists():
        logger.warning("vision.sections: no section specs at %s", folder)
        return specs
    for path in sorted(folder.glob("*.yaml")):
        try:
            raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
            specs.append(SectionSpec(
                section=raw.get("section") or path.stem,
                title=raw.get("title") or path.stem,
                instruction=(raw.get("instruction") or "").strip(),
                fields=raw.get("fields") or {},
                lists=raw.get("lists") or {},
                match_sections=raw.get("match_sections") or [],
                uad_version=str(raw.get("uad_version") or uad_version),
                doc_order=int(raw.get("doc_order") or 99),
                page_hint=(float(raw["page_hint"]) if raw.get("page_hint") is not None else None),
            ))
        except Exception as exc:
            logger.warning("vision.sections: cannot load %s: %s", path, exc)
    # Document order, not filename order — positional page windows depend on it.
    specs.sort(key=lambda s: s.doc_order)
    return specs


# ── schema construction ───────────────────────────────────────────────────────

def _value_object(describe: str, value_type: str = "string") -> Dict[str, Any]:
    """A field is an OBJECT, never a bare scalar.

    The provenance travels with the value because a value without its label is
    unauditable — and because requiring the model to name the label it matched
    is itself a guard: a confabulated value usually cannot produce a printed
    label to justify it, and the prompt then requires a null instead.
    """
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["value", "source_text", "label_text"],
        "properties": {
            "value": {"type": [value_type, "null"], "description": describe},
            "source_text": {"type": ["string", "null"],
                            "description": "The exact characters as printed on the page."},
            "label_text": {"type": ["string", "null"],
                           "description": "The printed label this value was matched to."},
        },
    }


def build_schema(spec: SectionSpec) -> Dict[str, Any]:
    """JSON schema for one section's extraction call."""
    props: Dict[str, Any] = {
        name: _value_object(cfg.get("describe", name), cfg.get("type", "string"))
        for name, cfg in spec.fields.items()
    }
    for name, cfg in spec.lists.items():
        item_type = cfg.get("type", "string")
        if item_type == "object":
            item = {
                "type": "object", "additionalProperties": False,
                "required": list((cfg.get("properties") or {}).keys()),
                "properties": {
                    k: {"type": ["string", "null"], "description": v.get("describe", k)}
                    for k, v in (cfg.get("properties") or {}).items()
                },
            }
        else:
            item = {"type": [item_type, "null"]}
        props[name] = {"type": ["array", "null"], "items": item,
                       "description": cfg.get("describe", name)}

    return {
        "type": "object", "additionalProperties": False,
        "required": list(props.keys()), "properties": props,
    }


def _triage_schema() -> Dict[str, Any]:
    return {
        "type": "object", "additionalProperties": False, "required": ["pages"],
        "properties": {"pages": {
            "type": "array",
            "items": {
                "type": "object", "additionalProperties": False,
                "required": ["page", "sections", "has_sales_grid"],
                "properties": {
                    "page": {"type": "integer",
                             "description": "The page number written on the image caption."},
                    "sections": {"type": "array", "items": {"type": "string"},
                                 "description": "Section headings visible on this page."},
                    "has_sales_grid": {"type": "boolean",
                                       "description": "True only if this page shows the "
                                                      "multi-column comparable sales grid."},
                },
            },
        }},
    }


# ── pass 1: triage ────────────────────────────────────────────────────────────

def triage_pages(pdf_path, profiles: List[PageProfile], provider: VisionProvider,
                 governor: BudgetGovernor, section_names: List[str],
                 max_pages: int = 30) -> Dict[str, Any]:
    """Map pages -> section headings, and find the sales grid, without assuming
    any fixed layout."""
    pages = [p.page for p in profiles if p.extractable][:max_pages]
    if not pages:
        return {"page_sections": {}, "grid_pages": [], "error": "no extractable pages"}

    batches = [pages[i:i + _TRIAGE_BATCH] for i in range(0, len(pages), _TRIAGE_BATCH)]
    est_in = 900 * len(batches) + 700 * len(pages)
    governor.check("triage", est_in, 250 * len(pages))

    def _run(batch: List[int]):
        images, captions = [], []
        for pno in batch:
            img = render_page(pdf_path, pno, dpi=_TRIAGE_DPI)
            if img is not None:
                images.append(img)
                captions.append(str(pno))
        if not images:
            return None, batch
        instruction = (
            "Each image is one page of an appraisal report. In order, they are "
            "pages " + ", ".join(captions) + ".\n\n"
            "For EACH image, list the section headings printed on it, using the "
            "report's own wording. Headings used by this form include: "
            + "; ".join(section_names[:40]) + ".\n\n"
            "Set has_sales_grid true ONLY for a page showing the side-by-side "
            "comparable sales grid — a table whose COLUMNS are the subject and "
            "several comparable properties. A page of photographs is not the grid."
        )
        return provider.transcribe(images, instruction, _triage_schema(),
                                   max_tokens=3_000, effort="low"), batch

    page_sections: Dict[int, List[str]] = {}
    grid_pages: List[int] = []
    errors: List[str] = []

    with ThreadPoolExecutor(max_workers=min(_MAX_CONCURRENCY, len(batches))) as pool:
        for future in as_completed([pool.submit(_run, b) for b in batches]):
            try:
                resp, batch = future.result()
            except Exception as exc:
                errors.append(str(exc))
                continue
            if resp is None:
                continue
            governor.record("triage", resp.input_tokens or 1_500, resp.output_tokens or 0,
                            resp.started_at, resp.ended_at)
            if not resp.ok:
                errors.append(resp.error or "unknown")
                continue
            for entry in (resp.data.get("pages") or []):
                try:
                    pno = int(entry.get("page"))
                except (TypeError, ValueError):
                    continue
                page_sections[pno] = [s for s in (entry.get("sections") or []) if s]
                if entry.get("has_sales_grid"):
                    grid_pages.append(pno)

    return {"page_sections": page_sections, "grid_pages": sorted(set(grid_pages)),
            "error": "; ".join(errors[:3]) if errors and not page_sections else None,
            "partial_errors": errors}


def _pages_by_hint(spec: SectionSpec, extractable: List[int], window: int) -> List[int]:
    """Candidate pages from the section's position through the document.

    No model call, no latency, and no hardcoded page numbers. It leans on the
    one thing that IS stable across URAR variants — the order sections appear
    in — rather than on absolute page positions, which move with addenda,
    photo counts and vendor template. A window (not a point) absorbs the drift.
    """
    if not extractable:
        return []
    if spec.page_hint is None:
        return extractable[:window]
    centre = int(round(spec.page_hint * (len(extractable) - 1)))
    lo = max(0, centre - window // 2)
    return extractable[lo:lo + window]


def _pages_for_spec(spec: SectionSpec, page_sections: Dict[int, List[str]],
                    extractable: List[int], window: int) -> List[int]:
    """Which pages carry this section — heading match when triage ran, position
    otherwise.

    When triage found nothing for a section, fall back to the positional window
    rather than to "all pages": a heading the triage pass could not read is not
    evidence the section is absent, and dropping it would silently lose every
    field in it.
    """
    wanted = [m.lower() for m in spec.match_sections] or [spec.title.lower()]
    hits = [
        page for page, headings in sorted(page_sections.items())
        if any(w in h.lower() or h.lower() in w
               for h in headings for w in wanted)
    ]
    return hits[:window] if hits else _pages_by_hint(spec, extractable, window)


# ── pass 2: section extraction ────────────────────────────────────────────────

def extract_sections(pdf_path, profiles: List[PageProfile], provider: VisionProvider,
                     governor: BudgetGovernor, dpi: int = 130, effort: str = "low",
                     uad_version: str = "3.6", use_triage: bool = False,
                     max_tokens: int = 8000, concurrency: int = 8,
                     ) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """Run triage then per-section extraction.

    Returns `(values, meta)`. `values` maps canonical field name ->
    {value, source_text, label_text, page, section}; `meta` carries the triage
    map, per-section call outcomes and any degradations, so a partial run is
    explainable rather than merely short.
    """
    specs = load_sections(uad_version)
    meta: Dict[str, Any] = {"sections_attempted": [], "sections_failed": {},
                            "degradations": [], "triage": {}}
    values: Dict[str, Any] = {}
    if not specs:
        meta["degradations"].append("no UAD 3.6 section specs configured")
        return values, meta

    extractable = [p.page for p in profiles if p.extractable]
    section_names = sorted({n for s in specs for n in (s.match_sections or [s.title])})

    # Triage is a SERIAL round trip in front of every section call — ~25s a 60s
    # budget cannot absorb. Off by default; positional windows locate sections
    # instead. Turn it on for an unfamiliar layout, where accuracy beats latency.
    page_sections: Dict[int, List[str]] = {}
    if use_triage:
        try:
            tri = triage_pages(pdf_path, profiles, provider, governor, section_names)
        except BudgetExceeded as exc:
            meta["degradations"].append(str(exc))
            return values, meta
        meta["triage"] = tri
        if tri.get("error"):
            meta["degradations"].append(
                f"triage failed ({tri['error']}) — locating sections by position instead")
        page_sections = tri.get("page_sections") or {}
    else:
        meta["triage"] = {"skipped": "positional windows used (VISION_USE_TRIAGE=0)"}

    # Sections are INDEPENDENT — each reads its own pages and writes its own
    # fields — so they run concurrently. This is the difference between a 60s
    # order and a 10-minute one: latency becomes the slowest single call rather
    # than the sum of every call. The pool is small because Together rate-limits
    # per key and over-sending buys 429-retry storms, not throughput.
    jobs: List[Tuple[SectionSpec, List[int]]] = []
    for spec in specs:
        pages = _pages_for_spec(spec, page_sections, extractable, _MAX_PAGES_PER_CALL)
        if pages:
            jobs.append((spec, pages))
            meta["sections_attempted"].append(spec.section)

    def _run(spec: SectionSpec, pages: List[int]) -> Tuple[SectionSpec, List[int], Any]:
        images = [img for img in (render_page(pdf_path, p, dpi=dpi) for p in pages)
                  if img is not None]
        if not images:
            return spec, pages, None
        instruction = (
            f"Section: {spec.title}.\n"
            f"These images are page(s) {', '.join(str(p) for p in pages)} of the report.\n\n"
            f"{spec.instruction}\n\n"
            "Emit null for any field not visible on these images. Do not carry a "
            "value over from another section or another page."
        )
        # max_tokens must cover REASONING PLUS the JSON. Fitted on run 14's ten
        # clean section calls, output is `515 + 159 x N` (R^2 = 0.68) — so the
        # per-field slope of ~200 holds, but the fixed base is a few hundred
        # tokens rather than the ~2,000 once assumed. The 2,000 is kept as
        # headroom, not as a measured cost.
        #
        # A LIST IS NOT ONE FIELD. It counts as 1 in `len()` and then emits a
        # dozen or more items, and that mismatch is what actually truncates:
        # `sketch` asks for 4 fields + 2 lists, drew a 3,200-token ceiling from
        # the old formula, exhausted it inside its reasoning, and needed 5,836
        # tokens on the retry. Every plain-field section, by contrast, finished
        # inside 25-80% of its ceiling. So the list weight is the fix; raising
        # the base would have been the wrong lever.
        budget_tokens = (2_000
                         + 200 * len(spec.fields)
                         + _LIST_TOKEN_WEIGHT * len(spec.lists))

        # NEVER LOSE A FIELD. Running out mid-reasoning returns an EMPTY body
        # with a 200 status — full latency and tokens paid, every field in the
        # call gone, and nothing in the response saying so. transcribe_complete
        # retries with more room and then splits the field set rather than
        # dropping any of it. Costs nothing on a healthy call.
        merged = {"fields": {**spec.fields}, "lists": {**spec.lists}}

        def _schema_for(subset: Dict[str, Any]) -> Dict[str, Any]:
            sub = SectionSpec(
                section=spec.section, title=spec.title, instruction=spec.instruction,
                fields={k: v for k, v in spec.fields.items() if k in subset},
                lists={k: v for k, v in spec.lists.items() if k in subset},
                match_sections=spec.match_sections, uad_version=spec.uad_version)
            return build_schema(sub)

        askable = {**spec.fields, **spec.lists}
        outcome = transcribe_complete(
            provider, images, instruction, askable, _schema_for,
            # Capped well below the old 16,000. A ceiling is only useful if the
            # call can actually reach it inside the read timeout: run 16's
            # `market` (7,600) and `contract_history` (8,200) each burned the
            # full 300s call budget and returned NOTHING, while their real usage
            # was 3,163 and 3,828. Headroom past what a call can spend is not
            # safety, it is just a longer way to fail.
            max_tokens=min(budget_tokens, 6_500), effort=effort,
            label=f"section:{spec.section}")
        return spec, pages, outcome

    est_per_call = 4_000
    try:
        governor.check("sections", est_per_call * len(jobs), 800 * len(jobs))
    except BudgetExceeded as exc:
        meta["degradations"].append(str(exc))
        return values, meta

    # Use the CONFIGURED concurrency, not the module default. This read
    # `_MAX_CONCURRENCY` (6) and silently ignored the setting, so 11 sections ran
    # as two waves instead of one — doubling the section pass's wall clock for a
    # reason invisible from the outside, because every call still succeeded.
    with ThreadPoolExecutor(max_workers=max(1, min(concurrency, len(jobs)))) as pool:
        futures = [pool.submit(_run, spec, pages) for spec, pages in jobs]
        for future in as_completed(futures):
            try:
                spec, pages, outcome = future.result()
            except Exception as exc:
                meta["degradations"].append(f"section call raised: {exc}")
                continue
            if outcome is None:
                meta["sections_failed"][spec.section] = "no pages rendered"
                continue
            governor.record(f"section:{spec.section}",
                            outcome.input_tokens or est_per_call, outcome.output_tokens or 0,
                            outcome.started_at, outcome.ended_at)
            meta.setdefault("resilience", {})[spec.section] = outcome.summary()
            if outcome.errors and not outcome.data:
                meta["sections_failed"][spec.section] = "; ".join(outcome.errors[:2])
                continue
            if outcome.missing_fields:
                meta["degradations"].append(
                    f"section {spec.section}: {len(outcome.missing_fields)} field(s) "
                    f"unresolved after retry and split")

            page_hint = pages[0]
            for name, payload in (outcome.data or {}).items():
                if isinstance(payload, dict):
                    if payload.get("value") in (None, ""):
                        continue
                    values[name] = {**payload, "page": page_hint, "section": spec.section}
                elif isinstance(payload, list) and payload:
                    values[name] = {"value": payload, "source_text": None,
                                    "label_text": None, "page": page_hint,
                                    "section": spec.section}

    return values, meta
