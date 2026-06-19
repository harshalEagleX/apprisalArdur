// Shared types for the audit module

export type NodeType =
  | "BATCH"
  | "FILE"
  | "QC_RUN"
  | "REVIEW_SESSION"
  | "DECISION"
  | "SUBMIT";

export type ViewMode = "ALL" | "BY_BATCH" | "BY_FILE" | "LIST";

/**
 * A supporting document (contract / engagement letter) is read for cross-document
 * checks but never QC'd on its own, so its file status stays PENDING permanently.
 * Surfacing "Pending" implies it's stuck — these helpers relabel it "Supporting".
 */
export function isSupportingPending(status: string, fileType?: string | null): boolean {
  return status === "PENDING" && (fileType === "CONTRACT" || fileType === "ENGAGEMENT");
}
export function nodeStatusLabel(status: string, fileType?: string | null): string {
  return isSupportingPending(status, fileType) ? "Supporting" : status.replace(/_/g, " ");
}

export interface GraphNode {
  id: string;
  label: string;
  type: NodeType;
  status: string;
  meta: Record<string, string | number | null | undefined>;
  x?: number;
  y?: number;
}

export interface GraphLink {
  source: string | GraphNode;
  target: string | GraphNode;
  type: string;
  timestamp?: string;
}

export interface GraphData {
  nodes: GraphNode[];
  links: GraphLink[];
}

export interface BatchSummary {
  id: number;
  parentBatchId: string;
  status: string;
  client?: { name: string; code: string };
  fileCount: number;
  assignedReviewer?: { id: number; username: string };
}

// Analytics data shapes (from Java AnalyticsService)
export interface AnalyticsOverview {
  totalFilesProcessed: number;
  activeSessions: number;
  // These averages are null when no files were processed in the window.
  avgOcrAccuracy: number | null;
  avgRulePassRate: number | null;
  avgProcessingSeconds: number | null;
  cacheHitRate: number;
  totalBatches: number;
  pendingReview: number;
  periodDays: number;
}

export interface TrendPoint {
  date: string;
  ocrAccuracy: number | null;
  passRate: number | null;
  fileCount: number;
}

export interface MlInsights {
  avgRulePassRate: number | null;
  decisionBreakdown: {
    // Java returns autoPass / toVerify / autoFail (counts) + *Pct fields
    autoPass: number;
    autoPassPct: number;
    toVerify: number;
    needsReviewPct: number;
    autoFail: number;
    autoFailPct: number;
  };
}

export interface SlaItem {
  ruleResultId: number;
  qcResultId: number;
  ruleId: string;
  ruleName: string;
  firstPresentedAt: string;
  filename: string;
}

export interface SlaDashboard {
  over4Hours: number;
  over8Hours: number;
  items: SlaItem[];
}

// Visual constants
export const NODE_COLOR: Record<NodeType, string> = {
  BATCH:          "#6366f1",
  FILE:           "#22c55e",
  QC_RUN:         "#ef4444",
  REVIEW_SESSION: "#f59e0b",
  DECISION:       "#f97316",
  SUBMIT:         "#06b6d4",
};

export const NODE_SIZE: Record<NodeType, number> = {
  BATCH:          14,
  FILE:           9,
  QC_RUN:         9,
  REVIEW_SESSION: 7,
  DECISION:       7,
  SUBMIT:         7,
};

export const EDGE_COLOR: Record<string, string> = {
  CONTAINS:      "#ffffff22",
  SUPPORTS:      "#22c55e55",
  HAS_QC_RUN:    "#ef444444",
  SUPERSEDED_BY: "#ef444466",
  HAS_SESSION:   "#f59e0b44",
  RESULTED_IN:   "#f9743644",
  LED_TO:        "#06b6d444",
  RE_REVIEW:     "#ef444466",
  ASSIGNS:       "#a78bfa33",
};
