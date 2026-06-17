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
- ⬜ Audit/align ProductWatermark + Toasts so overlays never collide with each other or content
  (reserve safe-area, stack, or dock).
- ⬜ Move activity into a top-nav Activity Center / bell as the longer-term home.

## Phase 2 — Reviewer workspace (highest product value)
- ✅ Hide passed rules by default — new "Needs attention" view (fail+needs-review) is the
  default; passes are an opt-in tab (key 1=attention,2=fail,3=review,4=pass,5=all).
- ✅ Progress as hero — wide bar + prominent count + "N left/all decided"; Submit turns green when ready.
- ⬜ Evidence-first ordering: Finding → Evidence → Decision controls.
- ⬜ Confidence framed safely ("High confidence · evidence available", not bare "100%").
- ✅ Override-to-Pass guarded — Confirm-Fail is now the wider/primary action; Override is muted, narrower, reason-gated.
- ⬜ Keyboard review mode: F/P confirm, N/J/K navigate.
- ⬜ PDF ↔ finding sync (jump + highlight evidence box) — bbox plumbing already exists.
- ⬜ Queue as a dense table (Priority/File/Client/Rules/Failures/Assigned/Age/Action).
- ⬜ Trim reviewer queue summary cards 7 → 3 (Pending / Needs-review / Completed today).
- ⬜ Submitted-result screen: closure summary + Download/Copy-language/Request-re-review.
- ⬜ Reviewer-facing language: Finding/Issue/No-issue (keep rule ids in a detail/diagnostics view).

## Phase 3 — Admin density & hierarchy
- ⬜ Batches: 3-tier row hierarchy (id/status/progress primary), richer progress (ETA, current
  file, engine, errors), bulk-action toolbar on selection.
- ⬜ Tables everywhere (Users, Clients, DocStats batch) with density modes; fill 80–90% width.
- ⬜ Users table: add Status/Last-login/Org/Actions. Clients: stats card (users/batches/files/
  success/last-activity) instead of one empty card.
- ⬜ Sidebar ≤220px, collapsible to ~72px. Reduce decorative grid background to ≤10%.
- ⬜ Overview: group 8 metrics → Pipeline/Resources/Health; remove the Workflow-Visibility
  duplication; richer Recent Activity row; bigger reviewer-workload table.
- ⬜ Empty states that educate (no bare 0s); skeleton loading states; breadcrumbs; ⌘K global search.

## Phase 4 — DocStats: operator-first
- ⬜ Reframe metrics to "so what" (e.g. "61% time waiting for AI → raise Groq limit").
- ⬜ Human-readable stage workflow; severity ranking (🔴/🟡/🟢).
- ⬜ Move per-rule telemetry under a Diagnostics area (not primary nav).
- ⬜ Rule-ranking: add recommendations. Trend: require ≥7 points or show "not enough history".

## Phase 5 — Cross-cutting
- ⬜ Color semantics pass (fail=red, review=amber, pass=neutral; purple=brand only) — within
  the existing palette, no new colors.
- ⬜ Accessibility contrast pass (≥ WCAG AA on metadata/confidence/timestamps).
- ⬜ Per-screen "one primary action".

## Open question for the user
- **File handling at scale:** files are 5–50 MB, 100+/day. Decide upload constraints + filters
  (per-file size cap, accepted types, virus/scan, chunked upload, per-file status/age filters in
  the queue). Needs a short spec before building the queue/table filters.
