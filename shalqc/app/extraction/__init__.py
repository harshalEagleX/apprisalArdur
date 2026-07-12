"""
app.extraction — SHALqc.md §3: intake → extract → normalize input.

Public entry point: `app.extraction.merge.run_extraction`. Everything else in
this package (schema, result, xml_extractor, pdf_digital, pdf_scanned,
grid_extractor, checkbox, engagement, llm_gapfill, plausibility) is an
implementation detail of that orchestrator — callers outside this package
should not need to import the individual extractors directly.
"""

from app.extraction.merge import run_extraction  # noqa: F401
from app.extraction.result import ExtractedField, ExtractedFieldSet, Source  # noqa: F401
from app.extraction.schema import schema_loader  # noqa: F401
