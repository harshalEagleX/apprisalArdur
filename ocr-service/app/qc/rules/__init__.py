"""Importing this package registers every QC rule via the @rule decorator."""

from app.qc.rules import (  # noqa: F401
    addendum,
    arithmetic,
    comp_grid,
    commentary,
    contract,
    cross_field,
    fha_usda,
    global_rules,
    improvements,
    neighborhood,
    order_rules,
    reconciliation,
    sales_comparison,
    signature,
    site,
    subject,
)
