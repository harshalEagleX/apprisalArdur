# OCR Service Models

## Two-Database Design

This project uses **two completely separate PostgreSQL databases**:

| Database | Managed by | Tables |
|----------|-----------|--------|
| Java schema | Hibernate / Spring Data JPA | `_user`, `batch`, `batch_file`, `qc_result`, `qc_rule_result`, `audit_log`, `processing_metrics` |
| Python schema | SQLAlchemy + Alembic | `documents`, `page_ocr_results`, `extracted_fields`, `rule_results`, `feedback_events`, `training_examples`, `rules_config`, `llm_response_cache` |

The two databases are **completely separate**. Java never reads Python tables directly.
Java receives QC results from Python via a **REST API call** to port 5001.

## Files in this directory

| File | Purpose |
|------|---------|
| `db_models.py` | SQLAlchemy ORM for the Python service's own database. Correctly placed here. |
| `appraisal.py` | Pydantic models for structured appraisal data (in-memory, not persisted by Python). |
| `difference_report.py` | Pydantic models for extraction result diffs. |
| `field_meta.py` | `FieldMetaResult` — wraps a field value with confidence, source page, extraction method. |

## Why models live in the Python service, not in Java

The `db_models.py` tables exist **only for the Python service's internal needs**:
- OCR result caching (avoid re-running Tesseract on the same PDF)
- ML training data collection (operator feedback → training examples)
- LLM response caching (avoid re-calling Ollama for identical commentary)
- Rule configuration (toggle rules live without code restart)

Java has its own schema for user-facing data (`qc_result`, `qc_rule_result`).
Python's `rule_results` table is an internal audit trail, not the same as Java's.

## Communication flow

```
Java (port 8080)
  └─ POST /qc/process/{batchId}
       └─ PythonClientService → HTTP POST → Python (port 5001) /qc/process
                                              ├─ runs OCR pipeline
                                              ├─ runs 136 rules
                                              ├─ stores results in Python DB
                                              └─ returns PythonQCResponse JSON
  ← Java stores QCResult + QCRuleResult[] in Java DB
```
