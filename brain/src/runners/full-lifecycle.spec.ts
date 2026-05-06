import { test, expect } from "@playwright/test";
import { ScenarioRunner } from "../orchestrator/scenarioRunner";
import { fullLifecycleScenario } from "../scenarios/full-lifecycle";

test.describe("multi-agent simulation", () => {
  test(fullLifecycleScenario.name, async ({ browser }) => {
    const runner = new ScenarioRunner(browser);
    const result = await runner.fullLifecycle();

    expect(result.store.batch?.id).toBeTruthy();
    expect(result.store.activeQcResultId).toBeTruthy();
    expect(result.store.events.some(event => event.event === "review:submitted")).toBe(true);
    expect(result.reportPath).toContain("full-lifecycle");
  });
});
