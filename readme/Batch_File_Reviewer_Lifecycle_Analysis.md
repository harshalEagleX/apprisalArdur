# Batch / File / Reviewer Lifecycle — Code Analysis & Edge Cases

> Scope: everything a batch and its files go through — **upload → run → re-run → reconcile** —
> with the reviewer role woven in, and a forensic look at the scenario **"reviewer has the file
> open, admin triggers re-run QC."** Every claim is tied to code (`file:method`).

---

## 1. The data model & links

```
Batch (1) ──< BatchFile (N) ──< QCResult (N, one ACTIVE + historical) ──< QCRuleResult (N)
  │  status (state machine)          │ supersededAt (null = active)        │ reviewerVerified
  │  assignedReviewer (User)         │ finalDecision (reviewer outcome)    │ overridePending / approvedBy
  │  @Version (optimistic lock)      │ reviewLockedBy / reviewLockExpiresAt│ firstPresentedAt / sessionToken
  │  updatedAt (QC heartbeat)        │ reviewSessionToken                  │ decisionLatencyMs
  └─ parentBatchId                   │ sourceDocumentHash / Version (rerun guard)
```

- **Active vs historical QC result:** `findActiveByBatchFileId` returns the one with
  `supersededAt IS NULL` (`QCResultRepository:260`). A re-run **supersedes** the prior result
  (stamps `supersededAt`) and creates a new active one — history is never deleted.
- **Every reviewer queue query filters `supersededAt IS NULL`** (`QCResultRepository` lines
  37,91,111,118,133,141,159,174,184) — superseded results vanish from the queue automatically.

---

## 2. Batch state machine (`BatchStatus`)

```
UPLOADED → (VALIDATING) → QC_PROCESSING → REVIEW_PENDING | COMPLETED | ERROR
                                REVIEW_PENDING → IN_REVIEW → COMPLETED | ERROR
```
- `IN_REVIEW` = a reviewer holds an active per-result lock.
- Transitions are done with **atomic, version-bumping UPDATEs** (not load-modify-save) to dodge
  optimistic-lock clashes between QC completion and reviewer/admin actions (`BatchRepository`).

---

## 3. Process walkthroughs

### 3.1 Upload (`BatchService.uploadBatch`)
- ZIP streamed in; **SHA-256 of the whole ZIP** for dedup → `findByFileHash`; a duplicate ZIP
  returns the **existing** batch (idempotent, `BatchService:290`). Per-file entries extracted to
  `uploads/<batch>/<type>/`, each `BatchFile` stamped with its own `contentHash` + `contentVersion`.
- Status starts `UPLOADED`. **Auto-process is off** (`qc.auto-process-on-upload: false`) → QC is
  admin-triggered.

### 3.2 Run QC (`QCApiController.processBatch` → `QCProcessingService`)
1. **Pre-flight:** batch exists; if already `QC_PROCESSING` → return "already processing" (no
   double-run, `:100`). **Python `/live` health checked BEFORE claiming** — if down, `503` and the
   batch is left exactly as-is (`:121`). *(Good: no stuck QC_PROCESSING on a dead Python.)*
2. **Atomic claim:** `claimBatchForProcessing` → `markQcProcessingIfTriggerable` flips status →
   `QC_PROCESSING` and `version+1` **in one UPDATE** — closes the double-click race
   (`BatchRepository:90`). An in-JVM `activeBatches` set + `runningThreads` map double-guards.
3. **Async run** (`processBatchAsync` on the bounded `qcTaskExecutor`): match files
   (`FileMatchingService`) → per pair, `processFilePair` (Python call kept **outside** any DB
   transaction) → `persistPythonResult` (short txn) → `determineBatchStatus` →
   `REVIEW_PENDING | COMPLETED | ERROR`. A periodic `touchQcProcessing` heartbeat keeps `updatedAt`
   fresh so the reconciler doesn't abandon a slow-but-live run.

### 3.3 Re-run when ALREADY run (the supersede path — `persistPythonResult:673`)
`markQcProcessingIfTriggerable` **allows triggering from `COMPLETED`, `REVIEW_PENDING`, and
`IN_REVIEW`** (`BatchRepository:90`) — so a re-run is permitted at any post-QC stage. On persist:
- `findActiveByBatchFileId` finds the prior active result → **isRerun = true**.
- Prior result is **superseded** (`supersededAt` set, kept for audit); new result created and linked
  via `rerunOf`.
- **Reviewer decisions are carried** by `migrateReviewerDecisions` (`QCProcessingService:1152`):
  a decision carries **only when** the finding key (rule id + target field) matches **and** the
  rule outcome (status) is unchanged **and** the reviewer had actually decided it. New/changed/gone
  findings are **re-queued** (left pending) — correct.
- A **`/topic/reviewer/qc/{oldResultId}/superseded`** WebSocket event is published with the new
  result id so an open reviewer UI can offer to reload.
- Batch ends at `REVIEW_PENDING` (via `determineBatchStatus`), **not** back to `IN_REVIEW`.

### 3.4 Cancel / Stop (`QCApiController.cancelBatch` → `cancelBatch`)
- Sets a cancellation flag, **interrupts the worker thread**, and `markUploadedIfQcProcessing`
  returns the batch to `UPLOADED` (files preserved). Late Python results are discarded via the
  cancellation check before persist.

### 3.5 Reconcile (`StuckBatchReconciler`, every 10 min)
- **Stuck QC:** batches in `QC_PROCESSING` with stale `updatedAt` → if Python healthy & within the
  retry window → re-trigger (cached re-OCR); past the abandon window → `ERROR`. `isBatchActive`
  guard skips ones live on this JVM.
- **Expired review locks:** `findExpiredInReviewBatches` returns `IN_REVIEW` batches whose
  per-result locks all expired but still have pending reviewer work → returns them to
  `REVIEW_PENDING` so the queue is honest (`BatchRepository.findExpiredInReviewBatches`).

---

## 4. Reviewer lifecycle (`VerificationService`)

| Step | Method | Guard |
|---|---|---|
| Open file | `beginReviewSession:66` | **pessimistic write lock** (`findByIdForUpdate`) closes the TOCTOU on the lock; `assertDocumentCurrent`; if another reviewer holds an unexpired lock → reject; `REVIEW_PENDING → IN_REVIEW`; sets `reviewLockExpiresAt` (TTL) |
| Keep alive | `heartbeatReviewSession:128` | `assertDocumentCurrent` + `assertSessionOwnsQcResult`; extends lock |
| Save one decision | `saveDecision:238` | `findByIdForUpdate` + `assertDocumentCurrent` + `assertSessionOwnsQcResult` + duplicate/freshness/engagement checks |
| Submit | `submitVerification:327` | `getForVerification` (**no** `assertDocumentCurrent`); sets `finalDecision`; `completeBatchIfReviewFinished` |
| Release | `releaseReviewSession:139` | expires lock; `IN_REVIEW → REVIEW_PENDING` if still pending |

**The linchpin — `assertDocumentCurrent` (`:675`):** it compares the result's
`sourceDocumentHash` / `sourceDocumentVersion` to the batch file's **current** values and throws
"a newer version was submitted…" on mismatch. **It catches a re-UPLOADED file — it does NOT catch a
same-file RE-RUN** (the hash is identical), and it isn't checked for `supersededAt`.

---

## 5. THE scenario: reviewer open + admin re-run — full trace

1. Reviewer opens result `R1` → lock held, batch `IN_REVIEW`, items presented.
2. Admin clicks Run QC. Endpoint computes `reviewerActive` via
   `countActiveReviewPresenceForBatch(batchId, now-30min)` and **returns it to the admin but does
   NOT block** — by design (`QCApiController:151`, comment: *"We do NOT block — the reviewer is
   notified live and their decisions are preserved"*).
3. `markQcProcessingIfTriggerable` flips `IN_REVIEW → QC_PROCESSING` (allowed). Re-run executes.
4. `persistPythonResult` supersedes `R1`, creates `R2`, **migrates** matching decided findings,
   publishes the `…/{R1}/superseded` WS event. Batch → `REVIEW_PENDING`.
5. Reviewer's UI (if subscribed) is told `R1` was superseded and can load `R2`.

**What is correctly handled:** decisions on unchanged findings survive; `R1` stays in history;
`R1` leaves the queue (supersede filter); `R2` enters; no data is deleted; double-click and
"already running" are blocked; Python-down is rejected pre-claim.

---

## 6. Edge cases HANDLED ✅

- Double-click re-run → atomic claim (`BatchRepository:90`).
- Re-run while running → `QC_PROCESSING` short-circuit (`QCApiController:100`).
- Python down at trigger → pre-flight `503`, batch untouched (`:121`).
- Two reviewers, same result → pessimistic lock + lock-TTL ownership check (`beginReviewSession`).
- **Re-uploaded** file invalidates a stale open review → `assertDocumentCurrent` throws.
- Expired review lock → reconciler `IN_REVIEW → REVIEW_PENDING`.
- Stuck `QC_PROCESSING` → reconciler retry/abandon with heartbeat.
- Superseded results excluded from every queue (`supersededAt IS NULL`).
- **Submitting a superseded result does NOT wrongly complete the batch:**
  `completeBatchIfReviewFinished:510` scans **all** batch results and the new active `R2`
  (`finalDecision == null`, not AUTO_PASS) keeps `hasPendingReviewerWork = true` → batch stays
  `REVIEW_PENDING`. *(Effective safety net.)*

---

## 7. Edge cases MISSING / RISKY ⚠️ (the real gaps)

1. **Decision saved during the re-run window can be silently lost.** Between
   `migrateReviewerDecisions` snapshotting `R1` and the supersede commit, a reviewer `saveDecision`
   lands on `R1` (a soon-dead result). `assertDocumentCurrent` passes (same hash),
   `assertSessionOwnsQcResult` passes (token still on `R1`) — nothing rejects the write, and the
   decision is **not** carried to `R2`. → **lost reviewer work, no warning.**
2. **`submitVerification` has no supersede/current guard** (`:327` uses `getForVerification`, no
   `assertDocumentCurrent`). A reviewer can "submit" a superseded `R1`: it sets `finalDecision` on a
   **dead result**, the submit *appears to succeed*, but the file is still pending under `R2`. →
   confusing UX + a `finalDecision` polluting historical/analytics rows.
3. **`assertDocumentCurrent` can't see a same-file re-run** (hash/version unchanged) — so for the
   most common case (admin re-runs the same PDF), the *only* protection is the WS notify + migrate,
   which has gap #1.
4. **Reviewer loses the file after a re-run.** Post-rerun the batch is `REVIEW_PENDING` and `R2`
   has **no lock**; `assignedReviewer` is preserved but another reviewer can open `R2` first → the
   original reviewer can silently lose it (only the WS event warns, and only if subscribed).
5. **No durable audit event for "re-run overrode an active review."** `reviewerActive` is written to
   the app log (`TimelineLog`) only; there is **no `BusinessEvent`** tying *admin re-run → active
   reviewer override*. For a sensitive action this is thin (the supersede WS event + the superseded
   row exist, but not a queryable audit record of the override).
6. **`reviewerActive` window (30 min) ≠ the review lock TTL.** A reviewer idle longer than 30 min
   but inside the lock window won't be flagged "active," so the admin warning can be a false
   negative.
7. **Non-subscribed reviewer never learns of the supersede.** If the reviewer navigated away from
   `R1`'s topic (or reconnected), the `…/{R1}/superseded` event is missed; they may return to a
   stale `R1` view and act on it (feeding #1/#2).

---

## 8. Audit linkage — coverage & gaps

**Covered (BusinessEvent + AuditLog + Envers):** `REVIEW_OPENED`, `REVIEW_SESSION_STARTED`
(AuditLog), `REVIEW_RELEASED`, `BATCH_QC_QUEUED/STARTED/COMPLETED/FAILED/CANCELLED`,
`QC_COMPLETED`, `QC_RULE_EVALUATED` (≈138/doc), `BATCH_COMPLETED`, FAIL-override events. Each event
carries batch/file/qcResult/rule ids + correlation id → a coherent timeline.

**Gaps:** (a) the **supersede-during-active-review** override has no business event (#5);
(b) a reviewer decision that lands on a superseded result (#1) leaves no "orphaned decision" audit
signal; (c) `submit-on-superseded` (#2) records a normal `REVIEW_SUBMITTED` with no indication it
targeted a dead result.

---

## 9. Recommendations (small, high-value)

1. **Guard the reviewer write paths on `supersededAt`.** In `saveDecision` and `submitVerification`,
   if `qcResult.getSupersededAt() != null` → reject with a clear "this report was re-processed,
   please reload the current results" error (HTTP 409). Closes #1 and #2 directly. *(One check each.)*
2. **Extend `assertDocumentCurrent`** to also throw when `supersededAt != null` — one line, makes the
   same-file re-run case visible to every guarded path (#3).
3. **Make re-run-with-active-reviewer a choice:** the data already exists (`reviewerActive`); add an
   admin confirm / optional block, and **emit a `QC_RERUN_OVER_ACTIVE_REVIEW` BusinessEvent** for
   audit (#5).
4. **Preserve the reviewer after re-run:** carry the lock / re-assign `R2` to the prior
   `reviewLockedBy`, or surface it prominently so they don't lose the file (#4).
5. **Align the `reviewerActive` window with the lock TTL** (#6) and consider a durable
   notification (not WS-only) so an unsubscribed reviewer still learns of the supersede (#7).

---

*Prepared from a read of `QCApiController`, `QCProcessingService`, `VerificationService`,
`StuckBatchReconciler`, `BatchService`, `BatchRepository`, `QCResultRepository`, and the
`Batch`/`QCResult`/`QCRuleResult` entities. Exploration only — no code changed.*
