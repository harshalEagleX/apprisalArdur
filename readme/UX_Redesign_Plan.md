# UX Redesign Plan — SHAL (enterprise-grade)

Source: two Principal-Designer reviews (Admin 5.5/10, DocStats/Overview 6.8/10, Reviewer 7.6/10).
Governing rules live in the **Enterprise UX** skill (`.claude/skills/enterprise-ux.md`).
Hard constraints: **don't change theme/colors**; **no component overlaps/blocks another**;
intelligent/responsive; **backend must match frontend**.

Legend: ✅ shipped · 🟡 in progress · ⬜ planned

## Phase 0 — Critical bugs (DONE)
- ✅ Data reset on every dev restart — `ddl-auto: create` → `update` (1a4169d). Verified data persists.
- ✅ 500 "Failed to load batches" — eager-fetch `assignedReviewer` (82c153f). Verified getBatch 200.
- ✅ Submit blocked at "1 left" — configurable second-approval; solo reviewer can self-approve
  override; `/api/reviewer/config` + policy-aware UI (c29a5af).

## Phase 1 — Non-overlap / on-demand overlays (the "VERY IMPORTANT NOTE")
- ✅ ActivityMonitor: default to a small pill, expand on demand, height-bounded scroll panel,
  true minimize, remembered. Never blocks content.
- ✅ ProductWatermark moved to bottom-LEFT + low z (was bottom-right colliding with the
  ActivityMonitor); pointer-events-none so it can never block. Toasts already top-stacked.
- ⬜ Move activity into a top-nav Activity Center / bell as the longer-term home.

## Phase 2 — Reviewer workspace (highest product value)
- ✅ Hide passed rules by default — new "Needs attention" view (fail+needs-review) is the
  default; passes are an opt-in tab (key 1=attention,2=fail,3=review,4=pass,5=all).
- ✅ Progress as hero — wide bar + prominent count + "N left/all decided"; Submit turns green when ready.
- ✅ Evidence-first ordering already in place — EvidenceCompare (finding+evidence) renders before the decision controls; verified.
- ✅ Confidence framed qualitatively (High/Moderate/Low + secondary %); low confidence flagged amber.
- ✅ Override-to-Pass guarded — Confirm-Fail is now the wider/primary action; Override is muted, narrower, reason-gated.
- ✅ Keyboard review mode already present (F/P decide, J/K/N navigate, C comment, A ack, S submit, [/] docs) — verified.
- ⬜ PDF ↔ finding sync (jump + highlight evidence box) — bbox plumbing already exists.
- ✅ Queue as a dense table: priority dot / file+QC# / Issues / Uncertain / Clear / Age /
  action button (red for files with issues, neutral otherwise). Replaced card stack.
- ✅ Trimmed reviewer queue stat tiles 5 → 3 (Pending / With issues / Completed by you).
- ✅ Submitted screen: closure summary card + Copy-rejection + Request-re-review present.
- ✅ Reviewer-facing language throughout: Finding/Issue/No-issue (queue filter "Has issues",
  verify tabs Issues/Uncertain/No issues, RuleCard buttons reframed).

## Phase 3 — Admin density & hierarchy
- ✅ Bulk-action toolbar already present. Richer progress (elapsed + ETA) shipped.
- ✅ Width: all pages fill to 1800px. Clients-as-table shipped.
- ✅ Clients dense TABLE with real per-client stats (batches/files/success/last-activity).
- ✅ Sidebar ≤220px (w-[220px]) + collapsible.
- ✅ Overview: removed Workflow-Visibility duplication; pipeline stages in Workflow only.
- ✅ Overview: Recent Activity rows show fileCount badge + assignedReviewer name alongside
  client + status; rows link directly to /admin/batches/{id} (batch detail).
- ✅ Batch detail drill-in page: /admin/batches/[id] — breadcrumb, header, intake-warnings
  banner, 4 stat tiles, per-file table (severity dot, QC status, issues/review/clear counts,
  size), error message panel. Batch ID cell in BatchRow now links through.
- ✅ ⌘K global command palette (CommandPalette): searches batches/clients/users, arrow-key
  navigation, Enter to go, Esc to close, ⌘K trigger in sidebar nav.
- ✅ Empty states: Analytics + breadcrumbs on Clients/DocStats detail pages.

## Phase 4 — DocStats: operator-first
- ✅ DocStats detail: actionable "so what" insight banner.
- ✅ DocStats detail: Overview/Diagnostics tab bar — per-rule timing moves to Diagnostics;
  pipeline stages + QC sections stay in Overview.
- ✅ Severity ranking in Rule Ranking tab: colored dots (🔴 ≥1000ms / 🟡 ≥300ms / 🟢 <300ms),
  bar fill matches severity, recommendation line under each high/medium cost rule,
  legend in header counts high/medium/low rules.
- ✅ Stage labels are already human-readable via stageLabels.ts (STAGE_LABELS map).
- ✅ Trend shows latest-vs-previous (Δ%) when < 7 runs.

## Phase 5 — Cross-cutting
- ✅ Color semantics already correct in StatusBadge: fail=red, review=amber, pass=green,
  neutral=slate. No new colors introduced.
- ✅ Reviewer language reframe: queue "Failures"→"Has issues", verify tabs
  Fail→Issues / Needs Review→Uncertain / Pass→No issues; RuleCard buttons
  "Confirm Fail"→"Confirm issue", "Override to Pass"→"Override — no issue",
  "Save Pass"→"No issue", "Save Fail"→"Issue found".
- ✅ Audit Graph demoted from primary ops nav to "Insights" secondary group.
- ⬜ Accessibility contrast pass (≥ WCAG AA on metadata/confidence/timestamps).

## Open question for the user
- **File handling at scale:** files are 5–50 MB, 100+/day. Decide upload constraints + filters
  (per-file size cap, accepted types, virus/scan, chunked upload, per-file status/age filters in
  the queue). Needs a short spec before building the queue/table filters.
