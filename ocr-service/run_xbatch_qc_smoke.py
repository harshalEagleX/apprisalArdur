import hashlib
import json
from collections import Counter
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(Path(__file__).resolve().parent / ".env")

from app.database import get_db
from app.models.db_models import ExtractedFieldRecord, RuleConfig, RuleResultRecord
from app.ocr.ocr_pipeline import OCRPipeline
from app.qc_processor import SmartQCProcessor
from app.rule_engine.rules_db import seed_rules_config


SETS = [
    {
        "key": "8234",
        "appraisal": ROOT / "uploads/EQSS/xBatch/appraisal/8234 E Pearson.pdf",
        "engagement": ROOT / "uploads/EQSS/xBatch/engagement/8234 E Pearson Order form.pdf",
        "contract": ROOT / "uploads/EQSS/xBatch/contract/8234 E Pearson Purchase-agreement.pdf",
    },
    {
        "key": "2307",
        "appraisal": ROOT / "uploads/EQSS/xBatch/appraisal/2307 Merrily Cir N.pdf",
        "engagement": ROOT / "uploads/EQSS/xBatch/engagement/2307 Merrily order form.pdf",
        "contract": ROOT / "uploads/EQSS/xBatch/contract/2307 Merrily CONTRACT (1).pdf",
    },
    {
        "key": "96",
        "appraisal": ROOT / "uploads/EQSS/xBatch/appraisal/96 Baell Trace Ct SE.pdf",
        "engagement": ROOT / "uploads/EQSS/xBatch/engagement/96 Baell Tr Ct Order form.pdf",
        "contract": ROOT / "uploads/EQSS/xBatch/contract/96 baell Tr Ct CONTRACT.pdf",
    },
]

RUN_TOKEN = datetime.utcnow().strftime("%Y%m%d%H%M%S")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def pdf_text(path: Path) -> str:
    result = OCRPipeline(use_tesseract=False).extract_all_pages(str(path))
    return "\n\n".join(result.page_index[p] for p in sorted(result.page_index))


def interesting_rules(result):
    wanted = {
        "S-1", "S-2", "C-1", "C-2", "C-3", "C-4", "C-5",
        "SCA-1", "SCA-2", "SCA-24", "SCA-25", "SCA-27",
        "PH-5", "PH-6", "I-10", "I-13", "SIG-3",
    }
    rows = []
    for rule in result.rule_results:
        if rule.rule_id in wanted or rule.status in {
            "fail",
            "cross_doc_mismatch",
            "source_missing",
            "extraction_failed",
            "system_error",
        }:
            rows.append({
                "rule_id": rule.rule_id,
                "status": rule.status,
                "message": rule.message,
            })
    return rows


def db_audit(document_id, processing_job_id):
    with get_db() as db:
        fields_query = db.query(ExtractedFieldRecord).filter(
            ExtractedFieldRecord.document_id == document_id
        )
        rules_query = db.query(RuleResultRecord).filter(
            RuleResultRecord.document_id == document_id
        )
        if processing_job_id:
            fields_query = fields_query.filter(ExtractedFieldRecord.processing_job_id == processing_job_id)
            rules_query = rules_query.filter(RuleResultRecord.processing_job_id == processing_job_id)
        fields = fields_query.all()
        rules = rules_query.all()
        unsafe_nulls = [
            f.field_name
            for f in fields
            if f.field_value is None and (f.extraction_status or "").upper() == "FOUND"
        ]
        return {
            "extracted_fields": len(fields),
            "unsafe_null_fields": unsafe_nulls,
            "missing_extraction_status": sum(1 for f in fields if not f.extraction_status),
            "db_rule_status_counts": dict(Counter(r.status for r in rules)),
            "null_rule_confidence": sum(1 for r in rules if r.confidence_score is None),
        }


def main():
    seed_rules_config()
    with get_db() as db:
        rules_config_count = db.query(RuleConfig).count()

    processor = SmartQCProcessor()
    output = {"rules_config_count": rules_config_count, "runs": []}

    for item in SETS:
        for field in ("appraisal", "engagement", "contract"):
            if not item[field].exists():
                raise FileNotFoundError(item[field])

        engagement_text = pdf_text(item["engagement"])
        contract_text = pdf_text(item["contract"])
        result = processor.process_document(
            pdf_path=str(item["appraisal"]),
            engagement_letter_text=engagement_text,
            contract_text=contract_text,
            file_hash=sha256(item["appraisal"]),
            original_filename=item["appraisal"].name,
            model_provider="disabled",
            model_name="disabled",
            vision_model="disabled",
            correlation_id=f"xbatch-smoke-{RUN_TOKEN}-{item['key']}",
            idempotency_key=f"xbatch-smoke-{RUN_TOKEN}-{item['key']}-{sha256(item['appraisal'])[:12]}",
        )
        output["runs"].append({
            "key": item["key"],
            "success": result.success,
            "document_id": result.document_id,
            "processing_job_id": result.processing_job_id,
            "cache_hit": result.cache_hit,
            "total_pages": result.total_pages,
            "processing_time_ms": result.processing_time_ms,
            "status_counts": result.status_counts,
            "passed": result.passed,
            "failed": result.failed,
            "review": result.review,
            "not_applicable": result.not_applicable,
            "source_missing": result.source_missing,
            "extraction_failed": result.extraction_failed,
            "ocr_low_confidence": result.ocr_low_confidence,
            "cross_doc_mismatch": result.cross_doc_mismatch,
            "system_error": result.system_error,
            "interesting_rules": interesting_rules(result),
            "db_audit": db_audit(result.document_id, result.processing_job_id),
        })

    print(json.dumps(output, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
