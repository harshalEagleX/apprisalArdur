export type Role = "ADMIN" | "REVIEWER";

export type BatchStatus =
  | "UPLOADED"
  | "VALIDATING"
  | "VALIDATION_FAILED"
  | "QC_PROCESSING"
  | "REVIEW_PENDING"
  | "IN_REVIEW"
  | "COMPLETED"
  | "ERROR"
  | string;

export interface User {
  id: number;
  username: string;
  email?: string;
  fullName?: string;
  role: Role;
  client?: Client;
}

export interface Client {
  id: number;
  name: string;
  code: string;
  status?: string;
}

export interface Batch {
  id: number;
  parentBatchId: string;
  status: BatchStatus;
  client?: Client;
  fileCount?: number;
  files?: BatchFile[];
  assignedReviewer?: Pick<User, "id" | "username" | "fullName">;
  errorMessage?: string;
  createdAt?: string;
  updatedAt?: string;
}

export interface BatchFile {
  id: number;
  filename: string;
  fileType: "APPRAISAL" | "ENGAGEMENT" | "CONTRACT" | string;
  fileSize?: number;
  status?: string;
}

export interface BatchStatusResponse {
  status: BatchStatus;
  totalFiles: number;
  processingTotalFiles: number;
  completedFiles: number;
  errorMessage?: string;
  updatedAt?: string;
}

export interface QCProgress {
  stage: string;
  message: string;
  current: number;
  total: number;
  percent: number;
  running: boolean;
}

export interface QCResult {
  id: number;
  batchFile: BatchFile;
  qcDecision: "AUTO_PASS" | "TO_VERIFY" | "AUTO_FAIL" | string;
  finalDecision?: "PASS" | "FAIL";
  totalRules: number;
  passedCount: number;
  failedCount: number;
  verifyCount: number;
  manualPassCount: number;
  processedAt: string;
}

export interface QCRuleResult {
  id: number;
  ruleId: string;
  ruleName: string;
  status: string;
  message: string;
  reviewRequired: boolean;
  severity?: string;
  reviewerVerified?: boolean;
  reviewerComment?: string;
}

export interface ReviewProgress {
  totalRules: number;
  totalToVerify: number;
  pending: number;
  canSubmit: boolean;
}
