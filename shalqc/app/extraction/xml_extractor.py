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
from app.normalize import dates as _dates

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
    # LAST on purpose: the UAD extension layer only fills slots the base MISMO
    # document left empty, so a base value is never overwritten by an extension.
    _extract_uad_extensions(root, fields)
    # needs addendum_text, which _extract_forms populates above.
    _listing_facts_from_addendum(fields)
    _site_comments_from_addendum(fields)
    _derive_basement_absence(fields)

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

# A form cell whose "value" is really a cross-reference to the addendum, not an
# answer ("See Attached Addendum", "See Addenda", "See Below"). Treated as NOT a
# value so a real narrative elsewhere can win the slot.
_POINTER_RX = re.compile(
    r"^\s*see\s+(attached\s+)?(addend(um|a)|comments?|below|remarks?|attach)", re.I)


def _a(el: Optional[ET.Element], attr: str, default: str = "") -> str:
    """Safe attribute getter — returns empty string when element or attr absent."""
    if el is None:
        return default
    return el.get(attr, default) or default


def _num_or_none(raw: str) -> Optional[float]:
    """First numeric token in `raw` as a float, or None — for magnitude checks."""
    m = re.search(r"-?\d[\d,]*\.?\d*", str(raw or ""))
    if not m:
        return None
    try:
        return float(m.group(0).replace(",", ""))
    except ValueError:
        return None


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
    # Vendor detection (deterministic, no LLM) — MISMO 2.6 GSE is a spec each vendor
    # implements as a subset + private extensions; the software product name pins
    # which dialect this file is so per-vendor quirks stay isolated and telemetry can
    # attribute a bad read to a dialect. Never a rule input — provenance only.
    _prod = report.get("AppraisalSoftwareProductName", "") or ""
    if _prod:
        pl = _prod.lower()
        f["xml_software_product"] = _prod
        f["xml_software_version"] = report.get("AppraisalSoftwareProductVersionIdentifier", "")
        f["xml_vendor"] = ("ACI" if "aci" in pl
                           else "TOTAL" if ("a la mode" in pl or "total" in pl)
                           else "ClickForms" if "clickforms" in pl
                           else "Bradford" if "bradford" in pl
                           else "unknown")
    raw_form = report.get("AppraisalFormType", "")
    f["form_type"] = _FORM_TYPE_MAP.get(raw_form, raw_form.lower().replace("fnm", ""))
    f["appraiser_file_id"] = report.get("AppraiserFileIdentifier", "")
    f["assignment_type"] = report.get("AppraisalPurposeType", "")
    # transaction_type is the report's PURPOSE (Purchase/Refinance) — the same
    # AppraisalPurposeType attribute, under the vocabulary name the checklist uses
    # for the order-vs-report match (EQ-B/EQ-D). loan_program (FHA/Conv) is a
    # DIFFERENT axis and lives only on the engagement letter, never in the XML.
    if f["assignment_type"]:
        f["transaction_type"] = f["assignment_type"]
    f["signature_date"] = report.get("AppraiserReportSignedDate", "")
    # 2026-07-13: also write the field_schema.yaml canonical names directly
    # (not just the field_resolution.yaml aliases) — app/rules/* (v1 rules
    # engine, catalog.py's own alias map) reads "form_type"/"signature_date"
    # directly, so those internal names stay put; but a checklist/binder that
    # asks for the schema field ("report_form_number", "date_of_signature")
    # would otherwise only see it via the alias FALLBACK, which only fires
    # when the direct name is absent — a wrong-but-plausible-looking PDF
    # label-proximity guess for that same schema field (e.g. the software
    # watermark text pdf_digital found for "report_form_number") is "found"
    # and never falls through to the alias at all. Writing XML's 0.97-
    # confidence value under the canonical name too lets it win the merge
    # outright, the way SHALqc.md step 9 intends.
    f["report_form_number"] = f["form_type"]
    f["date_of_signature"] = f["signature_date"]
    f["date_report_signed"] = f["signature_date"]
    # Appraisal report TYPE (EQ-121) — not a discrete MISMO field, but derivable
    # from the report title ("Uniform Residential Appraisal Report" → an Appraisal
    # Report, unless the title/conditions say "Restricted"). A URAR is never a
    # Restricted report, so this is a clean derivation, not a guess.
    _title = report.get("_TitleDescription", "") or ""
    if _title:
        f["report_title"] = _title
        f["appraisal_report_type"] = ("Restricted Appraisal Report"
                                      if "restrict" in _title.lower() else "Appraisal Report")
    # USPAPReportDescription states the report option DIRECTLY and is present on 10 of
    # 15 sample packets — a stronger source than deriving from the form title (which
    # only some vendors emit). It also disproves "report type is PDF-only": the answer
    # is in the XML on most packets.
    # NOTE: vendors disagree about this attribute — a la mode writes the property
    # ADDRESS into it ("3135 Great Oak St"), so it is only trusted when it actually
    # names a USPAP report option. Anything else is ignored rather than stored under a
    # name that implies a report type.
    _uspap = report.get("USPAPReportDescription", "") or ""
    _lo = _uspap.lower()
    if "restrict" in _lo:
        f["uspap_report_description"] = _uspap
        f["appraisal_report_type"] = "Restricted Appraisal Report"
    elif "appraisal report" in _lo:
        f["uspap_report_description"] = _uspap
        f["appraisal_report_type"] = "Appraisal Report"


# ── UAD GSE extension sections ────────────────────────────────────────────────
# Alongside base MISMO, 12 of 15 sample packets carry a parallel UAD layer shaped
#   <X>_EXTENSION/<X>_EXTENSION_SECTION[@ExtensionSectionOrganizationName=
#   'UNIFORM APPRAISAL DATASET']/<X>_EXTENSION_SECTION_DATA/<LEAF>@GSE*
# holding the authoritative UAD answer. None of it was read. Harvested generically
# (any depth, any section) via this attribute→canonical table, so onboarding a new
# GSE attribute is one row rather than new traversal code. Base MISMO WINS: these
# only fill slots the base document left empty.
# UAD "Materials/condition" rows — stated on 13-15 of 15 packets and previously read
# only for a foundation fallback. The description checks bind these names directly.
_EXTERIOR_FIELD: Dict[str, str] = {
    "Walls":                "exterior_walls",
    "RoofSurface":          "roof_surface",
    "WindowType":           "window_type",
    "GuttersAndDownspouts": "gutters_downspouts",
    "WindowStormSash":      "storm_sash",
    "WindowScreens":        "screens",
}
_INTERIOR_FIELD: Dict[str, str] = {
    "Floors":           "floor_material",
    "Walls":            "interior_walls",
    "TrimAndFinish":    "trim_finish",
    "BathroomFloors":   "bath_floor",
    "BathroomWainscot": "bath_wainscot",
}

_GSE_EXT_FIELD: Dict[str, str] = {
    "GSEBorrowerName":                    "borrower_name",
    "GSEAssessorsParcelIdentifier":       "assessors_parcel_number",
    "GSEEffectiveAgeDescription":         "effective_age",
    "GSENeighborhoodBoundariesDescription": "neighborhood_boundaries",
    "GSEPropertyTaxTotalTaxAmount":       "real_estate_taxes",
    "GSENFIPFloodZoneIdentifier":         "fema_flood_zone",
    "GSEFEMASpecialFloodHazardAreaIndicator": "fema_flood_hazard",
    "GSEStoriesCount":                    "stories",
    "GSEUpdateLastFifteenYearIndicator":  "updated_last_15_years",
}


def _parse_listing_facts(f: dict, text: str) -> None:
    """EQ-13 binds list_date / list_price / mls_number / days_on_market. MISMO has no
    attributes for them — vendors state them inside the listing prose ("...per
    RCMLS#20261040169 dated 07/14/2026 in the amount of $269,000"), so the facts exist
    but no slot held them. Anything not stated simply stays empty."""
    if not text:
        return
    _dom = re.search(r"\bDOM\s+(\d+)", text, re.I)
    if _dom:
        f.setdefault("days_on_market", _dom.group(1))
    _ld = re.search(r"(?:listed|dated)\s+(?:on\s+)?(\d{1,2}/\d{1,2}/\d{2,4})", text, re.I)
    if not _ld:
        # Many vendors state the listing date POSITIONALLY after the offering price,
        # with no "listed/dated" keyword: "MLS #410069  -  $1,549,000  -  06/25/2026".
        # Anchor on "$amount -" so a random date elsewhere in the prose is never grabbed.
        _ld = re.search(r"\$\s?[\d,]{3,}\s*[-–]\s*(\d{1,2}/\d{1,2}/\d{2,4})", text)
    if _ld:
        f.setdefault("list_date", _ld.group(1))
    _lp = re.search(r"\$\s?([\d,]{3,})", text)
    if _lp:
        f.setdefault("list_price", _lp.group(1).replace(",", ""))
    _mls = re.search(r"([A-Z]{0,6}MLS)\s*#?\s*([A-Z0-9\-]{5,})", text, re.I)
    if _mls:
        f.setdefault("mls_number", _mls.group(2))
        f.setdefault("mls_name", _mls.group(1))


def _listing_facts_from_addendum(f: dict) -> None:
    """The listing cell is usually just "See Attached Addendum"; the real line lives in
    the addendum's listing-history section. Runs AFTER _extract_forms, because that is
    what populates addendum_text — parsing earlier silently found nothing."""
    if f.get("list_date") and f.get("mls_number"):
        return
    _add = f.get("addendum_text") or ""
    if not _add:
        return
    _m = re.search(r"-:\s*[^:]*LISTING HISTORY[^:]*:-(.{0,1200})", _add, re.I | re.S)
    _parse_listing_facts(f, _m.group(1) if _m else "")


def _site_comments_from_addendum(f: dict) -> None:
    """The form's Site section carries only short cells; the appraiser's site
    narrative — including the street-MAINTENANCE comment a private street requires
    (EQ-32: "The private street ... is maintained by HOA") — lives in the addendum's
    "-:SITE COMMENTS:-" section. Merge it into site_comments so the judge reads the
    'why', instead of seeing only street_ownership=Private and firing a false reject.
    Section-scoped and label-driven, so it stays vendor-agnostic."""
    add = f.get("addendum_text") or ""
    if not add:
        return
    m = re.search(r"-:\s*SITE\s+COMMENTS?\s*:-\s*(.*?)(?=\n?-:\s*[A-Z]|\Z)", add, re.I | re.S)
    if not m:
        return
    section = re.sub(r"\s+", " ", m.group(1)).strip(" .-")
    if not section:
        return
    existing = (f.get("site_comments") or "").strip()
    if section in existing:
        return
    f["site_comments"] = f"{existing}  {section}".strip() if existing else section


_BSMT_EXIT = {"wo": "WalkOut", "wu": "WalkUp", "up": "WalkUp", "in": "InteriorOnly"}


def _split_basement(desc: str) -> Optional[dict]:
    """Split a MISMO combined below-grade cell into its URAR grid lines.
    "1726sf726sfwo" → area 1726 sf, finished 726 sf, exit WalkOut;
    "435sf0sfin" → area 435 sf, finished 0 sf, exit InteriorOnly;
    "0sf" → area 0 sf (no finish/exit stated). None when not this shape."""
    m = re.match(r"^\s*(\d+)\s*sf(?:\s*(\d+)\s*sf)?\s*([A-Za-z]{2})?\s*$", desc or "")
    if not m:
        return None
    out = {"area": f"{m.group(1)}sf", "finished": f"{m.group(2)}sf" if m.group(2) is not None else ""}
    if m.group(3):
        out["exit"] = _BSMT_EXIT.get(m.group(3).lower(), m.group(3))
    return out


def _derive_basement_absence(f: dict) -> None:
    """When the subject positively has NO basement (a marked slab/crawlspace
    foundation, or a 0-sf below-grade grid cell), state has_full_basement /
    has_partial_basement = "No" explicitly. Absent flags made EQ-44/EQ-70 hedge to
    REVIEW because the judge could not tell "no basement" from "unknown"; an explicit
    No lets them resolve to NOT_APPLICABLE. Only fires on positive no-basement
    evidence, never on unknowns, and never overrides a Yes already found."""
    if f.get("has_full_basement") or f.get("has_partial_basement"):
        return
    area = str(f.get("subject_grid_basement_area") or f.get("subject_grid_basement_gla") or "").strip()
    ft = str(f.get("foundation_type") or "").lower()
    no_basement = bool(re.match(r"^0\s*sf$", area, re.I)) or "slab" in ft or "crawl" in ft
    if no_basement:
        f["has_full_basement"] = "No"
        f["has_partial_basement"] = "No"


def _collapse_repeat(value: str) -> str:
    """Collapse a cell that is the SAME token repeated across whitespace
    ("07/14/2026 07/14/2026 07/14/2026" → "07/14/2026") — one value read across
    several grid columns. Unchanged when the tokens are not all identical."""
    toks = (value or "").split()
    if len(toks) > 1 and len(set(toks)) == 1:
        return toks[0]
    return value


def _extract_uad_extensions(root: ET.Element, f: dict) -> None:
    for data in root.iter():
        if not data.tag.split("}")[-1].endswith("_EXTENSION_SECTION_DATA"):
            continue
        for leaf in data.iter():
            for attr, val in leaf.attrib.items():
                key = _GSE_EXT_FIELD.get(attr.split("}")[-1])
                if key and val and not f.get(key):
                    f[key] = val


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
        # APPRAISER_LICENSE can repeat (a blank supervisor row alongside the real
        # one) — pick the license that actually carries an _Identifier so we never
        # read the empty row (which surfaced appraiser_cert_state as "#").
        lics = appraiser.findall("APPRAISER_LICENSE")
        lic = next((l for l in lics if _a(l, "_Identifier")), lics[0] if lics else None)
        if lic is not None:
            f["appraiser_license_number"] = _a(lic, "_Identifier")
            f["appraiser_state_cert_number"] = f["appraiser_license_number"]
            f["appraiser_license_type"] = _a(lic, "_Type")
            f["appraiser_license_state"] = _a(lic, "_State")
            f["appraiser_cert_state"] = f["appraiser_license_state"]
            f["appraiser_license_expiration"] = _a(lic, "_ExpirationDate")
            f["appraiser_cert_expiration_date"] = f["appraiser_license_expiration"]

    lender = parties.find("LENDER")
    if lender is not None:
        f["lender_name"] = _a(lender, "_UnparsedName")
        # ACI names the AMC on LENDER/CONTACT_DETAIL (the lender is the actual lender,
        # the contact is the ordering AMC — "Equity Solutions USA"). Without this,
        # EQ-109's amc_name resolved only from MANAGEMENT_COMPANY, which this vendor
        # does not emit, so the AMC-name check had nothing to compare at all.
        _lcd = lender.find("CONTACT_DETAIL")
        if _lcd is not None and _a(_lcd, "_Name"):
            f.setdefault("lender_contact_name", _a(_lcd, "_Name"))
            # EQ-109 only asks that SOME AMC name appears under Lender/Client. The
            # contact under LENDER is exactly that name for this vendor, so it answers
            # the check; MANAGEMENT_COMPANY (when present) still wins as the primary.
            f.setdefault("amc_name", _a(_lcd, "_Name"))
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

    # Owner of public record (EQ-1 / EQ-D) — stated on PROPERTY/_OWNER on all 15
    # packets and never read, so the owner-vs-borrower check had no owner to compare.
    _owner = root.find(".//PROPERTY/_OWNER")
    if _owner is not None and _a(_owner, "_Name"):
        f["owner_of_public_record"] = _a(_owner, "_Name")
        if not f.get("owner_name"):
            f["owner_name"] = _a(_owner, "_Name")

    # Subject inspection date (14/15 packets) — distinct from the signature date and
    # required by the inspection/effective-date checks.
    for _insp in root.iter("INSPECTION"):
        if _a(_insp, "AppraisalInspectionPropertyType") in ("", "Subject") and _a(_insp, "InspectionDate"):
            f["inspection_date"] = _a(_insp, "InspectionDate")
            break

    # Appraisal Management Company — MISMO carries it on MANAGEMENT_COMPANY
    # (not always under PARTIES, so search from root). Backs EQ-109, which asks
    # the AMC named on the report matches the AMC on the engagement letter.
    mgmt = root.find(".//MANAGEMENT_COMPANY")
    if mgmt is not None and _a(mgmt, "GSEManagementCompanyName"):
        f["management_company"] = _a(mgmt, "GSEManagementCompanyName")
        f["amc_name"] = f["management_company"]


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
    # Unit # (condo/co-op/PUD) — STRUCTURE/_UNIT carries the subject's unit id. Without
    # it the address-match check (EQ-C) sees the report city ("Haiku") against an
    # engagement city that folded the unit letter in ("A Haiku") and reads a false
    # mismatch; the unit is a distinct address component and must be extracted when the
    # form states one, so the check can reconcile it instead of tripping on it.
    _unit = prop.find(".//_UNIT")
    if _unit is not None and _a(_unit, "UnitIdentifier"):
        f["unit_number"] = _a(_unit, "UnitIdentifier")
        f["subject_unit"] = f["unit_number"]
    # Legal description — MISMO carries the clean text on PROPERTY/_LEGAL_DESCRIPTION;
    # without this mapping the field fell to a PDF label-proximity grab that returned
    # narrative fragments ("aware", "used, offering price(s),") every time.
    legal = prop.find("_LEGAL_DESCRIPTION")
    if legal is not None and _a(legal, "_TextDescription"):
        f["legal_description"] = _a(legal, "_TextDescription")
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
    if "is_pud" in f:
        f["is_pud_checked"] = f["is_pud"]

    ident = prop.find("_IDENTIFICATION")
    if ident is not None:
        f["apn"]                    = _a(ident, "AssessorsParcelIdentifier")
        f["assessors_parcel_number"] = f["apn"]
        f["census_tract"]           = _a(ident, "CensusTractIdentifier")
        # Map Reference (EQ-7) — appraiser-provided grid/page reference. MISMO
        # carries it on _IDENTIFICATION; without this it fell to a visual card.
        if _a(ident, "MapReferenceIdentifier"):
            f["map_reference"] = _a(ident, "MapReferenceIdentifier")

    struct = prop.find("STRUCTURE")
    if struct is not None:
        f["gla"]          = _a(struct, "GrossLivingAreaSquareFeetCount")
        # 2-4 unit forms (FNM1025) carry NO structure-level GLA: the form states Gross
        # BUILDING area, and living area is per unit on _UNIT_GROUP. Without this the
        # `gla` slot stayed empty, fell through to the PDF text layer (which yields
        # grid junk like "calculations,"), got suppressed, and every GLA check read
        # "missing" on a report that states it plainly. Verified ESMI-0049134:
        # 1340.5 + 1622.5 = 2963 = GrossBuildingAreaSquareFeetCount.
        if not f["gla"]:
            _unit_glas = [_num_or_none(_a(ug, "GrossLivingAreaSquareFeetCount"))
                          for ug in struct.findall("_UNIT_GROUP")]
            _unit_glas = [g for g in _unit_glas if g]
            if _unit_glas:
                _sum = sum(_unit_glas)
                f["gla"] = str(int(_sum)) if _sum == int(_sum) else str(_sum)
            elif _a(struct, "GrossBuildingAreaSquareFeetCount"):
                f["gla"] = _a(struct, "GrossBuildingAreaSquareFeetCount")
        if _a(struct, "GrossBuildingAreaSquareFeetCount"):
            f["gross_building_area"] = _a(struct, "GrossBuildingAreaSquareFeetCount")
        f["total_rooms"]  = _a(struct, "TotalRoomCount")
        f["bedrooms"]     = _a(struct, "TotalBedroomCount")
        f["bathrooms"]    = _a(struct, "TotalBathroomCount")
        f["stories"]      = _a(struct, "StoriesCount")
        f["year_built"]   = _a(struct, "PropertyStructureBuiltYear")
        f["design_style"] = _a(struct, "_DesignDescription")
        f["baths"]        = f["bathrooms"]
        f["units_count"]  = _a(struct, "LivingUnitCount")
        f["dwelling_type"] = _a(struct, "AttachmentType")
        # Building status (EQ-39) — Existing / Proposed / UnderConstruction. Native
        # on STRUCTURE; without it the Existing-vs-Proposed check fell to a visual card.
        if _a(struct, "BuildingStatusType"):
            f["building_status"] = _a(struct, "BuildingStatusType")
        # Heating / cooling — STRUCTURE carries HEATING (_Type + _FuelDescription)
        # and COOLING (_CentralizedIndicator Y/N). Neither was read before, so the
        # HVAC checks (EQ-72) fell to a PDF grab that returned "Patio/Deck Cov".
        _cool = struct.find("COOLING")
        if _cool is not None and _a(_cool, "_CentralizedIndicator"):
            f["air_conditioning_type"] = ("Central" if _a(_cool, "_CentralizedIndicator").upper() == "Y"
                                          else "None")
        # Not every vendor states centralized-Y/N. Window / evaporative / ductless
        # units are carried on _UnitDescription (with _IndividualIndicator or
        # _OtherIndicator set) — verified across 4 packets ("window", "Evap",
        # "Dctless"). Without this fallback a cooled property read as having no
        # cooling value at all and EQ-72 hedged.
        if _cool is not None and not f.get("air_conditioning_type"):
            _ud = _a(_cool, "_UnitDescription")
            if _ud and _ud.strip().lower() not in ("none", "n/a"):
                f["air_conditioning_type"] = _ud
            elif _a(_cool, "_IndividualIndicator").upper() == "Y":
                f["air_conditioning_type"] = "Individual"
            elif _ud.strip().lower() == "none" or _a(_cool, "_OtherIndicator").upper() == "Y":
                f["air_conditioning_type"] = "None"
        _heat = struct.find("HEATING")
        if _heat is not None:
            # When _Type is "Other" the real system name is in _TypeOtherDescription
            # ("Ductlss,Wall" = a ductless mini-split, a permanent heat source). Using
            # the bare "Other" made EQ-72 read it as "no permanent heat" and false-
            # reject. Prefer the descriptive name so the value states the actual system.
            _htype = _a(_heat, "_Type")
            _hdesc = _a(_heat, "_TypeOtherDescription") or _a(_heat, "_FuelDescription")
            if _htype == "Other" and _hdesc:
                f["heating"] = _hdesc
            elif _htype or _hdesc:
                f["heating"] = _htype or _hdesc
            if _hdesc:
                f["heating_description"] = _hdesc
        # Exterior / interior materials. The UAD "Materials/condition" rows are stated
        # here on every packet (15/15) and were never read, so the description checks
        # that bind exterior_walls / floor_material / roof_surface had nothing to judge
        # and hedged even though the report fills the whole block.
        for feat in struct.findall("EXTERIOR_FEATURE"):
            _key = _EXTERIOR_FIELD.get(_a(feat, "_Type"))
            if _key and _a(feat, "_Description") and not f.get(_key):
                f[_key] = _a(feat, "_Description")
        for feat in struct.findall("INTERIOR_FEATURE"):
            _key = _INTERIOR_FIELD.get(_a(feat, "_Type"))
            if _key and _a(feat, "_ConditionDescription") and not f.get(_key):
                f[_key] = _a(feat, "_ConditionDescription")
        # Foundation — FOUNDATION repeats once per checkbox; the MARKED one
        # (_ExistsIndicator='Y') carries the clean type (Slab / Basement). Prefer it
        # over the free-text EXTERIOR_FEATURE description ("Concrete/ave"). The same
        # checkbox family also answers basement presence (EQ-70).
        _found = [(_a(fd, "_Type"), _a(fd, "_ExistsIndicator").upper())
                  for fd in struct.findall("FOUNDATION")]
        _marked = [t for t, ind in _found if ind == "Y" and t]
        if _marked:
            f["foundation_type"] = _marked[0]
        else:
            for feat in struct.findall("EXTERIOR_FEATURE"):
                if _a(feat, "_Type") == "Foundation" and _a(feat, "_Description"):
                    f["foundation_type"] = _a(feat, "_Description")
                    break
        # Basement presence is only informative when a basement EXISTS — the check
        # (EQ-70) triggers on presence, and foundation_type="Slab" already conveys
        # "no basement". Emit only the marked (_ExistsIndicator='Y') rows so a slab
        # house doesn't carry two redundant "No" flags.
        for _t, _ind in _found:
            if _t == "Basement" and _ind == "Y":
                f["has_full_basement"] = "Yes"
                # an explicit negative, not silence: EQ-44/EQ-70 ask WHICH basement box
                # is marked, and an absent partial flag read as "unanswered".
                f.setdefault("has_partial_basement", "No")
            elif _t == "PartialBasement" and _ind == "Y":
                f["has_partial_basement"] = "Yes"
        # EQ-44/70: the subject's Outside Entry/Exit checkbox. When Yes, the grid
        # basement line must read a walkout/walkup (subject_basement_exit, from the
        # subject COMPARISON_DETAIL below). Emit only the marked ('Y') row.
        for bf in struct.findall(".//BASEMENT_FEATURE"):
            if _a(bf, "_Type") == "OutsideEntry" and _a(bf, "_ExistsIndicator").upper() == "Y":
                f["basement_outside_entry"] = "Yes"
        # Accessory dwelling unit (EQ-36) + basement dimensions — both native.
        if _a(struct, "_AccessoryUnitExistsIndicator"):
            f["has_adu"] = "Yes" if _a(struct, "_AccessoryUnitExistsIndicator").upper() == "Y" else "No"
        # Attic (EQ-43) — "at least one box checked". ATTIC._ExistsIndicator carries
        # the None/Yes state (an "N" IS the "None" box marked, doctrine rule 9); the
        # marked ATTIC_FEATURE names which one. Surfacing the state makes the check
        # text-judgeable instead of a visual card.
        _attic = struct.find("ATTIC")
        _af = [_a(af, "_Type") for af in struct.findall(".//ATTIC_FEATURE")
               if _a(af, "_ExistsIndicator").upper() == "Y" and _a(af, "_Type")]
        if _attic is not None and _a(_attic, "_ExistsIndicator"):
            # ACI carries the Yes/None state on ATTIC._ExistsIndicator directly.
            f["attic_indicator"] = "Yes" if _a(_attic, "_ExistsIndicator").upper() == "Y" else "No"
        elif _attic is not None or _af:
            # a la mode TOTAL leaves ATTIC empty and marks the access on ATTIC_FEATURE
            # (Scuttle / DropStair / Stairs …). A marked feature ⇒ attic present.
            f["attic_indicator"] = "Yes" if _af else "No"
        if _af:
            f["attic_features"] = ", ".join(_af)
        _bsmt = struct.find("BASEMENT")
        if _bsmt is not None:
            if _a(_bsmt, "SquareFeetCount"):
                f["basement_gla"] = _a(_bsmt, "SquareFeetCount")
            if _a(_bsmt, "_FinishedPercent"):
                f["basement_finish_pct"] = _a(_bsmt, "_FinishedPercent")
        for keq in struct.findall("KITCHEN_EQUIPMENT"):
            _fld = _APPLIANCE_FIELD.get(_a(keq, "_Type"))
            if not _fld:
                continue
            if _a(keq, "_ExistsIndicator").upper() == "Y":
                f[_fld] = "Yes"
            # Multi-unit forms state appliances as a COUNT (one per unit), not a Y/N
            # indicator — "2" then failed the boolean gate and was suppressed, so the
            # appliance checks read "nullish/blank" on a report that lists them.
            # A count is presence: >0 → Yes, explicit 0 → No.
            elif _a(keq, "_Count"):
                _c = _num_or_none(_a(keq, "_Count"))
                if _c is not None:
                    f[_fld] = "Yes" if _c > 0 else "No"
        # AMENITY was never read at all. Fireplace/porch/deck/pool/fence live here on
        # every form family; without it fireplace_count fell to PDF grid-bleed
        # ("2 WoodStove(s) # 0 Driveway") and was suppressed.
        # UAD CONDITION_DETAIL rows state whether each area was updated/remodeled and
        # roughly when ("Kitchen / Remodeled / OneToFiveYearsAgo"). Present on 8/15
        # packets and never read, so a condition/updates check had no update evidence.
        _updates = []
        for cd in struct.iter("CONDITION_DETAIL"):
            _area = _a(cd, "GSEImprovementAreaType")
            _desc = _a(cd, "GSEImprovementDescriptionType")
            _when = _a(cd, "GSEEstimateYearOfImprovementType")
            if _desc:
                _updates.append(" ".join(p for p in (_area, _desc, _when) if p))
        if _updates:
            f["condition_comments"] = "; ".join(_updates)
            if any("updat" in u.lower() or "remodel" in u.lower() for u in _updates):
                f["updated"] = "Yes"
        # Garage attached/detached (EQ-74) — stated on CAR_STORAGE itself, 7/15 packets.
        _cstore = struct.find("CAR_STORAGE")
        if _cstore is not None and _a(_cstore, "_AttachmentType"):
            f["garage_type"] = _a(_cstore, "_AttachmentType")
        for am in struct.findall("AMENITY"):
            _t = _a(am, "_Type")
            _cnt, _desc = _a(am, "_Count"), _a(am, "_DetailedDescription")
            _exists = _a(am, "_ExistsIndicator").upper() == "Y"
            if _t == "Fireplace" and _cnt:
                f["fireplace_count"] = _cnt
            elif _t == "WoodStove" and _cnt and not f.get("woodstove_count"):
                f["woodstove_count"] = _cnt
            elif _t in ("Pool", "Fence", "Deck", "Porch") and (_desc or _exists):
                _key = {"Pool": "pool", "Fence": "fence",
                        "Deck": "deck", "Porch": "porch"}[_t]
                if not f.get(_key):
                    f[_key] = _desc or ("Yes" if _exists else "")
        # The UAD grid states porch/patio/deck as ONE cell; EQ-45/EQ-75 bind that
        # combined name, which nothing populated. Build it from the amenity rows.
        _ppd = [v for v in (f.get("porch"), f.get("deck")) if v and v.lower() != "none"]
        if _ppd and not f.get("porch_patio_deck"):
            f["porch_patio_deck"] = "/".join(_ppd)
        # total parking = sum of the subject's CAR_STORAGE_LOCATION spaces
        # (Garage + Carport + Driveway); scoped to THIS subject STRUCTURE so a
        # comp's storage can never leak in.
        _spaces, _seen = 0, False
        for cs in struct.iter("CAR_STORAGE_LOCATION"):
            n = _a(cs, "ParkingSpacesCount").strip()
            if n.isdigit():
                _spaces += int(n); _seen = True
        if _seen:
            f["parking_space_number"] = str(_spaces)
            # EQ-45 binds `number_of_cars`; nothing populated it, so the car-storage
            # line read as blank even though the spaces are stated per location.
            f["number_of_cars"] = str(_spaces)
        sa = struct.find("STRUCTURE_ANALYSIS")
        if sa is not None:
            f["effective_age"] = _a(sa, "EffectiveAgeYearsCount")

    # PROPERTY_ANALYSIS is a typed repeater (P2) hung directly off PROPERTY:
    # select by _Type, then read the free-text _Comment and/or the Y/N
    # _ExistsIndicator depending on the field. Previously only the two comment
    # rows were mapped, so the six Y/N conformance/deficiency boxes the checklist
    # asks about (EQ-34/49/51/52) fell to a PDF label-proximity guess or stayed
    # unbound → REVIEW even though MISMO carries them cleanly.
    _ANALYSIS_COMMENT = {"QualityAndAppearance": "condition_comments",
                         "PropertyCondition":    "improvements_comments",
                         "AdditionalFeatures":   "additional_features"}
    # Y/N indicators — surfaced three-state ("Yes"/"No"; absent ⇒ VERIFY, never FAIL).
    _ANALYSIS_INDICATOR = {
        "ConformsToNeighborhood": "conforms_to_neighborhood",
        "UtilitiesAndOffSiteImprovementsConformToNeighborhood": "utilities_typical",
        "PhysicalDeficiency": "physical_deficiency",
        # AdverseSiteConditions also arrives via _CONDITION → adverse_site_conditions;
        # keep a distinct name here so the two sources never clobber each other.
        "AdverseSiteConditions": "adverse_site_conditions_analysis",
    }
    # EQ-51 asks "any physical deficiencies OR adverse conditions?" and binds the
    # single name `adverse_conditions`, which no extractor emitted — the check had
    # nothing to answer with even though BOTH underlying boxes are stated. Combine
    # them: either one marked Yes answers the question Yes.
    def _combine_adverse() -> None:
        _pd, _asc = f.get("physical_deficiency"), f.get("adverse_site_conditions_analysis")
        if _pd or _asc:
            f.setdefault("adverse_conditions",
                         "Yes" if "Yes" in (_pd, _asc) else "No")

    for pa in prop.findall("PROPERTY_ANALYSIS"):
        t = _a(pa, "_Type")
        comment = _a(pa, "_Comment")
        ckey = _ANALYSIS_COMMENT.get(t)
        if ckey and comment:
            f[ckey] = comment
        ikey = _ANALYSIS_INDICATOR.get(t)
        if ikey:
            ind = _a(pa, "_ExistsIndicator").upper()
            if ind in ("Y", "N"):
                f[ikey] = "Yes" if ind == "Y" else "No"
            # carry the narrative alongside the box state so a judge can read the "why"
            if comment:
                f.setdefault(f"{ikey}_comment", comment)
    _combine_adverse()

    site = prop.find("SITE")
    if site is not None:
        f["site_area"]          = _a(site, "_AreaDescription")
        f["site_dimensions"]    = _a(site, "_DimensionsDescription")
        f["zoning"]             = _a(site, "_ZoningClassificationIdentifier")
        if f["zoning"]:
            f["zoning_classification"] = f["zoning"]
        f["zoning_description"] = _a(site, "_ZoningClassificationDescription")
        f["zoning_compliance"]  = _a(site, "_ZoningComplianceType")
        _hbu = _a(site, "HighestBestUseIndicator")
        if _hbu:
            f["highest_and_best_use"] = {"Y": "Yes", "N": "No"}.get(_hbu.strip().upper(), _hbu)
        # Only the Y/N indicator was read; the appraiser's REASONING lives in
        # HighestBestUseDescription (present on 12/15 packets). Feed it to the site
        # prose slot the packet builder already looks for, so an H&BU/zoning check is
        # judged on the stated rationale instead of a bare Yes.
        _hbu_txt = _a(site, "HighestBestUseDescription")
        _zone_txt = _a(site, "_ZoningClassificationDescription")
        _site_prose = [t for t in (_hbu_txt, _zone_txt)
                       if t and not _POINTER_RX.search(t)]
        if _site_prose:
            f["site_comments"] = "  ".join(_site_prose)
        # only a SEPARATE zoning note earns its own slot — when the H&BU text is all
        # there is, site_comments already carries it and a second identical field just
        # duplicates a value the reviewer would see twice.
        if _zone_txt and _zone_txt != f.get("site_comments"):
            f["zoning_comments"] = _zone_txt
        # Street ownership (EQ-32 private-street branch) — the marked
        # _OFF_SITE_IMPROVEMENT[Street]._OwnershipType (Public|Private). These hang
        # off PROPERTY (a sibling of SITE), so query from `prop`. Prefer the
        # explicitly-marked ('Y') row; fall back to any row that names ownership.
        _st_marked = [_a(o, "_OwnershipType") for o in prop.findall(".//_OFF_SITE_IMPROVEMENT")
                      if _a(o, "_Type") == "Street" and _a(o, "_ExistsIndicator").upper() == "Y"
                      and _a(o, "_OwnershipType")]
        _st_any = [_a(o, "_OwnershipType") for o in prop.findall(".//_OFF_SITE_IMPROVEMENT")
                   if _a(o, "_Type") == "Street" and _a(o, "_OwnershipType")]
        if _st_marked or _st_any:
            f["street_ownership"] = (_st_marked or _st_any)[0]
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
            # Value keeps the informative supplier (Public / Private / a
            # _NonPublicDescription like "Septic"/"Well"/"Electric") — the field
            # is data_type=string so the descriptor survives the schema gate
            # instead of being dropped as a non-boolean. A companion
            # utilities_<x>_present carries the plain present/absent boolean for
            # any consumer that only needs "is it there?" (§ user-approved merge).
            if _a(util, "_PublicIndicator").upper() == "Y":
                f[key] = "Public"
            elif _a(util, "_NonPublicDescription"):
                f[key] = _a(util, "_NonPublicDescription")
            elif _a(util, "_NonPublicIndicator").upper() == "Y":
                f[key] = "Private"
            else:
                f[key] = "None"
            f[f"{key}_present"] = "No" if f[key] in ("None", "") else "Yes"
        fz = site.find("FLOOD_ZONE")
        if fz is not None:
            # NOTE ...Indicator vs ...Identifier: SpecialFloodHazardAreaIndicator is
            # a Y/N flag; NFIPFloodZoneIdentifier is a ZONE CODE ("X"=minimal risk,
            # "AE"/"VE"=SFHA, …) — stored as the literal string, never coerced to a
            # boolean (fema_flood_zone's schema allowed_values include "X").
            f["flood_zone_indicator"] = _a(fz, "SpecialFloodHazardAreaIndicator")
            f["flood_zone_id"]        = _a(fz, "NFIPFloodZoneIdentifier")
            if f["flood_zone_indicator"]:
                f["fema_flood_hazard"] = f["flood_zone_indicator"]
            if f["flood_zone_id"]:
                f["fema_flood_zone"] = f["flood_zone_id"]
            # ST-8 requires zone, map number AND map date even outside an SFHA.
            # Map number/date live on the same element; fall back to the UAD GSE
            # extension copy (FLOOD_ZONE_INFORMATION) when the primary is blank.
            gse = fz.find(".//FLOOD_ZONE_INFORMATION")
            map_no = _a(fz, "NFIPMapIdentifier") or (_a(gse, "GSEFEMAFloodMapIdentifier") if gse is not None else "")
            map_dt = _a(fz, "NFIPMapPanelDate")
            if map_no:
                f["fema_map_number"] = map_no
            if map_dt:
                f["fema_map_date"] = map_dt

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
        # The neighborhood cell is frequently just a pointer ("See Attached Addendum").
        # The 1004MC block (REPORT/FORM/MARKET) carries the REAL market narrative in
        # NeighborhoodMarketabilityFactorsDescription / MarketTrendsReconciliationComment
        # and was never read (11/15 packets carry it). Fall back to it so a market-
        # commentary check sees prose instead of a pointer.
        _mc = f.get("market_conditions_commentary") or ""
        if (not _mc.strip()) or _POINTER_RX.search(_mc):
            for _mk in root.iter("MARKET"):
                _alt = (_a(_mk, "NeighborhoodMarketabilityFactorsDescription")
                        or _a(_mk, "MarketTrendsReconciliationComment"))
                if _alt:
                    f["market_conditions_commentary"] = _alt
                    break
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
        # EQ-22 asks that the land-use percentages total 100. It binds `land_use_total`,
        # which nothing computed, so the check could never do the arithmetic it names.
        _lu_pcts = [_num_or_none(_a(lu, "_Percent"))
                    for lu in nbhd.findall(".//_PRESENT_LAND_USE")]
        _lu_pcts = [p for p in _lu_pcts if p is not None]
        if _lu_pcts:
            _tot = sum(_lu_pcts)
            f["land_use_total"] = str(int(_tot)) if _tot == int(_tot) else str(_tot)
        housing = nbhd.find("_HOUSING")
        if housing is not None:
            # The URAR "One-Unit Housing" price columns are in $(000)s per the GSE UAD
            # convention (e.g. "490" = $490,000), while comp sale prices and the
            # opinion of value are whole dollars. Scale to whole dollars so the
            # value-vs-predominant and range-brackets-comps checks (EQ-21/54) compare
            # like magnitudes. Guarded by magnitude: a value already >= 10,000 is
            # left untouched (no home price range is legitimately under $10k), so a
            # vendor that already exports whole dollars is never double-scaled.
            def _scale_000(raw: str) -> str:
                n = _num_or_none(raw)
                if n is None:
                    return raw
                return str(int(round(n * 1000))) if 0 < n < 10_000 else raw
            f["price_low"]            = _scale_000(_a(housing, "_LowPriceAmount"))
            f["price_high"]           = _scale_000(_a(housing, "_HighPriceAmount"))
            f["price_predominant"]    = _scale_000(_a(housing, "_PredominantPriceAmount"))
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
        if f["contract_analyzed"]:
            f["did_analyze_contract"] = f["contract_analyzed"]
        f["concessions_indicator"] = _a(sc, "SalesConcessionIndicator")
        if f["concessions_indicator"]:
            f["has_financial_assistance"] = f["concessions_indicator"]
        f["concessions_amount"]  = _a(sc, "SalesConcessionAmount")
        # `seller_concessions` is the slot the concession checks bind to; without the
        # alias it fell through to the PDF ("gift or downpayment" — a caption fragment)
        # and was suppressed, so a stated $10,000 concession read as absent.
        if f["concessions_amount"]:
            f["seller_concessions"] = f["concessions_amount"]
            # EQ-18 binds `financial_assistance_amount`; nothing populated it, so the
            # amount the contract states was invisible to the check.
            f["financial_assistance_amount"] = f["concessions_amount"]
        # The contract's own data source (e.g. "PA/Assessor") — the EQ-17 owner/data
        # source check reported it missing while the attribute was populated.
        if _a(sc, "DataSourceDescription"):
            f["data_source"] = _a(sc, "DataSourceDescription")
            f["owner_record_data_source"] = _a(sc, "DataSourceDescription")
        if _a(sc, "SalesConcessionDescription"):
            f["financial_assistance_description"] = _a(sc, "SalesConcessionDescription")
        f["contract_analysis_comment"] = _a(sc, "_ReviewComment")
        f["is_seller_owner_of_record"] = _a(sc, "SellerIsOwnerIndicator")
        # subject sale type (arms-length?) lives on the GSE SALES_TRANSACTION
        # extension INSIDE the contract — NOT the COMPARISON_DETAIL copies, which
        # are the comps' sale types (→ comp_N_sale_type, handled in the grid).
        st = sc.find(".//SALES_TRANSACTION")
        if st is not None and _a(st, "GSESaleType"):
            f["sale_type"] = _a(st, "GSESaleType")

    lh = prop.find("LISTING_HISTORY")
    if lh is not None:
        f["listed_past_year"]    = _a(lh, "ListedWithinPreviousYearIndicator")
        f["listing_history"]     = _a(lh, "ListedWithinPreviousYearDescription")
        f["offered_for_sale_12mo"] = f["listed_past_year"]
        # the UAD description packs "DOM <n>;<free text>" — pull days-on-market out
        # so EQ-13's data-source/DOM check reads a number, not the whole blob.
        _dom = re.search(r"\bDOM\s+(\d+)", f["listing_history"], re.I)
        if _dom:
            f["days_on_market"] = _dom.group(1)
        # EQ-13 binds list_date / list_price / mls_number. MISMO has no attributes for
        # them — vendors state them INSIDE this description ("The subject was listed on
        # 04/02/2026 for $135,000 ... MLS#20261040169"), so the facts exist but no slot
        # held them. Parsed out; anything not stated simply stays empty.
        _parse_listing_facts(f, f["listing_history"] or "")

    # Special assessments — the _TAX row carries a _TotalSpecialTaxAmount even
    # when it is "0" (a real answer, not a gap; EQ-10 only needs a comment when > 0).
    tax = prop.find(".//_TAX")
    if tax is not None and _a(tax, "_TotalSpecialTaxAmount"):
        f["special_assessments"] = _a(tax, "_TotalSpecialTaxAmount")
    # Annual R.E. taxes. "0" is a REAL answer (tax-exempt / land-bank parcels state
    # $0.00), so it is kept verbatim rather than treated as blank — the PDF fallback
    # produced "$ 0.00" which plausibility rejected, leaving the check with nothing.
    if tax is not None and _a(tax, "_TotalTaxAmount"):
        f["real_estate_taxes"] = _a(tax, "_TotalTaxAmount")
    if tax is not None and _a(tax, "_YearIdentifier"):
        f["tax_year"] = _a(tax, "_YearIdentifier")

    # PUD/condo PROJECT block (only present for project properties).
    proj = prop.find("PROJECT")
    if proj is not None:
        # Project name + developer-control flag + PUD classification live natively on
        # PROJECT — none were read before, so EQ-95 (developer controls HOA) and the
        # project-name check fell to narrative grabs ("Foxwood Meadows" → "work,").
        if _a(proj, "_Name"):
            f["project_name"] = _a(proj, "_Name")
        _dev = _a(proj, "_DeveloperControlsProjectManagementIndicator")
        if _dev:
            f["is_developer_controls_hoa"] = "Yes" if _dev.upper() == "Y" else "No"
        _pcls = _a(proj, "_ClassificationType")
        if _pcls and "is_pud" not in f:
            f["is_pud"] = "Yes" if _pcls.strip().lower() == "pud" else "No"
            f["is_pud_checked"] = f["is_pud"]
        if _a(proj, "_CommonElementsDescription"):
            f["common_elements_description"] = _a(proj, "_CommonElementsDescription")
        puf = proj.find(".//_PER_UNIT_FEE")
        if puf is not None:
            if _a(puf, "_PeriodType"):
                f["hoa_period"] = _a(puf, "_PeriodType")
            # Only surface hoa_dues when there is an actual due. A "0" _Amount is
            # "no HOA dues" — emitting it would make EQ-11's `hoa_dues present`
            # antecedent fire on every non-HOA property and demand is_pud=True.
            _fee = _a(puf, "_Amount").replace("$", "").replace(",", "").strip()
            try:
                if float(_fee) > 0:
                    f["hoa_dues"] = _a(puf, "_Amount")
            except ValueError:
                if _fee:
                    f["hoa_dues"] = _a(puf, "_Amount")


def _extract_market_inventory(root: ET.Element, f: dict) -> None:
    """1004MC market-conditions grid. Rows are keyed by _Type + _MonthRangeType
    (order-independent), never by column position."""
    _RANGE = {"Prior7To12Months": "prior_7_12", "Prior4To6Months": "prior_4_6",
              "Last3Months": "current_3"}
    _TYPE = {"TotalSales": "total_sales", "AbsorptionRate": "absorption_rate",
             "Supply": "months_supply", "MedianSalesPrice": "median_sale_price",
             "TotalListings": "total_listings", "MedianSalesDOM": "median_dom",
             "MedianListPrice": "median_list_price", "MedianListDOM": "median_list_dom",
             "MedianSalesToListRatio": "median_sale_list_ratio"}
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
    # NAME MISMATCH, not a data gap: the 1004MC "total listings" row IS the active
    # listing count, and the checklist binds `mca_active_listings_*`. Without the
    # alias EQ-113 asked for a number the grid already carried under another name.
    for _rng in ("current_3", "prior_4_6", "prior_7_12"):
        _v = f.get(f"mca_total_listings_{_rng}")
        if _v and not f.get(f"mca_active_listings_{_rng}"):
            f[f"mca_active_listings_{_rng}"] = _v


def _extract_conditions(root: ET.Element, f: dict) -> None:
    """Adverse-condition checkboxes and the as-is/subject-to assignment condition."""
    conds = [c for c in root.findall(".//_CONDITION")
             if _a(c, "_Type") in ("Infestation", "Dampness", "Settlement")]
    if conds:
        any_yes = any(_a(c, "_ExistsIndicator").upper() == "Y" for c in conds)
        f["adverse_conditions"] = "Yes" if any_yes else "No"
        # "adverse_site_conditions" is a duplicate schema entry for the same
        # form checkbox ("Are there any adverse site conditions...?") — XML
        # only ever populated the first name, so the second fell to a PDF
        # label-proximity guess every time ("or" — grabbed off "Yes  or  No").
        f["adverse_site_conditions"] = f["adverse_conditions"]

    coa = root.find(".//_CONDITION_OF_APPRAISAL")
    if coa is not None and _a(coa, "_Type"):
        t = _a(coa, "_Type")
        f["assignment_condition"] = t
        f["appraisal_subject_to"] = "As Is" if t.lower() in ("asis", "as is") else t


def _extract_valuation_methods(root: ET.Element, f: dict) -> None:
    recon = root.find(".//_RECONCILIATION")
    if recon is not None:
        if _a(recon, "_SummaryComment"):
            f["final_reconciliation_comment"] = _a(recon, "_SummaryComment")
        # Conditions/repairs commentary (EQ-91) — the "subject to" repairs & cost-to-
        # cure narrative lives here when present. Absent on an "As Is" report.
        if _a(recon, "_ConditionsComment"):
            f["conditions_comment"] = _a(recon, "_ConditionsComment")

    vm = root.find("VALUATION_METHODS")
    if vm is None:
        return

    sca = vm.find("SALES_COMPARISON")
    if sca is not None:
        f["final_value_sca"]      = _a(sca, "ValueIndicatedBySalesComparisonApproachAmount")
        if f["final_value_sca"]:
            f["indicated_value_sca"] = f["final_value_sca"]
        f["sca_comment"]          = _a(sca, "_Comment")
        if f["sca_comment"]:
            f["sales_comparison_summary"] = f["sca_comment"]
        f["prior_sale_analysis_comment"] = _a(sca, "_CurrentSalesAgreementAnalysisComment")
        # "I researched N comparable sales" — the top-of-grid count (ST/checklist
        # asks it be filled). Subject-level, single RESEARCH element.
        research = sca.find("RESEARCH")
        if research is not None:
            if _a(research, "ComparableSalesResearchedCount"):
                f["comparable_count"] = _a(research, "ComparableSalesResearchedCount")
                f["comp_sales_researched_count"] = _a(research, "ComparableSalesResearchedCount")
            if _a(research, "ComparableListingsResearchedCount"):
                f["comp_listings_researched_count"] = _a(research, "ComparableListingsResearchedCount")
            # Top-of-grid price ranges (EQ-53/54/114/115). These are the SALES and
            # LISTINGS ranges the appraiser researched — distinct from the
            # neighborhood _HOUSING range. low must be < high; each comp's price
            # should fall inside the sales range.
            if _a(research, "ComparableSalesPriceRangeLowAmount"):
                f["comp_sales_range_low"] = _a(research, "ComparableSalesPriceRangeLowAmount")
            if _a(research, "ComparableSalesPriceRangeHighAmount"):
                f["comp_sales_range_high"] = _a(research, "ComparableSalesPriceRangeHighAmount")
            if _a(research, "ComparableListingsPriceRangeLowAmount"):
                f["comp_listings_range_low"] = _a(research, "ComparableListingsPriceRangeLowAmount")
            if _a(research, "ComparableListingsPriceRangeHighAmount"):
                f["comp_listings_range_high"] = _a(research, "ComparableListingsPriceRangeHighAmount")
            # the "I DID / DID NOT research the sale history" checkbox — carried in
            # XML as a Y/N indicator, not a value. Checks EQ-79/80 ask whether this
            # box is marked; surface it so the judge sees the box STATE, not just
            # the prior-sale dates.
            if _a(research, "SalesHistoryResearchedIndicator"):
                f["sales_history_researched"] = "Yes" if _a(research, "SalesHistoryResearchedIndicator").upper() == "Y" else "No"

    ca = vm.find("COST_ANALYSIS")
    if ca is not None:
        f["cost_approach_value"]       = _a(ca, "ValueIndicatedByCostApproachAmount")
        if f["cost_approach_value"]:
            f["indicated_value_cost_approach"] = f["cost_approach_value"]
        # How the site value was derived (paired sales, extraction, …). EQ-92 asks for
        # SUPPORT for the site-value opinion; unread, the check only ever saw the bare
        # amount. Present on 12/15 packets. Routed to the cost prose slot.
        _sv_comment = _a(ca, "SiteEstimatedValueComment")
        if _sv_comment and not _POINTER_RX.search(_sv_comment):
            f["site_value_comment"] = _sv_comment
            f["cost_approach_comment"] = _sv_comment
        _ca_comment = _a(ca, "_Comment")
        if _ca_comment and not _POINTER_RX.search(_ca_comment) and not f.get("cost_approach_comment"):
            f["cost_approach_comment"] = _ca_comment
        f["site_value"]                = _a(ca, "SiteEstimatedValueAmount")
        if f["site_value"]:
            f["site_value_estimate"] = f["site_value"]
        f["remaining_economic_life"]   = _a(ca, "EstimatedRemainingEconomicLifeYearsCount")
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
        if f["income_approach_value"]:
            f["indicated_value_income_approach"] = f["income_approach_value"]
        f["gross_rent_multiplier"]  = _a(ia, "GrossRentMultiplierFactor")
        # Estimated market rent drives the income approach on 2-4 unit forms; unread,
        # it fell to the PDF layer which returned an address fragment.
        if _a(ia, "EstimatedMarketMonthlyRentAmount"):
            f["indicated_monthly_market_rent"] = _a(ia, "EstimatedMarketMonthlyRentAmount")
            f["income_approach_monthly_rent"] = _a(ia, "EstimatedMarketMonthlyRentAmount")
        if _a(ia, "_Comment"):
            f["rent_market_comments"] = _a(ia, "_Comment")


def _extract_valuation(root: ET.Element, f: dict) -> None:
    val = root.find("VALUATION")
    if val is None:
        return
    f["appraised_value"] = _a(val, "PropertyAppraisedValueAmount")
    f["effective_date"]  = _a(val, "AppraisalEffectiveDate")
    # market_value_opinion is the SAME fact as the appraised value (there is no
    # separate MISMO field) — alias it so the reconciliation/site-value checks
    # (EQ-89, EQ-92, EQ-108, EQ-21) have the value they compare against.
    if f["appraised_value"]:
        f["market_value_opinion"] = f["appraised_value"]


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
            # the subject's OWN condition/quality rating (schema fields
            # condition_rating/quality_rating, sections subject+improvements+
            # sales_comparison) is the exact same fact as the grid's subject
            # row — xml_extractor had only ever written the latter, so the
            # bare canonical name was never populated by XML and fell to a
            # PDF label-proximity guess ("of", "A head") every time (2026-07-13
            # dry-run cause #1/#3).
            if f.get(f"{pfx}_condition_rating"):
                f["condition_rating"] = f[f"{pfx}_condition_rating"]
            if f.get(f"{pfx}_quality_rating"):
                f["quality_rating"] = f[f"{pfx}_quality_rating"]
            # the subject's own functional-utility rating is the grid's subject-row
            # value (EQ-71) — the bare canonical name was never populated by XML, so
            # it fell to a PDF grab that returned the grid ROW LABEL, not the value.
            if f.get(f"{pfx}_functional_utility"):
                f["functional_utility"] = f[f"{pfx}_functional_utility"]
            # Subject design (style) (EQ-40/EQ-65) — canonical design_style is read
            # from STRUCTURE/_DesignDescription, which some vendors omit while still
            # populating the grid's subject-row Design (Style) cell (e.g. "DT1L;SFR").
            # Backfill from the grid so the check doesn't read "field absent" when the
            # value is plainly on the form. STRUCTURE wins when it did carry one.
            if not f.get("design_style") and f.get(f"{pfx}_design_style"):
                f["design_style"] = f[f"{pfx}_design_style"]
            if prior is not None:
                _pd = _a(prior, "PropertySalesDate")
                f["prior_sale_date"]  = _dates.to_display(_pd) or _pd
                f["prior_sale_price"] = _a(prior, "PropertySalesAmount")
                # EQ-85 binds prior_sale_effective_date_subject / data source — the
                # subject's PRIOR_SALES row carries both, but the SUBJECT-element reader
                # never sees this grid-row instance, so they were absent on every order.
                _psrc = comp.find("PRIOR_SALES")
                if _psrc is not None:
                    _ped = _a(_psrc, "DataSourceEffectiveDate")
                    if _ped:
                        f.setdefault("prior_sale_effective_date_subject", _dates.to_display(_ped) or _ped)
                    if _a(_psrc, "DataSourceDescription"):
                        f.setdefault("prior_sale_data_source_subject", _a(_psrc, "DataSourceDescription"))
            # EQ-119 (condo/co-op): the project phase — on the subject grid row. Absent
            # on every order because nothing read it; the check hedged for lack of it.
            if comp.get("ProjectPhaseIdentifier"):
                f.setdefault("project_phase", comp.get("ProjectPhaseIdentifier"))
            # EQ-44/70: the subject grid's basement exit type (WalkOut|WalkUp|
            # InteriorOnly) — must be a walkout/walkup when basement_outside_entry=Yes.
            _scd = comp.find(".//COMPARISON_DETAIL")
            if _scd is not None and _a(_scd, "GSEBasementExitType"):
                f["subject_basement_exit"] = _a(_scd, "GSEBasementExitType")
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
            # a la mode TOTAL carries the comp's did/did-not prior-sales box directly
            # (EQ-81); ACI omits it (inferred from the PRIOR_SALES child instead). Emit
            # when present so the box STATE is available, not just the prior dates.
            if _a(comp, "_HasPriorSalesIndicator"):
                f[f"{pfx}_has_prior_sales"] = "Yes" if _a(comp, "_HasPriorSalesIndicator").upper() == "Y" else "No"
            f[f"{pfx}_data_source"]         = comp.get("DataSourceDescription", "")
            f[f"{pfx}_verification_source"] = comp.get("DataSourceVerificationDescription", "")
            # Each comp carries its own COMPARISON_DETAIL (under COMPARISON_DETAIL_
            # EXTENSION) with the GSE UAD attributes: concession amount, listing
            # status (SettledSale/ActiveListing), MLS data source, DOM, sale type.
            # These back EQ-59 (concession w/o adjustment), EQ-115 (sale vs listing),
            # EQ-13/17 (data source). The plain COMPARABLE_SALE attributes above are
            # blank in a la mode files — the real values live here.
            cd = comp.find(".//COMPARISON_DETAIL")
            if cd is not None:
                if _a(cd, "GSEConcessionAmount"):
                    f[f"{pfx}_concession_amount"] = _a(cd, "GSEConcessionAmount")
                if _a(cd, "GSEDataSourceDescription"):
                    f[f"{pfx}_data_source"] = _a(cd, "GSEDataSourceDescription")
                if _a(cd, "GSEDaysOnMarketDescription"):
                    f[f"{pfx}_days_on_market"] = _a(cd, "GSEDaysOnMarketDescription")
                if _a(cd, "GSEBasementExitType"):
                    f[f"{pfx}_basement_exit"] = _a(cd, "GSEBasementExitType")
                # NOTE: GSEListingStatusType (SettledSale/ActiveListing) and
                # GSESaleType (ArmsLengthSale) are also here and back EQ-115, but they
                # are MISMO enum codes with NO literal PDF text, so the back-locator
                # cannot ground them (they'd all land location_quality="none"). Wiring
                # them now regresses the >=90% exact DoD. Deferred until the back-locator
                # can page-locate XML-only enum fields (or the DoD excludes that category).
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
                _cpd = _a(prior, "PropertySalesDate")
                f[f"{pfx}_prior_sale_date"]  = _dates.to_display(_cpd) or _cpd
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
    # The financing row's DESCRIPTION carries the terms + concession figure
    # ("Conv;0" = conventional, zero concessions). Only the _Amount was read, so a
    # concessions check reported "no adjustment or zero entry found" while the grid
    # plainly stated one.
    _set(f"{pfx}_financing_concessions", "FinancingConcessions", "_Description")
    _set(f"{pfx}_location_rating",   "Location",           "_Description")
    # EQ-62 binds comp_N_leasehold: the grid's PropertyRights row states each comp's
    # tenure ("Fee Simple" / "Leasehold"). It was never mapped, so the check saw the
    # subject's rights but NO comp rights and hedged to REVIEW on every order. Map the
    # rights cell and derive the leasehold flag the check reads.
    _set(f"{pfx}_property_rights",   "PropertyRights",     "_Description")
    _pr = _get("PropertyRights", "_Description")
    if _pr:
        f[f"{pfx}_leasehold"] = "Yes" if "lease" in _pr.lower() else "No"
    _set(f"{pfx}_site_area",         "SiteArea",           "_Description")
    _set(f"{pfx}_site_size",         "SiteArea",           "_Description")
    _set(f"{pfx}_view",              "View",               "_Description")
    _set(f"{pfx}_design_style",      "DesignStyle",        "_Description")
    _set(f"{pfx}_design",            "DesignStyle",        "_Description")
    _set(f"{pfx}_quality_rating",    "Quality",            "_Description")
    # EQ-66: the LINE-ITEM quality adjustment (not the net). Row-present-but-blank
    # ($0/absent cell) is tracked distinctly so "differs with no adjustment" is
    # judged on the quality cell itself, never the net.
    _set_amount(f"{pfx}_quality_adj", f"{pfx}_quality_adj_blank", "Quality")
    _set(f"{pfx}_age",               "Age",                "_Description")
    _set(f"{pfx}_condition_rating",  "Condition",          "_Description")
    _set_amount(f"{pfx}_condition_adj", f"{pfx}_condition_adj_blank", "Condition")
    _set(f"{pfx}_gla",               "GrossLivingArea",    "_Description")
    _set_amount(f"{pfx}_gla_adj",    f"{pfx}_gla_adj_blank", "GrossLivingArea")
    _set(f"{pfx}_garage",            "CarStorage",         "_Description")
    _set(f"{pfx}_garage_carport",    "CarStorage",         "_Description")
    _set(f"{pfx}_concessions",       "SalesConcessions",   "_Description")
    # EQ-59 binds comp_N_concession_amount / comp_N_financing_adj. The grid states the
    # concession in the SalesConcessions cell and the financing terms (incl. an explicit
    # "0") in FinancingConcessions, so alias both names onto the cells that hold them —
    # otherwise the check reads "no adjustment or zero entry" while the grid shows one.
    _set(f"{pfx}_concession_amount", "SalesConcessions",   "_Description")
    if not f.get(f"{pfx}_financing_adj"):
        _set(f"{pfx}_financing_adj", "FinancingConcessions", "_Description")
    # EQ-74 binds comp_N_garage_carport; the grid carries car storage on the Parking row.
    _set(f"{pfx}_garage_carport",    "Parking",            "_Description")
    _set(f"{pfx}_heating_cooling",   "HeatingCooling",     "_Description")
    _set(f"{pfx}_functional_utility","FunctionalUtility",  "_Description")
    _set(f"{pfx}_porch_patio_deck",  "PorchDeck",          "_Description")
    _set(f"{pfx}_basement",          "BasementArea",       "_Description")
    # EQ-70 binds comp_N_basement_gla; the grid states the below-grade area in the
    # SAME BasementArea cell ("0sf", "1340sf"), so alias rather than leave it blank.
    _set(f"{pfx}_basement_gla",      "BasementArea",       "_Description")
    # MISMO packs the URAR's TWO below-grade grid lines (Area / Finished) plus the
    # exit code into ONE BasementArea cell ("1726sf726sfwo" = 1726 sf total, 726 sf
    # finished, walkout). EQ-70 requires the two lines to read separately, so a
    # combined cell tripped it even though the appraiser filled both. Split the cell
    # into its components so the check sees the separate area + finish it expects.
    _bsmt = _split_basement(adj.get("BasementArea", {}).get("_Description", ""))
    if _bsmt:
        f[f"{pfx}_basement_area"]     = _bsmt["area"]
        f[f"{pfx}_basement_finished"] = _bsmt["finished"]
        if _bsmt.get("exit"):
            f[f"{pfx}_basement_exit"] = _bsmt["exit"]
    _set(f"{pfx}_energy_efficient",  "EnergyEfficient",    "_Description")
    # EQ-73: the LINE-ITEM energy-efficiency adjustment ($0 is an explicit "no
    # adjustment", tracked apart from an absent cell).
    _set_amount(f"{pfx}_energy_adj", f"{pfx}_energy_adj_blank", "EnergyEfficient")


def _extract_subject_prior_sales(root: ET.Element, f: dict) -> None:
    """SUBJECT-level prior-sale history + PSH research fields (catalog CG-PRIOR-
    SALE / PSH-*). MISMO carries these natively (layout-independent). Only the
    SUBJECT's own PRIOR_SALES (not the comp grid, handled elsewhere)."""
    subject = root.find(".//SUBJECT")
    if subject is not None:
        hps = _a(subject, "_HasPriorSalesIndicator")
        if hps:
            f["psh_research_flag"] = "Yes" if hps.strip().upper() == "Y" else "No"
        # Some vendors state the research source on SUBJECT itself rather than on a
        # child PRIOR_SALES row (ESMI-0049134: "Realcomp RCMLS/Wayne County Public
        # Records"), so the child-only read above missed it entirely.
        if _a(subject, "DataSourceDescription"):
            f.setdefault("prior_sale_data_source_subject", _a(subject, "DataSourceDescription"))
            f.setdefault("psh_data_source", _a(subject, "DataSourceDescription"))
        if _a(subject, "DataSourceEffectiveDate"):
            f.setdefault("prior_sale_effective_date_subject", _a(subject, "DataSourceEffectiveDate"))

    # RESEARCH/COMPARABLE states, once, whether the comps' prior-sale history was
    # researched (EQ-81 binds comp_N_has_prior_sales). Stamp it on each comp that has
    # a grid row so the per-comp check can read it; a comp's OWN PRIOR_SALES row, when
    # present, is the stronger answer and is written by the grid extractor.
    _res_comp = root.find(".//SALES_COMPARISON/RESEARCH/COMPARABLE")
    if _res_comp is not None and _a(_res_comp, "_HasPriorSalesIndicator"):
        _flag = "Yes" if _a(_res_comp, "_HasPriorSalesIndicator").strip().upper() == "Y" else "No"
        for _i in range(1, 10):
            if f.get(f"comp_{_i}_sale_price") and not f.get(f"comp_{_i}_has_prior_sales"):
                f[f"comp_{_i}_has_prior_sales"] = _flag
        # the subject's own prior-sales record sits directly under SUBJECT
        sps = subject.find("PRIOR_SALES")
        if sps is not None:
            if _a(sps, "PropertySalesDate"):
                f.setdefault("subject_prior_sale_date", _a(sps, "PropertySalesDate"))
            if _a(sps, "PropertySalesAmount"):
                f.setdefault("subject_prior_sale_price", _a(sps, "PropertySalesAmount"))
            if _a(sps, "DataSourceDescription"):
                f.setdefault("psh_data_source", _a(sps, "DataSourceDescription"))
                # EQ-84/EQ-85 bind the *_subject names, which nothing populated — the
                # prior-sale source and its effective date were invisible to them.
                f.setdefault("prior_sale_data_source_subject", _a(sps, "DataSourceDescription"))
            if _a(sps, "DataSourceEffectiveDate"):
                f.setdefault("psh_data_source_date", _a(sps, "DataSourceEffectiveDate"))
                f.setdefault("prior_sale_effective_date_subject", _a(sps, "DataSourceEffectiveDate"))
    # GSEPriorSaleComment / date as a secondary source
    for ps in root.iter("PRIOR_SALE"):
        if _a(ps, "GSEPriorSaleComment"):
            f.setdefault("prior_sale_analysis_comment", _a(ps, "GSEPriorSaleComment"))
        if _a(ps, "GSEPriorSaleDate"):
            f.setdefault("subject_prior_sale_date", _a(ps, "GSEPriorSaleDate"))

    # The subject's grid row (COMPARABLE_SALE seq=0) IS the subject's own prior
    # sale; use it when the SUBJECT element's PRIOR_SALES didn't carry the amount
    # (a $0 grant-deed transfer still has an explicit "0" here). Additive fallback.
    if not f.get("subject_prior_sale_price") and f.get("prior_sale_price") is not None:
        f["subject_prior_sale_price"] = f["prior_sale_price"]
    if not f.get("subject_prior_sale_date") and f.get("prior_sale_date"):
        f["subject_prior_sale_date"] = f["prior_sale_date"]

    # A grid row whose single date spans several comp columns can arrive space-joined
    # ("07/14/2026 07/14/2026 07/14/2026 07/14/2026"); EQ-82 then reads that as a
    # repeated-date typo the appraiser never made. Collapse an all-identical repeat to
    # the single token before any date handling. Generic (any repeated-token cell).
    if f.get("subject_prior_sale_date"):
        f["subject_prior_sale_date"] = _collapse_repeat(f["subject_prior_sale_date"])
    # MISMO stores prior-sale dates ISO (YYYY-MM-DD); the form and the AMC check
    # (EQ-82) use MM/DD/YYYY. Present the form's format so a valid ISO date is never
    # read as a wrong-format typo. Generic date display normalization, any AMC.
    if f.get("subject_prior_sale_date"):
        f["subject_prior_sale_date"] = _dates.to_display(f["subject_prior_sale_date"]) or f["subject_prior_sale_date"]

    # Surface the subject prior-sale under the checklist's OWN canonical names too
    # (the internal names alias only partially). setdefault → additive: never
    # overwrites a value another source already supplied.
    if f.get("subject_prior_sale_date"):
        f.setdefault("prior_sale_date_subject", f["subject_prior_sale_date"])
    if f.get("subject_prior_sale_price"):
        f.setdefault("prior_sale_price_subject", f["subject_prior_sale_price"])


def _extract_forms(root: ET.Element, f: dict) -> None:
    """Extract photo/sketch/addendum presence from FORM elements."""
    addendum_parts: list[str] = []

    for form in root.findall(".//FORM"):
        content_type = form.get("AppraisalReportContentType", "")
        # UAD data-set stamp (EQ-136): "UAD Version 9/2011" lives on the FORM's
        # AppraisalReportContentIdentifier. First non-empty one wins.
        cid = form.get("AppraisalReportContentIdentifier", "")
        if cid and "uad_version" not in f:
            f["uad_version"] = cid
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
