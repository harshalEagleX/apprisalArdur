"""
extraction.vision.grid (grd-1.0.0) — the comparable sales grid.

The densest, highest-stakes region in the report and the one place a misread is
most damaging: a column shifted by one turns every adjustment into a different
comparable's adjustment, and the resulting numbers are individually plausible.
Nothing downstream can detect that from the values alone.

Three defenses, each earned from a specific observed failure:

1. **Value and adjustment are ONE object per cell.** `{"value": "$5,350",
   "adjustment": 0}`. A flat grid extractor that reads them as separate rows
   can never surface the audit's single biggest catch — five comparables
   carrying real seller concessions, every one adjusted $0.

2. **The checksum is the arbiter, not the model's confidence.** A whole-page
   read is cheap, so it runs first; `verify.verify_comp_column` then tests two
   independent identities that a shifted, dropped or sign-flipped column cannot
   satisfy. Only a column that FAILS is re-extracted, as a per-comparable crop
   at higher DPI. This buys per-column isolation exactly where it is needed
   instead of paying for it on every comparable.

3. **Never emit a partial comp set.** Marked incomplete, and the caller must
   refuse range/bracketing checks until every column is in hand — partial
   coverage does not degrade gracefully, it manufactures findings.
"""

from __future__ import annotations

import logging
import time
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Dict, List, Optional, Tuple

from app.extraction import verify as V
from app.extraction.vision.budget import BudgetExceeded, BudgetGovernor
from app.extraction.vision.provider import VisionProvider
from app.extraction.vision.render import (label_and_column_clips,
                                          render_label_value_composite,
                                          render_page, render_region)

# Wall-clock cap on the whole checksum-retry pass. Run 27 spent 943s here,
# unlogged and unbounded, on a loop that is serial in both dimensions.
_RETRY_BUDGET_S = 90.0

__version__ = "grd-1.0.0"

logger = logging.getLogger(__name__)

# Grid rows carrying a paired value + dollar adjustment. Names map to the
# canonical comp_<n>_<suffix> contract the rest of the stack already speaks.
_PAIRED_ROWS: List[Tuple[str, str]] = [
    ("sales_concessions", "Sale or financing concessions"),
    ("sale_date", "Date of sale / time"),
    ("location", "Location rating"),
    ("site_size", "Site size / lot area"),
    ("view", "View rating"),
    ("design_style", "Design and appeal / style"),
    ("quality", "Quality of construction rating"),
    ("actual_age", "Actual age"),
    ("condition", "Condition rating"),
    ("room_count_total", "Total room count"),
    ("bedrooms", "Bedroom count"),
    ("bathrooms", "Bathroom count"),
    ("gla", "Gross living area"),
    ("basement", "Basement and finished rooms below grade"),
    ("functional_utility", "Functional utility"),
    ("heating_cooling", "Heating and cooling"),
    ("energy_efficient", "Energy efficient items"),
    ("vehicle_storage", "Garage / carport / vehicle storage"),
    ("porch_patio_deck", "Porch, patio, deck / outdoor living"),
    ("outbuilding", "Outbuilding"),
    ("other", "Other adjustments"),
]

# Rows that are values only — no dollar adjustment column.
_PLAIN_ROWS: List[Tuple[str, str]] = [
    ("address", "Street address of the comparable"),
    ("proximity", "Proximity to the subject"),
    ("sale_price", "Sale price"),
    ("data_source", "Data source(s)"),
    ("verification_source", "Verification source(s)"),
    ("listing_status", "Whether this comparable is a settled sale or an active/pending listing"),
    ("days_on_market", "Days on market"),
    ("comparable_weight", "Comparable weight, if the form states one"),
]


def _cell() -> Dict[str, Any]:
    return {
        "type": "object", "additionalProperties": False,
        "required": ["value", "adjustment"],
        "properties": {
            "value": {"type": ["string", "null"],
                      "description": "The cell's value exactly as printed."},
            "adjustment": {"type": ["string", "null"],
                           "description": "The dollar adjustment for this row exactly as "
                                          "printed, including accounting parentheses for "
                                          "negatives, e.g. $(12,000). Null if the cell is "
                                          "blank or shows no adjustment. '0' and blank are "
                                          "DIFFERENT — do not substitute one for the other."},
        },
    }


# The canonical row vocabulary, handed to the model AS DATA. This replaces the
# regex label map: rather than transcribing free-form labels and pattern-matching
# them back in code — a per-vendor hardcode that breaks the moment a form prints
# "Garage/Carport" instead of "Vehicle Storage" — the model is given the allowed
# names and does the semantic matching itself, which is the part it is good at.
# The list is data, so a new row type is a config change, not a code change.
_ROW_VOCAB: List[Tuple[str, str]] = [
    ("address", "street address of the comparable"),
    ("proximity", "proximity/distance to the subject"),
    ("list_price", "list price"),
    ("sale_price", "sale or settled price"),
    ("contract_price", "contract price"),
    ("listing_status", "settled sale / pending / active listing"),
    ("data_source", "data source, e.g. an MLS number"),
    ("verification_source", "verification source"),
    ("days_on_market", "days on market"),
    ("sale_type", "transfer terms, e.g. arm's length / typically motivated"),
    ("financing_type", "financing type"),
    ("sales_concessions", "sale or financing concessions"),
    ("contract_date", "contract date"),
    ("sale_date", "date of sale"),
    ("property_rights", "property rights appraised"),
    ("location", "site influence or location rating"),
    ("site_size", "site size / lot area"),
    ("view", "view rating or range of view"),
    ("design_style", "design, style or construction method"),
    ("year_built", "year built"),
    ("actual_age", "actual age of the dwelling"),
    ("quality", "quality of construction rating"),
    ("condition", "condition rating"),
    ("room_count_total", "total room count"),
    ("bedrooms", "bedroom count"),
    ("bathrooms", "bathroom count"),
    ("gla", "finished area ABOVE grade / gross living area"),
    ("basement_gla", "finished area BELOW grade"),
    ("basement_unfinished", "unfinished area below grade"),
    ("functional_utility", "functional utility"),
    ("heating_cooling", "heating and cooling"),
    ("energy_efficient", "energy efficient items"),
    ("vehicle_storage", "garage, carport or vehicle storage"),
    ("porch_patio_deck", "outdoor living: porch, patio or deck"),
    ("water_features", "water features"),
    ("outbuilding", "outbuilding"),
    ("dwelling_type", "attached or detached"),
    ("net_adjustment_total", "NET adjustment total"),
    ("gross_adjustment_total", "GROSS adjustment total"),
    ("adjusted_price", "adjusted sale price"),
    ("comparable_weight", "comparable weight"),
    ("other", "any other row not covered above"),
]

# Rows that are summary figures, not adjustable line items. Folding these into
# the line-item set would feed the net total back into the sum it is meant to be
# checked against, and the checksum would then pass on any reading whatsoever.
_SUMMARY_ROWS = frozenset({
    "net_adjustment_total", "gross_adjustment_total", "adjusted_price",
    "comparable_weight", "address", "proximity", "data_source",
    "verification_source", "listing_status", "days_on_market", "list_price",
    "contract_price", "sale_price", "property_rights",
})


def _ordinal(n: int) -> str:
    return {1: "first", 2: "second", 3: "third", 4: "fourth",
            5: "fifth", 6: "sixth"}.get(n, f"{n}th")


def _single_comp_schema() -> Dict[str, Any]:
    """ONE comparable, as canonically-named rows."""
    return {
        "type": "object", "additionalProperties": False,
        "required": ["comp_number", "rows"],
        "properties": {
            "comp_number": {"type": ["integer", "null"],
                            "description": "The number printed in this column's heading."},
            "rows": {
                "type": "array",
                "description": "One entry per row visible for this comparable on this page.",
                "items": {
                    "type": "object", "additionalProperties": False,
                    "required": ["field", "value", "adjustment"],
                    "properties": {
                        "field": {"type": "string", "enum": [n for n, _ in _ROW_VOCAB],
                                  "description": "Which row this is: "
                                                 + "; ".join(f"{n} = {d}" for n, d in _ROW_VOCAB)},
                        "value": {"type": ["string", "null"],
                                  "description": "This comparable's value, exactly as printed."},
                        "adjustment": {"type": ["string", "null"],
                                       "description": "Dollar adjustment for this row, keeping "
                                                      "accounting parentheses on negatives e.g. "
                                                      "$(12,000). null if none printed. '0' and "
                                                      "blank are DIFFERENT."},
                    },
                },
            },
        },
    }


def _page_grid_schema() -> Dict[str, Any]:
    """Every comparable on one page, each as a list of canonically-named rows."""
    return {
        "type": "object", "additionalProperties": False,
        "required": ["comparables"],
        "properties": {
            "comparables": {
                "type": "array",
                "description": "One entry per COMPARABLE column on this page. "
                               "Exclude the subject column.",
                "items": {
                    "type": "object", "additionalProperties": False,
                    "required": ["comp_number", "rows"],
                    "properties": {
                        "comp_number": {
                            "type": ["integer", "null"],
                            "description": "The number in this column's heading, "
                                           "e.g. 4 for 'Comparable #4'."},
                        "rows": {
                            "type": "array",
                            "description": "One entry per row visible for THIS comparable.",
                            "items": {
                                "type": "object", "additionalProperties": False,
                                "required": ["field", "value", "adjustment"],
                                "properties": {
                                    "field": {
                                        "type": "string",
                                        "enum": [n for n, _ in _ROW_VOCAB],
                                        "description": "Which row this is. Choose the "
                                                       "closest name: "
                                                       + "; ".join(f"{n} = {d}" for n, d in _ROW_VOCAB)},
                                    "value": {"type": ["string", "null"],
                                              "description": "This comparable's value, exactly as printed."},
                                    "adjustment": {
                                        "type": ["string", "null"],
                                        "description": "Dollar adjustment printed for this row, "
                                                       "keeping accounting parentheses on negatives "
                                                       "e.g. $(12,000). null if none is printed. "
                                                       "'0' and blank are DIFFERENT."},
                                },
                            },
                        },
                    },
                },
            },
        },
    }


def _rows_to_comp_v2(payload: Dict[str, Any], comp_no: int) -> Dict[str, Any]:
    """Canonically-labelled rows -> the paired-cell shape verify.py expects.
    No pattern matching: the model already chose the name from the vocabulary."""
    comp: Dict[str, Any] = {"comp_number": comp_no}
    for row in (payload.get("rows") or []):
        if not isinstance(row, dict):
            continue
        field_name = str(row.get("field") or "").strip()
        if not field_name or field_name == "other":
            continue
        value, adj = row.get("value"), row.get("adjustment")
        if field_name in _SUMMARY_ROWS:
            if value not in (None, ""):
                comp.setdefault(field_name, value)
            continue
        if not _is_empty(comp.get(field_name)):
            continue
        comp[field_name] = {"value": value, "adjustment": adj}
    return comp


def _row_schema() -> Dict[str, Any]:
    """One comparable as a LIST OF ROWS, not as fixed properties.

    The fixed-property schema forced 37 keys on every call regardless of what the
    page held, so output scaled with the SCHEMA rather than with the page — most
    of it nulls the model still had to reason about and emit. That cost latency
    on every call and, worse, invited invention: asked for `energy_efficient` on
    a page that has no such row, a model looking for something to put there can
    find it.

    A row list scales with what is actually printed. Fewer output tokens, and
    abstention becomes the default rather than an instruction — a row that isn't
    on the page simply isn't in the list. Labels are mapped to canonical field
    names afterwards, in code, where the mapping is deterministic and auditable.
    """
    return {
        "type": "object", "additionalProperties": False,
        "required": ["comp_number", "rows"],
        "properties": {
            "comp_number": {"type": ["integer", "null"],
                            "description": "This comparable's number as printed in its column heading."},
            "rows": {
                "type": "array",
                "description": "One entry per row VISIBLE on this page, in printed order.",
                "items": {
                    "type": "object", "additionalProperties": False,
                    "required": ["label", "value", "adjustment"],
                    "properties": {
                        "label": {"type": "string",
                                  "description": "The row's label exactly as printed in the left-hand label column."},
                        "value": {"type": ["string", "null"],
                                  "description": "This comparable's value for that row, exactly as printed."},
                        "adjustment": {"type": ["string", "null"],
                                       "description": "The dollar adjustment printed for this row, "
                                                      "keeping accounting parentheses on negatives, "
                                                      "e.g. $(12,000). null if no adjustment is printed. "
                                                      "'0' and blank are DIFFERENT — never substitute one."},
                    },
                },
            },
        },
    }


def _comp_schema(single: bool = False) -> Dict[str, Any]:
    props: Dict[str, Any] = {
        "comp_number": {"type": ["integer", "null"],
                        "description": "1-based position of this comparable in the grid."},
        "net_adjustment_total": {"type": ["string", "null"],
                                 "description": "Net adjustment total exactly as printed."},
        "gross_adjustment_total": {"type": ["string", "null"],
                                   "description": "Gross adjustment total exactly as printed."},
        "adjusted_price": {"type": ["string", "null"],
                           "description": "Adjusted sale price exactly as printed."},
    }
    for name, describe in _PLAIN_ROWS:
        props[name] = {"type": ["string", "null"], "description": describe}
    for name, describe in _PAIRED_ROWS:
        cell = _cell()
        cell["description"] = describe
        props[name] = cell

    comp = {"type": "object", "additionalProperties": False,
            "required": list(props.keys()), "properties": props}
    if single:
        return {"type": "object", "additionalProperties": False,
                "required": ["comparable"], "properties": {"comparable": comp}}
    return {
        "type": "object", "additionalProperties": False,
        "required": ["comparables", "subject_gla", "subject_site_size"],
        "properties": {
            "comparables": {"type": "array", "items": comp},
            "subject_gla": {"type": ["string", "null"],
                            "description": "The SUBJECT column's gross living area."},
            "subject_site_size": {"type": ["string", "null"],
                                  "description": "The SUBJECT column's site size."},
        },
    }


_GRID_RULES = (
    "This is a comparable sales grid. Read it as a table.\n\n"
    "- Each COLUMN is one property. The leftmost data column is the SUBJECT; the "
    "columns to its right are the comparables, numbered 1, 2, 3... left to right.\n"
    "- Each ROW is one characteristic, named by the label in the left-hand label "
    "column. Identify every row by its own printed LABEL. Do NOT use band or "
    "section headers to identify rows — on this form some band headers render as "
    "overlapping garbled glyphs, and a header you cannot read cleanly must never "
    "be used.\n"
    "- Most rows have TWO parts per comparable: the value, and a dollar adjustment "
    "beside it. Report both, in that row's own object. If a row shows a value but "
    "no adjustment, the adjustment is null. If it shows an explicit 0 or $0, the "
    "adjustment is \"0\" — a blank and a zero are different facts and one of them "
    "is a finding.\n"
    "- Negative adjustments are printed as $(12,000) or (12,000). Transcribe them "
    "exactly as printed, parentheses included.\n"
    "- Stay inside one column when reading that comparable. Never take a value "
    "from the column to its left or right.\n"
    "- If a cell is blank, emit null. Do not carry a value down from the row above "
    "or across from the neighbouring column."
)


# Printed row label -> canonical suffix. Matched on normalised substrings, so
# wording drift between vendors ("Gross Living Area" / "Finished Area Above
# Grade" / "Above Grade Finished") lands on the same field without a per-vendor
# template. Order matters: the FIRST match wins, so more specific patterns come
# first ("finished area below grade" before "finished area").
_LABEL_MAP: List[Tuple[Tuple[str, ...], str]] = [
    (("street address", "property address", "address"), "address"),
    (("proximity",), "proximity"),
    (("data source", "data sources"), "data_source"),
    (("verification",), "verification_source"),
    (("list price",), "list_price"),
    (("listing status", "status"), "listing_status"),
    (("contract price",), "contract_price"),
    (("sale price", "sales price"), "sale_price"),
    (("transfer terms",), "sale_type"),
    (("financing type", "financing"), "financing_type"),
    (("sales concession", "sale or financing", "concession"), "sales_concessions"),
    (("contract date",), "contract_date"),
    (("sale date", "date of sale"), "sale_date"),
    (("days on market", "dom"), "days_on_market"),
    (("attached/detached", "attachment"), "dwelling_type"),
    (("property rights",), "property_rights"),
    (("site size", "site area", "lot size"), "site_size"),
    (("site influence", "location"), "location"),
    (("view",), "view"),
    (("year built",), "year_built"),
    (("construction method", "design", "style"), "design_style"),
    (("heating", "cooling"), "heating_cooling"),
    (("bedroom",), "bedrooms"),
    (("bath",), "bathrooms"),
    (("total room", "room count"), "room_count_total"),
    (("finished area below grade", "below grade"), "basement_gla"),
    (("unfinished area", "unfinished"), "basement_unfinished"),
    (("finished area above grade", "above grade", "gross living area", "gla"), "gla"),
    (("basement",), "basement"),
    (("actual age", "age"), "actual_age"),
    (("quality",), "quality"),
    (("condition",), "condition"),
    (("outdoor living", "porch", "patio", "deck"), "porch_patio_deck"),
    (("water feature",), "water_features"),
    (("vehicle storage", "garage", "carport"), "vehicle_storage"),
    (("outbuilding",), "outbuilding"),
    (("functional utility",), "functional_utility"),
    (("energy",), "energy_efficient"),
    (("net adjustment",), "net_adjustment_total"),
    (("gross adjustment",), "gross_adjustment_total"),
    (("adjusted price", "adjusted sale price"), "adjusted_price"),
    (("comparable weight", "weight"), "comparable_weight"),
    (("indicated value",), "indicated_value"),
]


def _canonical_row(label: str) -> Optional[str]:
    """Map a printed row label to its canonical suffix, or None if unrecognised.

    None is deliberate: an unmapped row is kept in the raw payload for the report
    but is NOT invented into a canonical field. Guessing a binding is how a value
    ends up under the wrong name, which is worse than not having it — the judge
    would then reason about the right number in the wrong place.
    """
    text = re.sub(r"[^a-z0-9 ]+", " ", str(label or "").lower())
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        return None
    # WORD-BOUNDARY matching, not substring. A plain `in` test looks correct and
    # silently mis-files rows: "age" matches "stor-AGE", so "Vehicle Storage"
    # mapped to actual_age and the vehicle-storage adjustment would have landed
    # under the age line. The checksum cannot catch that — the sum is unchanged,
    # only the meaning is wrong — so it has to be prevented here.
    for needles, canon in _LABEL_MAP:
        for needle in needles:
            # Optional plural suffix: forms print "Bedrooms"/"Baths"/"Sales
            # Concessions" while the needles are singular. The leading boundary
            # still blocks the "age" in "storage".
            if re.search(rf"(?<![a-z0-9]){re.escape(needle)}(?:e?s)?(?![a-z0-9])", text):
                return canon
    return None


def _rows_to_comp(payload: Dict[str, Any], comp_no: int) -> Dict[str, Any]:
    """Row list -> the paired-cell shape verify.py and the emitter expect."""
    comp: Dict[str, Any] = {"comp_number": comp_no}
    unmapped: List[str] = []
    for row in (payload.get("rows") or []):
        if not isinstance(row, dict):
            continue
        canon = _canonical_row(row.get("label"))
        value, adj = row.get("value"), row.get("adjustment")
        if canon is None:
            if row.get("label"):
                unmapped.append(str(row.get("label"))[:40])
            continue
        # Summary rows are scalars, not adjustable line items — folding them into
        # the paired shape would feed the net total back into the sum of lines it
        # is supposed to be checked against, and the checksum would pass on any
        # reading at all.
        if canon in ("net_adjustment_total", "gross_adjustment_total",
                     "adjusted_price", "comparable_weight", "address",
                     "proximity", "data_source", "verification_source",
                     "listing_status", "days_on_market", "list_price",
                     "contract_price", "indicated_value"):
            if value not in (None, ""):
                comp.setdefault(canon, value)
            continue
        if canon == "sale_price":
            if value not in (None, ""):
                comp.setdefault("sale_price", value)
            if adj not in (None, ""):
                comp.setdefault("sale_price_line", {"value": value, "adjustment": adj})
            continue
        existing = comp.get(canon)
        if isinstance(existing, dict) and not _is_empty(existing):
            continue
        comp[canon] = {"value": value, "adjustment": adj}
    if unmapped:
        comp["_unmapped_rows"] = unmapped
    return comp


def _absorb(comps: Dict[int, Dict[str, Any]], comp: Dict[str, Any],
            comp_no: int, page: int) -> None:
    """Fold one page's reading of a comparable into what is already held.

    The grid spans a page PAIR and the same comparable appears on both halves:
    the first page carries its line adjustments, the second the net total and
    adjusted price those lines must reconcile against. Merging (rather than
    treating the second sighting as a new comparable) is what lets the checksum
    see one whole column instead of two unverifiable halves.
    """
    if _is_empty_comp(comp):
        # Fewer comparables than the layout allows — a real fact about the
        # report, not a failure. Record nothing rather than a blank comparable.
        return
    comp["comp_number"] = comp_no
    existing = comps.get(comp_no)
    if existing is None:
        comp["_page"] = page
        comp["_pages"] = [page]
        comps[comp_no] = comp
        return
    for key, val in comp.items():
        if key in ("_page", "_pages", "comp_number"):
            continue
        if _is_empty(existing.get(key)) and not _is_empty(val):
            existing[key] = val
    existing.setdefault("_pages", [existing.get("_page")]).append(page)


def _is_empty_comp(comp: Dict[str, Any]) -> bool:
    return not any(not _is_empty(v) for k, v in comp.items()
                   if k not in ("comp_number", "_page", "_pages", "_unmapped_rows"))


def _is_empty(value: Any) -> bool:
    """Treat a paired cell whose value AND adjustment are both absent as empty,
    so a page-pair merge fills it rather than keeping the hollow object."""
    if value in (None, "", []):
        return True
    if isinstance(value, dict):
        return all(v in (None, "") for v in value.values())
    return False


def extract_grid(pdf_path, grid_pages: List[int], provider: VisionProvider,
                 governor: BudgetGovernor, dpi: int = 150, dpi_retry: int = 200,
                 effort: str = "medium", max_retries: int = 2,
                 expected_comps: Optional[int] = None, max_tokens: int = 20_000,
                 concurrency: int = 8, per_column: bool = True,
                 comps_per_page: int = 3) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """Extract every comparable column, then checksum-gate each one.

    Returns `(result, meta)` where result carries `comparables` and `complete`,
    and meta carries per-comparable verification outcomes. A column that never
    verifies is RETAINED but flagged unverified — it must reach the reviewer as
    a REVIEW card, never a silent pass and never a silent drop.
    """
    meta: Dict[str, Any] = {"pages": list(grid_pages), "calls": [], "verification": {},
                            "retries": 0, "degradations": []}
    comps: Dict[int, Dict[str, Any]] = {}
    subject: Dict[str, Any] = {}

    if not grid_pages:
        meta["degradations"].append(
            "no sales-grid page identified — comparable checks cannot run")
        return {"comparables": [], "complete": False, "subject": {}}, meta

    # ── pass 1: ONE CALL PER COMPARABLE, all in parallel ─────────────────────
    #
    # Per-column rather than per-page, for two independent reasons that happen
    # to point the same way:
    #
    #   LATENCY. Output tokens are generated serially at ~75/s, so one call
    #   carrying six comparables x ~29 rows is a single long generation — up to
    #   268s at a 20k ceiling. Six calls each carrying ONE comparable emit a
    #   sixth of the tokens and run concurrently, so wall-clock collapses to
    #   roughly one call.
    #
    #   CORRECTNESS. A crop containing exactly one comparable cannot be read one
    #   column to the right. Column shift is the failure mode that produces
    #   individually plausible numbers no downstream check can catch, which is
    #   why the design called for column extraction in the first place.
    #
    # Each comparable's call carries the label strip and its own column from
    # BOTH pages of its pair, because the pair splits one comparable's rows
    # across two pages — p21 has the line adjustments, p22 has the net total and
    # adjusted price that must reconcile against them.
    if per_column and len(grid_pages) >= 1:
        return _extract_by_column(
            pdf_path, grid_pages, provider, governor, dpi, dpi_retry, effort,
            max_retries, expected_comps, max_tokens, concurrency, meta)

    # ── fallback: whole grid pages, in parallel ───────────────────────────────
    # Grid pages are independent reads, so they overlap. Comparable numbering
    # RESTARTS on the second page-pair (p23 shows "Comparable #4-6" as its own
    # columns but a model may report them 1-3), so each pair carries an offset
    # derived from its position in the page list, and pages within a pair share
    # an offset so their rows merge onto the same comparable.
    pair_offset = {p: (i // 2) * 3 for i, p in enumerate(sorted(grid_pages))}

    def _read(page: int):
        img = render_page(pdf_path, page, dpi=dpi)
        if img is None:
            return page, None
        return page, provider.transcribe(
            [img],
            f"Page {page} of the report.\n\n{_GRID_RULES}\n\n"
            "Transcribe EVERY comparable column shown on this page. If this page "
            "continues a grid started on the previous page, the comparables are "
            "numbered left to right as shown in THIS page's column headings.",
            _comp_schema(), max_tokens=max_tokens, effort=effort)

    est_in, est_out = 4_000, 3_000
    try:
        governor.check("grid", est_in * len(grid_pages), est_out * len(grid_pages))
    except BudgetExceeded as exc:
        meta["degradations"].append(str(exc))
        return {"comparables": [], "complete": False, "subject": {}}, meta

    responses = []
    with ThreadPoolExecutor(max_workers=min(concurrency, max(len(grid_pages), 1))) as pool:
        for future in as_completed([pool.submit(_read, p) for p in grid_pages]):
            try:
                responses.append(future.result())
            except Exception as exc:
                meta["degradations"].append(f"grid page call raised: {exc}")

    for page, resp in sorted(responses, key=lambda r: r[0]):
        if resp is None:
            meta["degradations"].append(f"page {page} could not be rendered")
            continue
        page_offset = pair_offset.get(page, 0)
        governor.record(f"grid:p{page}", resp.input_tokens or est_in, resp.output_tokens or 0,
                        resp.started_at, resp.ended_at)
        meta["calls"].append({"page": page, "ok": resp.ok, "error": resp.error})
        if not resp.ok:
            continue

        subject.setdefault("gla", resp.data.get("subject_gla"))
        subject.setdefault("site_size", resp.data.get("subject_site_size"))
        for comp in (resp.data.get("comparables") or []):
            n = V.to_number(comp.get("comp_number"))
            if n is None:
                continue
            idx = int(n) + page_offset
            comp["_page"] = page
            comp["comp_number"] = idx
            if idx in comps:
                # ── MERGE, never renumber ────────────────────────────────────
                # The grid spans a PAGE PAIR. Verified on this form: page 21
                # carries comps 1-3's General Information, Site, Dwelling and
                # Unit rows, while page 22 carries the SAME comps 1-3 continued
                # — Amenities, Vehicle Storage, Outbuilding, and crucially the
                # Summary block with Net Adjustment Total, Adjusted Price and
                # Comparable Weight.
                #
                # So "Comparable #1" legitimately appears twice, and treating
                # the second sighting as a new comparable would both invent a
                # phantom comp and strand the net/adjusted figures away from the
                # line adjustments they must reconcile against — breaking the
                # checksum that is the entire safety mechanism here.
                merged = comps[idx]
                for key, val in comp.items():
                    if key in ("_page", "comp_number"):
                        continue
                    existing = merged.get(key)
                    if _is_empty(existing) and not _is_empty(val):
                        merged[key] = val
                merged.setdefault("_pages", [merged.get("_page")])
                merged["_pages"].append(page)
            else:
                comps[idx] = comp

    # ── pass 2: checksum gate, with per-column re-extraction on failure ───────
    #
    # BOUNDED IN WALL CLOCK. This loop is serial across comparables and serial
    # again across each one's retries, and every retry is a fresh model call at
    # the HIGHER retry DPI — bigger images, slower calls. Six failing columns at
    # two attempts each is twelve serial calls with nothing capping them.
    #
    # Run 27 spent 943 SECONDS here — 72% of a 1,305s run — in a stretch that
    # logged nothing at all between the consistency pass and the final
    # surrenders. A reviewer waiting on that order had no way to tell the
    # pipeline apart from a hang.
    #
    # A column that will not reconcile after one bounded attempt is a REVIEW
    # card, and a REVIEW card delivered now is worth more than a certified one
    # delivered a quarter of an hour late.
    retry_deadline = time.monotonic() + _RETRY_BUDGET_S
    for idx in sorted(comps):
        res = V.verify_comp_column(comps[idx], idx)
        attempt = 0
        while res.errors and attempt < max_retries:
            if time.monotonic() >= retry_deadline:
                meta.setdefault("degradations", []).append(
                    f"grid retry budget ({_RETRY_BUDGET_S:.0f}s) spent — comp {idx} "
                    "and any later column keep their unverified read")
                logger.warning("vision(grid): retry budget spent at comp %s — "
                               "remaining columns go to review unretried", idx)
                break
            attempt += 1
            meta["retries"] += 1
            redo = _reextract_column(
                pdf_path, comps[idx].get("_page"), idx, len(comps), provider, governor,
                dpi=dpi_retry, effort=effort, prior_errors=res.errors)
            if redo is None:
                break
            redo["_page"] = comps[idx].get("_page")
            redo["comp_number"] = idx
            new_res = V.verify_comp_column(redo, idx)
            # Keep the re-read only if it is actually better. A retry that
            # verifies replaces the original; one that fails differently is not
            # progress, and swapping it in would trade a known-bad read for an
            # unknown-bad one.
            if new_res.verified or len(new_res.errors) < len(res.errors):
                comps[idx], res = redo, new_res
            if new_res.verified:
                break

        meta["verification"][f"comp_{idx}"] = res.as_dict()

    comp_list = [comps[i] for i in sorted(comps)]
    set_res = V.verify_comp_set(comp_list, expected=expected_comps)
    meta["verification"]["comp_set"] = set_res.as_dict()

    return {
        "comparables": comp_list,
        "subject": subject,
        "complete": set_res.ok,
        "verified_comps": [i for i in sorted(comps)
                           if meta["verification"].get(f"comp_{i}", {}).get("verified")],
    }, meta


def _extract_by_column(pdf_path, grid_pages: List[int], provider: VisionProvider,
                       governor: BudgetGovernor, dpi: int, dpi_retry: int, effort: str,
                       max_retries: int, expected_comps: Optional[int],
                       max_tokens: int, concurrency: int, meta: Dict[str, Any],
                       comps_per_page: int = 3
                       ) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """One call per comparable, every call in flight at once."""
    pages = sorted(grid_pages)
    # Pages pair up: (p21,p22) carry comps 1-3, (p23,p24) carry comps 4-6.
    pairs = [pages[i:i + 2] for i in range(0, len(pages), 2)]

    # ONE call per (comparable, PAGE): a label-strip + column-strip crop of a
    # single page, one comparable per call.
    #
    # Four shapes have been tried against this document. What each one taught:
    #
    #   column crops, per page   clipped overflowing text at 4% padding; let the
    #                            neighbour bleed in at 22% (comp 1 came back with
    #                            14 line adjustments where 7 exist). 8% padding is
    #                            the measured compromise — see label_and_column_clips.
    #   whole page, all comps    three columns x ~29 rows in one generation
    #                            exhausted the ceiling on the dense pages and
    #                            returned NOTHING for them.
    #   whole page, one comp     the model reasons about everything VISIBLE before
    #                            reporting the column asked for, so the dense pages
    #                            still exhausted the ceiling.
    #   crops, both pages/call   run 14. Fewer, bigger calls: total output fell 42%
    #                            exactly as predicted, and reliability collapsed to
    #                            2 of 6.
    #
    # Run 14 is why this is back to one page per call, and the per-call numbers say
    # why plainly. Three of the six pair-calls stopped at EXACTLY the 9,000-token
    # ceiling and returned nothing at all — comps 2 and 3 burned 26,760 characters
    # of reasoning without emitting a single field. That is 27,000 output tokens,
    # 36% of the entire order's output, spent for zero data. A fourth call spent
    # 546s in a retry loop and also returned nothing.
    #
    # The earlier rationale for merging the pair rested on two numbers that the
    # per-call data has since disproved (P19): there is no ~4,000-token fixed
    # reasoning tax to amortise — the fitted fixed cost is ~515 tokens — and wall
    # clock is not `total_output / (keys x 100)`, it is set by the SLOWEST CALL.
    # Both corrections point the same way: make each call small enough to finish,
    # and let them run in parallel. Halving the rows per call halves both the
    # reasoning and the JSON, which is the only lever that moves the slowest call.
    #
    # Merging back across the pair is safe and already structural: _absorb keys on
    # the comparable number, so the line adjustments from the first page and the
    # net/adjusted summary from the second reconcile as one column (P15).
    tasks: List[Tuple[int, List[int], int]] = []
    for pair_idx, pair in enumerate(pairs):
        for col in range(comps_per_page):
            comp_no = pair_idx * comps_per_page + col + 1
            for page in pair:
                tasks.append((comp_no, [page], col))
    meta["strategy"] = (f"one_call_per_comparable_per_page ({len(tasks)} calls over "
                        f"{len(pairs)} page pair(s))")

    est_in, est_out = 3_000, 2_500
    try:
        governor.check("grid", est_in * len(tasks), est_out * len(tasks))
    except BudgetExceeded as exc:
        meta["degradations"].append(str(exc))
        return {"comparables": [], "complete": False, "subject": {}}, meta

    # +1 column: the SUBJECT occupies the first data column, so comparable N
    # sits at crop index N (0 = subject).
    n_cols = comps_per_page + 1

    def _one(comp_no: int, pair: List[int], col: int):
        # CROP to the label column plus this comparable's column, full height so
        # the column HEADING rides along and the model can confirm which
        # comparable it is looking at.
        #
        # A whole-page image was tried and fails for a non-obvious reason: the
        # model reasons about EVERYTHING visible before reporting the one column
        # asked for, so the two dense grid pages exhausted the token ceiling and
        # returned nothing at all — leaving each comparable with only the half
        # from the sparser page, and no checksum able to close. Cropping bounds
        # what there is to reason about, which is what keeps the call finishing.
        images = []
        for page in pair:
            img = render_label_value_composite(pdf_path, page, col + 1, n_cols, dpi=dpi)
            if img is not None:
                images.append(img)
                continue
            # Composite unavailable (no Pillow, or a render fault): fall back to
            # the two-image form, which works but correlates rows by ordinal
            # position and mis-aligns on merged cells.
            labels, column = label_and_column_clips(col + 1, n_cols)
            for clip in (labels, column):
                fb = render_region(pdf_path, page, dpi=dpi, clip=clip)
                if fb is not None:
                    images.append(fb)
        if not images:
            return comp_no, pair, None
        pages_txt = ", ".join(str(p) for p in pair)
        instruction = (
            f"One crop from page {pages_txt} of an appraisal sales grid.\n"
            f"The image has TWO panels separated by a black vertical rule: the "
            f"left panel is the grid's row labels, the right panel is ONE "
            f"comparable's values for those same rows. A label and its value sit "
            f"at the SAME HEIGHT — read straight across, and use the vertical "
            f"position to pair them, never the row order alone. Rows are not all "
            f"the same height and some cells are merged across rows.\n"
            f"Every row that shows a dollar figure in the adjustment cell has an "
            f"adjustment, including large negatives such as $(23,800). An empty "
            f"adjustment cell is null; a printed $0 is zero. They are different.\n"
            f"This page carries only PART of the comparable; the rest is on the "
            f"facing page and is read separately. Report only what is printed "
            f"here, and emit null for rows that are not on this page rather than "
            f"carrying anything over.\n"
            f"The right panel is cropped a little wide, so a sliver of a "
            f"neighbouring column may show at an edge: report only the column "
            f"whose heading is centred in that panel.\n\n"
            f"{_GRID_RULES}\n\n"
            f"Give one row entry per printed row. Do not repeat a row."
        )
        return comp_no, pair, provider.transcribe(
            images, instruction, _single_comp_schema(),
            max_tokens=max_tokens, effort=effort)

    comps: Dict[int, Dict[str, Any]] = {}
    with ThreadPoolExecutor(max_workers=min(concurrency, max(len(tasks), 1))) as pool:
        futures = [pool.submit(_one, c, p, col) for c, p, col in tasks]
        for future in as_completed(futures):
            try:
                comp_no, pair, resp = future.result()
            except Exception as exc:
                meta["degradations"].append(f"comparable call raised: {exc}")
                continue
            if resp is None:
                continue
            governor.record(f"grid:comp{comp_no}", resp.input_tokens or est_in,
                            resp.output_tokens or 0, resp.started_at, resp.ended_at)
            meta["calls"].append({"comp": comp_no, "pages": pair,
                                  "ok": resp.ok, "error": resp.error})
            if not resp.ok:
                continue
            # comp_no comes from the TASK, not from the model's reading of the
            # heading: the task decides which column was requested, so a model
            # that misreads "#4" as "#1" cannot silently overwrite another
            # comparable's data.
            _absorb(comps, _rows_to_comp_v2(resp.data or {}, comp_no), comp_no, pair[0])

    for idx in sorted(comps):
        res = V.verify_comp_column(comps[idx], idx)
        meta["verification"][f"comp_{idx}"] = res.as_dict()

    comp_list = [comps[i] for i in sorted(comps)]
    set_res = V.verify_comp_set(comp_list, expected=expected_comps)
    meta["verification"]["comp_set"] = set_res.as_dict()
    return {
        "comparables": comp_list, "subject": {}, "complete": set_res.ok,
        "verified_comps": [i for i in sorted(comps)
                           if meta["verification"].get(f"comp_{i}", {}).get("verified")],
    }, meta


def _reextract_column(pdf_path, page: Optional[int], comp_no: int, n_comps: int,
                      provider: VisionProvider, governor: BudgetGovernor,
                      dpi: int, effort: str,
                      prior_errors: List[str]) -> Optional[Dict[str, Any]]:
    """Re-read ONE comparable as a label-strip + column-strip crop at higher DPI.

    Both escalations are mechanisms rather than model bets: cropping removes the
    neighbouring columns a misread could shift into, and higher DPI puts more
    pixels on the same cells. The failed arithmetic is quoted back so the model
    knows which identity did not hold — it is a concrete, checkable statement
    about the page, not a vague instruction to try harder.
    """
    if page is None:
        return None
    # Grid columns are: label column, subject, then the comparables. The subject
    # occupies one comparable-width slot, so the crop index is offset by one.
    composite = render_label_value_composite(pdf_path, page, comp_no, n_comps + 1, dpi=dpi)
    if composite is not None:
        imgs = [composite]
    else:
        labels_clip, column_clip = label_and_column_clips(comp_no, n_comps + 1)
        imgs = [render_region(pdf_path, page, dpi=dpi, clip=labels_clip),
                render_region(pdf_path, page, dpi=dpi, clip=column_clip)]
        imgs = [i for i in imgs if i is not None]
        if len(imgs) < 2:
            return None

    est_in = sum(i.tokens for i in imgs) + 2_000
    try:
        governor.check(f"grid:comp{comp_no}:retry", est_in, 1_200)
    except BudgetExceeded:
        return None

    instruction = (
        f"A crop from page {page} in two panels separated by a black vertical "
        f"rule: the LEFT panel is the grid's row labels, the RIGHT panel is the "
        f"single column for comparable {comp_no}. A label and its value sit at "
        f"the SAME HEIGHT — read straight across. Rows vary in height and some "
        f"cells are merged, so pair by vertical position, never by row order "
        f"alone.\n\n{_GRID_RULES}\n\n"
        f"A previous transcription of this column FAILED an arithmetic check:\n  - "
        + "\n  - ".join(prior_errors) +
        "\n\nThe printed figures on the page are correct; the previous reading of "
        "them was not. Re-read every row carefully, keeping each value aligned "
        "with its own label, and report exactly what is printed."
    )
    resp = provider.transcribe(imgs, instruction, _comp_schema(single=True),
                               max_tokens=8_000, effort=effort)
    governor.record(f"grid:comp{comp_no}:retry", resp.input_tokens or est_in,
                    resp.output_tokens or 0)
    if not resp.ok:
        return None
    return (resp.data or {}).get("comparable")


def grid_row_vocabulary() -> List[str]:
    """Every row label this grid can legitimately carry an adjustment against.

    Exposed so verification can bind adjustments to rows rather than only summing
    them. A sum is invariant to which label each addend sits under, so a
    one-row shift reconciles perfectly while every adjustment below it means the
    wrong thing — which is exactly what happened to comparable 4 on run 18.
    """
    return [name for name, _ in _ROW_VOCAB if name not in _SUMMARY_ROWS]
