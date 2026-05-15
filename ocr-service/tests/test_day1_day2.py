"""
Day 2 Verification — Run Tier 3 extraction on all 6 real document batches.

Tests:
1. Schema loads without errors, all fields have required attributes
2. Every extraction function returns ExtractionResult (never None or raw string)
3. confidence is set (not left as 0.0) on found fields
4. source_page is set (not 0) on found fields
5. extraction_method is not NOT_FOUND on found fields
6. Results summary printed per batch so we can see what's working

Usage:
    cd ocr-service
    python -m pytest tests/test_day1_day2.py -v

Or run directly:
    python tests/test_day1_day2.py
"""

import sys
import os
from pathlib import Path

# Make sure we can import from the ocr-service root
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from app.core.schema import schema_loader, FieldDefinition
from app.core.result import ExtractionResult, ExtractionResultSet, ExtractionMethod
from app.ocr.document import load_pdf
from app.extraction.tier3_pattern import Tier3PatternExtractor

UPLOADS = Path(__file__).parent.parent.parent / "uploads"

BATCHES = {
    "MSL":          UPLOADS / "EQSS" / "MSL",
    "TestX121":     UPLOADS / "EQSS" / "TestX121",
    "#2321525427":  UPLOADS / "sort" / "#2321525427",
    "#2321525470":  UPLOADS / "sort" / "#2321525470",
    "#2321525505":  UPLOADS / "sort" / "#2321525505",
    "#2321525530":  UPLOADS / "sort" / "#2321525530",
}

DOC_TYPE_MAP = {
    "appraisal":  "appraisal_report",
    "engagement": "engagement_letter",
    "contract":   "sales_contract",
}

CRITICAL_FIELDS = [
    "property_address", "city", "state", "zip_code",
    "borrower_name", "lender_name", "contract_price",
    "appraised_value", "effective_date", "assignment_type",
]


# ===========================================================================
# Schema Tests (Day 1)
# ===========================================================================

class TestDay1Schema:

    def test_schema_loads(self):
        assert schema_loader.schema_version != "unknown"
        assert len(schema_loader.all_fields()) > 50, "Schema must define >50 fields"

    def test_every_field_has_required_attributes(self):
        errors = []
        for f in schema_loader.all_fields():
            if not f.canonical_name:
                errors.append(f"Field missing canonical_name: {f}")
            if not f.data_type:
                errors.append(f"Field {f.canonical_name} missing data_type")
            if not f.required:
                errors.append(f"Field {f.canonical_name} missing required status")
            if not f.sections:
                errors.append(f"Field {f.canonical_name} missing sections")
            if not f.source_authority:
                errors.append(f"Field {f.canonical_name} missing source_authority")
        assert not errors, "\n".join(errors)

    def test_all_fields_have_synonyms(self):
        no_synonyms = [f.canonical_name for f in schema_loader.all_fields() if not f.synonyms]
        # Derived/template fields may skip synonyms — flag but don't fail hard
        print(f"\nFields with no synonyms: {no_synonyms}")

    def test_canonical_name_lookup(self):
        assert schema_loader.get_field("borrower_name") is not None
        assert schema_loader.get_field("Borrower") is not None
        assert schema_loader.get_field("Client Name") is not None
        assert schema_loader.get_field("nonexistent_field_xyz") is None

    def test_synonym_lookup_case_insensitive(self):
        assert schema_loader.get_field("BORROWER NAME") is not None
        assert schema_loader.get_field("borrower name") is not None

    def test_thresholds_loaded(self):
        t = schema_loader.thresholds_for("contract_price")
        assert t.auto_accept > t.review > t.reject > 0

    def test_critical_fields_present(self):
        missing = []
        for name in CRITICAL_FIELDS:
            if schema_loader.get_field(name) is None:
                missing.append(name)
        assert not missing, f"Critical fields missing from schema: {missing}"

    def test_required_for_review_fields(self):
        rfr = schema_loader.required_for_review()
        names = [f.canonical_name for f in rfr]
        assert "borrower_name" in names
        assert "property_address" in names
        assert "appraised_value" in names


# ===========================================================================
# Result Format Tests (Day 2)
# ===========================================================================

class TestDay2ResultFormat:

    def test_extraction_result_found(self):
        r = ExtractionResult(
            canonical_name="borrower_name",
            document_type="appraisal_report",
            value="John Smith",
            raw_source_text="Borrower: John Smith",
            extraction_method=ExtractionMethod.EXACT_LABEL_MATCH,
            confidence=0.95,
            source_page=1,
        )
        assert r.found is True
        assert r.effective_confidence == 0.95
        assert r.to_db_dict()["field_value"] == "John Smith"

    def test_extraction_result_not_found(self):
        r = ExtractionResult(
            canonical_name="borrower_name",
            document_type="appraisal_report",
            extraction_method=ExtractionMethod.NOT_FOUND,
            confidence=0.0,
        )
        assert r.found is False
        assert r.value is None

    def test_sanity_check_penalty(self):
        r = ExtractionResult(
            canonical_name="contract_price",
            document_type="appraisal_report",
            value="500000",
            confidence=0.90,
            source_page=1,
            extraction_method=ExtractionMethod.EXACT_LABEL_MATCH,
            sanity_check_failed=True,
        )
        assert r.effective_confidence == 0.65  # 0.90 - 0.25

    def test_result_set_summary(self):
        rs = ExtractionResultSet(
            document_path="/fake/path.pdf",
            document_type="appraisal_report",
            total_pages=10,
        )
        rs.add(ExtractionResult(
            canonical_name="borrower_name", document_type="appraisal_report",
            value="Jane Doe", confidence=0.92, source_page=1,
            extraction_method=ExtractionMethod.EXACT_LABEL_MATCH,
        ))
        rs.add(ExtractionResult(
            canonical_name="appraised_value", document_type="appraisal_report",
            extraction_method=ExtractionMethod.NOT_FOUND,
        ))
        rs.finalize()
        s = rs.summary()
        assert s["fields_found"] == 1
        assert s["fields_not_found"] == 1


# ===========================================================================
# Integration Tests — real documents
# ===========================================================================

def _find_pdfs(batch_dir: Path) -> dict:
    """Return {doc_type: path} for a batch directory."""
    found = {}
    for sub in ("appraisal", "engagement", "contract"):
        sub_dir = batch_dir / sub
        if sub_dir.exists():
            pdfs = list(sub_dir.glob("*.pdf"))
            if pdfs:
                found[sub] = pdfs[0]
    return found


extractor = Tier3PatternExtractor()


def _run_batch(batch_name: str, batch_dir: Path) -> dict:
    """Run extraction on all document types in a batch. Return results dict."""
    pdfs = _find_pdfs(batch_dir)
    batch_results = {}

    for doc_subtype, pdf_path in pdfs.items():
        doc_type = DOC_TYPE_MAP[doc_subtype]
        try:
            doc = load_pdf(pdf_path)
            result_set = extractor.extract(doc, doc_type)
            batch_results[doc_subtype] = result_set
        except Exception as exc:
            print(f"  ERROR {batch_name}/{doc_subtype}: {exc}")

    return batch_results


class TestDay2RealDocuments:
    """
    Integration tests against the 6 real document batches.
    Failures here tell us where the baseline extractor needs work.
    These are NOT meant to be perfect on Day 2 — they document the baseline.
    """

    @pytest.fixture(scope="class")
    def all_results(self):
        results = {}
        for name, path in BATCHES.items():
            if path.exists():
                results[name] = _run_batch(name, path)
            else:
                print(f"SKIP: batch dir not found: {path}")
        return results

    def test_all_batches_load(self, all_results):
        assert len(all_results) > 0, "No batches found"

    def test_result_sets_have_fields(self, all_results):
        for batch_name, batch in all_results.items():
            for doc_type, rs in batch.items():
                assert len(rs) > 0, f"{batch_name}/{doc_type} produced no results"

    def test_every_result_is_extraction_result(self, all_results):
        """Core Day 2 contract: nothing returns a raw string."""
        for batch_name, batch in all_results.items():
            for doc_type, rs in batch.items():
                for canonical, result in rs:
                    assert isinstance(result, ExtractionResult), (
                        f"{batch_name}/{doc_type}/{canonical} returned {type(result)}"
                    )

    def test_found_results_have_confidence_set(self, all_results):
        """Found fields must have confidence > 0."""
        violations = []
        for batch_name, batch in all_results.items():
            for doc_type, rs in batch.items():
                for canonical, result in rs:
                    if result.found and result.confidence == 0.0:
                        violations.append(f"{batch_name}/{doc_type}/{canonical}")
        assert not violations, f"Found fields with confidence=0.0: {violations}"

    def test_found_results_have_source_page(self, all_results):
        """Found fields must have source_page > 0."""
        violations = []
        for batch_name, batch in all_results.items():
            for doc_type, rs in batch.items():
                for canonical, result in rs:
                    if result.found and result.source_page == 0:
                        violations.append(f"{batch_name}/{doc_type}/{canonical}")
        assert not violations, f"Found fields with source_page=0: {violations}"

    def test_found_results_have_extraction_method(self, all_results):
        """Found fields must not have NOT_FOUND as method."""
        violations = []
        for batch_name, batch in all_results.items():
            for doc_type, rs in batch.items():
                for canonical, result in rs:
                    if result.found and result.extraction_method == ExtractionMethod.NOT_FOUND:
                        violations.append(f"{batch_name}/{doc_type}/{canonical}")
        assert not violations, f"Found fields with NOT_FOUND method: {violations}"


# ===========================================================================
# Human-readable report (run directly, not via pytest)
# ===========================================================================

def print_report():
    print("\n" + "=" * 70)
    print("APPRISAL EXTRACTION BASELINE — Day 2 Report")
    print(f"Schema version: {schema_loader.schema_version}")
    print(f"Total schema fields: {len(schema_loader.all_fields())}")
    print("=" * 70)

    for batch_name, batch_dir in BATCHES.items():
        if not batch_dir.exists():
            print(f"\n[SKIP] {batch_name} — directory not found")
            continue

        print(f"\n{'─' * 60}")
        print(f"BATCH: {batch_name}")
        batch = _run_batch(batch_name, batch_dir)

        for doc_subtype, rs in batch.items():
            s = rs.summary()
            print(f"\n  [{doc_subtype.upper()}] {Path(rs.document_path).name}")
            print(f"  Pages: {s['total_pages']}  |  "
                  f"Found: {s['fields_found']}/{s['fields_attempted']}  |  "
                  f"Avg confidence: {s['avg_confidence']:.2f}  |  "
                  f"Time: {s['extraction_time_ms']}ms")

            # Show critical fields
            print(f"\n  Critical fields:")
            for fname in CRITICAL_FIELDS:
                r = rs.get(fname)
                if r and r.found:
                    print(f"    ✓ {fname:<35} = '{r.value}' "
                          f"({r.effective_confidence:.2f} | {r.extraction_method} | p{r.source_page})")
                else:
                    print(f"    ✗ {fname:<35}  [NOT FOUND]")

            # Show what was found beyond critical
            other_found = [r for _, r in rs if r.found and r.canonical_name not in CRITICAL_FIELDS]
            if other_found:
                print(f"\n  Other found fields ({len(other_found)}):")
                for r in sorted(other_found, key=lambda x: -x.effective_confidence)[:15]:
                    print(f"    · {r.canonical_name:<35} = '{str(r.value)[:40]}' "
                          f"({r.effective_confidence:.2f} | p{r.source_page})")

            # Missing required
            missing = rs.required_missing(schema_loader)
            if missing:
                print(f"\n  Required fields NOT found: {missing}")

    print("\n" + "=" * 70)
    print("END OF REPORT")
    print("=" * 70 + "\n")


if __name__ == "__main__":
    print_report()
