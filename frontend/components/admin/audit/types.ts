// Shared types for the audit module

export type NodeType =
  | "BATCH"
  | "FILE"
  | "REVIEW_SESSION"
  | "DECISION"
  | "RE_REVIEW"
  | "SUBMIT";

export type ViewMode = "ALL" | "BY_BATCH" | "BY_FILE" | "LIST";

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
  avgOcrAccuracy: number;
  avgRulePassRate: number;
  avgProcessingSeconds: number;
  cacheHitRate: number;
  totalBatches: number;
  pendingReview: number;
  periodDays: number;
}

export interface TrendPoint {
  date: string;
  ocrAccuracy: number;
  passRate: number;
  fileCount: number;
}

export interface MlInsights {
  avgRulePassRate: number;
  decisionBreakdown: {
    autoPassCount: number;
    autoPassPct: number;
    toVerifyCount: number;
    needsReviewPct: number;
    autoFailCount: number;
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
  REVIEW_SESSION: "#f59e0b",
  DECISION:       "#f97316",
  RE_REVIEW:      "#ef4444",
  SUBMIT:         "#06b6d4",
};

export const NODE_SIZE: Record<NodeType, number> = {
  BATCH:          14,
  FILE:           9,
  REVIEW_SESSION: 7,
  DECISION:       7,
  RE_REVIEW:      9,
  SUBMIT:         7,
};

export const EDGE_COLOR: Record<string, string> = {
  CONTAINS:    "#ffffff22",
  HAS_SESSION: "#f59e0b44",
  RESULTED_IN: "#f9743644",
  LED_TO:      "#06b6d444",
  RE_REVIEW:   "#ef444466",
  ASSIGNS:     "#a78bfa33",
};
