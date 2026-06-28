#!/usr/bin/env python3
"""
Quick smoke-test for the MISMO 2.6 GSE XML extractor.
Runs against all three test XML files and prints a summary.

Usage:
    cd ocr-service
    python scripts/test_xml_extractor.py
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pathlib import Path

TEST_DIR = Path(__file__).parent.parent.parent / "uploads" / "xml1 copy"

XML_FILES = [
    TEST_DIR / "1" / "ESCA-0019573.xml",
    TEST_DIR / "2" / "5807 Fox Hunt Trl.xml",
    TEST_DIR / "3" / "MAGU96793.XML",
]

KEY_FIELDS = [
    # ── Report / Assignment ──────────────────────────────────────────────────
    "form_type",
    "assignment_type",
    "signature_date",
    "appraiser_file_id",

    # ── Appraiser ────────────────────────────────────────────────────────────
    "appraiser_name",
    "appraiser_company_name",
    "appraiser_license_number",
    "appraiser_license_type",
    "appraiser_license_state",
    "appraiser_license_expiration",

    # ── Lender / Borrower ────────────────────────────────────────────────────
    "lender_name",
    "borrower_name",
    "co_borrower_name",

    # ── Subject Property ─────────────────────────────────────────────────────
    "property_address",
    "city",
    "state",
    "zip_code",
    "county",
    "occupancy_type",
    "property_rights",
    "apn",
    "census_tract",

    # ── Structure / Improvements ─────────────────────────────────────────────
    "gla",
    "total_rooms",
    "bedrooms",
    "bathrooms",
    "stories",
    "year_built",
    "effective_age",
    "design_style",

    # ── Site ─────────────────────────────────────────────────────────────────
    "site_area",
    "zoning",
    "zoning_description",
    "flood_zone_indicator",
    "flood_zone_id",

    # ── Neighborhood ─────────────────────────────────────────────────────────
    "neighborhood_name",
    "location_type",
    "built_up",
    "growth",
    "property_values_trend",
    "demand_supply",
    "marketing_time_typical",
    "price_low",
    "price_high",
    "price_predominant",
    "age_low_years",
    "age_high_years",
    "age_predominant_years",

    # ── Contract (from appraisal XML SALES_CONTRACT section) ─────────────────
    "contract_price",
    "contract_date",
    "contract_analyzed",
    "concessions_indicator",
    "concessions_amount",
    "listed_past_year",
    "listing_history",

    # ── Value Conclusions ────────────────────────────────────────────────────
    "appraised_value",
    "effective_date",
    "final_value_sca",
    "cost_approach_value",
    "income_approach_value",
    "site_value",
    "total_improvements_cost",
    "total_depreciation",
    "physical_depreciation",
    "functional_depreciation",
    "gross_rent_multiplier",

    # ── Subject Prior Sale ───────────────────────────────────────────────────
    "prior_sale_date",
    "prior_sale_price",

    # ── Subject Grid Column (from seq=0 comparable) ──────────────────────────
    "subject_grid_rooms",
    "subject_grid_bedrooms",
    "subject_grid_bathrooms",
    "subject_grid_gla",
    "subject_grid_condition_rating",
    "subject_grid_quality_rating",
    "subject_grid_location_rating",
    "subject_grid_site_area",
    "subject_grid_view",
    "subject_grid_design_style",
    "subject_grid_age",
    "subject_grid_garage",

    # ── Comp 1 (full set) ────────────────────────────────────────────────────
    "comp_1_address",
    "comp_1_proximity",
    "comp_1_sale_price",
    "comp_1_data_source",
    "comp_1_verification_source",
    "comp_1_adjusted_sale_price",
    "comp_1_net_adjustment",
    "comp_1_net_adj_pct",
    "comp_1_gross_adj_pct",
    "comp_1_rooms",
    "comp_1_bedrooms",
    "comp_1_bathrooms",
    "comp_1_sale_date",
    "comp_1_location_rating",
    "comp_1_site_area",
    "comp_1_view",
    "comp_1_design_style",
    "comp_1_quality_rating",
    "comp_1_age",
    "comp_1_condition_rating",
    "comp_1_condition_adj",
    "comp_1_gla",
    "comp_1_gla_adj",
    "comp_1_garage",
    "comp_1_financing_adj",
    "comp_1_concessions",
    "comp_1_prior_sale_date",
    "comp_1_prior_sale_price",

    # ── Comp 2 (abbreviated) ─────────────────────────────────────────────────
    "comp_2_address",
    "comp_2_sale_price",
    "comp_2_adjusted_sale_price",
    "comp_2_net_adj_pct",
    "comp_2_gross_adj_pct",
    "comp_2_condition_rating",
    "comp_2_gla",

    # ── Comp 3 (abbreviated) ─────────────────────────────────────────────────
    "comp_3_address",
    "comp_3_sale_price",
    "comp_3_adjusted_sale_price",
    "comp_3_net_adj_pct",
    "comp_3_gross_adj_pct",
    "comp_3_condition_rating",
    "comp_3_gla",

    # ── Photos / Forms Presence ──────────────────────────────────────────────
    "photo_front",
    "photo_rear",
    "photo_street",
    "comp_1_photo_present",
    "comp_2_photo_present",
    "comp_3_photo_present",
    "sketch_present",
    "location_map_present",

    # ── Addendum ─────────────────────────────────────────────────────────────
    "addendum_text",
]


def main():
    from app.extraction.xml_extractor import extract_xml

    for xml_path in XML_FILES:
        if not xml_path.exists():
            print(f"\n[SKIP] {xml_path.name} not found")
            continue

        print(f"\n{'='*60}")
        print(f"FILE: {xml_path.name}")
        print('='*60)

        rs = extract_xml(xml_path)
        found = {name: r for name, r in rs if r.found}
        total = len(found)
        print(f"Total fields extracted: {total}")

        print("\n--- Key field values ---")
        for field in KEY_FIELDS:
            r = found.get(field)
            val = r.value if r else "<NOT FOUND>"
            if val and len(val) > 80:
                val = val[:77] + "..."
            status = "✓" if r else "✗"
            print(f"  {status} {field:<35} {val}")

        # Show comp count
        comps = sorted(set(
            int(k.split("_")[1])
            for k in found
            if k.startswith("comp_") and k[5].isdigit() and "_sale_price" in k
        ))
        print(f"\n  Comparable indices with sale_price: {comps}")

        # Show all fields starting with "subject_grid"
        sg = {k: v.value for k, v in found.items() if k.startswith("subject_grid")}
        if sg:
            print(f"\n  Subject grid fields: {sg}")


if __name__ == "__main__":
    main()
