import type { Role } from "./domain";

export type ActionKind =
  | "navigate"
  | "click"
  | "fill"
  | "select"
  | "upload"
  | "waitForState"
  | "api"
  | "evaluate"
  | "noop";

export interface BrainAction {
  kind: ActionKind;
  description: string;
  selector?: string;
  text?: string;
  value?: string;
  path?: string;
  targetState?: string;
  confidence: number;
}

export interface BrainContext {
  goal: string;
  role: Role;
  url?: string;
  dom?: string;
  backendState?: unknown;
  recentActions?: string[];
}

export interface EvaluationResult {
  ok: boolean;
  summary: string;
  issues: string[];
  nextActions: BrainAction[];
}
