import path from "node:path";
import "dotenv/config";

function numberFromEnv(name: string, fallback: number): number {
  const value = Number(process.env[name]);
  return Number.isFinite(value) && value > 0 ? value : fallback;
}

function required(name: string): string {
  const value = process.env[name];
  if (!value) throw new Error(`Missing required environment variable: ${name}`);
  return value;
}

export const config = {
  appBaseUrl: process.env.APP_BASE_URL ?? "http://localhost:3000",
  javaBaseUrl: process.env.JAVA_BASE_URL ?? "http://localhost:8080",
  aiProvider: process.env.AI_PROVIDER ?? "heuristic",
  openAiApiKey: process.env.OPENAI_API_KEY,
  openAiModel: process.env.OPENAI_MODEL ?? "gpt-5.4-mini",
  admin: {
    username: process.env.ADMIN_USERNAME ?? "admin",
    password: process.env.ADMIN_PASSWORD ?? "admin"
  },
  reviewer: {
    username: process.env.REVIEWER_USERNAME ?? "reviewer",
    password: process.env.REVIEWER_PASSWORD ?? "reviewer"
  },
  batchZipPath: process.env.BATCH_ZIP_PATH
    ? path.resolve(process.env.BATCH_ZIP_PATH)
    : undefined,
  clientId: process.env.CLIENT_ID ? Number(process.env.CLIENT_ID) : undefined,
  scenarioTimeoutMs: numberFromEnv("SCENARIO_TIMEOUT_MS", 900_000),
  qcTimeoutMs: numberFromEnv("QC_TIMEOUT_MS", 600_000),
  reviewTimeoutMs: numberFromEnv("REVIEW_TIMEOUT_MS", 600_000)
};

export function requireUploadInputs(): { batchZipPath: string; clientId: number } {
  const batchZipPath = config.batchZipPath;
  const clientId = config.clientId;
  if (!batchZipPath) required("BATCH_ZIP_PATH");
  if (!Number.isFinite(clientId)) required("CLIENT_ID");
  return { batchZipPath: batchZipPath as string, clientId: clientId as number };
}
