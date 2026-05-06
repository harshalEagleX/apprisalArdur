import type { Browser } from "@playwright/test";
import { AdminAgent, ReviewerAgent } from "../agents";
import { ScenarioStore } from "../state/store";
import { writeScenarioReport } from "./report";
import { Scheduler } from "./scheduler";

export type ScenarioResult = {
  reportPath: string;
  store: ScenarioStore;
};

export class ScenarioRunner {
  private readonly scheduler = new Scheduler();
  readonly store = new ScenarioStore();

  constructor(private readonly browser: Browser) {}

  async fullLifecycle(): Promise<ScenarioResult> {
    const admin = new AdminAgent(this.browser, this.store);
    const reviewer = new ReviewerAgent(this.browser, this.store);

    try {
      await this.scheduler.parallel([
        () => admin.bootstrap(),
        () => reviewer.bootstrap()
      ] as const);

      const batch = await admin.createOrReuseBatch();
      const readyBatch = await admin.runQcIfNeeded(batch);
      await admin.assignReviewer(readyBatch);

      const qcResult = await reviewer.waitForAssignedResult();
      await reviewer.completeReview(qcResult.id);
      await admin.waitForCompleted(readyBatch.id);

      const reportPath = await writeScenarioReport(this.store, "full-lifecycle");
      return { reportPath, store: this.store };
    } finally {
      await Promise.allSettled([admin.stop(), reviewer.stop()]);
    }
  }
}
