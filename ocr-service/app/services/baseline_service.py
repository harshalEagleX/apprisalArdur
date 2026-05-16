"""
Day 4 — Baseline Measurement Service

Two responsibilities:
  1. seed_test_set()  — load ground_truth.yaml into the database test set tables
  2. run_baseline()   — extract all test documents, compare to ground truth,
                        store results in adaptive_baseline_runs, return metrics

This is the measurement infrastructure the plan requires before any extraction
improvements can be claimed as meaningful.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import yaml

from app.config import MODEL_VERSION
from app.core.result import ExtractionResult, ExtractionResultSet
from app.core.schema import schema_loader
from app.database import get_db
from app.models.db_models import (
    BaselineRunRow,
    ExtractionResultRow,
    TestGroundTruthRow,
    TestSetDocumentRow,
)
from app.extraction.spatial_tier3 import SpatialTier3Extractor
from app.ocr.pipeline import process_document as _pipeline_process

logger = logging.getLogger(__name__)

GROUND_TRUTH_PATH = Path(__file__).parent.parent.parent / "config" / "ground_truth.yaml"
UPLOADS_ROOT = Path(__file__).parent.parent.parent.parent / "uploads"


# ---------------------------------------------------------------------------
# Comparison helpers
# ---------------------------------------------------------------------------

def _normalize_for_compare(value: Optional[str]) -> Optional[str]:
    """Normalize a field value before accuracy comparison."""
    if value is None:
        return None
    v = str(value).strip().lower()
    # Remove trailing zeros from decimals: 263000.0 → 263000
    import re
    v = re.sub(r"\.0+$", "", v)
    # Strip $ and ,
    v = re.sub(r"[$,]", "", v)
    # Collapse whitespace
    v = re.sub(r"\s+", " ", v)
    return v


def _values_match(extracted: Optional[str], correct: Optional[str]) -> bool:
    if extracted is None and correct is None:
        return True
    if extracted is None or correct is None:
        return False
    return _normalize_for_compare(extracted) == _normalize_for_compare(correct)


# ---------------------------------------------------------------------------
# Result containers
# ---------------------------------------------------------------------------

@dataclass
class FieldResult:
    field_name: str
    correct_value: Optional[str]
    extracted_value: Optional[str]
    is_correct: bool
    is_absent: bool           # ground truth says field is absent from document
    confidence: float

@dataclass
class DocumentResult:
    document_id: str
    batch_name: str
    amc_id: str
    document_type: str
    field_results: List[FieldResult] = field(default_factory=list)

    @property
    def accuracy(self) -> float:
        testable = [f for f in self.field_results if not f.is_absent]
        if not testable:
            return 0.0
        return sum(1 for f in testable if f.is_correct) / len(testable)

    @property
    def fields_correct(self) -> int:
        return sum(1 for f in self.field_results if f.is_correct and not f.is_absent)

    @property
    def fields_tested(self) -> int:
        return sum(1 for f in self.field_results if not f.is_absent)

@dataclass
class BaselineReport:
    run_label: str
    document_results: List[DocumentResult] = field(default_factory=list)

    @property
    def overall_field_accuracy(self) -> float:
        total_tested = sum(d.fields_tested for d in self.document_results)
        total_correct = sum(d.fields_correct for d in self.document_results)
        return total_correct / total_tested if total_tested else 0.0

    @property
    def overall_document_accuracy(self) -> float:
        if not self.document_results:
            return 0.0
        return sum(d.accuracy for d in self.document_results) / len(self.document_results)

    def field_accuracy_by_name(self) -> Dict[str, Tuple[int, int]]:
        """Return {field_name: (correct_count, total_tested)} across all documents."""
        counts: Dict[str, List[int]] = {}
        for dr in self.document_results:
            for fr in dr.field_results:
                if fr.is_absent:
                    continue
                if fr.field_name not in counts:
                    counts[fr.field_name] = [0, 0]
                counts[fr.field_name][1] += 1
                if fr.is_correct:
                    counts[fr.field_name][0] += 1
        return {k: tuple(v) for k, v in counts.items()}

    def amc_accuracy(self) -> Dict[str, float]:
        by_amc: Dict[str, List[int]] = {}
        for dr in self.document_results:
            amc = dr.amc_id
            if amc not in by_amc:
                by_amc[amc] = [0, 0]
            by_amc[amc][0] += dr.fields_correct
            by_amc[amc][1] += dr.fields_tested
        return {
            amc: (c[0] / c[1] if c[1] else 0.0)
            for amc, c in by_amc.items()
        }


# ---------------------------------------------------------------------------
# Seed test set
# ---------------------------------------------------------------------------

def seed_test_set(force: bool = False) -> int:
    """
    Load config/ground_truth.yaml into adaptive_test_set and adaptive_test_ground_truth.
    Returns number of documents seeded.
    """
    gt = yaml.safe_load(GROUND_TRUTH_PATH.read_text())
    seeded = 0

    with get_db() as session:
        for batch_name, batch_data in gt.get("batches", {}).items():
            amc_id = batch_data.get("amc_id", "unknown")

            for doc_subtype, doc_data in batch_data.get("documents", {}).items():
                doc_id = f"{batch_name}:{doc_subtype}"
                doc_path = UPLOADS_ROOT / doc_data["path"]

                # Skip if already seeded
                existing = session.query(TestSetDocumentRow).filter_by(
                    document_id=doc_id
                ).first()
                if existing and not force:
                    logger.debug("Test doc already seeded: %s", doc_id)
                    continue
                if existing and force:
                    session.delete(existing)
                    session.flush()

                # Count pages
                total_pages = 0
                if doc_path.exists():
                    try:
                        import fitz
                        d = fitz.open(str(doc_path))
                        total_pages = len(d)
                        d.close()
                    except Exception:
                        pass

                doc_row = TestSetDocumentRow(
                    document_id=doc_id,
                    batch_name=batch_name,
                    amc_id=amc_id,
                    document_type=doc_data["document_type"],
                    document_path=str(doc_path),
                    total_pages=total_pages,
                    is_scanned=doc_data.get("is_scanned", False),
                )
                session.add(doc_row)
                session.flush()

                # Seed ground truth fields
                for fname, fdata in doc_data.get("fields", {}).items():
                    gt_row = TestGroundTruthRow(
                        test_document_id=doc_row.id,
                        field_name=fname,
                        correct_value=fdata.get("value"),
                        is_absent=fdata.get("absent", False),
                        verified_by=fdata.get("verified_by", "manual"),
                        notes=fdata.get("notes"),
                    )
                    session.add(gt_row)

                seeded += 1

    logger.info("Test set seeding complete: %d documents", seeded)
    return seeded


# ---------------------------------------------------------------------------
# Run baseline
# ---------------------------------------------------------------------------

def run_baseline(label: str = "Week1-Day4") -> BaselineReport:
    """
    Run extraction on all test set documents, compare to ground truth,
    store in adaptive_baseline_runs and adaptive_extraction_results.
    """
    report = BaselineReport(run_label=label)

    # Use full three-tier pipeline (spatial → embeddings → LLM) for honest measurement.
    # P-8: 'Define measurement before building the feature.'
    # The measurement must reflect the actual system output, not a subset tier.
    use_full_pipeline = True

    with get_db() as session:
        test_docs = session.query(TestSetDocumentRow).all()
        if not test_docs:
            raise RuntimeError("Test set is empty — run seed_test_set() first")

        for test_doc in test_docs:
            doc_path = Path(test_doc.document_path)
            if not doc_path.exists():
                logger.warning("Test document not found: %s", doc_path)
                continue

            # Load and extract using the full pipeline
            try:
                if use_full_pipeline:
                    pipeline_result = _pipeline_process(
                        doc_path,
                        document_id=test_doc.document_id,
                        document_type_override=test_doc.document_type,
                        persist_metadata=False,
                        use_llm=False,        # skip LLM in baseline — it times out on M1
                        use_embeddings=True,  # include embedding tier
                    )
                    result_set = pipeline_result.extraction_result_set
                else:
                    result_set = SpatialTier3Extractor().extract(doc_path, test_doc.document_type)
            except Exception as exc:
                logger.error("Extraction failed for %s: %s", test_doc.document_id, exc)
                continue

            # Persist extraction results
            run_id = f"{label}:{test_doc.document_id}"
            for canonical, result in result_set:
                row = ExtractionResultRow(
                    document_id=test_doc.document_id,
                    amc_id=test_doc.amc_id,
                    document_type=test_doc.document_type,
                    document_path=test_doc.document_path,
                    total_pages=result_set.total_pages,
                    field_name=canonical,
                    field_value=result.value,
                    raw_source_text=result.raw_source_text,
                    extraction_method=result.extraction_method,
                    confidence_score=result.effective_confidence,
                    source_page=result.source_page,
                    char_start=result.char_start,
                    normalization_steps=json.dumps(result.normalization_applied or []),
                    sanity_check_failed=result.sanity_check_failed,
                    sanity_check_reason=result.sanity_check_reason,
                    hallucination_flag=result.hallucination_flag,
                    cross_validated=result.cross_validated,
                    cross_validated_source=result.cross_validated_source,
                    routing=result.routing,
                    model_version=MODEL_VERSION,
                    run_id=run_id,
                )
                session.add(row)

            # Compare against ground truth
            doc_result = DocumentResult(
                document_id=test_doc.document_id,
                batch_name=test_doc.batch_name,
                amc_id=test_doc.amc_id,
                document_type=test_doc.document_type,
            )

            gt_entries = session.query(TestGroundTruthRow).filter_by(
                test_document_id=test_doc.id
            ).all()

            for gt in gt_entries:
                extracted_result = result_set.get(gt.field_name)
                extracted_value = extracted_result.value if extracted_result else None

                if gt.is_absent:
                    # Field should be absent — correct if not extracted
                    is_correct = extracted_value is None
                else:
                    is_correct = _values_match(extracted_value, gt.correct_value)

                doc_result.field_results.append(FieldResult(
                    field_name=gt.field_name,
                    correct_value=gt.correct_value,
                    extracted_value=extracted_value,
                    is_correct=is_correct,
                    is_absent=gt.is_absent,
                    confidence=extracted_result.effective_confidence if extracted_result else 0.0,
                ))

            report.document_results.append(doc_result)
            session.flush()

        # Store baseline run summary
        field_acc = report.field_accuracy_by_name()
        amc_acc = report.amc_accuracy()
        doc_acc = {d.document_id: round(d.accuracy, 3) for d in report.document_results}

        total_tested = sum(d.fields_tested for d in report.document_results)
        total_correct = sum(d.fields_correct for d in report.document_results)

        baseline_row = BaselineRunRow(
            run_label=label,
            schema_version=schema_loader.schema_version,
            model_version=MODEL_VERSION,
            total_documents=len(report.document_results),
            total_fields_tested=total_tested,
            fields_correct=total_correct,
            fields_not_found=sum(
                1 for d in report.document_results
                for f in d.field_results
                if not f.is_absent and f.extracted_value is None
            ),
            fields_wrong=total_tested - total_correct - sum(
                1 for d in report.document_results
                for f in d.field_results
                if not f.is_absent and f.extracted_value is None
            ),
            field_accuracy_json=json.dumps(
                {k: {"correct": v[0], "total": v[1], "rate": round(v[0]/v[1], 3) if v[1] else 0}
                 for k, v in field_acc.items()}
            ),
            amc_accuracy_json=json.dumps(
                {k: round(v, 3) for k, v in amc_acc.items()}
            ),
            doc_accuracy_json=json.dumps(doc_acc),
            field_accuracy_rate=round(report.overall_field_accuracy, 3),
            document_accuracy_rate=round(report.overall_document_accuracy, 3),
        )
        session.add(baseline_row)

    logger.info(
        "Baseline run '%s': %.1f%% field accuracy, %.1f%% document accuracy across %d documents",
        label,
        report.overall_field_accuracy * 100,
        report.overall_document_accuracy * 100,
        len(report.document_results),
    )
    return report


def print_baseline_report(report: BaselineReport) -> None:
    """Print a human-readable baseline report to stdout."""
    print("\n" + "=" * 70)
    print(f"BASELINE MEASUREMENT — {report.run_label}")
    print(f"Schema version: {schema_loader.schema_version}")
    print(f"Model version:  {MODEL_VERSION}")
    print("=" * 70)
    print(f"\nOverall field accuracy:    {report.overall_field_accuracy * 100:.1f}%")
    print(f"Overall document accuracy: {report.overall_document_accuracy * 100:.1f}%")
    print(f"Documents measured:        {len(report.document_results)}")

    print("\n--- By Document ---")
    for dr in report.document_results:
        print(f"\n  {dr.document_id}")
        print(f"  Type: {dr.document_type}  AMC: {dr.amc_id}")
        print(f"  Accuracy: {dr.accuracy * 100:.1f}%  ({dr.fields_correct}/{dr.fields_tested} fields correct)")
        for fr in dr.field_results:
            if fr.is_absent:
                status = "ABSENT" if fr.is_correct else "WRONG(found)"
            elif fr.is_correct:
                status = "✓"
            elif fr.extracted_value is None:
                status = "NOT_FOUND"
            else:
                status = f"WRONG → got '{fr.extracted_value}'"
            print(f"    {fr.field_name:<35} {status}")

    print("\n--- Field Accuracy ---")
    fa = report.field_accuracy_by_name()
    for fname, (correct, total) in sorted(fa.items(), key=lambda x: -x[1][0]/x[1][1] if x[1][1] else 0):
        rate = correct / total if total else 0
        bar = "█" * int(rate * 20)
        print(f"  {fname:<35} {bar:<20} {correct}/{total} ({rate*100:.0f}%)")

    print("\n--- AMC Accuracy ---")
    for amc, rate in report.amc_accuracy().items():
        print(f"  {amc:<40} {rate * 100:.1f}%")

    print("\n" + "=" * 70)
