# SHALqc — Implementation Plan (v1.1.0)

**Scope:** Ground-up rebuild of the Python OCR/QC service. UAD 2.6 (fixed form layout — values change, layout doesn't). Java stays the orchestrator; this service is the extraction + rules brain.
**Timeline:** 2 days with Claude Code. RnD done; this doc is the build spec.
**Stack (locked):** FastAPI, Celery, Redis, PostgreSQL (psycopg2), PyMuPDF, pdfplumber, Camelot, Tesseract, pdf2image, OpenCV, scikit-learn, PyYAML, httpx, OpenTelemetry. LLM: 2× `openai/gpt-oss-120b` API keys (primary + fallback).

---

## 0. Non-Negotiable Principles

| #  | Principle                                                                                                                                 |
| -- | ----------------------------------------------------------------------------------------------------------------------------------------- |
| P1 | Extract once, identically, for every AMC. AMC differences live ONLY in profiles.                                                          |
| P2 | Every extracted value carries`{value, source, confidence, page, bbox}`. Never a bare value.                                             |
| P3 | XML is authoritative (0.97). PDF fills gaps. Conflicts are kept, not discarded.                                                           |
| P4 | FAIL requires high-confidence evidence. Doubt degrades to VERIFY. Low confidence can NEVER auto-FAIL.                                     |
| P5 | LLM never emits a verdict alone. It reads grounded facts (verbatim-validated) or seconds a verdict. Deterministic code renders PASS/FAIL. |
| P6 | Normalize before compare. One shared normalizer; no rule does its own string cleanup.                                                     |
| P7 | New AMC = new YAML profile + wording file. Zero engine code changes for the 80% case.                                                     |

---

## 1. Component Versioning

Every component carries its own semver, stamped into every QC report (`report.versions`) so any result is reproducible/auditable. Bump rules: MAJOR = output contract change, MINOR = behavior change, PATCH = bugfix.

| Component                               | Start version                | Version lives in                    |
| --------------------------------------- | ---------------------------- | ----------------------------------- |
| `schema` (canonical field dictionary) | `sch-1.0.0`                | `config/field_schema.yaml` header |
| `extractor.xml`                       | `xml-1.0.0`                | module`__version__`               |
| `extractor.pdf_digital`               | `pdd-1.0.0`                | module`__version__`               |
| `extractor.pdf_scanned` (OCR)         | `ocr-1.0.0`                | module`__version__`               |
| `extractor.grid` (comp grid + 1004MC) | `grd-1.0.0`                | module`__version__`               |
| `extractor.engagement`                | `eng-1.0.0`                | module`__version__`               |
| `extractor.llm_gapfill`               | `lgf-1.0.0`                | module`__version__`               |
| `normalizer` (synonyms/USPS/units)    | `nrm-1.0.0`                | `config/normalizer.yaml` header   |
| `rule_library`                        | `rul-1.0.0`                | `app/rules/__init__.py`           |
| Each individual rule                    | `rule_version: 1` per rule | rule registration decorator         |
| `amc_profile.<code>`                  | `prof-<code>-1.0.0`        | each profile YAML header            |
| `llm_verify` pass                     | `lvf-1.0.0`                | module`__version__`               |
| `confidence_router`                   | `crt-1.0.0`                | `config/routing.yaml` header      |
| `report_builder` (reviewer output)    | `rpt-1.0.0`                | module`__version__`               |
| API contract                            | `api-1.0.0`                | `/health` response                |

A run's fingerprint = hash of all versions + document content hash. Same fingerprint ⇒ identical output guaranteed (LLM calls cached by content hash in Redis).

---

## 2. Folder Structure

```
shalqc/
├── app/
│   ├── main.py                    # FastAPI app, auth middleware (X-API-Key), OTel
│   ├── api/
│   │   ├── qc.py                  # /qc/process /qc/submit /qc/job /qc/progress
│   │   ├── admin.py               # /schema/* /qc/rules /routing/config /amc/profiles
│   │   ├── corrections.py         # /corrections*
│   │   └── health.py              # /live /health /baseline/*
│   ├── worker/
│   │   ├── celery_app.py
│   │   └── tasks.py               # run_qc(order) — the single pipeline task
│   ├── pipeline/
│   │   ├── orchestrator.py        # intake → extract → normalize → rules → report
│   │   ├── intake.py              # doc classification, order assembly, G-0 gate
│   │   └── progress.py            # Redis-backed progress tokens
│   ├── extraction/
│   │   ├── schema.py              # loads field_schema.yaml → FieldDef registry
│   │   ├── result.py              # ExtractedField{value,source,confidence,page,bbox,conflicts[]}
│   │   ├── xml_extractor.py       # MISMO 2.6 → canonical fields (conf 0.97)
│   │   ├── pdf_digital.py         # PyMuPDF word maps, label-proximity (0.85–0.92)
│   │   ├── pdf_scanned.py         # pdf2image 300dpi → Tesseract psm6 (0.80)
│   │   ├── grid_extractor.py      # comp grid + 1004MC: pdfplumber + Camelot, arbitrated
│   │   ├── checkbox.py            # drawing-layer X-marks + OpenCV fill density
│   │   ├── engagement.py          # order form label regex (0.92)
│   │   ├── llm_gapfill.py         # LLM fills blanks; verbatim-validated or discarded
│   │   ├── plausibility.py        # rejects garbage (email='Freddie', 46x adjustments)
│   │   └── merge.py               # confidence merge + XML overlay + conflict retention
│   ├── normalize/
│   │   ├── normalizer.py          # THE one comparison-prep function
│   │   └── tables/                # loaded from config/normalizer.yaml
│   ├── rules/
│   │   ├── registry.py            # @rule decorator: id, checklist_no, section, version, needs[]
│   │   ├── verdict.py             # Verdict{status, evidence[], message_key, confidence}
│   │   ├── deterministic/         # value-compare rules (subject.py, contract.py, site.py,
│   │   │                          #   improvements.py, sca.py, reconciliation.py, signature.py,
│   │   │                          #   addendum_1004mc.py, cross_document.py, prior_sales.py)
│   │   ├── llm_judged/            # narrative rules (canned-vs-specific, substantive-vs-pointer)
│   │   └── custom/                # per-AMC custom rules: custom/<amc_code>/*.py
│   ├── llm/
│   │   ├── client.py              # 2-key failover, Redis content-hash cache, telemetry
│   │   │                          #   (cache hits STILL emit LLMCall{cached:true})
│   │   ├── grounding.py           # verbatim-quote validation against page text
│   │   └── verify_pass.py         # post-verdict cross-check; can only ADD VERIFY
│   ├── profiles/
│   │   ├── loader.py              # profile resolution: manifest amc_code → YAML
│   │   ├── model.py               # AmcProfile{rules_on, severity_map, thresholds, wording}
│   │   └── engine_binding.py      # applies profile to registry before rule run
│   ├── routing/
│   │   └── router.py              # confidence gates: auto-accept / verify / reject per field
│   ├── report/
│   │   ├── builder.py             # findings → reviewer JSON for Java (grouped, plain words)
│   │   └── wording.py             # renders AMC reject_as templates with values
│   └── persistence/
│       ├── models.py              # Order, Run, ExtractedFieldRow, Finding, Correction
│       └── repo.py
├── config/
│   ├── field_schema.yaml          # sch-x.y.z — every UAD 2.6 field, ~600 entries
│   ├── normalizer.yaml            # nrm-x.y.z — USPS suffixes, enums, units, booleans
│   ├── routing.yaml               # crt-x.y.z — per-field confidence thresholds
│   └── amc_profiles/
│       ├── _base.yaml             # defaults every AMC inherits
│       ├── AMC001.yaml            # the current AMC — "hardcoded" = it's the only file today
│       └── AMC001.wording.yaml    # their verbatim reject_as templates (from checklist)
├── alembic/                       # migrations
├── tests/
│   ├── fixtures/                  # ESAZ-0002909, ESTX-0007568, ESFL-0027719 golden files
│   ├── test_extraction/  test_normalizer/  test_rules/  test_profiles/
│   └── golden/                    # expected findings per fixture — regression gate
└── requirements.txt
```

---

## 3. Extraction — Full Detail

### 3.1 Intake & classification (`pipeline/intake.py`)

1. Unzip package. Manifest (if present) declares `amc_code`, `order_id`, `revision_flag`. No manifest ⇒ `amc_code` from engagement-letter letterhead match, else profile `_base`.
2. Classify each file: appraisal PDF (36-ish pages, UAD form markers), MISMO XML, engagement letter, purchase contract (purchase only).
3. **G-0 gate:** missing appraisal PDF or unparseable XML on an XML-expected order ⇒ order status `BLOCKED` / HOLD, non-overridable. Missing engagement ⇒ proceed, cross-document rules resolve `NOT_APPLICABLE` with a HOLD finding "engagement letter not provided".
4. Folder boundary = order boundary (never filename stem — known prior failure).

### 3.2 Extraction order & merge (`extraction/merge.py`)

| Step | Extractor           | Conf       | Notes                                                                                                                                                                                                                                          |
| ---- | ------------------- | ---------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 1    | XML (MISMO 2.6)     | 0.97       | Parse ALL fields first. This is the spine.                                                                                                                                                                                                     |
| 2    | PDF digital pages   | 0.85–0.92 | PyMuPDF word maps; per page: ≥30 words = digital. Label-proximity lookup against schema anchors.                                                                                                                                              |
| 3    | PDF scanned pages   | 0.80       | <30 words ⇒ 300dpi grayscale → Tesseract`--psm 6 --oem 3`, conf floor 30.                                                                                                                                                                  |
| 4    | Grid extractor      | 0.88–0.90 | pdfplumber bands + Camelot lattice run**sequentially, not parallel** (kills the recursion crash). Two reads arbitrated: agree ⇒ keep at 0.90; disagree ⇒ keep both, flag.                                                              |
| 5    | Checkboxes          | 0.92       | Drawing-layer X-marks first; OpenCV fill density fallback. Emit schema enum vocabulary (`Public`, `OwnerOccupied`) — never raw `True/False`.                                                                                            |
| 6    | Engagement letter   | 0.92       | Label regex over order-form text. Regex is fine HERE — it's locating labeled values, not judging rules.                                                                                                                                       |
| 7    | LLM gap-fill        | grounded   | Only fields still blank after 1–6. Batch one call per section. Returned value must appear verbatim on the page or it is discarded.                                                                                                            |
| 8    | Plausibility filter | —         | Type/range/format sanity per field (from schema). Failing values are suppressed → treated as MISSING, never passed to rules as truth.                                                                                                         |
| 9    | XML overlay         | —         | XML wins ties. A materially-disagreeing loser is kept as`conflicts[]` on the winner. Unresolved disagreements become one consolidated `XML-CONFLICT` VERIFY **after normalization** (so `Owner` vs `OwnerOccupied` never fires). |

**Concurrency rule:** max 3 workers; PDF-object-parsing extractors (Camelot, pdfplumber deep parse) never run concurrently with OCR on the same document. This is a hard lesson, not a preference.

### 3.3 Wrong-value handling (explicit conditions)

| Condition                                     | Behavior                                                                                                                                                        |
| --------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Value fails plausibility (garbage OCR)        | Suppressed → field = MISSING. Rule outcome: VERIFY "could not read X (page N)", never FAIL.                                                                    |
| Conf below field's routing threshold          | Rule may emit VERIFY only. FAIL is blocked by the router even if the comparison fails.                                                                          |
| XML vs PDF disagree after normalization       | XML value used; one VERIFY showing both values + both pages.                                                                                                    |
| Two grid extractors disagree                  | Lower conf, VERIFY with both reads.                                                                                                                             |
| LLM gap-fill value not found verbatim on page | Discarded silently; field stays MISSING.                                                                                                                        |
| Field missing but rule needs it               | Per rule config: VERIFY ("please confirm X") or NOT_APPLICABLE. FAIL only when absence is*proven* (page located, region read cleanly, value genuinely blank). |
| High conf, all sources agree, rule fails      | FAIL — the only path to FAIL.                                                                                                                                  |

---

## 4. Normalizer (nrm-1.0.0) — Fix False FAILs Here, Once

Single function `normalize(field_def, raw) → canonical`, applied to **both sides** of every comparison. Config-driven (`normalizer.yaml`), hot-reloadable via `/schema/reload`.

| Table                | Examples                                                                                                      |
| -------------------- | ------------------------------------------------------------------------------------------------------------- |
| USPS street suffixes | Mdw→Meadow, Ct→Court, St→Street, Dr→Drive, Ave→Avenue, Blvd→Boulevard, Ln→Lane (full USPS Pub 28 list) |
| Enum synonyms        | Owner↔OwnerOccupied, Under 3 mths↔UnderThreeMonths, Det.↔Detached, Conc.Slab↔Concrete Slab                |
| Boolean↔categorical | True↔Public (utilities), False↔No, Yes↔True                                                                |
| Units                | "4800 sf"→4800(sf), 0.25 ac↔10890 sf                                                                        |
| Numbers/words        | One↔1, currency strip, whole-dollar coercion                                                                 |
| Names                | case/punct/suffix (JR/SR) aware; Jaro-Winkler ≥0.90 = auto-PASS, <0.90 = never auto-FAIL, route VERIFY       |
| Dates                | any input format → ISO                                                                                       |

---

## 5. Rule Engine — And the Regex Question, Answered

**Your instinct is right and wrong in a useful way.** Regex is bad at *judgment* but the fix is not "LLM judges everything." Three tiers:

| Tier                                    | What                                                                                                                | How judged                                                                                                                                                                                                                                                                                                     | Why                                                                                                                                                                                                                                                                                            |
| --------------------------------------- | ------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| T1 — Structured checks (~75% of rules) | presence, format, equality, cross-section, cross-document on structured fields                                      | **Deterministic value comparison** on normalized canonical values. NOT regex-on-raw-text. `norm(a) == norm(b)`, `x <= y`, `abs(net)/price <= threshold`. Regex used only for format validation (census tract `\d{4}\.\d{2}`, date shapes) — a legitimate regex job.                             | 100% reproducible, auditable, instant, free. An LLM judging "does 4800 equal 4800 sf" adds cost + nondeterminism and can only be worse. Your past false FAILs weren't regex-as-judge failures — they were*missing normalization* failures. Fix the normalizer, keep deterministic verdicts. |
| T2 — Semantic/narrative checks (~15%)  | canned vs specific commentary, substantive vs pointer analysis, description quality, trend-vs-narrative consistency | **LLM classifies → deterministic maps class to verdict.** Prompt returns `{class, quote}`; quote must exist verbatim on page (grounding gate) or finding is dropped. Class → verdict mapping is code. Max severity from this tier: **VERIFY** (LLM-sourced findings never auto-FAIL an order). | This is what regex genuinely cannot do and where the LLM is the right tool.                                                                                                                                                                                                                    |
| T3 — Verify pass (100% of rules)       | second opinion behind every T1/T2 verdict                                                                           | LLM re-reads extracted values + page snippets vs the verdict. Disagreement ⇒ ADD one VERIFY. Can never flip/remove a verdict.                                                                                                                                                                                 | Catches the "both sources agree but it's still wrong" class. This is your existing catalog_verify pattern, kept.                                                                                                                                                                               |

**Rule contract (every rule):**

```
@rule(id="S-1", checklist="C", section="subject", version=1,
      needs=["property_address", "engagement.property_address"], tier=1)
def s1(ctx) -> Verdict  # status, evidence[{field,value,page,bbox}], message_key, confidence
```

`needs[]` drives auto-NOT_APPLICABLE (missing doc type) and auto-VERIFY (missing/low-conf field) *before* the rule body runs — rules never see garbage.

---

## 6. AMC Profile Layer — Hardcoded Now, Dynamic Forever

"Hardcoded" = there is exactly one profile file today (`AMC001.yaml`). The loading mechanism is fully dynamic from day one.

### 6.1 Resolution

`manifest.amc_code` → `config/amc_profiles/<code>.yaml` → deep-merge over `_base.yaml`. Unknown code ⇒ `_base` + a HOLD finding "AMC profile not found". Loaded at intake, cached in Redis, hot-reloadable.

### 6.2 Profile schema (`AMC001.yaml`)

```yaml
meta: {amc_code: AMC001, name: "...", version: prof-AMC001-1.0.0}
rules:
  default: on                       # everything in the library runs unless overridden
  off: [FHA-10]                     # rules this AMC doesn't want
  severity_overrides:               # engine emits canonical severity; profile remaps
    S-5:  {FAIL: VERIFY}            # this AMC treats neighborhood-name as soft
  thresholds:
    SCA-NET.net_adjustment_pct: 15  # another AMC: 20
    SCA-GROSS.gross_pct: 25
    S-1.name_match_jw: 0.90
  custom_rules: []                  # module names under rules/custom/AMC001/
wording_file: AMC001.wording.yaml   # reject_as templates keyed by message_key
routing_overrides: {}               # per-field confidence gates if AMC is strict/lax
output: {group_by: root_cause, tone: reviewer_plain}
```

### 6.3 Wording file

Their verbatim checklist "Reject as:" text (your YAML catalog is exactly this — it becomes `AMC001.wording.yaml` almost as-is): `message_key → template` with `{value}` placeholders. Engine produces `message_key + values`; `report/wording.py` renders the AMC's exact language. Another AMC's different phrasing = different wording file, zero code.

### 6.4 Onboarding AMC #2 and #3 (the "little changes" you asked for)

1. Copy `_base.yaml` → `AMC002.yaml`; walk their checklist; ~80% is severity/threshold/wording edits.
2. Write `AMC002.wording.yaml` from their reject language.
3. Genuinely new checks → `rules/custom/AMC002/` (auto-discovered via the same `@rule` decorator, `amc_scope="AMC002"`), OR if generally useful, promote into the shared library and just switch it `on` in their profile.
4. Regression-run their sample orders against golden expectations before go-live.
   No engine changes. Steps 1–2 are an afternoon.

---

## 7. Confidence Routing (crt-1.0.0)

`config/routing.yaml`, editable via `PUT /routing/config` (no deploy):

```yaml
defaults: {auto_accept: 0.90, review: 0.70}   # <0.70 ⇒ field unusable ⇒ MISSING
fields:
  comp_*_sale_price: {auto_accept: 0.95}      # money = stricter
  appraiser_email:   {auto_accept: 0.85}
```

Router sits between extraction and rules; enforces P4 mechanically (a rule literally cannot FAIL on a below-threshold field).

## 8. Reviewer Output — Simple Words

Java receives one JSON per run; each finding is one card:

| Field                  | Example                                                                       |
| ---------------------- | ----------------------------------------------------------------------------- |
| headline (plain words) | "Contract date is filled in, but this is a refinance"                         |
| what_we_checked        | "Refinance orders must leave the contract section blank (UAD)"                |
| what_we_found          | "Contract date 2026-07-08 found on page 17"                                   |
| evidence[]             | `{field, value, page, bbox}` per value → click-to-scroll                   |
| suggested_wording      | AMC's exact reject_as text, values filled — copy-paste ready                 |
| status / confidence    | FAIL / 0.92                                                                   |
| group                  | one card per root cause (address mismatch = ONE card, not 3 sibling findings) |

Order of cards: FAIL → HOLD → VERIFY → (PASS/NA collapsed behind a count). Grouping key = shared root field, so the reviewer sees "38 checks passed, 2 need your words, 5 to verify" — not 322 rows. Reviewer decisions post back via `/corrections` and are stored per rule per field (feeds normalizer/threshold tuning later).

## 9. API Surface (api-1.0.0)

Keep your existing contract so Java barely changes: `/live`, `/health` (now returns all component versions), `/schema/reload`, `/schema/fields`, `/qc/rules`, `/qc/process` (sync), `/qc/submit` + `/qc/job/{id}` + `/qc/progress/{token}` (async), `/corrections*`, `/validate/{document_id}`, `/routing/config` GET/PUT, `/amc/profiles` GET — plus new: `POST /amc/profiles/reload`, `GET /runs/{run_id}` (full audit dump). `X-API-Key` middleware on everything except health/docs.

## 10. LLM Subsystem

- 2 keys: primary → fallback on 429/5xx/timeout; per-key rate budget.
- Redis cache keyed by `hash(model + prompt + page_content)`, 7-day TTL. **Cache hits emit telemetry (`cached: true`)** — usage counts stay honest.
- Every response passes `grounding.py`: cited quote must be a verbatim substring of the source page. Ungrounded ⇒ dropped + logged.
- Budget per order target: ≤ 25 calls (section-batched gap-fill ~6, T2 narrative ~8, T3 verify batched ~10).

---

## 11. Two-Day Build Plan (Claude Code)

### Day 1 — Spine: intake → extraction → normalize → verdicts

| Block | Deliverable                                                                                | Done when                                                 |
| ----- | ------------------------------------------------------------------------------------------ | --------------------------------------------------------- |
| D1-1  | Repo skeleton, config loaders,`ExtractedField`, `@rule` registry, FastAPI stubs + auth | `/live`, `/health`, `/schema/fields` respond        |
| D1-2  | XML extractor + field_schema.yaml (port your existing schema — biggest reuse)             | 400+ fields from ESAZ-0002909 XML                         |
| D1-3  | PDF digital + scanned + checkbox extractors; merge + XML overlay + conflict retention      | ≥85% schema coverage on fixture; conflicts retained      |
| D1-4  | Grid extractor, sequentialized + arbitrated; plausibility filter                           | Comp prices match XML on fixture; zero recursion errors   |
| D1-5  | **Normalizer with full USPS + enum + unit + boolean tables**                         | "Mdw Ct"=="Meadow Ct"; True==Public; unit tests green |
| D1-6  | Engagement extractor; T1 rules ported (subject, contract, cross-document, site)            | ESAZ + ESTX fixtures produce zero known-false FAILs       |

### Day 2 — Rules complete, profiles, LLM, output, API

| Block | Deliverable                                                                                       | Done when                                                                      |
| ----- | ------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------ |
| D2-1  | Remaining T1 rules (improvements, SCA, reconciliation, signature, 1004MC, prior sales)            | All checklist rule_ids registered,`/qc/rules` lists them                     |
| D2-2  | Confidence router + routing.yaml + PUT endpoint                                                   | Sub-threshold field provably cannot FAIL (test)                                |
| D2-3  | LLM client (failover, cache, honest telemetry) + grounding + gap-fill                             | Ungrounded value discarded (test); cache hit logged                            |
| D2-4  | T2 narrative rules + T3 verify pass (VERIFY-only, add-only)                                       | Verify pass adds, never flips (test)                                           |
| D2-5  | Profile loader +`_base.yaml` + `AMC001.yaml` + wording renderer (port your catalog reject_as) | Severity remap + threshold override + custom-rule discovery all proven by test |
| D2-6  | Report builder (grouped cards, plain words) + Celery async + progress + persistence + corrections | Full`/qc/process` on both fixtures; golden-file regression green             |

**Cut list if time runs out (in cut order):** T3 verify pass → corrections stats endpoint → baseline endpoints. **Never cut:** normalizer, router, profile layer — those are the product.

## 12. Definition of Done

1. Both fixture orders end-to-end with zero known-false FAILs (address suffix, enum, unit classes all normalized away).
2. Every finding traceable: field → value → source → confidence → page/bbox → rule id + version → profile version.
3. Flipping one severity line in `AMC001.yaml` changes output with no restart.
4. A below-threshold field cannot produce FAIL (enforced by router, covered by test).
5. `report.versions` present in every response.

---

# v1.1 DELTA — Pre-Build Additions (binding; supersedes conflicting v1.0 text)

## 13. Status Model Clarification — HOLD

`HOLD` is **never** an LLM/judge verdict. It is emitted only by (a) intake gates (G-0..G-3 below), and (b) AMC profile severity remaps. The judge vocabulary stays PASS/FAIL/VERIFY/NOT_APPLICABLE (see SHALqc-CORE §4.2). Report builder treats HOLD as its own card group, ordered first.

## 14. Intake Gates (expanded, all code-side, all pre-extraction)

| Gate | Check                                                                                                                                                                                | On fail                                                                                                                           |
| ---- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | --------------------------------------------------------------------------------------------------------------------------------- |
| G-0  | Appraisal PDF present + parseable; XML parseable when present                                                                                                                        | HOLD`blocked_missing_doc`, run ends with intake report                                                                          |
| G-1  | Package safety: size cap (200 MB), zip-bomb ratio guard (≤100:1), path-traversal-safe extraction, MIME sniff per file, encrypted/corrupt PDF detection                              | HOLD`package_unsafe` / `pdf_unreadable`, never a crash                                                                        |
| G-2  | **XML-belongs-to-report gate:** XML subject address + borrower vs a direct PDF page-1 template-region read; normalized token overlap must clear 0.8 on at least one of the two | HOLD`xml_document_mismatch`; XML overlay is DISABLED for the run (PDF-only mode) — wrong-order XML must never poison the merge |
| G-3  | Idempotency: sha256 over all package bytes; hash seen before with same profile+config fingerprint                                                                                    | return the stored run (`cached_run: true`), do not reprocess                                                                    |

## 15. Revision Handling (new, first-class)

- `orders(order_id)` ↔ `runs(run_id, order_id, revision_no, package_hash, fingerprint)`. Same order_id resubmitted with a different package hash ⇒ `revision_no += 1`.
- **Revision diff (rpt-1.1.0):** on revision_no > 0, each finding is diffed against the prior run by `(rule_id, message_key, root_field)` → labeled `new | still_open | resolved`. Reviewer card header on revisions: "Revision 2 — 4 resolved, 1 still open, 1 new." `resolved` items render collapsed.
- API: `GET /runs/{run_id}` gains `diff_vs_previous`; `/qc/process` response gains `revision_no`.
- Even if the diff UI ships later, the schema keys (order_id, revision_no) are mandatory NOW — retrofitting them is a migration; adding the diff on top of them is a feature.

## 16. Partial-Failure Contract (invariant + test)

Any page-level or stage-level exception is caught at the orchestrator boundary; affected fields become MISSING, affected rules resolve per the missing-field policy (VERIFY/NA), the run **completes**, and `report.degradations[]` lists what broke. Java never receives a 5xx for a processable order. Covered by a test that injects a mid-stage exception and asserts a complete report.

## 17. Ops Rails

- **Config audit:** every `PUT /routing/config` and profile file change writes `config_audit(who, what, before_hash, after_hash, ts)`. Run fingerprint (§1) now = component versions + prompt versions + **config hashes** (routing.yaml, normalizer.yaml, active profile + wording).
- **Health metrics (alert on):** LLM failover rate >5%/h; validator degradation rate (`ungrounded`+`math_mismatch`) >3 per 100 verdicts; location_quality-exact <85% on any run; Celery queue depth.
- **PII:** LLM prompt/response cache in Redis carries borrower PII → dedicated Redis DB, TTL 72h (down from 7d), AUTH required, plus `DELETE /runs/{order_id}/cache` purge endpoint. Persisted runs keep PII in Postgres only.
- **Date discipline:** one shared parser (`normalize/dates.py`): accepts mm/dd/yyyy, m/d/yy, ISO; 2-digit years pivot at 50; all dates stored ISO; service timezone fixed UTC; comparisons date-only unless a rule states otherwise.

## 18. Fixture Discipline

Golden expected-findings files for the 2–3 fixture orders are **hand-authored before D1-1 starts** and frozen. They are the acceptance test for every block's "done when." A change to a golden file requires a written reason in the commit.

## 19. Explicitly Deferred (do NOT build in the 2-day sprint)

Corrections-driven learning loops; image/vision rules (photos, sketch, maps — the 21 known catalog gaps); non-1004 forms (1073/1025/2055); rush-order queue priority; revision-diff *UI polish* beyond the labels in §15. Claude Code must not invent these.

## 20. Definition of Done (additions)

6. G-2 wrong-XML fixture (mismatched XML + PDF) yields HOLD `xml_document_mismatch` with XML overlay disabled — proven by test.
7. Resubmitting an identical package returns the cached run without reprocessing.
8. Injected mid-stage failure still yields a complete report with `degradations[]` populated.
9. Run fingerprint changes when routing.yaml, normalizer.yaml, or the active profile changes.
