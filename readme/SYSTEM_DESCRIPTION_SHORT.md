# Apprisal System Description - Short End-to-End View

Apprisal is an appraisal quality-control platform. The user uploads appraisal
documents, the system extracts key fields from appraisal, engagement, and
contract PDFs, runs QC rules, and gives reviewers a guided screen to verify
exceptions with evidence and PDF page locations.

## Service Sides

### Python Side: OCR, Extraction, and QC Brain

The Python service is a FastAPI app running on port `5001`. It owns the document
intelligence work.

- Receives PDFs from Java through `/qc/process`.
- Extracts text and structured fields from appraisal, engagement, and contract
  documents.
- Uses layered extraction: embedded text, spatial labels, checkbox detection,
  comparable-grid parsing, Camelot/table parsing, UAD template extraction, LLM
  gap-fill, sketch GLA extraction, narrative extraction, and photo analysis.
- Runs transaction-level QC rules across subject, contract, neighborhood, site,
  improvements, sales comparison, reconciliation, addendum, signature, photos,
  and FHA/USDA areas.
- Produces a `PythonQCResponse` with rule results, counts, confidence, evidence,
  source pages, and field bounding boxes.
- Tracks sub-stage progress so Java and frontend can show live QC progress.
- Stores correction, baseline, routing, and validation data for improvement
  loops.

### Java Side: Backend, Workflow, Persistence, and Security

The Java backend is a Spring Boot app running on port `8080`. It owns business
workflow, users, batches, database persistence, and reviewer decisions.

- Handles authentication, users, clients, roles, admin access, and reviewer
  access.
- Accepts ZIP uploads, extracts files, classifies appraisal/supporting document
  types, stores files, and creates `Batch` and `BatchFile` records.
- Matches appraisal files with engagement letters and contracts.
- Calls Python OCR/QC service, receives rule results, and persists them as
  `QCResult`, `QCRuleResult`, `ProcessingMetrics`, `DocStat`, and business
  events.
- Broadcasts QC progress through WebSocket topics.
- Supports reviewer sessions, locks, heartbeats, decisions, comments,
  acknowledgement, final submit, re-review requests, and admin overrides.
- Provides admin APIs for users, clients, batches, audit graph, analytics, doc
  stats, stuck batch reconciliation, and QC history.

### Frontend Side: Admin and Reviewer UI

The frontend is a Next.js app running on port `3000`. It owns the user
experience for admins and reviewers.

- Uses the Java backend API with HttpOnly cookie authentication.
- Provides login, admin dashboard, batch upload/listing, client management, user
  management, reviewer assignment, audit view, analytics, and DocStats screens.
- Shows QC progress with polling/WebSocket updates while Java and Python process
  documents.
- Provides reviewer queue, review sessions, rule cards, evidence comparison,
  PDF viewer integration, decision save, submit, re-review, and override flows.
- Displays source evidence, confidence, page number, and field-level PDF
  coordinates when available.

## End-to-End Flow

1. Admin logs in from the frontend.
2. Admin uploads a batch ZIP from the frontend.
3. Java validates the upload, extracts files, stores them, and creates batch
   records.
4. Java matches appraisal files with engagement letter and contract files.
5. Admin starts QC processing.
6. Java calls Python `/qc/process` with the appraisal and supporting PDFs.
7. Python extracts fields, enriches weak/missing fields, locates evidence on PDF
   pages, runs QC rules, and returns structured results.
8. Java saves QC summary, rule results, evidence, confidence, timings, and
   progress metrics.
9. Frontend receives live progress and then shows the batch/result status.
10. Reviewer opens the queue, starts a review session, checks rule evidence,
    jumps to PDF pages/boxes, saves decisions, and submits the final review.
11. Java stores decisions, audit events, and final QC status.

## Implemented Feature List

- Authentication and roles: Admin and reviewer access with Java security and
  frontend session handling.
- Client management: Admin can create and manage client organizations.
- Batch upload: Admin can upload batch ZIP files and assign them to clients.
- File extraction and storage: Java extracts uploaded files and stores them in a
  batch-based upload structure.
- Document type handling: Appraisal, engagement, and contract files are handled
  as separate document roles.
- File matching: Appraisal files are matched with supporting engagement and
  contract documents.
- QC processing trigger: Admin can start QC on a batch from the frontend.
- Python service health/progress: Java can check Python availability and poll
  per-job progress.
- Adaptive OCR: Python chooses embedded text, OCR, or mixed extraction depending
  on document quality.
- Layered field extraction: Multiple deterministic and AI-assisted extractors
  combine to improve field coverage.
- Comparable-grid extraction: Sales comparison fields are parsed from grid/table
  structure, including comp values and adjustment-related fields.
- Contract extraction: Sales contract price, date, concessions, buyer names, and
  related transaction facts are extracted.
- Engagement extraction: Engagement/order form details are extracted for
  cross-document comparison.
- Subject gap-fill: LLM-assisted extraction fills selected missing subject,
  cost, reconciliation, signature, and USPAP fields.
- Sketch GLA extraction: Building sketch pages can provide GLA evidence.
- Narrative extraction: Important narrative/commentary text is captured for
  rules.
- Photo analysis: Photo/comparable-photo signals are analyzed when vision
  backends are available, with fallback behavior.
- Rule engine: Python evaluates QC rules and returns PASS, FAIL, VERIFY, HOLD,
  NOT_APPLICABLE, or SKIPPED style outcomes.
- Cross-document checks: Rules compare appraisal, engagement, and contract facts
  such as address, borrower/buyer, price, date, and transaction type.
- Missing-document logic: Rules can distinguish not-applicable cases from
  required manual review when supporting documents are missing.
- Confidence handling: Extracted values carry confidence and are routed to
  auto-pass or review behavior based on reliability.
- Evidence model: Rule results include document-tagged evidence, values,
  confidence, source page, method, and comparable/source labels.
- Field locator highlights: Python locates extracted values on PDF pages and
  returns normalized bounding boxes for reviewer click-to-scroll/highlight.
- Java persistence: QC results, rule results, evidence, decisions, metrics, and
  business events are saved in PostgreSQL.
- WebSocket/progress updates: Java publishes QC progress to the frontend in near
  real time.
- Reviewer queue: Reviewers can see pending and submitted QC results.
- Review session locking: Review sessions use start/heartbeat tokens to reduce
  conflicting edits.
- Decision workflow: Reviewers can pass/fail rules, add comments, acknowledge
  references, and submit final decisions.
- Evidence comparison UI: Frontend highlights differences between appraisal and
  supporting document values.
- PDF page navigation: Review UI can open source PDFs and scroll to page/field
  locations when page/bbox evidence exists.
- Re-review workflow: Submitted results can request another review pass.
- Override workflow: Reviewer/admin override requests can be queued and decided.
- Audit trail: Java records business events and audit-related activity for
  batches, users, decisions, and workflow changes.
- Analytics dashboard: Admin can view operational metrics, OCR/QC metrics, SLA
  trends, and anomalies.
- DocStats: Per-appraisal timing captures pipeline stage, rule timing, LLM
  inference time, throttle wait, rate-limit hits, and slowest rules.
- QC history: Java exposes prior QC runs for a file, including active and
  superseded results.
- Stuck batch reconciliation: Admin can ask Java to recover batches stuck in
  processing states.
- Corrections and baseline support: Python stores reviewer corrections and can
  run baseline accuracy checks.
- Routing configuration: Python exposes confidence threshold configuration for
  fields/AMC profiles.

## Implemented Quality and Operational Factors

- Accuracy factor: Multiple extraction layers are combined so weak areas in one
  method can be repaired by another.
- Confidence factor: Each field and rule can carry confidence to avoid treating
  uncertain extraction as definite truth.
- Evidence factor: Reviewer decisions are backed by source document, value,
  page, method, and confidence.
- Location factor: Page and bounding box coordinates allow faster human review
  and reduce manual searching in PDFs.
- Resilience factor: Python uses fallback behavior for unavailable AI/vision
  backends and avoids crashing the full QC path when one overlay fails.
- Performance factor: Java uses async QC processing and Python reports stage
  progress/timings for long-running jobs.
- Auditability factor: Java records workflow decisions, events, reviewer action,
  and processing metrics.
- Human-in-loop factor: VERIFY/HOLD outcomes route uncertain or policy-sensitive
  items to reviewers instead of auto-approving them.
- Security factor: Frontend calls Java with cookie-based auth, and Java enforces
  admin/reviewer role boundaries.
- Observability factor: Logs, progress snapshots, DocStats, analytics, and
  history screens make processing behavior visible.

## Main Runtime Ports

- Frontend: `http://localhost:3000`
- Java backend: `http://localhost:8080`
- Python OCR/QC service: `http://localhost:5001`
- PostgreSQL: application database
- Redis/Groq/Groq/Gemini: optional or configured support services depending
  on the active environment

