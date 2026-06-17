# Batch / Reviewer Robustness + UX — Fix Plan

> Consolidates the lifecycle analysis (`Batch_File_Reviewer_Lifecycle_Analysis.md`) **plus** the new
> issues surfaced from the live audit/batch screens. Goal: the system never shows the user wrong or
> confusing data, every state change is captured in the audit, partial re-runs are safe, and the
> Batch screen is genuinely usable. Each item has a fix + a test gate.

## Issues (evidence-grounded)

| # | Issue | Evidence | Severity |
|---|---|---|---|
| **D1** | Reviewer decision saved during a re-run window is **silently lost** | `saveDecision` guards `assertDocumentCurrent` (hash only) + session token — neither catches a same-file rerun | 🔴 data loss |
| **D2** | `submitVerification` / `acceptAll` / `rejectAll` have **no supersede guard** → can submit a dead result | `submitVerification:327` uses `getForVerification` (no check) | 🔴 data integrity |
| **D3** | `assertDocumentCurrent` ignores `supersededAt` (only hash/version) → same-file rerun invisible | `VerificationService:675` | 🔴 |
| **A1** | **Audit does not record re-runs** — no node, no event | `AuditGraphController` has no rerun node; no `BATCH_QC_RERUN`/`QC_RESULT_SUPERSEDED` business event | 🔴 "system is blind" |
| **U1** | Batch row shows **stale model** `ollama · llava:7b` and **contradictory progress** (`2%` + `queued — waiting for Celery worker` + `Running OCR…`) | live screen | 🟠 confusing |
| **R1** | **Re-run is whole-batch only**; fixing 2 files in a 50-file batch **supersedes all 50** and wipes review state on the untouched 48 | `processBatch` loops all `getMatchedPairs` | 🔴 review-work loss at scale |
| **R2** | Reviewer **loses the file after a re-run** (new result has no lock; another reviewer can grab it) | `persistPythonResult` ends at `REVIEW_PENDING`, no lock carry | 🟠 |
| **X1** | Multi-file batch audit is **flat** — a batch with N appraisal sets isn't clearly grouped/attributed | audit graph caps at 300 nodes, no per-set grouping | 🟡 |
| **UX** | Batch screen actions/states aren't self-explanatory (Run/Re-run/Stop/Assign, stuck states, per-file) | live screen | 🟠 |

## Phased plan

### Phase 1 — Data integrity + truthful audit (🔴, surgical backend) — **DO FIRST**
1. **D3:** `assertDocumentCurrent` also throws when `supersededAt != null`. One line; instantly covers
   `beginReviewSession`, `heartbeat`, `saveDecision`, `completeSavedVerification`.
2. **D2:** add the guard to `submitVerification`, `acceptAll`, `rejectAll` (the paths that bypass it).
3. **D1:** with D3 in place, a decision-save against a just-superseded result is rejected with a clear
   HTTP 409 "this report was re-processed — reload current results" (frontend already handles the
   superseded WS event).
4. **A1:** emit durable audit on re-run — a batch-level `BATCH_QC_RERUN` event (with `reviewer_active`,
   model, supersededCount) and a per-file `QC_RESULT_SUPERSEDED` event (old→new result id) in
   `persistPythonResult`. → audit + the graph can now show re-runs.
   **Gate:** trigger a re-run; assert the two events exist and the file decision-save on the old
   result returns 409.

### Phase 2 — Progress / model truthfulness (🟠) 
5. **U1a:** the progress label must reflect the **actual** model; default Groq (done in `QCModelConfig`).
   Backfill/clear any stale `ollama·llava` progress; never show a removed provider.
6. **U1b:** make the sub-stage non-contradictory: when the Celery job is queued, the top-level stage
   is `Queued` (not `Running OCR`), and the percent stays at the queue step until `STARTED`. Surface a
   distinct **"waiting for worker"** state (and a clear stuck indicator if PENDING > grace).
   **Gate:** a queued batch shows one coherent state; a stuck batch is visibly "stuck", not "2% running".

### Phase 3 — Partial / per-file re-run (🔴 feature)
7. **R1:** add **per-file re-run**: `POST /api/qc/process/{batchId}/files` with a file-id list →
   re-run only those appraisal sets; supersede **only** their results; leave the other files'
   results + review state intact. Audit each superseded file.
8. **R2:** after a re-run, **carry the review lock / re-assignment** to the prior `reviewLockedBy` for
   the new result (don't silently release).
   **Gate:** 50-file batch, re-run 2 files → exactly 2 superseded, 48 untouched (review state intact),
   audit shows 2 file re-runs.

### Phase 4 — Batch screen UI/UX
9. Clear status taxonomy + actions per state (Run / Re-run / Stop / Assign / Open review), explicit
   **stuck** badge, per-file actions (re-run this file, view journey), and a re-run history/audit
   surface so the user is never blind. File-set grouping for multi-file batches.

### Phase 5 — End-to-end tests (so production never fails)
10. Integration tests for: upload→run→review→submit; re-run-while-in-review (decision-loss guard,
    409, audit events); partial re-run (N files); stuck-worker recovery; double-click; superseded
    queue exclusion. Plus the load/soak gates from `SCALABILITY_PLAN.md`.

---

*Status: Phase 1 implemented in this pass (see commit). Phases 2–5 staged.*
