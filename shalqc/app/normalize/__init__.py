"""
app.normalize — SHALqc.md §4: THE one comparison-prep layer.

Public surface: `normalize(field_def, raw)`, `compare(field_def, a, b)`, and
the `normalizer` singleton (all from normalizer.py); `dates` for the shared
date parser (§17). No rule does its own string cleanup — it calls in here (P6).
"""

from app.normalize import dates  # noqa: F401
from app.normalize.normalizer import (  # noqa: F401
    MatchResult,
    compare,
    jaro_winkler,
    normalize,
    normalizer,
)
