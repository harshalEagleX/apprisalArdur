/**
 * API client — all calls go to the Java backend on port 8080.
 * Two roles: ADMIN and REVIEWER only.
 *
 * Authentication strategy: HttpOnly "jwt" cookie set by the backend on login.
 * The browser sends it automatically via credentials:"include". JavaScript
 * never reads or writes the token — this eliminates the XSS token-theft vector.
 */

import { adminBatchTimeline, elapsedMs } from "@/lib/adminBatchTimeline";
import { JAVA } from "@/lib/config";

function normalizeHeaders(headers?: HeadersInit): Record<string, string> {
  const normalized: Record<string, string> = {};
  if (!headers) return normalized;
  if (headers instanceof Headers) {
    headers.forEach((value, key) => { normalized[key] = value; });
    return normalized;
  }
  if (Array.isArray(headers)) {
    for (const [key, value] of headers) normalized[key] = value;
    return normalized;
  }
  return { ...headers };
}

async function readErrorMessage(res: Response, fallback: string): Promise<string> {
  const text = await res.text();
  if (!text) return fallback;
  try {
    const parsed = JSON.parse(text) as { error?: unknown; message?: unknown };
    const message = typeof parsed.message === "string" ? parsed.message : parsed.error;
    if (typeof message === "string" && message.trim()) {
      return sanitizeErrorMessage(message);
    }
    return fallback;
  } catch {
    return sanitizeErrorMessage(text);
  }
}

function sanitizeErrorMessage(message: string): string {
  const clean = message.trim();
  if (!clean) return "Something went wrong. Please try again.";
  if (clean.includes("Unexpected row count") || clean.includes("OptimisticLocking") || clean.includes("StaleObjectState")) {
    return "This item was updated a moment ago. Refresh the page to see the latest saved decision before trying again.";
  }
  if (clean.includes("Read timed out")) {
    return "The request took too long to finish. Please try again in a moment.";
  }
  if (clean.includes("TOO_MANY_REQUESTS") || clean.includes("Too many login")) {
    return "Too many login attempts. Please wait 5 minutes before trying again.";
  }
  return clean;
}

// Default request timeout: 30 s for data calls, 90 s for heavy OCR triggers.
const DEFAULT_TIMEOUT_MS = 30_000;
const LONG_TIMEOUT_MS    = 90_000;

const LONG_TIMEOUT_PATHS = ["/api/qc/process/", "/api/admin/batches/upload", "/qc/process"];
const ADMIN_BATCH_TIMELINE_PATHS = [
  "/api/admin/batches",
  "/api/qc/process/",
  "/api/qc/cancel/",
  "/api/qc/progress/",
  "/api/qc/reconcile",
];

function shouldLogAdminBatchTimeline(path: string): boolean {
  return ADMIN_BATCH_TIMELINE_PATHS.some(p => path.includes(p));
}

async function apiFetch<T>(path: string, options?: RequestInit & { timeoutMs?: number }): Promise<T> {
  let res: Response;
  const { headers, timeoutMs, ...rest } = options ?? {};

  const timeout = timeoutMs
    ?? (LONG_TIMEOUT_PATHS.some(p => path.includes(p)) ? LONG_TIMEOUT_MS : DEFAULT_TIMEOUT_MS);

  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeout);
  const started = performance.now();
  const method = rest.method ?? "GET";
  const timeline = shouldLogAdminBatchTimeline(path);

  if (timeline) {
    adminBatchTimeline("frontend_api_request_start", {
      path,
      method,
      timeout_ms: timeout,
    });
  }

  try {
    res = await fetch(`${JAVA}${path}`, {
      // credentials:"include" sends the HttpOnly jwt cookie on every request.
      credentials: "include",
      signal: controller.signal,
      ...rest,
      headers: {
        "Content-Type": "application/json",
        ...normalizeHeaders(headers),
      },
    });
  } catch (err) {
    if (timeline) {
      adminBatchTimeline("frontend_api_request_failed", {
        path,
        method,
        elapsed_ms: elapsedMs(started),
        error: err instanceof Error ? err.message : String(err),
      });
    }
    if (err instanceof DOMException && err.name === "AbortError") {
      throw new Error(`Request timed out after ${timeout / 1000}s. Please try again.`);
    }
    // Network error or CORS failure (e.g. backend redirected to /login cross-origin).
    if (typeof window !== "undefined"
        && err instanceof TypeError
        && window.location.pathname !== "/login") {
      window.location.href = "/login";
    }
    throw err;
  } finally {
    clearTimeout(timer);
  }

  if (timeline) {
    adminBatchTimeline("frontend_api_response_received", {
      path,
      method,
      status: res.status,
      ok: res.ok,
      elapsed_ms: elapsedMs(started),
    });
  }

  if (res.status === 401 || res.status === 302) {
    if (typeof window !== "undefined") window.location.href = "/login";
    throw new Error("Unauthenticated");
  }
  if (res.status === 403) throw new Error("Access denied");
  if (res.status === 429) throw new Error("Too many requests. Please wait before trying again.");

  if (!res.ok) {
    if (timeline) {
      adminBatchTimeline("frontend_api_response_rejected", {
        path,
        method,
        status: res.status,
        elapsed_ms: elapsedMs(started),
      });
    }
    throw new Error(await readErrorMessage(res, `Request failed (${res.status})`));
  }

  const text = await res.text();
  if (timeline) {
    adminBatchTimeline("frontend_api_response_parsed", {
      path,
      method,
      status: res.status,
      elapsed_ms: elapsedMs(started),
      response_bytes: text.length,
    });
  }
  return text ? JSON.parse(text) : ({} as T);
}

// ── Session expiry tracking ────────────────────────────────────────────────────
const SESSION_EXPIRES_KEY = "shal_session_expires_at";
const SESSION_TTL_MS = 24 * 60 * 60 * 1_000; // 24 h — matches JwtUtils expiry

/** Record session start time after a successful login. */
function recordSessionStart(): void {
  if (typeof window === "undefined") return;
  sessionStorage.setItem(SESSION_EXPIRES_KEY, String(Date.now() + SESSION_TTL_MS));
}

/** Returns milliseconds until the JWT cookie is expected to expire, or null if unknown. */
export function sessionMsRemaining(): number | null {
  if (typeof window === "undefined") return null;
  const raw = sessionStorage.getItem(SESSION_EXPIRES_KEY);
  if (!raw) return null;
  const expiresAt = Number(raw);
  return Number.isFinite(expiresAt) ? Math.max(0, expiresAt - Date.now()) : null;
}

/** Clear the session-expiry record on logout. */
function clearSessionRecord(): void {
  if (typeof window !== "undefined") sessionStorage.removeItem(SESSION_EXPIRES_KEY);
}

// ── Auth ──────────────────────────────────────────────────────────────────────

/**
 * Authenticate with username + password.
 *
 * The backend sets an HttpOnly "jwt" cookie on success. No token storage in
 * JavaScript — the browser manages the cookie automatically from here on.
 * A form-login POST to /login establishes the session cookie (JSESSIONID) as
 * well, needed for WebSocket handshake verification.
 */
export async function login(username: string, password: string): Promise<void> {
  const res = await fetch(`${JAVA}/api/auth/authenticate`, {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username, password }),
  });

  if (res.status === 429) {
    throw new Error("Too many login attempts. Please wait 5 minutes before trying again.");
  }
  if (!res.ok) {
    throw new Error("Invalid username or password");
  }
  // jwt HttpOnly cookie is now set by the backend — record expiry for the
  // session-expiry warning hook, then nothing else needed from JS.
  recordSessionStart();

  // Also establish a session cookie for WebSocket auth fallback path.
  const form = new URLSearchParams({ username, password });
  await fetch(`${JAVA}/login`, {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body: form.toString(),
    redirect: "manual",
  });
  // Ignore session login result — primary auth is the jwt cookie above.
}

export async function logout(): Promise<void> {
  clearSessionRecord();
  // Clear jwt cookie server-side.
  await fetch(`${JAVA}/api/auth/logout`, {
    method: "POST",
    credentials: "include",
  }).catch(() => {/* ignore network errors on logout */});

  // Also invalidate the Spring session.
  await fetch(`${JAVA}/logout`, {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body: "",
    redirect: "manual",
  }).catch(() => {/* ignore */});
}

export async function getMe(): Promise<{ role: "ADMIN" | "REVIEWER"; username: string }> {
  return apiFetch("/api/me");
}

export interface UserProfile {
  id: number;
  username: string;
  fullName: string | null;
  email: string | null;
  role: "ADMIN" | "REVIEWER";
  active: boolean;
  lastLoginAt: string | null;
  createdAt: string | null;
  client: { id: number; name: string; code: string } | null;
}

export const getProfile = () => apiFetch<UserProfile>("/api/me/profile");

export const updateProfile = (data: { fullName?: string; email?: string }) =>
  apiFetch<{ success: boolean; message?: string }>("/api/me/profile", {
    method: "PUT",
    body: JSON.stringify(data),
  });

export const changePassword = (currentPassword: string, newPassword: string, confirmPassword: string) =>
  apiFetch<{ success: boolean; message?: string }>("/api/me/change-password", {
    method: "POST",
    body: JSON.stringify({ currentPassword, newPassword, confirmPassword }),
  });

export const getPasswordPolicy = () =>
  apiFetch<{ minLength: number }>("/api/config/password-policy");

// ── Admin: Dashboard ──────────────────────────────────────────────────────────
export const getAdminDashboard    = () => apiFetch<Record<string, unknown>>("/api/admin/dashboard");
export const getReviewerDashboard = () => apiFetch<Record<string, unknown>>("/api/reviewer/dashboard");

// ── Admin: Users ──────────────────────────────────────────────────────────────
export const getUsers = (page = 0, size = 20) =>
  apiFetch<{ content: User[]; totalPages: number; number: number; totalElements?: number }>(`/api/admin/users?page=${page}&size=${size}`);

export async function getAllUsers(size = 100): Promise<User[]> {
  const first = await getUsers(0, size);
  const users = [...first.content];
  for (let page = 1; page < first.totalPages; page += 1) {
    const next = await getUsers(page, size);
    users.push(...next.content);
  }
  return users;
}

export const createUser = (data: Omit<User, "id" | "createdAt"> & { password: string; clientId?: number }) =>
  apiFetch<User>("/api/admin/users", { method: "POST", body: JSON.stringify(data) });

export const updateUser = (id: number, data: Partial<User> & { clientId?: number }) =>
  apiFetch<User>(`/api/admin/users/${id}`, { method: "PUT", body: JSON.stringify(data) });

export const deleteUser = (id: number) =>
  apiFetch(`/api/admin/users/${id}`, { method: "DELETE" });

/** Admin resets a user's password (audited). */
export const resetUserPassword = (id: number, password: string) =>
  apiFetch(`/api/admin/users/${id}/reset-password`, { method: "POST", body: JSON.stringify({ password }) });

/** Activate / deactivate a user — deactivated users can't sign in. */
export const setUserStatus = (id: number, active: boolean) =>
  apiFetch<User>(`/api/admin/users/${id}/status`, { method: "POST", body: JSON.stringify({ active }) });

// ── Admin: Clients ────────────────────────────────────────────────────────────
export const getClients = () => apiFetch<Client[]>("/api/admin/clients");

export interface ClientStat {
  batches: number; completed: number; files: number;
  successRate: number | null; lastActivity: string | null;
}
/** Per-client operational rollup, keyed by client id (string). */
export const getClientStats = () =>
  apiFetch<Record<string, ClientStat>>("/api/admin/clients/stats");

export interface ClientDetail {
  client: Client;
  stats: { batches: number; completed: number; successRate: number | null };
  recentBatches: { id: number; parentBatchId: string; status: string; fileCount: number; createdAt: string | null }[];
  users: { id: number; username: string; fullName: string | null; role: string; active: boolean }[];
}
/** Client drill-in: the client + stats + recent batches + its users. */
export const getClientDetail = (id: number) =>
  apiFetch<ClientDetail>(`/api/admin/clients/${id}`);

export const createClient = (name: string, code: string) =>
  apiFetch<Client>("/api/admin/clients", { method: "POST", body: JSON.stringify({ name, code }) });

// ── Admin: Batches ────────────────────────────────────────────────────────────
export const getAdminBatches = (page = 0, status?: string, search?: string) => {
  const params = new URLSearchParams({ page: String(page), size: "20" });
  if (status) params.set("status", status);
  if (search?.trim()) params.set("search", search.trim());
  return apiFetch<{ content: Batch[]; totalPages: number; number: number; totalElements?: number }>(
    `/api/admin/batches?${params}`
  );
};

export const getBatchById = (id: number) =>
  apiFetch<Batch>(`/api/admin/batches/${id}`);

/** The batch statuses the backend recognises — authoritative source for the admin
 * status filter so its options can never drift from the BatchStatus enum. */
export const getBatchStatuses = () =>
  apiFetch<string[]>(`/api/admin/batches/statuses`);

// ── Admin: Orders ─────────────────────────────────────────────────────────────
// "Order" is the canonical business entity: one real-world AMC order, with its
// documents, QC result, and lifecycle status reachable here regardless of which
// batch(es) it was uploaded through — this is what fixes the same order showing
// up duplicated across multiple re-uploaded batches.

export interface OrderSummary {
  id: number;
  transactionRef: string;
  status: string;
  documentStatus: "INCOMPLETE" | "UNMATCHED" | "READY_FOR_QC" | "QC_PROCESSING" | "NEEDS_REVIEW" | "COMPLETED" | "ERROR";
  propertyAddress?: string | null;
  amcCode?: string | null;
  orderNumber?: string | null;
  revisionNumber: number;
  client: Client | null;
  activeDocumentCount: number;
  assignedReviewer?: { id: number; username: string; fullName?: string } | null;
  reviewerAssignedAt?: string | null;
  createdAt?: string;
  updatedAt?: string;
}

export interface OrderDocument {
  id: number;
  filename: string;
  fileType: BatchFile["fileType"];
  status: string;
  contentVersion: number;
  active: boolean;
  supersededAt?: string | null;
  batchId?: number | null;
  createdAt?: string;
}

export interface OrderBatchHistoryEntry {
  id: number;
  parentBatchId: string;
  status: string;
  createdAt?: string;
}

export interface OrderDetail extends OrderSummary {
  documents: OrderDocument[];
  activeQcResult?: {
    id: number;
    qcDecision: string;
    finalDecision?: string | null;
    totalRules: number;
    passedCount: number;
    failedCount: number;
    verifyCount: number;
    processedAt?: string;
  } | null;
  batchHistory: OrderBatchHistoryEntry[];
}

export const getOrders = (page = 0, documentStatus?: string, search?: string) => {
  const params = new URLSearchParams({ page: String(page), size: "20" });
  if (documentStatus) params.set("documentStatus", documentStatus);
  if (search?.trim()) params.set("search", search.trim());
  return apiFetch<{ content: OrderSummary[]; totalPages: number; number: number; totalElements?: number }>(
    `/api/admin/orders?${params}`
  );
};

export const getOrderById = (id: number) =>
  apiFetch<OrderDetail>(`/api/admin/orders/${id}`);

export const getOrderStatuses = () =>
  apiFetch<string[]>(`/api/admin/orders/statuses`);

/** One-time, idempotent reconciliation: links pre-existing files with no
 * resolved Order (ingested before this feature existed) using the same
 * content-hash → orderId → propertySetName identity matching used at intake. */
export const runOrderBackfill = () =>
  apiFetch<{ filesProcessed: number; ordersTouched: number; ordersCreated: number; duplicatesFound: number }>(
    `/api/admin/orders/backfill`, { method: "POST" }
  );

/** Run QC for a single order — the order is the QC unit; it runs as its own job. */
export const processOrderQC = (orderId: number, model?: QCModelSelection) =>
  apiFetch<{ message: string; ordersResolved: number; startedOrderIds: number[]; alreadyRunningOrderIds: number[] }>(
    `/api/qc/process/order/${orderId}`,
    { method: "POST", body: JSON.stringify(model ?? {}), headers: { "Content-Type": "application/json" } }
  );

/** Run QC for several selected orders at once (each order runs as its own job). */
export const processOrdersQC = (orderIds: number[], model?: QCModelSelection) =>
  apiFetch<{ message: string; ordersRequested: number; ordersResolved: number; startedOrderIds: number[]; alreadyRunningOrderIds: number[]; ordersWithoutAppraisal: number[] }>(
    `/api/qc/process/orders`,
    { method: "POST", body: JSON.stringify({ orderIds, ...(model ?? {}) }), headers: { "Content-Type": "application/json" } }
  );

/** Allocate (or clear, when reviewerId is null) a single order to a reviewer. */
export const assignOrderReviewer = (orderId: number, reviewerId: number | null) =>
  apiFetch(`/api/admin/orders/${orderId}/assign`, {
    method: "POST", body: JSON.stringify({ reviewerId }), headers: { "Content-Type": "application/json" },
  });

export interface ServerNotification {
  id: number;
  type: string;
  title: string;
  message: string;
  link: string | null;
  read: boolean;
  createdAt: string | null;
}

/** The current user's persisted in-app notifications, newest first, with unread count. */
export const getNotifications = (limit = 30) =>
  apiFetch<{ items: ServerNotification[]; unreadCount: number }>(`/api/notifications?limit=${limit}`);

export const markNotificationRead = (id: number) =>
  apiFetch(`/api/notifications/${id}/read`, { method: "POST" });

export const markAllNotificationsRead = () =>
  apiFetch<{ markedRead: number }>(`/api/notifications/read-all`, { method: "POST" });

/** Current order load per reviewer + the average — powers the manual-assign fairness hint. */
export const getReviewerLoad = () =>
  apiFetch<{ loads: { reviewerId: number; count: number }[]; average: number; total: number }>(
    `/api/admin/orders/reviewer-load`
  );

/** Permanently delete an order and all of its documents (hard delete — not recoverable). */
export const deleteOrder = (orderId: number) =>
  apiFetch<{ success: boolean; deletedFiles: number; message: string }>(
    `/api/admin/orders/${orderId}`,
    { method: "DELETE" }
  );

/** Bulk-allocate several selected orders to one reviewer (or clear when null). */
export const bulkAssignOrderReviewer = (orderIds: number[], reviewerId: number | null) =>
  apiFetch<{ assignedCount: number; assignedOrderIds: number[]; skippedOrderIds: number[] }>(
    `/api/admin/orders/assign`,
    { method: "POST", body: JSON.stringify({ orderIds, reviewerId }), headers: { "Content-Type": "application/json" } }
  );

/** Auto-assign: system balances unassigned orders across active reviewers (only on click).
 * Pass orderIds to limit distribution to a selection; omit to distribute every unassigned order. */
export const autoAssignOrders = (orderIds?: number[]) =>
  apiFetch<{ message: string; assignedCount: number; distribution?: Record<string, number> }>(
    `/api/admin/orders/auto-assign`,
    { method: "POST", body: JSON.stringify(orderIds && orderIds.length ? { orderIds } : {}), headers: { "Content-Type": "application/json" } }
  );

/** Manually assign a NEEDS_ASSIGNMENT supporting file to a specific appraisal. */
/** Thrown when the assign target fails content cross-validation — the document's
 * own text points to a different order. Caught by the UI to offer an override. */
export class AddressMismatchError extends Error {}

/**
 * Thrown by {@link uploadBatch} when the backend rejects a ZIP (422) because its
 * folder/file structure is invalid. Carries the list of user-fixable issues so the
 * upload dialog can show exactly what to correct. The batch is never queued.
 */
export class BatchStructureError extends Error {
  issues: string[];
  constructor(issues: string[], message?: string) {
    super(message ?? "The ZIP can't be accepted until its structure is fixed.");
    this.name = "BatchStructureError";
    this.issues = issues;
  }
}

/**
 * Link a NEEDS_ASSIGNMENT file to an appraisal. By default the backend cross-checks
 * the document's own content against every appraisal in the batch and rejects
 * (409) an assignment that confidently points elsewhere; pass force=true to
 * override after the admin has manually verified it's correct.
 */
export async function assignFileToAppraisal(
  batchId: number, fileId: number, appraisalFileId: number, force = false,
): Promise<{ success: boolean; message: string }> {
  const res = await fetch(`${JAVA}/api/admin/batches/${batchId}/files/${fileId}/assign`, {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ appraisalFileId, force }),
  });
  if (res.status === 409) {
    const body = await res.json().catch(() => ({}));
    throw new AddressMismatchError(
      typeof body.message === "string" ? body.message : "This document appears to belong to a different order.");
  }
  if (!res.ok) {
    throw new Error(await readErrorMessage(res, `Request failed (${res.status})`));
  }
  const text = await res.text();
  return text ? JSON.parse(text) : ({ success: true, message: "" });
}

/** Change a file's document type (e.g. CONTRACT → APPRAISAL_XML after misclassification). */
export const reclassifyBatchFile = (batchId: number, fileId: number, fileType: string) =>
  apiFetch<{ success: boolean; message: string }>(
    `/api/admin/batches/${batchId}/files/${fileId}/reclassify`,
    { method: "POST", body: JSON.stringify({ fileType }) },
  );

export type SystemHealth = {
  degraded: boolean;
  pool: { active?: number; idle?: number; total?: number; waiting?: number; max?: number };
};

// DB connection-pool health — drives the admin "system under load" banner.
export const getSystemHealth = () =>
  apiFetch<SystemHealth>("/api/admin/system/health");

// ── DocStats (per-appraisal QC timing breakdown) ────────────────────────────
export interface DocStatSummary {
  id: number;
  batchFileId: number | null;
  batchId: number | null;
  filename: string | null;
  clientName: string | null;
  qcDecision: string | null;
  totalMs: number | null;
  ruleEngineMs: number | null;
  measuredPipelineMs: number | null;
  ruleCount: number | null;
  slowestStageLabel: string | null;
  slowestStageMs: number | null;
  slowestSectionLabel: string | null;
  slowestSectionMs: number | null;
  slowestRuleId: string | null;
  slowestRuleName: string | null;
  slowestRuleMs: number | null;
  llmCalls: number | null;
  llmInferenceMs: number | null;
  llmThrottleWaitMs: number | null;
  rateLimitHits: number | null;
  createdAt: string | null;
}
export interface DocStatStage {
  // `stage` is the stable key; the display name is derived from it via lib/stageLabels.
  // `label` is no longer sent by the backend (kept optional only as a legacy fallback).
  stage: string; label?: string; ms: number; pctOfPipeline: number;
  llmCalls: number; inferenceMs: number; throttleWaitMs: number;
}
export interface DocStatSection { section: string; label: string; ms: number; ruleCount: number; pctOfRules: number; }
export interface DocStatRule {
  ruleId: string; ruleName: string; section: string; status: string; ms: number;
  confidence: number; llmCalls: number; llmMs: number; throttleMs: number;
}
export interface DocStatDetail extends DocStatSummary {
  clientId: number | null;
  stages: DocStatStage[];
  sections: DocStatSection[];
  rules: DocStatRule[];
}
export interface Pctl { p50: number; p95: number; p99: number; min: number; max: number; avg: number; count: number; }
export interface DocStatBatchRollup {
  batchId: number; clientName: string; appraisalCount: number; lastRun: string;
  totalMs: Pctl; ruleEngineMs: Pctl; pipelineMs: Pctl;
}
export interface DocStatRuleRank {
  ruleId: string; ruleName: string; section: string;
  avgMs: number; maxMs: number; llmCalls: number; runs: number; llmRuns: number; pctLlm: number;
  avgConfidence: number; confidencePerMs: number;
}
export interface DocStatTrendPoint {
  id: number; at: string; filename: string;
  totalMs: number; ruleEngineMs: number; inferenceMs: number; throttleWaitMs: number;
}
export interface DocStatDelta { current: number; previous: number; deltaMs: number; pct: number; }
export interface DocStatCompare {
  current: DocStatDetail;
  previous: DocStatDetail | null;
  delta?: { totalMs: DocStatDelta; ruleEngineMs: DocStatDelta; llmInferenceMs: DocStatDelta; llmThrottleWaitMs: DocStatDelta };
}

export const getDocStats = (page = 0, q?: string, batchId?: number, size = 20) => {
  const params = new URLSearchParams({ page: String(page), size: String(size) });
  if (q) params.set("q", q);
  if (batchId != null) params.set("batchId", String(batchId));
  return apiFetch<{ content: DocStatSummary[]; number: number; totalPages: number; totalElements: number }>(
    `/api/admin/doc-stats?${params.toString()}`);
};

export const getDocStatDetail = (id: number) =>
  apiFetch<DocStatDetail>(`/api/admin/doc-stats/${id}`);

export const getDocStatBatches = () =>
  apiFetch<DocStatBatchRollup[]>(`/api/admin/doc-stats/batches`);

export const getDocStatRuleRanking = () =>
  apiFetch<DocStatRuleRank[]>(`/api/admin/doc-stats/rules/ranking`);

export const getDocStatThresholds = () =>
  apiFetch<Record<string, number>>(`/api/admin/doc-stats/thresholds`);

export const getDocStatTrend = (filename?: string, limit = 30) => {
  const params = new URLSearchParams({ limit: String(limit) });
  if (filename) params.set("filename", filename);
  return apiFetch<DocStatTrendPoint[]>(`/api/admin/doc-stats/trend?${params.toString()}`);
};

export const getDocStatCompare = (id: number) =>
  apiFetch<DocStatCompare>(`/api/admin/doc-stats/${id}/compare`);

export const getBatchStatus = (id: number) =>
  apiFetch<{
    status: string;
    totalFiles: number;
    processingTotalFiles: number;
    completedFiles: number;
    errorMessage?: string;
    updatedAt?: string;
  }>(`/api/admin/batches/${id}/status`);

export async function uploadBatch(
  file: File,
  clientId: number
): Promise<{ batchId: number; parentBatchId: string; fileCount: number }> {
  const started = performance.now();
  adminBatchTimeline("frontend_upload_api_start", {
    filename: file.name,
    file_size_bytes: file.size,
    client_id: clientId,
  });
  const fd = new FormData();
  fd.append("file", file);
  fd.append("clientId", String(clientId));
  try {
    const res = await fetch(`${JAVA}/api/admin/batches/upload`, {
      method: "POST",
      credentials: "include",
      body: fd,
    });
    adminBatchTimeline("frontend_upload_api_response", {
      status: res.status,
      ok: res.ok,
      elapsed_ms: elapsedMs(started),
    });
    if (!res.ok) {
      adminBatchTimeline("frontend_upload_api_rejected", {
        status: res.status,
        elapsed_ms: elapsedMs(started),
      });
      // 422 = structural rejection carrying a fixable issue list.
      if (res.status === 422) {
        const body = (await res.json().catch(() => null)) as { error?: string; issues?: unknown } | null;
        const issues = Array.isArray(body?.issues)
          ? body!.issues.filter((i): i is string => typeof i === "string")
          : [];
        if (issues.length) {
          throw new BatchStructureError(issues, typeof body?.error === "string" ? body.error : undefined);
        }
        throw new Error(typeof body?.error === "string" ? body.error : `Upload failed (${res.status})`);
      }
      throw new Error(await readErrorMessage(res, `Upload failed (${res.status})`));
    }
    const parsed = await res.json();
    adminBatchTimeline("frontend_upload_api_complete", {
      batch_id: parsed.batchId,
      batch_ref: parsed.parentBatchId,
      file_count: parsed.fileCount,
      elapsed_ms: elapsedMs(started),
    });
    return parsed;
  } catch (err) {
    adminBatchTimeline("frontend_upload_api_failed", {
      filename: file.name,
      client_id: clientId,
      elapsed_ms: elapsedMs(started),
      error: err instanceof Error ? err.message : String(err),
    });
    throw err;
  }
}

// ── Admin: Bulk Batch Operations ──────────────────────────────────────────────

/**
 * Bulk-delete batches in parallel.
 */
export async function bulkDeleteBatches(
  batchIds: number[],
): Promise<{ succeeded: number[]; failed: number[] }> {
  const results = await Promise.allSettled(
    batchIds.map(id => deleteBatch(id))
  );
  const succeeded: number[] = [];
  const failed:    number[] = [];
  results.forEach((r, i) => {
    if (r.status === "fulfilled") succeeded.push(batchIds[i]);
    else failed.push(batchIds[i]);
  });
  return { succeeded, failed };
}

/**
 * Bulk-assign a reviewer to multiple batches in parallel.
 */
export async function bulkAssignReviewer(
  batchIds: number[],
  reviewerId: number,
): Promise<{ succeeded: number[]; failed: number[] }> {
  const results = await Promise.allSettled(
    batchIds.map(id => assignReviewer(id, reviewerId))
  );
  const succeeded: number[] = [];
  const failed:    number[] = [];
  results.forEach((r, i) => {
    if (r.status === "fulfilled") succeeded.push(batchIds[i]);
    else failed.push(batchIds[i]);
  });
  return { succeeded, failed };
}

export const reconcileStuckBatches = () =>
  apiFetch<{ stuckFound: number; retried: number; abandoned: number; pythonHealthy: boolean; message: string }>(
    "/api/qc/reconcile",
    { method: "POST" }
  );

export interface QCModelSelection {
  provider?: string;
  textModel?: string;
  visionModel?: string;
}

// Batch-grain QC triggering was removed — QC is initiated per Order only
// (processOrderQC / processOrdersQC). The Batch is upload-only.

export interface QCProgressSnapshot {
  stage: string;
  message: string;
  current: number;
  total: number;
  percent: number;
  smoothedPercent?: number;
  running: boolean;
  modelProvider?: string;
  modelName?: string;
  visionModel?: string;
  startedAt?: string;
  updatedAt?: string;
  subStage?: string | null;
  subMessage?: string | null;
  subPercent?: number;
  subElapsedMs?: number;
}

/** Live QC progress for one order (poll fallback; WS /topic/qc/order/{id}/progress is primary). */
export const getOrderQCProgress = (orderId: number) =>
  apiFetch<QCProgressSnapshot>(`/api/qc/progress/order/${orderId}`);

/** Best-effort stop for a running order QC job. */
export const cancelOrderQC = (orderId: number) =>
  apiFetch<{ message: string; orderId: number; cancelled: boolean }>(
    `/api/qc/cancel/order/${orderId}`,
    { method: "POST" }
  );

export const assignReviewer = (batchId: number, reviewerId: number) =>
  apiFetch(`/api/admin/batches/${batchId}/assign`, {
    method: "POST",
    body: JSON.stringify({ reviewerId }),
  });

// Soft-delete by default (data + audit trail preserved). Pass hard=true for an
// irreversible purge — the UI gates that behind a second confirmation.
export const deleteBatch = (batchId: number, hard = false) =>
  apiFetch(`/api/admin/batches/${batchId}${hard ? "?hard=true" : ""}`, { method: "DELETE" });

// ── Reviewer ──────────────────────────────────────────────────────────────────
export const getQCResults = (batchId: number) =>
  apiFetch<QCResult[]>(`/api/qc/results/${batchId}`);

export const getQCRules = (qcResultId: number) =>
  apiFetch<QCRuleResult[]>(`/api/reviewer/qc/${qcResultId}/rules`);

/** Review policy flags the UI mirrors so its messaging matches the backend. */
export const getReviewConfig = () =>
  apiFetch<{ requireSecondApprovalForOverride: boolean }>("/api/reviewer/config");

export const getQCProgress = (qcResultId: number) =>
  apiFetch<{ totalRules: number; totalToVerify: number; pending: number; canSubmit: boolean }>(
    `/api/reviewer/qc/${qcResultId}/progress`
  );

export const startReviewSession = (qcResultId: number, acknowledgeExistingLock = false) =>
  apiFetch<ReviewSession>(`/api/reviewer/qc/${qcResultId}/session/start`, {
    method: "POST",
    body: JSON.stringify({ acknowledgeExistingLock }),
  });

export const heartbeatReviewSession = (qcResultId: number, sessionToken: string) =>
  apiFetch<{ success: boolean; expiresAt?: string }>(`/api/reviewer/qc/${qcResultId}/session/heartbeat`, {
    method: "POST",
    body: JSON.stringify({ sessionToken }),
  });

export const getQCFileInfo = (qcResultId: number) =>
  apiFetch<QCFileInfo>(`/api/qc/file/${qcResultId}`);

export const saveDecision = (
  ruleResultId: number,
  decision: "PASS" | "FAIL",
  comment: string | undefined,
  sessionToken: string,
  decisionLatencyMs: number,
  acknowledged: boolean,
) =>
  apiFetch<DecisionSaveResponse>("/api/reviewer/decision/save", {
    method: "POST",
    body: JSON.stringify({ ruleResultId, decision, comment, sessionToken, decisionLatencyMs, acknowledged }),
  });

export const recordRuleFocus = (ruleResultId: number, sessionToken: string) =>
  apiFetch<{ success: boolean }>("/api/reviewer/decision/focus", {
    method: "POST",
    body: JSON.stringify({ ruleResultId, sessionToken }),
  });

export const getPdfUrl = (batchFileId: number) => `${JAVA}/files/${batchFileId}`;

// ── Override / escalation workflow ───────────────────────────────────────────

export interface PendingOverride {
  ruleResultId: number;
  ruleId: string;
  ruleName: string;
  status: string;
  message: string;
  severity: string;
  overridePending: boolean;
  overrideRequestedAt: string | null;
  overrideRequestedBy: string | null;
  reviewerComment: string | null;
  qcResultId?: number;
  filename?: string;
  batchId?: number;
  parentBatchId?: string;
}

export const getPendingOverrides = () =>
  apiFetch<PendingOverride[]>("/api/reviewer/admin/overrides/pending");

export const decideOverride = (
  ruleResultId: number,
  approve: boolean,
  comment?: string,
) =>
  apiFetch<{ success: boolean; ruleResultId: number; approved: boolean; approvedBy: string }>(
    `/api/reviewer/admin/overrides/${ruleResultId}/decide`,
    { method: "POST", body: JSON.stringify({ approve, comment: comment ?? "" }) },
  );

export const getQCHistory = (batchFileId: number) =>
  apiFetch<QCHistoryRun[]>(`/api/qc/history/file/${batchFileId}`);

export interface FileHistoryEvent {
  id: number;
  eventType: string;
  outcome: string | null;
  sourceLayer: string | null;
  occurredAt: string | null;
}

export interface FileHistoryResponse {
  batchFileId: number;
  filename: string;
  fileType: string | null;
  status: string | null;
  propertySetName: string | null;
  events: FileHistoryEvent[];
  activeQcResult: {
    id: number;
    qcDecision: string | null;
    finalDecision: string | null;
    rejectionCategory: string | null;
    rejectionNote: string | null;
    reviewerNotes: string | null;
    totalRules: number;
    passedCount: number;
    failedCount: number;
    processedAt: string | null;
    reviewedAt: string | null;
    rerunOfId: number | null;
  } | null;
}

/** Full per-file history including events and active QC result summary. */
export const getFileHistory = (batchFileId: number) =>
  apiFetch<FileHistoryResponse>(`/api/qc/file-history/${batchFileId}`);

export type QCDiffFinding = {
  ruleId: string | null;
  ruleName: string | null;
  section: string | null;
  targetField: string | null;
  status: string | null;
  severity: string | null;
  previousStatus?: string | null;
  previousSeverity?: string | null;
};

export type QCDiffRevision = {
  revision: number;
  revisionType: string;
  changedAt: string;
  changedBy: string | null;
  action: string;
  changes: Record<string, { from: unknown; to: unknown }>;
};

export type QCResultDiff = {
  resultId: number;
  ruleEngineVersion: string | null;
  hasPrevious: boolean;
  previousResultId?: number;
  previousRuleEngineVersion?: string | null;
  ruleEngineChanged?: boolean;
  added?: QCDiffFinding[];
  removed?: QCDiffFinding[];
  changed?: QCDiffFinding[];
  unchangedCount?: number;
  summary?: { added: number; removed: number; changed: number; unchanged: number };
  message?: string;
  /** Envers entity-level revision trail for this QC run's QCResult record */
  auditTrail?: QCDiffRevision[];
};

export type QCHistoryRun = {
  id: number;
  qcDecision: string | null;
  finalDecision: string | null;
  totalRules: number;
  passedCount: number;
  failedCount: number;
  verifyCount: number;
  processedAt: string | null;
  supersededAt: string | null;
  isActive: boolean;
  rerunOfId: number | null;
  cacheHit: boolean | null;
  extractionMethod: string | null;
  ruleEngineVersion: string | null;
};

// Diff a QC result against the run it replaced (added / removed / changed findings).
export const getQCResultDiff = (qcResultId: number) =>
  apiFetch<QCResultDiff>(`/api/qc/history/diff/${qcResultId}`);

// Download the structured findings export (JSON or CSV) for a batch — the artifact
// an admin sends to the AMC manually. Streams the file to the browser.
export async function downloadFindingsExport(
  batchId: number,
  parentBatchId: string,
  format: "json" | "csv",
): Promise<void> {
  const res = await fetch(`${JAVA}/api/qc/findings/${batchId}?format=${format}`, {
    credentials: "include",
  });
  if (!res.ok) throw new Error(`Findings export failed (${res.status})`);
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `findings_${parentBatchId}.${format}`;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

export const requestReReview = (qcResultId: number, reason: string) =>
  apiFetch<{ success: boolean; message: string }>(`/api/reviewer/qc/${qcResultId}/request-re-review`, {
    method: "POST",
    body: JSON.stringify({ reason }),
  });

export const getSubmittedQCResult = (qcResultId: number) =>
  apiFetch<{ id: number; finalDecision: string; reviewedAt: string; reviewerNotes?: string }>(
    `/api/reviewer/qc/${qcResultId}/result`
  );

export interface SubmittedQCResult {
  id: number;
  finalDecision: "PASS" | "FAIL";
  failedCount: number;
  passedCount: number;
  totalRules: number;
  reviewedAt: string;
  batchFile: { id: number; filename: string };
}

export const getSubmittedQueue = () =>
  apiFetch<SubmittedQCResult[]>("/api/reviewer/qc/results/submitted");

/** Results currently assigned to the reviewer and awaiting a decision. */
export const getReviewerPending = <T = unknown>() =>
  apiFetch<T>("/api/reviewer/qc/results/pending");

/** Submit a reviewer's final sign-off for a QC result. */
export const submitReview = (qcResultId: number, notes: string, sessionToken: string) =>
  apiFetch<Record<string, unknown>>(`/api/reviewer/qc/${qcResultId}/submit`, {
    method: "POST",
    body: JSON.stringify({ notes, sessionToken }),
  });

/**
 * WebSocket URL for the QC real-time channel.
 *
 * No token is appended to the URL — the browser automatically sends the
 * HttpOnly jwt cookie in the Upgrade handshake headers.  The backend's
 * WebSocketAuthHandshakeInterceptor reads the cookie from there.
 */
export const getRealtimeUrl = () =>
  `${JAVA.replace(/^http/, "ws")}/ws/qc`;

// ── Analytics (ADMIN only) ────────────────────────────────────────────────────
export const getAnalyticsOverview  = (days = 30) => apiFetch<Record<string, unknown>>(`/api/analytics/overview?days=${days}`);
export const getAnalyticsOcr       = (days = 30) => apiFetch<Record<string, unknown>>(`/api/analytics/ocr?days=${days}`);
export const getAnalyticsMl        = (days = 30) => apiFetch<Record<string, unknown>>(`/api/analytics/ml?days=${days}`);
export const getAnalyticsOperators = (days = 30) => apiFetch<Record<string, unknown>>(`/api/analytics/operators?days=${days}`);
export const getAnalyticsTrend     = (days = 30) => apiFetch<unknown[]>(`/api/analytics/trend?days=${days}`);
export const getAnalyticsReviewSla = () => apiFetch<Record<string, unknown>>("/api/analytics/review-sla");
export const getAnalyticsAnomalies = (days = 7) => apiFetch<Record<string, unknown>>(`/api/analytics/anomalies?days=${days}`);

// ── Types ─────────────────────────────────────────────────────────────────────
export interface User {
  id: number;
  username: string;
  email?: string;
  fullName?: string;
  role: "ADMIN" | "REVIEWER";
  client?: { id: number; name: string; code: string };
  createdAt?: string;
  active?: boolean;
  lastLoginAt?: string;
}

export interface Client {
  id: number;
  name: string;
  code: string;
  status: string;
  createdAt?: string;
}

export interface Batch {
  id: number;
  parentBatchId: string;
  status: string;
  client: Client;
  files: BatchFile[];
  /** Eagerly-computed file count from DB @Formula — always accurate even when files is not loaded */
  fileCount?: number;
  /** Property sets derived from ZIP folder structure — populated on GET /api/admin/batches/{id} */
  propertySets?: PropertySet[];
  /** Number of distinct property set folders found in the ZIP (0 for flat/single-set batches) */
  setCount?: number;
  assignedReviewer?: Pick<User, "id" | "username" | "fullName">;
  createdBy?: Pick<User, "id" | "username">;
  errorMessage?: string;
  /** Non-fatal intake warnings (e.g. ambiguous document roles); newline-separated. */
  intakeWarnings?: string | null;
  /** Total NEEDS_ASSIGNMENT files across all property sets; populated on GET /api/admin/batches/{id}. */
  needsAssignmentCount?: number;
  /** Honest per-order breakdown for this batch: OrderDocumentStatus → count. Batch status is
   *  only the intake/processing state; QC/review/completion are per-order. */
  orderStatusRollup?: Record<string, number>;
  /** Number of resolved orders in this batch (sum of orderStatusRollup). */
  orderCount?: number;
  /** Supporting files that could not be auto-matched — same data as per-set, collected at batch level. */
  unassignedFiles?: BatchFile[];
  createdAt: string;
  updatedAt: string;
}

export interface BatchFile {
  id: number;
  filename: string;
  fileType: "APPRAISAL" | "APPRAISAL_XML" | "ENGAGEMENT" | "CONTRACT";
  fileSize: number;
  status: string;
  orderId?: string;
  propertySetName?: string | null;
  documentQualityFlags?: string | null;
  /** Resolved Order (AppraisalTransaction) id — null for legacy files ingested
   * before Order resolution existed (run the Orders backfill to fix). */
  resolvedOrderId?: number | null;
  orderDocumentStatus?: string | null;
}

/**
 * A property set groups files from one property/case folder within a batch —
 * backed by the resolved Order when available (orderId set), falling back to
 * the raw ZIP-folder-derived name for legacy files with no resolved order yet.
 */
export interface PropertySet {
  setName: string | null;
  /** The canonical Order id this set resolves to — link through to /admin/orders/{orderId}. */
  orderId?: number | null;
  documentStatus?: string | null;
  files: BatchFile[];
  fileCount: number;
  completedCount: number;
  errorCount: number;
  pendingCount: number;
  /** Supporting files that could not be auto-matched; admin must assign manually. */
  needsAssignmentCount: number;
}

export interface QCResult {
  id: number;
  batchFile: BatchFile;
  qcDecision: "AUTO_PASS" | "TO_VERIFY" | "AUTO_FAIL" | "BLOCKED";
  finalDecision?: "PASS" | "FAIL";
  totalRules: number;
  passedCount: number;
  failedCount: number;
  verifyCount: number;
  manualPassCount: number;
  processingTimeMs?: number;
  cacheHit?: boolean;
  missingDocuments?: string | null;
  rejectionCategory?: string | null;
  rejectionNote?: string | null;
  reviewerNotes?: string | null;
  processedAt: string;
  reviewedAt?: string | null;
}

export interface QCRuleResult {
  id: number;
  ruleId: string;
  ruleName: string;
  section?: string;
  status: string;
  message: string;
  actionItem?: string;
  // JSON string from the QC pipeline: {checklist_num, template_id, fields, reasoning}.
  // `reasoning` carries the Layer-B/C plain-language "why" for the reviewer.
  details?: string | null;
  appraisalValue?: string;
  engagementValue?: string;
  confidence?: number | null;
  extractedValue?: string | null;
  expectedValue?: string | null;
  verifyQuestion?: string | null;
  rejectionText?: string | null;
  // Document-tagged evidence from the QC pipeline: which document each value was
  // read from. The API returns this as a structured array (objects), but legacy
  // rows may surface as plain strings, and older callers may still see a JSON
  // string — ruleEvidence.ts normalizes all three shapes.
  evidence?: RuleEvidenceEntry[] | string | null;
  sourceDocuments?: string[] | null;
  comparedFields?: string[] | null;
  comparedValues?: Record<string, unknown> | null;
  comparisonMethod?: string | null;
  decisionPath?: string[] | null;
  exceptionType?: string | null;
  stage?: string | null;
  retryEligible?: boolean;
  help?: RuleHelp | null;
  reviewRequired: boolean;
  reviewerVerified?: boolean;
  reviewerComment?: string;
  firstPresentedAt?: string | null;
  decisionLatencyMs?: number | null;
  acknowledgedReferences?: boolean;
  overridePending?: boolean;
  overrideRequestedBy?: string | null;
  overrideRequestedAt?: string | null;
  verifiedAt?: string | null;
  severity?: string;
  // Slim finding contract — backend-owned, generated at QC eval time. The collapsed
  // reviewer row renders from these instead of deriving a one-liner client-side.
  summary?: string | null;
  confidenceTier?: "high" | "medium" | "low" | string | null;
  highlightedValues?: string[] | null;
  pdfPage?: number | null;
  bboxX?: number | null;
  bboxY?: number | null;
  bboxW?: number | null;
  bboxH?: number | null;
}

/** Full per-rule evidence, fetched lazily when a reviewer expands a finding row. */
export interface RuleDetail {
  id: number;
  ruleId: string;
  sources: RuleEvidenceEntry[];
  explanation: string;
  highlightedValues: string[];
  pdfPage?: number | null;
  bboxX?: number | null;
  bboxY?: number | null;
  bboxW?: number | null;
  bboxH?: number | null;
}

/** Lazy-load the full evidence for one rule result (on row expand). */
export const getRuleDetail = (ruleResultId: number) =>
  apiFetch<RuleDetail>(`/api/reviewer/qc/rules/${ruleResultId}/detail`);

export interface RuleEvidenceEntry {
  document?: string;
  comparable?: string | null;   // "Comp 1" | "Subject" | null — which property
  value?: string;
  confidence?: number | null;
  page?: number | null;
  method?: string | null;
}

export interface RuleHelp {
  summary?: string;
  terms?: Record<string, string>;
  example?: string;
}

export interface DecisionSaveResponse {
  success: boolean;
  ruleResultId: number;
  ruleId: string;
  decision: "PASS" | "FAIL";
  savedAt: string;
  status: string;
  reviewerVerified?: boolean | null;
  overridePending?: boolean;
  reviewerComment?: string;
}

export interface ReviewSession {
  success: boolean;
  sessionToken: string;
  lockedBy?: string;
  startedAt?: string;
  expiresAt?: string;
  lockAcknowledged?: boolean;
  priorActionCount?: number;
}

export interface QCFileInfo {
  id: number;
  qcDecision?: "AUTO_PASS" | "TO_VERIFY" | "AUTO_FAIL" | "BLOCKED";
  missingDocuments?: string | null;
  batchFile?: BatchFile;
  documents?: BatchFile[];
  documentMatches?: DocumentMatch[];
}

export interface DocumentMatch {
  id: number;
  appraisalFileId?: number | null;
  supportingFileId?: number | null;
  supportingFileType?: "ENGAGEMENT" | "CONTRACT" | string | null;
  supportingFilename?: string | null;
  matchType?: string | null;
  confidenceScore?: number | null;
  matchReason?: string | null;
  ambiguousCandidatesJson?: string | null;
  rejectedCandidatesJson?: string | null;
  matchedAt?: string | null;
}
