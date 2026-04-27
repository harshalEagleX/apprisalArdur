# ── Import order = execution priority ────────────────────────────────────────
# Each import triggers the @rule decorators which self-register with the engine.
# Order determines nothing here — execution order is set in rules_db.py.
#
# Total: 136 rules across 16 files

# ── Tier 1: Subject + Contract (structural, fast) ─────────────────────────────
from . import subject_rules          # S-1..S-12   (12)
from . import contract_rules         # C-1..C-5    (5)

# ── Tier 2: Neighborhood + Site + Improvements (form completeness) ────────────
from . import neighborhood_rules     # N-1..N-7    (7)
from . import site_rules             # ST-1..ST-10 (10)
from . import improvement_rules      # I-1..I-13   (13)

# ── Tier 3: Sales Comparison + Approaches ─────────────────────────────────────
from . import sales_comparison_rules # SCA-1..SCA-27 (27)
from . import additional_approach_rules  # R-1..R-2, CA-1..CA-2, IA-1..IA-2 (6)

# ── Tier 4: Addenda + Documentation ──────────────────────────────────────────
from . import addendum_rules         # ADD-1..ADD-9  (9)
from . import doc_rules              # DOC-1..DOC-4  (4)
from . import signature_rules        # SIG-1..SIG-4  (4)

# ── Tier 5: Physical evidence (photos, maps, sketch) ─────────────────────────
from . import photo_rules            # PH-1..PH-6   (6)
from . import maps_rules             # M-1..M-4     (4)
from . import sketch_rules           # SK-1..SK-5   (5)

# ── Tier 6: Loan-type specific ────────────────────────────────────────────────
from . import fha_rules              # FHA-1..FHA-14 (14)
from . import usda_mf_rules          # USDA-1, MF-1..MF-2 (3)

# ── Tier 7: Commentary quality (LLM, runs last) ───────────────────────────────
from . import narrative_rules        # COM-1..COM-7  (7)

__all__ = [
    'subject_rules', 'contract_rules',
    'neighborhood_rules', 'site_rules', 'improvement_rules',
    'sales_comparison_rules', 'additional_approach_rules',
    'addendum_rules', 'doc_rules', 'signature_rules',
    'photo_rules', 'maps_rules', 'sketch_rules',
    'fha_rules', 'usda_mf_rules',
    'narrative_rules',
]
