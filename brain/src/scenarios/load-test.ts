import type { Browser } from "@playwright/test";
import { AdminAgent } from "../agents/AdminAgent";
import { ReviewerAgent } from "../agents/ReviewerAgent";
import { ScenarioStore } from "../state/store";
import type { LoadTestFixture } from "../fixtures/setup";

export interface WorkerResult {
  workerIndex: number;
  adminLabel: string;
  reviewerLabel: string;
  batchId: number;
  status: "completed" | "failed";
  durationMs: number;
  error?: string;
  store: ScenarioStore;
}

export interface LoadTestResult {
  workers: WorkerResult[];
  startedAt: string;
  finishedAt: string;
  totalDurationMs: number;
}

// Semaphore: limits concurrent OCR/QC jobs to avoid overwhelming the single-worker
// Python OCR service.  Each admin acquires a slot before calling runQcIfNeeded,
// releases it immediately after (OCR runs async inside the Java backend anyway).
class Semaphore {
  private queue: Array<() => void> = [];
  private running = 0;
  constructor(private readonly max: number) {}

  async acquire(): Promise<void> {
    if (this.running < this.max) { this.running++; return; }
    return new Promise<void>(resolve => this.queue.push(resolve));
  }

  release(): void {
    const next = this.queue.shift();
    if (next) { next(); } else { this.running--; }
  }

  async run<T>(fn: () => Promise<T>): Promise<T> {
    await this.acquire();
    try { return await fn(); } finally { this.release(); }
  }
}

export async function runLoadTest(browser: Browser, fixture: LoadTestFixture): Promise<LoadTestResult> {
  const startedAt = Date.now();

  // Fully serialize QC starts: the Ollama model inside the Python OCR service
  // handles one LLM inference at a time, so 2 concurrent jobs double wall time
  // without doubling throughput, and easily exceed the per-batch QC timeout.
  // All 10 browser sessions are still active simultaneously; only the
  // long-running OCR/LLM calls are serialized.
  const qcSlots = new Semaphore(1);

  const workers = await Promise.all(
    fixture.admins.map(async (adminCreds, i): Promise<WorkerResult> => {
      const reviewerCreds = fixture.reviewers[i];
      const store = new ScenarioStore();
      const adminLabel = `admin${i + 1}`;
      const reviewerLabel = `rev${i + 1}`;
      const workerStart = Date.now();

      const result: WorkerResult = {
        workerIndex: i,
        adminLabel,
        reviewerLabel,
        batchId: -1,
        status: "failed",
        durationMs: 0,
        store,
      };

      const admin = new AdminAgent(browser, store, {
        credentials: { username: adminCreds.username, password: adminCreds.password },
        zipPath: fixture.zipPaths[i],
        clientId: fixture.clients[i].id,
        targetReviewerId: reviewerCreds.id,
        label: adminLabel,
      });
      const reviewer = new ReviewerAgent(browser, store, {
        credentials: { username: reviewerCreds.username, password: reviewerCreds.password },
        label: reviewerLabel,
      });

      try {
        store.record(adminLabel, "worker:start", { zipPath: fixture.zipPaths[i] });

        // Stagger bootstrap by 500ms per worker to avoid overwhelming the
        // Next.js dev server with 10 simultaneous page loads.
        await new Promise(r => setTimeout(r, i * 500));

        // Phase 1 — all 10 users log in simultaneously (offset start, not serial).
        await Promise.all([admin.bootstrap(), reviewer.bootstrap()]);

        // Phase 2 — admin uploads batch (upload is fast; no throttle needed).
        const batch = await admin.createOrReuseBatch();
        result.batchId = batch.id;

        // Phase 3 — serialized via semaphore: at most one QC job starts at a time.
        store.record(adminLabel, "qc:queued");
        const readyBatch = await qcSlots.run(() => admin.runQcIfNeeded(batch));

        // Phase 4 — assign reviewer (fast; no throttle needed).
        await admin.assignReviewer(readyBatch);

        // Phase 5 — all reviewers work their queues simultaneously. A batch can
        // contain multiple appraisal QC results, so keep draining this reviewer's
        // assigned queue until the batch reaches a terminal state.
        for (let reviewed = 0; reviewed < 20; reviewed += 1) {
          const before = await admin.api.getBatchStatus(readyBatch.id);
          if (before.status === "COMPLETED") break;
          if (before.status === "ERROR") {
            throw new Error(`QC ended in ERROR: ${before.errorMessage ?? "unknown error"}`);
          }

          const qcResult = await reviewer.waitForAssignedResult();
          await reviewer.completeReview(qcResult.id);

          const after = await admin.api.getBatchStatus(readyBatch.id);
          if (after.status === "COMPLETED") break;
          if (after.status === "ERROR") {
            throw new Error(`QC ended in ERROR: ${after.errorMessage ?? "unknown error"}`);
          }

          store.record(reviewerLabel, "review:batch-still-pending", {
            batchId: readyBatch.id,
            reviewed: reviewed + 1,
            status: after.status
          });
        }

        // Phase 6 — confirm COMPLETED.
        await admin.waitForCompleted(readyBatch.id);

        result.status = "completed";
        store.record(adminLabel, "worker:done", { batchId: readyBatch.id });
      } catch (err) {
        result.status = "failed";
        result.error = String(err);
        store.record(adminLabel, "worker:error", { error: String(err) });
      } finally {
        await Promise.allSettled([admin.stop(), reviewer.stop()]);
        result.durationMs = Date.now() - workerStart;
      }

      return result;
    })
  );

  const finishedAt = Date.now();
  return {
    workers,
    startedAt: new Date(startedAt).toISOString(),
    finishedAt: new Date(finishedAt).toISOString(),
    totalDurationMs: finishedAt - startedAt,
  };
}
