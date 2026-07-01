"""
MISMO 2.6 GSE XML extractor — the primary structured data source for appraisal QC.

Why this exists: the appraisal XML is the machine-generated output of the appraiser's
software (ClickFORMS, TOTAL, etc.) and carries the same facts as the PDF but without
OCR ambiguity.  Every value extracted here is verbatim from the file; confidence is
set at 0.97 (effectively certain — only a software bug or a field the appraiser left
genuinely blank would make a value wrong).

Output: an ExtractionResultSet whose fields slot directly into the existing QCContext /
rule engine via the same canonical field names the PDF extractors use.  Where both
sources have a value, the XML result has higher confidence so it wins in DocView.

Canonical field names produced (partial list):
  Report / metadata:
    form_type, assignment_type, signature_date, appraiser_file_id
  Appraiser:
    appraiser_name, appraiser_company_name, appraiser_license_number,
    appraiser_license_type, appraiser_license_state, appraiser_license_expiration
  Lender / borrower:
    lender_name, borrower_name, co_borrower_name
  Subject property:
    property_address, city, state, zip_code, county, occupancy_type,
    property_rights, apn, census_tract
    gla, total_rooms, bedrooms, bathrooms, stories, year_built, effective_age,
    design_style
  Site / neighborhood:
    site_area, zoning, zoning_description, flood_zone_indicator, flood_zone_id
    neighborhood_name, location_type, built_up, growth, property_values_trend,
    demand_supply, marketing_time_typical,
    price_low, price_high, price_predominant,
    age_low_years, age_high_years, age_predominant_years
  Contract (from appraisal-reported contract):
    contract_price, contract_date, contract_analyzed,
    concessions_indicator, concessions_amount
  Value conclusions:
    appraised_value, effective_date,
    final_value_sca, cost_approach_value, income_approach_value,
    site_value, total_depreciation, gross_rent_multiplier
  Prior sale (subject):
    prior_sale_date, prior_sale_price
  Comp grid (comp_1_ … comp_9_):
    comp_N_address, comp_N_proximity, comp_N_sale_price, comp_N_data_source,
    comp_N_verification_source, comp_N_adjusted_sale_price, comp_N_net_adjustment,
    comp_N_net_adj_pct, comp_N_gross_adj_pct, comp_N_rooms, comp_N_bedrooms,
    comp_N_bathrooms, comp_N_prior_sale_date, comp_N_prior_sale_price,
    comp_N_sale_date, comp_N_financing_adj, comp_N_location_rating,
    comp_N_site_area, comp_N_view, comp_N_design_style, comp_N_quality_rating,
    comp_N_age, comp_N_condition_rating, comp_N_condition_adj, comp_N_gla,
    comp_N_gla_adj, comp_N_garage
  Subject grid column (seq=0):
    subject_grid_location_rating, subject_grid_site_area, subject_grid_view,
    subject_grid_design_style, subject_grid_quality_rating, subject_grid_age,
    subject_grid_condition_rating, subject_grid_gla, subject_grid_garage,
    subject_grid_rooms, subject_grid_bedrooms, subject_grid_bathrooms
  Photos / forms presence:
    photo_front, photo_rear, photo_street,
    sketch_present, location_map_present,
    comp_1_photo_present … comp_9_photo_present
  Addendum:
    addendum_text
"""

from __future__ import annotations

import logging
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

_METHOD = "xml_parser"
_CONF   = 0.97       # XML is machine-generated — virtually certain

# Map MISMO AppraisalFormType → canonical form_type string
_FORM_TYPE_MAP = {
    "FNM1004":   "1004",
    "FNM1073":   "1073",
    "FNM1025":   "1025",
    "FNM1004C":  "1004c",
    "FNM1004D":  "1004d",
    "FNM2055":   "2055",
    "VA26-1802a": "va",
}


def extract_xml(xml_path) -> "ExtractionResultSet":
    """Parse a MISMO 2.6 GSE appraisal XML and return an ExtractionResultSet.

    Never raises — parsing failures are logged and an empty result set is returned
    so the calling overlay degrades gracefully (P-6).
    """
    from app.core.result import ExtractionResult, ExtractionResultSet

    rs = ExtractionResultSet(
        document_path=str(xml_path),
        document_type="appraisal_report",
        total_pages=0,
        ocr_method=_METHOD,
    )

    try:
        tree = ET.parse(str(xml_path))
        root = tree.getroot()
    except ET.ParseError as exc:
        logger.error("XML parse error for %s: %s", xml_path, exc)
        rs.finalize()
        return rs
    except OSError as exc:
        logger.error("Cannot open XML file %s: %s", xml_path, exc)
        rs.finalize()
        return rs

    fields: dict[str, str] = {}

    _extract_report(root, fields)
    _extract_parties(root, fields)
    _extract_property(root, fields)
    _extract_valuation_methods(root, fields)
    _extract_valuation(root, fields)
    _extract_comp_grid(root, fields)
    _extract_forms(root, fields)

    for canonical, value in fields.items():
        if value is None:
            continue
        v = str(value).strip()
        if not v:
            continue
        rs.add(ExtractionResult(
            canonical_name=canonical,
            document_type="appraisal_report",
            value=v,
            raw_source_text=v,
            extraction_method=_METHOD,
            confidence=_CONF,
            source_page=0,
            normalization_applied=[_METHOD],
        ))

    rs.finalize()
    logger.info(
        "XML extractor: %d fields extracted from %s",
        len(rs.found_results()), Path(xml_path).name,
    )
    return rs


# ---------------------------------------------------------------------------
# Section extractors
# ---------------------------------------------------------------------------

def _a(el: Optional[ET.Element], attr: str, default: str = "") -> str:
    """Safe attribute getter — returns empty string when element or attr absent."""
    if el is None:
        return default
    return el.get(attr, default) or default


def _extract_report(root: ET.Element, f: dict) -> None:
    report = root.find("REPORT")
    if report is None:
        return
    raw_form = report.get("AppraisalFormType", "")
    f["form_type"] = _FORM_TYPE_MAP.get(raw_form, raw_form.lower().replace("fnm", ""))
    f["appraiser_file_id"] = report.get("AppraiserFileIdentifier", "")
    f["assignment_type"] = report.get("AppraisalPurposeType", "")
    f["signature_date"] = report.get("AppraiserReportSignedDate", "")


def _extract_parties(root: ET.Element, f: dict) -> None:
    parties = root.find("PARTIES")
    if parties is None:
        return

    appraiser = parties.find("APPRAISER")
    if appraiser is not None:
        f["appraiser_name"] = _a(appraiser, "_Name")
        f["appraiser_company_name"] = _a(appraiser, "_CompanyName")
        lic = appraiser.find("APPRAISER_LICENSE")
        if lic is not None:
            f["appraiser_license_number"] = _a(lic, "_Identifier")
            f["appraiser_license_type"] = _a(lic, "_Type")
            f["appraiser_license_state"] = _a(lic, "_State")
            f["appraiser_license_expiration"] = _a(lic, "_ExpirationDate")
            f["appraiser_cert_expiration_date"] = f["appraiser_license_expiration"]

    lender = parties.find("LENDER")
    if lender is not None:
        f["lender_name"] = _a(lender, "_UnparsedName")

    borrower = parties.find("BORROWER")
    if borrower is not None:
        raw_name = _a(borrower, "_UnparsedName")
        # Keep the full name for matching (e.g. "SCOTT & KELLY CARPER").
        # Split only to populate co_borrower_name separately; do NOT truncate
        # borrower_name to the first token — S-2 needs the full string to match
        # engagement-letter values like "Kelly Carper; Scott Carper".
        f["borrower_name"] = raw_name
        if "&" in raw_name:
            parts = [p.strip() for p in raw_name.split("&", 1)]
            f["co_borrower_name"] = parts[1]


def _extract_property(root: ET.Element, f: dict) -> None:
    prop = root.find("PROPERTY")
    if prop is None:
        return

    f["property_address"] = _a(prop, "_StreetAddress")
    f["city"]             = _a(prop, "_City")
    f["state"]            = _a(prop, "_State")
    f["zip_code"]         = _a(prop, "_PostalCode")
    f["county"]           = _a(prop, "_County")
    f["occupancy_type"]   = _a(prop, "_CurrentOccupancyType")
    f["occupant_status"]  = f["occupancy_type"]               # S-7 uses occupant_status
    f["property_rights"]  = _a(prop, "_RightsType")

    ident = prop.find("_IDENTIFICATION")
    if ident is not None:
        f["apn"]                    = _a(ident, "AssessorsParcelIdentifier")
        f["assessors_parcel_number"] = f["apn"]               # S-4b uses assessors_parcel_number
        f["census_tract"]           = _a(ident, "CensusTractIdentifier")

    struct = prop.find("STRUCTURE")
    if struct is not None:
        f["gla"]          = _a(struct, "GrossLivingAreaSquareFeetCount")
        f["total_rooms"]  = _a(struct, "TotalRoomCount")
        f["bedrooms"]     = _a(struct, "TotalBedroomCount")
        f["bathrooms"]    = _a(struct, "TotalBathroomCount")
        f["stories"]      = _a(struct, "StoriesCount")
        f["year_built"]   = _a(struct, "PropertyStructureBuiltYear")
        f["design_style"] = _a(struct, "_DesignDescription")
        sa = struct.find("STRUCTURE_ANALYSIS")
        if sa is not None:
            f["effective_age"] = _a(sa, "EffectiveAgeYearsCount")

    site = prop.find("SITE")
    if site is not None:
        f["site_area"]          = _a(site, "_AreaDescription")
        f["zoning"]             = _a(site, "_ZoningClassificationIdentifier")
        f["zoning_description"] = _a(site, "_ZoningClassificationDescription")
        fz = site.find("FLOOD_ZONE")
        if fz is not None:
            f["flood_zone_indicator"] = _a(fz, "SpecialFloodHazardAreaIndicator")
            f["flood_zone_id"]        = _a(fz, "NFIPFloodZoneIdentifier")

    nbhd = prop.find("NEIGHBORHOOD")
    if nbhd is not None:
        f["neighborhood_name"]        = _a(nbhd, "_Name")
        f["location_type"]            = _a(nbhd, "PropertyNeighborhoodLocationType")
        f["location"]                 = f["location_type"]            # N-1 _CHARACTERISTICS
        f["built_up"]                 = _a(nbhd, "_BuiltupRangeType")
        f["growth"]                   = _a(nbhd, "_GrowthPaceType")
        f["growth_rate"]              = f["growth"]                   # N-1 _CHARACTERISTICS
        f["property_values_trend"]    = _a(nbhd, "_PropertyValueTrendType")
        f["property_values"]          = f["property_values_trend"]    # N-2 _TRENDS
        f["demand_supply"]            = _a(nbhd, "_DemandSupplyType")
        f["marketing_time_typical"]   = _a(nbhd, "_TypicalMarketingTimeDurationType")
        f["marketing_time"]           = f["marketing_time_typical"]   # N-2 _TRENDS
        housing = nbhd.find("_HOUSING")
        if housing is not None:
            f["price_low"]            = _a(housing, "_LowPriceAmount")
            f["price_high"]           = _a(housing, "_HighPriceAmount")
            f["price_predominant"]    = _a(housing, "_PredominantPriceAmount")
            f["predominant_price"]    = f["price_predominant"]        # N-3, SCA-BR
            f["age_low_years"]        = _a(housing, "_NewestYearsCount")
            f["age_low"]              = f["age_low_years"]            # N-3 _range_check
            f["age_high_years"]       = _a(housing, "_OldestYearsCount")
            f["age_high"]             = f["age_high_years"]           # N-3 _range_check
            f["age_predominant_years"]  = _a(housing, "_PredominantAgeYearsCount")
            f["predominant_age"]        = f["age_predominant_years"]  # N-3 _range_check

    sc = prop.find("SALES_CONTRACT")
    if sc is not None:
        f["contract_price"]      = _a(sc, "_Amount")
        f["contract_date"]       = _a(sc, "_Date")
        f["contract_analyzed"]   = _a(sc, "_ReviewedIndicator")
        f["concessions_indicator"] = _a(sc, "SalesConcessionIndicator")
        f["concessions_amount"]  = _a(sc, "SalesConcessionAmount")
        f["contract_comment"]    = _a(sc, "_ReviewComment")

    lh = prop.find("LISTING_HISTORY")
    if lh is not None:
        f["listed_past_year"]    = _a(lh, "ListedWithinPreviousYearIndicator")
        f["listing_history"]     = _a(lh, "ListedWithinPreviousYearDescription")


def _extract_valuation_methods(root: ET.Element, f: dict) -> None:
    vm = root.find("VALUATION_METHODS")
    if vm is None:
        return

    sca = vm.find("SALES_COMPARISON")
    if sca is not None:
        f["final_value_sca"]      = _a(sca, "ValueIndicatedBySalesComparisonApproachAmount")
        f["sca_comment"]          = _a(sca, "_Comment")
        f["prior_sale_analysis"]  = _a(sca, "_CurrentSalesAgreementAnalysisComment")

    ca = vm.find("COST_ANALYSIS")
    if ca is not None:
        f["cost_approach_value"]       = _a(ca, "ValueIndicatedByCostApproachAmount")
        f["site_value"]                = _a(ca, "SiteEstimatedValueAmount")
        f["total_improvements_cost"]   = _a(ca, "NewImprovementTotalCostAmount")
        f["cost_new_improvements"]     = f["total_improvements_cost"]  # CA-3, reconciliation
        # "As-is" Value of Site Improvements — 3rd addend in cost approach total.
        # URAR: Indicated = Site Value + Depreciated Cost + Site Improvements.
        # Missing this term causes CA-ARITH to false-fail any report that uses the line.
        f["site_other_improvements"]   = _a(ca, "SiteOtherImprovementsAsIsAmount")
        dep = ca.find("DEPRECIATION")
        if dep is not None:
            f["total_depreciation"]       = _a(dep, "_TotalAmount")
            f["physical_depreciation"]    = _a(dep, "_PhysicalAmount")
            f["functional_depreciation"]  = _a(dep, "_FunctionalAmount")

    ia = vm.find("INCOME_ANALYSIS")
    if ia is not None:
        f["income_approach_value"]  = _a(ia, "ValueIndicatedByIncomeApproachAmount")
        f["gross_rent_multiplier"]  = _a(ia, "GrossRentMultiplierFactor")


def _extract_valuation(root: ET.Element, f: dict) -> None:
    val = root.find("VALUATION")
    if val is None:
        return
    f["appraised_value"] = _a(val, "PropertyAppraisedValueAmount")
    f["effective_date"]  = _a(val, "AppraisalEffectiveDate")


def _extract_comp_grid(root: ET.Element, f: dict) -> None:
    """Extract subject grid row (seq=0) and comparable rows (seq=1..N)."""
    comps = root.findall(".//COMPARABLE_SALE")
    comp_index = 0  # 1-based counter for real comps

    for comp in comps:
        seq = comp.get("PropertySequenceIdentifier", "")
        is_subject = (seq == "0")

        adj_by_type: dict[str, dict[str, str]] = {}
        for adj in comp.findall("SALE_PRICE_ADJUSTMENT"):
            t = adj.get("_Type", "")
            if t:
                adj_by_type[t] = dict(adj.attrib)

        loc = comp.find("LOCATION")
        rooms_el = comp.find("ROOM_ADJUSTMENT")
        prior = comp.find("PRIOR_SALES")

        if is_subject:
            # Subject comparison column — provides the subject's grid row values
            pfx = "subject_grid"
            if loc is not None:
                f[f"{pfx}_proximity"] = _a(loc, "ProximityToSubjectDescription")
            if rooms_el is not None:
                f[f"{pfx}_rooms"]     = _a(rooms_el, "TotalRoomCount")
                f[f"{pfx}_bedrooms"]  = _a(rooms_el, "TotalBedroomCount")
                f[f"{pfx}_bathrooms"] = _a(rooms_el, "TotalBathroomCount")
            _map_adj(adj_by_type, pfx, f)
            if prior is not None:
                f["prior_sale_date"]  = _a(prior, "PropertySalesDate")
                f["prior_sale_price"] = _a(prior, "PropertySalesAmount")
        else:
            comp_index += 1
            pfx = f"comp_{comp_index}"
            if loc is not None:
                addr = _a(loc, "PropertyStreetAddress")
                city = _a(loc, "PropertyCity")
                state = _a(loc, "PropertyState")
                f[f"{pfx}_address"]   = f"{addr}, {city}, {state}".strip(", ")
                f[f"{pfx}_proximity"] = _a(loc, "ProximityToSubjectDescription")
            f[f"{pfx}_sale_price"]          = comp.get("PropertySalesAmount", "")
            f[f"{pfx}_data_source"]         = comp.get("DataSourceDescription", "")
            f[f"{pfx}_verification_source"] = comp.get("DataSourceVerificationDescription", "")
            f[f"{pfx}_adjusted_sale_price"] = comp.get("AdjustedSalesPriceAmount", "")
            f[f"{pfx}_net_adjustment"]      = comp.get("SalePriceTotalAdjustmentAmount", "")
            f[f"{pfx}_net_adj_pct"]         = comp.get("SalePriceTotalAdjustmentNetPercent", "")
            f[f"{pfx}_gross_adj_pct"]       = comp.get("SalesPriceTotalAdjustmentGrossPercent", "")
            if rooms_el is not None:
                f[f"{pfx}_rooms"]    = _a(rooms_el, "TotalRoomCount")
                f[f"{pfx}_bedrooms"] = _a(rooms_el, "TotalBedroomCount")
                f[f"{pfx}_bathrooms"]= _a(rooms_el, "TotalBathroomCount")
            if prior is not None:
                f[f"{pfx}_prior_sale_date"]  = _a(prior, "PropertySalesDate")
                f[f"{pfx}_prior_sale_price"] = _a(prior, "PropertySalesAmount")
            _map_adj(adj_by_type, pfx, f)


def _map_adj(adj: dict[str, dict], pfx: str, f: dict) -> None:
    """Map SALE_PRICE_ADJUSTMENT types to canonical field names."""
    _get = lambda t, k: adj.get(t, {}).get(k, "")

    def _set(key: str, t: str, attr: str) -> None:
        v = _get(t, attr)
        if v:
            f[key] = v

    _set(f"{pfx}_sale_date",         "DateOfSale",         "_Description")
    _set(f"{pfx}_financing_adj",     "FinancingConcessions","_Amount")
    _set(f"{pfx}_location_rating",   "Location",           "_Description")
    _set(f"{pfx}_site_area",         "SiteArea",           "_Description")
    _set(f"{pfx}_site_size",         "SiteArea",           "_Description")  # SCA-11 uses site_size
    _set(f"{pfx}_view",              "View",               "_Description")
    _set(f"{pfx}_design_style",      "DesignStyle",        "_Description")
    _set(f"{pfx}_design",            "DesignStyle",        "_Description")  # SCA-13 uses design
    _set(f"{pfx}_quality_rating",    "Quality",            "_Description")
    _set(f"{pfx}_age",               "Age",                "_Description")
    _set(f"{pfx}_condition_rating",  "Condition",          "_Description")
    _set(f"{pfx}_condition_adj",     "Condition",          "_Amount")
    _set(f"{pfx}_gla",               "GrossLivingArea",    "_Description")
    _set(f"{pfx}_gla_adj",           "GrossLivingArea",    "_Amount")
    _set(f"{pfx}_garage",            "CarStorage",         "_Description")
    _set(f"{pfx}_garage_carport",    "CarStorage",         "_Description")  # SCA-21 uses garage_carport
    _set(f"{pfx}_concessions",       "SalesConcessions",   "_Description")


def _extract_forms(root: ET.Element, f: dict) -> None:
    """Extract photo/sketch/addendum presence from FORM elements."""
    addendum_parts: list[str] = []
    comp_photo_found: set[int] = set()

    for form in root.findall(".//FORM"):
        content_type = form.get("AppraisalReportContentType", "")
        addendum_text = form.get("AppraisalAddendumText", "")
        if addendum_text.strip():
            addendum_parts.append(addendum_text.strip())

        for img in form.findall("IMAGE"):
            ident = img.get("_Identifier", "")
            has   = img.get("_Name", "NoImage") == "HasImage"
            if ident == "SubjectFront":
                f["photo_front"]  = "True" if has else "False"
            elif ident == "SubjectRear":
                f["photo_rear"]   = "True" if has else "False"
            elif ident == "SubjectStreet":
                f["photo_street"] = "True" if has else "False"
            elif ident.startswith("ComparablePhoto"):
                try:
                    n = int(ident[len("ComparablePhoto"):])
                    if has:
                        comp_photo_found.add(n)
                    f[f"comp_{n}_photo_present"] = "True" if has else "False"
                except ValueError:
                    pass

        if content_type == "Sketch":
            has_sketch = any(
                img.get("_Name") == "HasImage" for img in form.findall("IMAGE")
            )
            f["sketch_present"] = "True" if has_sketch else "False"
        elif content_type == "LocationMap":
            has_map = any(
                img.get("_Name") == "HasImage" for img in form.findall("IMAGE")
            )
            f["location_map_present"] = "True" if has_map else "False"

    if addendum_parts:
        f["addendum_text"] = "\n\n".join(addendum_parts)
