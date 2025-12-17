# Appraisal QC Checklist - OPUS Rules Documentation

> **Purpose**: This document provides a comprehensive, detailed understanding of all Quality Control (QC) rules for mortgage appraisal reports. It is designed to be the definitive reference for automated QC systems leveraging AI, OCR, NLP, and image processing technologies similar to HomeVision software.

---

## Table of Contents

1. [Overview](#overview)
2. [Document Processing & Automation Framework](#document-processing--automation-framework)
3. [Subject Section Rules](#subject-section-rules)
4. [Contract Section Rules](#contract-section-rules)
5. [Neighborhood Section Rules](#neighborhood-section-rules)
6. [Site Section Rules](#site-section-rules)
7. [Improvement Section Rules](#improvement-section-rules)
8. [Sales Comparison Approach Rules](#sales-comparison-approach-rules)
9. [Reconciliation Section Rules](#reconciliation-section-rules)
10. [Cost Approach Rules](#cost-approach-rules)
11. [Income Approach Rules](#income-approach-rules)
12. [Addendum & Commentary Rules](#addendum--commentary-rules)
13. [Photograph & Image Processing Rules](#photograph--image-processing-rules)
14. [Floor Plan Sketch Rules](#floor-plan-sketch-rules)
15. [Maps Section Rules](#maps-section-rules)
16. [Additional Documentation Rules](#additional-documentation-rules)
17. [FHA Assignment Requirements](#fha-assignment-requirements)
18. [USDA Loan Requirements](#usda-loan-requirements)
19. [Multi-Family / 1007-216 Form Rules](#multi-family--1007-216-form-rules)
20. [Signature Page Rules](#signature-page-rules)
21. [Image Annotation & AI Processing Guidelines](#image-annotation--ai-processing-guidelines)

---

## Overview

This QC checklist covers quality control validation for residential mortgage appraisal reports. The rules are designed to ensure compliance with:

- **UAD (Uniform Appraisal Dataset)** requirements
- **FNMA (Fannie Mae)** guidelines
- **FHA/HUD** requirements (when applicable)
- **USDA** requirements (when applicable)
- **USPAP (Uniform Standards of Professional Appraisal Practice)** standards

### Report Types Covered

| Form Type | Description | Applicable Loan Types |
|-----------|-------------|----------------------|
| 1004 | Single Family Residential Appraisal Report | Conventional, FHA, USDA |
| 1073 | Individual Condominium Unit Appraisal Report | Site Condos (FHA Required) |
| 1004MC | Market Conditions Addendum | FHA/USDA (Required), Conventional (Optional) |
| 1007 | Single Family Comparable Rent Schedule | Investment Properties |
| 216 | Operating Income Statement | Investment Properties |

---

## Document Processing & Automation Framework

> [!IMPORTANT]
> This section defines how AI, OCR, NLP, and machine learning technologies should be applied to automate and enhance QC validation, inspired by HomeVision appraisal software capabilities.

### OCR (Optical Character Recognition) Processing

**Target Documents for OCR:**
- Appraisal report pages (PDF/XML)
- Client Engagement Letters
- Purchase Agreements/Contracts
- MLS listings data
- Public records/Tax records
- Appraiser licenses

**OCR Extraction Fields:**
| Document | Fields to Extract |
|----------|------------------|
| Engagement Letter | Property address, Borrower name(s), Lender name, Lender address, Transaction type, Loan type |
| Purchase Agreement | Contract price, Contract date, Seller name, Concessions, Personal property items |
| Appraisal Report | All form fields, Commentary sections, Signatures, Dates |

### NLP (Natural Language Processing) Analysis

**Commentary Analysis Targets:**
- Addendum sections for canned/generic commentary detection
- Subject property descriptions
- Neighborhood descriptions
- Market conditions analysis
- Reconciliation statements
- Comparable selection reasoning

**NLP Validation Rules:**
1. **No Canned Commentary**: Detect generic/template text that is not property-specific
2. **Headers Required**: Verify proper section headers exist in addenda
3. **Reasoning Detection**: Confirm "WHY" explanations are provided, not just "WHAT" was done
4. **Consistency Check**: Cross-reference commentary with data fields

### Machine Learning Classification

**Automated Classifications:**
- Property condition ratings (C1-C6) from images
- Quality ratings (Q1-Q6) from images
- Room type identification from interior photos
- Health and safety issue detection
- External obsolescence identification from aerial/street photos

---

## Subject Section Rules

### Rule S-1: Property Address Validation

| Attribute | Details |
|-----------|---------|
| **Target Field** | Property Address, City, State, Zip Code, County |
| **Rule** | Must match Client Engagement Letter EXACTLY |
| **Validation** | Cross-verify with USPS address verification |
| **Condition** | If USPS differs from engagement letter, comment MUST be provided |
| **Reject Conditions** | Address mismatch, City mismatch, Zip code mismatch (first 5 digits), County mismatch |
| **AI/OCR Action** | OCR extract from engagement letter → Compare to report fields → Flag discrepancies |

**Rejection Templates:**
- `Property address does not match with order form.`
- `Property City name does not match with order form.`
- `Property Zip code does not match with order form. (First 5 digits must match)`
- `Property county does not match with order form.`

---

### Rule S-2: Borrower Name Validation

| Attribute | Details |
|-----------|---------|
| **Target Field** | Borrower |
| **Rule** | Must match Client Engagement Letter EXACTLY |
| **Validation** | Include ALL borrowers and co-borrowers |
| **Watch Items** | Spelling errors, Middle names, Suffixes (JR/SR) |
| **Note** | Does NOT need to match Owner of Public Record |
| **Condition** | If Refinance AND Owner of Record ≠ Borrower → Comment REQUIRED |

**Rejection Template:**
- `Please include Co-borrower name _______ as per order form.`
- `Assignment type is 'Refinance'; however, owner name and borrower name are different, please revise or comment.`

---

### Rule S-3: Owner of Public Record

| Attribute | Details |
|-----------|---------|
| **Target Field** | Owner of Public Record |
| **Rule** | Must be provided and current |
| **Validation** | Does NOT need to match borrower |
| **Condition** | If Refinance AND Owner of Record ≠ Borrower → Comment REQUIRED |
| **AI Action** | Cross-reference with county assessor records |

---

### Rule S-4: Legal Description, APN, and Taxes

| Attribute | Details |
|-----------|---------|
| **Target Fields** | Legal Description, Assessor's Parcel #, Tax Year, R.E. Taxes |
| **Rule** | All fields MUST be completed, current, and non-blank |
| **Tax Year** | Must be latest year or within last 2 years |
| **R.E. Taxes** | Decimal values NOT allowed; whole numbers only |
| **AI Action** | Validate against county assessor database |

---

### Rule S-5: Neighborhood Name

| Attribute | Details |
|-----------|---------|
| **Target Field** | Neighborhood Name |
| **Rule** | Must be provided with actual subdivision/area name |
| **Invalid Values** | Cannot be: Blank, "None", "N/A", "Unknown" |
| **Alternative** | If no subdivision, use most common name for the area |

**Rejection Template:**
- `The neighborhood name in subject section is mentioned as N/A. Per UAD requirements, the appraiser should enter a neighborhood name recognized by the municipality or the common name by which residents refer to the location. Please revise.`

---

### Rule S-6: Map Reference and Census Tract

| Attribute | Details |
|-----------|---------|
| **Target Fields** | Map Reference, Census Tract |
| **Rule** | Must be provided and current |
| **Map Reference Format** | Numeric values |
| **Census Tract Format** | Four digits, then 2 digits after decimal (XXXX.XX) |
| **Cannot be** | Blank or missing |

---

### Rule S-7: Occupant Status

| Attribute | Details |
|-----------|---------|
| **Target Field** | Occupant (Owner, Tenant, Vacant) |
| **If Tenant** | Must verify and state lease dates and rental amount |
| **If Vacant** | Must state if utilities are ON |
| **Image Validation** | Cross-check photos against stated occupancy |

**Rejection Templates:**
- `Subject section indicates property is owner occupied; however, photos appear to show property is vacant. Please revise or comment.`
- `Subject section shows occupancy as vacant; however, photos show property appears occupied. Please revise or comment if it is a staged home.`

> [!TIP]
> **AI Image Processing**: Use computer vision to detect occupancy indicators:
> - Personal belongings visible → Occupied
> - Empty rooms, no furniture → Vacant
> - Staged furniture with no personal items → Potentially staged

---

### Rule S-8: Special Assessments

| Attribute | Details |
|-----------|---------|
| **Target Field** | Special Assessments |
| **Rule** | Must comment if assessments exist (amount and purpose) |
| **If None** | Field must contain "0" |
| **Cannot be** | Blank |

**Rejection Template:**
- `In the subject section, please specify what the special assessment of $*** is for.`

---

### Rule S-9: PUD and HOA

| Attribute | Details |
|-----------|---------|
| **Target Fields** | PUD checkbox, HOA Dues |
| **Rule** | If HOA dues are mandatory → PUD checkbox MUST be marked |
| **Required** | Per Year OR Per Month must be indicated |
| **PUD Section** | Must be properly completed if PUD is marked |

**Rejection Template:**
- `HOA dues are noted as "$XXX" per year in subject section; however, PUD box is not marked. Please revise.`

---

### Rule S-10: Lender/Client Information

| Attribute | Details |
|-----------|---------|
| **Target Fields** | Lender/Client Name, Lender/Client Address |
| **Rule** | Must match Client Engagement Letter EXACTLY |
| **Reference** | "Client Displayed on Report" from engagement letter |

**Rejection Templates:**
- `Please correct the lender's name so it reflects as: (name as per order form)`
- `Please correct the lender's address so it reflects as: (address as per order form)`

---

### Rule S-11: Property Rights Appraised

| Attribute | Details |
|-----------|---------|
| **Target Field** | Property Rights Appraised |
| **Rule** | Only ONE checkbox may be marked |
| **Options** | Fee Simple, Leasehold, De Minimis PUD |

---

### Rule S-12: Prior Listing/Sale History

| Attribute | Details |
|-----------|---------|
| **Target Field** | Subject currently offered/been offered for sale in past 12 months |
| **If NO** | Appraiser MUST include data source (MLS abbreviated name) |
| **If YES** | Must include: DOM #, Abbreviated MLS name, MLS #, List/sale price, List/sale date |
| **Location** | This information MUST be on Page 1 |
| **Condition** | If listed but NOT a purchase, and market value varies from listing price by >3% → Comment REQUIRED |

**Rejection Template:**
- `Please provide Data sources in subject section for the question "Is the subject property currently offered for sale or has it been offered for sale in the twelve months prior to the effective date of this appraisal?" as per UAD requirement.`

---

## Contract Section Rules

> [!NOTE]
> Contract Section rules apply ONLY to Purchase Transactions. For Refinance transactions, this entire section must be BLANK.

### Rule C-1: Contract Analysis Requirement

| Attribute | Details |
|-----------|---------|
| **Target Field** | Did/Did Not Analyze Contract checkbox |
| **If Purchase** | Contract MUST be analyzed; section MUST be completed |
| **If Refinance** | Entire contract section MUST be blank |
| **Commentary** | Must show Analysis of Contract, Sale Type, and Results |

**Sale Types to Identify:**
- Arms-Length Transaction
- Non Arms-Length Transaction
- REO Sale
- Short Sale
- Court Ordered Sale

**Rejection Templates:**
- `Assignment is meant for a refinance transaction; per UAD requirements, the contract section should be left blank.`
- `Appraiser must provide detailed reasoning and reconciliation if appraised value varies from contract price.`

---

### Rule C-2: Contract Price and Date

| Attribute | Details |
|-----------|---------|
| **Target Fields** | Contract Price, Date of Contract |
| **Rule** | Must match Purchase Agreement EXACTLY |
| **Contract Date** | Date of LAST signature (fully executed date) |
| **Example** | Seller signs 3/1/2019, Buyer signs 4/2/2019 → Contract Date = 4/2/2019 |

**Rejection Templates:**
- `In contract section, Contract Price noted as $XXX; however, purchase contract shows $YYY. Please verify.`
- `In contract section, Contract Date noted as XX/XX/XXXX; however, purchase contract shows YY/YY/YYYY. Please verify.`

---

### Rule C-3: Owner of Record Data Source

| Attribute | Details |
|-----------|---------|
| **Target Field** | Is the property seller the owner of public record? |
| **Rule** | Must check Yes or No with data source |
| **If No** | Commentary MUST be provided |

**Rejection Template:**
- `Please provide data source for "Is the property seller the owner of public record?" under contract section.`

---

### Rule C-4: Financial Assistance/Concessions

| Attribute | Details |
|-----------|---------|
| **Target Field** | Financial Assistance (loan charges, sale concessions, gift or down payment assistance) |
| **Rule** | Yes or No checkbox MUST be marked |
| **If Yes** | Report total dollar amount and describe items |
| **If No** | Dollar amount field should show "0" |
| **Validation** | Cross-check with Purchase Agreement |

**Rejection Template:**
- `Purchase agreement shows concession as $XXX; however, report shows concession as $YYY. Please verify.`

---

### Rule C-5: Personal Property Analysis

| Attribute | Details |
|-----------|---------|
| **Target** | Concessions Commentary |
| **Rule** | Identify all personal property items from contract |
| **Requirement** | State whether personal property items contribute to value |

---

## Neighborhood Section Rules

### Rule N-1: Neighborhood Characteristics

| Attribute | Details |
|-----------|---------|
| **Target Fields** | Location (Urban/Suburban/Rural), Built-Up (Over 75%/25-75%/Under 25%), Growth (Rapid/Stable/Slow) |
| **Rule** | At least 1 box in each category MUST be checked |
| **Validation** | Built-Up percentage must coincide with Present Land Use |

**Rejection Template:**
- `In the neighborhood section, checkbox is missing for _____, please revise.`

---

### Rule N-2: Housing Trends

| Attribute | Details |
|-----------|---------|
| **Target Fields** | Property Values (Increasing/Stable/Declining), Demand/Supply, Marketing Time |
| **Rule** | Be aware of Characteristics and Land Use |
| **If DECLINING or INCREASING** | Proper directional adjustments REQUIRED in sales grid |
| **Consistency** | Trend must match 1004MC form or specific commentary required |
| **Condition** | If no time adjustments made in increasing/declining market → Commentary REQUIRED |

---

### Rule N-3: One-Unit Housing Price and Age

| Attribute | Details |
|-----------|---------|
| **Target Fields** | Price Low/High/Predominant, Age Low/High/Predominant |
| **Format** | Range must be Low to High |
| **Validation** | Unadjusted sales prices of comparables must fall within ranges |
| **Exception** | If comps outside neighborhood → Comment REQUIRED |
| **Condition** | If Market Value differs from Predominant by >10% → Comment on over/under improvement and marketability impact |

---

### Rule N-4: Present Land Use

| Attribute | Details |
|-----------|---------|
| **Target Field** | Present Land Use percentages |
| **Rule** | Must complete and identify "Other" uses if any percentage given |
| **Cannot be** | Blank, "Vacant" (must be specific) |
| **Validation** | Total MUST equal 100% |
| **If Other** | Description REQUIRED |

**Rejection Template:**
- `The sum of present land use in the neighborhood section should always be 100%. Please verify and revise as needed.`

---

### Rule N-5: Neighborhood Boundaries

| Attribute | Details |
|-----------|---------|
| **Target Field** | Boundaries (North, South, East, West) |
| **Rule** | All four boundaries MUST be described |
| **Format** | Must spell out: "North", "South", "East", "West" |
| **Cannot** | Abbreviate as N, S, E, W |
| **Validation** | Boundaries must be visible on location map |

**Rejection Templates:**
- `____ boundary is missing under Neighborhood Boundaries. Please revise.`
- `Neighborhood Boundaries does not contain boundary delineations. Must be clearly delineated using 'North', 'South', 'East', and 'West'.`

---

### Rule N-6: Neighborhood Description

| Attribute | Details |
|-----------|---------|
| **Target Field** | Neighborhood Description |
| **Rule** | Must be completed with specific area description |
| **NLP Check** | Commentary must be specific to the area, no canned text |

---

### Rule N-7: Market Conditions

| Attribute | Details |
|-----------|---------|
| **Target Field** | Market Conditions |
| **Rule** | Must be completed with actual market analysis |
| **Invalid** | "See 1004MC" is NOT acceptable |
| **Consistency** | Must align with 1004MC form data |

---

## Site Section Rules

### Rule ST-1: Site Dimensions

| Attribute | Details |
|-----------|---------|
| **Target Field** | Dimensions |
| **Rule** | Must list site dimensions (e.g., 50 X 100) |
| **If Irregular** | Plat map MUST be provided with subject clearly marked |

---

### Rule ST-2: Site Area

| Attribute | Details |
|-----------|---------|
| **Target Field** | Area |
| **Rule** | Must include unit designation |
| **If <1 Acre** | Provide in square feet with "sf" |
| **If ≥1 Acre** | Provide in acreage with "ac" |
| **Auto-Calculate** | Form will calculate if dimensions provided |
| **If Acreage with Barn/Outbuildings/Agricultural Zoning** | Comment if subject is a working farm |

---

### Rule ST-3: Site Shape

| Attribute | Details |
|-----------|---------|
| **Target Field** | Shape |
| **Rule** | Must be provided |
| **If Irregular** | Plat map MUST be provided with subject clearly marked |

---

### Rule ST-4: View

| Attribute | Details |
|-----------|---------|
| **Target Field** | View |
| **Rule** | Must be UAD Compliant |
| **Format** | Rating;Factor;Other as needed |
| **Validation** | Must match View field in Sales Comparison grid |

---

### Rule ST-5: Zoning Classification and Compliance

| Attribute | Details |
|-----------|---------|
| **Target Fields** | Zoning Classification, Zoning Description, Zoning Compliance |
| **Compliance Options** | Legal, Legal Non-Conforming, No Zoning, Illegal |
| **Rule** | At least one compliance checkbox MUST be marked |
| **If Legal** | No additional comment needed |
| **If Legal Non-Conforming or No Zoning** | Comment if subject can be rebuilt if destroyed >50% |
| **If Illegal** | HOLD report for escalation |
| **If Non-Conforming** | State why (site size, width, improvement type, illegal use) |

**Rejection Templates:**
- `Zoning Compliance is marked 'No Zoning'. Please comment if the subject can be rebuilt if destroyed.`
- `Zoning Compliance is marked 'Legal Non-Conforming'. Please explain why and if subject can be rebuilt if destroyed over 50%.`

---

### Rule ST-6: Highest and Best Use

| Attribute | Details |
|-----------|---------|
| **Target Field** | Is the subject property's existing use its highest and best use? |
| **Expected** | YES should be marked |
| **If NO** | HOLD report and notify immediately |
| **Requirement** | Highest and Best Use analysis MUST be provided |

---

### Rule ST-7: Utilities and Off-Site Improvements

| Attribute | Details |
|-----------|---------|
| **Target Fields** | Electricity, Gas, Water, Sanitary Sewer, Street, Alley |
| **Rule** | If box is checked, description field CANNOT state "None" or "N/A" |
| **If Private Well/Septic** | Comment if typical for market, if public access possible, and effect on marketability |
| **If Private Street** | Comment on condition and maintenance responsibility |

**Rejection Templates:**
- `Private well and septic system: please comment if it is typical and if having this feature has impact on marketability and value.`
- `Subject has "Private Street"; please comment on condition and who is responsible for the maintenance.`

---

### Rule ST-8: FEMA Flood Hazard Area

| Attribute | Details |
|-----------|---------|
| **Target Fields** | FEMA Special Flood Hazard Area (Yes/No), FEMA Flood Zone, FEMA Map #, FEMA Map Date |
| **If Yes** | Comment on marketability impact |
| **Flood Map** | REQUIRED if subject in flood zone |
| **Comparables** | Comment on which comparables, if any, are in flood zone |

**Rejection Template:**
- `The appraisal indicates the subject property is in a FEMA designated flood zone. Please comment if it will impact the marketability of the Subject.`

---

### Rule ST-9: Utilities Typical for Market

| Attribute | Details |
|-----------|---------|
| **Target Field** | Are the utilities and off-site improvements typical for the market area? |
| **Rule** | Yes or No MUST be checked |
| **If No** | Commentary REQUIRED |

---

### Rule ST-10: Adverse Site Conditions

| Attribute | Details |
|-----------|---------|
| **Target Field** | Adverse site conditions or external factors |
| **Examples** | Easements, Encroachments, Environmental conditions, Land uses |
| **If Yes** | Comment MUST support the response |
| **Adjustments** | Should be reflected in sales grid |
| **External Obsolescence** | If proximity to commercial, traffic street, airport, high-tension wires → Explain marketability impact and provide similar comparables |

---

## Improvement Section Rules

### Rule I-1: General Description

| Attribute | Details |
|-----------|---------|
| **Target Fields** | Units, Stories, Type, Existing/Proposed/Under Construction, Design Style, Year Built, Effective Age |
| **Rule** | All fields must be completed as applicable |

---

### Rule I-2: Foundation

| Attribute | Details |
|-----------|---------|
| **Target Fields** | Concrete Slab, Crawl Space, Full Basement, Partial Basement, Sump Pump, Evidence of Moisture/Settlement |
| **Rule** | All fields must be completed as applicable |
| **Validation** | Must match Sales Comparison grid section |

---

### Rule I-3: Exterior Description

| Attribute | Details |
|-----------|---------|
| **Target Fields** | Foundation Walls, Exterior Walls, Roof Surface, Gutters & Downspouts, Window Type, Storm Sash/Screens |
| **Rule** | All fields must be completed |
| **Validation** | Must match Sales Comparison grid section |

---

### Rule I-4: Interior Description

| Attribute | Details |
|-----------|---------|
| **Target Fields** | Floors, Walls, Trim/Finish, Bath Floor, Bath Wainscot |
| **Rule** | Complete as applicable |
| **Car Storage Rule** | If None checked → All # of cars fields = 0, driveway surface blank |
| **Note** | Car storage should NOT be "None" if subject has a driveway |

---

### Rule I-5: Utilities

| Attribute | Details |
|-----------|---------|
| **Target Field** | Utilities status |
| **Rule** | Must state if utilities were ON at time of inspection |

---

### Rule I-6: Appliances

| Attribute | Details |
|-----------|---------|
| **Target Field** | Built-in Appliances |
| **Rule** | Note ONLY built-in items |
| **FHA Requirement** | Appraiser MUST operate built-in appliances and provide statement on operational status |

---

### Rule I-7: Above Grade Room Count

| Attribute | Details |
|-----------|---------|
| **Target Field** | Above Grade Contains (Total Rooms, Bedrooms, Baths, GLA) |
| **Rule** | Partially or fully below-grade areas MUST be excluded |
| **Below Grade Beds/Baths** | Must NOT be included in above grade count |
| **Validation** | Must match Sales Comparison grid section |

---

### Rule I-8: Additional Features

| Attribute | Details |
|-----------|---------|
| **Target Field** | Additional features |
| **Rule** | List energy efficient items if any |
| **If None** | State "NONE" |

---

### Rule I-9: Property Condition Rating

| Attribute | Details |
|-----------|---------|
| **Target Field** | Condition of the Property |
| **Rule** | Must be UAD Compliant (C1-C6) |
| **Validation** | Must match photos, commentary, and be supported by effective age |

**UAD Condition Ratings:**
| Rating | Description |
|--------|-------------|
| C1 | Brand new, never occupied |
| C2 | Recently built or renovated, minimal wear |
| C3 | Well-maintained, limited deferred maintenance |
| C4 | Adequately maintained, some deferred maintenance |
| C5 | Obvious deferred maintenance, some items affecting livability |
| C6 | Substantial damage or deferred maintenance, major repairs needed |

> [!TIP]
> **AI Image Processing**: Computer vision should analyze interior/exterior photos to:
> - Detect visible deferred maintenance
> - Identify condition inconsistencies with reported rating
> - Flag C5/C6 indicators like peeling paint, damaged fixtures, structural issues

---

### Rule I-10: Adverse Conditions Affecting Livability

| Attribute | Details |
|-----------|---------|
| **Target Field** | Adverse conditions affecting livability |
| **If Yes Checked** | Verify items actually affect livability; may be typo requiring correction |

---

### Rule I-11: Neighborhood Conformity

| Attribute | Details |
|-----------|---------|
| **Target Field** | Does property conform to neighborhood? |
| **Rule** | Yes or No must be checked |
| **If No** | Extensive commentary REQUIRED |
| **Commentary Must Address** | Why doesn't it conform? Can it be rebuilt if destroyed >50%? Is it overbuilt? |

---

### Rule I-12: Additions to Subject

| Attribute | Details |
|-----------|---------|
| **Target** | Additions detected |
| **Required Commentary** | 1. Is addition permitted? 2. Does addition conform to original structure in quality and functional utility? 3. Marketability impact and zoning compliance |
| **If Health/Safety Issue** | Appraisal must be "Subject To" remediation or removal with cost to cure |

---

### Rule I-13: Security Bars

| Attribute | Details |
|-----------|---------|
| **Target** | Security bars on windows |
| **Rule** | Potential safety issue |
| **Comment Required** | Safety release latches present? Meets building codes? |
| **If Meets Local Codes** | Acceptable regardless of release latches |

---

## Sales Comparison Approach Rules

### Rule SCA-1: Comparable Market Summary

| Attribute | Details |
|-----------|---------|
| **Target Fields** | # of Comparable Properties Currently Offered, # of Comparable Sales within 12 Months |
| **Rule** | MUST only include competing listings/sales |
| **Validation** | Range must be consistent with comparables provided |
| **Cross-Check** | Must match 1004MC form and Predominant price ranges from Page 1 |

---

### Rule SCA-2: Comparables Required

| Attribute | Details |
|-----------|---------|
| **Value < $1 Million** | Minimum 3 sales + 2 listings |
| **Value ≥ $1 Million** | Minimum 4 sales + 2 listings |
| **Pending Sales** | Do not need to be included in listing count |

---

### Rule SCA-3: Address (Subject and Comparables)

| Attribute | Details |
|-----------|---------|
| **Rule** | Must be UAD Compliant and USPS Verified |
| **Subject Address** | MUST match Page 1 exactly including Zip code |
| **If Subject Address Differs from Engagement Letter** | Comment REQUIRED |

---

### Rule SCA-4: Proximity to Subject

| Attribute | Details |
|-----------|---------|
| **Target Field** | Proximity |
| **Rule** | Must be provided as minimum 0.01 miles with direction |
| **Directions** | N, S, NW, NE, SW, SE, E, W |
| **Even if Same Complex** | Must still provide proximity |
| **If Blank** | Verify location map is provided |

---

### Rule SCA-5: Data Sources

| Attribute | Details |
|-----------|---------|
| **Rule** | Must be UAD Compliant |
| **Format** | Specific MLS name; MLS number; DOM (e.g., MISMLS#3546935;DOM12) |
| **DOM** | Must be provided or "Unk" with commentary |
| **Validation** | DOM for majority of comps should reflect marketing time on Page 1 |
| **If Not Consistent** | Commentary REQUIRED |

---

### Rule SCA-6: Verification Sources

| Attribute | Details |
|-----------|---------|
| **Rule** | At least 1 verification source MUST be provided |
| **Format** | Full specific source name (e.g., "Orange County Assessor Tax Card") |

---

### Rule SCA-7: Sale or Financing Concessions

| Attribute | Details |
|-----------|---------|
| **Rule** | Must be UAD Compliant |
| **Format** | Sale type; Financing type; Concession |
| **Adjustment Direction** | Verify adjustments are in appropriate direction |
| **If No Adjustment for Difference** | Field must contain "0" |

---

### Rule SCA-8: Date of Sale/Time Adjustment

| Attribute | Details |
|-----------|---------|
| **Rule** | Must be UAD Compliant |
| **Format** | Status type; Sale date; Contract date |
| **Validation** | Contract date is ALWAYS before sale date |
| **Housing Trend Awareness** | If increasing/declining market → adjustment REQUIRED in correct direction |
| **Commentary Required** | Contract dates: 90 days, 6 months, over 12 months |

---

### Rule SCA-9: Location Rating

| Attribute | Details |
|-----------|---------|
| **Rule** | Must be UAD Compliant |
| **Format** | Rating;Type;Other (max 2 descriptors, separated by semicolon) |
| **If No Adjustment for Difference** | Grid field must contain "0" |

---

### Rule SCA-10: Leasehold/Fee Simple

| Attribute | Details |
|-----------|---------|
| **Target Field** | Leasehold/Fee Simple |
| **Rule** | Must be provided |
| **If Leasehold** | Similar leasehold comps must be provided |
| **Note** | FNMA and Freddie allow Fee Simple sales |

---

### Rule SCA-11: Site

| Attribute | Details |
|-----------|---------|
| **Rule** | Must include size with proper units |
| **If < 1 Acre** | Provide in SF |
| **If ≥ 1 Acre** | Provide in acreage |
| **If No Adjustment for Difference** | Grid field must contain "0" |

---

### Rule SCA-12: View

| Attribute | Details |
|-----------|---------|
| **Rule** | Must be UAD Compliant |
| **Format** | Rating;Factor;Factor2 (max 2 descriptors, separated by semicolon) |
| **If Waterfront Property** | Report actual frontage in linear feet on extra line item |
| **If No Adjustment for Difference** | Grid field must contain "0" |

---

### Rule SCA-13: Design (Style)

| Attribute | Details |
|-----------|---------|
| **Rule** | Must be UAD Compliant |
| **Format** | Attachment type; # of stories; Design style |
| **Note** | No adjustment needed for style difference only |
| **If No Adjustment for Difference** | Grid field must contain "0" |

---

### Rule SCA-14: Quality of Construction

| Attribute | Details |
|-----------|---------|
| **Rule** | Must be UAD Compliant (Q1-Q6) |
| **If No Adjustment for Difference** | Grid field must contain "0" AND commentary REQUIRED |

**UAD Quality Ratings:**
| Rating | Description |
|--------|-------------|
| Q1 | Unique, custom designed by architect |
| Q2 | Custom quality, upgraded materials |
| Q3 | Improved quality materials and finishes |
| Q4 | Standard/typical construction quality |
| Q5 | Economy construction, minimal features |
| Q6 | Basic quality, below minimum standards |

---

### Rule SCA-15: Actual Age

| Attribute | Details |
|-----------|---------|
| **Rule** | Must be UAD Compliant |
| **Validation** | Verify actual age matches Year Built |
| **If No Adjustment for Difference** | Grid field must contain "0" |

---

### Rule SCA-16: Condition

| Attribute | Details |
|-----------|---------|
| **Rule** | Must be UAD Compliant (C1-C6) |
| **Validation** | Verify condition rating matches photos provided |
| **If No Adjustment for Difference** | Grid field must contain "0" |

---

### Rule SCA-17: Above Grade Room Count and GLA

| Attribute | Details |
|-----------|---------|
| **Rule** | Must be provided |
| **Validation** | All rooms and GLA must match Sketch |

---

### Rule SCA-18: Basement & Finished Rooms Below Grade

| Attribute | Details |
|-----------|---------|
| **Rule** | Must be UAD Compliant with complete exit type |
| **Validation** | Data must match Page 1 |
| **If No Adjustment for Difference** | Grid field must contain "0" |

---

### Rule SCA-19: Functional Utility

| Attribute | Details |
|-----------|---------|
| **Rule** | Appraiser to provide |
| **If No Adjustment for Difference** | Grid field must contain "0" |

---

### Rule SCA-20: Heating/Cooling

| Attribute | Details |
|-----------|---------|
| **Rule** | Must be provided |
| **Validation** | Must match information from Page 1 |

---

### Rule SCA-21: Garage/Carport

| Attribute | Details |
|-----------|---------|
| **Rule** | UAD compliance required |
| **Format** | # of cars and type; description optional |
| **If No Adjustment for Difference** | Grid field must contain "0" |

---

### Rule SCA-22: Porch/Patio/Deck

| Attribute | Details |
|-----------|---------|
| **Rule** | Must be provided |
| **Validation** | Must match Page 1 or note "None" |
| **If No Adjustment for Difference** | Grid field must contain "0" |

---

### Rule SCA-23: Listing Comparables

| Attribute | Details |
|-----------|---------|
| **Rule** | Apply list-to-sales price ratio adjustment OR explain why not warranted |
| **Validation** | Listing must support opinion of value |

---

### Rule SCA-24: Unique Design Properties

| Attribute | Details |
|-----------|---------|
| **Target** | Green homes, Log homes, 1 bedroom, Accessory units, etc. |
| **Rule** | Include similar comparables |
| **If Not Available** | Explain in detail why similar comparables were not available |

---

### Rule SCA-25: New Construction

| Attribute | Details |
|-----------|---------|
| **Rule** | Provide at least one comparable from competing development |
| **Exception** | Dated sale acceptable if necessary |
| **Alternative** | Resales from outside development OR new sales from competing tract |

---

### Rule SCA-26: Square Footage

| Attribute | Details |
|-----------|---------|
| **Rule** | Cannot use below-grade SF in GLA unless necessary |
| **If Below-Grade Included** | Explain why necessary; comparables should reflect same methodology |
| **When Necessary** | All MLS/public records lump above and below grade together |

---

### Rule SCA-27: Comparable Photos

| Attribute | Details |
|-----------|---------|
| **Conventional Loans** | MLS photos acceptable with commentary stating drive-by inspection was conducted |
| **FHA Loans** | Drive-by photos required |

---

## Reconciliation Section Rules

### Rule R-1: Value Reconciliation

| Attribute | Details |
|-----------|---------|
| **Target Field** | Indicated Value by Sales Comparison Approach |
| **Rule** | Must be reconciled with all approaches used |
| **Commentary** | Must explain weight given to each approach |

---

### Rule R-2: Final Opinion of Value

| Attribute | Details |
|-----------|---------|
| **Rule** | Must be clearly stated |
| **Condition** | If differs significantly from contract price → Detailed reconciliation REQUIRED |

---

## Cost Approach Rules

### Rule CA-1: Cost Approach Requirement

| Attribute | Details |
|-----------|---------|
| **USDA Loans** | Cost Approach is REQUIRED for all USDA loans |
| **Other Loans** | May be optional based on client requirements |

---

### Rule CA-2: Cost Approach Completion

| Attribute | Details |
|-----------|---------|
| **Target Fields** | Land Value, Cost New, Depreciation, Indicated Value by Cost Approach |
| **Rule** | All fields must be completed when Cost Approach is required |

---

## Income Approach Rules

### Rule IA-1: Subject Rent Matching

| Attribute | Details |
|-----------|---------|
| **Validation** | Total Gross Monthly Rent in Income Approach must match Subject Rent Schedule on Page 2 |

---

### Rule IA-2: Operating Income Statement (Form 216)

| Attribute | Details |
|-----------|---------|
| **Rule** | Form 216 must be completely filled out when income approach is used |

---

## Addendum & Commentary Rules

### Rule ADD-1: Commentary Standards

| Attribute | Details |
|-----------|---------|
| **Rule** | Must be specific to the report completed |
| **Prohibited** | NO canned/generic commentary |
| **Required** | Headers MUST be used in addendum (Beginning addendum, Comments on sales comparison, etc.) |

---

### Rule ADD-2: Comparable Selection Commentary

| Attribute | Details |
|-----------|---------|
| **Rule** | Must provide detailed reasoning behind comparable selection |
| **Requirement** | Explain WHY, not just WHAT was done |

---

### Rule ADD-3: Dated Sales Commentary

| Attribute | Details |
|-----------|---------|
| **Must Address** | Dated sales, Distant comparables, Comparables crossing major boundaries, Need for various designs/ages/GLA |

---

### Rule ADD-4: Market Conditions Addendum (1004MC)

| Attribute | Details |
|-----------|---------|
| **FHA/USDA** | REQUIRED |
| **Conventional** | Not required |

---

### Rule ADD-5: 1004MC Inventory Analysis

| Attribute | Details |
|-----------|---------|
| **Rule** | All lightly shaded areas REQUIRED or specific comment why not possible |
| **If None** | Required blank spaces = "0" or "N/A" |

---

### Rule ADD-6: 1004MC Comparables Matching

| Attribute | Details |
|-----------|---------|
| **Total # of Comparable Sales** | Must match top of sales grid for neighborhood |
| **Total # of Active Listings** | Must match current offerings at top of sales grid |

---

### Rule ADD-7: 1004MC Overall Trend

| Attribute | Details |
|-----------|---------|
| **Rule** | Mark trends where at least 2 data points exist |
| **If Declining/Increasing** | Apply appropriate market conditions adjustment based on contract dates OR explain why not applicable |

---

### Rule ADD-8: 1004MC Condo/Co-Op

| Attribute | Details |
|-----------|---------|
| **If Subject is Condo/Co-Op** | All lightly shaded areas in this section must be completed, specific to subject's project |

---

### Rule ADD-9: USPAP 2014 Addendum

| Attribute | Details |
|-----------|---------|
| **Appraisal Identification** | Must be completed with only 2 choices: Appraisal Report OR Restricted Appraisal Report |
| **Reasonable Exposure Time** | Must be single point or range (e.g., 90 or 30-60 days) |
| **Additional Certifications** | If "I HAVE performed services" checked → Commentary REQUIRED on prior services |

---

## Photograph & Image Processing Rules

> [!IMPORTANT]
> This section defines comprehensive image requirements and AI-powered processing guidelines for automated quality control and compliance verification.

### Rule PH-1: Required Subject Photos (All Loans)

| Photo Type | Requirement | AI Processing |
|------------|-------------|---------------|
| Front Exterior | REQUIRED | Property identification, Condition assessment, Design style detection |
| Rear Exterior | REQUIRED | Condition assessment, Outbuilding identification |
| Street Scene | REQUIRED | Neighborhood assessment, Location verification |

---

### Rule PH-2: Interior Photos (Interior Inspection Reports)

| Photo Type | Requirement | Labeling |
|------------|-------------|----------|
| Kitchen | REQUIRED | Specific room name |
| Living Room | REQUIRED | Specific room name |
| Dining Room | REQUIRED | Specific room name |
| Family Room | REQUIRED | Specific room name |
| All Bedrooms | REQUIRED | Specific room name (e.g., "Master Bedroom", "Bedroom 2") |
| All Bathrooms | REQUIRED | Specific room name |
| Deferred Maintenance | REQUIRED if present | Description of issue |

---

### Rule PH-3: Additional Subject Photos

| Photo Type | Requirement |
|------------|-------------|
| Outbuildings | REQUIRED for all |
| Outbuilding Interiors | REQUIRED |
| Special Features (pools, etc.) | REQUIRED |
| Deferred Maintenance | REQUIRED if present |
| Exterior Obsolescence | REQUIRED if present |

> [!WARNING]
> Photos containing people or interior personal pictures should be AVOIDED if possible.

---

### Rule PH-4: FHA Specific Photo Requirements

| Photo Type | Requirement |
|------------|-------------|
| Front Exterior | REQUIRED |
| Rear Exterior | REQUIRED |
| Left Side Exterior | REQUIRED |
| Right Side Exterior | REQUIRED |
| Attic | REQUIRED with "Head and Shoulders" inspection comment |
| Crawl Space | REQUIRED with "Head and Shoulders" inspection comment |

---

### Rule PH-5: Comparable Photos

| Loan Type | Requirement |
|-----------|-------------|
| Conventional | MLS photos acceptable with drive-by commentary |
| FHA | Drive-by photos required |

---

### Rule PH-6: Obsolescence Photo Requirements

| Condition | Requirement |
|-----------|-------------|
| External Obsolescence Observed | Sufficient photos with commentary |
| Internal Obsolescence | Photos documenting specific issues |
| Deferred Maintenance | Photos of all affected areas |

---

## Floor Plan Sketch Rules

### Rule SK-1: Sketch Location

| Attribute | Details |
|-----------|---------|
| **Rule** | Must be on Floor Plan Sketch page provided in appraisal software |

---

### Rule SK-2: Floor Coverage

| Attribute | Details |
|-----------|---------|
| **Rule** | Must include ALL floors |

---

### Rule SK-3: Dimensions

| Attribute | Details |
|-----------|---------|
| **Exterior Dimensions** | REQUIRED |
| **All Rooms** | Must be labeled |
| **Room Count** | Must match rooms reported in sales grid |

---

### Rule SK-4: Outbuildings and Structures

| Attribute | Details |
|-----------|---------|
| **Rule** | All structures contributing to value must be on sketch |
| **Includes** | Garages, Outbuildings, Decks, Porches, Patios, Balconies |
| **FHA Additional** | Show covered or uncovered designation |
| **Dimensions** | REQUIRED for all |

---

### Rule SK-5: Area Calculations

| Attribute | Details |
|-----------|---------|
| **Rule** | Must be provided |
| **Location** | Usually at bottom of sketch page |
| **Validation** | Must match GLA in report |

---

## Maps Section Rules

### Rule M-1: Location Map

| Attribute | Details |
|-----------|---------|
| **Rule** | REQUIRED |
| **Content** | Must show subject and ALL comparables |
| **Detail** | Sufficient to identify relative locations |
| **Validation** | Neighborhood boundaries should be visible |

---

### Rule M-2: Aerial Map

| Attribute | Details |
|-----------|---------|
| **Rule** | NOT REQUIRED but recommended |
| **If Provided** | Must display external obsolescence within 2-4 block radius |
| **Commentary** | Any observed obsolescence requires sufficient commentary |

---

### Rule M-3: Plat Map

| Attribute | Details |
|-----------|---------|
| **Rule** | REQUIRED if site dimensions cannot be provided on Page 1 |
| **Content** | Subject must be clearly marked |

---

### Rule M-4: Flood Map

| Attribute | Details |
|-----------|---------|
| **Rule** | REQUIRED if subject is in Flood Zone |

---

## Additional Documentation Rules

### Rule DOC-1: Appraiser License

| Attribute | Details |
|-----------|---------|
| **Rule** | REQUIRED for every report |
| **Validation** | Verify license is current and valid for state |

---

### Rule DOC-2: E&O Insurance

| Attribute | Details |
|-----------|---------|
| **Rule** | NOT required |
| **If Not Included** | No revision needed |

---

### Rule DOC-3: UAD Data Set

| Attribute | Details |
|-----------|---------|
| **Rule** | May be required based on client requirements |

---

### Rule DOC-4: Trainee Signatures

| Attribute | Details |
|-----------|---------|
| **Rule** | Trainees NOT allowed to sign reports |
| **If Not Licensed/Certified** | Report must be returned for correction |

---

## FHA Assignment Requirements

> [!CAUTION]
> FHA assignments have specific additional requirements. Non-compliance will result in report rejection.

### Rule FHA-1: HUD Minimum Property Requirements

| Attribute | Details |
|-----------|---------|
| **Rule** | Property MUST meet minimum HUD guidelines |
| **If Does NOT Meet** | Report MUST be made "Subject To" |
| **Form Requirement** | All Site Condos must be on 1073 form (per HUD directive) |

---

### Rule FHA-2: FHA Case Number

| Attribute | Details |
|-----------|---------|
| **Location** | Upper right hand corner of ALL pages |
| **Format** | XXX-XXXXXXX (10 numbers total with dash between) |
| **Validation** | Must appear on every page of report |

---

### Rule FHA-3: FHA Intended Use and Intended User

| Attribute | Details |
|-----------|---------|
| **Rule** | BOTH statements MUST be included |
| **Intended User Statement** | "The INTENDED USER of this appraisal report is the Lender/Client and HUD/FHA. The Intended Use is to evaluate the property that is the subject of this appraisal for a mortgage finance transaction, subject to the stated Scope of Work, purpose of the appraisal, reporting requirements of this appraisal report form, and Definition of Market Value. No additional Intended Users are identified by the appraiser." |
| **Intended Use Statement** | "The INTENDED USE of this appraisal is to support FHA's decision to provide mortgage insurance on the real property that is the subject of the appraisal." |

---

### Rule FHA-4: FHA Minimum Property Requirements Statement

| Attribute | Details |
|-----------|---------|
| **Rule** | Include statement noting if subject meets FHA MPR per HUD Handbook 4000.1 |
| **If Subject To** | Include statement that property will meet FHA MPR upon completion of repairs |

---

### Rule FHA-5: FHA Comparable Sales Dating

| Attribute | Details |
|-----------|---------|
| **Rule** | Comparables 1, 2, and 3 MUST be within 12 months of effective date |

---

### Rule FHA-6: FHA Repairs

| Attribute | Details |
|-----------|---------|
| **If Beyond Cosmetic Repairs** | Complete appraisal "Subject To" |
| **Note Required Items** | Repairs, Alterations, Inspection conditions |
| **Systems** | Water, Furnace, Electrical, Mechanics must be operational |
| **Cost to Cure** | REQUIRED for all repair items |

---

### Rule FHA-7: Space Heater as Primary Heat

| Attribute | Details |
|-----------|---------|
| **If Primary Heat Source** | Verify and state: Permanently affixed, Can heat/maintain 50°F minimum in all living spaces and spaces with plumbing, Acceptable to local authority |

---

### Rule FHA-8: Security Bars on Windows

| Attribute | Details |
|-----------|---------|
| **Rule** | At least one window in every bedroom must have quick-release latches |
| **Statement Required** | Confirm emergency exit capability |

---

### Rule FHA-9: FHA Photo Requirements

| Attribute | Details |
|-----------|---------|
| **Required Photos** | Front, Rear, Left Side, Right Side (all 4 sides) |

---

### Rule FHA-10: Estimated Remaining Economic Life

| Attribute | Details |
|-----------|---------|
| **Required For** | Single-family, Multi-family, Condominiums |
| **If < 30 Years** | Clearly explain why subject does not meet FHA minimum |

---

### Rule FHA-11: Attic/Crawl Space Inspection

| Attribute | Details |
|-----------|---------|
| **Rule** | Head and Shoulders inspection REQUIRED |
| **Photos** | REQUIRED |
| **Commentary** | Must state inspection was performed |

---

### Rule FHA-12: Well and Septic (FHA)

| Attribute | Details |
|-----------|---------|
| **Rule** | Comment if public water/sewer available for hookup |
| **If Available** | Provide cost to hook up |

---

### Rule FHA-13: FHA Appliances

| Attribute | Details |
|-----------|---------|
| **Rule** | Appraiser MUST operate all built-in appliances |
| **Statement Required** | "Appliances were operational" or "Appliances were NOT operational" |

---

### Rule FHA-14: FHA Sketch Requirements

| Attribute | Details |
|-----------|---------|
| **Additional** | All outbuildings, garages, structures (deck, porch, patio, balcony) must be labeled with dimensions and show covered/uncovered |

---

## USDA Loan Requirements

### Rule USDA-1: Cost Approach

| Attribute | Details |
|-----------|---------|
| **Rule** | Cost Approach is REQUIRED on ALL USDA loans |

---

## Multi-Family / 1007-216 Form Rules

### Rule MF-1: Subject Rent Matching

| Attribute | Details |
|-----------|---------|
| **Validation** | Income Approach Total Gross Monthly Rent must match Subject Rent Schedule on Page 2 |

---

### Rule MF-2: Operating Income Statement (Form 216)

| Attribute | Details |
|-----------|---------|
| **Rule** | Form 216 must be completely filled out |

---

## Signature Page Rules

### Rule SIG-1: Signature Requirements

| Attribute | Details |
|-----------|---------|
| **Target Fields** | Date of Signature, Appraiser Signature |
| **Rule** | Must be completely filled out |

---

### Rule SIG-2: Appraiser Information

| Attribute | Details |
|-----------|---------|
| **Target Fields** | Appraiser Name, Company Name, Company Address, Phone #, Email, State Certification #, State, Expiration Date |
| **Rule** | All fields REQUIRED |

---

### Rule SIG-3: Supervisory Appraiser (If Applicable)

| Attribute | Details |
|-----------|---------|
| **Target Fields** | Supervisory Appraiser Signature, Name, Company details, License info |
| **Inspection Field** | Did/Did Not Inspect Property checkboxes |

---

### Rule SIG-4: Email Address

| Attribute | Details |
|-----------|---------|
| **Rule** | Not required but recommended |

---

## Image Annotation & AI Processing Guidelines

> [!IMPORTANT]
> This section provides comprehensive guidelines for AI-powered image processing and annotation systems to support automated QC validation.

### Image Classification Categories

| Category | AI Detection Target | QC Validation Purpose |
|----------|--------------------|-----------------------|
| Property Exterior | Building type, Design style, Condition indicators | Verify reported design and condition |
| Street Scene | Neighborhood characteristics, External obsolescence | Confirm location and neighborhood quality |
| Interior Rooms | Room type, Condition, Quality, Finishes | Validate room counts and condition ratings |
| Kitchen | Appliances, Countertops, Cabinets, Condition | Quality and condition assessment |
| Bathrooms | Fixtures, Finishes, Condition | Quality and condition assessment |
| Basements | Finished vs Unfinished, Moisture indicators | Validate basement description |
| Attic | Access, Insulation, Condition | FHA compliance |
| Crawl Space | Access, Moisture, Condition | FHA compliance |
| Outbuildings | Type, Size, Condition | Validate reported amenities |
| Deferred Maintenance | Specific issues | Flag for condition rating validation |

### AI-Powered Condition Assessment

**Condition Indicators to Detect:**

| Rating | Visual Indicators |
|--------|-------------------|
| C1/C2 | New materials, No wear, Modern finishes |
| C3 | Minor wear, Well-maintained, Recent updates |
| C4 | Normal wear, Adequate maintenance, Some dated finishes |
| C5 | Visible wear, Deferred maintenance, Outdated systems, Cosmetic issues |
| C6 | Major damage, Structural issues, Safety hazards, Extensive repairs needed |

### Health and Safety Issue Detection

**AI Must Flag:**
- Visible mold or water damage
- Cracked or damaged foundations
- Missing railings on stairs/decks
- Damaged electrical panels or exposed wiring
- Broken windows or doors
- Roof damage visible in photos
- Fire damage indicators
- Structural damage indicators

### Occupancy Detection

**AI Should Analyze:**
- Presence of furniture and personal belongings (Occupied)
- Empty rooms with no furnishings (Vacant)
- Staged furniture without personal items (Staged)
- Utilities status indicators (lights on, displays active)

### External Obsolescence Detection

**AI Should Flag in Aerial/Street Photos:**
- Proximity to commercial properties
- High-traffic road locations
- Power lines or towers nearby
- Industrial facilities in vicinity
- Railroad tracks
- Airports/flight paths
- Landfills or waste facilities
- Flood zones (water proximity)

### Photo Quality Validation

**AI Should Verify:**
- Photo is clear and not blurry
- Subject property is identifiable
- Photo matches reported address (if visible)
- Lighting is adequate
- All required angles are captured

### Annotation Output Format

```json
{
  "photo_id": "string",
  "photo_type": "enum[front, rear, left_side, right_side, street, interior, kitchen, bathroom, etc.]",
  "detected_condition": "enum[C1-C6]",
  "detected_quality": "enum[Q1-Q6]",
  "room_type": "string (if applicable)",
  "issues_detected": [
    {
      "issue_type": "string",
      "severity": "enum[low, medium, high, critical]",
      "location_in_image": "bounding_box",
      "description": "string"
    }
  ],
  "occupancy_indicators": "enum[occupied, vacant, staged, unknown]",
  "external_obsolescence": ["list of detected items"],
  "validation_flags": [
    {
      "field": "string",
      "expected_value": "string",
      "detected_value": "string",
      "match": "boolean"
    }
  ],
  "confidence_score": "float 0-1"
}
```

### Cross-Reference Validation Rules

| Photo Analysis Result | Report Field to Validate | Action if Mismatch |
|----------------------|-------------------------|-------------------|
| Detected Condition | Condition (C1-C6) | Flag for review |
| Room Count | Above Grade Room Count | Flag for review |
| Property Style | Design (Style) | Flag for review |
| Occupancy Status | Occupant field | Flag for review |
| Pool/Outbuildings visible | Additional Features | Flag if not reported |
| Deferred Maintenance | Condition Rating | Suggest downgrade if applicable |
| External Obsolescence | Adverse Site Conditions | Flag if not reported |

---

## Appendix A: UAD Compliance Reference

### UAD Field Formats

| Field | Format | Example |
|-------|--------|---------|
| Location | Rating;Type;Other | N;Res;Cul |
| View | Rating;Factor;Factor2 | B;Res; |
| Design | Attachment;Stories;Style | DT;1;Ranch |
| Condition | Rating | C3 |
| Quality | Rating | Q4 |
| Date of Sale | Status;Sale Date;Contract Date | s09/19;c07/19 |
| Data Source | MLS;Number;DOM | MISMLS#123456;DOM30 |
| Basement | Size;Finish%;Exit Type | 1000sf;50%;wu |

---

## Appendix B: Rejection Code Reference

### Quick Reference for Common Rejections

| Code | Issue | Rejection Template |
|------|-------|-------------------|
| ADDR-01 | Address mismatch | "Property address does not match with order form." |
| BORR-01 | Missing co-borrower | "Please include Co-borrower name _______ as per order form." |
| NEIGH-01 | N/A neighborhood | "The neighborhood name is mentioned as N/A. Please revise per UAD requirements." |
| ZONE-01 | No zoning comment | "Zoning Compliance is marked 'No Zoning'. Please comment if subject can be rebuilt if destroyed." |
| FLOOD-01 | No marketability comment | "Subject is in FEMA flood zone. Please comment on marketability impact." |
| HOA-01 | PUD not marked | "HOA dues noted but PUD box not marked. Please revise." |
| CONT-01 | Contract section filled on refi | "Assignment is refinance; contract section should be left blank per UAD." |
| DATA-01 | Missing data source | "Please provide data sources for prior listing question per UAD requirement." |

---

> **Document Version**: 1.0  
> **Last Updated**: Based on source files "Appraisal QC Checklist (2).xlsx" and "Appraisal QC Checklist -Detailed.xlsx"  
> **Purpose**: Comprehensive QC rule documentation for automated appraisal review systems
