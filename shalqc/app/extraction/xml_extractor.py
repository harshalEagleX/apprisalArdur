"""
extractor.xml (xml-1.0.0) — MISMO 2.6 GSE XML extractor.

SHALqc.md §3.2 step 1: "Parse ALL fields first. This is the spine." XML is the
machine-generated output of the appraiser's software (ClickFORMS, TOTAL, etc.)
and carries the same facts as the PDF but without OCR ambiguity — confidence is
fixed at 0.97 (P3: XML is authoritative). Ported from
ocr-service/app/extraction/xml_extractor.py (SHALqc.md §11 D1-2: "port your
existing schema — biggest reuse"), re-pointed at the ExtractedField contract.

XML has no page/bbox — every field lands at page=0/bbox=None here; the
back-locator that recovers a page/bbox for XML-sourced values is out of scope
for this build (SHALqc-CORE §3, not part of SHALqc.md §1-3).

Canonical field names produced (partial list) — see the section extractors
below for the full mapping: report/appraiser/lender/borrower metadata, subject
property, site, neighborhood, contract, value conclusions, prior sale, the
comp grid (subject_grid_* and comp_N_*), photo/sketch/map presence, addendum.
"""

from __future__ import annotations

import logging
import re
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Optional

from app.extraction.result import ExtractedField, ExtractedFieldSet, Source

__version__ = "xml-1.0.0"

logger = logging.getLogger(__name__)

_CONF = 0.97       # XML is machine-generated — virtually certain (P3)

_FORM_TYPE_MAP = {
    "FNM1004":   "1004",
    "FNM1073":   "1073",
    "FNM1025":   "1025",
    "FNM1004C":  "1004c",
    "FNM1004D":  "1004d",
    "FNM2055":   "2055",
    "VA26-1802a": "va",
}


def extract_xml(xml_path) -> ExtractedFieldSet:
    """Parse a MISMO 2.6 GSE appraisal XML and return an ExtractedFieldSet.

    Never raises — parsing failures are logged and an empty set is returned so
    the merge overlay degrades gracefully (missing XML ⇒ PDF-only fields).
    """
    fs = ExtractedFieldSet()

    try:
        tree = ET.parse(str(xml_path))
        root = tree.getroot()
    except ET.ParseError as exc:
        logger.error("XML parse error for %s: %s", xml_path, exc)
        return fs
    except OSError as exc:
        logger.error("Cannot open XML file %s: %s", xml_path, exc)
        return fs

    fields: dict[str, str] = {}

    _extract_report(root, fields)
    _extract_parties(root, fields)
    _extract_property(root, fields)
    _extract_market_inventory(root, fields)
    _extract_conditions(root, fields)
    _extract_valuation_methods(root, fields)
    _extract_valuation(root, fields)
    _extract_comp_grid(root, fields)
    _extract_forms(root, fields)
    _extract_subject_prior_sales(root, fields)

    for canonical, value in fields.items():
        if value is None:
            continue
        v = str(value).strip()
        if not v:
            continue
        fs.add(ExtractedField(
            canonical_name=canonical,
            value=v,
            raw_value=v,
            source=Source.XML,
            confidence=_CONF,
            page=0,
        ))

    logger.info("XML extractor: %d fields extracted from %s", len(fs.found_fields()), Path(xml_path).name)
    return fs


# ---------------------------------------------------------------------------
# Section extractors
# ---------------------------------------------------------------------------

def _a(el: Optional[ET.Element], attr: str, default: str = "") -> str:
    """Safe attribute getter — returns empty string when element or attr absent."""
    if el is None:
        return default
    return el.get(attr, default) or default


_APPLIANCE_FIELD = {
    "Refrigerator": "appliance_refrigerator",
    "RangeOven":    "appliance_range_oven",
    "Disposal":     "appliance_disposal",
    "Dishwasher":   "appliance_dishwasher",
    "Microwave":    "appliance_microwave",
    "WasherDryer":  "appliance_washer_dryer",
}


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
        _astreet = _a(appraiser, "_StreetAddress")
        if _astreet:
            _acity, _astate, _azip = (_a(appraiser, "_City"), _a(appraiser, "_State"),
                                      _a(appraiser, "_PostalCode"))
            _tail = " ".join(p for p in (_astate, _azip) if p)
            f["appraiser_company_address"] = ", ".join(
                p for p in (_astreet, _acity, _tail) if p)
        _cd = appraiser.find("CONTACT_DETAIL")
        if _cd is not None:
            for _cp in _cd.findall("CONTACT_POINT"):
                _ct, _cv = (_cp.get("_Type") or "").lower(), _cp.get("_Value")
                if not _cv:
                    continue
                if _ct == "phone":
                    f["appraiser_phone"] = _cv
                elif _ct == "email":
                    f.setdefault("appraiser_email", _cv)
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
        # lender/client address — MISMO carries it natively (layout-independent),
        # so prefer it over any PDF read. Use the unparsed address when present,
        # else assemble from the component attributes.
        _laddr = _a(lender, "AppraisalFormsUnparsedAddress")
        if not _laddr:
            _lstreet, _lcity = _a(lender, "_StreetAddress"), _a(lender, "_City")
            _lstate, _lzip = _a(lender, "_State"), _a(lender, "_PostalCode")
            _ltail = " ".join(p for p in (_lstate, _lzip) if p)
            _laddr = ", ".join(p for p in (_lstreet, _lcity.strip(), _ltail) if p)
        if _laddr.strip():
            f["lender_address"] = re.sub(r"\s+,", ",", _laddr).strip()

    borrower = parties.find("BORROWER")
    if borrower is not None:
        raw_name = _a(borrower, "_UnparsedName")
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
    f["occupant_status"]  = f["occupancy_type"]
    f["property_rights"]  = _a(prop, "_RightsType")
    _proj = _a(prop, "ProjectClassificationType")
    if _proj:
        f["is_pud"] = "Yes" if _proj.strip().lower() == "pud" else "No"
    # PUD fallback — the GSE_PUDIndicator (Y/N) carries it when the project type
    # attribute is absent (layout-independent).
    if "is_pud" not in f:
        for pt in root.iter():
            _pud = _a(pt, "GSE_PUDIndicator")
            if _pud:
                f["is_pud"] = "Yes" if _pud.strip().upper() == "Y" else "No"
                break

    ident = prop.find("_IDENTIFICATION")
    if ident is not None:
        f["apn"]                    = _a(ident, "AssessorsParcelIdentifier")
        f["assessors_parcel_number"] = f["apn"]
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
        f["baths"]        = f["bathrooms"]
        f["units_count"]  = _a(struct, "LivingUnitCount")
        f["dwelling_type"] = _a(struct, "AttachmentType")
        for feat in struct.findall("EXTERIOR_FEATURE"):
            if _a(feat, "_Type") == "Foundation" and _a(feat, "_Description"):
                f["foundation_type"] = _a(feat, "_Description")
                break
        if not f.get("foundation_type"):
            for found in struct.findall("FOUNDATION"):
                if _a(found, "_ExistsIndicator").upper() == "Y":
                    f["foundation_type"] = _a(found, "_Type")
                    break
        for keq in struct.findall("KITCHEN_EQUIPMENT"):
            _fld = _APPLIANCE_FIELD.get(_a(keq, "_Type"))
            if _fld and _a(keq, "_ExistsIndicator").upper() == "Y":
                f[_fld] = "Yes"
        sa = struct.find("STRUCTURE_ANALYSIS")
        if sa is not None:
            f["effective_age"] = _a(sa, "EffectiveAgeYearsCount")

    _ANALYSIS_FIELD = {"QualityAndAppearance": "condition_comments",
                       "PropertyCondition":    "improvements_comments"}
    for pa in prop.findall("PROPERTY_ANALYSIS"):
        key = _ANALYSIS_FIELD.get(_a(pa, "_Type"))
        comment = _a(pa, "_Comment")
        if key and comment:
            f[key] = comment

    site = prop.find("SITE")
    if site is not None:
        f["site_area"]          = _a(site, "_AreaDescription")
        f["site_dimensions"]    = _a(site, "_DimensionsDescription")
        f["zoning"]             = _a(site, "_ZoningClassificationIdentifier")
        f["zoning_description"] = _a(site, "_ZoningClassificationDescription")
        f["zoning_compliance"]  = _a(site, "_ZoningComplianceType")
        _hbu = _a(site, "HighestBestUseIndicator")
        if _hbu:
            f["highest_and_best_use"] = {"Y": "Yes", "N": "No"}.get(_hbu.strip().upper(), _hbu)
        for feat in site.findall("SITE_FEATURE"):
            t = _a(feat, "_Type")
            c = _a(feat, "_Comment")
            if not c:
                continue
            if t == "Shape":
                f["site_shape"] = c
            elif t == "View":
                f["site_view"] = c
                f.setdefault("subject_grid_view", c)
        _UTIL_FIELD = {"Electricity": "utilities_electricity", "Gas": "utilities_gas",
                       "Water": "utilities_water", "SanitarySewer": "utilities_sewer"}
        for util in site.findall("SITE_UTILITY"):
            key = _UTIL_FIELD.get(_a(util, "_Type"))
            if not key:
                continue
            if _a(util, "_PublicIndicator").upper() == "Y":
                f[key] = "Public"
            elif _a(util, "_NonPublicDescription"):
                f[key] = _a(util, "_NonPublicDescription")
            elif _a(util, "_NonPublicIndicator").upper() == "Y":
                f[key] = "Private"
            else:
                f[key] = "None"
        fz = site.find("FLOOD_ZONE")
        if fz is not None:
            f["flood_zone_indicator"] = _a(fz, "SpecialFloodHazardAreaIndicator")
            f["flood_zone_id"]        = _a(fz, "NFIPFloodZoneIdentifier")

    nbhd = prop.find("NEIGHBORHOOD")
    if nbhd is not None:
        f["neighborhood_name"]        = _a(nbhd, "_Name")
        f["location_type"]            = _a(nbhd, "PropertyNeighborhoodLocationType")
        f["location"]                 = f["location_type"]
        f["built_up"]                 = _a(nbhd, "_BuiltupRangeType")
        f["growth"]                   = _a(nbhd, "_GrowthPaceType")
        f["growth_rate"]              = f["growth"]
        f["property_values_trend"]    = _a(nbhd, "_PropertyValueTrendType")
        f["property_values"]          = f["property_values_trend"]
        f["demand_supply"]            = _a(nbhd, "_DemandSupplyType")
        f["marketing_time_typical"]   = _a(nbhd, "_TypicalMarketingTimeDurationType")
        f["marketing_time"]           = f["marketing_time_typical"]
        f["neighborhood_boundaries"]      = _a(nbhd, "_BoundaryAndCharacteristicsDescription")
        f["neighborhood_description"]     = _a(nbhd, "_Description")
        f["market_conditions_commentary"] = _a(nbhd, "_MarketConditionsDescription")
        _LAND_USE = {"SingleFamily": "land_use_one_unit",
                     "TwoToFourFamily": "land_use_2_4_unit",
                     "Apartment": "land_use_multi_family",
                     "Commercial": "land_use_commercial",
                     "Other": "land_use_other"}
        for lu in nbhd.findall(".//_PRESENT_LAND_USE"):
            t = _a(lu, "_Type")
            key = _LAND_USE.get(t)
            if key and _a(lu, "_Percent"):
                f[key] = _a(lu, "_Percent")
            if t == "Other" and _a(lu, "_TypeOtherDescription"):
                f["land_use_other_description"] = _a(lu, "_TypeOtherDescription")
        housing = nbhd.find("_HOUSING")
        if housing is not None:
            f["price_low"]            = _a(housing, "_LowPriceAmount")
            f["price_high"]           = _a(housing, "_HighPriceAmount")
            f["price_predominant"]    = _a(housing, "_PredominantPriceAmount")
            f["predominant_price"]    = f["price_predominant"]
            f["age_low_years"]        = _a(housing, "_NewestYearsCount")
            f["age_low"]              = f["age_low_years"]
            f["age_high_years"]       = _a(housing, "_OldestYearsCount")
            f["age_high"]             = f["age_high_years"]
            f["age_predominant_years"]  = _a(housing, "_PredominantAgeYearsCount")
            f["predominant_age"]        = f["age_predominant_years"]

    sc = prop.find("SALES_CONTRACT")
    if sc is not None:
        f["contract_price"]      = _a(sc, "_Amount")
        f["contract_date"]       = _a(sc, "_Date")
        f["contract_analyzed"]   = _a(sc, "_ReviewedIndicator")
        f["concessions_indicator"] = _a(sc, "SalesConcessionIndicator")
        f["concessions_amount"]  = _a(sc, "SalesConcessionAmount")
        f["contract_analysis_comment"] = _a(sc, "_ReviewComment")

    lh = prop.find("LISTING_HISTORY")
    if lh is not None:
        f["listed_past_year"]    = _a(lh, "ListedWithinPreviousYearIndicator")
        f["listing_history"]     = _a(lh, "ListedWithinPreviousYearDescription")


def _extract_market_inventory(root: ET.Element, f: dict) -> None:
    """1004MC market-conditions grid. Rows are keyed by _Type + _MonthRangeType
    (order-independent), never by column position."""
    _RANGE = {"Prior7To12Months": "prior_7_12", "Prior4To6Months": "prior_4_6",
              "Last3Months": "current_3"}
    _TYPE = {"TotalSales": "total_sales", "AbsorptionRate": "absorption_rate",
             "Supply": "months_supply", "MedianSalesPrice": "median_sale_price",
             "TotalListings": "total_listings", "MedianSalesDOM": "median_dom"}
    for mi in root.findall(".//MARKET_INVENTORY"):
        t = _TYPE.get(_a(mi, "_Type"))
        if not t:
            continue
        value = _a(mi, "_Count") or _a(mi, "_Rate") or _a(mi, "_Amount")
        rng = _RANGE.get(_a(mi, "_MonthRangeType"))
        if rng and value:
            f[f"mca_{t}_{rng}"] = value
        trend = _a(mi, "_TrendType")
        if trend:
            f[f"mca_trend_{t}"] = trend


def _extract_conditions(root: ET.Element, f: dict) -> None:
    """Adverse-condition checkboxes and the as-is/subject-to assignment condition."""
    conds = [c for c in root.findall(".//_CONDITION")
             if _a(c, "_Type") in ("Infestation", "Dampness", "Settlement")]
    if conds:
        any_yes = any(_a(c, "_ExistsIndicator").upper() == "Y" for c in conds)
        f["adverse_conditions"] = "Yes" if any_yes else "No"

    coa = root.find(".//_CONDITION_OF_APPRAISAL")
    if coa is not None and _a(coa, "_Type"):
        t = _a(coa, "_Type")
        f["assignment_condition"] = t
        f["appraisal_subject_to"] = "As Is" if t.lower() in ("asis", "as is") else t


def _extract_valuation_methods(root: ET.Element, f: dict) -> None:
    recon = root.find(".//_RECONCILIATION")
    if recon is not None and _a(recon, "_SummaryComment"):
        f["final_reconciliation_comment"] = _a(recon, "_SummaryComment")

    vm = root.find("VALUATION_METHODS")
    if vm is None:
        return

    sca = vm.find("SALES_COMPARISON")
    if sca is not None:
        f["final_value_sca"]      = _a(sca, "ValueIndicatedBySalesComparisonApproachAmount")
        f["sca_comment"]          = _a(sca, "_Comment")
        f["prior_sale_analysis_comment"] = _a(sca, "_CurrentSalesAgreementAnalysisComment")

    ca = vm.find("COST_ANALYSIS")
    if ca is not None:
        f["cost_approach_value"]       = _a(ca, "ValueIndicatedByCostApproachAmount")
        f["site_value"]                = _a(ca, "SiteEstimatedValueAmount")
        f["total_improvements_cost"]   = _a(ca, "NewImprovementTotalCostAmount")
        f["cost_new_improvements"]     = f["total_improvements_cost"]
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
    comp_index = 0

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
            f[f"{pfx}_net_adj_positive"]    = comp.get("SalesPriceTotalAdjustmentPositiveIndicator", "")
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

    def _set_amount(amt_key: str, blank_key: str, t: str) -> None:
        """Preserve three states a grid rule must tell apart: row absent (write
        nothing), row present with a blank cell (flag `blank_key`), row present
        with a value ($0 is an explicit "no adjustment", not a blank)."""
        if t not in adj:
            return
        v = adj[t].get("_Amount", "")
        if v and v.strip():
            f[amt_key] = v
        else:
            f[blank_key] = "True"

    _set(f"{pfx}_sale_date",         "DateOfSale",         "_Description")
    _dos = _get("DateOfSale", "_Description")
    _m = re.search(r"s\s*(\d{1,2}/\d{2,4})", _dos or "", re.I)
    if _m:
        f[f"{pfx}_settlement_date"] = _m.group(1)
    _set(f"{pfx}_financing_adj",     "FinancingConcessions","_Amount")
    _set(f"{pfx}_location_rating",   "Location",           "_Description")
    _set(f"{pfx}_site_area",         "SiteArea",           "_Description")
    _set(f"{pfx}_site_size",         "SiteArea",           "_Description")
    _set(f"{pfx}_view",              "View",               "_Description")
    _set(f"{pfx}_design_style",      "DesignStyle",        "_Description")
    _set(f"{pfx}_design",            "DesignStyle",        "_Description")
    _set(f"{pfx}_quality_rating",    "Quality",            "_Description")
    _set(f"{pfx}_age",               "Age",                "_Description")
    _set(f"{pfx}_condition_rating",  "Condition",          "_Description")
    _set_amount(f"{pfx}_condition_adj", f"{pfx}_condition_adj_blank", "Condition")
    _set(f"{pfx}_gla",               "GrossLivingArea",    "_Description")
    _set_amount(f"{pfx}_gla_adj",    f"{pfx}_gla_adj_blank", "GrossLivingArea")
    _set(f"{pfx}_garage",            "CarStorage",         "_Description")
    _set(f"{pfx}_garage_carport",    "CarStorage",         "_Description")
    _set(f"{pfx}_concessions",       "SalesConcessions",   "_Description")
    _set(f"{pfx}_heating_cooling",   "HeatingCooling",     "_Description")
    _set(f"{pfx}_functional_utility","FunctionalUtility",  "_Description")
    _set(f"{pfx}_porch_patio_deck",  "PorchDeck",          "_Description")
    _set(f"{pfx}_basement",          "BasementArea",       "_Description")
    _set(f"{pfx}_energy_efficient",  "EnergyEfficient",    "_Description")


def _extract_subject_prior_sales(root: ET.Element, f: dict) -> None:
    """SUBJECT-level prior-sale history + PSH research fields (catalog CG-PRIOR-
    SALE / PSH-*). MISMO carries these natively (layout-independent). Only the
    SUBJECT's own PRIOR_SALES (not the comp grid, handled elsewhere)."""
    subject = root.find(".//SUBJECT")
    if subject is not None:
        hps = _a(subject, "_HasPriorSalesIndicator")
        if hps:
            f["psh_research_flag"] = "Yes" if hps.strip().upper() == "Y" else "No"
        # the subject's own prior-sales record sits directly under SUBJECT
        sps = subject.find("PRIOR_SALES")
        if sps is not None:
            if _a(sps, "PropertySalesDate"):
                f.setdefault("subject_prior_sale_date", _a(sps, "PropertySalesDate"))
            if _a(sps, "PropertySalesAmount"):
                f.setdefault("subject_prior_sale_price", _a(sps, "PropertySalesAmount"))
            if _a(sps, "DataSourceDescription"):
                f.setdefault("psh_data_source", _a(sps, "DataSourceDescription"))
            if _a(sps, "DataSourceEffectiveDate"):
                f.setdefault("psh_data_source_date", _a(sps, "DataSourceEffectiveDate"))
    # GSEPriorSaleComment / date as a secondary source
    for ps in root.iter("PRIOR_SALE"):
        if _a(ps, "GSEPriorSaleComment"):
            f.setdefault("prior_sale_analysis_comment", _a(ps, "GSEPriorSaleComment"))
        if _a(ps, "GSEPriorSaleDate"):
            f.setdefault("subject_prior_sale_date", _a(ps, "GSEPriorSaleDate"))


def _extract_forms(root: ET.Element, f: dict) -> None:
    """Extract photo/sketch/addendum presence from FORM elements."""
    addendum_parts: list[str] = []

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
                    f[f"comp_{n}_photo_present"] = "True" if has else "False"
                except ValueError:
                    pass

        if content_type == "Sketch":
            has_sketch = any(img.get("_Name") == "HasImage" for img in form.findall("IMAGE"))
            f["sketch_present"] = "True" if has_sketch else "False"
        elif content_type == "LocationMap":
            has_map = any(img.get("_Name") == "HasImage" for img in form.findall("IMAGE"))
            f["location_map_present"] = "True" if has_map else "False"

    if addendum_parts:
        f["addendum_text"] = "\n\n".join(addendum_parts)
