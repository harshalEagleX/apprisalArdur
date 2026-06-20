---
name: Enterprise UX
description: Apply the SHAL enterprise-UX design rules to every frontend change — operator-first, data-dense, decision-driving, non-overlapping. Use whenever building or reviewing admin/reviewer UI.
---

## Enterprise UX rules for SHAL

This product is an **Appraisal Quality Control platform** (Upload → OCR → QC → Review →
Decision → Export). It competes with nCino, Blend, ICE/Encompass, Appraisal Firewall.
Build **operator-first**, not designer-first. Apply these rules to every UI change.

### Hard constraints (never violate)
- **Do NOT change the theme or the color palette.** Work within the existing dark theme and
  tokens. Improve layout, density, hierarchy, and behavior — not the brand colors.
- **No component may overlap or block another.** Floating/overlay elements (activity monitor,
  watermark, toasts, drawers) must yield to content: reserve space, collapse, or move on
  demand. They must "feel" the other components and never cover them.
- **Intelligent/responsive:** components adjust where necessary (collapse on narrow widths,
  dock instead of float when content would be occluded, respect safe areas).
- **Backend must always match the frontend** (and vice-versa): any UI affordance/policy must
  be backed by a real endpoint/flag, and any backend policy must be mirrored in the UI copy.

### Layout & density
1. **Content > decoration.** Never waste >30% of screen on empty space/background grid. Keep
   decorative backgrounds ≤10% visual weight. Content consumes 80–90% width.
2. **Tables are the primary enterprise UI.** Lists that scale (batches, users, clients, queue,
   docstats) are dense tables, not big cards. Cards are for detail views. Target 15–50 rows
   per viewport, not 2–3. Offer density modes (comfortable/compact/dense) where lists are long.
3. **Sidebar ≤220px**, collapsible to ~72px. Don't waste workspace on a wide rail for few items.
4. **Three-tier visual hierarchy** per row/screen: primary (id, status, progress) > secondary
   (client, files, reviewer, date) > tertiary (actions). Don't give everything equal weight.

### Decision-driving (the core principle)
5. **Every screen answers in 5s:** What is happening? What needs attention? What do I do next?
6. **Every metric must support a decision.** Bad: "17.2s". Good: "61% of time waiting for AI →
   raise Groq limit / reduce concurrency." If no action follows a metric, remove it.
7. **Every page has ONE primary action** (Overview→Assign work, Batch→Run QC, Review→Review
   findings, DocStats→Investigate bottlenecks).
8. **Status without explanation is a bug.** "Needs Review" → "Needs Review · 7 validation
   failures". Every status is actionable and reasoned.
9. **Internal telemetry (per-rule ms, throttle, AI-call counts) is diagnostics**, not primary
   UX. Put it under a Diagnostics/Developer area, not main navigation.
10. **Severity layer:** rank by impact (🔴 major / 🟡 moderate / 🟢 healthy) instead of flat lists.
11. **Charts reveal trends, not decorate.** Never draw a trend line with <7 points — show
    "Latest vs Previous · Δ%" or "Not enough history yet" instead.

### States
12. **Empty states educate** ("No batches yet — upload your first appraisal package [Upload]"),
    never bare 0s that read as "broken". Don't show 0/"-" metrics as if data exists; use the
    empty state.
13. **Loading states** are mandatory: skeletons, progress bars, optimistic updates.
14. **Long-running ops show Progress + ETA + Current step + Failures** (e.g. QC: "1/3 files ·
    ETA 3m · GPT-OSS-120B · 0 errors").

### Color semantics (within the existing palette)
15. Reserve semantic meaning: success=green, warning=amber, error=red, info=blue,
    neutral=gray. Purple = brand only. Don't color every number; let fail(red)/review(amber)
    stand out against neutral pass.

### Accessibility
16. Body/metadata text ≥ WCAG AA 4.5:1 (aim 7:1). No tiny low-contrast gray on dark for
    evidence metadata, confidence, timestamps, section labels.

### Navigation & search
17. **Global search (⌘K)** across batch/file/reviewer/client/address/loan number — not a
    different search box per page.
18. **Breadcrumbs** for hierarchy (Dashboard › Batches › Batch #…).
19. **Bulk actions:** when rows are selectable, a contextual toolbar appears (Assign / Run QC /
    Delete / Export / Archive).
20. **Overlays open on demand:** activity/notifications live behind a bell/Activity Center or a
    right drawer — never a permanent floating card that covers content.

### Reviewer workspace (the "money screen")
21. **Reframe around Findings → Evidence → Decision**, not Rules → Confidence → Status.
    Evidence comes BEFORE the decision controls ("show proof before asking for judgment").
22. **Hide passed rules by default** (show Fail + Needs-Review; "Show passed" is opt-in). Cuts
    cognitive load massively.
23. **Progress is hero information** (large bar + "46/47 · 1 decision remaining"), not a tiny
    counter.
24. **Confidence framed safely:** "High confidence · evidence available", never a bare "100%"
    that invites blind trust.
25. **High-risk actions are guarded:** Override-to-Pass is visually secondary to Confirm-Fail
    (or behind a modal). Don't make the risky and safe actions identical-weight.
26. **Keyboard review mode:** F=Confirm Fail, P=Override Pass, N/J/K=navigate. Every repetitive
    reviewer workflow needs shortcuts.
27. **PDF ↔ finding sync:** clicking a finding jumps the PDF to the page and highlights the
    evidence box.
28. **Queue = table** (Priority/File/Client/Rules/Failures/Assigned/Age/Action). Detail = cards.
    Reviewers process 50–500/week; cards don't scale.

### Process
- When implementing, change layout/behavior/hierarchy — not colors/theme.
- Keep this list as the checklist for any admin/reviewer screen PR.
- Track the redesign in `readme/UX_Redesign_Plan.md`; update its status as items ship.
