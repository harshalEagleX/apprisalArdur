# Frontend Design Audit — Ardur QC (product-grade pass)

How the components/routes are wired, the ambiguities, and the **APIs still missing** for
detail surfaces. Companion to `readme/UX_Redesign_Plan.md`. Severity: 🔴 breaks a workflow ·
🟠 product-grade gap · 🟡 polish.

## A. Navigation / workflow breaks
- ✅ **FIXED — `/admin/overrides` now in the admin nav** (Overrides, ShieldCheck). Admin/supervisor is the override approver (route is ROLE_ADMIN by design).
- ~~🔴 `/admin/overrides` orphaned~~ (was) "Pending Overrides" is where a SECOND
  reviewer approves a FAIL→Pass override — the core of the two-person rule. It has **no nav
  link** in either AdminLayout or ReviewerLayout, and it sits under `/admin` even though the
  approver is a *reviewer*. So in multi-reviewer mode the approval step is a dead end (you can
  only reach it by typing the URL). Fix: add it to the reviewer nav (and/or surface a "N
  overrides awaiting your approval" entry point), and confirm a reviewer role can open it.
- ✅ **FIXED — `/qc-review` now redirects** to /reviewer/queue (was dead demo code).
- ~~🔴 `/qc-review` dead code~~ (was) Zero references anywhere; a legacy QC review page superseded
  by `/reviewer/verify/[id]`. Remove it (or redirect) — it's a maintenance/confusion trap.
- ✅ **FIXED — client rows now link to `/admin/clients/{id}`** (detail page: stats, recent batches, users) via new `GET /api/admin/clients/{id}`.
- ~~🟠 Client rows don't drill down~~ (was) The new Clients table has real stats but rows aren't
  clickable — there's no client-detail view (its batches/users/activity). Needs a route +
  endpoint (see C).
- 🟠 **Batch rows have no full detail view.** Actions (Run/Stop/Assign/History) are inline, and
  the History drawer shows runs, but there's no single "batch detail" (file list + per-file
  status + results) — the row is a control strip, not a drill-in.
- 🟡 **Analytics lives at `/analytics`, not `/admin/analytics`.** Inconsistent with every other
  admin route; the nav points outside the `/admin` tree.

## B. Missing APIs / data gaps (block product-grade detail)
- ✅ **FIXED — User now has `active` + `lastLoginAt`** (populated on login); Users table shows Status + Last-login.
- ~~🟠 User has no status/lastLoginAt~~ (was) `User` = {id, username, email, fullName, role,
  client, createdAt}. The reviews ask for Status + Last-login columns — both need new entity
  fields + population (track `lastLoginAt` on authenticate; an `enabled`/`status` flag).
- ✅ **FIXED — `POST /users/{id}/reset-password` + `/users/{id}/status`** added; Users table has Reset-password + Activate/Deactivate actions; deactivated users blocked at login (UserPrincipal.isEnabled).
- ~~🟠 No reset/deactivate~~ (was) Admins can create / edit /
  delete users (`createUser`/`updateUser`/`deleteUser`) but cannot reset a password or
  deactivate without deleting. Needs `POST /api/admin/users/{id}/reset-password` and a status
  toggle. ("Delete" as the only off-switch is dangerous for an audit system.)
- ✅ **FIXED — `GET /api/admin/clients/{id}`** added (client + stats + recent batches + users).
- ~~🟠 No client-detail endpoint~~ (was) `clientBatchStats` powers
  the table totals, but there's no `GET /api/admin/clients/{id}` returning that client's
  batches/users/recent activity for a drill-in page.
- 🟡 **Analytics shows raw `0`/`—` on an empty system** (endpoints exist; data is just empty).
  Not a missing API — needs an educational empty-state ("No processed files yet — upload a
  batch"), per the review.
- 🟡 **DocStats per-rule telemetry is primary nav.** The per-rule timing table is engineer-grade
  diagnostics; product-wise it belongs behind a Diagnostics sub-tab, not top-level.

## C. Placement / IA ambiguities
- 🟠 **No breadcrumbs** anywhere — on a detail page (DocStats/[id], verify/[id]) there's no
  "where am I / how do I get back to the parent list" cue beyond a single back link.
- 🟠 **No global (⌘K) search** — each page has its own search box; no cross-entity jump
  (batch/file/reviewer/client/address/loan#).
- 🟡 **Audit Graph is a top-level nav peer** of Batches/Users. The reviews rate it low on
  operational utility; consider demoting it under an "Insights"/secondary group.
- 🟡 **Reviewer language is "Rules/Pass/Fail"** throughout; reviewers think
  "Findings/Issue/No-issue". (Keep rule IDs in the evidence/detail view.)

## E. Security (found during audit)
- ✅ **FIXED — `/api/admin/users` leaked the bcrypt password hash.** Added WRITE_ONLY to User.password so it's never serialized to API responses.

## D. Confirmed-good (no action — verified during audit)
- Reviewer queue rows correctly deep-link to `/reviewer/verify/{id}` (and submitted → submitted view).
- Batch bulk-action toolbar, sidebar collapse, reviewer keyboard mode, evidence-first ordering
  all already exist and work.
- Analytics is backed by real endpoints (overview/ocr/ml/operators/trend).
- No `href="#"` / empty-onClick dead buttons found in admin or reviewer trees.

## Suggested priority order
1. 🔴 Wire **Pending Overrides** into reviewer nav (+ access) — it silently breaks the
   two-person approval the platform advertises.
2. 🔴 Delete/redirect **`/qc-review`** dead route.
3. 🟠 **User `status` + `lastLoginAt`** fields + admin **password-reset / deactivate** endpoints
   → then the Users table columns + actions menu.
4. 🟠 **Client detail** route + `GET /api/admin/clients/{id}` → clickable client rows.
5. 🟠 **Breadcrumbs** + 🟠 **⌘K global search**.
6. 🟡 Analytics empty-states; DocStats → Diagnostics sub-tab; reviewer Finding/Issue language.
