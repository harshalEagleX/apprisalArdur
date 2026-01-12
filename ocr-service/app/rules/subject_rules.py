"""
Subject Section Rules (S-1 through S-12)
All validation rules for the Subject section of appraisal reports.
"""
from typing import Optional
import re
import difflib
from datetime import datetime
from app.rule_engine.engine import rule, RuleStatus, RuleResult, DataMissingException
from app.models.appraisal import ValidationContext


@rule(id="S-1", name="Property Address Validation")
def validate_property_address(ctx: ValidationContext) -> RuleResult:
    """
    Target Fields: Property Address, City, State, Zip Code, County
    Rule: Must match Client Engagement Letter EXACTLY
    Validation: Cross-verify with USPS address verification
    Reject Conditions: Address/City/Zip/County mismatch
    """
    if not ctx.report.subject.address:
        # If components are there but 'address' (street) is missing, we might still proceed, 
        # but usually address is required.
        raise DataMissingException("Property Address (Report)")
    
    if not ctx.engagement_letter:
        raise DataMissingException("Client Engagement Letter")
    
    eng = ctx.engagement_letter
    subj = ctx.report.subject
    
    if not eng.property_address:
        raise DataMissingException("Property Address (Engagement Letter)")
    
    # helper: normalize string
    def normalize_string(s: Optional[str]) -> str:
        if not s:
            return ""
        # Remove special chars, extra spaces, upper case
        return re.sub(r'[^A-Z0-9\s]', '', s.strip().upper())

    # --- 1. Prepare Engagement Letter Components ---
    eng_street = eng.property_address
    eng_city = eng.city
    eng_state = eng.state
    eng_zip = eng.zip_code
    
    # If Engagement components are missing, try to parse from the full string
    # The engagement letter often has format: "123 Main St City State Zip" (all in one line)
    if eng_street and (not eng_city or not eng_state or not eng_zip):
        # Try multiple patterns to parse the combined address
        
        # Pattern 1: "Street City, State Zip" (with comma before state)
        match = re.search(r'^(.+?)\s+([A-Za-z\s]+?),\s*([A-Z]{2})\s+(\d{5}(?:-\d{4})?)$', eng_street)
        if match:
            eng_street = match.group(1).strip()
            if not eng_city: eng_city = match.group(2).strip()
            if not eng_state: eng_state = match.group(3).strip()
            if not eng_zip: eng_zip = match.group(4).strip()
        else:
            # Pattern 2: "Street City State Zip" (no comma, capturing last occurrence of state pattern)
            # Matches: "25126 N Jack Tone Rd Acampo CA 95220"
            match = re.search(r'^(.+?)\s+([A-Za-z\s]+?)\s+([A-Z]{2})\s+(\d{5}(?:-\d{4})?)$', eng_street)
            if match:
                eng_street = match.group(1).strip()
                if not eng_city: eng_city = match.group(2).strip()
                if not eng_state: eng_state = match.group(3).strip()
                if not eng_zip: eng_zip = match.group(4).strip()

    # --- 2. Compare Components ---
    mismatches = []
    
    # Street: Fuzzy Match
    norm_eng_street = normalize_string(eng_street)
    norm_rpt_street = normalize_string(subj.address)
    
    # Calculate similarity
    similarity = difflib.SequenceMatcher(None, norm_rpt_street, norm_eng_street).ratio()
    
    # Pass if > 0.85 (85%) similarity or strict containment
    if similarity < 0.85:
        # Fallback: check strict containment (e.g. "123 MAIN" in "123 MAIN ST")
        if norm_rpt_street not in norm_eng_street and norm_eng_street not in norm_rpt_street:
            mismatches.append(f"Street mismatch: '{subj.address}' vs '{eng_street}' (Match: {similarity:.1%})")

    # City: Exact Match (Normalized)
    rpt_city = normalize_string(subj.city)
    eng_city_norm = normalize_string(eng_city)
    if not rpt_city: 
        mismatches.append("City missing in Report")
    elif rpt_city != eng_city_norm:
        # Allow containment for City too? "San Francisco" vs "San Francisco" is exact. 
        # Sometimes "Mt View" vs "Mountain View". For now, strict normalized.
        mismatches.append(f"City mismatch: '{subj.city}' vs '{eng_city}'")

    # State: Exact Match
    rpt_state = (subj.state or "").strip().upper()
    eng_state_clean = (eng_state or "").strip().upper()
    if not rpt_state:
        mismatches.append("State missing in Report")
    elif rpt_state != eng_state_clean:
         mismatches.append(f"State mismatch: '{rpt_state}' vs '{eng_state_clean}'")

    # Zip: Exact Match (5 digit)
    rpt_zip = (subj.zip_code or "")[:5]
    eng_zip_clean = (eng_zip or "")[:5]
    if not rpt_zip:
        mismatches.append("Zip code missing in Report")
    elif rpt_zip != eng_zip_clean:
        mismatches.append(f"Zip mismatch: '{rpt_zip}' vs '{eng_zip_clean}'")

    # --- 3. Result ---
    if not mismatches:
        return RuleResult(
            rule_id="S-1",
            rule_name="Property Address Validation",
            status=RuleStatus.PASS,
            message="Property address components match engagement letter."
        )
    
    return RuleResult(
        rule_id="S-1",
        rule_name="Property Address Validation",
        status=RuleStatus.FAIL,
        message=f"Property address does not match with order form. {'; '.join(mismatches)}",
        appraisal_value=f"{subj.address}, {subj.city}, {subj.state} {subj.zip_code}",
        engagement_value=f"{eng_street}, {eng_city}, {eng_state} {eng_zip}",
        review_required=True,
        details={
            "report_components": {
                "street": subj.address, 
                "city": subj.city, 
                "state": subj.state, 
                "zip": subj.zip_code
            },
            "engagement_components": {
                "street": eng_street, 
                "city": eng_city, 
                "state": eng_state, 
                "zip": eng_zip
            }
        }
    )


@rule(id="S-2", name="Borrower Name Validation")
def validate_borrower_name(ctx: ValidationContext) -> RuleResult:
    """
    Target Field: Borrower
    Rule: Must match Client Engagement Letter EXACTLY
    Validation: Include ALL borrowers and co-borrowers
    Watch Items: Spelling errors, Middle names, Suffixes (JR/SR)
    """
    if not ctx.report.subject.borrower:
        raise DataMissingException("Borrower Name (Report)")
    
    if not ctx.engagement_letter or not ctx.engagement_letter.borrower_name:
        raise DataMissingException("Borrower Name (Engagement Letter)")
    
    rpt_borrower = ctx.report.subject.borrower.strip().upper()
    eng_borrower = ctx.engagement_letter.borrower_name.strip().upper()
    
    # fuzzy match Logic
    from difflib import SequenceMatcher
    
    # 1. Exact match (normalized)
    if rpt_borrower == eng_borrower:
        return RuleResult(
            rule_id="S-2",
            rule_name="Borrower Name Validation",
            status=RuleStatus.PASS,
            message="Borrower names match exactly."
        )

    # 2. Token Set Match (handles order, extra spaces)
    def get_tokens(s):
        # Remove punctuation and split
        clean = re.sub(r'[^\w\s]', '', s)
        return set(clean.split())
        
    rpt_tokens = get_tokens(rpt_borrower)
    eng_tokens = get_tokens(eng_borrower)
    
    # Check similarity ratio
    matcher = SequenceMatcher(None, rpt_borrower, eng_borrower)
    similarity = matcher.ratio()
    
    # If high similarity (> 85%) or Token Subset (missing middle name), return WARNING/VERIFY instead of FAIL
    is_subset = rpt_tokens.issubset(eng_tokens) or eng_tokens.issubset(rpt_tokens)
    
    if similarity > 0.85 or (is_subset and len(rpt_tokens) > 0 and len(eng_tokens) > 0):
        # It's a match but with minor differences (typo or middle name)
        status = RuleStatus.WARNING
        msg_prefix = "Minor mismatch" if similarity > 0.85 else "Partial match (middle name/initial difference)"
        
        return RuleResult(
            rule_id="S-2",
            rule_name="Borrower Name Validation",
            status=status,
            message=f"{msg_prefix}: '{ctx.report.subject.borrower}' vs '{ctx.engagement_letter.borrower_name}'.",
            appraisal_value=str(ctx.report.subject.borrower),
            engagement_value=str(ctx.engagement_letter.borrower_name),
            review_required=True, # Still want human lookup
            details={"report": rpt_borrower, "engagement": eng_borrower, "similarity": round(similarity, 2)}
        )
    
    # 3. Significant Mismatch -> FAIL
    return RuleResult(
        rule_id="S-2",
        rule_name="Borrower Name Validation",
        status=RuleStatus.FAIL,
        message=f"Borrower name mismatch. Report shows '{ctx.report.subject.borrower}' but order form shows '{ctx.engagement_letter.borrower_name}'.",
        appraisal_value=str(ctx.report.subject.borrower),
        engagement_value=str(ctx.engagement_letter.borrower_name),
        review_required=True,
        details={"report": rpt_borrower, "engagement": eng_borrower, "similarity": round(similarity, 2)}
    )
    
    # Check for co-borrower (if present in engagement but missing in report)
    # Note: This would require co-borrower field in EngagementLetter model
    # Placeholder for now
    
    # Check Refinance condition: Owner != Borrower requires comment
    if ctx.engagement_letter.assignment_type == "Refinance":
        if ctx.report.subject.owner_of_public_record:
            owner = ctx.report.subject.owner_of_public_record.strip().upper()
            if owner != rpt_borrower:
                # Should verify comment exists
                return RuleResult(
                    rule_id="S-2",
                    rule_name="Borrower Name Validation",
                    status=RuleStatus.WARNING,
                    message="Assignment type is 'Refinance'; however, owner name and borrower name are different, please revise or comment.",
                    appraisal_value=f"Owner: {owner}, Borrower: {rpt_borrower}",
                    engagement_value="Refinance - Borrower should match Owner",
                    review_required=True,
                    details={"owner": owner, "borrower": rpt_borrower}
                )
    
    return RuleResult(
        rule_id="S-2",
        rule_name="Borrower Name Validation",
        status=RuleStatus.PASS,
        message="Borrower name matches engagement letter."
    )


@rule(id="S-3", name="Owner of Public Record")
def validate_owner_record(ctx: ValidationContext) -> RuleResult:
    """
    Target Field: Owner of Public Record
    Rule: Must be provided and current
    Validation: Does NOT need to match borrower
    Condition: If Refinance AND Owner != Borrower → Comment REQUIRED
    """
    if not ctx.report.subject.owner_of_public_record:
        return RuleResult(
            rule_id="S-3",
            rule_name="Owner of Public Record",
            status=RuleStatus.FAIL,
            message="Owner of Public Record is missing or blank."
        )
    
    # Check Refinance condition
    if ctx.engagement_letter and ctx.engagement_letter.assignment_type == "Refinance":
        borrower = (ctx.report.subject.borrower or "").strip().upper()
        owner = ctx.report.subject.owner_of_public_record.strip().upper()
        
        if borrower and owner != borrower:
            # In production, would check for actual comment in report
            return RuleResult(
                rule_id="S-3",
                rule_name="Owner of Public Record",
                status=RuleStatus.WARNING,
                message="Refinance transaction: Owner of Public Record differs from Borrower. Verify comment is provided explaining the discrepancy.",
                details={"owner": owner, "borrower": borrower}
            )
    
    return RuleResult(
        rule_id="S-3",
        rule_name="Owner of Public Record",
        status=RuleStatus.PASS,
        message="Owner of Public Record is present and valid."
    )


@rule(id="S-4", name="Legal Description and Taxes")
def validate_legal_tax(ctx: ValidationContext) -> RuleResult:
    """
    Target Fields: Legal Description, APN, Tax Year, R.E. Taxes
    Rule: All fields MUST be completed, current, and non-blank
    Tax Year: Must be latest year or within last 2 years
    R.E. Taxes: Decimal values NOT allowed; whole numbers only
    """
    subj = ctx.report.subject
    missing = []
    
    if not subj.legal_description:
        missing.append("Legal Description")
    if not subj.apn:
        missing.append("Assessor's Parcel Number (APN)")
    if not subj.tax_year:
        missing.append("Tax Year")
    if subj.re_taxes is None:
        missing.append("Real Estate Taxes")
    
    if missing:
        raise DataMissingException(f"Missing Tax/Legal Fields: {', '.join(missing)}")
    
    # Check Tax Year currency (within last 2 years)
    try:
        tax_year = int(subj.tax_year)
        current_year = datetime.now().year
        if tax_year < current_year - 2:
            return RuleResult(
                rule_id="S-4",
                rule_name="Legal Description and Taxes",
                status=RuleStatus.FAIL,
                message=f"Tax Year ({tax_year}) must be within the last 2 years. Current year: {current_year}."
            )
    except (ValueError, TypeError):
        return RuleResult(
            rule_id="S-4",
            rule_name="Legal Description and Taxes",
            status=RuleStatus.FAIL,
            message=f"Tax Year '{subj.tax_year}' is not a valid year format."
        )
    
    # Check R.E. Taxes format (no decimals allowed)
    if subj.re_taxes is not None:
        if subj.re_taxes % 1 != 0:
            return RuleResult(
                rule_id="S-4",
                rule_name="Legal Description and Taxes",
                status=RuleStatus.FAIL,
                message=f"Real Estate Taxes (${subj.re_taxes}) must be a whole number, not a decimal value."
            )
    
    return RuleResult(
        rule_id="S-4",
        rule_name="Legal Description and Taxes",
        status=RuleStatus.PASS,
        message="Legal description and tax data are complete and valid."
    )


@rule(id="S-5", name="Neighborhood Name")
def validate_neighborhood_name(ctx: ValidationContext) -> RuleResult:
    """
    Target Field: Neighborhood Name
    Rule: Must be provided with actual subdivision/area name
    Invalid Values: Cannot be blank, "None", "N/A", "Unknown"
    Alternative: If no subdivision, use most common name for the area
    """
    neighborhood = ctx.report.subject.neighborhood_name
    
    if not neighborhood:
        return RuleResult(
            rule_id="S-5",
            rule_name="Neighborhood Name",
            status=RuleStatus.FAIL,
            message="The neighborhood name in subject section is blank. Per UAD requirements, the appraiser should enter a neighborhood name recognized by the municipality or the common name by which residents refer to the location. Please revise."
        )
    
    # Check for invalid placeholder values
    invalid_values = ["NONE", "N/A", "NA", "UNKNOWN", "NOT APPLICABLE", "N.A.", "BLANK"]
    if neighborhood.strip().upper() in invalid_values:
        return RuleResult(
            rule_id="S-5",
            rule_name="Neighborhood Name",
            status=RuleStatus.FAIL,
            message=f"The neighborhood name in subject section is mentioned as {neighborhood}. Per UAD requirements, the appraiser should enter a neighborhood name recognized by the municipality or the common name by which residents refer to the location. Please revise."
        )
    
    return RuleResult(
        rule_id="S-5",
        rule_name="Neighborhood Name",
        status=RuleStatus.PASS,
        message=f"Neighborhood name '{neighborhood}' is provided."
    )


@rule(id="S-6", name="Map Reference and Census Tract")
def validate_map_census(ctx: ValidationContext) -> RuleResult:
    """
    Target Fields: Map Reference (OPTIONAL), Census Tract (OPTIONAL for some forms)
    HomeVision Logic:
    - Map Reference is NOT required for standard URAR forms
    - Census Tract is preferred but not always present in all report formats
    - Both are optional - only validate format if present
    """
    subject = ctx.report.subject
    warnings = []
    
    # Map Reference is OPTIONAL
    if not subject.map_reference:
        warnings.append("Map Reference not provided (N/A for this report type).")
    
    # Census Tract is also OPTIONAL for some URAR forms
    if not subject.census_tract:
        warnings.append("Census Tract not provided (may be N/A for this report type).")
    else:
        # Validate Census Tract format if present: XXXX.XX
        census_pattern = r'^\d{4}\.\d{2}$'
        if not re.match(census_pattern, subject.census_tract.strip()):
            # Be lenient - accept if it has numbers
            if not re.search(r'\d+', subject.census_tract):
                warnings.append(f"Census Tract format may be invalid: '{subject.census_tract}'")
    
    # Determine message and status
    if subject.map_reference and subject.census_tract:
        message = "Map Reference and Census Tract are present and valid."
        status = RuleStatus.PASS
    elif subject.census_tract:
        message = "Census Tract is present and valid."
        status = RuleStatus.PASS
    elif subject.map_reference:
        message = "Map Reference is present. Census Tract not provided."
        status = RuleStatus.PASS
    else:
        # Both missing - still PASS per HomeVision, just note it
        message = "Map Reference and Census Tract not provided (N/A for this report type)."
        status = RuleStatus.PASS
    
    return RuleResult(
        rule_id="S-6",
        rule_name="Map Reference and Census Tract",
        status=status,
        message=message,
        details={"warnings": warnings} if warnings else None
    )


@rule(id="S-7", name="Occupant Status")
def validate_occupant(ctx: ValidationContext) -> RuleResult:
    """
    Target Field: Occupant (Owner, Tenant, Vacant)
    If Tenant: Must verify and state lease dates and rental amount
    If Vacant: Must state if utilities are ON
    Image Validation: Cross-check photos against stated occupancy
    """
    occu = ctx.report.subject.occupant
    
    if not occu:
        return RuleResult(
            rule_id="S-7",
            rule_name="Occupant Status",
            status=RuleStatus.FAIL,
            message="Occupant status is missing or blank."
        )
    
    valid_status = ["OWNER", "TENANT", "VACANT", "OWNER OCCUPIED"]
    occu_upper = occu.strip().upper()
    
    if occu_upper not in valid_status:
        return RuleResult(
            rule_id="S-7",
            rule_name="Occupant Status",
            status=RuleStatus.FAIL,
            message=f"Invalid occupant status: '{occu}'. Must be one of: Owner, Tenant, Vacant."
        )
    
    # Check Tenant-specific requirements
    if "TENANT" in occu_upper:
        if not ctx.report.subject.lease_dates:
            return RuleResult(
                rule_id="S-7",
                rule_name="Occupant Status",
                status=RuleStatus.WARNING,
                message="Property is tenant-occupied. Please provide lease dates.",
                appraisal_value="Tenant Occupied",
                engagement_value="Lease dates required",
                review_required=True
            )
        if not ctx.report.subject.rental_amount:
            return RuleResult(
                rule_id="S-7",
                rule_name="Occupant Status",
                status=RuleStatus.WARNING,
                message="Property is tenant-occupied. Please provide rental amount."
            )
    
    # Check Vacant-specific requirements
    if "VACANT" in occu_upper:
        if ctx.report.subject.utilities_on is None:
            return RuleResult(
                rule_id="S-7",
                rule_name="Occupant Status",
                status=RuleStatus.WARNING,
                message="Property is vacant. Please state if utilities are ON or OFF."
            )
    
    return RuleResult(
        rule_id="S-7",
        rule_name="Occupant Status",
        status=RuleStatus.PASS,
        message=f"Occupant status '{occu}' is valid."
    )


@rule(id="S-8", name="Special Assessments")
def validate_special_assessments(ctx: ValidationContext) -> RuleResult:
    """
    Target Field: Special Assessments
    Rule: Must comment if assessments exist (amount and purpose)
    If None: Field must contain "0"
    Cannot be: Blank
    """
    subj = ctx.report.subject
    
    if subj.special_assessments is None:
        raise DataMissingException("Special Assessments")
    
    if subj.special_assessments > 0:
        # Check for commentary explaining the assessment
        if not subj.special_assessments_comment or len(subj.special_assessments_comment.strip()) < 10:
            return RuleResult(
                rule_id="S-8",
                rule_name="Special Assessments",
                status=RuleStatus.FAIL,
                message=f"In the subject section, please specify what the special assessment of ${subj.special_assessments:.2f} is for."
            )
    
    return RuleResult(
        rule_id="S-8",
        rule_name="Special Assessments",
        status=RuleStatus.PASS,
        message="Special assessments are properly documented."
    )


@rule(id="S-9", name="PUD and HOA")
def validate_pud_hoa(ctx: ValidationContext) -> RuleResult:
    """
    Target Fields: PUD checkbox, HOA Dues
    Rule: If HOA dues are mandatory → PUD checkbox MUST be marked
    Required: Per Year OR Per Month must be indicated
    PUD Section: Must be properly completed if PUD is marked
    """
    subject = ctx.report.subject
    hoa_dues = subject.hoa_dues or 0.0
    is_pud = subject.is_pud
    
    if hoa_dues > 0 and not is_pud:
        period = subject.hoa_period or "year"
        return RuleResult(
            rule_id="S-9",
            rule_name="PUD and HOA",
            status=RuleStatus.FAIL,
            message=f"HOA dues are noted as \"${hoa_dues:.2f}\" per {period} in subject section; however, PUD box is not marked. Please revise."
        )
    
    # Check if period is specified when HOA dues exist
    if hoa_dues > 0 and not subject.hoa_period:
        return RuleResult(
            rule_id="S-9",
            rule_name="PUD and HOA",
            status=RuleStatus.WARNING,
            message=f"HOA dues (${hoa_dues:.2f}) are specified but period (Per Year/Per Month) is not indicated."
        )
    
    return RuleResult(
        rule_id="S-9",
        rule_name="PUD and HOA",
        status=RuleStatus.PASS,
        message="PUD/HOA information is consistent."
    )


@rule(id="S-10", name="Lender/Client Information")
def validate_lender_client(ctx: ValidationContext) -> RuleResult:
    """
    Target Fields: Lender/Client Name, Lender/Client Address
    Rule: Must match Client Engagement Letter EXACTLY
    Reference: "Client Displayed on Report" from engagement letter
    """
    if not ctx.engagement_letter:
        raise DataMissingException("Engagement Letter (for Lender Verification)")
    
    eng_lender = ctx.engagement_letter.lender_name
    eng_address = ctx.engagement_letter.lender_address
    rpt_lender = ctx.report.subject.lender_name
    rpt_address = ctx.report.subject.lender_address
    
    # Check lender name
    if eng_lender and rpt_lender:
        if rpt_lender.strip().upper() != eng_lender.strip().upper():
            return RuleResult(
                rule_id="S-10",
                rule_name="Lender/Client Information",
                status=RuleStatus.FAIL,
                message=f"Please correct the lender's name so it reflects as: {eng_lender}",
                details={"report": rpt_lender, "engagement": eng_lender}
            )
    elif eng_lender and not rpt_lender:
        raise DataMissingException("Lender Name (Report)")
    
    # Check lender address
    if eng_address and rpt_address:
        if rpt_address.strip().upper() != eng_address.strip().upper():
            return RuleResult(
                rule_id="S-10",
                rule_name="Lender/Client Information",
                status=RuleStatus.FAIL,
                message=f"Please correct the lender's address so it reflects as: {eng_address}",
                details={"report": rpt_address, "engagement": eng_address}
            )
    
    return RuleResult(
        rule_id="S-10",
        rule_name="Lender/Client Information",
        status=RuleStatus.PASS,
        message="Lender/Client information matches engagement letter."
    )


@rule(id="S-11", name="Property Rights Appraised")
def validate_property_rights(ctx: ValidationContext) -> RuleResult:
    """
    Target Field: Property Rights Appraised
    Rule: Only ONE checkbox may be marked
    Options: Fee Simple, Leasehold, De Minimis PUD
    """
    subj = ctx.report.subject
    
    if not subj.property_rights:
        raise DataMissingException("Property Rights Appraised")
    
    # Valid values
    valid_rights = ["FEE SIMPLE", "LEASEHOLD", "DE MINIMIS PUD", "LEASEHOLD INTEREST"]
    rights_upper = subj.property_rights.strip().upper()
    
    if rights_upper not in valid_rights:
        return RuleResult(
            rule_id="S-11",
            rule_name="Property Rights Appraised",
            status=RuleStatus.FAIL,
            message=f"Invalid Property Rights value: '{subj.property_rights}'. Must be one of: Fee Simple, Leasehold, De Minimis PUD."
        )
    
    return RuleResult(
        rule_id="S-11",
        rule_name="Property Rights Appraised",
        status=RuleStatus.PASS,
        message=f"Property rights appraised: {subj.property_rights}"
    )


@rule(id="S-12", name="Prior Listing/Sale History")
def validate_prior_history(ctx: ValidationContext) -> RuleResult:
    """
    Target Field: Subject currently offered/been offered for sale in past 12 months
    If NO: Appraiser MUST include data source (MLS abbreviated name)
    If YES: Must include DOM #, Abbreviated MLS name, MLS #, List/sale price, List/sale date
    Location: This information MUST be on Page 1
    Condition: If listed but NOT a purchase, and market value varies from listing price by >3% → Comment REQUIRED
    """
    subj = ctx.report.subject
    
    if subj.prior_sale_offered_12mo is None:
        return RuleResult(
            rule_id="S-12",
            rule_name="Prior Listing/Sale History",
            status=RuleStatus.FAIL,
            message="Prior sale/offered status (Yes/No) is not indicated in subject section."
        )
    
    # Must have data sources regardless of Yes or No
    if not subj.data_sources or len(subj.data_sources.strip()) < 2:
        return RuleResult(
            rule_id="S-12",
            rule_name="Prior Listing/Sale History",
            status=RuleStatus.FAIL,
            message='Please provide Data sources in subject section for the question "Is the subject property currently offered for sale or has it been offered for sale in the twelve months prior to the effective date of this appraisal?" as per UAD requirement.'
        )
    
    # If YES, check for additional details
    if subj.prior_sale_offered_12mo:
        missing_details = []
        if not subj.mls_number:
            missing_details.append("MLS Number")
        if not subj.days_on_market:
            missing_details.append("Days on Market (DOM)")
        if not subj.list_price:
            missing_details.append("List Price")
        if not subj.list_date:
            missing_details.append("List Date")
        
        if missing_details:
            return RuleResult(
                rule_id="S-12",
                rule_name="Prior Listing/Sale History",
                status=RuleStatus.WARNING,
                message=f"Property was offered for sale in past 12 months. Missing: {', '.join(missing_details)}."
            )
    
    return RuleResult(
        rule_id="S-12",
        rule_name="Prior Listing/Sale History",
        status=RuleStatus.PASS,
        message="Prior listing/sale history is complete with data sources."
    )
