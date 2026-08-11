# UAD 3.6 — Vision-First Extraction: Build Plan & Cost Model

**Status:** proposal / not yet implemented
**Author:** derived from the 2026-08-03 audit of `shalqc/3.6/`
**Scope:** UAD 3.6 (redesigned URAR, Fannie/Freddie Sept 2024) only. **UAD 2.6 is untouched.**

---

## 0. Why this document exists

The existing extractor was built for **UAD 2.6 = fixed-grid 1004 PDF + MISMO 2.6 XML**. The
first UAD 3.6 sample arrives as a **40-page flowing URAR with no XML and no text layer**.
We measured what the current pipeline does with it. It does not work, and it does not
fail loudly — it emits confidently wrong values.

This document is the plan to fix that, plus a cost model so the spend is a decision
rather than a surprise.

---

## 1. Evidence base — what we actually measured

Sample: `shalqc/3.6/Email - AppraisalArdur - Outlook (1).pdf`
Subject: 1465 Turner Rd NE, Rome, GA 30165 · Purchase · $300,000 contract / $310,000 opinion

### 1.1 The PDF has no text

| Probe | Result |
|---|---|
| `page.get_text()` across all 40 pages | **0 characters** |
| `page.get_fonts()` | **0 fonts, every page** |
| `get_text("rawdict")` blocks | **0** |
| `pdftotext` output | **40 bytes** (one form-feed per page) |
| `get_drawings()` items, page 2 alone | 18,392 curves + 8,717 lines + 200 rects |

Producer metadata is **PDFium**. The glyphs are **vector outlines**, not text — a sampled
"drawing" occupies `Rect(214.2, 57.5, 217.1, 62.5)` (2.9pt × 5pt), i.e. one letter drawn
as bezier paths.

> **Root cause is partly the delivery channel.** The file is titled
> `Email - AppraisalArdur - Outlook (1).pdf` and was produced by PDFium — the
> Chrome/Outlook print-to-PDF engine. Someone printed the report from a browser preview,
> which flattened the text. The native TOTAL export is normally a real digital PDF.
> **Action item #1 in §9 is to obtain a native export before building anything.**

### 1.2 What the current pipeline produced

```
run_extraction("3.6/Email - AppraisalArdur - Outlook (1).pdf")   # no XML
```

| Extractor | Fields found | Why |
|---|---|---|
| `acroform` | **0** | no embedded widgets |
| `xml` | **0** | no XML supplied |
| `pdf_digital` | **0** | `is_digital_page()` needs ≥30 words; every page has 0 |
| `checkbox` | **0** | every Yes/No on the form is invisible |
| `grid` | **0** | the entire comparable sales grid is invisible |
| `sweep` | **0** | text-based |
| `pdf_scanned` (OCR) | 52 raw → **31 after plausibility** | the only path that produced anything |

**31 of 279 schema fields = 11.1% populated.** Runtime 73.5s.

Auditing those 31 against visual ground truth: **13 correct, 4 partial, 14 wrong.**
→ **42% precision on what it emitted, 4.7% coverage of the schema.**

Three of the wrong values are actively dangerous:

| Field | Extracted | Truth | Page |
|---|---|---|---|
| `property_address` | `'Structure'` | 1465 Turner Rd NE, Rome GA 30165 | p2 |
| `year_built` | `'Detached'` | 1979 | p7 |
| `has_adu` | `'1'` | **0** (it read the adjacent label "Units Excluding ADUs: 1") | p2 |
| `borrower_name` | `'ReferenceID 4208000694'` | Jessica & Robert Talmage | p2 (footer artifact) |
| `lender_name` | `'ReferenceID 4208000694'` | Homeowners Financial Group USA, LLC | p2 (footer artifact) |
| `appraiser_company_address` | `'4800 N Scottdale Rd,'` | 115 Gardenia Trl — **it grabbed the lender's address** | p2 |

Two things worked and should be preserved:
- **`plausibility` suppressed 21 junk fields** (`gla='Level 1'`, `condition_rating='As Is'`, …).
- **Intake did not block** — but only via the rule-4 fallback at
  [`intake.py:247`](../app/pipeline/intake.py#L247) (*"a long PDF with no distinguishing
  markers is still the appraisal"*). `uad_count` was **0** because the marker test reads text.

### 1.3 OCR destroys checkbox state

Raw tesseract on the page-2 Yes/No block:

```
Planned Unit Development (PUD)     Oo Mm
Condominium                        om
Cooperative                        mee
Condop                             O vy
Property on Native American Lands  oO [Ivf
Homeowner Responsible for ...      KA oO
```

Every one of those is a boolean the checklist asks about. None is recoverable.
OCR also misread the APN `J08 018J08 018` → `J08 018508 018`.

### 1.4 The 8-page cap

Both [`pdf_digital.py:222`](../app/extraction/pdf_digital.py#L222) and
[`pdf_scanned.py:97`](../app/extraction/pdf_scanned.py#L97) default to `max_pages: int = 8`
— correct for a 1004, catastrophic for a 40-page URAR:

| Section | Page | Reachable today? |
|---|---|---|
| Sketch + area calcs | 6–7 | ✅ |
| Unit Interior | 8–12 | partial |
| Outbuilding / Vehicle Storage | 13–14 | ❌ |
| **Highest and Best Use** | **15** | ❌ |
| **Market / trends / DOM** | **15–18** | ❌ |
| **Listing history + Sales Contract** | **19** | ❌ |
| **Prior Sale & Transfer History** | 19–20 | ❌ |
| **Sales Comparison Approach (6 comps)** | **21–24** | ❌ |
| **Reconciliation** | **26** | ❌ |
| Adjustment support (TrueTracts) | 27–35 | ❌ |
| **Certifications + Signature** | **38–40** | ❌ |

**The entire valuation is invisible.** This one is a config change, not a rewrite, and it
is mandatory regardless of everything else in this document.

---

## 2. The core architectural insight

We currently use **deterministic code for perception** and an **LLM for checking**.
That is backwards.

| Layer | Nature of the problem | Right tool |
|---|---|---|
| **Extraction** | perception — messy, visual, layout-dependent | **LLM / vision** |
| **Verification** | arithmetic — crisp, closed-form | **deterministic code** |
| **Judgment** | policy — genuinely interpretive | **LLM judge** (already in place) |

> **This does not touch the "LLM judges, no hardcode" doctrine.** The arithmetic layer in
> §5 verifies that *extraction faithfully reproduces the page* — not whether the appraiser
> complied. Compliance stays with the judge. Two different questions; the deterministic
> layer never answers the second.

---

## 3. Target architecture

```
                    ┌──────────────────────────┐
                    │  0. STRUCTURAL PROBE      │  fitz: chars/fonts/drawings/images
                    │     → document_class      │  digital | flattened | scanned
                    │     → uad_version         │  2.6 | 3.6
                    └────────────┬─────────────┘
                                 │  routes on (uad_version, document_class)
              ┌──────────────────┴──────────────────┐
              ▼                                     ▼
   ┌────────────────────┐              ┌──────────────────────────┐
   │  UAD 2.6 PATH      │              │  UAD 3.6 PATH  (new)     │
   │  UNTOUCHED         │              │                          │
   │  xml → digital →   │              │  1. PAGE MAP             │
   │  grid → checkbox   │              │  2. VISION EXTRACT       │
   └─────────┬──────────┘              │  3. GRID VISION (6 comp) │
             │                         └────────────┬─────────────┘
             │                                      │
             └──────────────┬───────────────────────┘
                            ▼
              ┌──────────────────────────────┐
              │  4. VERIFY  (deterministic)  │  ← the precision engine
              │     arithmetic checksums     │
              │     fail → re-extract region │
              └──────────────┬───────────────┘
                             ▼
              ┌──────────────────────────────┐
              │  5. SHARED DOWNSTREAM         │  plausibility, normalizer,
              │     (unchanged)               │  back-locator, merge,
              │                               │  judge, severity gate
              └──────────────────────────────┘
```

**The fork is at the extraction layer only.** Everything downstream — merge, plausibility,
normalizer, back-locator, judge, severity gate, persistence, reviewer UI — is shared and
version-agnostic.

### 3.1 The seam already exists

[`app/registry/__init__.py:3`](../app/registry/__init__.py#L3):

> *"Keyed by (uad_version, form_type, field_id) **from day one so UAD 2.6 and 3.6 orders
> coexist without a rekey** through the whole stack."*

[`registry/loader.py`](../app/registry/loader.py) already takes `uad_version` on
`known_form()` and `is_absent_field()`. But `config/field_registry/` contains **only
`uad26/`** — the 3.6 side is an empty socket. The architecture is right; the content is
missing.

---

## 4. Build phases

### Phase 0 — Unblock (hours, do first)

| # | Change | File |
|---|---|---|
| 0.1 | Raise `max_pages` from 8; make it config, not a literal | `pdf_digital.py:222`, `pdf_scanned.py:97` |
| 0.2 | Add UAD 3.6 markers to `_UAD_MARKERS` | `pipeline/intake.py:37` |
| 0.3 | Add PDFium + TOTAL entries to `vendor_detect` | `config/template_positions.yaml` |
| 0.4 | Add `Source.VISION = "vision"` at confidence **0.93** | `extraction/result.py` |

Confidence 0.93 sits **above `pdf_digital` (0.92)** and **below `XML` (0.97)**, so
`_merge_field`'s XML-priority rule keeps working untouched and vision correctly loses to
3.6 XML when it eventually arrives.

### Phase 1 — Structural probe & page map

**New file: `app/extraction/page_map.py`**

```python
"""Structural page profiling — a table of contents without reading a word."""
from dataclasses import dataclass

@dataclass
class PageProfile:
    page: int
    chars: int
    fonts: int
    images: int
    drawings: int
    kind: str            # "text_dense" | "photo_grid" | "mixed" | "blank"
    section: str | None = None


def profile(pdf_path) -> list[PageProfile]:
    import fitz
    doc = fitz.open(str(pdf_path))
    out = []
    for i, p in enumerate(doc):
        chars = len(p.get_text().strip())
        imgs, draws = len(p.get_images()), len(p.get_drawings())
        if imgs >= 15 and draws < 600:      kind = "photo_grid"
        elif imgs == 0 and draws >= 600:    kind = "text_dense"
        elif draws < 100 and imgs == 0:     kind = "blank"
        else:                                kind = "mixed"
        out.append(PageProfile(i + 1, chars, len(p.get_fonts()), imgs, draws, kind))
    doc.close()
    return out


def classify_document(profiles) -> str:
    """digital | flattened | scanned — decides the whole extraction strategy."""
    total_chars = sum(p.chars for p in profiles)
    total_fonts = sum(p.fonts for p in profiles)
    total_draws = sum(p.drawings for p in profiles)
    if total_chars > 200 * len(profiles):
        return "digital"
    if total_fonts == 0 and total_draws > 500 * len(profiles):
        return "flattened"          # ← our sample
    return "scanned"
```

Measured signatures on the sample:

| Signature | Meaning | Pages |
|---|---|---|
| 0 imgs, high drawings | dense text/table | 2, 3, 20, 22, 24, 38, 39 |
| many imgs, low drawings | photo sheet — **skip** | 10, 11, 12, 25–37 |
| few imgs, high drawings | mixed data + exhibit | 7, 9, 15, 19, 21, 23 |

**This is the cost-control lever.** It drops ~20 pure-photo pages from the vision budget
before a single call is made.

### Phase 2 — Vision extraction

**New file: `app/extraction/vision_extractor.py`**

Four rules produce the precision. Drop any one and it collapses.

| Rule | What | Why |
|---|---|---|
| **R1** | Schema-constrained output via `output_config.format` | shape is guaranteed, not hoped for |
| **R2** | Page-scoped — one section per call, never the whole doc | narrow scope → fewer hallucinations |
| **R3** | Abstention required — `null` is a first-class answer | kills `property_address='Structure'` |
| **R4** | Provenance mandatory — page + verbatim `source_text` | auditable + click-to-scroll |

```python
"""Vision extraction — the LLM TRANSCRIBES, never judges."""
import base64, fitz
from anthropic import Anthropic
from app.extraction.result import ExtractedField, ExtractedFieldSet, Source

RENDER_DPI = 150          # see §6.1 for the DPI/cost tradeoff
MODEL      = "claude-opus-5"

client = Anthropic()

SYSTEM = """You transcribe appraisal report pages into structured JSON.

RULES — violating any of these is a defect:
1. Transcribe ONLY what is visibly printed. Never infer, complete, or normalize.
2. If a field is not visible on this page, emit null. Do NOT guess.
   An honest null is correct; a plausible guess is a defect.
3. For every non-null value also emit `source_text` (the exact characters as
   printed) and `label_text` (the printed label you matched it to).
4. Checkboxes: report the CHECKED option by name. If none is marked, null.
5. Never output an opinion, verdict, or assessment. Values only."""


def _render(pdf_path: str, page_no: int) -> str:
    doc = fitz.open(pdf_path)
    png = doc[page_no - 1].get_pixmap(dpi=RENDER_DPI).tobytes("png")
    doc.close()
    return base64.b64encode(png).decode()


def extract_section(pdf_path, page_no, section_name, json_schema) -> dict:
    resp = client.messages.parse(
        model=MODEL,
        max_tokens=4000,
        system=[{"type": "text", "text": SYSTEM,
                 "cache_control": {"type": "ephemeral"}}],   # §6.3
        output_config={
            "format": {"type": "json_schema", "schema": json_schema},
            "effort": "medium",          # NOT temperature — see §4.2.1
        },
        messages=[{"role": "user", "content": [
            {"type": "image", "source": {"type": "base64",
             "media_type": "image/png", "data": _render(pdf_path, page_no)}},
            {"type": "text",
             "text": f"Page {page_no}. Section: {section_name}. "
                     f"Emit null for anything not visible on this page."},
        ]}],
    )
    return resp.content[0].text          # already parsed against the schema
```

#### 4.2.1 ⚠️ `temperature` is REMOVED on Claude Opus 5 / Sonnet 5

Sending `temperature`, `top_p`, or `top_k` to `claude-opus-5` or `claude-sonnet-5`
returns **HTTP 400**. Determinism comes from three other levers:

1. **`output_config.format`** — a JSON schema constrains the output shape absolutely.
2. **`output_config.effort`** — `"low"`/`"medium"` scope the work tightly.
3. **A tight, literal prompt** — these models follow instructions literally.

Also note on Opus 5: **thinking is ON by default** (omitting `thinking` runs adaptive).
`thinking={"type": "disabled"}` is permitted only at `effort` **`high` or below** — pairing
it with `xhigh`/`max` is a 400. `max_tokens` caps thinking **plus** response text, so size
it with headroom.

#### 4.2.2 Structured-output schema limits — design around these

| Supported | **Not supported** |
|---|---|
| object, array, string, integer, number, boolean, null | recursive schemas |
| `enum`, `const`, `anyOf`, `allOf`, `$ref`/`$defs` | `minimum` / `maximum` / `multipleOf` |
| formats: `date`, `date-time`, `uri`, `uuid`, … | `minLength` / `maxLength` |
| `additionalProperties: false` (**required on every object**) | `additionalProperties` ≠ `false` |

Enforce numeric ranges in `verify.py` (§5), not in the schema.

New schemas incur a **one-time compilation cost on first use**, then hit a 24-hour cache.
Our schemas are stable, so this is a non-issue after warm-up.

### Phase 3 — Grid extraction (the hard part)

**New file: `app/extraction/grid_vision.py`**

The 3.6 grid holds **6 comparables** across **two page-pairs** (comps 1–3 on p21+p22,
comps 4–6 on p23+p24), with value and adjustment paired inside one cell.

```python
COMP_SCHEMA = {
  "type": "object",
  "additionalProperties": False,
  "required": ["comp_number", "address", "proximity_miles", "net_adjustment_total"],
  "properties": {
    "comp_number":      {"type": "integer"},
    "address":          {"type": "string"},
    "proximity_miles":  {"type": ["number", "null"]},
    "data_source":      {"type": ["string", "null"]},
    "listing_status":   {"type": ["string", "null"]},
    "sale_price":       {"type": ["integer", "null"]},
    "contract_date":    {"type": ["string", "null"]},
    "sale_date":        {"type": ["string", "null"]},
    "sales_concessions": {"$ref": "#/$defs/pair"},
    "site_size":        {"$ref": "#/$defs/pair"},
    "gla":              {"$ref": "#/$defs/pair"},
    "bedrooms":         {"$ref": "#/$defs/pair"},
    "baths_full_half":  {"$ref": "#/$defs/pair"},
    "year_built":       {"$ref": "#/$defs/pair"},
    "condition":        {"$ref": "#/$defs/pair"},
    "vehicle_storage":  {"$ref": "#/$defs/pair"},
    "outbuilding":      {"$ref": "#/$defs/pair"},
    "outdoor_living":   {"$ref": "#/$defs/pair"},
    "net_adjustment_total": {"type": "integer"},
    "adjusted_price":   {"type": ["integer", "null"]},
    "comparable_weight": {"type": ["string", "null"]},
  },
  "$defs": {"pair": {
      "type": "object", "additionalProperties": False,
      "required": ["value", "adjustment"],
      "properties": {"value": {"type": ["string", "null"]},
                     "adjustment": {"type": ["integer", "null"]}}}},
}
```

**Three defenses, each earned from a specific observed failure:**

1. **Extract by column, not by row.** One call per comparable, sending both pages of the
   pair. A misread cannot silently shift a value one column right.
2. **Value and adjustment are one object.** `{"value": "$5,350", "adjustment": 0}`.
   This is exactly the finding the flat-text grid extractor can never surface — the
   audit's biggest catch (5 comps with real concessions, all adjusted **$0**).
3. **Never emit a partial comparable set.** Mark the section `incomplete` and refuse to
   run bracketing/range checks until all 6 are in hand.

> **Why defense 3 exists:** during the manual audit, reading only p21–22 produced a
> confident false positive — "the $310,000 opinion sits below the adjusted range
> ($311,000 min)". Page 23 then revealed comps 4–6, the true range was
> $277,400–$341,700, and the finding evaporated. **Partial coverage does not degrade
> gracefully; it manufactures findings.**

**Known rendering defect:** on **both** p22 and p24 the Outbuilding band header renders as
overlapping garbled glyphs (`Outbuilding (ADU and vehicle storage are not included in
Fi▮▮▯▮▯Com▮▯▮▯▯▮…`). It is systematic in this TOTAL template. Add a schema note telling the
transcriber to read the row **labels**, not the band header.

### Phase 4 — Deterministic verification (build this FIRST)

**New file: `app/extraction/verify.py`**

Appraisal reports are full of **closed-form arithmetic**. Every instance is a free
correctness oracle. This is the single highest-leverage component and it needs no LLM.

```python
"""Self-verifying checksums. These test whether EXTRACTION is faithful to the
page — NOT whether the appraiser complied. Compliance belongs to the judge."""

def verify_comp_column(comp: dict) -> list[str]:
    errs = []
    lines = [v["adjustment"] for k, v in comp.items()
             if isinstance(v, dict) and v.get("adjustment") is not None]
    net = comp.get("net_adjustment_total")
    if net is not None and lines and abs(sum(lines) - net) > 1:
        errs.append(f"net_adj {net} != sum(lines) {sum(lines)} — re-extract column")
    sale, adj = comp.get("sale_price"), comp.get("adjusted_price")
    if None not in (sale, net, adj) and abs(sale + net - adj) > 1:
        errs.append(f"adjusted {adj} != sale {sale} + net {net} — re-extract column")
    return errs


def verify_area(sketch: dict, interior: dict) -> list[str]:
    errs = []
    calc = sum(sketch.get("living_area_calcs", []))
    if abs(calc - sketch["total_living_area"]) > 2:
        errs.append("sketch line items don't sum to total")
    if sketch["total_living_area"] != interior["finished_above_grade"]:
        errs.append("sketch total != interior finished above grade")
    return errs


def verify_rooms(room_summary: dict, totals: dict) -> list[str]:
    errs = []
    if room_summary.get("Bedroom") != totals.get("total_bedrooms"):
        errs.append("room summary bedrooms != total bedrooms")
    if room_summary.get("Bath - Full") != totals.get("total_bathrooms_full"):
        errs.append("room summary baths != total baths full")
    return errs
```

**Verified against the sample — all three close:**

| Check | Arithmetic | Result |
|---|---|---|
| Comp #1 net | `-23,800 +9,000 +11,600 +5,000 +5,000 -12,000 +3,500 = -1,700` | = printed net ✅ |
| Comp #1 adjusted | `320,000 - 1,700 = 318,300` | = printed adjusted ✅ |
| Sketch total | `128.38 + 1018.58 + 892.53 + 97.87 = 2,137.36 → 2,137` | = p8 finished above grade ✅ |
| Room counts | p8 summary `4-Bedroom, 3-Bath Full` | = `Total Bedrooms 4 / Baths-Full 3` ✅ |

**Retry loop:**

```python
for attempt in range(3):
    comp = extract_comp_column(pdf, pages, comp_no)
    if not verify_comp_column(comp):
        return comp, "verified"
    # escalate: bump DPI 150→200, then re-prompt stating the arithmetic error
return comp, "unverified"      # → REVIEW card, never a silent PASS
```

When the arithmetic closes, extraction is almost certainly right. When it doesn't, you
re-extract rather than ship. **This converts unverifiable LLM output into verifiable
output** — the whole difference between "LLM extraction" and "LLM extraction you can trust."

### Phase 5 — Routing (keep 2.6 sealed)

```python
# app/extraction/merge.py
def run_extraction(appraisal_pdf, xml_path=None, ..., uad_version="2.6"):
    profiles  = page_map.profile(appraisal_pdf)
    doc_class = page_map.classify_document(profiles)

    if uad_version == "3.6":
        return run_extraction_36(appraisal_pdf, profiles, doc_class, ...)

    # ── everything below is the existing 2.6 path, byte-for-byte unchanged ──
```

`uad_version` is detected at intake. The **"Fannie Mae | Freddie Mac / September 2024"
footer is on all 40 pages** and is a reliable signal, as is the 3.6 section vocabulary.

### Phase 6 — Field registry & schemas

Populate `config/field_registry/uad36/forms.yaml` and
`config/vision_sections/uad36/*.yaml` (one schema per section).

**3.6 section vocabulary** (vs the 2.6 `subject / neighborhood / site / improvements / …`):

Assignment Information · Contact Information · Subject Property · Ownership Rights ·
Legal Description · Site · Site Influence · View · Site Features · Utilities · Sketch ·
Dwelling Exterior · Quality and Condition · Mechanical System Details · Unit Interior ·
Kitchen and Bathroom Details · Interior Features · Outbuilding · Vehicle Storage ·
Subject Property Amenities · Overall Quality and Condition · Highest and Best Use ·
Market · Housing Trends · Market Exhibits · Subject Listing Information · Sales Contract ·
Financial Sales Concessions · Prior Sale and Transfer History · Sales Comparison
Approach · Reconciliation · Supplemental Information · Certifications · Signature

Roughly **60–70% of canonical names carry over** by meaning (`appraised_value`,
`contract_price`, `year_built`, …). The rest are new — see §8.

### Phase 7 — Rebind the checklist

90 numbered items via the existing section-scoped LLM binder + compile gate.

> ⚠️ **Two hard prerequisites.**
>
> 1. **The checklist CSV must be cleaned first** (§8.2). Do not compile an inverted
>    item 70 into a bundle.
> 2. **Compile to a NEW bundle hash under a separate key.** The active
>    `compiled/EQUITYSOLUTIONS/96b595e6f127ba4f.yaml` (134 items, `status: active`) holds
>    ~46 hand-tuned bindings that exist **only there** and are not regenerable. A keyless
>    `--force` recompile destroys them. **Never recompile over the active 2.6 bundle.**

---

## 5. Effort sizing

| Tier | Work | Size |
|---|---|---|
| 0 | max_pages, markers, vendor detect, `Source.VISION` | hours |
| 1 | `page_map.py` + `verify.py` (no LLM, no API key needed) | small |
| 2 | 3.6 field schema + section map (~70 fields, ~20 genuinely new) | **largest single item** |
| 3 | `grid_vision.py` — 6 comps, page-pairs, paired cells | contained rewrite |
| 4 | Checklist rebind (mechanical, once CSV is clean) | medium |
| 5 | 3.6 XML extractor sibling — **defer until XML actually arrives** | later |

**Do not try to make one extractor serve both forms.** They share a name and almost
nothing else: the 2.6 extractor assumes a fixed grid, 3 comps, content in the first 8
pages, and a MISMO 2.6 spine. All four are false for 3.6.

---

## 6. Cost model

> **Pricing source:** Anthropic first-party API rates, cached 2026-06-24.
> Re-verify before committing to a budget — WebFetch
> `https://platform.claude.com/docs/en/pricing.md`.

### 6.1 Image token math

```
tokens ≈ (width_px × height_px) / 750
```

US Letter (8.5" × 11") at various render DPI. Opus 5 and Sonnet 5 are in the
**high-resolution tier** (max 2576px long edge, ~4784 tokens/image cap); Haiku 4.5 is in
the older 1568px tier and downsamples.

| DPI | Pixels | Opus 5 / Sonnet 5 tokens | Haiku 4.5 tokens (after downscale) |
|---:|---|---:|---:|
| 110 | 935 × 1210 | 1,508 | 1,508 |
| 130 | 1105 × 1430 | 2,107 | 2,107 |
| **150** | **1275 × 1650** | **2,805** | 2,534 |
| 200 | 1700 × 2200 | 4,784 (capped) | 2,534 |

**150 DPI is the recommended default** — legible for dense grid cells, comfortably under
the token cap, and the resolution used successfully in the manual audit. Drop to 110 DPI
for simple label-value sections to save ~46% of image tokens; escalate to 200 DPI only as
a retry step when a checksum fails.

### 6.2 Per-order call budget

From the page map of the sample (40 pages → **19 pages worth extracting**, ~20 pure-photo
pages skipped):

| Pass | Calls | Images/call | Input tokens/call | Output/call |
|---|---:|---:|---:|---:|
| **A — sections** (p1,2,3,6,7,8,9,13,14,15,16,19,20,26,40) | 15 | 1 | 2,805 + ~1,000 = **3,805** | ~500 |
| **B — grid** (6 comps × page-pair) | 6 | 2 | 5,610 + ~1,200 = **6,810** | ~700 |

- Pass A input: `15 × 3,805 = 57,075` · output `15 × 500 = 7,500`
- Pass B input: `6 × 6,810 = 40,860` · output `6 × 700 = 4,200`
- **Totals: 97,935 input · 11,700 output**
- **Retry allowance: +15%** (checksum-triggered re-extraction)

### 6.3 Cost per order — extraction only

| Model | $/1M in | $/1M out | Base | **+15% retries** |
|---|---:|---:|---:|---:|
| **Claude Opus 5** | $5.00 | $25.00 | $0.782 | **$0.90** |
| **Claude Sonnet 5** (intro, thru 2026-08-31) | $2.00 | $10.00 | $0.313 | **$0.36** |
| Claude Sonnet 5 (standard) | $3.00 | $15.00 | $0.469 | **$0.54** |
| Claude Haiku 4.5 | $1.00 | $5.00 | $0.149 | **$0.17** |

> ⚠️ **Haiku 4.5 on the 6-comp grid is not recommended.** The grid is the densest,
> highest-stakes region and the one where a column shift is most damaging. See §6.6 for
> the tiered assignment that captures most of the savings without that risk.

### 6.4 Cost per order — including the checklist judge

The judge layer already exists; this is for total-cost-of-order planning. Assume ~15
section-batched judge calls, ~3,000 input / ~800 output each (45,000 in / 12,000 out).

| Model | Extraction | Judge | **Total per order** |
|---|---:|---:|---:|
| Claude Opus 5 | $0.90 | $0.53 | **$1.43** |
| Claude Sonnet 5 (intro) | $0.36 | $0.21 | **$0.57** |
| Claude Sonnet 5 (standard) | $0.54 | $0.32 | **$0.86** |

### 6.5 Monthly projections

| Volume | Opus 5 | Sonnet 5 (intro) | Sonnet 5 (std) |
|---:|---:|---:|---:|
| 100 orders | $143 | $57 | $86 |
| 1,000 orders | $1,430 | $570 | $860 |
| 10,000 orders | $14,300 | $5,700 | $8,600 |
| 50,000 orders | $71,500 | $28,500 | $43,000 |

### 6.6 Cost levers, ranked

| # | Lever | Saving | Notes |
|---|---|---:|---|
| **1** | **Message Batches API** | **−50%** | QC is inherently non-latency-sensitive. This is the single biggest lever and costs nothing but a queue. First-party API only. |
| **2** | **Page map skips photo pages** | −50% | Already in the model above (19 of 40 pages). Without it, double every figure. |
| **3** | **Tiered model assignment** | −30–40% | Sonnet 5 for label-value sections; **Opus 5 for the grid + reconciliation**. |
| **4** | **Prompt caching on the system prompt** | −5–15% | Min cacheable prefix: **512 tokens on Opus 5**, **1024 on Sonnet 5**. Images dominate (74% of input), so the ceiling is modest. |
| **5** | **110 DPI for simple sections** | −20% | Keep 150 DPI for grid/sketch; escalate to 200 DPI only on checksum failure. |
| **6** | **Fewer output tokens** | −5% | Tight schemas; avoid free-text fields. |

**Batch + page-map + tiered models stacked:**

| Model strategy | Per order | 1,000/mo | 10,000/mo |
|---|---:|---:|---:|
| Opus 5 everywhere, batched | **$0.72** | $720 | $7,200 |
| Tiered (Sonnet sections / Opus grid), batched | **~$0.40** | ~$400 | ~$4,000 |
| Sonnet 5 everywhere, batched, intro pricing | **$0.29** | $290 | $2,900 |

### 6.7 ⚠️ Re-baseline before budgeting

**Do not commit to these numbers.** They are an engineering estimate from one document.
Before signing off on a budget, measure with the real API:

```python
from anthropic import Anthropic
client = Anthropic()

n = client.messages.count_tokens(
    model="claude-opus-5",
    messages=[{"role": "user", "content": [
        {"type": "image", "source": {"type": "base64",
         "media_type": "image/png", "data": page_b64}},
        {"type": "text", "text": prompt},
    ]}],
).input_tokens
```

Run this over all 19 pages of 3 real orders and multiply by live pricing. Output tokens
must be measured from real responses (`response.usage.output_tokens`), not estimated.

### 6.8 Alternative considered: send the PDF directly

The Messages API accepts a whole PDF as a `document` block (base64, no beta header;
limits 32 MB / 600 pages). Our file is 15.8 MB / 40 pages, so it fits.

**Rejected as the primary path**, for three reasons:

1. **Cost** — every call re-sends all 40 pages. Page-scoped rendering sends 1–2.
2. **No page-scoping** — R2 (§4.2) is what suppresses cross-section hallucination.
3. **No skip list** — you pay for 20 photo pages on every call.

**Keep it in reserve** for genuine whole-document questions (e.g. "is an FHA case number
present anywhere?") where the page map can't localize the answer.

---

## 7. Precision techniques, ranked by impact

| # | Technique | Why it matters | Cost |
|---|---|---|---|
| **1** | **Arithmetic checksums** (`verify.py`) | Converts unverifiable output into verifiable. Biggest single win. | Low |
| **2** | **Abstention as a first-class answer** | Kills `property_address='Structure'`, `has_adu='1'` outright. | Free |
| **3** | **Schema-constrained output** (`output_config.format`) | Shape guaranteed by the API, not by parsing hope. | Free |
| **4** | **`effort` instead of `temperature`** | Determinism without a 400. | Free |
| **5** | **Provenance** (`source_text` + page + bbox) | Auditable; click-to-scroll; mismatches expose bad reads. | Low |
| **6** | **Complete-section gate** | Prevents partial-read false positives (§Phase 3). | Low |
| **7** | **Two-pass on numerics** | Re-extract money/dates independently; disagreement → REVIEW. | Medium |
| **8** | **Structural page map** | Skips 20 pages. Cost *and* precision from one move. | Low |
| **9** | **Cross-page fusion pass** | Where the real findings live. Runs *after* extraction, on facts. | Medium |

**If you build only #1 and #2 you get most of the way**, and they are the cheapest two.

### 7.1 Why cross-page fusion (#9) matters

No single page produced a finding in the audit. Every one came from **two or three pages
held against each other**:

| Finding | Pages fused |
|---|---|
| "As Is" vs contract-mandated septic repair | p1 (As Is) + p26 (defects None) + p19 (contract: seller must repair septic) + p8 (septic excavation photo) |
| Concessions unadjusted | p21/p23 ($5,350/$7,000/$10,000 → **$0** adj) + p18 (65.3% of market sales carry concessions) + p38 (definition: adjustments **must** be made) |
| Declining market | p15 (−1.5%, reconciled "in balance") + p16 (supply 3.5→5.0, DOM 45→63) + p19 (listing $350k→$330k→$310k→$300k) |

**A section-scoped extractor structurally cannot produce these.** They exist only in the
joins, which is why fusion is a separate pass over already-extracted facts.

### 7.2 The false-positive trap to encode

A naive item-91 rule ("market is declining → all time adjustments should be negative")
would flag three **correct** adjustments. Comp #1 gets **+$3,500** in a −1.5% market.

The p16 monthly matrix is cumulative-to-effective-date and **not monotonic**:
Jul −1.5%, Aug −1.1%, Sep −0.6%, Oct 0.0%, Nov **+0.6%**, Dec **+1.1%**, Jan +1.4%…

- Comp #1, Dec 2025 → `+1.1% × $320,000 = $3,520 ≈ $3,500` ✅
- Comp #2, Aug 2025 → `−1.1% × $274,500 = $(3,020) ≈ $(3,000)` ✅
- Comp #3, Jun 2025 → `≈ −1.7% × $320,000 = $(5,440) ≈ $(5,400)` ✅

**The judge needs the page-16 matrix in context, not just the headline number.**
Extract the full 36-month trend matrix as a first-class field.

---

## 8. Known gaps in the 3.6 checklist

### 8.1 Fields the 3.6 form exposes that the checklist never asks about

`Property Data Report used in lieu of Inspection` · `Appraiser Fee` ·
`Broadband Internet Available` · `Property on Native American Lands` ·
`Homeowner Responsible for Exterior Maintenance` · `Front Door Elevation` ·
`Core Heating System Below Grade` · `Attachment Type` ·
`Units Excluding ADUs` **vs** `Accessory Dwelling Units` (now two separate counts) ·
`Level and Room Detail` · per-room `Update Status` / `Time Frame` ·
per-feature `Condition Status` · `Site Influence` / `Range of View` / `Impact` triples ·
**`Comparable Weight`** · **`Reasonable Exposure Time`** · the `Search Result Metrics`
block · the adjustment-support methodology section

The checklist also still assumes **3 comps** (items 73, 81) when 3.6 delivers **6**.

### 8.2 CSV defects that MUST be fixed before binding

| Defect | Detail |
|---|---|
| **Inverted logic — item 70** | *"If under these recommended mileage, pleased esnure commentay."* Commentary is required when comps are **over** the limit. As written the rule fires backwards — and it fires on this very report (Comp #3 at **7.59 miles**). **Highest-priority fix.** |
| **10 missing IDs** | 3, 4, 25, 27, 28, 38, 39, 88, 89, 96. Confirm whether deleted or dropped. |
| **1 unnumbered item** | The HBU four-tests row (line 66) has no ID. The five "STOP and Contact Office" conditions are also unnumbered. |
| **Typos** | `exceededs`, `Phyisically`, `pleased esnure commentay` |
| **Mojibake** | `�` in FHA rows (`if �subject to�`, `subject�s heat source`, `HUD�s directive`) |
| **No polarity column** | Some items are "Yes = good" (10, 15, 20, 73), others "Yes = problem" (8, 18, 19, 29, 44, 54, 55, 56, 57, 66, 68). Nothing marks which. An LLM judge will reject on healthy answers. |
| **Compound items** | 16 (two questions), 63 (refinance AND listed) |
| **Wh-questions in a Yes/No grid** | 9 ("How are the property rights appraised?"), 95 ("How has the report been completed?") |
| **No thresholds** | 52 ("median DOM reflective of an active market?" — 63 days, yes or no?), 47/48 ("meet investor criteria" — which investor?) |

---

## 9. Validation methodology

You cannot tune what you cannot measure, and there is **no ground truth for 3.6 today**.

1. Take **3 UAD 3.6 orders** (per the standing min-three rule — never judge from fewer).
2. Vision-extract every field, page by page.
3. **Hand-verify against the rendered pages.** This is the expensive, unavoidable step.
4. Freeze as `testfiles/uad36/<order>/ground_truth.json`.
5. Score every change as **precision** (of what it emitted, how much is right) and
   **coverage** (of the schema, how much it filled) — **reported separately**.

That is exactly how "13 correct / 4 partial / 14 wrong = 42% precision, 4.7% coverage"
was produced. Without ground truth that sentence is unwriteable, and so is any claim
that a change improved anything.

**Add the checksum suite as a permanent regression gate** — it needs no ground truth at
all. Any report whose comp arithmetic doesn't close is either a bad extraction or a
genuinely broken report, and both deserve a card.

---

## 10. Risks & open questions

| # | Risk | Mitigation |
|---|---|---|
| **1** | **The flattened-PDF question is upstream of everything.** If we obtain the native TOTAL export, `pdf_digital` may light up and vision becomes a *fallback* — cheaper and more deterministic. | **Ask the AMC for one native 3.6 PDF before building the vision path.** The answer changes what gets built. |
| 2 | Vision misreads on dense grid cells at 150 DPI | Checksum retry escalates to 200 DPI; unverified → REVIEW card, never silent PASS |
| 3 | Cost at volume | Batch API (−50%), page map (−50%), tiered models (−30%). Measure with `count_tokens` before committing. |
| 4 | Compiled-bundle destruction | New bundle hash under a separate key. **Never `--force` over the active 2.6 bundle.** |
| 5 | Schema-compilation latency on first use | One-time per schema, then 24h cache. Warm at deploy. |
| 6 | This plan is **design, not proven implementation** | Prototype `verify.py` against 3 orders before committing to the rest. |
| 7 | 3.6 XML arriving mid-build (MISMO v3.6, not 2.6) | `Source.VISION` at 0.93 already loses to `Source.XML` at 0.97 — the merge absorbs it with no rework |

---

## 11. Where to start Monday

1. **Get the native PDF.** One email. It may delete the hardest problem in this document.
2. **`page_map.py` + `verify.py`.** Small, deterministic, no LLM, no API key. They tell
   you immediately whether the rest is worth building.
3. **Raise the 8-page cap.** Until then every 3.6 run is blind to pages 9–40, where the
   entire valuation lives.
4. **Clean the checklist CSV** (§8.2) — specifically item 70's inverted logic.

---

## Appendix A — Sample document facts (ground truth)

| Field | Value | Page |
|---|---|---|
| Form | Uniform Residential Appraisal Report, Fannie/Freddie **Sept 2024** | all (footer) |
| Vendor | TOTAL by a la mode; printed via **PDFium** | metadata + footer |
| Subject | 1465 Turner Rd NE, Rome, GA 30165 (Floyd Co., Whispering Pines) | p2 |
| Assignment | Purchase · contract **$300,000** · opinion **$310,000** | p1, p19 |
| Effective / signed | 07/24/2026 · 07/27/2026 | p2, p40 |
| Appraiser | Eric Colcord, CR359036, GA, exp 07/31/2027 | p2, p37, p40 |
| Lender | Homeowners Financial Group USA, LLC | p2 |
| Improvements | Ranch, 1979, 2,137 sf, 4 BR / 3 full baths, Q4 / C4 | p7, p8, p14 |
| Site | 40,511 sf, 1 parcel, APN `J08 018J08 018`, A-R zoning, Fee Simple | p2, p3 |
| Utilities | Electric + water public; **sewer private/septic** | p3 |
| Comparables | **6** (5 settled + 1 pending), pp. 21–24 | p21–24 |
| Approaches | Sales Comparison only; Cost & Income excluded | p26 |

## Appendix B — Checksums verified on the sample

```
Comp #1 net:      -23,800 +9,000 +11,600 +5,000 +5,000 -12,000 +3,500 = -1,700  ✅
Comp #1 adjusted: 320,000 + (-1,700)                                  = 318,300 ✅
Comp #2 gross:    5,900+9,000+40,400+5,000+5,000+12,000+3,000         = 80,300
                  80,300 / 274,500                                    = 29.3%   (>25% guideline)
Comp #2 net:      50,300 / 274,500                                    = 18.3%   (>15% guideline)
Sketch:           128.38 + 1018.58 + 892.53 + 97.87 = 2,137.36 → 2,137          ✅
                  = p8 Finished Above Grade 2,137                               ✅
Rooms:            p8 "4-Bedroom, 3-Bath Full" = Total BR 4 / Baths-Full 3       ✅
```

Comps #2 (29.3% gross) and #4 (27.0% gross) breach the conventional 25% gross guideline;
#2 also breaches 15% net. Those are **judge** findings, surfaced by extraction — not
extraction errors.
