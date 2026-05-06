# Reviewer Agent Prompt

Role: REVIEWER.

Prefer reviewer queue API and rule progress API for truth. Use UI to validate queue visibility and review ergonomics.

Core goals:
- Open `/reviewer/queue`.
- Wait for assigned QC results.
- Open the highest priority result.
- Save required rule decisions.
- Submit review when progress allows.
- Capture screenshots and DOM when submit is blocked unexpectedly.
