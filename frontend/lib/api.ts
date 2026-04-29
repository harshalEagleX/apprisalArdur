/**
 * API client — all calls go to the Java backend on port 8080.
 * Two roles: ADMIN and REVIEWER only.
 */

const JAVA = process.env.NEXT_PUBLIC_JAVA_URL ?? "http://localhost:8080";

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
    const body = await res.text();
    throw new Error(body || `HTTP ${res.status}`);
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
  apiFetch<{ status: string; totalFiles: number; completedFiles: number }>(`/api/admin/batches/${id}/status`);

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
    const err = await res.json().catch(() => ({}));
    throw new Error((err as Record<string, string>).error ?? `Upload failed ${res.status}`);
  }
  return res.json();
}

export const reconcileStuckBatches = () =>
  apiFetch<{ stuckFound: number; retried: number; abandoned: number; pythonHealthy: boolean; message: string }>(
    "/api/qc/reconcile",
    { method: "POST" }
  );

export const processQC = (batchId: number) =>
  apiFetch<{ message: string; batchId: number; pollUrl?: string; status?: string }>(
    `/api/qc/process/${batchId}`,
    { method: "POST" }
  );

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

export const saveDecision = (ruleResultId: number, decision: "ACCEPT" | "REJECT", comment?: string) =>
  apiFetch("/api/reviewer/decision/save", {
    method: "POST",
    body: JSON.stringify({ ruleResultId, decision, comment }),
  });

export const getPdfUrl = (batchFileId: number) => `${JAVA}/files/${batchFileId}`;

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
  reviewRequired: boolean;
  reviewerVerified?: boolean;
  reviewerComment?: string;
  severity?: string;
}
