"""
Appraisal-Only Extraction Test

Tests extraction on every appraisal report found in uploads/.
Produces per-document field tables and aggregate QC rule coverage.

Focus: appraisal_report type only. Engagement letters and contracts excluded.

Usage:
    cd ocr-service
    conda run -n apprisal python scripts/appraisal_extraction_test.py
"""

import sys
import time
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import fitz
from app.core.schema import schema_loader
from app.services.document_classifier import document_classifier
from app.extraction.spatial_tier3 import SpatialTier3Extractor

schema_loader.reload()
extractor = SpatialTier3Extractor()
UPLOADS = Path(__file__).parent.parent.parent / "uploads"

# ── QC Rule → field groups (per QCChceklistOpus.md) ──────────────────────────
QC_RULES = {
    "S-1  Address":         ["property_address", "city", "state", "zip_code", "county"],
    "S-2  Borrower":        ["borrower_name"],
    "S-3  Owner of Record": ["owner_of_public_record"],
    "S-4  APN/Taxes":       ["assessors_parcel_number", "tax_year", "real_estate_taxes"],
    "S-5  Neighborhood":    ["neighborhood_name"],
    "S-6  Map/Census":      ["map_reference", "census_tract"],
    "S-7  Occupant":        ["occupant_status"],
    "S-8  Assessments":     ["special_assessments"],
    "S-9  PUD/HOA":         ["is_pud_checked", "hoa_dues"],
    "S-10 Lender":          ["lender_name", "lender_address"],
    "S-11 Prop Rights":     ["property_rights"],
    "S-12 Prior Listing":   ["offered_for_sale_12mo", "data_source"],
    "C-1  Contract Anal":   ["assignment_type", "did_analyze_contract", "sale_type"],
    "C-2  Price/Date":      ["contract_price", "contract_date"],
    "C-3  Seller Owner":    ["is_seller_owner_of_record"],
    "C-4  Concessions":     ["has_financial_assistance", "financial_assistance_amount"],
    "N-1  Char (loc/blt)":  ["location", "built_up", "growth_rate"],
    "N-2  Trends":          ["property_values", "demand_supply", "marketing_time"],
    "N-3  Price Ranges":    ["price_low", "price_high", "predominant_price"],
    "N-4  Land Use":        ["land_use_one_unit", "land_use_commercial", "land_use_total"],
    "N-5  Boundaries":      ["neighborhood_boundaries"],
    "N-6  Description":     ["neighborhood_description"],
    "N-7  Market Cond":     ["market_conditions_commentary"],
    "ST-1 Dimensions":      ["site_dimensions"],
    "ST-2 Site Area":       ["site_area", "site_area_unit"],
    "ST-3 Shape":           ["site_shape"],
    "ST-4 View":            ["site_view"],
    "ST-5 Zoning":          ["zoning_classification", "zoning_compliance"],
    "ST-6 HBU":             ["highest_and_best_use"],
    "ST-7 Utilities":       ["utilities_electricity", "utilities_gas",
                             "utilities_water", "utilities_sewer"],
    "ST-8 FEMA":            ["fema_flood_hazard", "fema_flood_zone", "fema_map_date"],
    "ST-10 Adverse":        ["adverse_site_conditions"],
    "I-1  Gen Desc":        ["design_style", "year_built", "effective_age", "stories"],
    "I-7  Rooms/GLA":       ["total_rooms", "bedrooms", "baths", "gla"],
    "I-9  Condition":       ["condition_rating"],
    "R-2  Final Value":     ["appraised_value", "effective_date"],
    "SIG-1 Signature":      ["date_of_signature"],
    "SIG-2 Appraiser":      ["appraiser_name", "appraiser_state_cert_number"],
}

ALL_TRACKED = [f for fields in QC_RULES.values() for f in fields]


def collect_appraisals():
    """Collect all unique appraisal PDFs: structured + Orders/ (classified)."""
    seen_sizes = set()
    appraisals = []

    # Structured: /appraisal/ subfolders (definitely appraisal reports)
    for pdf in sorted(UPLOADS.rglob("*.pdf")):
        if "/appraisal/" not in str(pdf):
            continue
        sz = pdf.stat().st_size
        if sz in seen_sizes:
            continue
        seen_sizes.add(sz)
        appraisals.append(pdf)

    # Orders/: classify and take only appraisal_report
    for pdf in sorted((UPLOADS / "Orders").rglob("*.pdf")):
        sz = pdf.stat().st_size
        if sz in seen_sizes:
            continue
        try:
            doc = fitz.open(str(pdf))
            pages = {i+1: doc[i].get_text("text") for i in range(min(2, len(doc)))}
            doc.close()
            result = document_classifier.classify(pages, total_pages=len(pages))
            if result.document_type == "appraisal_report":
                seen_sizes.add(sz)
                appraisals.append(pdf)
        except Exception:
            pass

    return appraisals


def format_val(v):
    if v is None:
        return "—"
    v = str(v)
    return v[:35] + "…" if len(v) > 35 else v


def run_test():
    appraisals = collect_appraisals()
    print("=" * 100)
    print(f"APPRAISAL EXTRACTION TEST — {len(appraisals)} unique appraisal reports")
    print(f"Schema v{schema_loader.schema_version} | {len(schema_loader.all_fields())} fields")
    print("=" * 100)

    # Per-rule aggregates
    rule_totals = defaultdict(lambda: {"found": 0, "total": 0, "doc_count": 0})
    field_found = defaultdict(int)
    field_tested = defaultdict(int)
    per_doc_scores = []

    for pdf in appraisals:
        rel = str(pdf).replace(str(UPLOADS) + "/", "")
        print(f"\n{'─'*100}")
        print(f"  {rel}")
        print(f"{'─'*100}")

        start = time.time()
        try:
            rs = extractor.extract(pdf, "appraisal_report")
        except Exception as exc:
            print(f"  ERROR: {exc}")
            continue
        elapsed = int((time.time() - start) * 1000)

        found_count = len(rs.found_results())
        print(f"  Fields found: {found_count}/{len(rs)} | Time: {elapsed}ms")
        print()

        # QC Rule breakdown for this document
        doc_qc_score = {"total_rules": 0, "full": 0, "partial": 0, "missing": 0}
        print(f"  {'QC Rule':<18} {'Coverage':>8}  {'Fields found'}")
        print(f"  {'─'*18} {'─'*8}  {'─'*50}")

        for rule_id, fields in QC_RULES.items():
            found_in_rule = []
            missing_in_rule = []
            for fname in fields:
                r = rs.get(fname)
                if r and r.found and r.value:
                    found_in_rule.append(f"{fname}={format_val(r.value)}")
                else:
                    missing_in_rule.append(fname)
                field_tested[fname] += 1
                if r and r.found and r.value:
                    field_found[fname] += 1

            pct = len(found_in_rule) / len(fields) if fields else 0
            status = "✓" if pct >= 1.0 else ("~" if pct >= 0.5 else "✗")

            # Show what was found (green) and what's missing
            found_str = " | ".join(found_in_rule)[:55]
            miss_str = ",".join(missing_in_rule)

            print(f"  {rule_id:<18} {status} {pct*100:>3.0f}%  {found_str}")
            if missing_in_rule and pct < 1.0:
                print(f"  {'':18}       missing: {miss_str}")

            # Aggregate
            rule_totals[rule_id]["found"] += len(found_in_rule)
            rule_totals[rule_id]["total"] += len(fields)
            rule_totals[rule_id]["doc_count"] += 1
            doc_qc_score["total_rules"] += 1
            if pct >= 1.0:
                doc_qc_score["full"] += 1
            elif pct >= 0.5:
                doc_qc_score["partial"] += 1
            else:
                doc_qc_score["missing"] += 1

        per_doc_scores.append((rel, doc_qc_score, found_count))
        pct_rules = doc_qc_score["full"] / doc_qc_score["total_rules"] * 100
        print(f"\n  QC summary: ✓{doc_qc_score['full']} full | ~{doc_qc_score['partial']} partial | "
              f"✗{doc_qc_score['missing']} missing ({pct_rules:.0f}% rules fully covered)")

    # ── AGGREGATE REPORT ────────────────────────────────────────────────────
    print("\n" + "=" * 100)
    print("AGGREGATE QC RULE COVERAGE — ALL APPRAISAL REPORTS")
    print("=" * 100)
    print(f"\n  {'QC Rule':<20} {'Coverage':>8}  {'Bar':<22} {'Status'}")
    print(f"  {'─'*20} {'─'*8}  {'─'*22} {'─'*15}")

    rules_full = rules_partial = rules_missing = 0
    for rule_id in QC_RULES:
        t = rule_totals[rule_id]
        if t["doc_count"] == 0:
            continue
        pct = t["found"] / t["total"] if t["total"] > 0 else 0
        bar = "█" * int(pct * 20)
        if pct >= 0.90:
            status = "✓ FULL"
            rules_full += 1
        elif pct >= 0.50:
            status = "~ PARTIAL"
            rules_partial += 1
        else:
            status = "✗ MISSING"
            rules_missing += 1
        print(f"  {rule_id:<20} {pct*100:>6.1f}%  [{bar:<20}] {status}  ({t['doc_count']} docs)")

    print("\n" + "=" * 100)
    print("FIELD-LEVEL EXTRACTION RATES (appraisal reports only)")
    print("=" * 100)
    print(f"\n  {'Field':<40} {'Rate':>6}  {'Bar':<22} {'Extraction Method Available'}")
    print(f"  {'─'*40} {'─'*6}  {'─'*22} {'─'*28}")

    # Group by QC rule
    shown = set()
    for rule_id, fields in QC_RULES.items():
        rule_printed = False
        for fname in fields:
            if fname in shown:
                continue
            shown.add(fname)
            total = field_tested[fname]
            found = field_found[fname]
            if total == 0:
                continue
            rate = found / total
            bar = "█" * int(rate * 20)
            # Determine extraction capability
            fd = schema_loader.get_field(fname)
            if fd:
                dtype = fd.data_type
                if dtype in ("boolean",):
                    method = "checkbox_detector"
                elif dtype in ("enum",):
                    method = "checkbox_detector / spatial"
                elif dtype in ("uad_condition", "uad_quality"):
                    method = "UAD code pattern"
                elif dtype in ("currency",):
                    method = "spatial currency"
                elif dtype in ("date",):
                    method = "spatial date"
                elif dtype in ("string",):
                    method = "spatial label"
                else:
                    method = f"spatial ({dtype})"
            else:
                method = "schema missing"

            if not rule_printed:
                print(f"\n  [{rule_id}]")
                rule_printed = True
            pct_str = f"{rate*100:.0f}%"
            print(f"    {fname:<38} {pct_str:>6}  [{bar:<20}] {method}")

    print("\n" + "=" * 100)
    print("DOCUMENT SUMMARY")
    print("=" * 100)
    print(f"\n  {'Document':<55} {'Rules✓':>6} {'Rules~':>6} {'Rules✗':>6} {'Fields'}")
    print(f"  {'─'*55} {'─'*6} {'─'*6} {'─'*6} {'─'*8}")
    for rel, score, found_count in per_doc_scores:
        name = rel[-55:]
        print(f"  {name:<55} {score['full']:>6} {score['partial']:>6} {score['missing']:>6} {found_count:>6}/253")

    print(f"\n  Total appraisals tested: {len(per_doc_scores)}")
    print(f"\n  QC Rules overall:")
    print(f"    ✓ Full coverage (≥90%):    {rules_full}")
    print(f"    ~ Partial (50–89%):        {rules_partial}")
    print(f"    ✗ Missing (<50%):          {rules_missing}")
    print()


if __name__ == "__main__":
    run_test()
