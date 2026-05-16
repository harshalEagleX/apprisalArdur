"""
Full Appraisal Extraction Test — Layered Architecture

Runs the complete layered extraction (L0+L1+L2+L3+L4 in parallel threads)
on every unique appraisal PDF found in uploads/.

Speed: PDFs themselves are processed with all layers running in parallel.
       Multiple PDFs processed concurrently via outer thread pool.

Usage:
    cd ocr-service
    conda run -n apprisal python scripts/run_full_appraisal_test.py
"""

import sys
import time
import hashlib
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import fitz
from app.core.schema import schema_loader
from app.services.document_classifier import document_classifier
from app.extraction.layers.orchestrator import run_full_extraction

schema_loader.reload()
UPLOADS = Path(__file__).parent.parent.parent / "uploads"

# QC Rules → field coverage mapping (per QCChceklistOpus.md)
QC_RULES = {
    "S-1  Address":       ["property_address","city","state","zip_code","county"],
    "S-2  Borrower":      ["borrower_name"],
    "S-3  Owner Rec":     ["owner_of_public_record"],
    "S-4  APN/Taxes":     ["assessors_parcel_number","tax_year","real_estate_taxes"],
    "S-5  Nbhd Name":     ["neighborhood_name"],
    "S-6  Map/Census":    ["map_reference","census_tract"],
    "S-7  Occupant":      ["occupant_status"],
    "S-8  Assessments":   ["special_assessments"],
    "S-9  PUD/HOA":       ["is_pud_checked","hoa_dues"],
    "S-10 Lender":        ["lender_name","lender_address"],
    "S-11 Prop Rights":   ["property_rights"],
    "S-12 Prior List":    ["offered_for_sale_12mo","data_source"],
    "C-1  Assignment":    ["assignment_type","did_analyze_contract","sale_type"],
    "C-2  Price/Date":    ["contract_price","contract_date"],
    "C-3  Seller Own":    ["is_seller_owner_of_record"],
    "C-4  Concessions":   ["has_financial_assistance","financial_assistance_amount"],
    "N-1  Char":          ["location","built_up","growth_rate"],
    "N-2  Trends":        ["property_values","demand_supply","marketing_time"],
    "N-3  Price Range":   ["price_low","price_high","predominant_price"],
    "N-4  Land Use":      ["land_use_one_unit","land_use_2_4_unit","land_use_commercial"],
    "N-5  Boundaries":    ["neighborhood_boundaries"],
    "N-6  Description":   ["neighborhood_description"],
    "N-7  Market Cond":   ["market_conditions_commentary"],
    "ST-1 Dimensions":    ["site_dimensions"],
    "ST-2 Site Area":     ["site_area","site_area_unit"],
    "ST-3 Shape":         ["site_shape"],
    "ST-4 View":          ["site_view"],
    "ST-5 Zoning":        ["zoning_classification","zoning_compliance"],
    "ST-6 HBU":           ["highest_and_best_use"],
    "ST-7 Utilities":     ["utilities_electricity","utilities_gas",
                           "utilities_water","utilities_sewer"],
    "ST-8 FEMA":          ["fema_flood_hazard","fema_flood_zone","fema_map_date"],
    "I-1  Gen Desc":      ["design_style","year_built","effective_age","stories"],
    "I-7  Rooms/GLA":     ["total_rooms","bedrooms","baths","gla"],
    "I-9  Condition":     ["condition_rating"],
    "R-2  Final Value":   ["appraised_value","effective_date"],
    "SIG-1 Signature":    ["date_of_signature"],
    "SIG-2 Appraiser":    ["appraiser_name","appraiser_state_cert_number"],
}

CRITICAL = [
    "property_address","city","state","zip_code","county",
    "borrower_name","lender_name","contract_price","contract_date",
    "appraised_value","effective_date","assignment_type","property_rights",
    "condition_rating","gla","year_built","total_rooms","bedrooms","baths",
    "neighborhood_name","census_tract","assessors_parcel_number",
    "occupant_status","zoning_compliance","fema_flood_zone",
    "location","built_up","growth_rate","property_values",
    "price_low","price_high","predominant_price",
    "land_use_one_unit","highest_and_best_use","is_pud_checked",
]


def file_hash(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        h.update(f.read(65536))
    return h.hexdigest()[:16]


def collect_appraisals() -> list:
    """Collect all unique appraisal PDFs — structured folders + Orders/."""
    seen = set()
    result = []

    # Structured: /appraisal/ subfolders
    for pdf in sorted(UPLOADS.rglob("*.pdf")):
        if "/appraisal/" not in str(pdf):
            continue
        h = file_hash(pdf)
        if h not in seen:
            seen.add(h)
            result.append(pdf)

    # Orders/ — classify each PDF
    for pdf in sorted((UPLOADS / "Orders").rglob("*.pdf")):
        h = file_hash(pdf)
        if h in seen:
            continue
        try:
            doc = fitz.open(str(pdf))
            pages = {i+1: doc[i].get_text("text") for i in range(min(2, len(doc)))}
            doc.close()
            cls = document_classifier.classify(pages, total_pages=len(pages))
            if cls.document_type == "appraisal_report":
                seen.add(h)
                result.append(pdf)
        except Exception:
            pass

    return result


def process_one(pdf_path: Path) -> dict:
    """Extract one PDF and return summary dict."""
    rel = str(pdf_path).replace(str(UPLOADS) + "/", "")
    t0 = time.time()
    try:
        rs = run_full_extraction(pdf_path, "appraisal_report", use_paddle=False, use_llm=False)
        elapsed = int((time.time() - t0) * 1000)
        found = {name: r.value for name, r in rs if r.found and r.value}
        not_found = {name for name, r in rs if not r.found}

        # QC score
        qc = {}
        for rule, fields in QC_RULES.items():
            n_found = sum(1 for f in fields if f in found)
            qc[rule] = {"found": n_found, "total": len(fields),
                        "pct": n_found / len(fields) if fields else 0}

        return {
            "path": rel, "ok": True,
            "found": found, "not_found": not_found,
            "total_fields": len(rs), "found_count": len(found),
            "elapsed_ms": elapsed, "qc": qc,
        }
    except Exception as exc:
        return {"path": rel, "ok": False, "error": str(exc), "elapsed_ms": int((time.time()-t0)*1000)}


def main():
    appraisals = collect_appraisals()

    print("=" * 90)
    print(f"FULL APPRAISAL EXTRACTION TEST — LAYERED ARCHITECTURE")
    print(f"Schema v{schema_loader.schema_version} | {len(schema_loader.all_fields())} fields")
    print(f"Documents: {len(appraisals)} unique appraisal reports")
    print(f"Tools: pdfplumber + OpenCV visual + grid resolver + spatial + checkbox")
    print("=" * 90)
    print()

    # Process all PDFs with outer concurrency (max 3 simultaneous — each uses 5 inner threads)
    results = []
    total_start = time.time()

    with ThreadPoolExecutor(max_workers=3) as outer:
        futures = {outer.submit(process_one, pdf): pdf for pdf in appraisals}
        for future in as_completed(futures):
            r = future.result()
            results.append(r)
            if r["ok"]:
                qc_full = sum(1 for q in r["qc"].values() if q["pct"] >= 1.0)
                qc_partial = sum(1 for q in r["qc"].values() if 0.5 <= q["pct"] < 1.0)
                qc_missing = sum(1 for q in r["qc"].values() if q["pct"] < 0.5)
                name = r['path'][-60:]
                print(f"  ✓ {name:<60} "
                      f"fields={r['found_count']:>3}/253 "
                      f"rules=✓{qc_full}/~{qc_partial}/✗{qc_missing} "
                      f"{r['elapsed_ms']:>5}ms")
            else:
                print(f"  ✗ {r['path'][-60]:60} ERROR: {r.get('error','')[:40]}")

    total_elapsed = int((time.time() - total_start) * 1000)
    ok_results = [r for r in results if r["ok"]]

    # ── CRITICAL FIELDS ACROSS ALL DOCS ──────────────────────────────────────
    print()
    print("=" * 90)
    print("CRITICAL FIELD EXTRACTION RATES")
    print("=" * 90)
    print(f"\n  {'Field':<42} {'Rate':>5}  {'Bar':<20}  {'Status'}")
    print(f"  {'─'*42} {'─'*5}  {'─'*20}  {'─'*10}")

    for fname in CRITICAL:
        found_in = sum(1 for r in ok_results if fname in r.get("found", {}))
        total = len(ok_results)
        rate = found_in / total if total else 0
        bar = "█" * int(rate * 20)
        status = "✓ GOOD" if rate >= 0.85 else ("~ OK" if rate >= 0.60 else "✗ LOW")
        # Find a sample value
        sample = next((r["found"][fname][:25] for r in ok_results
                       if fname in r.get("found", {})), "—")
        print(f"  {fname:<42} {rate*100:>4.0f}%  [{bar:<20}] {status}  e.g. {repr(sample)}")

    # ── QC RULE AGGREGATE ─────────────────────────────────────────────────────
    print()
    print("=" * 90)
    print("QC RULE COVERAGE (aggregate across all appraisals)")
    print("=" * 90)
    print(f"\n  {'Rule':<20} {'Avg':>6}  {'Bar':<20}  {'Status'}")
    print(f"  {'─'*20} {'─'*6}  {'─'*20}  {'─'*10}")

    rules_full = rules_partial = rules_missing = 0
    for rule in QC_RULES:
        rule_pcts = [r["qc"][rule]["pct"] for r in ok_results if rule in r.get("qc", {})]
        avg = sum(rule_pcts) / len(rule_pcts) if rule_pcts else 0
        bar = "█" * int(avg * 20)
        if avg >= 0.90:
            status = "✓ FULL"; rules_full += 1
        elif avg >= 0.50:
            status = "~ PARTIAL"; rules_partial += 1
        else:
            status = "✗ MISSING"; rules_missing += 1
        print(f"  {rule:<20} {avg*100:>5.0f}%  [{bar:<20}]  {status}")

    # ── DOCUMENT SUMMARY ──────────────────────────────────────────────────────
    print()
    print("=" * 90)
    print("DOCUMENT SUMMARY")
    print("=" * 90)
    results_sorted = sorted(ok_results, key=lambda r: -r["found_count"])
    print(f"\n  {'Document':<55} Fields  Time")
    for r in results_sorted:
        name = r["path"][-55:]
        qf = sum(1 for q in r["qc"].values() if q["pct"] >= 1.0)
        print(f"  {name:<55} {r['found_count']:>3}/253  ✓{qf}  {r['elapsed_ms']:>5}ms")

    # ── FIELDS NEVER FOUND ────────────────────────────────────────────────────
    never_found = [f for f in CRITICAL
                   if all(f not in r.get("found", {}) for r in ok_results)]
    if never_found:
        print()
        print("=" * 90)
        print("FIELDS NEVER FOUND ACROSS ALL DOCUMENTS")
        print("=" * 90)
        for f in never_found:
            qc_rule = next((r for r, fs in QC_RULES.items() if f in fs), "—")
            print(f"  ✗ {f:<45} [{qc_rule}]")

    print()
    print("=" * 90)
    total_docs = len(ok_results)
    total_found = sum(r["found_count"] for r in ok_results)
    total_fields = sum(r["total_fields"] for r in ok_results)
    print(f"TOTAL: {total_docs} appraisals | "
          f"{total_found}/{total_fields} field extractions ({100*total_found//max(total_fields,1)}%) | "
          f"QC: ✓{rules_full}/~{rules_partial}/✗{rules_missing} | "
          f"{total_elapsed/1000:.1f}s total")
    print()

    # Camelot note
    print("─" * 90)
    print("NOTE — Why Camelot was NOT used:")
    print("  Camelot requires Ghostscript (system dependency) which is NOT installed.")
    print("  'ghostscript not found' — run 'brew install ghostscript' to enable it.")
    print("  Once installed, Camelot's lattice strategy would improve bordered-table")
    print("  extraction for comparable sale grids and MCA tables.")
    print("  pdfplumber covers the same use case without this system dependency.")
    print("─" * 90)


if __name__ == "__main__":
    main()
