# UAD 3.6 — start here

Written 2026-08-15 at the end of a long session. Everything below is measured,
not assumed. Where something is unproven it says so.

**Rule zero: never touch 2.6.** It is working, `status: active`, 134 items, and
it holds **49 hand-tuned bindings that exist nowhere else and are not
regenerable**. This session deleted it with `rm -f compiled/EQUITYSOLUTIONS/*.yaml`
and only recovered it because it is git-tracked. To recompile 3.6, delete
**only** its own hash — `compiled_path('EQUITYSOLUTIONS', uad_version='3.6')` —
and assert the filename is not `96b595e6f127ba4f.yaml`.

---

## State

| | |
|---|---|
| tests | **417 pass**, 7 skipped |
| checklist | 90 items (3.6) — was wrongly scoring on 134-item 2.6 |
| extraction | 243.7s (was 555.6s), 374 fields (was 266) |
| judge | 0 timeouts (was 3), 24 lanes (was 10) |
| total QC | 499.7s (was 820.2s) |
| **PASS on 3.6** | **0** — the open problem |

---

## The open problem: 0 PASS

Not a speed issue. Three causes, in order of size.

### 1. Fourteen items are bound to no fields

They can only ever be REVIEW. Get the live list with:

```bash
python -c "
import sys;sys.path.insert(0,'.')
from app.language.compiler import compile_checklist
c=compile_checklist('EQUITYSOLUTIONS',uad_version='3.6')
for i in c:
    if not (i.bound_labels or []): print(i.item_id, i.check_text[:70])"
```

Three of them need fields the extractor does not produce at all
(`comp_N_location`, `comp_N_property_rights`) — those are extraction work, not
binding work. Seven are photo/graph items; see §3.

### 2. Twenty-six items bind 2–5 fields and are UNVERIFIED

This is the one the user raised repeatedly, and it is the real quality lever.
Many checklist questions cannot be answered from one value — the septic finding
needs `site.apparent_defects` **and** `unit_interior.utilities_operating` **and**
`contract.analysis_comment` **and** `reconciliation.value_condition`. Every one
of those reads "fine" alone.

**A binding that lists four fields but delivers one looks covered and behaves
like a guess.** Verify the packet actually carries every declared field before
trusting any verdict from these 26.

### 3. `visual` items have no evidence path

18 items are scope `visual`. `app/extraction/vision/visual_checks.py` was built
for exactly these and has **zero callers** — `merge.py` routes 3.6 only to
`run_vision_extraction`. Same for `checklist_arithmetic.py` (now wired) and
`checklist_cards.py` (still only referenced by a test).

---

## The naming contract — this cost hours

```
comp_1_gla  ->  canonicalises to  comp_N_gla     KNOWN
comp_N_gla                                        KNOWN
comp_gla / comp_proximity / comp_location         NOT KNOWN
```

Comparable fields are `comp_N_<field>` (or `comp_1_..comp_6_`, which canonicalise
to the N form). The short `comp_<field>` form **does not resolve**.

Unknown names used to be dropped **silently**, so a hand-written binding could
read `binding: bound` in the YAML and `unbound` in the compiler with nothing
explaining the gap. That is now loud (`_UNKNOWN_BINDINGS` + a WARNING) and
pinned by `tests/test_extraction/test_binding_names_are_known.py`, which fails
the build if the shipped 3.6 checklist references a field nobody extracts.

---

## Latency: what is true

**The reasoning tax is FIXED PER CALL, not per field.** Measured on
`gemma-4-31B-it`, sequential, no contention:

```
1 field   -> 1,245 output tokens, 14.3s
15 fields -> 1,536 output tokens, 16.5s
output ≈ 1,230 + 21 × N
```

So **fewer, bigger calls win**. Sharding into more, smaller calls multiplies the
tax — the opposite of the obvious optimisation, and the reason most early tuning
bought nothing. (PROBLEM_LOG's `515 + 159×N` does not hold for this config.)

**Hard limits:** 10 images per call succeed, **11 returns HTTP 400**. Decode is
~87–93 tok/s uncontended — the provider is healthy.

**60s is not reachable on gemma.** One 10-page call is ~57s of decode and a
40-page report needs four. Extraction alone floors near 100s.

`app/extraction/vision/bulk.py` implements the whole report in
`ceil(pages/10)` calls (flag `VISION_USE_BULK`, default on). It must run
**sequentially with the grid** — run concurrently, its 4 fat calls and the grid's
12 split throughput 16 ways and the biggest calls starve first (measured: 12
fields, 3 of 4 calls dead at zero output tokens, no provider error).

### Two things I concluded and later disproved

- **"12 keys made it slower."** Throughput swung 43–429 tok/s across *identical*
  configs. The comparison was inside the noise. Nothing is known either way.
- **`tok/s` as a throughput measure.** It was tokens ÷ wall clock, so it merely
  re-reported wall clock under a second name.

Establish a noise floor before any config A/B on this account.

---

## The one experiment worth running first

`VISION_PROVIDER=anthropic VISION_MODEL=claude-sonnet-5` is fully wired — key in
`.env`, `anthropic` package installed, provider initialises. It fails only with
`400 invalid_request_error: credit balance is too low`.

Add credit and run the probe below. It answers the single question that decides
whether 60s is achievable at all: **does Claude carry the same fixed per-call
reasoning cost?**

```bash
VISION_PROVIDER=anthropic VISION_MODEL=claude-sonnet-5 PYTHONPATH=. python -c "
import time
from app.extraction.vision.provider import get_vision_provider
from app.extraction.vision.render import render_page
p=get_vision_provider()
img=render_page('3.6/Email - AppraisalArdur - Outlook (1).pdf',2,dpi=100)
for n in (1,15):
    f={f'f{i}':{'type':['string','null']} for i in range(n)}
    t=time.monotonic()
    r=p.transcribe([img],'Transcribe.',{'type':'object','properties':f,'required':[]},max_tokens=3000)
    print(n,'fields:',round(time.monotonic()-t,1),'s',r.output_tokens,'tok')"
```

If a 1-field call comes back well under 1,245 tokens, extraction collapses and
60s is plausible. If not, ~180s is the floor and the target should be renegotiated.

**Rotate the Anthropic key** — it was pasted in a chat transcript.

---

## Harnesses

```bash
python 3.6/run_extract.py  <pdf> 3.6/_runN    # extraction only
python 3.6/run_full_qc.py  <pdf> 3.6/_qcN     # full QC incl. judge + checklist
python 3.6/section_router.py <pdf>            # structural router, no model calls
```

Always redirect to a real log file (`> file.log 2>&1`) and never pipe through
`tail` — it buffers to EOF and the run appears to hang. That mistake cost two
runs this session.
