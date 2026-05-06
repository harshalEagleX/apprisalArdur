import { EventEmitter } from "node:events";

export type SimulationEvent = {
  topic: string;
  payload?: unknown;
  at: string;
};

export class EventBus {
  private readonly emitter = new EventEmitter();

  publish(topic: string, payload?: unknown): void {
    this.emitter.emit(topic, { topic, payload, at: new Date().toISOString() } satisfies SimulationEvent);
  }

  once(topic: string, timeoutMs = 60_000): Promise<SimulationEvent> {
    return new Promise((resolve, reject) => {
      const timer = setTimeout(() => {
        this.emitter.off(topic, listener);
        reject(new Error(`Timed out waiting for event ${topic}`));
      }, timeoutMs);
      const listener = (event: SimulationEvent) => {
        clearTimeout(timer);
        resolve(event);
      };
      this.emitter.once(topic, listener);
    });
  }
}
