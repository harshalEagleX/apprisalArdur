# OCR Service Models

## Two Ownership Boundaries

This project has **two persistence ownership boundaries**. They may run as two
physical PostgreSQL databases, or as two sets of tables in the same PostgreSQL
database during local/product deployments. The important rule is ownership, not
physical separation:

| Boundary | Managed by | Tables |
|----------|------------|--------|
| Java product schema | Hibernate / Spring Data JPA | `_user`, `batch`, `batch_file`, `qc_result`, `qc_rule_result`, `audit_log`, `processing_metrics`, `business_event`, `document_match` |
| Python OCR operational schema | SQLAlchemy ORM | `documents`, `processing_jobs`, `processing_stages`, `page_ocr_results`, `extracted_fields`, `rule_results`, `llm_call_logs`, `feedback_events`, `confidence_calibration`, `training_examples`, `rules_config`, `llm_response_cache` |

Java never reads Python tables directly. Java receives reviewer-facing QC data
from Python through the REST contract and persists it into Java-owned entities.
Python keeps technical lifecycle, cache, model, and learning-loop data. The two
sides are linked by `correlation_id`, Java batch IDs, `python_document_id`, and
`python_processing_job_id`.

## Files in this directory

| File | Purpose |
|------|---------|
| `db_models.py` | SQLAlchemy ORM for Python-owned OCR operational tables. Correctly placed here. |
| `appraisal.py` | Pydantic models for structured appraisal data (in-memory, not persisted by Python). |
| `difference_report.py` | Pydantic models for extraction result diffs. |
| `field_meta.py` | `FieldMetaResult` — wraps a field value with confidence, source page, extraction method. |

## Why models live in the Python service, not in Java

The `db_models.py` tables exist **only for the Python service's internal needs**:
- OCR result caching (avoid re-running Tesseract on the same PDF)
- Durable technical lifecycle (`processing_jobs`, `processing_stages`)
- LLM call metadata and timing (`llm_call_logs`)
- ML training data collection (operator feedback → training examples)
- LLM response caching (avoid re-calling Ollama for identical commentary)
- Rule configuration (toggle rules live without code restart)
- Reviewer-derived confidence calibration (`confidence_calibration`)

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
                                              ├─ records processing_job/stage/LLM metadata
                                              └─ returns PythonQCResponse JSON
  ← Java stores QCResult + QCRuleResult[] in Java DB
  ← Java stores python_document_id + python_processing_job_id for traceability
```

## Consistency Model (Eventual Consistency — Accepted Tradeoff)

There is **no distributed transaction** between the two owned writes:
1. Python writes to its own DB (rule_results, extracted_fields, page_ocr_results)
2. Java writes to its own DB (qc_result, qc_rule_result)

These two writes happen sequentially over HTTP. If Java crashes between step 1 and step 2:
- Python has the results cached (by file_hash)
- Java's batch is stuck in `QC_PROCESSING`

**This is intentional and acceptable because:**

- Java is the **system of record** for QC outcomes and reviewer decisions
- Python's data is **operational** (OCR cache, ML training signals) — not what reviewers act on
- Python's `file_hash` cache makes re-processing the same file **fast** (no re-OCR)
- Python's `processing_jobs.idempotency_key` prevents duplicate async jobs for
  the same business document/model/rules tuple
- The `StuckBatchReconciler` detects and recovers stuck batches every 10 minutes
- The `qc_result.python_document_id` and `qc_result.python_processing_job_id`
  fields link Java records to Python records for debugging and audit

**Recovery path for the crash scenario:**
```
1. JVM crashes after Python writes, before Java writes
2. Batch stays in QC_PROCESSING with stale updatedAt
3. StuckBatchReconciler fires 10 minutes later
4. Calls processBatchAsync(batchId) → PythonClientService → Python returns cached/idempotent result
5. Java writes QCResult this time → consistency restored
```

**The alternative — a distributed transaction (2PC/Saga) — is not justified here:**
- Adds significant complexity (coordinator, compensation logic)
- The failure window is milliseconds between two local writes
- The recovery is automatic and invisible to the user within 10-15 minutes
- Reviewer decisions are synced back to Python through `/qc/feedback`, so the
  learning loop does not depend on Java reading Python tables
