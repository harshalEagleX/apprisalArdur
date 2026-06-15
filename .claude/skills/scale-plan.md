---
name: Scale Plan
description: Keep readme/SCALABILITY_PLAN.md in sync with reality — verify a phase, record measured numbers, advance the tracker
---

## Scale Plan

Maintain the platform scaling effort defined in `readme/SCALABILITY_PLAN.md` (targets:
50+ concurrent users, 5,000 docs, 250+ docs/day, fast read/write). This skill is the
**only** sanctioned way to update that document — it keeps the plan honest (P-8: numbers
are measured, never guessed) and the Progress Tracker truthful.

### When to invoke
- After landing any increment from a phase → record what changed + the measured gate result.
- When asked "what's next" / "where are we" on scaling → report status from the tracker.
- When a config knob in §4.1 changes → update the table and the rationale.
- Before starting a phase → confirm the prior phase's **Gate** actually passed.

### Steps
1. **Read the plan.** Open `readme/SCALABILITY_PLAN.md`. Identify the current phase from
   §10 Progress Tracker and the relevant target(s) in §1.
2. **Verify against code, don't trust memory.** Use the code-review-graph MCP tools first
   (`semantic_search_nodes`, `query_graph`, `get_minimal_context`), then Read, to confirm
   what is actually implemented vs. what the plan claims. Key anchors to re-check:
   - Queue real? `ocr-service/requirements.txt` has celery/redis; `ocr-service/celery_app.py`
     exists; `main.py` exposes `/qc/submit` + `celery_worker_running`.
   - Sizing: `AsyncConfig.java`, `application.yml` (Hikari), `ocr-service/app/database.py`.
   - Read path: pagination/DTO/`@Cacheable` in `ReviewerApiController` + repos.
   - Indexes applied; Postgres + backup config present (Phases 5).
3. **Confirm the measurement (P-8).** A phase is only "Gate passed" if its measurement was
   actually run. If a number is claimed, find its source (load test output, slow-query log,
   docs/h from a soak run). If there's no evidence, mark the phase ◐ In progress, not ☑.
4. **Update the document, surgically:**
   - §9 **Measured Baselines** — fill real p50/p95, docs/h, latencies. Never invent.
   - §10 **Progress Tracker** — flip status (☐/◐/☑), set dates, add a one-line note.
   - §1 **Targets** — flip a target to "met (date, number)" only when its Phase-6 (or
     equivalent) measurement passed.
   - §2A **Service inventory** / §2B **QL findings** — when a service is refactored, mark the
     relevant QL-# resolved (strike or note the phase that closed it) and correct any profile
     that changed; add a new QL-# if a fresh query/latency issue is found.
   - §4.1 config table / §8 risks — adjust if reality diverged (e.g. Groq tier decision R-1).
   - Bump the footer date.
5. **Respect scope.** Stay within the locked decisions in §0 (single host, Redis+Celery,
   local FS + backups). If a decision needs to change, surface it and ask before rewriting
   the plan around it.
6. **Don't duplicate.** Edit the existing doc; do not create a parallel plan file. Honor the
   DB policy in `CLAUDE.md` (no Flyway/Liquibase/Alembic).

### Output Format
- One short status line: current phase + whether its gate passed.
- A bullet list of exactly what you changed in the doc (section + before→after).
- Any new risk or measurement that contradicts a prior claim, called out explicitly.
- The single next action (the next unstarted phase's first task, or the open gate to close).

### Guardrails
- Measured > assumed. If you cannot measure it, say so and leave the cell `_TBD_`.
- Never mark a target "met" without a recorded measurement (P-8, P-1 Level 2).
- Keep edits minimal and reviewable; this is a living doc, not a rewrite each time.
