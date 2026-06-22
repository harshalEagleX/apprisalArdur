# Extraction Optimization — Findings & Status (Problems 1, 2, 4)

Grounded in real verification (no guessing). Page-layout claims confirmed by running `_group_pages` on real PDFs and by the shared screenshots.

## Verified facts (the premise)
- **Standard URAR (1718 Theon St):** `subject`(+contract) and `neighborhood` resolve to the **same page 1**; `cost` and `uspap` share a page too. → the per-group gap-fill sent **page-1 text twice**.
- **Subject group already covers the CONTRACT section** — `PAGE_GROUPS["subject"]` is labeled *"page 1 (SUBJECT and CONTRACT sections)"*. So Subject + Contract are one group already; Neighborhood is the duplicate.
- **Condo with a cover page (90 NE 32nd):** the form is on **page 3** (after cover + USPAP); the **content matchers found it correctly** and subject+neighborhood still co-resolved. → page location is by content, not page number, so the cover-page variation is already handled.

---

## Problem 1 — same page text sent multiple times → **FIXED (flag-gated, measured-pending)**

**Implemented:** `form_llm_extractor._gap_call_by_page` (under `FORM_LLM_BATCH`). It groups the gap-fill groups by **identical page text** and makes **one LLM call per unique page**, with the union of that page's fields. So page 1 (Subject+Contract+Neighborhood) is sent **once**, not twice; Cost+USPAP likewise.

**Why this is the correct version** (the earlier all-pages batch 413'd): each call carries **exactly one page's** text → never exceeds the 8K per-request ceiling. The prompt format is the same as per-group (`_prompt`), only the field list is the union. Every value is still **verbatim-validated against its page** (P-14a).

**Verified (mock, zero quota):** on 1718 Theon, OFF = 9 calls / page-1 sent 2×; ON = 7 calls / page-1 sent **1×**, and the merged call requests both subject and neighborhood fields.

**Status:** code in place, **default OFF**. Per P-8 it needs the accuracy A/B (PASS/FAIL/VERIFY + fill-rate via `measure_form_batch.py`) before default-on — pending Groq quota (currently rate-limited). Structurally it's lower-risk than the old batch (one page per call, natural reading), so it is expected to hold, but **measurement gates the switch**.

---

## Problem 2 — prompt layout blocks Groq caching → **ANALYSIS ONLY (do not implement)**

**Key realization:** Fix 1 **removes the very duplication Problem 2 wanted to cache.** Once Subject+Neighborhood are one call, there is no "second call with the same page text" to cache. So caching the duplicate is moot.

**What remains for caching after Fix 1?** The ~7 calls read **different** content (different pages / SCA grid / contract). They share only the short `_SYSTEM` line — **below Groq's 128–1024-token cache minimum** — so caching still can't engage (matches the measured 0%).

**The "common start across PDF variants" idea — the honest answer:**
- The thing that *is* byte-identical across every 1004 is the **blank form's printed boilerplate** (labels/section headers: "Property Address", "Owner of Public Record", "Sale Price", …). The *filled values* differ; the *template labels* don't.
- But the spatial OCR text **interleaves label and value on the same line** (`Property Address 28203 Fantail Dr City Katy …`), so labels and values can't be cleanly split into a stable prefix + variable suffix.
- To exploit it you'd have to **lead every call with a large stable block** (e.g., the canonical blank-form reference or a fixed instruction ≥1024 tok) so Groq caches it **across documents**. On the **free tier** the first call still pays that block in full (must stay <8K), and the per-doc variable text still counts — so the payoff is **bounded and complex**.
- **Cover-page variation is already solved** (content-based page location, verified on the condo). There is no page-number fragility to fix.

**Recommendation:** do **not** invert prompt layout for caching. Fix 1 captures the real saving (dedup); cross-document form-template caching is a complex, marginal lever that the free-tier 8K wall caps. Revisit only on a paid tier, where it would save dollars (not ceiling).

---

## Problem 4 — SCA has no true double-verification → **DESIGN ONLY (do not implement yet)**

**Today (`_overlay_sca_llm`):** Camelot reads the grid → the LLM **overwrites** the cells it confidently reads (validating `adjusted = sale + net`). This is **repair**, not verification: the two readers never formally **agree/disagree**, and if Camelot is wrong AND the LLM hallucinates the same wrong number on garbled OCR, **the error passes silently**.

**Proposed double-verification layer (design):**
1. **Run both readers independently** — Camelot and LLM — and keep **both** values (P-5: preserve inputs). Don't let one silently overwrite the other.
2. **Compare per currency cell** (`sale_price`, `net_adjustment`, `adjusted_sale_price`):
   - **Agree** (within tolerance) → accept, **HIGH** confidence.
   - **Disagree** → resolve by the **arithmetic invariant** (`adjusted ≈ sale + net`) and plausibility ranges; accept the one that validates.
   - **Neither validates / both fail** → emit the cell as **VERIFY** (flag for the human) rather than guessing.
3. **Three-way confidence:** agreement of (Camelot, LLM, arithmetic) = high; any disagreement → VERIFY. This is what closes the "both wrong, silent" gap — a disagreement becomes a *flag*, not a coin-flip.
4. **Record the verdict** — store Camelot value, LLM value, and the chosen value + reason, so a reviewer can see *why* `Z` was chosen. Feeds the training/feedback loop.

**Status — PROTOTYPE STAGED (flag `SCA_DOUBLE_VERIFY`, default OFF, UNVERIFIED):**
Implemented `_sca_double_verify` in `transaction.py` behind the flag. Default off ⇒ the SCA path is byte-identical to today. The reconciliation logic is **unit-verified with synthetic values** (zero Groq):
- agree (cam==llm) → value kept, `sca_camelot+llm_agree`, **conf 0.95**, both recorded;
- disagree (cam≠llm) → keep deterministic, `sca_conflict`, **conf 0.40** (forces the SCA rule to VERIFY), records `CONFLICT camelot=…|llm=…`;
- LLM-only → `sca_llm`, conf 0.9 (unchanged).

**End-to-end run (real Groq, 28203 Fantail, clean digital doc):** `off=(190,2,32) on=(191,1,32)` — **VERIFY unchanged (32→32): no over-flagging** on a clean doc, PASS/FAIL moved ±1 (LLM nondeterminism). The agree/conflict counters read 0 — an **introspection bug in the measure script** (couldn't read the extraction set), so the agreement rate is unquantified. **Conflicts only appear when Camelot and the LLM actually disagree — i.e. scanned/garbled docs, which this clean corpus lacks.** Verdict: prototype is safe (no over-flag) but its **error-catching value is still unproven** — needs a disagreement case (a scanned/low-quality appraisal) to demonstrate. Keep OFF. Next: fix the introspection counter + test on a scanned doc.

---

## Problem 3 — multi-page comps + 12-comp cap → **cap raised 12→15, verified**

The URAR fits 3 comps/page; extra comps spill to continuation pages whose header restarts at "#1,#2,#3" but are really comps 4,5,6…

**Verified (zero Groq) across 4 docs** — the **deterministic** reader numbers comps **sequentially across pages, with NO cap**:
| Doc | comps | grid pages |
|---|---|---|
| 1718 Theon (standard) | max **3** | 1 |
| 90 NE 32nd (condo + cover page) | max **5** | **2** |
| 28203 Fantail (standard) | max **6** | **2** |
| 191 Neeley (standard) | max **3** | 1 |

The condo (5 comps) and Fantail (6 comps) confirm continuation-page comps are numbered 4–6 correctly, not restarted.

**Change made:** the **LLM** path's hard cap (`if gi > 12`) is now `_MAX_COMPS = 15` (named constant, `sca_llm_extractor.py`). The deterministic path was already uncapped. **Honest gap:** none of the available docs exceed 6 comps, so the 13–15 LLM extraction itself is **compile-verified but not live-verified** — it needs a real ≥13-comp report + Groq to confirm comps 13–15 extract. Standard 3–6-comp docs are unaffected.

## Fix 1 — verified on all 4 docs + accuracy A/B (real Groq)
Page-1 (Subject+Contract+Neighborhood) text sent **2× → 1×** on every doc (incl. the cover-page condo where the form is page 3); total LLM calls dropped 8→6, 10→9, 9→8, 8→7. Co-page dedup works across layouts.

**Accuracy A/B (real Groq, 3 docs, cache off):**
| | total PASS | FAIL | VERIFY | calls | tokens |
|---|---|---|---|---|---|
| OFF (per-group) | 454 | 4 | 67 | 34 | 38,163 |
| ON (per-page merge) | **454** | **4** | **67** | 26 (**−24%**) | 34,852 (−9%) |

**Totals identical (454/4/67) → accuracy net-neutral.** Per-doc deltas were ±1 and went *both ways* (1718 Theon +1 PASS, Fantail −1 PASS, Neeley identical) — LLM nondeterminism (gpt-oss-120b JSON-mode 400s hit both runs), not a systematic merge effect. **−24% calls** (relieves the binding RPD limit), −9% tokens. **Recommendation: safe to enable** (a larger-corpus confirm would remove the last ±1 doubt). Contrast: the earlier all-pages batch had a *real* regression (413-driven). The per-page merge does not.

## Summary

| Problem | Status |
|---|---|
| 1 — duplicate co-page text | **Fixed** (per-page merge, flag-gated; mock-verified; accuracy A/B pending quota) |
| 2 — caching via prompt reorder | **Not worth it** — Fix 1 subsumes it; free-tier 8K wall caps cross-doc caching |
| 4 — true double-verification | **Designed** (compare-and-flag, not silent overwrite) — recommend, measure before adopting |
