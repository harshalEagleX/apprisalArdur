import { test, expect } from "@playwright/test";
import { createFixtures } from "../fixtures/setup";
import { runLoadTest } from "../scenarios/load-test";
import { writeLoadTestReport } from "../orchestrator/report";
import { config } from "../config";

async function checkServices(): Promise<void> {
  const ocrUrl = `${config.javaBaseUrl.replace("8080", "5001")}/health`;
  try {
    const res = await fetch(ocrUrl, { signal: AbortSignal.timeout(10_000) });
    console.log(`[load-test] OCR service: ${res.ok ? "healthy" : "not healthy"} (${res.status})`);
  } catch {
    console.warn("[load-test] OCR service unreachable on :5001 — QC will fail");
  }
  try {
    const res = await fetch(`${config.javaBaseUrl}/api/me`, { signal: AbortSignal.timeout(5_000) });
    console.log(`[load-test] Java backend: ${res.status !== 0 ? "reachable" : "unreachable"}`);
  } catch {
    console.warn("[load-test] Java backend unreachable on :8080");
  }
}

test.describe("load simulation — 10 concurrent users", () => {
  // Each QC job takes 5-15 min. With 5 serialized jobs + 5 review sessions
  // the ceiling is 5 × 15 min + review time = ~90 minutes.
  // Set hard ceiling at 90 min to cover worst case.
  test.setTimeout(5_400_000); // 90 min

  test("5 admin + 5 reviewer pairs complete full lifecycle concurrently", async ({ browser }) => {
    // Verify service health (reset-and-prep.sh already preloaded Ollama model)
    console.log("\n[load-test] Checking service health...");
    await checkServices();

    console.log("[load-test] Creating fixtures (clients + users)...");
    const fixture = await createFixtures();
    console.log(`[load-test] Fixture ready: ${fixture.clients.length} clients, ${fixture.admins.length} admins, ${fixture.reviewers.length} reviewers`);
    console.log("[load-test] ZIP paths:");
    fixture.zipPaths.forEach((p, i) => console.log(`  [${i + 1}] ${p}`));

    console.log("\n[load-test] Starting 10-user concurrent simulation...");
    const result = await runLoadTest(browser, fixture);

    const reportPath = await writeLoadTestReport(result);
    console.log(`\n[load-test] Report: ${reportPath}`);

    const completed = result.workers.filter(w => w.status === "completed").length;
    const failed = result.workers.filter(w => w.status === "failed");

    console.log("\n╔══════════════════════════════════════════════════╗");
    console.log("║              LOAD TEST RESULTS                  ║");
    console.log("╠══════════════════════════════════════════════════╣");
    console.log(`║  Workers completed : ${String(completed).padEnd(4)} / ${result.workers.length}                   ║`);
    console.log(`║  Total duration    : ${String((result.totalDurationMs / 1000).toFixed(1) + "s").padEnd(26)}║`);
    for (const w of result.workers) {
      const dLabel = (w.durationMs / 1000).toFixed(1) + "s";
      const decisions = w.store.events.filter(e => e.event === "decision:saved").length;
      const statusIcon = w.status === "completed" ? "✓" : "✗";
      console.log(`║  ${statusIcon} ${w.adminLabel}+${w.reviewerLabel}  batch=${w.batchId}  ${dLabel}  decisions=${decisions}  ║`);
    }
    console.log("╚══════════════════════════════════════════════════╝\n");

    if (failed.length > 0) {
      for (const w of failed) {
        console.error(`[load-test] FAILED worker ${w.adminLabel}: ${w.error}`);
      }
    }

    // At least 80% success rate required
    expect(completed, `Only ${completed}/${result.workers.length} workers succeeded`).toBeGreaterThanOrEqual(
      Math.ceil(result.workers.length * 0.8)
    );
  });
});
