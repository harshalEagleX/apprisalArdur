# UX Redesign Plan — Ardur QC (enterprise-grade)

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
- ⬜ Queue as a dense table (Priority/File/Client/Rules/Failures/Assigned/Age/Action).
- ✅ Trimmed reviewer queue stat tiles 5 → 3 (Pending / With failures / Completed by you).
- ✅ Submitted screen: closure summary card (reviewed/confirmed/overrides/passed). Copy-rejection-
  language + Request-re-review already present. (PDF Download still TODO.)
- ⬜ Reviewer-facing language: Finding/Issue/No-issue (keep rule ids in a detail/diagnostics view).

## Phase 3 — Admin density & hierarchy
- ✅ Bulk-action toolbar already present. Richer progress (elapsed + ETA) shipped. 3-tier row
  visual hierarchy still TODO.
- 🟡 Width: Users/Clients/Batches/DocStats now fill to 1800px (was 1200–1500 left-aligned/centered). Density modes + Clients-as-table still TODO.
- ✅ Clients dense TABLE with real per-client stats (batches/files/success/last-activity) via a
  new grouped /api/admin/clients/stats endpoint (no N+1). Users table extra columns still TODO.
- ✅ Sidebar ≤220px (w-[220px]) + already collapsible. Grid overlay already 3.2% (within rule).
- ✅ Overview: removed the Workflow-Visibility duplication — flat metric row trimmed 8→4
  (resources+health); pipeline stages live only in the actionable Workflow section.
- ⬜ Overview: richer Recent Activity row; bigger reviewer-workload table.
- 🟡 Empty states: ✅ Analytics empty-state + ✅ breadcrumbs on Clients/DocStats detail. ⌘K global search + more empty/loading states still TODO.

## Phase 4 — DocStats: operator-first
- ✅ DocStats detail: actionable "so what" insight banner (dominant cost + recommendation).
- ⬜ Human-readable stage workflow; severity ranking (🔴/🟡/🟢).
- ⬜ Move per-rule telemetry under a Diagnostics area (not primary nav).
- ✅ Trend now shows latest-vs-previous (with Δ%) under 7 runs instead of a misleading line.
- ⬜ Rule-ranking: add recommendations. Stage workflow rename + move per-rule telemetry to Diagnostics.

## Phase 5 — Cross-cutting
- ⬜ Color semantics pass (fail=red, review=amber, pass=neutral; purple=brand only) — within
  the existing palette, no new colors.
- ⬜ Accessibility contrast pass (≥ WCAG AA on metadata/confidence/timestamps).
- ⬜ Per-screen "one primary action".

## Open question for the user
- **File handling at scale:** files are 5–50 MB, 100+/day. Decide upload constraints + filters
  (per-file size cap, accepted types, virus/scan, chunked upload, per-file status/age filters in
  the queue). Needs a short spec before building the queue/table filters.
