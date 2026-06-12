"""Shared builders for rule unit tests (DRY across the rule test modules).

`rs()` builds a synthetic ExtractionResultSet; `statuses()`/`by_template()`
flatten a rule's single-or-list output for assertions.
"""

from app.core.result import ExtractionResult, ExtractionResultSet


def rs(doc_type="appraisal_report", **fields) -> ExtractionResultSet:
    out = ExtractionResultSet(document_path="x", document_type=doc_type)
    for name, value in fields.items():
        out.add(ExtractionResult(canonical_name=name, document_type=doc_type,
                                 value=str(value), extraction_method="test",
                                 confidence=0.9, source_page=1))
    out.finalize()
    return out


def as_list(results):
    return results if isinstance(results, list) else [results]


def statuses(results):
    return [r.status for r in as_list(results)]


def by_template(results, template_id):
    return [r for r in as_list(results) if r.template_id == template_id]
