# API Reference

Complete REST API documentation for the Apprisal QC Platform.

> **Updated:** May 2026 — Derived from a full code audit of the actual controllers and
> services. The previous version documented a Phase-1 MVP; this version reflects the
> fully-implemented platform.

---

## Base URLs

| Service | Base URL | Auth |
|---------|----------|------|
| Java Backend | `http://localhost:8080` | JWT Bearer + Session cookie |
| Python OCR Service | `http://localhost:5001` | `X-API-Key` header |

All Java REST endpoints are prefixed with `/api`. Responses are `application/json` unless noted.

---

## Authentication

### Login

Authenticates the user and establishes both a JWT token (for API) and a session cookie
(for server-side pages).

```
POST /api/auth/authenticate
Content-Type: application/json
```

**Request:**
```json
{ "username": "admin@example.com", "password": "Admin123!" }
```

**Success (200):**
```json
{ "token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..." }
```

Store the `token` value and send it as `Authorization: Bearer {token}` on all subsequent
API requests. Also POST the same credentials to `/login` (form-encoded) to establish a
session cookie for WebSocket auth.

**Errors:** `401 Unauthorized` — invalid credentials.

---

### Current User

```
GET /api/me
Authorization: Bearer {token}
```

**Success (200):**
```json
{ "role": "ADMIN", "username": "admin@example.com" }
```

---

### Logout

```
POST /logout
Content-Type: application/x-www-form-urlencoded
```

Invalidates the session cookie. Also clear the JWT from client storage.

---

### Password Policy

```
GET /api/config/password-policy
```

**Success (200):**
```json
{ "minLength": 8 }
```

---

## Admin — Batches

All batch endpoints require `ROLE_ADMIN`.

### List Batches

```
GET /api/admin/batches
Authorization: Bearer {token}
```

**Query Parameters:**

| Param | Type | Default | Description |
|-------|------|---------|-------------|
| page | int | 0 | Zero-indexed page number |
| size | int | 20 | Items per page |
| status | string | (all) | Filter: UPLOADED, QC_PROCESSING, REVIEW_PENDING, COMPLETED, ERROR |
| search | string | | Search by filename or parentBatchId |

**Success (200):**
```json
{
  "content": [
    {
      "id": 42,
      "parentBatchId": "batch-2026-05-11-abc123",
      "status": "REVIEW_PENDING",
      "fileCount": 3,
      "client": { "id": 1, "name": "Acme Lending", "code": "ACME" },
      "assignedReviewer": { "id": 7, "username": "reviewer1", "fullName": "Jane Smith" },
      "createdBy": { "id": 1, "username": "admin" },
      "errorMessage": null,
      "createdAt": "2026-05-11T09:00:00",
      "updatedAt": "2026-05-11T09:15:00"
    }
  ],
  "totalPages": 5,
  "number": 0,
  "totalElements": 94
}
```

---

### Get Batch

```
GET /api/admin/batches/{id}
Authorization: Bearer {token}
```

Returns full `Batch` with file list. Same shape as list item plus `files: BatchFile[]`.

---

### Get Batch Status

Lightweight status check for polling during QC processing.

```
GET /api/admin/batches/{id}/status
Authorization: Bearer {token}
```

**Success (200):**
```json
{
  "status": "QC_PROCESSING",
  "totalFiles": 3,
  "processingTotalFiles": 3,
  "completedFiles": 1,
  "errorMessage": null,
  "updatedAt": "2026-05-11T09:20:00"
}
```

---

### Upload Batch

Accepts a ZIP file containing appraisal PDFs, engagement letters, and/or contracts.
File classification is by filename keyword: `appraisal`, `engagement`/`order`, `contract`.

```
POST /api/admin/batches/upload
Authorization: Bearer {token}
Content-Type: multipart/form-data
```

**Form Fields:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| file | File | Yes | ZIP archive, max 25 MB |
| clientId | number | Yes | Client organisation ID |

**Success (200):**
```json
{
  "batchId": 42,
  "parentBatchId": "batch-2026-05-11-abc123",
  "fileCount": 3
}
```

**Errors:** `400` invalid ZIP / no appraisal file found; `413` file too large; `409` duplicate
(same file hash already exists as a batch, returns existing batch).

---

### Assign Reviewer

```
POST /api/admin/batches/{id}/assign
Authorization: Bearer {token}
Content-Type: application/json
```

**Request:**
```json
{ "reviewerId": 7 }
```

**Success (200):** Updated `Batch` object.

---

### Delete Batch

Permanently deletes the batch, all files, QC results, and rule results.
Bypasses Envers audit on bulk deletes — use with caution.

```
DELETE /api/admin/batches/{id}
Authorization: Bearer {token}
```

**Success (200):**
```json
{ "message": "Batch 42 deleted successfully", "batchId": 42 }
```

---

## Admin — Users

All user management endpoints require `ROLE_ADMIN`.

### List Users

```
GET /api/admin/users?page=0&size=20
Authorization: Bearer {token}
```

**Success (200):**
```json
{
  "content": [
    {
      "id": 7,
      "username": "reviewer1",
      "email": "reviewer1@example.com",
      "fullName": "Jane Smith",
      "role": "REVIEWER",
      "client": { "id": 1, "name": "Acme Lending", "code": "ACME" },
      "createdAt": "2026-01-15T10:00:00"
    }
  ],
  "totalPages": 1,
  "number": 0,
  "totalElements": 5
}
```

---

### Create User

```
POST /api/admin/users
Authorization: Bearer {token}
Content-Type: application/json
```

**Request:**
```json
{
  "username": "newreviewer",
  "email": "newreviewer@example.com",
  "fullName": "Bob Jones",
  "password": "SecurePass1!",
  "role": "REVIEWER",
  "clientId": 1
}
```

**Success (201):** Created `User` object.

**Errors:** `400` validation error; `409` username or email already exists.

---

### Update User

```
PUT /api/admin/users/{id}
Authorization: Bearer {token}
Content-Type: application/json
```

**Request:** Same fields as create (all optional except `id`).

**Success (200):** Updated `User` object.

---

### Delete User

Soft-delete: marks user inactive, preserves audit trail.

```
DELETE /api/admin/users/{id}
Authorization: Bearer {token}
```

**Success (200):** `{ "message": "User deleted" }`

---

## Admin — Clients

### List Clients

```
GET /api/admin/clients
Authorization: Bearer {token}
```

**Success (200):** `Client[]`

---

### Create Client

```
POST /api/admin/clients
Authorization: Bearer {token}
Content-Type: application/json
```

**Request:**
```json
{ "name": "Acme Lending", "code": "ACME" }
```

**Success (201):** Created `Client` object.

---

## Admin — Dashboard

```
GET /api/admin/dashboard
Authorization: Bearer {token}
```

Returns aggregate statistics for the admin dashboard.

**Success (200):**
```json
{
  "totalBatches": 94,
  "pendingReview": 12,
  "completedToday": 3,
  "errorBatches": 1,
  "activeReviewers": 4,
  "avgQcTimeMs": 14500
}
```

---

## QC Processing

All QC processing endpoints require `ROLE_ADMIN`.

### Trigger QC Processing

Starts async QC processing for a batch. Returns immediately (202); poll progress via
WebSocket or `GET /api/qc/progress/{batchId}`.

```
POST /api/qc/process/{batchId}
Authorization: Bearer {token}
Content-Type: application/json
```

**Request (optional model selection):**
```json
{
  "provider": "ollama",
  "textModel": "llava:7b",
  "visionModel": "llava:7b"
}
```

**Success (202):**
```json
{
  "message": "QC processing started",
  "batchId": 42,
  "pollUrl": "/api/qc/progress/42",
  "status": "QC_PROCESSING"
}
```

**Errors:** `409` — batch already being processed; `503` — Python OCR service unreachable.

---

### Cancel QC Processing

```
POST /api/qc/cancel/{batchId}
Authorization: Bearer {token}
```

**Success (200):**
```json
{
  "message": "QC stop requested",
  "batchId": 42,
  "cancelled": true,
  "status": "UPLOADED"
}
```

---

### Get QC Progress

Polling endpoint for in-progress QC. Prefer WebSocket for real-time updates.

```
GET /api/qc/progress/{batchId}
Authorization: Bearer {token}
```

**Success (200):**
```json
{
  "stage": "python",
  "message": "Running OCR and QC rules for appraisal.pdf",
  "current": 1,
  "total": 3,
  "percent": 33,
  "smoothedPercent": 45,
  "running": true,
  "modelProvider": "ollama",
  "modelName": "llava:7b",
  "visionModel": "llava:7b",
  "startedAt": "2026-05-11T09:15:00Z",
  "updatedAt": "2026-05-11T09:17:30Z",
  "subStage": "ocr_pages",
  "subMessage": "Processing page 12 of 27",
  "subPercent": 0.44,
  "subElapsedMs": 6200
}
```

**Stage values:** `queued`, `starting`, `matching`, `matched`, `python`, `saving`, `complete`, `error`, `stopped`

---

### Get QC Results for Batch

```
GET /api/qc/results/{batchId}
Authorization: Bearer {token}
```

**Success (200):** `QCResult[]` — one per appraisal file in the batch.

```json
[
  {
    "id": 101,
    "batchFile": {
      "id": 55,
      "filename": "appraisal_96_baell.pdf",
      "fileType": "APPRAISAL",
      "fileSize": 2048576,
      "status": "COMPLETED",
      "orderId": null,
      "documentQualityFlags": null
    },
    "qcDecision": "TO_VERIFY",
    "finalDecision": null,
    "totalRules": 136,
    "passedCount": 98,
    "failedCount": 24,
    "verifyCount": 14,
    "manualPassCount": 0,
    "processingTimeMs": 14500,
    "cacheHit": false,
    "missingDocuments": null,
    "processedAt": "2026-05-11T09:20:00"
  }
]
```

---

### Get QC File Info

Returns file details and document match information for a QC result.

```
GET /api/qc/file/{qcResultId}
Authorization: Bearer {token}
```

**Success (200):**
```json
{
  "id": 101,
  "qcDecision": "TO_VERIFY",
  "missingDocuments": null,
  "batchFile": { "id": 55, "filename": "appraisal.pdf", "fileType": "APPRAISAL" },
  "documents": [
    { "id": 55, "filename": "appraisal.pdf", "fileType": "APPRAISAL" },
    { "id": 56, "filename": "engagement.pdf", "fileType": "ENGAGEMENT" }
  ],
  "documentMatches": [
    {
      "id": 22,
      "appraisalFileId": 55,
      "supportingFileId": 56,
      "supportingFileType": "ENGAGEMENT",
      "supportingFilename": "engagement.pdf",
      "matchType": "FILENAME_KEYWORD",
      "confidenceScore": 0.95,
      "matchReason": "Engagement letter matched by filename keyword",
      "matchedAt": "2026-05-11T09:15:05"
    }
  ]
}
```

---

### Reconcile Stuck Batches

Finds batches stuck in `QC_PROCESSING` beyond the configured timeout and retries or abandons them.

```
POST /api/qc/reconcile
Authorization: Bearer {token}
```

**Success (200):**
```json
{
  "stuckFound": 2,
  "retried": 1,
  "abandoned": 1,
  "pythonHealthy": true,
  "message": "Reconciliation complete"
}
```

---

## Reviewer Workflow

Reviewer endpoints require `ROLE_REVIEWER` or `ROLE_ADMIN`.

### Reviewer Dashboard

```
GET /api/reviewer/dashboard
Authorization: Bearer {token}
```

**Success (200):** Statistics for the logged-in reviewer's queue.

---

### Get Pending Review Queue

```
GET /api/reviewer/qc/pending
Authorization: Bearer {token}
```

Returns `QCResult[]` with `qcDecision = TO_VERIFY` or `AUTO_FAIL`, sorted by
failed count descending.

---

### Get Submitted Queue

```
GET /api/reviewer/qc/results/submitted
Authorization: Bearer {token}
```

Returns recently submitted (finalised) QC results for the reviewer.

**Success (200):**
```json
[
  {
    "id": 101,
    "finalDecision": "PASS",
    "failedCount": 0,
    "passedCount": 136,
    "totalRules": 136,
    "reviewedAt": "2026-05-11T10:30:00",
    "batchFile": { "id": 55, "filename": "appraisal.pdf" }
  }
]
```

---

### Get Rule Results

Returns all rule results for a QC result, ordered by severity then rule ID.

```
GET /api/reviewer/qc/{qcResultId}/rules
Authorization: Bearer {token}
```

**Success (200):** `QCRuleResult[]`

```json
[
  {
    "id": 5001,
    "ruleId": "S-1",
    "ruleName": "Property Address Match",
    "status": "fail",
    "message": "Appraisal address '96 Baell Trace Ct SE' differs from engagement order",
    "actionItem": "Verify correct address with appraiser — possible OCR error on street name",
    "appraisalValue": "96 Baell Trace Ct SE",
    "engagementValue": "96 Bell Trace Ct SE",
    "confidence": 0.82,
    "extractedValue": "96 Baell Trace Ct SE",
    "expectedValue": "96 Bell Trace Ct SE",
    "verifyQuestion": "Is '96 Baell Trace Ct SE' the correct address?",
    "rejectionText": "Address mismatch — must be corrected before approval",
    "evidence": ["Page 1, line 3", "Engagement letter page 1"],
    "reviewRequired": true,
    "reviewerVerified": null,
    "reviewerComment": null,
    "severity": "BLOCKING",
    "pdfPage": 1,
    "bboxX": 0.08, "bboxY": 0.12, "bboxW": 0.45, "bboxH": 0.02,
    "firstPresentedAt": null,
    "decisionLatencyMs": null,
    "acknowledgedReferences": false,
    "overridePending": false
  }
]
```

---

### Get Review Progress

Returns how many rules still need reviewer decisions.

```
GET /api/reviewer/qc/{qcResultId}/progress
Authorization: Bearer {token}
```

**Success (200):**
```json
{
  "totalRules": 136,
  "totalToVerify": 14,
  "pending": 6,
  "canSubmit": false
}
```

---

### Start Review Session

Acquires a review lock on a QC result. Only one reviewer can hold the lock at a time
(30-minute TTL, renewed by heartbeat).

```
POST /api/reviewer/qc/{qcResultId}/session/start
Authorization: Bearer {token}
Content-Type: application/json
```

**Request:**
```json
{ "acknowledgeExistingLock": false }
```

**Success (200):**
```json
{
  "success": true,
  "sessionToken": "550e8400-e29b-41d4-a716-446655440099",
  "lockedBy": null,
  "startedAt": "2026-05-11T10:00:00",
  "expiresAt": "2026-05-11T10:30:00",
  "lockAcknowledged": false,
  "priorActionCount": 0
}
```

If another reviewer holds the lock, `success: false` is returned with `lockedBy` set.
Pass `acknowledgeExistingLock: true` to force-acquire (admin override).

---

### Heartbeat Review Session

Extends the review lock TTL. Call every 2 minutes.

```
POST /api/reviewer/qc/{qcResultId}/session/heartbeat
Authorization: Bearer {token}
Content-Type: application/json
```

**Request:**
```json
{ "sessionToken": "550e8400-e29b-41d4-a716-446655440099" }
```

**Success (200):**
```json
{ "success": true, "expiresAt": "2026-05-11T10:32:00" }
```

---

### Save Decision

Records a reviewer's PASS or FAIL decision on a single rule result.

```
POST /api/reviewer/decision/save
Authorization: Bearer {token}
Content-Type: application/json
```

**Request:**
```json
{
  "ruleResultId": 5001,
  "decision": "PASS",
  "comment": "Confirmed correct address with appraiser — OCR error on street name",
  "sessionToken": "550e8400-e29b-41d4-a716-446655440099",
  "decisionLatencyMs": 12400,
  "acknowledged": true
}
```

**`decision`** values: `"PASS"` or `"FAIL"`

**Success (200):**
```json
{
  "success": true,
  "ruleResultId": 5001,
  "ruleId": "S-1",
  "decision": "PASS",
  "savedAt": "2026-05-11T10:05:00",
  "status": "pass",
  "reviewerVerified": true,
  "overridePending": false,
  "reviewerComment": "Confirmed correct address..."
}
```

**Errors:** `403` — invalid session token; `409` — optimistic lock conflict (stale entity);
`423` — session expired.

---

### Record Rule Focus

Tracks when a reviewer opens/focuses a rule (used for latency analytics).

```
POST /api/reviewer/decision/focus
Authorization: Bearer {token}
Content-Type: application/json
```

**Request:**
```json
{ "ruleResultId": 5001, "sessionToken": "550e8400-..." }
```

**Success (200):** `{ "success": true }`

---

### Request Re-Review

Marks a completed QC result for re-review.

```
POST /api/reviewer/qc/{qcResultId}/request-re-review
Authorization: Bearer {token}
Content-Type: application/json
```

**Request:**
```json
{ "reason": "Appraiser submitted corrected report" }
```

**Success (200):**
```json
{ "success": true, "message": "Re-review requested" }
```

---

### Get Submitted Result

Retrieves finalised result details for a specific QC result.

```
GET /api/reviewer/qc/{qcResultId}/result
Authorization: Bearer {token}
```

**Success (200):**
```json
{
  "id": 101,
  "finalDecision": "PASS",
  "reviewedAt": "2026-05-11T10:30:00",
  "reviewerNotes": "All issues resolved"
}
```

---

## Analytics

All analytics endpoints require `ROLE_ADMIN`.

### Overview

```
GET /api/analytics/overview?days=30
Authorization: Bearer {token}
```

Returns high-level processing and review statistics over the specified window.

---

### OCR Metrics

```
GET /api/analytics/ocr?days=30
Authorization: Bearer {token}
```

Returns OCR processing statistics: cache hit rate, average confidence, low-confidence
field counts, extraction method breakdown.

---

### Operator Statistics

```
GET /api/analytics/operators?days=30
Authorization: Bearer {token}
```

Returns per-reviewer productivity metrics.

---

### Trend Data

```
GET /api/analytics/trend?days=30
Authorization: Bearer {token}
```

**Success (200):** Array of daily data points for charting.

---

### Review SLA

```
GET /api/analytics/review-sla
Authorization: Bearer {token}
```

Returns SLA compliance metrics: % within target, average review time.

---

### Anomalies

```
GET /api/analytics/anomalies?days=7
Authorization: Bearer {token}
```

Returns recent anomaly signals (high failure rates, unusual processing times, etc.).

---

## Audit

Requires `ROLE_ADMIN`.

### Audit Graph Data

```
GET /api/graph/audit
Authorization: Bearer {token}
```

Returns audit event graph data (nodes and edges) for the admin audit visualisation.

---

## File Serving

### Download Appraisal PDF

Returns the raw PDF file. Ownership is enforced — users can only access files in
batches they have access to.

```
GET /files/{batchFileId}
Authorization: Bearer {token}
```

**Response:** `application/pdf` binary stream with
`Content-Disposition: inline; filename="{original_filename}"`.

---

## WebSocket — Real-Time Events

Connect via:
```
ws://localhost:8080/ws/qc?access_token={jwt_token}
```

After connection, subscribe to topics by sending a plain-text message:
```
subscribe:/topic/qc/batch/{batchId}/progress
```

### Topic: QC Batch Progress

**Topic:** `/topic/qc/batch/{batchId}/progress`

Emitted by `QCProcessingService` during batch processing.

**Payload:**
```json
{
  "batchId": 42,
  "stage": "python",
  "message": "Running OCR for appraisal.pdf",
  "current": 1,
  "total": 3,
  "percent": 33,
  "smoothedPercent": 45,
  "running": true,
  "modelProvider": "ollama",
  "modelName": "llava:7b",
  "visionModel": "llava:7b",
  "startedAt": "2026-05-11T09:15:00Z",
  "updatedAt": "2026-05-11T09:17:30Z",
  "subStage": "ocr_pages",
  "subMessage": "Processing page 12 of 27",
  "subPercent": 0.44,
  "subElapsedMs": 6200
}
```

### Topic: Reviewer Decision Update

**Topic:** `/topic/reviewer/qc/{qcResultId}/decision`

Emitted by `VerificationService` after a decision is saved.

---

## Python OCR Service API

Base URL: `http://localhost:5001`

All endpoints except `/health` require `X-API-Key: {PYTHON_API_KEY}` header.
In dev mode (`PYTHON_API_KEY` not set), the header is optional.

### Health Check

```
GET /health
```

**Success (200):**
```json
{
  "status": "ok",
  "tesseract_available": true,
  "db_available": true,
  "celery_worker_running": true,
  "ollama_available": true
}
```

---

### Process QC (Synchronous)

Runs full OCR + extraction + rule engine synchronously. Blocks until complete (5-15 min).
Prefer `/qc/submit` (async) for production use.

```
POST /qc/process
X-API-Key: {key}
Content-Type: multipart/form-data
```

**Form Fields:**

| Field | Required | Description |
|-------|----------|-------------|
| file | Yes | Appraisal PDF |
| engagement_letter | No | Engagement letter PDF |
| contract_file | No | Purchase contract PDF |
| model_provider | No | `"ollama"` (default) |
| text_model | No | e.g. `"llava:7b"` |
| vision_model | No | e.g. `"llava:7b"` |
| progress_token | No | UUID for sub-stage progress polling |
| batch_id | No | Java batch ID (for correlation) |
| batch_file_id | No | Java BatchFile ID (for correlation) |
| idempotency_key | No | Prevents duplicate processing |
| correlation_id | No | Distributed tracing ID |

**Success (200):** `PythonQCResponse` (see schema below)

---

### Submit QC Job (Async)

Enqueues an async Celery job and returns immediately with a job ID.

```
POST /qc/submit
X-API-Key: {key}
Content-Type: multipart/form-data
```

Same form fields as `/qc/process`.

**Success (200):**
```json
{
  "job_id": "550e8400-e29b-41d4-a716-446655440099",
  "status": "queued",
  "file_hash": "sha256hexstring"
}
```

**Errors:** `409` — job already running for the same `idempotency_key`;
returns `{ "job_id": "existing-job-id", ... }`.

---

### Poll Job Status

```
GET /qc/job/{jobId}
X-API-Key: {key}
```

**Success (200):**
```json
{
  "status": "SUCCESS",
  "result": { /* PythonQCResponse */ }
}
```

**`status`** values: `PENDING`, `STARTED`, `SUCCESS`, `FAILURE`

When `FAILURE`:
```json
{ "status": "FAILURE", "error": "OCR failed: corrupted PDF stream on page 14" }
```

---

### Sub-Stage Progress

Polling endpoint for fine-grained OCR progress during a synchronous call.

```
GET /qc/progress/{progressToken}
X-API-Key: {key}
```

**Success (200):**
```json
{
  "stage": "ocr_pages",
  "message": "Processing page 14 of 27",
  "sub_percent": 0.52,
  "elapsed_ms": 8200
}
```

**404** — token not yet registered or already evicted.

---

### Submit Reviewer Feedback

Sends a reviewer's correction back to Python for ML training.

```
POST /qc/feedback
X-API-Key: {key}
Content-Type: application/json
```

**Request:**
```json
{
  "document_id": "uuid",
  "processing_job_id": "uuid",
  "correlation_id": "batch:42",
  "rule_id": "S-1",
  "field_name": "property_address",
  "original_value": "96 Baell Trace Ct SE",
  "corrected_value": "96 Bell Trace Ct SE",
  "feedback_type": "CORRECTION",
  "operator_comment": "OCR misread street name",
  "reviewer_role": "REVIEWER",
  "decision_latency_ms": 12400,
  "acknowledged": true,
  "source_page": 1,
  "bbox_x": 0.08, "bbox_y": 0.12, "bbox_w": 0.45, "bbox_h": 0.02,
  "confidence_score": 0.82
}
```

**Success (200):** `{ "success": true }`

---

### List QC Rules

Returns all configured rules with their active/inactive status.

```
GET /qc/rules
X-API-Key: {key}
```

**Success (200):**
```json
[
  {
    "rule_id": "S-1",
    "rule_name": "Property Address Match",
    "is_active": true,
    "severity": "BLOCKING",
    "execution_order": 10,
    "category": "subject"
  }
]
```

---

### Toggle Rule (Admin)

```
PATCH /admin/rules/{ruleId}
X-API-Key: {key}
Content-Type: application/json
```

**Request:**
```json
{ "is_active": false }
```

Takes effect immediately on the next job — no restart required.

---

## Response Schemas

### PythonQCResponse

The full response returned from `/qc/process` and embedded in successful job results.

```json
{
  "success": true,
  "processing_time_ms": 14500,
  "total_pages": 27,
  "total_rules": 136,
  "passed": 98,
  "failed": 24,
  "verify": 14,
  "document_id": "uuid",
  "processing_job_id": "uuid",
  "cache_hit": false,
  "extraction_method": "HYBRID",
  "model_provider": "ollama",
  "model_name": "llava:7b",
  "vision_model": "llava:7b",
  "supporting_document_missing": false,
  "missing_supporting_documents": [],
  "field_confidence": {
    "property_address": 0.92,
    "borrower_name": 0.88,
    "appraised_value": 0.95
  },
  "rule_results": [
    {
      "rule_id": "S-1",
      "rule_name": "Property Address Match",
      "status": "fail",
      "message": "Address mismatch between appraisal and engagement",
      "action_item": "Verify correct address",
      "severity": "BLOCKING",
      "appraisal_value": "96 Baell Trace Ct SE",
      "engagement_value": "96 Bell Trace Ct SE",
      "confidence": 0.82,
      "extracted_value": "96 Baell Trace Ct SE",
      "expected_value": "96 Bell Trace Ct SE",
      "verify_question": "Is this the correct address?",
      "rejection_text": "Must match engagement order",
      "evidence": ["Page 1, line 3"],
      "review_required": true,
      "source_page": 1,
      "bbox_x": 0.08,
      "bbox_y": 0.12,
      "bbox_w": 0.45,
      "bbox_h": 0.02,
      "target_field": "property_address"
    }
  ]
}
```

### QCRuleResult (Java)

```json
{
  "id": 5001,
  "ruleId": "S-1",
  "ruleName": "Property Address Match",
  "status": "fail",
  "message": "...",
  "actionItem": "...",
  "severity": "BLOCKING",
  "appraisalValue": "...",
  "engagementValue": "...",
  "confidence": 0.82,
  "extractedValue": "...",
  "expectedValue": "...",
  "verifyQuestion": "...",
  "rejectionText": "...",
  "evidence": "...",
  "reviewRequired": true,
  "reviewerVerified": null,
  "reviewerComment": null,
  "firstPresentedAt": null,
  "decisionLatencyMs": null,
  "acknowledgedReferences": false,
  "overridePending": false,
  "overrideRequestedBy": null,
  "overrideRequestedAt": null,
  "verifiedAt": null,
  "pdfPage": 1,
  "bboxX": 0.08,
  "bboxY": 0.12,
  "bboxW": 0.45,
  "bboxH": 0.02
}
```

---

## Error Responses

All Java API errors follow this structure:

```json
{
  "error": "ERROR_CODE",
  "message": "Human-readable description",
  "field": "fieldName",
  "timestamp": "2026-05-11T10:00:00Z"
}
```

### HTTP Status Codes

| Code | Meaning | When Used |
|------|---------|-----------|
| 200 | OK | Successful operation |
| 201 | Created | Resource created |
| 202 | Accepted | Async operation started (QC processing) |
| 400 | Bad Request | Validation error, invalid input |
| 401 | Unauthorized | Missing or invalid authentication |
| 403 | Forbidden | Authenticated but not authorised |
| 404 | Not Found | Resource does not exist |
| 409 | Conflict | Duplicate upload, already processing, or stale lock |
| 413 | Payload Too Large | ZIP exceeds 25 MB |
| 423 | Locked | Review session expired |
| 500 | Internal Server Error | Unexpected server error |
| 503 | Service Unavailable | Python OCR service unreachable |

### Common Error Codes

| Code | Description |
|------|-------------|
| `INVALID_CREDENTIALS` | Wrong username or password |
| `TOKEN_EXPIRED` | JWT access token has expired |
| `ACCESS_DENIED` | User lacks required permission |
| `NOT_FOUND` | Resource does not exist |
| `BATCH_NOT_FOUND` | Batch ID does not exist |
| `DUPLICATE_BATCH` | ZIP with same hash already uploaded |
| `ALREADY_PROCESSING` | Batch is already in QC_PROCESSING |
| `QC_SERVICE_UNAVAILABLE` | Python OCR service is unreachable |
| `INVALID_FILE_TYPE` | Uploaded file is not a ZIP |
| `FILE_TOO_LARGE` | File exceeds 25 MB limit |
| `SESSION_EXPIRED` | Review session token has expired |
| `SESSION_LOCKED` | Another reviewer holds the review lock |
| `STALE_ENTITY` | Optimistic lock conflict — refresh and retry |
| `VALIDATION_ERROR` | Request body failed validation |

---

## Rate Limiting

No rate limiting is currently implemented on Java endpoints.
The Python OCR service has per-route rate limiting via `slowapi`.
Enterprise deployments should add rate limiting at the reverse proxy layer (nginx / Cloudflare).

---

*For architecture context, see [ARCHITECTURE.md](./ARCHITECTURE.md)*
*For roadmap and audit findings, see [IMPLEMENTATION_PLAN.md](./IMPLEMENTATION_PLAN.md)*
