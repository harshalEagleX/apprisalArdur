import type { Browser } from "@playwright/test";
import { expect } from "@playwright/test";
import { config } from "../config";
import { waitFor } from "../state/wait";
import type { ScenarioStore } from "../state/store";
import type { Batch, User } from "../types/domain";
import { BaseAgent } from "./BaseAgent";

const READY_FOR_QC = new Set(["UPLOADED", "ERROR", "VALIDATING"]);

export interface AdminAgentOptions {
  /** Override global config.admin credentials */
  credentials?: { username: string; password: string };
  /** ZIP file to upload. Falls back to config.batchZipPath */
  zipPath?: string;
  /** Client to upload the batch for. Falls back to config.clientId */
  clientId?: number;
  /** Reviewer user ID to assign after QC. When set, skips the auto-pick logic. */
  targetReviewerId?: number;
  /** Unique label for log prefixes (default: "admin") */
  label?: string;
}

export class AdminAgent extends BaseAgent {
  private readonly opts: AdminAgentOptions;

  constructor(browser: Browser, store: ScenarioStore, options?: AdminAgentOptions) {
    super(browser, "ADMIN", store, options?.label ?? "admin");
    this.opts = options ?? {};
  }

  private get creds() { return this.opts.credentials ?? config.admin; }
  private get zipPath() { return this.opts.zipPath ?? config.batchZipPath; }
  private get clientId() { return this.opts.clientId ?? config.clientId; }
  private get label() { return this.ui.actor; }

  async bootstrap(): Promise<void> {
    await this.start(this.creds);
    // Retry once on ERR_ABORTED — Next.js dev server occasionally drops
    // connections when many contexts start at once.
    for (let attempt = 1; attempt <= 2; attempt++) {
      try {
        await this.ui.goto("/admin/batches");
        await expect(this.ui.requirePage().getByRole("heading", { name: /batches/i })).toBeVisible({ timeout: 15_000 });
        return;
      } catch (err) {
        if (attempt === 2) throw err;
        this.store.record(this.label, "bootstrap:retry", { attempt, error: String(err).slice(0, 120) });
        await new Promise(r => setTimeout(r, 3_000));
      }
    }
  }

  async createOrReuseBatch(): Promise<Batch> {
    const actions = await this.planner.decide({
      role: "ADMIN",
      goal: this.zipPath ? "upload batch" : "reuse existing batch",
      dom: await this.ui.domSnapshot(),
      recentActions: this.store.recent().map(event => `${event.actor}:${event.event}`)
    });
    this.store.record(this.label, "brain:plan", actions);

    if (this.zipPath && Number.isFinite(this.clientId)) {
      const uploaded = await this.api.uploadBatch(this.zipPath, this.clientId as number);
      const batch: Batch = {
        id: uploaded.batchId,
        parentBatchId: uploaded.parentBatchId,
        status: "UPLOADED",
        fileCount: uploaded.fileCount
      };
      this.store.batch = batch;
      this.store.record(this.label, "batch:uploaded", batch);
      await this.ui.goto("/admin/batches");
      return batch;
    }

    const batches = await this.api.getBatches();
    const reusable = batches.find(batch => READY_FOR_QC.has(batch.status))
      ?? batches.find(batch => batch.status === "REVIEW_PENDING")
      ?? batches.find(batch => batch.status === "IN_REVIEW");
    if (!reusable) {
      throw new Error("No reusable batch found. Set BATCH_ZIP_PATH and CLIENT_ID in brain/.env to upload one.");
    }
    this.store.batch = reusable;
    this.store.record(this.label, "batch:reused", reusable);
    return reusable;
  }

  async runQcIfNeeded(batch: Batch): Promise<Batch> {
    const latest = await this.refreshBatch(batch.id);
    if (latest.status === "REVIEW_PENDING" || latest.status === "IN_REVIEW" || latest.status === "COMPLETED") {
      this.store.record(this.label, "qc:skipped", latest.status);
      return latest;
    }

    if (!READY_FOR_QC.has(latest.status)) {
      throw new Error(`Batch ${latest.id} is not ready for QC. Current status: ${latest.status}`);
    }

    await this.ui.goto(`/admin/batches?search=${encodeURIComponent(latest.parentBatchId)}`);
    await this.api.processQC(latest.id);
    this.store.record(this.label, "qc:started", { batchId: latest.id });
    await this.ui.screenshot("qc-started");

    const ready = await waitFor(
      `batch ${latest.id} to reach REVIEW_PENDING`,
      () => this.api.getBatchStatus(latest.id),
      state => state.status === "REVIEW_PENDING" || state.status === "COMPLETED" || state.status === "ERROR",
      { timeoutMs: config.qcTimeoutMs, intervalMs: 5_000 }
    );
    if (ready.status === "ERROR") {
      throw new Error(`QC ended in ERROR: ${ready.errorMessage ?? "no backend error message"}`);
    }
    return this.refreshBatch(latest.id);
  }

  async assignReviewer(batch: Batch): Promise<User> {
    const latest = await this.refreshBatch(batch.id);
    if (latest.status === "COMPLETED") {
      throw new Error(`Batch ${latest.id} is already COMPLETED; assignment is no longer needed.`);
    }
    if (latest.status !== "REVIEW_PENDING" && latest.status !== "IN_REVIEW") {
      throw new Error(`Cannot assign reviewer while batch is ${latest.status}.`);
    }

    let reviewerId: number;
    if (this.opts.targetReviewerId != null) {
      reviewerId = this.opts.targetReviewerId;
    } else {
      const reviewers = (await this.api.getUsers()).filter(user => user.role === "REVIEWER");
      if (reviewers.length === 0) throw new Error("No REVIEWER users exist.");
      const fallback = reviewers.find(user => user.username === config.reviewer.username) ?? reviewers[0];
      reviewerId = fallback.id;
    }

    if (latest.assignedReviewer?.id === reviewerId) {
      return { id: reviewerId, username: "", role: "REVIEWER" };
    }
    await this.api.assignReviewer(latest.id, reviewerId);
    this.store.record(this.label, "reviewer:assigned", { batchId: latest.id, reviewerId });
    await this.ui.goto(`/admin/batches?status=REVIEW_PENDING&search=${encodeURIComponent(latest.parentBatchId)}`);
    await this.ui.screenshot("reviewer-assigned");
    return { id: reviewerId, username: "", role: "REVIEWER" };
  }

  async waitForCompleted(batchId: number): Promise<void> {
    await waitFor(
      `batch ${batchId} to complete`,
      () => this.api.getBatchStatus(batchId),
      state => state.status === "COMPLETED",
      { timeoutMs: config.reviewTimeoutMs, intervalMs: 5_000 }
    );
    this.store.record(this.label, "batch:completed", { batchId });
  }

  private async refreshBatch(batchId: number): Promise<Batch> {
    const batches = await this.api.getBatches();
    const batch = batches.find(item => item.id === batchId);
    if (!batch) throw new Error(`Batch ${batchId} not found.`);
    this.store.batch = batch;
    return batch;
  }
}
