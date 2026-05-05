# Ardur Appraisal QC Frontend Workflow

This frontend is a Next.js 16 application for an appraisal quality-control platform. It is not a public marketing site; it is an authenticated operations workspace used by two real roles:

- `ADMIN`: manages client organisations, users, batch uploads, QC processing, reviewer assignment, recovery, and analytics.
- `REVIEWER`: works an assigned verification queue, reviews rule failures/VERIFY items against PDFs, saves decisions, and signs off reviews.

The frontend talks to a Java/Spring backend at `NEXT_PUBLIC_JAVA_URL`, falling back to `http://localhost:8080`. Authentication is cookie based. Most pages are protected by the Next.js `proxy.ts` route gate that calls `/api/me` before allowing access.

## High-Level Application Flow

```text
User opens app
  -> / checks /api/me
  -> unauthenticated: /login
  -> ADMIN: /admin
  -> REVIEWER: /reviewer/queue

Admin workflow
  -> create client organisation
  -> create admin/reviewer users
  -> upload ZIP batch for a client
  -> run QC with selected Ollama model
  -> poll backend QC progress
  -> if REVIEW_PENDING, assign reviewer
  -> reviewer completes manual decisions
  -> batch becomes COMPLETED
  -> admin monitors analytics/recovery

Reviewer workflow
  -> open /reviewer/queue
  -> choose prioritized QC result
  -> open /reviewer/verify/[id]
  -> frontend starts review session lock
  -> load rules, progress, documents
  -> compare rule evidence against PDF
  -> save PASS/FAIL decisions
  -> submit sign-off after all required decisions are saved
  -> return to queue
```

## Tech Stack

- Framework: Next.js App Router.
- UI: React 19 client components, Tailwind CSS 4 classes, lucide-react icons.
- PDF rendering: `react-pdf` and pdf.js worker.
- HTTP: native `fetch`; most endpoints are wrapped in `lib/api.ts`.
- Realtime: plain WebSocket wrapper at `/ws/qc` with topic subscription messages.
- State style: local React state and small module-level stores for toast/activity jobs.
- Device policy: admin/reviewer workspaces block phone-sized layouts using `DeviceGate`.

## Route Map

```text
/
  app/page.tsx
  Role router. Calls /api/me, sends admins to /admin, reviewers to /reviewer/queue.

/login
  app/login/page.tsx
  Username/password form. Posts to backend /login, then redirects to /.

/admin
  app/admin/layout.tsx -> components/shared/AdminLayout.tsx
  app/admin/page.tsx
  Admin overview/dashboard.

/admin/batches
  app/admin/batches/page.tsx
  Batch upload, search, filter, QC run/stop, reviewer assignment, delete, recovery.

/admin/users
  app/admin/users/page.tsx
  Create/edit/delete users. Roles are ADMIN and REVIEWER.

/admin/clients
  app/admin/clients/page.tsx
  Create and list client organisations.

/analytics
  app/analytics/page.tsx
  Admin-only analytics dashboard. Protected by proxy as an admin path.

/reviewer/queue
  app/reviewer/layout.tsx -> components/shared/ReviewerLayout.tsx
  app/reviewer/queue/page.tsx
  Reviewer assigned work queue.

/reviewer/verify/[id]
  app/reviewer/verify/[id]/page.tsx
  app/reviewer/verify/[id]/PdfDocumentViewer.tsx
  Side-by-side PDF/rule review workspace.

/help
  app/help/page.tsx
  Help articles and operator guidance.

Global error and 404
  app/error.tsx
  app/not-found.tsx
```

## Authentication And Access Control

### Middleware

`proxy.ts` runs for all routes except static Next assets and the favicon.

```text
request path
  -> if /login: allow
  -> call Java backend /api/me with browser cookie
  -> no role: redirect /login?next=<path>
  -> /admin or /analytics and role is not ADMIN: redirect /reviewer/queue
  -> otherwise allow
```

The proxy has these protected admin prefixes:

```text
/admin
/analytics
```

Reviewer pages are protected by login, but not restricted away from admins by proxy. Admin-only routes are explicitly restricted.

### Runtime Redirects

`lib/api.ts` also handles auth failures:

- `401` or `302` from API calls redirect to `/login`.
- failed cross-origin fetch caused by Spring Security login redirects is treated as unauthenticated and redirects to `/login`.
- `403` throws `Access denied`.

### Login/Logout

`login(username, password)` posts form data to backend `/login` with credentials included. Success redirects to `/`, where `app/page.tsx` routes by role.

`logout()` posts to backend `/logout`, then layouts send the user to `/login`.

## Backend API Contract Used By Frontend

Central API wrapper: `lib/api.ts`.

### Auth

```text
POST /login
POST /logout
GET  /api/me
```

### Admin Dashboard

```text
GET /api/admin/dashboard
GET /api/reviewer/dashboard
```

The admin dashboard expects keys such as:

```text
totalBatches
pendingOcr
pendingReview
inReview
completed
errors
reviewerCount
clientOrganizations
recentBatches
reviewers
reviewerWorkload
```

### Users

```text
GET    /api/admin/users?page=<n>&size=<n>
POST   /api/admin/users
PUT    /api/admin/users/{id}
DELETE /api/admin/users/{id}
```

### Clients

```text
GET  /api/admin/clients
POST /api/admin/clients
```

### Batches And QC

```text
GET    /api/admin/batches?page=<n>&size=20&status=<status>&search=<text>
GET    /api/admin/batches/{id}
GET    /api/admin/batches/{id}/status
POST   /api/admin/batches/upload
POST   /api/qc/reconcile
POST   /api/qc/process/{batchId}
POST   /api/qc/cancel/{batchId}
GET    /api/qc/progress/{batchId}
POST   /api/admin/batches/{batchId}/assign
DELETE /api/admin/batches/{batchId}
GET    /api/qc/results/{batchId}
GET    /files/{batchFileId}
```

### Reviewer

```text
GET  /api/reviewer/qc/results/pending
GET  /api/reviewer/qc/{qcResultId}/rules
GET  /api/reviewer/qc/{qcResultId}/progress
POST /api/reviewer/qc/{qcResultId}/session/start
POST /api/reviewer/qc/{qcResultId}/session/heartbeat
GET  /api/qc/file/{qcResultId}
POST /api/reviewer/decision/save
POST /api/reviewer/qc/{qcResultId}/submit
WS   /ws/qc
```

Reviewer realtime topics:

```text
/topic/reviewer/qc/{qcResultId}/progress
/topic/reviewer/qc/{qcResultId}/decision
```

### Analytics

`app/analytics/page.tsx` fetches:

```text
GET /api/analytics/overview?days=7|30|90
GET /api/analytics/ocr?days=7|30|90
GET /api/analytics/ml?days=7|30|90
GET /api/analytics/operators?days=7|30|90
GET /api/analytics/trend?days=7|30|90
GET /api/analytics/review-sla
GET /api/analytics/anomalies?days=7|30|90
```

Note: `lib/api.ts` has helpers for most analytics endpoints, but the analytics page uses a local `api()` helper and additionally calls `/api/analytics/ml`.

## Data Model Concepts

### Client

A client organisation/tenant:

```text
id
name
code
status
createdAt
```

Client code is used for storage paths and cleanup logic according to the modal copy.

### User

```text
id
username
email
fullName
role: ADMIN | REVIEWER
client?: Client
createdAt
```

Reviewers must be assigned to a client organisation in the frontend validation. Admins are platform scoped and do not require a client.

### Batch

```text
id
parentBatchId
status
client
files
fileCount
assignedReviewer
createdBy
errorMessage
createdAt
updatedAt
```

### Batch File

```text
id
filename
fileType: APPRAISAL | ENGAGEMENT | CONTRACT
fileSize
status
orderId
documentQualityFlags
```

### QC Result

A processed appraisal file result:

```text
id
batchFile
qcDecision: AUTO_PASS | TO_VERIFY | AUTO_FAIL
finalDecision?: PASS | FAIL
totalRules
passedCount
failedCount
verifyCount
manualPassCount
processingTimeMs
cacheHit
processedAt
```

### QC Rule Result

One rule/evidence item in reviewer workflow:

```text
id
ruleId
ruleName
status
message
actionItem
appraisalValue
engagementValue
confidence
extractedValue
expectedValue
verifyQuestion
rejectionText
evidence
help
reviewRequired
reviewerVerified
reviewerComment
firstPresentedAt
decisionLatencyMs
acknowledgedReferences
overridePending
overrideRequestedBy
overrideRequestedAt
verifiedAt
severity
pdfPage
bboxX / bboxY / bboxW / bboxH
```

## Status Lifecycle

Batch statuses shown by `StatusBadge`:

```text
UPLOADED
  -> batch uploaded and ready for QC

VALIDATING
  -> backend is validating uploaded archive

VALIDATION_FAILED
  -> upload/archive structure failed validation

QC_PROCESSING
  -> OCR/model/rule processing is running

REVIEW_PENDING
  -> QC finished and human review is needed

IN_REVIEW
  -> reviewer has started/locked review work

COMPLETED
  -> QC/review workflow is complete

ERROR
  -> QC failed; admin can retry, reconcile, inspect error, delete, or reupload
```

QC decision statuses:

```text
AUTO_PASS
TO_VERIFY
AUTO_FAIL
```

Rule statuses:

```text
pass
fail
verify
MANUAL_PASS
```

## Admin Layout

`components/shared/AdminLayout.tsx` wraps all `/admin/*` pages.

It provides:

- left sidebar navigation
- collapsible sidebar on narrower screens
- sign-out button
- global toast container
- global background activity monitor
- `DeviceGate` blocking screens under 768px

Navigation:

```text
Overview  -> /admin
Batches   -> /admin/batches
Users     -> /admin/users
Clients   -> /admin/clients
Analytics -> /analytics
```

## Admin Overview Page

File: `app/admin/page.tsx`

Purpose: the admin control-room homepage.

On load:

```text
page mounts
  -> getAdminDashboard()
  -> calculate counts
  -> show next-best action
  -> show workflow stage cards
  -> show recent activity
  -> show reviewer workload
```

Main panels:

- next best action
- system signals
- eight stat cards
- workflow visibility links
- attention areas
- recent activity
- reviewer workload

Next-best-action logic:

```text
if errors > 0
  -> "Fix failed batches" -> /admin/batches?status=ERROR
else if pendingReview > 0
  -> "Assign review work" -> /admin/batches?status=REVIEW_PENDING
else if pendingOcr > 0
  -> "Monitor QC processing" -> /admin/batches?status=QC_PROCESSING
else
  -> "System is clear" -> /admin/batches
```

Workflow stage links:

```text
QC running      -> /admin/batches?status=QC_PROCESSING
Awaiting review -> /admin/batches?status=REVIEW_PENDING
In review       -> /admin/batches?status=IN_REVIEW
Completed       -> /admin/batches?status=COMPLETED
Errors          -> /admin/batches?status=ERROR
```

## Admin Batches Page

File: `app/admin/batches/page.tsx`

Purpose: batch intake and operational management.

On load:

```text
read URL params: page, status, search
  -> debounce search by 350ms
  -> load getAdminBatches(page, status, search)
  -> load getAllUsers()
  -> load getAdminDashboard()
  -> filter users to reviewers
  -> store reviewer workload
  -> auto-poll any batch already QC_PROCESSING
```

Visible controls:

- Reconcile
- Upload batch
- search
- status filter
- model selector
- table pagination
- per-row Run QC / Retry
- per-row Stop
- per-row Assign reviewer
- per-row Delete
- per-row Recovery drawer for errors

Batch list arrow flow:

```text
Admin opens /admin/batches
  -> batches load from backend
  -> admin filters/searches
  -> admin uploads ZIP or runs QC on existing batch
  -> row status updates
  -> progress polling starts
  -> QC finishes
  -> page reloads latest batch state
  -> if review is needed, admin assigns reviewer
```

Upload flow:

```text
Upload batch button
  -> UploadModal opens
  -> getClients()
  -> admin chooses client organisation
  -> admin selects ZIP file
  -> frontend validates:
       file must end .zip
       file must be <= 50 MB
       client must be selected
  -> POST /api/admin/batches/upload
  -> show simulated progress while server responds
  -> success toast
  -> reload batch table
```

QC run flow:

```text
Run QC / Retry
  -> POST /api/qc/process/{batchId}
       body: { provider: "ollama", textModel, visionModel }
  -> optimistic row status QC_PROCESSING
  -> toast "QC started"
  -> useBatchPolling.startPolling(batch)
  -> poll every 2 seconds:
       GET /api/admin/batches/{id}/status
       GET /api/qc/progress/{id}
  -> update inline row progress
  -> update global ActivityMonitor
  -> when status leaves QC_PROCESSING:
       stop polling
       remove job
       show success/error/info toast
       reload batches
```

Stop QC flow:

```text
Stop button
  -> POST /api/qc/cancel/{batchId}
  -> stop polling
  -> remove global job
  -> set local row back to UPLOADED with "QC stopped by admin"
  -> reload batches
```

Assignment flow:

```text
Batch status REVIEW_PENDING
  -> ReviewerAssignControl appears
  -> reviewers are ranked by:
       same client fit first
       lower active workload second
       display name third
  -> admin chooses reviewer
  -> POST /api/admin/batches/{batchId}/assign
  -> reload table
```

Recovery flow:

```text
Batch has ERROR or VALIDATION_FAILED and errorMessage
  -> click error text
  -> BatchRecoveryDrawer opens
  -> drawer classifies failure advice by error text
  -> admin can:
       copy error
       retry QC
       upload replacement
       delete batch
```

Reconcile flow:

```text
Reconcile button
  -> POST /api/qc/reconcile
  -> backend returns:
       stuckFound
       retried
       abandoned
       pythonHealthy
       message
  -> page shows reconciliation summary
  -> reload batches if any were retried
```

Delete flow:

```text
Delete icon
  -> ConfirmDialog
  -> DELETE /api/admin/batches/{batchId}
  -> success toast
  -> reload
```

## Admin Users Page

File: `app/admin/users/page.tsx`

Purpose: manage platform access.

Load flow:

```text
page mounts
  -> GET /api/admin/users?page=<page>&size=20
  -> display table
```

Features:

- local search by username, full name, or email
- page controls
- create new user
- edit existing user
- delete user with confirmation
- role summary counts for admins/reviewers

Create user flow:

```text
New user
  -> UserModal opens with empty user
  -> GET /api/admin/clients
  -> admin enters username, password, name, email, role
  -> if role REVIEWER, client org is required
  -> POST /api/admin/users
  -> reload users
```

Edit user flow:

```text
Edit button
  -> UserModal opens with user data
  -> username/password are not edited here
  -> admin edits fullName/email/role/client
  -> PUT /api/admin/users/{id}
  -> reload users
```

Delete user flow:

```text
Delete button
  -> ConfirmDialog
  -> DELETE /api/admin/users/{id}
  -> reload users
```

Frontend validations:

- username required for new users
- password minimum 8 characters for new users
- email must look valid if present
- reviewers must have a client organisation

## Admin Clients Page

File: `app/admin/clients/page.tsx`

Purpose: create/list tenant client organisations.

Load flow:

```text
page mounts
  -> GET /api/admin/clients
  -> render client cards
```

Features:

- search by name, code, or status
- total client count
- active client count
- create new client modal

Create client flow:

```text
New client
  -> ClientModal opens
  -> admin enters organisation name and short code
  -> frontend validates:
       name required
       code required
       code must match /^[A-Z0-9_-]{2,10}$/
  -> POST /api/admin/clients
  -> reload clients
```

## Analytics Page

File: `app/analytics/page.tsx`

Purpose: admin-only reporting dashboard.

Load flow:

```text
page mounts or day range changes
  -> fetch all analytics endpoints in parallel
  -> render overview, OCR, compliance, operators, trend, SLA, anomaly sections
```

Day filters:

```text
7d
30d
90d
```

Sections:

- overview cards
- document reading quality
- compliance rule results
- team performance
- daily trend
- review SLA queue
- compliance flags
- guidance banner explaining metrics

Important links:

```text
Pending Review  -> /admin/batches?status=REVIEW_PENDING
VERIFY Over SLA -> /analytics#review-sla
Open in-review  -> /admin/batches?status=IN_REVIEW
Awaiting review -> /admin/batches?status=REVIEW_PENDING
Back            -> /admin
```

## Reviewer Layout

File: `components/shared/ReviewerLayout.tsx`

Wraps `/reviewer/*` pages.

It provides:

- top navigation
- Queue link
- Help link
- active review badge when on `/reviewer/verify`
- sign out
- global toasts
- `DeviceGate` blocking screens under 768px

## Reviewer Queue Page

File: `app/reviewer/queue/page.tsx`

Purpose: show assigned QC results needing reviewer decisions.

Load flow:

```text
page mounts
  -> GET /api/reviewer/qc/results/pending
  -> store pending QC results
  -> read q and view from URL
  -> select first prioritized item
```

Queue sorting/prioritisation:

```text
sort by:
  failedCount descending
  verifyCount descending
  processedAt ascending
```

Filtering:

```text
view=all      -> all assigned items
view=failures -> failedCount > 0
view=review   -> failedCount == 0
q=<text>      -> filename, QC id, or qcDecision
```

Queue page arrow flow:

```text
Reviewer opens queue
  -> sees next review action
  -> failures are grouped first
  -> reviewer filters/searches if needed
  -> reviewer clicks Review
  -> navigates to /reviewer/verify/{qcResultId}?returnTo=<queue URL>
```

Keyboard shortcuts:

```text
/       focus queue search
Escape  clear search
r       refresh queue
n       open next prioritized item
j/down  move selection down
k/up    move selection up
Home    select first item
End     select last item
Enter   open selected item
1       all
2       failures
3       review only
```

## Reviewer Verify Page

File: `app/reviewer/verify/[id]/page.tsx`

Purpose: the main human verification workspace.

This page is desktop/laptop only. It uses `DeviceGate` with `minWidth=1024` and blocks tablets/phones because the layout depends on side-by-side PDF and rule panels.

Initial load:

```text
route id -> qcResultId
  -> parse safe returnTo path
  -> start review session:
       POST /api/reviewer/qc/{id}/session/start
  -> load rules and progress:
       GET /api/reviewer/qc/{id}/rules
       GET /api/reviewer/qc/{id}/progress
  -> load file/document info:
       GET /api/qc/file/{id}
  -> connect WebSocket:
       /ws/qc
       subscribe progress topic
       subscribe decision topic
  -> render PDF left and rule checklist right
```

Review session behavior:

```text
start session
  -> backend returns sessionToken
  -> frontend requires token before saving decisions
  -> heartbeat every 120 seconds
  -> if backend says previous lock/prior decisions exist:
       show warning
       reviewer can acknowledge and continue
```

PDF/document behavior:

```text
documents come from /api/qc/file/{qcResultId}
  -> buttons for Report, Order, Contract
  -> active PDF URL is /files/{batchFileId}
  -> react-pdf renders all pages
  -> rule focus can jump to extracted pdfPage
  -> bbox coordinates draw an amber highlight overlay
```

Rule panel behavior:

```text
load QCRuleResult[]
  -> normalize status manual_pass -> MANUAL_PASS
  -> calculate counts:
       pass
       fail
       review
  -> filter:
       all
       fail
       verify
       pass
  -> search rule fields
  -> select/focus rule
```

Decision rules:

```text
PASS save allowed when:
  -> reviewRequired is true
  -> sessionToken exists
  -> browser online
  -> not already saving
  -> if current status is fail, comment has at least 20 chars
  -> if blocking verify, reviewer acknowledged references

FAIL save allowed when:
  -> same session/online/saving checks pass
  -> current rule status is verify
```

Decision save flow:

```text
reviewer clicks Save Pass or Save Fail
  -> calculate decisionLatencyMs from firstPresentedAt
  -> POST /api/reviewer/decision/save
       ruleResultId
       decision
       comment
       sessionToken
       decisionLatencyMs
       acknowledged
  -> update local rule status/comment
  -> mark saved
  -> decrement progress pending locally
  -> refresh progress from backend
  -> WebSocket decision events can also apply saved decisions
```

Submit/sign-off flow:

```text
Submit review
  -> GET latest /api/reviewer/qc/{id}/progress
  -> if canSubmit false, stay on page
  -> if canSubmit true, open SignOffDialog
  -> reviewer types last 4 digits of qcResultId
  -> optional notes
  -> POST /api/reviewer/qc/{id}/submit
       notes
       sessionToken
  -> redirect to returnTo queue URL
```

Reviewer verify keyboard shortcuts:

```text
Escape  clear rule search or session error
r       reload rules/progress
/       focus rule search
1       all rules
2       fail rules
3       needs review rules
4       pass rules
j/down  next rule
k/up    previous rule
Enter   focus selected rule and scroll it into view
n       next pending required decision
c       focus comment field for active rule
a       toggle acknowledgement for active rule
s       submit review
[       previous document
]       next document
+/=     zoom in
-       zoom out
0       reset zoom
p       save PASS for active rule when allowed
f       save FAIL for active rule when allowed
```

## RuleCard Details

File: `components/reviewer/RuleCard.tsx`

Each rule card can show:

- rule id
- rule name
- severity badge
- status color
- save state
- prior saved state
- override pending state
- SLA countdown/expired warning
- message, verification question, or rejection text
- evidence comparison
- action item
- confidence
- rule help
- acknowledgement checkbox for blocking VERIFY items
- override reason warning for failing rules
- Save Pass / Save Fail buttons
- comment textarea

Special rules:

```text
VERIFY rule
  -> user must wait 8 seconds from firstPresentedAt before action unlocks
  -> can save PASS or FAIL

BLOCKING VERIFY rule
  -> user must check acknowledgement before saving

FAIL rule
  -> only PASS is presented as override
  -> comment must be at least 20 characters
  -> second reviewer approval may be required by backend

PASS / MANUAL_PASS rule without reviewRequired
  -> no action required
```

## Evidence Comparison

File: `components/reviewer/EvidenceCompare.tsx`

Purpose: make mismatches obvious.

```text
found value = appraisalValue or extractedValue
expected value = engagementValue or expectedValue
tokenize both values
highlight tokens in either side that do not appear in the other
show PDF page label, confidence, and reason/question text
```

## Help Page

File: `app/help/page.tsx`

Purpose: simple guidance articles for users.

Topics:

- how to upload and process a file
- understanding file status labels
- understanding PASS/FAIL/VERIFY
- what to do when something goes wrong
- access and permissions
- best practices for faster processing

Note: the implemented account model is `ADMIN` and `REVIEWER`.

## Shared Components And Utilities

### `DeviceGate`

Blocks workspaces on too-small screens. This protects admin tables and reviewer PDF decisions from cramped layouts.

### `Toast`

Module-level toast store in `lib/toast.ts`, rendered by `components/shared/Toast.tsx`.

Toast types:

```text
success
error
info
notice
```

### `ActivityMonitor`

Shows background QC jobs tracked in `lib/jobs.ts`.

```text
QC starts
  -> trackJob(qc-{batchId})
  -> polling updates current/total/stage/model/sub-stage
  -> monitor shows floating progress panel
  -> QC finishes/stops/errors
  -> removeJob(qc-{batchId})
```

### `StatusBadge`

Central display mapping for batch statuses, QC decisions, and rule statuses.

### `ConfirmDialog`

Used for destructive confirmation, mainly deleting batches and users.

### Skeleton/Spinner/EmptyState/StatCard

Small reusable display primitives for loading, empty states, and dashboards.

### UI Components

`components/ui/*` contains shadcn-style primitive components (`button`, `input`, `card`, `tabs`, etc.). The current app mostly uses custom Tailwind markup directly, but these primitives are available.

## Important Frontend State Stores

### Toast Store

`lib/toast.ts`

```text
toast.success/error/info/notice
  -> add ToastItem
  -> notify subscribers
  -> ToastContainer renders
  -> auto-dismiss after duration
```

### Job Store

`lib/jobs.ts`

```text
trackJob()
updateJob()
removeJob()
subscribeJobs()
```

This is used by admin batch polling and `ActivityMonitor`.

## File-Level Responsibility Map

```text
app/layout.tsx
  Global HTML/body shell, fonts, metadata.

app/page.tsx
  Authenticated role router.

app/login/page.tsx
  Login form.

proxy.ts
  Server-side route guard using /api/me.

lib/api.ts
  Backend client and TypeScript interfaces.

lib/jobs.ts
  In-memory active QC job tracker.

lib/toast.ts
  In-memory toast tracker.

hooks/useBatchPolling.ts
  Admin QC progress polling and background activity updates.

hooks/useReviewSession.ts
  Reviewer session lock and heartbeat.

hooks/useWebSocket.ts
  Realtime topic subscription.

hooks/useKeyboardShortcuts.ts
  Stable keydown listener helper.

components/shared/AdminLayout.tsx
  Admin shell, sidebar, signout, toasts, activity monitor.

components/shared/ReviewerLayout.tsx
  Reviewer shell, top nav, signout, toasts.

components/admin/UploadModal.tsx
  ZIP upload modal.

components/admin/BatchRow.tsx
  One admin batch table row and row-level actions.

components/admin/BatchRecoveryDrawer.tsx
  Error inspection and recovery actions.

components/admin/ReviewerAssignControl.tsx
  Reviewer ranking and assignment select.

components/admin/ClientModal.tsx
  Client organisation creation.

components/admin/UserModal.tsx
  User create/edit modal.

components/reviewer/RuleCard.tsx
  Human rule decision UI.

components/reviewer/EvidenceCompare.tsx
  Found-vs-expected evidence display.

components/reviewer/SignOffDialog.tsx
  Final review submission confirmation.

app/reviewer/verify/[id]/PdfDocumentViewer.tsx
  PDF rendering and target highlight overlay.

app/globals.css
  Tailwind import, theme variables, focus styles, scrollbar, data table scroll shadow.
```

## Complete Operator Workflow In Plain Words

An admin signs in and lands on the overview. The overview tells them what needs attention first: failed batches, unassigned review work, running QC, or a clear system. From there, the admin usually goes to Batches.

Before uploading work, an admin creates client organisations and reviewer users. A reviewer belongs to a client organisation; this client fit is later used when recommending assignments.

On the Batches page, the admin uploads a ZIP archive for a client. The frontend checks only basic file rules: it must be a ZIP and not bigger than 50 MB. The backend does the real archive validation. After upload, the batch appears in the table, usually as `UPLOADED` or validation-related status.

The admin starts QC by pressing Run QC. The frontend sends the selected Ollama model choice to the backend, changes the row to `QC_PROCESSING`, and starts polling every two seconds. While QC runs, the row shows file count, stage, percent, model details, and sub-stage. A floating background activity monitor also appears so the admin can navigate while processing continues.

When QC ends, the backend status determines the next admin action. If it becomes `COMPLETED`, no reviewer is needed. If it becomes `REVIEW_PENDING`, the admin assigns a reviewer. If it becomes `ERROR` or `VALIDATION_FAILED`, the admin opens the recovery drawer, reads/copies the error, retries QC, deletes the batch, or uploads a replacement.

The reviewer signs in and lands on the verification queue. The queue shows assigned QC results, prioritizing files with failures first, then files with more review items, then older items. The reviewer can filter all/failures/review-only, search, refresh, or use keyboard navigation.

When the reviewer opens a QC result, the frontend starts a review session lock. That session token is required for saving any decisions. The page loads the rules, current progress, document list, and PDFs. The screen is split: PDF on the left, decision checklist on the right.

For each rule, the reviewer can inspect the evidence. If the backend provided a PDF page and bounding box, clicking/focusing the rule jumps to the page and highlights the location. The evidence card compares the value found in the appraisal/report with the value expected from the engagement/order data.

Rules that need review allow a saved decision. VERIFY rules can be saved as Pass or Fail. Blocking VERIFY rules require the reviewer to acknowledge that they reviewed the referenced document sections. Failed rules can be overridden with Pass, but the frontend requires a specific comment of at least 20 characters; the backend may then require a second reviewer approval.

Each saved decision posts to the backend with the rule id, decision, comment, session token, decision latency, and acknowledgement flag. The frontend updates immediately, refreshes progress, and also listens for realtime decision/progress events over WebSocket.

Once all required decisions are saved, Submit review becomes available. The reviewer presses Submit, the page asks for the last four digits of the QC result id, optional notes can be entered, and the frontend posts final sign-off to the backend. After success, the reviewer returns to the queue.

Admins can later inspect analytics for processing volume, OCR quality, rule pass rates, model/rule behavior, operator throughput, SLA issues, and compliance flags.

## Key Observations

- The real implemented roles are `ADMIN` and `REVIEWER`.
- The frontend assumes a Java backend on port 8080 unless `NEXT_PUBLIC_JAVA_URL` is set.
- Admin and reviewer workspaces intentionally block phone-sized layouts.
- Most backend calls are centralized in `lib/api.ts`, but reviewer queue, review submit, and analytics page also use direct `fetch`.
- QC progress uses polling, while reviewer decisions use REST plus optional WebSocket updates.
- The app is operational and internal: upload, process, review, decide, sign off, monitor.
