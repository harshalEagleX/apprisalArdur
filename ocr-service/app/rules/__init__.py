"""
QC Rules Module
Contains all validation rules for appraisal QC processing.

This module now focuses exclusively on:
- Subject Section Rules (S-1 to S-12)
- Contract Section Rules (C-1 to C-5)
"""

# ── Import order = execution priority ────────────────────────────────────────
# Structural / field-check rules first (fast, no LLM)
from . import subject_rules        # S-1  to S-12
from . import contract_rules       # C-1  to C-5
from . import neighborhood_rules   # N-1  to N-7   (structural completeness)
# Commentary / quality rules last (may call LLM)
from . import narrative_rules      # COM-1 to COM-7 (LLM commentary quality)

__all__ = [
    'subject_rules', 'contract_rules',
    'neighborhood_rules', 'narrative_rules',
]
