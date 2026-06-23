/**
 * SHAL — full lifecycle E2E (real Chrome, fully visible, no background work).
 *
 * Everything happens through the actual UI — there are no hidden API calls. An
 * on-page HUD narrates every single step and gives you Play / Pause control:
 *   • Pause  — freezes the script before the next action so you can inspect.
 *   • Resume — continues.
 *   • Step ▸ — (while paused) nudges a one-shot continue is not needed; Resume runs.
 *
 * Flow:
 *   ADMIN    : login → Clients (create tenant) → Users (create reviewer) →
 *              Batches (upload ZIP → Run QC → watch status → assign reviewer) → sign out
 *   REVIEWER : login → queue (open the assigned file) → read each finding and make a
 *              human-like Save Pass / Confirm Fail decision → submit → sign-off →
 *              rejection language + Copy all
 *
 * A structured log is written to brain/reports/demo-e2e-*.{json,md}.
 */
import { test, expect, type Page } from "@playwright/test";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const ADMIN = {
  username: process.env.ADMIN_USERNAME ?? "harshal@eaglexinfo.com",
  password: process.env.ADMIN_PASSWORD ?? "Admin123!",
};
const STAMP = Date.now();
const REVIEWER = {
  username: `reviewer_demo_${STAMP}`,
  password: "Review123!",
  email: `reviewer_demo_${STAMP}@demo.com`,
  fullName: "Demo Reviewer",
};
const ZIP = path.resolve(__dirname, "../../test-data/fantail_batch.zip");

// ── structured logging ──────────────────────────────────────────────────────
type Status = "OK" | "FAIL" | "INFO";
const EVENTS: Array<{ t: string; step: string; status: Status; detail?: unknown }> = [];
function log(step: string, status: Status, detail?: unknown) {
  const e = { t: new Date().toISOString(), step, status, detail };
  EVENTS.push(e);
  const d = detail !== undefined ? "  " + JSON.stringify(detail) : "";
  // eslint-disable-next-line no-console
  console.log(`[${status.padEnd(4)}] ${step}${d}`);
}
function flush() {
  const dir = path.resolve(__dirname, "../../reports");
  fs.mkdirSync(dir, { recursive: true });
  fs.writeFileSync(path.join(dir, "demo-e2e-log.json"), JSON.stringify(EVENTS, null, 2));
  const md = ["# SHAL — full lifecycle E2E log", "", `Run: ${new Date().toISOString()}`, ""]
    .concat(EVENTS.map(e => `- **${e.status}** \`${e.step}\`${e.detail !== undefined ? " — " + "`" + JSON.stringify(e.detail) + "`" : ""}`));
  fs.writeFileSync(path.join(dir, "demo-e2e-log.md"), md.join("\n"));
}

// ── on-page HUD: narration + Play/Pause, persists across navigations ─────────
async function installHud(page: Page) {
  await page.addInitScript(() => {
    const ROOT_ID = "shal-e2e-hud";
    function ensure() {
      if (document.getElementById(ROOT_ID) || !document.body) return;
      const hud = document.createElement("div");
      hud.id = ROOT_ID;
      hud.style.cssText =
        "position:fixed;z-index:2147483647;left:16px;bottom:16px;width:440px;max-width:46vw;" +
        "font:13px/1.45 -apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;color:#eef3f9;" +
        "background:rgba(13,18,26,.97);border:1px solid rgba(255,255,255,.14);border-radius:14px;" +
        "box-shadow:0 18px 54px rgba(0,0,0,.55);padding:13px 15px;backdrop-filter:blur(7px);";
      hud.innerHTML =
        '<div style="display:flex;align-items:center;gap:8px;margin-bottom:8px">' +
          '<span style="font-weight:800;font-size:10px;letter-spacing:.13em;color:#7fb3ff">APPRISAL · E2E DEMO</span>' +
          '<span id="e2e-phase" style="font-size:10px;letter-spacing:.08em;color:#8fa3b8"></span>' +
          '<span id="e2e-count" style="margin-left:auto;font-size:11px;color:#8fa3b8"></span>' +
        '</div>' +
        '<div id="e2e-step" style="font-size:13px;color:#eaf1f8;min-height:36px;font-weight:500"></div>' +
        '<div id="e2e-sub" style="font-size:11px;color:#90a2b6;margin-top:4px;min-height:14px"></div>' +
        '<div style="display:flex;gap:8px;margin-top:11px">' +
          '<button id="e2e-toggle" style="flex:1;cursor:pointer;border:1px solid rgba(255,255,255,.16);background:#1f6feb;color:#fff;border-radius:9px;padding:7px 10px;font-weight:700;font-size:12px">⏸ Pause</button>' +
          '<button id="e2e-continue" style="flex:1;cursor:pointer;border:1px solid rgba(255,255,255,.16);background:#21262d;color:#cdd9e5;border-radius:9px;padding:7px 10px;font-weight:700;font-size:12px;display:none">Continue ▸</button>' +
        '</div>';
      document.body.appendChild(hud);
      const toggle = hud.querySelector("#e2e-toggle") as HTMLButtonElement;
      toggle.addEventListener("click", () => {
        const paused = localStorage.getItem("__e2ePaused") === "1";
        localStorage.setItem("__e2ePaused", paused ? "0" : "1");
        render();
      });
      const cont = hud.querySelector("#e2e-continue") as HTMLButtonElement;
      cont.addEventListener("click", () => { localStorage.setItem("__e2eContinue", String(Date.now())); });
      function render() {
        const paused = localStorage.getItem("__e2ePaused") === "1";
        toggle.textContent = paused ? "▶ Resume" : "⏸ Pause";
        toggle.style.background = paused ? "#2ea043" : "#1f6feb";
        const waiting = localStorage.getItem("__e2eWaitUser") === "1";
        cont.style.display = waiting ? "block" : "none";
        cont.style.background = waiting ? "#fb8500" : "#21262d";
        cont.style.color = waiting ? "#1a1200" : "#cdd9e5";
        hud.style.borderColor = waiting ? "rgba(251,133,0,.85)" : "rgba(255,255,255,.14)";
        (hud.querySelector("#e2e-step") as HTMLElement).textContent = localStorage.getItem("__e2eStep") || "Starting demo…";
        (hud.querySelector("#e2e-sub") as HTMLElement).textContent = localStorage.getItem("__e2eSub") || "";
        (hud.querySelector("#e2e-count") as HTMLElement).textContent = localStorage.getItem("__e2eCount") || "";
        (hud.querySelector("#e2e-phase") as HTMLElement).textContent = localStorage.getItem("__e2ePhase") || "";
      }
      (window as unknown as { __e2eRender: () => void }).__e2eRender = render;
      setInterval(render, 180);
      render();
    }
    if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", ensure);
    else ensure();
    setInterval(ensure, 400); // survive SPA route changes / re-mounts
  });
}

let STEP_N = 0;
let PHASE = "";
async function setPhase(page: Page, phase: string) {
  PHASE = phase;
  await page.evaluate(p => localStorage.setItem("__e2ePhase", p), phase).catch(() => undefined);
}
// Narrate a step, honor Pause, then pause briefly so it is readable.
async function step(page: Page, text: string, sub = "") {
  STEP_N++;
  await page.evaluate(
    ({ text, sub, n }) => {
      localStorage.setItem("__e2eStep", text);
      localStorage.setItem("__e2eSub", sub);
      localStorage.setItem("__e2eCount", `step ${n}`);
      (window as unknown as { __e2eRender?: () => void }).__e2eRender?.();
    },
    { text, sub, n: STEP_N },
  ).catch(() => undefined);
  log(`${PHASE}.step.${STEP_N}`, "INFO", { text, ...(sub ? { sub } : {}) });
  // block while paused
  for (;;) {
    const paused = await page.evaluate(() => localStorage.getItem("__e2ePaused") === "1").catch(() => false);
    if (!paused) break;
    await page.waitForTimeout(250);
  }
  await page.waitForTimeout(550); // let the viewer read the narration
}

// Hand control to the human: show the Continue ▸ button and block until they
// click it — or until `until()` becomes true (e.g. the uploaded batch appears).
async function waitForUser(page: Page, prompt: string, sub: string, until?: () => Promise<boolean>) {
  STEP_N++;
  const baseline = await page.evaluate(() => localStorage.getItem("__e2eContinue") || "").catch(() => "");
  await page.evaluate(
    ({ prompt, sub, n }) => {
      localStorage.setItem("__e2eStep", prompt);
      localStorage.setItem("__e2eSub", sub);
      localStorage.setItem("__e2eCount", `step ${n} · waiting for you`);
      localStorage.setItem("__e2eWaitUser", "1");
      (window as unknown as { __e2eRender?: () => void }).__e2eRender?.();
    },
    { prompt, sub, n: STEP_N },
  ).catch(() => undefined);
  log(`${PHASE}.step.${STEP_N}`, "INFO", { text: prompt, sub, waitForUser: true });

  for (;;) {
    const clicked = await page.evaluate(b => (localStorage.getItem("__e2eContinue") || "") !== b, baseline).catch(() => false);
    if (clicked) { log(`${PHASE}.user_continue`, "OK", { via: "button" }); break; }
    if (until && (await until().catch(() => false))) { log(`${PHASE}.user_continue`, "OK", { via: "auto-detected" }); break; }
    await page.waitForTimeout(400);
  }
  await page.evaluate(() => { localStorage.setItem("__e2eWaitUser", "0"); (window as unknown as { __e2eRender?: () => void }).__e2eRender?.(); }).catch(() => undefined);
  await page.waitForTimeout(300);
}

// ── human-like decision: read the finding and decide like a reviewer ────────
function humanDecision(status: "fail" | "verify", message: string) {
  const msg = (message ?? "").toLowerCase();
  const hardDefect = /does not match|mismatch|prohibited term|signature.*missing|not marked.*revise|inconsistent/.test(msg);
  if (status === "fail" || hardDefect) {
    return { decision: "FAIL" as const, reason: `Confirmed defect after reading the evidence: "${(message ?? "").slice(0, 90)}"` };
  }
  return { decision: "PASS" as const, reason: "Reviewed the referenced section; finding is advisory/explained — confirming pass." };
}

test.describe.configure({ mode: "serial" });
test.use({ channel: "chrome" });

test("SHAL — full admin + reviewer lifecycle", async ({ page }) => {
  test.setTimeout(30 * 60 * 1000);
  await installHud(page);

  const clientName = `Demo Client ${STAMP}`;
  const shortCode = `D${String(STAMP).slice(-7)}`; // ≤10 chars, unique per run

  const nav = async (label: string, urlPart: string) => {
    await page.getByRole("link", { name: new RegExp(`^${label}$`, "i") }).first().click()
      .catch(async () => { await page.goto(`/admin/${urlPart}`, { waitUntil: "domcontentloaded" }); });
    await page.waitForURL(new RegExp(`/admin/${urlPart}`), { timeout: 15_000 }).catch(() => undefined);
  };

  try {
    // ═════════════════════════════ ADMIN ═════════════════════════════════════
    await setPhase(page, "admin");
    await page.goto("/login", { waitUntil: "domcontentloaded" });

    await step(page, "Admin signs in", `username ${ADMIN.username}`);
    await page.getByPlaceholder(/enter username/i).fill(ADMIN.username);
    await page.getByPlaceholder(/enter password/i).fill(ADMIN.password);
    await page.getByRole("button", { name: /sign in|log ?in/i }).click();
    await page.waitForURL(u => !u.pathname.startsWith("/login"), { timeout: 20_000 });
    log("admin.login", "OK", { url: page.url() });

    // ── CLIENTS ──
    await step(page, "Open the Clients tab", "admin → Clients");
    await nav("Clients", "clients");
    await step(page, "Click “New client” to open the create dialog");
    await page.getByRole("button", { name: /new client|create first client/i }).first().click();
    await step(page, `Type the organisation name`, clientName);
    await page.getByPlaceholder("Acme Lending").fill(clientName);
    await step(page, `Type the short code`, shortCode);
    await page.getByPlaceholder("ACME", { exact: true }).fill(shortCode);
    await step(page, "Click “Create” to save the client");
    await page.getByRole("button", { name: /^create$/i }).click();
    await expect(page.getByText(clientName).first()).toBeVisible({ timeout: 12_000 });
    log("admin.create_client", "OK", { clientName, shortCode });

    // ── USERS ──
    await step(page, "Open the Users tab", "admin → Users");
    await nav("Users", "users");
    await step(page, "Click “New user” to open the create dialog");
    await page.getByRole("button", { name: /new user|add first user/i }).first().click();
    await step(page, "Fill the reviewer’s username", REVIEWER.username);
    await page.getByPlaceholder("jane.smith").fill(REVIEWER.username);
    await step(page, "Fill the full name", REVIEWER.fullName);
    await page.getByPlaceholder("Jane Smith").fill(REVIEWER.fullName);
    await step(page, "Fill the email", REVIEWER.email);
    await page.getByPlaceholder("jane@firm.com").fill(REVIEWER.email);
    await step(page, "Set a password");
    await page.getByPlaceholder(/Min\. .* characters/i).fill(REVIEWER.password);
    await step(page, "Scope the reviewer to the new client", clientName);
    await page.locator("select").filter({ has: page.locator("option", { hasText: clientName }) })
      .first().selectOption({ label: clientName }).catch(() => undefined);
    await step(page, "Click “Create user” to save the reviewer");
    await page.getByRole("button", { name: /create user/i }).click();
    await expect(page.getByText(REVIEWER.username).first()).toBeVisible({ timeout: 12_000 });
    log("admin.create_reviewer", "OK", { username: REVIEWER.username });

    // ── BATCHES ──
    await step(page, "Open the Batches tab", "admin → Batches");
    await nav("Batches", "batches");
    await step(page, "Click “Upload batch” to open the upload dialog");
    await page.getByRole("button", { name: /upload batch|upload first batch/i }).first().click();
    await step(page, "Pick the client for this batch", clientName);
    await page.locator("select").filter({ has: page.locator("option", { hasText: clientName }) })
      .first().selectOption({ label: `${clientName} (${shortCode})` }).catch(() => undefined);
    const runQcVisible = () => page.getByRole("button", { name: /^run qc$/i }).first().isVisible();
    if (process.env.AUTO_UPLOAD === "1") {
      await step(page, "Attach the appraisal ZIP archive", path.basename(ZIP));
      await page.locator('input[type="file"]').setInputFiles(ZIP);
      await step(page, "Click “Upload batch” to validate and store the documents");
      // scope to the dialog — the page header also has an “Upload batch” button
      await page.getByRole("dialog").getByRole("button", { name: /^upload batch$/i }).first().click()
        .catch(async () => { await page.getByRole("button", { name: /^upload batch$/i }).last().click(); });
    } else {
      await waitForUser(
        page,
        "Your turn — attach the ZIP and click “Upload batch” in the dialog.",
        "Continuing automatically once the batch appears, or click Continue ▸.",
        runQcVisible,
      );
    }
    await expect(page.getByRole("button", { name: /^run qc$/i }).first()).toBeVisible({ timeout: 120_000 });
    log("admin.upload_batch", "OK");

    // ── RUN QC ──
    await step(page, "Click “Run QC” on the batch row", "deterministic extraction + 74 rules");
    await page.getByRole("button", { name: /^run qc$/i }).first().click();
    log("admin.run_qc", "OK");

    // ── WATCH STATUS until REVIEW_PENDING (the assign dropdown appears) ──
    const assignSel = page.getByRole("combobox", { name: /assign reviewer for/i }).first();
    let qcReady = false;
    for (let i = 0; i < 60; i++) {
      if (await assignSel.isVisible().catch(() => false)) { qcReady = true; break; }
      // read the visible status chip with a hard timeout so it can never hang
      const statusTxt = await page.locator("tbody tr td").nth(2).innerText({ timeout: 1500 }).catch(() => "processing");
      await step(page, "Waiting for QC to finish…", `status: ${statusTxt.replace(/\s+/g, " ").trim().slice(0, 40)} · check ${i + 1}`);
      await page.waitForTimeout(5_000);
      await page.reload({ waitUntil: "domcontentloaded" }).catch(() => undefined);
    }
    log("admin.qc_done", qcReady ? "OK" : "FAIL", { qcReady });
    expect(qcReady).toBeTruthy();

    // ── ASSIGN reviewer ──
    await step(page, "QC complete — assign the batch to the reviewer", REVIEWER.fullName);
    await assignSel.selectOption({ label: REVIEWER.fullName });
    log("admin.assign_reviewer", "OK", { reviewer: REVIEWER.fullName });
    await page.waitForTimeout(900);

    // ── LOGOUT ──
    await step(page, "Admin signs out");
    await page.getByRole("button", { name: /sign out/i }).click().catch(() => undefined);
    await page.waitForURL(/\/login/, { timeout: 12_000 }).catch(() => undefined);
    await page.context().clearCookies();
    log("admin.logout", "OK");

    // ═══════════════════════════ REVIEWER ═════════════════════════════════════
    await setPhase(page, "reviewer");
    await step(page, "Reviewer signs in", REVIEWER.username);
    await page.goto("/login", { waitUntil: "domcontentloaded" });
    await page.getByPlaceholder(/enter username/i).fill(REVIEWER.username);
    await page.getByPlaceholder(/enter password/i).fill(REVIEWER.password);
    await page.getByRole("button", { name: /sign in|log ?in/i }).click();
    await page.waitForURL(u => !u.pathname.startsWith("/login"), { timeout: 20_000 });
    log("reviewer.login", "OK", { url: page.url() });

    await step(page, "Open the review queue");
    await page.goto("/reviewer/queue", { waitUntil: "domcontentloaded" });
    await step(page, "Click the assigned appraisal to start reviewing");
    await page.locator('a[href*="/reviewer/verify/"]').first().click();
    await page.waitForURL(/\/reviewer\/verify\//, { timeout: 20_000 });
    log("reviewer.open_file", "OK", { url: page.url() });

    // enumerate the findings that need a decision straight from the rendered cards
    await page.locator('[id^="rule-"]').first().waitFor({ timeout: 20_000 }).catch(() => undefined);
    const actionableIds: string[] = await page.locator('[id^="rule-"]').evaluateAll(els =>
      els
        .filter(el => Array.from(el.querySelectorAll("button")).some(b => /save pass|save fail|confirm fail|override to pass/i.test(b.textContent || "")))
        .map(el => el.id),
    );
    log("reviewer.rules_loaded", "OK", { actionable: actionableIds.length });
    await step(page, `The reviewer screen lists every QC finding`, `${actionableIds.length} findings need a human decision`);

    // verify rules enforce an 8s forced-reading timer before buttons unlock
    await step(page, "Reading the findings before deciding…", "verify rules enforce an 8s reading timer");
    await page.waitForTimeout(8_800);

    let decided = 0;
    for (const id of actionableIds) {
      const card = page.locator(`#${id}`);
      try {
        await card.scrollIntoViewIfNeeded({ timeout: 5_000 });
        const isFailRule = (await card.getByRole("button", { name: /confirm fail/i }).count()) > 0;
        const message = (await card.locator("p").first().innerText({ timeout: 2000 }).catch(() => "")) || "";
        const ruleTag = (await card.locator("span.font-mono").first().innerText({ timeout: 2000 }).catch(() => id)) || id;
        const { decision, reason } = humanDecision(isFailRule ? "fail" : "verify", message);

        await step(
          page,
          `${ruleTag}: ${decision === "FAIL" ? "Confirm Fail" : "Save Pass"}`,
          reason.slice(0, 110),
        );

        // blocking-verify rules require acknowledging the referenced sections
        const ack = card.getByRole("checkbox").first();
        if ((await ack.isVisible().catch(() => false)) && !(await ack.isChecked().catch(() => false))) {
          await ack.check().catch(() => undefined);
        }
        // override-to-pass on a FAIL rule needs a ≥20 char justification
        if (decision === "PASS" && isFailRule) {
          const note = reason.length >= 20 ? reason : `${reason} — reviewer override confirmed.`;
          await card.getByRole("textbox").first().fill(note).catch(() => undefined);
        }
        const btnName =
          decision === "FAIL"
            ? (isFailRule ? /confirm fail/i : /save fail/i)
            : (isFailRule ? /override to pass/i : /save pass/i);
        const btn = card.getByRole("button", { name: btnName }).first();
        await expect(btn).toBeEnabled({ timeout: 12_000 });
        await btn.click();
        decided++;
        log(`reviewer.decide.${ruleTag}`, "OK", { decision, button: btnName.source });
        await page.waitForTimeout(350);
      } catch (err) {
        log(`reviewer.decide.${id}`, "FAIL", { error: String(err).slice(0, 160) });
      }
    }
    log("reviewer.decisions_done", "INFO", { decided, expected: actionableIds.length });

    // ── SUBMIT review → sign-off dialog → confirm ──
    await step(page, "All findings decided — submit the review");
    const submitBtn = page.getByRole("button", { name: /submit review|submit \(\d+ left\)/i }).first();
    await expect(submitBtn).toBeEnabled({ timeout: 30_000 });
    await submitBtn.click();
    log("reviewer.submit.click", "OK");
    await step(page, "Confirm sign-off in the dialog");
    const dialog = page.getByRole("dialog");
    await dialog.waitFor({ timeout: 10_000 }).catch(() => undefined);
    await dialog.getByRole("button", { name: /submit review/i }).first().click({ timeout: 10_000 })
      .catch(async () => { await page.getByRole("button", { name: /submit review/i }).last().click().catch(() => undefined); });
    await page.waitForURL(/\/reviewer\/submitted\//, { timeout: 25_000 }).catch(() => undefined);
    log("reviewer.submitted", page.url().includes("/submitted/") ? "OK" : "INFO", { url: page.url() });

    // ── REJECTION LANGUAGE + Copy all ──
    const copyAll = page.getByRole("button", { name: /copy all/i }).first();
    if (await copyAll.isVisible().catch(() => false)) {
      await step(page, "Copy the generated rejection language for the appraiser");
      await copyAll.click();
      log("reviewer.copy_all_rejection", "OK");
    } else {
      log("reviewer.copy_all_rejection", "INFO", { note: "no rejection block rendered" });
    }

    await step(page, "Lifecycle complete ✓", `${decided} findings decided · review submitted`);
    log("lifecycle", "OK", { decided });
  } finally {
    flush();
  }
});
