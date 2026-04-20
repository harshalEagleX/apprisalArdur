# OCR Service

FastAPI-based OCR and QC service for appraisal documents.

This service supports:
- OCR extraction from PDF files
- Rule-based QC processing
- Optional local Ollama-assisted extraction for low-confidence facts
- Human feedback capture (`/feedback/correction`)
- Feedback-driven retraining/export scripts

## Architecture (current)

- API entry: `main.py`
- QC flow: `app/qc_processor.py`
- OCR pipeline: `app/ocr/ocr_pipeline.py`
- Rule engine: `app/rule_engine/engine.py`
- Regex extraction: `app/services/extraction_service.py`
- Ollama extraction assist: `app/services/ai_extraction_service.py`
- Feedback endpoint: `app/api/v1/endpoints/feedback.py`
- Feedback store: `app/services/feedback_store.py`

## Prerequisites

- Python 3.11
- Tesseract
- Poppler tools (`pdfinfo`, `pdftoppm`)

macOS:
```bash
brew install tesseract poppler
```

## Quick Start (local Python)

```bash
cd ocr-service
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python main.py
```

Service runs on `http://localhost:5001`.

## Environment Configuration

Use `.env.example` as reference.

Core flags:
- `USE_AI_EXTRACTION` -> `true|false`
- `AI_PROVIDER` -> `ollama`
- `CONFIDENCE_THRESHOLD` -> default `0.95`

Feedback storage:
- `DATABASE_URL` set -> PostgreSQL mode
- `DATABASE_URL` empty -> SQLite mode using `FEEDBACK_DB_PATH`

## Local Ollama Assist

Ollama is optional and local. Treat its output as a suggestion for low-confidence fields, not as a QC decision. Java rules and reviewer corrections remain the source of truth.

Example:
```bash
export USE_AI_EXTRACTION=true
export AI_PROVIDER=ollama
export AI_MODEL=llama3.1:8b
export OLLAMA_BASE_URL=http://127.0.0.1:11434
```

Run Ollama model:
```bash
brew install ollama
ollama pull llama3.1:8b
ollama serve
```

## Docker Compose (Postgres + OCR Service)

From `ocr-service`:
```bash
docker compose up --build
```

This starts:
- `postgres` on `localhost:5433`
- `ocr-service` on `localhost:5001`

Compose sets:
- `DATABASE_URL=postgresql://apprisal:apprisal@postgres:5432/apprisal`

Migration bootstrap file:
- `migrations/001_create_field_corrections.sql`

## Key Endpoints

- `GET /health`
- `POST /ocr/appraisal`
- `POST /qc/extract`
- `POST /qc/process`
- `POST /feedback/correction`

## Example API Calls

Health:
```bash
curl -sS http://127.0.0.1:5001/health
```

OCR appraisal:
```bash
curl -sS -X POST http://127.0.0.1:5001/ocr/appraisal \
  -F "file=@uploads/EQSS/xBatch/appraisal/apprisal_002.pdf"
```

QC process:
```bash
curl -sS -X POST http://127.0.0.1:5001/qc/process \
  -F "file=@uploads/EQSS/xBatch/appraisal/apprisal_003.pdf"
```

Feedback correction:
```bash
curl -sS -X POST http://127.0.0.1:5001/feedback/correction \
  -H "Content-Type: application/json" \
  -d '{
    "document_id":"doc-123",
    "field_name":"borrower_name",
    "predicted_value":"John",
    "corrected_value":"John A Doe",
    "confidence_score":0.71,
    "section":"subject",
    "operator_id":"reviewer-1"
  }'
```

## Retraining/Export Scripts

Build few-shot examples from recent corrections:
```bash
python training/retrain_pipeline.py --limit 50
```

Export corrections as JSONL:
```bash
python training/export_corrections.py --limit 1000
```

Artifacts generated in:
- `training/artifacts/fewshot_examples.json`
- `training/artifacts/field_corrections.jsonl`

## Notes

- AI extraction is optional and safely falls back to regex extraction on errors.
- Feedback pipeline works in SQLite by default and PostgreSQL when `DATABASE_URL` is provided.
