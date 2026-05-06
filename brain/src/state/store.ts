import type { Batch, QCResult } from "../types/domain";

export type ScenarioEvent = {
  at: string;
  actor: string;
  event: string;
  payload?: unknown;
};

export class ScenarioStore {
  batch?: Batch;
  qcResults: QCResult[] = [];
  activeQcResultId?: number;
  events: ScenarioEvent[] = [];

  record(actor: string, event: string, payload?: unknown): void {
    const entry = { at: new Date().toISOString(), actor, event, payload };
    this.events.push(entry);
    const detail = payload === undefined ? "" : ` ${JSON.stringify(payload)}`;
    console.log(`[brain:${actor}] ${event}${detail}`);
  }

  recent(limit = 20): ScenarioEvent[] {
    return this.events.slice(-limit);
  }
}
