"""
app.language — the v1.0.69 language-driven judgment path (final_shalqccore.md).

A SECOND judgment path behind JUDGE_MODE=language. The AMC checklist's own text
IS the rule: the engine extracts every labeled value, binds each check to real
labels (compiled once per checklist), hands the LLM the check text + labeled
values + coordinates, and turns every reply into a reviewer card. The reviewer
is final — the engine only ever drafts.

Nothing in the legacy path (app/rules/*) changes; extraction, merge, normalize,
back-locator, LLM client, report shell are all reused unchanged.
"""

__version__ = "lang-1.0.69"
