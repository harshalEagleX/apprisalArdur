/**
 * API client — all calls go to the Java backend on port 8080.
 * Two roles: ADMIN and REVIEWER only.
 *
 * Authentication strategy: HttpOnly "jwt" cookie set by the backend on login.
 * The browser sends it automatically via credentials:"include". JavaScript
 * never reads or writes the token — this eliminates the XSS token-theft vector.
 */

import { adminBatchTimeline, elapsedMs } from "@/lib/adminBatchTimeline";

const JAVA = process.env.NEXT_PUBLIC_JAVA_URL ?? "http://localhost:8080";

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

// ── Admin: Clients ────────────────────────────────────────────────────────────
export const getClients = () => apiFetch<Client[]>("/api/admin/clients");

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
 * Bulk-process QC on multiple batches in parallel.
 * Returns a summary of how many succeeded / failed.
 */
export async function bulkProcessQC(
  batchIds: number[],
  model?: QCModelSelection,
): Promise<{ succeeded: number[]; failed: number[] }> {
  const results = await Promise.allSettled(
    batchIds.map(id => processQC(id, model))
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
  provider: "ollama";
  textModel?: string;
  visionModel?: string;
}

export async function processQC(batchId: number, model?: QCModelSelection) {
  const started = performance.now();
  adminBatchTimeline("frontend_qc_trigger_api_start", {
    batch_id: batchId,
    model_provider: model?.provider ?? "ollama",
    text_model: model?.textModel,
    vision_model: model?.visionModel,
  });
  try {
    const response = await apiFetch<{ message: string; batchId: number; pollUrl?: string; status?: string }>(
    `/api/qc/process/${batchId}`,
    { method: "POST", body: JSON.stringify(model ?? { provider: "ollama" }) }
    );
    adminBatchTimeline("frontend_qc_trigger_api_complete", {
      batch_id: response.batchId,
      status: response.status,
      elapsed_ms: elapsedMs(started),
    });
    return response;
  } catch (err) {
    adminBatchTimeline("frontend_qc_trigger_api_failed", {
      batch_id: batchId,
      elapsed_ms: elapsedMs(started),
      error: err instanceof Error ? err.message : String(err),
    });
    throw err;
  }
}

export const cancelQC = (batchId: number) =>
  apiFetch<{ message: string; batchId: number; cancelled: boolean; status: string }>(
    `/api/qc/cancel/${batchId}`,
    { method: "POST" }
  );

export const getBatchQCProgress = (batchId: number) =>
  apiFetch<{
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
  }>(`/api/qc/progress/${batchId}`);

export const assignReviewer = (batchId: number, reviewerId: number) =>
  apiFetch(`/api/admin/batches/${batchId}/assign`, {
    method: "POST",
    body: JSON.stringify({ reviewerId }),
  });

export const deleteBatch = (batchId: number) =>
  apiFetch(`/api/admin/batches/${batchId}`, { method: "DELETE" });

// ── Reviewer ──────────────────────────────────────────────────────────────────
export const getQCResults = (batchId: number) =>
  apiFetch<QCResult[]>(`/api/qc/results/${batchId}`);

export const getQCRules = (qcResultId: number) =>
  apiFetch<QCRuleResult[]>(`/api/reviewer/qc/${qcResultId}/rules`);

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
  apiFetch<Array<{
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
  }>>(`/api/qc/history/file/${batchFileId}`);

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
  assignedReviewer?: Pick<User, "id" | "username" | "fullName">;
  createdBy?: Pick<User, "id" | "username">;
  errorMessage?: string;
  createdAt: string;
  updatedAt: string;
}

export interface BatchFile {
  id: number;
  filename: string;
  fileType: "APPRAISAL" | "ENGAGEMENT" | "CONTRACT";
  fileSize: number;
  status: string;
  orderId?: string;
  documentQualityFlags?: string | null;
}

export interface QCResult {
  id: number;
  batchFile: BatchFile;
  qcDecision: "AUTO_PASS" | "TO_VERIFY" | "AUTO_FAIL";
  finalDecision?: "PASS" | "FAIL";
  totalRules: number;
  passedCount: number;
  failedCount: number;
  verifyCount: number;
  manualPassCount: number;
  processingTimeMs?: number;
  cacheHit?: boolean;
  missingDocuments?: string | null;
  processedAt: string;
}

export interface QCRuleResult {
  id: number;
  ruleId: string;
  ruleName: string;
  status: string;
  message: string;
  actionItem?: string;
  appraisalValue?: string;
  engagementValue?: string;
  confidence?: number | null;
  extractedValue?: string | null;
  expectedValue?: string | null;
  verifyQuestion?: string | null;
  rejectionText?: string | null;
  evidence?: string | null;
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
  pdfPage?: number | null;
  bboxX?: number | null;
  bboxY?: number | null;
  bboxW?: number | null;
  bboxH?: number | null;
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
  qcDecision?: "AUTO_PASS" | "TO_VERIFY" | "AUTO_FAIL";
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
