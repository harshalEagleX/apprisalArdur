# Renamed to form_llm_extractor.py — this shim keeps old imports working.
from app.extraction.form_llm_extractor import *  # noqa: F401, F403
from app.extraction.form_llm_extractor import (  # explicit for type checkers
    extract_gap_fields_llm,
    extract_subject_contract_llm,
    GAP_FIELDS,
    ALWAYS_REFILL,
    SUBJECT_LLM_VERSION,
    PAGE_GROUPS,
)
