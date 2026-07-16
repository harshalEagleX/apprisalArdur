"""registry — the version-namespaced field registry (L2).

BBOX_PROVENANCE_REGISTRY_PLAN.md Phase 1. Keyed by (uad_version, form_type,
field_id) from day one so UAD 2.6 and 3.6 orders coexist without a rekey through
the 2026-11-02 → 2027-05-03 transition. Today it answers ONE question —
form-aware applicability (is a field absent on this form?) — but the same loader
grows to carry caption stop-text, cell regions, and per-vendor XML reliability.
"""

from app.registry.loader import registry

__all__ = ["registry"]
