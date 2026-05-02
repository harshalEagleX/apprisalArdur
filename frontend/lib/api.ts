/**
 * API client — all calls go to the Java backend on port 8080.
 * Two roles: ADMIN and REVIEWER only.
 */

const JAVA = process.env.NEXT_PUBLIC_JAVA_URL ?? "http://localhost:8080";

async function readErrorMessage(res: Response, fallback: string): Promise<string> {
  const text = await res.text();
  if (!text) return fallback;

  try {
    const parsed = JSON.parse(text) as { error?: unknown; message?: unknown };
    const message = typeof parsed.error === "string" ? parsed.error : parsed.message;
    return typeof message === "string" && message.trim() ? message : fallback;
  } catch {
    return text;
  }
}

async function apiFetch<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${JAVA}${path}`, {
    credentials: "include",
    headers: { "Content-Type": "application/json", ...options?.headers },
    ...options,
  });

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
  const form = new URLSearchParams({ username, password });
  const res = await fetch(`${JAVA}/login`, {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body: form.toString(),
    redirect: "manual",
  });
  const ok = res.status === 0 || res.status === 200 || res.status === 301 || res.status === 302;
  if (!ok) throw new Error("Invalid username or password");
}

export async function logout(): Promise<void> {
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

// ── Admin: Dashboard ──────────────────────────────────────────────────────────
export const getAdminDashboard    = () => apiFetch<Record<string, unknown>>("/api/admin/dashboard");
export const getReviewerDashboard = () => apiFetch<Record<string, unknown>>("/api/reviewer/dashboard");

// ── Admin: Users ──────────────────────────────────────────────────────────────
export const getUsers = (page = 0) =>
  apiFetch<{ content: User[]; totalPages: number; number: number }>(`/api/admin/users?page=${page}&size=20`);

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
export const getAdminBatches = (page = 0, status?: string) => {
  const params = new URLSearchParams({ page: String(page), size: "20" });
  if (status) params.set("status", status);
  return apiFetch<{ content: Batch[]; totalPages: number; number: number }>(
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
  provider: "ollama" | "claude";
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
    running: boolean;
    modelProvider?: string;
    modelName?: string;
    visionModel?: string;
    startedAt?: string;
    updatedAt?: string;
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
  apiFetch("/api/reviewer/decision/save", {
    method: "POST",
    body: JSON.stringify({ ruleResultId, decision, comment, sessionToken, decisionLatencyMs, acknowledged }),
  });

export const getPdfUrl = (batchFileId: number) => `${JAVA}/files/${batchFileId}`;

export const getRealtimeUrl = () => `${JAVA.replace(/^http/, "ws")}/ws/qc`;

// ── Analytics (ADMIN only) ────────────────────────────────────────────────────
export const getAnalyticsOverview  = (days = 30) => apiFetch<Record<string, unknown>>(`/api/analytics/overview?days=${days}`);
export const getAnalyticsOcr       = (days = 30) => apiFetch<Record<string, unknown>>(`/api/analytics/ocr?days=${days}`);
export const getAnalyticsOperators = (days = 30) => apiFetch<Record<string, unknown>>(`/api/analytics/operators?days=${days}`);
export const getAnalyticsTrend     = (days = 30) => apiFetch<unknown[]>(`/api/analytics/trend?days=${days}`);

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
  reviewRequired: boolean;
  reviewerVerified?: boolean;
  reviewerComment?: string;
  firstPresentedAt?: string | null;
  decisionLatencyMs?: number | null;
  acknowledgedReferences?: boolean;
  overridePending?: boolean;
  overrideRequestedBy?: string | null;
  overrideRequestedAt?: string | null;
  severity?: string;
  pdfPage?: number | null;
  bboxX?: number | null;
  bboxY?: number | null;
  bboxW?: number | null;
  bboxH?: number | null;
}

export interface ReviewSession {
  success: boolean;
  sessionToken: string;
  lockedBy?: string;
  startedAt?: string;
  expiresAt?: string;
  lockAcknowledged?: boolean;
}

export interface QCFileInfo {
  id: number;
  qcDecision?: "AUTO_PASS" | "TO_VERIFY" | "AUTO_FAIL";
  batchFile?: BatchFile;
  documents?: BatchFile[];
}
