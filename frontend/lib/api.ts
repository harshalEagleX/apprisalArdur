/**
 * API client — all calls go to the Java backend on port 8080.
 * Two roles: ADMIN and REVIEWER only.
 */

const JAVA = process.env.NEXT_PUBLIC_JAVA_URL ?? "http://localhost:8080";
const AUTH_TOKEN_KEY = "apprisal_auth_token";

function storedAuthToken(): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem(AUTH_TOKEN_KEY);
}

function rememberAuthToken(token: string | null): void {
  if (typeof window === "undefined") return;
  if (token?.trim()) window.localStorage.setItem(AUTH_TOKEN_KEY, token);
  else window.localStorage.removeItem(AUTH_TOKEN_KEY);
}

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
  return clean;
}

async function apiFetch<T>(path: string, options?: RequestInit): Promise<T> {
  let res: Response;
  const token = storedAuthToken();
  const { headers, ...rest } = options ?? {};
  try {
    res = await fetch(`${JAVA}${path}`, {
      credentials: "include",
      ...rest,
      headers: {
        "Content-Type": "application/json",
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
        ...normalizeHeaders(headers),
      },
    });
  } catch (err) {
    // Spring Security 302-redirects unauthenticated /api/** calls to /login.
    // The browser follows the redirect cross-origin; the /login response
    // doesn't carry the right CORS headers, so fetch surfaces a generic
    // `TypeError: Failed to fetch`. Bounce the user to login instead of
    // letting the calling page crash.
    if (typeof window !== "undefined"
        && err instanceof TypeError
        && window.location.pathname !== "/login") {
      window.location.href = "/login";
    }
    throw err;
  }

  if (res.status === 401 || res.status === 302) {
    if (typeof window !== "undefined") window.location.href = "/login";
    throw new Error("Unauthenticated");
  }
  if (res.status === 403) throw new Error("Access denied");

  if (!res.ok) {
    throw new Error(await readErrorMessage(res, `Request failed (${res.status})`));
  }

  const text = await res.text();
  return text ? JSON.parse(text) : ({} as T);
}

// ── Auth ──────────────────────────────────────────────────────────────────────
export async function login(username: string, password: string): Promise<void> {
  const tokenRes = await fetch(`${JAVA}/api/auth/authenticate`, {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username, password }),
  });
  if (!tokenRes.ok) {
    rememberAuthToken(null);
    throw new Error("Invalid username or password");
  }
  const tokenBody = await tokenRes.json() as { token?: string };
  rememberAuthToken(tokenBody.token ?? null);

  const form = new URLSearchParams({ username, password });
  const res = await fetch(`${JAVA}/login`, {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body: form.toString(),
    redirect: "manual",
  });
  const ok = res.status === 0 || res.status === 200 || res.status === 301 || res.status === 302;
  if (!ok) {
    rememberAuthToken(null);
    throw new Error("Invalid username or password");
  }
}

export async function logout(): Promise<void> {
  rememberAuthToken(null);
  await fetch(`${JAVA}/logout`, {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body: "",
    redirect: "manual",
  });
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
  const fd = new FormData();
  fd.append("file", file);
  fd.append("clientId", String(clientId));
  const res = await fetch(`${JAVA}/api/admin/batches/upload`, {
    method: "POST",
    credentials: "include",
    body: fd,
  });
  if (!res.ok) {
    throw new Error(await readErrorMessage(res, `Upload failed (${res.status})`));
  }
  return res.json();
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

export const processQC = (batchId: number, model?: QCModelSelection) =>
  apiFetch<{ message: string; batchId: number; pollUrl?: string; status?: string }>(
    `/api/qc/process/${batchId}`,
    { method: "POST", body: JSON.stringify(model ?? { provider: "ollama" }) }
  );

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

export const getRealtimeUrl = () => {
  const base = `${JAVA.replace(/^http/, "ws")}/ws/qc`;
  const token = storedAuthToken();
  return token ? `${base}?access_token=${encodeURIComponent(token)}` : base;
};

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
