import type { Browser } from "@playwright/test";
import { Planner, Evaluator } from "../brain";
import { BackendClient } from "../state/backend";
import type { ScenarioStore } from "../state/store";
import { UIAgent } from "../ui/UIAgent";
import type { Role } from "../types/domain";

export abstract class BaseAgent {
  readonly ui: UIAgent;
  readonly api: BackendClient;
  readonly planner = new Planner();
  readonly evaluator = new Evaluator();

  protected constructor(
    browser: Browser,
    protected readonly role: Role,
    protected readonly store: ScenarioStore,
    label?: string
  ) {
    this.ui = new UIAgent(browser, role, store, label);
    this.api = new BackendClient();
  }

  async start(credentials: { username: string; password: string }): Promise<void> {
    await Promise.all([
      this.api.login(this.role, credentials),
      this.ui.start().then(() => this.ui.login(credentials.username, credentials.password))
    ]);
    this.store.record(this.ui.actor, "agent:start");
  }

  async stop(): Promise<void> {
    await Promise.allSettled([this.ui.stop(), this.api.dispose()]);
  }
}
