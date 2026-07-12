"""
app.rules (rul-1.0.0) — SHALqc.md §5 rule engine.

Importing this package populates the rule registry as a side effect (each rule
module's @rule decorators run on import). The public surface is the registry,
the engine, the Verdict model, and QCContext.

Rule tiers (SHALqc.md §5): deterministic/ = T1 value-compare rules (this build);
llm_judged/ = T2 narrative rules (registered, body deferred to Part 10);
custom/<amc_code>/ = per-AMC rules discovered by the profile binding (Part 6).
"""

# --- public surface ---------------------------------------------------------
from app.rules.context import QCContext  # noqa: F401
from app.rules.engine import counts, run_rules  # noqa: F401
from app.rules.registry import RuleSpec, all_rules, rule, rules_for_section  # noqa: F401
from app.rules.verdict import Evidence, Status, Verdict  # noqa: F401

# --- import rule modules so their @rule decorators register (side effect) ---
# Kept last so the registry symbols above are importable even if a rule module
# has an issue; each import is what actually adds that section's rules.
from app.rules.deterministic import (  # noqa: F401,E402
    contract, cross_document, cross_field, order_rules, site, subject)
from app.rules.llm_judged import narrative  # noqa: F401,E402

# --- catalog interpreter: register a rule per AMC-checklist item NOT already
#     hand-coded above (dedup by rule_id). This turns the whole 135-item
#     rejection catalog into runnable rules dynamically (SHALqc-CORE §4). ---
from app.rules.catalog import register_catalog_rules  # noqa: E402

register_catalog_rules()

__version__ = "rul-1.0.0"
