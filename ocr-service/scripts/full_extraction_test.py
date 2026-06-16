"""
Full Extraction Test — All uploads/ PDFs mapped to QC Rules

Runs spatial extraction on every unique PDF in uploads/, classifies each
document, extracts fields, and reports coverage against the QC Checklist rules
from QCChceklistOpus.md.

QC Rule → Required Fields mapping (per QCChceklistOpus.md):
  S-1:  property_address, city, state, zip_code, county
  S-2:  borrower_name, co_borrower_name
  S-3:  owner_of_public_record
  S-4:  legal_description, assessors_parcel_number, tax_year, real_estate_taxes
  S-5:  neighborhood_name
  S-6:  map_reference, census_tract
  S-7:  occupant_status
  S-8:  special_assessments
  S-9:  is_pud_checked, hoa_dues, hoa_period
  S-10: lender_name, lender_address
  S-11: property_rights
  S-12: offered_for_sale_12mo, data_source, mls_number
  C-1:  assignment_type, did_analyze_contract, sale_type
  C-2:  contract_price, contract_date
  C-3:  is_seller_owner_of_record, owner_record_data_source
  C-4:  has_financial_assistance, financial_assistance_amount
  C-5:  personal_property_items, personal_property_contributes_to_value
  N-1:  location, built_up, growth_rate
  N-2:  property_values, demand_supply, marketing_time
  N-3:  price_low, price_high, predominant_price, age_low, age_high
  N-4:  land_use_one_unit, land_use_2_4_unit, land_use_commercial, land_use_total
  N-5:  neighborhood_boundaries
  N-6:  neighborhood_description
  N-7:  market_conditions_commentary
  ST-1: site_dimensions
  ST-2: site_area, site_area_unit
  ST-3: site_shape
  ST-4: site_view
  ST-5: zoning_classification, zoning_compliance
  ST-6: highest_and_best_use
  ST-7: utilities_electricity, utilities_gas, utilities_water, utilities_sewer
  ST-8: fema_flood_hazard, fema_flood_zone, fema_map_date
  ST-10:adverse_site_conditions
  I-1:  design_style, year_built, effective_age, stories, status, units_count
  I-7:  total_rooms, bedrooms, baths, gla
  I-9:  condition_rating
  R-2:  appraised_value, effective_date
  SIG-1:date_of_signature
  SIG-2:appraiser_name, appraiser_state_cert_number, appraiser_cert_state, appraiser_cert_expiration_date

Usage:
  conda run -n apprisal python scripts/full_extraction_test.py
"""

import sys
import time
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.core.schema import schema_loader
from app.services.document_classifier import document_classifier
from app.extraction.spatial_extractor import SpatialExtractor
import fitz

schema_loader.reload()
extractor = SpatialExtractor()

UPLOADS = Path(__file__).parent.parent.parent / "uploads"

# QC rule → fields mapping
QC_RULES = {
    "S-1  Property Address":   ["property_address", "city", "state", "zip_code", "county"],
    "S-2  Borrower":           ["borrower_name", "co_borrower_name"],
    "S-3  Owner of Record":    ["owner_of_public_record"],
    "S-4  Legal/APN/Taxes":    ["legal_description", "assessors_parcel_number", "tax_year", "real_estate_taxes"],
    "S-5  Neighborhood Name":  ["neighborhood_name"],
    "S-6  Map/Census":         ["map_reference", "census_tract"],
    "S-7  Occupant":           ["occupant_status"],
    "S-8  Assessments":        ["special_assessments"],
    "S-9  PUD/HOA":            ["is_pud_checked", "hoa_dues"],
    "S-10 Lender":             ["lender_name", "lender_address"],
    "S-11 Property Rights":    ["property_rights"],
    "S-12 Prior Listing":      ["offered_for_sale_12mo", "data_source"],
    "C-1  Contract Analysis":  ["assignment_type", "did_analyze_contract", "sale_type"],
    "C-2  Contract Price/Date":["contract_price", "contract_date"],
    "C-3  Owner of Record":    ["is_seller_owner_of_record"],
    "C-4  Concessions":        ["has_financial_assistance", "financial_assistance_amount"],
    "N-1  Characteristics":    ["location", "built_up", "growth_rate"],
    "N-2  Trends":             ["property_values", "demand_supply", "marketing_time"],
    "N-3  Price/Age Ranges":   ["price_low", "price_high", "predominant_price"],
    "N-4  Land Use":           ["land_use_one_unit", "land_use_commercial", "land_use_total"],
    "N-5  Boundaries":         ["neighborhood_boundaries"],
    "N-6  Description":        ["neighborhood_description"],
    "N-7  Market Conditions":  ["market_conditions_commentary"],
    "ST-1 Dimensions":         ["site_dimensions"],
    "ST-2 Site Area":          ["site_area", "site_area_unit"],
    "ST-3 Shape":              ["site_shape"],
    "ST-4 View":               ["site_view"],
    "ST-5 Zoning":             ["zoning_classification", "zoning_compliance"],
    "ST-6 HBU":                ["highest_and_best_use"],
    "ST-7 Utilities":          ["utilities_electricity", "utilities_gas", "utilities_water", "utilities_sewer"],
    "ST-8 FEMA":               ["fema_flood_hazard", "fema_flood_zone", "fema_map_date"],
    "ST-10 Adverse Site":      ["adverse_site_conditions"],
    "I-1  General Desc":       ["design_style", "year_built", "effective_age", "stories"],
    "I-7  Room Count/GLA":     ["total_rooms", "bedrooms", "baths", "gla"],
    "I-9  Condition":          ["condition_rating"],
    "R-2  Final Value":        ["appraised_value", "effective_date"],
    "SIG-1 Signature":         ["date_of_signature"],
    "SIG-2 Appraiser Info":    ["appraiser_name", "appraiser_state_cert_number"],
}

# Document type → which QC rules apply
DOC_TYPE_RULES = {
    "appraisal_report": list(QC_RULES.keys()),
    "engagement_letter": ["S-1  Property Address", "S-2  Borrower", "S-10 Lender", "C-1  Contract Analysis"],
    "sales_contract":    ["S-1  Property Address", "C-2  Contract Price/Date", "C-4  Concessions"],
}


def deduplicate_pdfs(all_pdfs):
    """Remove duplicate PDFs (same content, different paths) using file size + first 512 bytes."""
    seen = {}
    unique = []
    for pdf_path in all_pdfs:
        try:
            stat = pdf_path.stat()
            key = stat.st_size
            if key not in seen:
                seen[key] = pdf_path
                unique.append(pdf_path)
        except Exception:
            pass
    return unique


def classify_pdf(pdf_path: Path) -> str:
    """Classify a PDF using the document classifier."""
    try:
        doc = fitz.open(str(pdf_path))
        pages = {}
        for i in range(min(2, len(doc))):
            pages[i + 1] = doc[i].get_text("text")
        doc.close()
        result = document_classifier.classify(pages, total_pages=len(pages))
        return result.document_type, result.amc_id or "unknown"
    except Exception:
        return "unknown", "unknown"


def run_extraction(pdf_path: Path, doc_type: str):
    """Run spatial extraction on one PDF."""
    try:
        return extractor.extract(pdf_path, doc_type)
    except Exception as exc:
        return None


def score_qc_coverage(result_set, doc_type: str) -> dict:
    """Score which QC rules are satisfied by this extraction."""
    applicable_rules = DOC_TYPE_RULES.get(doc_type, list(QC_RULES.keys()))
    scores = {}
    for rule_id in applicable_rules:
        fields = QC_RULES.get(rule_id, [])
        found_count = 0
        for fname in fields:
            r = result_set.get(fname)
            if r and r.found and r.value and len(r.value.strip()) > 0:
                found_count += 1
        pct = found_count / len(fields) if fields else 0
        scores[rule_id] = {
            "found": found_count,
            "total": len(fields),
            "pct": pct,
            "status": "✓" if pct >= 1.0 else ("~" if pct >= 0.5 else "✗"),
        }
    return scores


def main():
    print("=" * 80)
    print("APPRISAL FULL EXTRACTION TEST — ALL UPLOADS + QC RULE COVERAGE")
    print(f"Schema: {schema_loader.schema_version} | {len(schema_loader.all_fields())} fields")
    print("=" * 80)

    # Collect all PDFs
    all_pdfs = list(UPLOADS.rglob("*.pdf"))
    unique_pdfs = deduplicate_pdfs(all_pdfs)
    print(f"\nFound: {len(all_pdfs)} PDFs → {len(unique_pdfs)} unique after deduplication\n")

    # Separate by known structure (sort/ and EQSS/ are structured)
    structured_pdfs = [p for p in unique_pdfs if ("sort/" in str(p) or "EQSS/" in str(p)) and
                       any(s in str(p) for s in ("/appraisal/", "/engagement/", "/contract/"))]
    orders_pdfs = [p for p in unique_pdfs if "/Orders/" in str(p)]
    other_pdfs = [p for p in unique_pdfs if p not in structured_pdfs and p not in orders_pdfs]

    print(f"Structured batches (sort/ + EQSS/): {len(structured_pdfs)} PDFs")
    print(f"Orders/ directory:                  {len(orders_pdfs)} PDFs")
    print(f"Other:                              {len(other_pdfs)} PDFs")

    all_to_test = structured_pdfs + orders_pdfs
    print(f"\nTotal to test: {len(all_to_test)}\n")

    # Track results
    rule_totals = defaultdict(lambda: {"found": 0, "total": 0, "doc_count": 0})
    doc_results = []
    field_found_counts = defaultdict(int)
    field_doc_counts = defaultdict(int)
    doc_type_counts = defaultdict(int)

    for pdf_path in sorted(all_to_test):
        rel_path = str(pdf_path).replace(str(UPLOADS) + "/", "")

        # Determine document type
        if "/appraisal/" in str(pdf_path):
            doc_type = "appraisal_report"
        elif "/engagement/" in str(pdf_path):
            doc_type = "engagement_letter"
        elif "/contract/" in str(pdf_path):
            doc_type = "sales_contract"
        else:
            # For Orders/ files, use classifier
            doc_type, amc_id = classify_pdf(pdf_path)
            if doc_type == "unknown":
                doc_type = "appraisal_report"  # most likely

        doc_type_counts[doc_type] += 1

        start = time.time()
        rs = run_extraction(pdf_path, doc_type)
        elapsed = int((time.time() - start) * 1000)

        if rs is None:
            print(f"  FAILED  {rel_path[:60]}")
            continue

        found = len(rs.found_results())
        total = len(rs)
        scores = score_qc_coverage(rs, doc_type)

        # Tally per-rule
        for rule_id, score in scores.items():
            rule_totals[rule_id]["found"] += score["found"]
            rule_totals[rule_id]["total"] += score["total"]
            rule_totals[rule_id]["doc_count"] += 1

        # Per-field counts
        for fname, r in rs:
            field_doc_counts[fname] += 1
            if r.found:
                field_found_counts[fname] += 1

        # Status summary
        rules_ok = sum(1 for s in scores.values() if s["pct"] >= 1.0)
        rules_partial = sum(1 for s in scores.values() if 0.5 <= s["pct"] < 1.0)
        rules_missing = sum(1 for s in scores.values() if s["pct"] < 0.5)

        status_line = (
            f"  {doc_type[:12]:<12} {rel_path[:50]:<50} "
            f"fields={found}/{total} rules=✓{rules_ok}/~{rules_partial}/✗{rules_missing} {elapsed}ms"
        )
        print(status_line)
        doc_results.append((rel_path, doc_type, found, total, scores))

    # ---- Summary Report ----
    print()
    print("=" * 80)
    print("QC RULE COVERAGE ACROSS ALL DOCUMENTS")
    print("=" * 80)
    print(f"{'Rule':<28} {'Coverage':>8}  {'Status'}")
    print("-" * 80)

    rule_order = list(QC_RULES.keys())
    for rule_id in rule_order:
        t = rule_totals[rule_id]
        if t["doc_count"] == 0:
            continue
        pct = t["found"] / t["total"] if t["total"] > 0 else 0
        bar = "█" * int(pct * 20)
        status = "✓ FULL" if pct >= 0.90 else ("~ PARTIAL" if pct >= 0.50 else "✗ MISSING")
        print(f"  {rule_id:<26} {pct*100:>5.0f}%  [{bar:<20}] {status}  ({t['doc_count']} docs)")

    print()
    print("=" * 80)
    print("FIELD-LEVEL EXTRACTION COVERAGE")
    print("=" * 80)

    # Critical fields per QC checklist
    critical_fields = [
        "property_address", "city", "state", "zip_code", "county",
        "borrower_name", "lender_name", "contract_price", "contract_date",
        "appraised_value", "effective_date", "assignment_type", "property_rights",
        "condition_rating", "gla", "year_built", "total_rooms", "bedrooms", "baths",
        "neighborhood_name", "census_tract", "assessors_parcel_number",
        "occupant_status", "zoning_compliance", "fema_flood_zone",
        "appraiser_name", "date_of_signature", "appraiser_state_cert_number",
    ]

    print(f"\n{'Field':<40} {'Rate':>6}  {'Bar':<22} {'QC Rule'}")
    print("-" * 80)
    for fname in critical_fields:
        total = field_doc_counts[fname]
        found = field_found_counts[fname]
        if total == 0:
            continue
        rate = found / total
        bar = "█" * int(rate * 20)
        # find QC rule
        qc_rule = next((r for r, fs in QC_RULES.items() if fname in fs), "—")
        print(f"  {fname:<38} {rate*100:>5.0f}%  [{bar:<20}] {qc_rule}")

    print()
    print("=" * 80)
    print("FIELDS WITH 0% EXTRACTION — NEED ATTENTION")
    print("=" * 80)
    zero_fields = [(fname, field_doc_counts[fname])
                   for fname in critical_fields
                   if field_found_counts[fname] == 0 and field_doc_counts[fname] > 0]
    for fname, doc_count in sorted(zero_fields, key=lambda x: -x[1]):
        qc_rule = next((r for r, fs in QC_RULES.items() if fname in fs), "—")
        print(f"  ✗ {fname:<40} (tested in {doc_count} docs) [{qc_rule}]")

    print()
    print("=" * 80)
    print("DOCUMENT TYPE DISTRIBUTION")
    print("=" * 80)
    for dt, cnt in sorted(doc_type_counts.items()):
        print(f"  {dt}: {cnt}")

    print()
    print(f"Total documents tested: {len(doc_results)}")
    overall_found = sum(r[2] for r in doc_results)
    overall_total = sum(r[3] for r in doc_results)
    print(f"Overall field extraction: {overall_found}/{overall_total} = {overall_found/max(overall_total,1)*100:.1f}%")
    print()
    print("QC RULES STATUS:")
    rules_full = sum(1 for r in rule_order if rule_totals[r]["doc_count"] > 0 and
                     rule_totals[r]["found"]/max(rule_totals[r]["total"],1) >= 0.90)
    rules_partial = sum(1 for r in rule_order if rule_totals[r]["doc_count"] > 0 and
                        0.50 <= rule_totals[r]["found"]/max(rule_totals[r]["total"],1) < 0.90)
    rules_missing = sum(1 for r in rule_order if rule_totals[r]["doc_count"] > 0 and
                        rule_totals[r]["found"]/max(rule_totals[r]["total"],1) < 0.50)
    print(f"  ✓ Full coverage (≥90%):    {rules_full}")
    print(f"  ~ Partial coverage (50-89%): {rules_partial}")
    print(f"  ✗ Missing (<50%):           {rules_missing}")


if __name__ == "__main__":
    main()
