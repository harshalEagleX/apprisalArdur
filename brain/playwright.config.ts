import { defineConfig, devices } from "@playwright/test";
import "dotenv/config";

const headless = process.env.HEADLESS !== "false";
const slowMo = Number(process.env.SLOW_MO_MS ?? 0);

export default defineConfig({
  testDir: "./src/runners",
  timeout: Number(process.env.SCENARIO_TIMEOUT_MS ?? 900_000),
  expect: { timeout: 15_000 },
  fullyParallel: true,
  workers: Number(process.env.PLAYWRIGHT_WORKERS ?? 5),
  reporter: [
    ["list"],
    ["html", { outputFolder: "playwright-report", open: "never" }],
    ["json", { outputFile: "reports/playwright-results.json" }]
  ],
  use: {
    baseURL: process.env.APP_BASE_URL ?? "http://localhost:3000",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    video: "retain-on-failure",
    headless,
    launchOptions: { slowMo }
  },
  projects: [
    {
      name: "chromium-desktop",
      use: { ...devices["Desktop Chrome"], viewport: { width: 1440, height: 1000 } }
    }
  ],
  outputDir: "test-results"
});
