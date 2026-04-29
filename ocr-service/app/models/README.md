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

## Consistency Model (Eventual Consistency — Accepted Tradeoff)

There is **no distributed transaction** between the two writes:
1. Python writes to its own DB (rule_results, extracted_fields, page_ocr_results)
2. Java writes to its own DB (qc_result, qc_rule_result)

These two writes happen sequentially over HTTP. If Java crashes between step 1 and step 2:
- Python has the results cached (by file_hash)
- Java's batch is stuck in `QC_PROCESSING`

**This is intentional and acceptable because:**

- Java is the **system of record** for QC outcomes and reviewer decisions
- Python's data is **operational** (OCR cache, ML training signals) — not what reviewers act on
- Python's `file_hash` cache makes re-processing the same file **fast** (no re-OCR)
- The `StuckBatchReconciler` detects and recovers stuck batches every 10 minutes
- The `qc_result.python_document_id` field links Java records to Python records for debugging

**Recovery path for the crash scenario:**
```
1. JVM crashes after Python writes, before Java writes
2. Batch stays in QC_PROCESSING with stale updatedAt
3. StuckBatchReconciler fires 10 minutes later
4. Calls processBatchAsync(batchId) → PythonClientService → Python returns cached result
5. Java writes QCResult this time → consistency restored
```

**The alternative — a distributed transaction (2PC/Saga) — is not justified here:**
- Adds significant complexity (coordinator, compensation logic)
- The failure window is milliseconds between two local writes
- The business consequence of divergence (ML data inconsistency) is low-severity
- The recovery is automatic and invisible to the user within 10-15 minutes
