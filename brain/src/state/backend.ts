import fs from "node:fs";
import { request as playwrightRequest, type APIRequestContext } from "@playwright/test";
import { config } from "../config";
import type {
  Batch,
  BatchStatusResponse,
  QCProgress,
  QCResult,
  QCRuleResult,
  ReviewProgress,
  Role,
  User
} from "../types/domain";

type Credentials = { username: string; password: string };
type ApiMethod = "GET" | "POST" | "PUT" | "DELETE";

export class BackendClient {
  private requestContext?: APIRequestContext;

  constructor(private readonly baseUrl = config.javaBaseUrl) {}

  async dispose(): Promise<void> {
    await this.requestContext?.dispose();
  }

  async login(role: Role, credentials?: Credentials): Promise<void> {
    const resolved = credentials ?? (role === "ADMIN" ? config.admin : config.reviewer);
    this.requestContext = await playwrightRequest.newContext({ baseURL: this.baseUrl });
    const response = await this.requestContext.post("/login", {
      form: { username: resolved.username, password: resolved.password },
      maxRedirects: 0
    });
    if (![0, 200, 301, 302].includes(response.status())) {
      throw new Error(`Backend login failed for ${role}: ${response.status()} ${await response.text()}`);
    }
  }

  storageStatePath(role: Role): string {
    return `.auth/${role.toLowerCase()}-backend-state.json`;
  }

  async api<T>(method: ApiMethod, path: string, data?: unknown): Promise<T> {
    if (!this.requestContext) throw new Error("BackendClient.login() must be called before api().");
    const response = await this.requestContext.fetch(path, {
      method,
      data,
      headers: data instanceof FormData ? undefined : { "Content-Type": "application/json" }
    });
    if (!response.ok()) {
      throw new Error(`${method} ${path} failed: ${response.status()} ${await response.text()}`);
    }
    const text = await response.text();
    return text ? (JSON.parse(text) as T) : ({} as T);
  }

  async me(): Promise<{ role: Role; username: string }> {
    return this.api("GET", "/api/me");
  }

  async getUsers(page = 0, size = 100): Promise<User[]> {
    const first = await this.api<{ content: User[]; totalPages: number }>("GET", `/api/admin/users?page=${page}&size=${size}`);
    const users = [...first.content];
    for (let nextPage = page + 1; nextPage < first.totalPages; nextPage += 1) {
      const next = await this.api<{ content: User[]; totalPages: number }>("GET", `/api/admin/users?page=${nextPage}&size=${size}`);
      users.push(...next.content);
    }
    return users;
  }

  async getBatches(status?: string): Promise<Batch[]> {
    const params = new URLSearchParams({ page: "0", size: "100" });
    if (status) params.set("status", status);
    const response = await this.api<{ content: Batch[] }>("GET", `/api/admin/batches?${params}`);
    return response.content;
  }

  async getBatchStatus(batchId: number): Promise<BatchStatusResponse> {
    return this.api("GET", `/api/admin/batches/${batchId}/status`);
  }

  async uploadBatch(zipPath: string, clientId: number): Promise<{ batchId: number; parentBatchId: string; fileCount: number }> {
    if (!this.requestContext) throw new Error("BackendClient.login() must be called before uploadBatch().");
    if (!fs.existsSync(zipPath)) throw new Error(`Batch ZIP does not exist: ${zipPath}`);
    const response = await this.requestContext.post("/api/admin/batches/upload", {
      multipart: {
        clientId: String(clientId),
        file: fs.createReadStream(zipPath)
      }
    });
    if (!response.ok()) {
      throw new Error(`Upload failed: ${response.status()} ${await response.text()}`);
    }
    return response.json();
  }

  async processQC(batchId: number): Promise<unknown> {
    return this.api("POST", `/api/qc/process/${batchId}`, { provider: "ollama" });
  }

  async getQCProgress(batchId: number): Promise<QCProgress> {
    return this.api("GET", `/api/qc/progress/${batchId}`);
  }

  async assignReviewer(batchId: number, reviewerId: number): Promise<unknown> {
    return this.api("POST", `/api/admin/batches/${batchId}/assign`, { reviewerId });
  }

  async getQCResults(batchId: number): Promise<QCResult[]> {
    return this.api("GET", `/api/qc/results/${batchId}`);
  }

  async getReviewerQueue(): Promise<QCResult[]> {
    return this.api("GET", "/api/reviewer/qc/results/pending");
  }

  async getRules(qcResultId: number): Promise<QCRuleResult[]> {
    return this.api("GET", `/api/reviewer/qc/${qcResultId}/rules`);
  }

  async getReviewProgress(qcResultId: number): Promise<ReviewProgress> {
    return this.api("GET", `/api/reviewer/qc/${qcResultId}/progress`);
  }

  async startReviewSession(qcResultId: number, acknowledgeExistingLock = false): Promise<{ sessionToken: string }> {
    return this.api("POST", `/api/reviewer/qc/${qcResultId}/session/start`, { acknowledgeExistingLock });
  }

  async saveDecision(input: {
    ruleResultId: number;
    decision: "PASS" | "FAIL";
    comment?: string;
    sessionToken: string;
    acknowledged: boolean;
  }): Promise<unknown> {
    return this.api("POST", "/api/reviewer/decision/save", {
      ruleResultId: input.ruleResultId,
      decision: input.decision,
      comment: input.comment,
      sessionToken: input.sessionToken,
      decisionLatencyMs: 0,
      acknowledged: input.acknowledged
    });
  }

  async submitReview(qcResultId: number, sessionToken: string, notes: string): Promise<unknown> {
    return this.api("POST", `/api/reviewer/qc/${qcResultId}/submit`, { sessionToken, notes });
  }

  async getClients(): Promise<Array<{ id: number; code: string; name: string; status: string }>> {
    return this.api("GET", "/api/admin/clients");
  }

  async createClient(name: string, code: string): Promise<{ id: number; code: string; name: string }> {
    return this.api("POST", "/api/admin/clients", { name, code });
  }

  async createUser(data: {
    username: string;
    password: string;
    role: "ADMIN" | "REVIEWER";
    fullName: string;
    email: string;
    clientId?: number;
  }): Promise<{ id: number; username: string; role: string }> {
    return this.api("POST", "/api/admin/users", data);
  }
}
