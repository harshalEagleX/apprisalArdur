"""
Foundation tests — schema, extraction format, database, test set, baseline, corrections.

From the 30-day plan, Week One exit criteria are:
  ✓ The field schema covers all document types and all extractable fields.
  ✓ Every extraction function returns the structured result format.
  ✓ All database tables exist and have been tested.
  ✓ The test set has at least 15 documents with verified correct extractions.
  ✓ Baseline accuracy numbers are recorded.
  ✓ The correction capture interface is functional (API endpoint responds).

Run:
    conda run -n apprisal python -m pytest tests/test_week1_exit_criteria.py -v
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from sqlalchemy import inspect

from app.core.schema import schema_loader
from app.database import engine, get_db, verify_connection
from app.models.db_models import (
    BaselineRunRow,
    CorrectionRow,
    ExtractionResultRow,
    FieldSchemaLogRow,
    TestGroundTruthRow,
    TestSetDocumentRow,
)
from app.services.correction_service import CorrectionRequest, save_correction


REQUIRED_TABLES = [
    "adaptive_extraction_results",
    "adaptive_corrections",
    "adaptive_amc_profiles",
    "adaptive_amc_template_versions",
    "adaptive_field_schema_log",
    "adaptive_test_set",
    "adaptive_test_ground_truth",
    "adaptive_baseline_runs",
]


# ---------------------------------------------------------------------------
# Criterion 1: Field schema covers all document types and extractable fields
# ---------------------------------------------------------------------------

class TestCriterion1Schema:

    def test_schema_loads_successfully(self):
        assert schema_loader.schema_version != "unknown"
        assert len(schema_loader.all_fields()) >= 100

    def test_all_four_document_types_represented(self):
        sections_covered = set()
        for f in schema_loader.all_fields():
            sections_covered.update(f.sections)
        assert "subject" in sections_covered
        assert "contract" in sections_covered
        assert "neighborhood" in sections_covered
        assert "site" in sections_covered
        assert "improvements" in sections_covered
        assert "sales_comparison" in sections_covered
        assert "reconciliation" in sections_covered
        assert "engagement_letter" in sections_covered

    def test_required_cross_document_fields_present(self):
        cross_doc = [f for f in schema_loader.all_fields() if f.required == "required_cross_document"]
        names = [f.canonical_name for f in cross_doc]
        assert "property_address" in names
        assert "borrower_name" in names
        assert "lender_name" in names
        assert "city" in names
        assert "state" in names
        assert "zip_code" in names

    def test_every_field_has_at_least_one_synonym(self):
        no_synonyms = [
            f.canonical_name for f in schema_loader.all_fields()
            if not f.synonyms and f.required != "derived"
        ]
        assert not no_synonyms, f"Fields with no synonyms: {no_synonyms}"

    def test_synonym_lookup_works(self):
        assert schema_loader.get_field("Borrower Name") is not None
        assert schema_loader.get_field("BORROWER NAME") is not None
        assert schema_loader.get_field("Client Name") is not None
        assert schema_loader.get_field("Purchase Price") is not None
        assert schema_loader.get_field("Final Opinion of Value") is not None


# ---------------------------------------------------------------------------
# Criterion 2: Every extraction returns the structured result format
# ---------------------------------------------------------------------------

class TestCriterion2ExtractionFormat:

    def test_every_field_returns_extraction_result(self):
        from app.core.result import ExtractionResult, ExtractionResultSet
        from app.extraction.tier3_pattern import Tier3PatternExtractor
        from app.ocr.document import load_pdf

        pdf = Path("../uploads/EQSS/MSL/engagement/96 Baell Tr Ct Order form.pdf")
        if not pdf.exists():
            pytest.skip("Test document not available")

        extractor = Tier3PatternExtractor()
        doc = load_pdf(pdf)
        rs = extractor.extract(doc, "engagement_letter")

        assert isinstance(rs, ExtractionResultSet)
        for _, result in rs:
            assert isinstance(result, ExtractionResult), f"Got {type(result)}"
            if result.found:
                assert result.confidence > 0.0, f"Found field {result.canonical_name} has confidence=0"
                assert result.source_page > 0, f"Found field {result.canonical_name} has source_page=0"
                assert result.extraction_method != "not_found", f"Found field with NOT_FOUND method"

    def test_not_found_fields_have_correct_state(self):
        from app.core.result import ExtractionMethod, ExtractionResult

        r = ExtractionResult(
            canonical_name="test_field",
            document_type="appraisal_report",
            extraction_method=ExtractionMethod.NOT_FOUND,
            confidence=0.0,
        )
        assert r.found is False
        assert r.value is None
        assert r.effective_confidence == 0.0


# ---------------------------------------------------------------------------
# Criterion 3: All database tables exist and have been tested
# ---------------------------------------------------------------------------

class TestCriterion3Database:

    def test_database_is_reachable(self):
        assert verify_connection(), "Cannot reach the database"

    def test_all_required_tables_exist(self):
        insp = inspect(engine)
        existing = set(insp.get_table_names(schema="public"))
        missing = [t for t in REQUIRED_TABLES if t not in existing]
        assert not missing, f"Missing tables: {missing}"

    def test_field_schema_was_seeded(self):
        with get_db() as session:
            count = session.query(FieldSchemaLogRow).filter_by(
                schema_version=schema_loader.schema_version
            ).count()
        assert count > 100, f"Schema log has only {count} rows — expected >100"

    def test_can_insert_and_query_extraction_result(self):
        with get_db() as session:
            row = ExtractionResultRow(
                document_id="test_criterion3",
                amc_id="test_amc",
                document_type="appraisal_report",
                field_name="borrower_name",
                field_value="Test Borrower",
                extraction_method="exact_label_match",
                confidence_score=0.95,
                source_page=1,
                model_version="test",
                run_id="week1_criteria_test",
            )
            session.add(row)
            session.flush()
            rid = row.id
            found = session.get(ExtractionResultRow, rid)
            assert found is not None
            assert found.field_value == "Test Borrower"
            # Clean up
            session.delete(found)


# ---------------------------------------------------------------------------
# Criterion 4: Test set has at least 15 documents with verified correct extractions
# ---------------------------------------------------------------------------

class TestCriterion4TestSet:

    def test_test_set_has_minimum_documents(self):
        with get_db() as session:
            count = session.query(TestSetDocumentRow).count()
        assert count >= 15, f"Test set has {count} documents — need at least 15"

    def test_each_document_has_ground_truth(self):
        with get_db() as session:
            docs_without_gt = (
                session.query(TestSetDocumentRow)
                .outerjoin(TestGroundTruthRow, TestSetDocumentRow.id == TestGroundTruthRow.test_document_id)
                .filter(TestGroundTruthRow.id == None)
                .all()
            )
        # All documents should have at least some ground truth
        assert not docs_without_gt, f"Documents without ground truth: {[d.document_id for d in docs_without_gt]}"

    def test_critical_fields_have_ground_truth(self):
        critical = {"property_address", "borrower_name", "state", "zip_code"}
        with get_db() as session:
            field_names = {
                r.field_name
                for r in session.query(TestGroundTruthRow.field_name).distinct()
            }
        missing = critical - field_names
        assert not missing, f"Critical fields with no ground truth: {missing}"


# ---------------------------------------------------------------------------
# Criterion 5: Baseline accuracy numbers are recorded
# ---------------------------------------------------------------------------

class TestCriterion5Baseline:

    def test_baseline_run_exists(self):
        with get_db() as session:
            count = session.query(BaselineRunRow).count()
        assert count > 0, "No baseline runs found — run scripts/seed_and_baseline.py first"

    def test_baseline_has_metrics(self):
        with get_db() as session:
            row = session.query(BaselineRunRow).order_by(
                BaselineRunRow.run_at.desc()
            ).first()
            assert row is not None
            total_docs = row.total_documents
            fa = row.field_accuracy_rate
            da = row.document_accuracy_rate
        assert total_docs > 0
        assert fa >= 0.0
        assert da >= 0.0


# ---------------------------------------------------------------------------
# Criterion 6: Correction capture interface is functional
# ---------------------------------------------------------------------------

class TestCriterion6Corrections:

    def test_can_save_correction(self):
        req = CorrectionRequest(
            document_id="test:criterion6",
            document_type="appraisal_report",
            field_name="borrower_name",
            source_page=1,
            original_extracted_value="John Smith",
            original_ocr_text="Borrower: John Smith",
            corrected_value="Jane Smith",
            reason_category="ocr_error",
            explanation="OCR read J as Ja incorrectly",
            reviewer_id="test_reviewer",
        )
        response = save_correction(req)
        assert response.correction_id > 0
        assert response.field_name == "borrower_name"
        assert response.corrected_value == "Jane Smith"

        # Verify it's in the database
        with get_db() as session:
            row = session.get(CorrectionRow, response.correction_id)
            assert row is not None
            assert row.reason_category == "ocr_error"
            assert row.original_ocr_text == "Borrower: John Smith"
            # Clean up
            session.delete(row)

    def test_all_six_reason_categories_are_valid(self):
        from app.services.correction_service import VALID_REASON_CATEGORIES
        expected = {
            "wrong_label_matched",
            "ocr_error",
            "value_wrong_location",
            "completely_absent",
            "ambiguous_context",
            "other",
        }
        assert VALID_REASON_CATEGORIES == expected

    def test_invalid_reason_category_rejected(self):
        with pytest.raises(Exception):
            CorrectionRequest(
                document_id="test",
                document_type="appraisal_report",
                field_name="borrower_name",
                reason_category="invalid_reason",
            )
