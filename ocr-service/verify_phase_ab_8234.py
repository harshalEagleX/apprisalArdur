import hashlib
import json
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(Path(__file__).resolve().parent / ".env")

from app.ocr.ocr_pipeline import OCRPipeline
from app.qc_processor import SmartQCProcessor
from app.database import get_db
from app.models.db_models import ExtractedFieldRecord, PageOCRResult, RuleResultRecord


UPLOAD = ROOT / "uploads" / "EQSS" / "8234X 2"
APPRAISAL = UPLOAD / "appraisal" / "8234 E Pearson.pdf"
ENGAGEMENT = UPLOAD / "engagement" / "8234 E Pearson Order form.pdf"
CONTRACT = UPLOAD / "contract" / "8234 E Pearson Purchase-agreement.pdf"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def pdf_text(path: Path) -> str:
    result = OCRPipeline(use_tesseract=False).extract_all_pages(str(path))
    return "\n\n".join(result.page_index[p] for p in sorted(result.page_index))


def row_value(row):
    return {
        "value": row.field_value,
        "confidence": row.confidence_score,
        "page": row.source_page,
        "method": row.extraction_method,
        "bbox": [row.bbox_x, row.bbox_y, row.bbox_w, row.bbox_h],
    }


def main():
    engagement_text = pdf_text(ENGAGEMENT)
    contract_text = pdf_text(CONTRACT)
    file_hash = sha256(APPRAISAL)

    processor = SmartQCProcessor()
    result = processor.process_document(
        pdf_path=str(APPRAISAL),
        engagement_letter_text=engagement_text,
        contract_text=contract_text,
        file_hash=file_hash,
        original_filename=APPRAISAL.name,
        model_provider="ollama",
    )

    with get_db() as db:
        page_rows = (
            db.query(PageOCRResult)
            .filter(PageOCRResult.document_id == result.document_id)
            .order_by(PageOCRResult.page_number)
            .all()
        )
        field_rows = {
            row.field_name: row
            for row in db.query(ExtractedFieldRecord)
            .filter(ExtractedFieldRecord.document_id == result.document_id)
            .all()
        }
        rule_count = (
            db.query(RuleResultRecord)
            .filter(RuleResultRecord.document_id == result.document_id)
            .count()
        )

        inspected_fields = [
            "property_address",
            "city",
            "state",
            "zip_code",
            "county",
            "owner_of_public_record",
            "legal_description",
            "assessors_parcel_number",
            "tax_year",
            "neighborhood_name",
            "map_reference",
            "census_tract",
            "lender_name",
            "lender_address",
            "comp_1_address",
            "comp_2_address",
            "comp_3_address",
        ]

        word_pages = {}
        for row in page_rows:
            try:
                word_pages[row.page_number] = len(json.loads(row.word_json or "[]"))
            except json.JSONDecodeError:
                word_pages[row.page_number] = -1

        summary = {
            "success": result.success,
            "document_id": result.document_id,
            "cache_hit": result.cache_hit,
            "total_pages": result.total_pages,
            "extraction_method": result.extraction_method,
            "processing_time_ms": result.processing_time_ms,
            "rule_count_result": result.total_rules,
            "rule_count_db": rule_count,
            "status_counts": {
                "pass": result.passed,
                "fail": result.failed,
                "verify": result.verify,
            },
            "page_word_counts_first_5": {str(k): word_pages[k] for k in sorted(word_pages)[:5]},
            "pages_with_word_json": sum(1 for count in word_pages.values() if count > 0),
            "inspected_fields": {
                name: row_value(field_rows[name])
                for name in inspected_fields
                if name in field_rows
            },
        }
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
