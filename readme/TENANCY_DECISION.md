# Tenancy Decision — Single Organization (CONFIRMED by owner)

**Status:** Confirmed by business owner · **Date:** 2026-06-21 · **Applies to:** whole platform

> **Owner confirmation (2026-06-21):** "Our system is for office internal use only — nothing like multi-tenant." The platform is a single-organization internal tool. Multi-tenancy is **explicitly out of scope**, so the entire TEN-* checklist is **N/A by design**, not a set of defects. `organization_id`, tenant row-filtering, and Postgres RLS are intentionally absent because there is no second tenant to isolate.

Closes audit items **DB-010, TEN-001, TEN-002, TEN-003, TEN-004, TEN-005, TEN-007, TEN-008, JAVA-008** by making the (previously implicit) tenancy model **explicit**.

## Decision

The SHAL platform runs as a **single-organization (single-tenant) deployment.**
There is intentionally **no `organization_id`** and no cross-tenant row isolation.

- `Role` = `{ADMIN, REVIEWER}` is the access model.
- `client` (the AMC/lender on a `Batch`) is a **business dimension**, *not* a security boundary. One organization processes work for many clients; staff of that organization may legitimately see all clients.

## Why this is safe (the boundary that IS enforced)

The audit confirmed the access boundary is **per-reviewer assignment**, enforced in code — not "everyone sees everything":

- `ReviewerApiController` + `VerificationService.assertReviewerOwns{QcResult,RuleResult,Batch}` — a REVIEWER can only read/act on batches assigned to them.
- `findPendingForReviewer(userId, pageable)` / `findRecentlyReviewedForReviewer(userId)` scope every reviewer list query by user id.
- ADMIN sees across all clients — **expected** for a single-org operator.

So within the single-org model there is **no IDOR** at the reviewer level; the only cross-client visibility is ADMIN, which is correct.

## What would change if we ever go multi-organization

This is a deliberate, planned change — **not** a drop-in. If a second isolated organization is onboarded:

1. Add `organization_id` (FK) to `client`, `user`, `batch`, and — by inheritance through `batch_file` — to the QC result chain. Backfill all existing rows to org #1.
2. Add a tenant filter to every repository read/write (Hibernate `@Filter` or a `WHERE organization_id = :org` enforced in a base repository), plus the same scoping on Python `adaptive_*` reads if they ever serve cross-org data.
3. Scope dedup (`findByFileHash`) and reviewer assignment by `organization_id`.
4. Consider Postgres RLS as defense-in-depth.
5. Re-run the TEN-* checklist against the new model.

Until that decision is made, the single-org model above is the **declared, enforced** posture and the TEN-* items are closed as *by design*, not as defects.
