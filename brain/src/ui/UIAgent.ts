import fs from "node:fs/promises";
import path from "node:path";
import { expect, type Browser, type BrowserContext, type Locator, type Page } from "@playwright/test";
import { config } from "../config";
import type { Role } from "../types/domain";
import type { ScenarioStore } from "../state/store";

export class UIAgent {
  readonly actor: string;
  context?: BrowserContext;
  page?: Page;

  constructor(
    private readonly browser: Browser,
    private readonly role: Role,
    private readonly store: ScenarioStore,
    label?: string
  ) {
    this.actor = label ?? role.toLowerCase();
  }

  async start(): Promise<Page> {
    this.context = await this.browser.newContext({
      baseURL: config.appBaseUrl,
      viewport: { width: 1440, height: 1000 }
    });
    this.page = await this.context.newPage();
    this.page.on("console", message => {
      if (message.type() === "error" && !message.text().includes("/_next/webpack-hmr")) {
        this.store.record(this.actor, "console:error", message.text());
      }
    });
    this.page.on("pageerror", error => this.store.record(this.actor, "page:error", error.message));
    return this.page;
  }

  async stop(): Promise<void> {
    await this.context?.close();
  }

  async login(username: string, password: string): Promise<void> {
    const page = this.requirePage();
    this.store.record(this.actor, "login:start", { username });
    const response = await this.requireContext().request.post(`${config.javaBaseUrl}/login`, {
      form: { username, password },
      maxRedirects: 0,
      timeout: 15_000
    });
    if (![0, 200, 301, 302].includes(response.status())) {
      throw new Error(`UI context login failed for ${this.role}: ${response.status()} ${await response.text()}`);
    }
    await page.goto("/", { waitUntil: "domcontentloaded", timeout: 15_000 });
    await page.waitForURL(url => !url.pathname.startsWith("/login"), { timeout: 15_000 });
    await expect(page).not.toHaveURL(/\/login/);
    this.store.record(this.actor, "login:complete", { url: page.url() });
  }

  async goto(pathname: string): Promise<void> {
    const page = this.requirePage();
    this.store.record(this.actor, "goto", pathname);
    await page.goto(pathname, { waitUntil: "domcontentloaded", timeout: 20_000 });
  }

  async clickByRole(role: Parameters<Page["getByRole"]>[0], name: RegExp | string): Promise<void> {
    const page = this.requirePage();
    this.store.record(this.actor, "click", { role, name: String(name) });
    await page.getByRole(role, { name }).click();
  }

  async fillByLabel(label: RegExp | string, value: string): Promise<void> {
    const page = this.requirePage();
    this.store.record(this.actor, "fill", { label: String(label) });
    await page.getByLabel(label).fill(value);
  }

  async read(): Promise<string> {
    const page = this.requirePage();
    return page.locator("body").innerText({ timeout: 5_000 });
  }

  async domSnapshot(maxChars = 12_000): Promise<string> {
    const text = await this.read().catch(error => `DOM read failed: ${String(error)}`);
    return text.slice(0, maxChars);
  }

  async screenshot(name: string): Promise<string> {
    const page = this.requirePage();
    const dir = path.resolve("reports", "screenshots");
    await fs.mkdir(dir, { recursive: true });
    const file = path.join(dir, `${Date.now()}-${this.actor}-${name}.png`);
    await page.screenshot({ path: file, fullPage: true });
    this.store.record(this.actor, "screenshot", file);
    return file;
  }

  locatorByText(text: string | RegExp): Locator {
    return this.requirePage().getByText(text);
  }

  requirePage(): Page {
    if (!this.page) throw new Error(`${this.role} UIAgent has not been started.`);
    return this.page;
  }

  requireContext(): BrowserContext {
    if (!this.context) throw new Error(`${this.role} UIAgent has no browser context.`);
    return this.context;
  }
}
