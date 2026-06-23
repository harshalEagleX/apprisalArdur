# Appraisal QC — Demo Quickstart

End-to-end demo of the adaptive extraction + QC rule engine, from a transaction
folder of PDFs to a clickable reviewer dashboard.

## Prerequisites

- conda env `shal` (Python 3.11) — has all deps (pymupdf, pdfplumber,
  camelot, pytesseract, sentence-transformers, sqlalchemy, fastapi…).
  Interpreter: `/opt/homebrew/Caskroom/miniconda/base/envs/shal/bin/python`
- Local Postgres (`brew services start postgresql@18`), database `shal`.
  Connection string in `ocr-service/.env` (`postgresql://postgres@localhost/shal`).
- Tesseract (`brew install tesseract`) and Ghostscript (`brew install ghostscript`,
  enables Camelot bordered-table extraction).
- Node 20+ for the Next.js frontend.

## 1. Database

```bash
cd ocr-service
conda run -n shal python manage_db.py status     # verify adaptive_* tables exist
conda run -n shal python manage_db.py create     # create if missing
```

## 2. Run QC on the document corpus

A "transaction" is a folder under `uploads/` containing `appraisal/`,
`engagement/`, and (for purchases) `contract/` subfolders.

```bash
# QC every transaction folder, persist reports to adaptive_validation_results:
conda run -n shal python scripts/run_qc_corpus.py

# Or one transaction:
conda run -n shal python -c "from app.qc.transaction import run_transaction_qc; \
  print(run_transaction_qc('../uploads/sort/#2321525505').counts())"

# Print a readable report for one transaction:
conda run -n shal python scripts/show_qc_report.py "sort/#2321525505"
conda run -n shal python scripts/show_qc_report.py --list   # list QC'd transactions
```

## 3. API service

```bash
cd ocr-service
conda run -n shal python -m uvicorn main:app --host 127.0.0.1 --port 5001
```

Key endpoints:
| Endpoint | Purpose |
|---|---|
| `POST /qc/transaction` `{folder, store_results}` | Run the engine on a transaction folder, return the reviewer report |
| `GET /qc/report/{transaction_id}` | The persisted reviewer report (grouped by section, with evidence) |
| `GET /qc/transactions` | List every QC'd transaction + overall outcome (dashboard picker) |
| `POST /qc/process` `{document_path, document_type}` | Single-document extract + persist |
| `GET /health` | Service + schema + DB + Groq status |

## 4. Reviewer dashboard

```bash
cd frontend
npm install        # first time
npm run dev        # http://localhost:3000
```

Open **http://localhost:3000/qc-review**. Left = transaction list with overall
status; right = the selected transaction's findings grouped by section, with the
verbatim rejection wording and side-by-side evidence (which document each value
came from, its confidence, and page). Toggle "Show passed / not-applicable" to
see the full rule set.

## How it works (one screen)

```
transaction folder (appraisal + engagement + contract PDFs)
        │
        ▼  app/qc/transaction.py
  extract each doc:  layered orchestrator (L0 pdfplumber … L5 UAD template)
        │            + targeted overlays:
        │              · engagement_extractor (order-form labels)
        │              · spatial_tier3 subject-row (city/state/zip)
        │              · comp_grid_extractor (per-comp grid cells)
        │              · contract_extractor (price/date, Tesseract OCR)
        │              · photo_detector + checkbox_extractor
        ▼  app/qc/context.py  → QCContext (3 docs, loan/transaction/form type)
        ▼  app/qc/engine.py   → run 59 rules (app/qc/rules/*)
        │     5-state: PASS / FAIL / VERIFY / HOLD / NOT_APPLICABLE
        │     confidence→VERIFY gating · loan-gated FHA/USDA · verbatim templates
        ▼  persist → adaptive_validation_results
        ▼  app/qc/report.py   → reviewer JSON (sections + evidence) → dashboard
```

Tunables (no code change): `config/qc_thresholds.yaml` (confidence cutoffs, fuzzy
match bands), `config/qc_templates.yaml` (verbatim rejection wording),
`config/qc_canned_phrases.yaml` (commentary canned phrases).

See `TASK_HISTORY.txt` for the dated build log and `readme/QCChceklistOpus.md`
for the full rule reference.
