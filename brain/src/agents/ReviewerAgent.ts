import type { Browser } from "@playwright/test";
import { expect } from "@playwright/test";
import { config } from "../config";
import { waitFor } from "../state/wait";
import type { ScenarioStore } from "../state/store";
import type { QCRuleResult, QCResult } from "../types/domain";
import { BaseAgent } from "./BaseAgent";

export interface ReviewerAgentOptions {
  /** Override global config.reviewer credentials */
  credentials?: { username: string; password: string };
  /** Unique label for log prefixes (default: "reviewer") */
  label?: string;
}

function normalizedStatus(rule: QCRuleResult): string {
  return rule.status.toLowerCase();
}

function decisionFor(rule: QCRuleResult): "PASS" | "FAIL" {
  return normalizedStatus(rule) === "fail" ? "FAIL" : "PASS";
}

export class ReviewerAgent extends BaseAgent {
  private readonly opts: ReviewerAgentOptions;

  constructor(browser: Browser, store: ScenarioStore, options?: ReviewerAgentOptions) {
    super(browser, "REVIEWER", store, options?.label ?? "reviewer");
    this.opts = options ?? {};
  }

  private get creds() { return this.opts.credentials ?? config.reviewer; }
  private get label() { return this.ui.actor; }

  async bootstrap(): Promise<void> {
    await this.start(this.creds);
    // Retry once on ERR_ABORTED — the Next.js dev server occasionally drops
    // connections when too many contexts start simultaneously.
    for (let attempt = 1; attempt <= 2; attempt++) {
      try {
        await this.ui.goto("/reviewer/queue");
        await expect(this.ui.requirePage().getByRole("heading", { name: /verification queue/i })).toBeVisible({ timeout: 15_000 });
        return;
      } catch (err) {
        if (attempt === 2) throw err;
        this.store.record(this.label, "bootstrap:retry", { attempt, error: String(err).slice(0, 120) });
        await new Promise(r => setTimeout(r, 3_000));
      }
    }
  }

  async waitForAssignedResult(): Promise<QCResult> {
    const actions = await this.planner.decide({
      role: "REVIEWER",
      goal: "wait for assigned review queue item",
      dom: await this.ui.domSnapshot(),
      backendState: this.store.batch,
      recentActions: this.store.recent().map(event => `${event.actor}:${event.event}`)
    });
    this.store.record(this.label, "brain:plan", actions);

    const queue = await waitFor(
      "reviewer queue to contain assigned QC result",
      () => this.api.getReviewerQueue(),
      items => items.length > 0,
      { timeoutMs: config.reviewTimeoutMs, intervalMs: 4_000 }
    );
    const result = [...queue].sort((a, b) =>
      (b.failedCount - a.failedCount)
      || (b.verifyCount - a.verifyCount)
      || (new Date(a.processedAt).getTime() - new Date(b.processedAt).getTime())
    )[0];
    this.store.activeQcResultId = result.id;
    this.store.record(this.label, "queue:item-selected", { qcResultId: result.id });
    // Intentionally no navigation here — session/start is called first in
    // completeReview so the lock is established before the page's useEffect fires it.
    return result;
  }

  async completeReview(qcResultId: number): Promise<void> {
    // Establish session via API first so the page's auto-call is idempotent.
    const session = await this.api.startReviewSession(qcResultId, true);
    this.store.record(this.label, "session:started", { sessionToken: session.sessionToken });

    await this.ui.goto(`/reviewer/verify/${qcResultId}`);
    await expect(this.ui.requirePage().getByText(new RegExp(`QC Result #${qcResultId}`))).toBeVisible();
    await this.ui.screenshot("review-opened");

    const rules = await this.api.getRules(qcResultId);
    const actionable = rules.filter(rule => rule.reviewRequired && rule.reviewerVerified == null);
    this.store.record(this.label, "rules:loaded", { total: rules.length, actionable: actionable.length });

    for (const rule of actionable) {
      const decision = decisionFor(rule);
      const comment = decision === "FAIL"
        ? `Simulation marked ${rule.ruleId} as failed after reviewing evidence.`
        : undefined;
      // Retry up to 3 times on transient conflicts (409 optimistic lock, 500 save failed).
      for (let attempt = 1; attempt <= 3; attempt++) {
        try {
          await this.api.saveDecision({
            ruleResultId: rule.id,
            decision,
            comment,
            sessionToken: session.sessionToken,
            acknowledged: true
          });
          break;
        } catch (err) {
          const msg = String(err);
          const isRetryable = msg.includes("409") || msg.includes("500") || msg.includes("conflict") || msg.includes("CONFLICT");
          if (attempt === 3 || !isRetryable) throw err;
          this.store.record(this.label, "decision:retry", { ruleId: rule.ruleId, attempt, error: msg.slice(0, 80) });
          await new Promise(r => setTimeout(r, 2_000 * attempt));
        }
      }
      this.store.record(this.label, "decision:saved", { ruleId: rule.ruleId, decision });
    }

    const progress = await waitFor(
      `qc result ${qcResultId} to become submittable`,
      () => this.api.getReviewProgress(qcResultId),
      state => state.canSubmit,
      { timeoutMs: 60_000, intervalMs: 2_000 }
    );
    this.store.record(this.label, "review:submittable", progress);

    await this.ui.goto(`/reviewer/verify/${qcResultId}`);
    await this.ui.screenshot("before-submit");
    await this.api.submitReview(qcResultId, session.sessionToken, "Submitted by multi-agent simulation.");
    this.store.record(this.label, "review:submitted", { qcResultId });

    const evaluation = await this.evaluator.evaluate({
      role: "REVIEWER",
      goal: "review submitted and queue returns to stable state",
      dom: await this.ui.domSnapshot(),
      backendState: await this.api.getReviewProgress(qcResultId).catch(error => ({ error: String(error) })),
      recentActions: this.store.recent().map(event => `${event.actor}:${event.event}`)
    });
    this.store.record(this.label, "brain:evaluation", evaluation);
    if (!evaluation.ok) throw new Error(`Evaluator found review issues: ${evaluation.issues.join("; ")}`);
  }
}
