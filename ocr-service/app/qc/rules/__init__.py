"""Importing this package registers every QC rule via the @rule decorator."""

from app.qc.rules import (  # noqa: F401
    contract,
    global_rules,
    improvements,
    neighborhood,
    reconciliation,
    sales_comparison,
    signature,
    site,
    subject,
)
