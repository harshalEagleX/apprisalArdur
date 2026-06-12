"""Importing this package registers every QC rule via the @rule decorator."""

from app.qc.rules import (  # noqa: F401
    addendum,
    commentary,
    contract,
    fha_usda,
    global_rules,
    improvements,
    neighborhood,
    photos,
    reconciliation,
    sales_comparison,
    signature,
    site,
    subject,
)
