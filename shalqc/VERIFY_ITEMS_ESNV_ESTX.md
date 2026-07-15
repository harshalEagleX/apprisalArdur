# VERIFY items — ESNV (6901 Camp Fire Rd) & ESTX (7243 Foxtail Meadow Ct)

AMC bundle: **EQUITYSOLUTIONS** (`3f9eafa82a7849f2.yaml`). Status VERIFY = the reviewer must eyeball it (shalqc REVIEW/CANNOT_EVALUATE → Java VERIFY). For each tag: what it checks, the AMC's verbatim check + rejection language, the fields it binds, the pass condition (`expects`) and any conditional, and what was found.


## ESNV-0000885 — 6901 Camp Fire Rd — 73 VERIFY items (qc_result 4)

### EQ-1 — Owner of Public record

- **Section:** SUBJECT  |  **Scope:** cross_section  |  **Card group:** please_verify  |  **Bound by:** llm (conf 0.9)
- **Check language:** Owner of Public record — Provided by the appraiser and be current. Owner of Public record does not have to match the borrower. If the transaction type is Refinance and the Owner of Record and the borrower do not match, a comment must be provided. \| Triggers: IF Owner of Public record does not match the borrower
- **Rejection text:** Assignment type of the report is noted as ‘Refinance’; however, the owner name and the borrower name are different, please revise or comment.
- **Bound labels:** owner_of_public_record, borrower_name
- **Condition (`expects`):** _(empty — no predicate → auto-VERIFY)_
- **Conditional:** condition=['owner_of_public_record', 'borrower_name'] → consequence=[]
- **Found (extracted):** owner_of_public_record: Michael O Smith/Lee Ann Smith; borrower_name: Alyssa M Smith & Kira M Smith  |  **Expected:** If transaction type is Refinance and Owner of Record differs from borrower, a comment must be provided
- **Resolved values:** owner_of_public_record=Michael O Smith/Lee Ann Smith, borrower_name=Alyssa M Smith & Kira M Smith
- **Why VERIFY / reviewer line:** Owner and borrower differ, but transaction type is unknown – please confirm if a comment is required.

### EQ-10 — Special Assessments

- **Section:** SUBJECT  |  **Scope:** subject  |  **Card group:** please_verify  |  **Bound by:** manual (conf 0.9)
- **Check language:** Special Assessments — Must comment if there are Special Assessments provided, how much and what they are for. If no special assessment it must contain "0". \| Triggers: If special assessment mentioned
- **Rejection text:** In the subject section, please specify what is the special assessment of $*** for?
- **Bound labels:** special_assessments, special_assessments_comment
- **Condition (`expects`):** special_assessments == "0" satisfies (no special assessment); only if special_assessments > 0 must special_assessments_comment be non-empty
- **Found (extracted):** __NO_EXTRACTED_VALUE__  |  **Expected:** __NO_EXPECTED_VALUE__
- **Resolved values:** special_assessments=0
- **Why VERIFY / reviewer line:** Automated judgment was unavailable for this check — please review the values shown.

### EQ-100 — Email Address

- **Section:** SIGNATURE  |  **Scope:** subject  |  **Card group:** please_verify  |  **Bound by:** llm (conf 0.92)
- **Check language:** Email Address — Should match the engagement letter
- **Rejection text:** _(none authored)_
- **Bound labels:** appraiser_email
- **Condition (`expects`):** appraiser_email matches engagement_letter_email
- **Found (extracted):** appraiser_email: "jlholliday11@cox.net"; engagement email not present  |  **Expected:** Email address should match the engagement letter email
- **Resolved values:** appraiser_email=jlholliday11@cox.net
- **Why VERIFY / reviewer line:** Engagement letter email missing; cannot confirm match, please verify.

### EQ-106 — Expiration Date of Certification or License

- **Section:** SIGNATURE  |  **Scope:** subject  |  **Card group:** please_verify  |  **Bound by:** llm (conf 0.96)
- **Check language:** Expiration Date of Certification or License — Verify valid date and matches attached License.
- **Rejection text:** _(none authored)_
- **Bound labels:** appraiser_cert_expiration_date
- **Condition (`expects`):** date not past
- **Found (extracted):** appraiser_cert_expiration_date: "2026-12-31"; attached license expiration not present  |  **Expected:** Expiration date must be valid and match attached license expiration
- **Resolved values:** appraiser_cert_expiration_date=2026-12-31
- **Why VERIFY / reviewer line:** License expiration date missing; cannot verify match, please verify.

### EQ-107 — ADDRESS OF PROPERTY APPRAISED

- **Section:** SIGNATURE  |  **Scope:** subject  |  **Card group:** please_verify  |  **Bound by:** llm (conf 0.92)
- **Check language:** ADDRESS OF PROPERTY APPRAISED — Subject property address same as engagement letter or Subject section
- **Rejection text:** _(none authored)_
- **Bound labels:** property_address
- **Condition (`expects`):** _(empty — no predicate → auto-VERIFY)_
- **Found (extracted):** property_address: "6901 Camp Fire Rd"; engagement address not present  |  **Expected:** Property address should match engagement letter or Subject section
- **Resolved values:** property_address=6901 Camp Fire Rd
- **Why VERIFY / reviewer line:** No engagement or subject address to compare; please verify.

### EQ-108 — APPRAISED VALUE OF SUBJECT PROPERTY $

- **Section:** SIGNATURE  |  **Scope:** cross_document  |  **Card group:** please_verify  |  **Bound by:** llm (conf 0.92)
- **Check language:** APPRAISED VALUE OF SUBJECT PROPERTY $ — Should match with Reconciliation section
- **Rejection text:** _(none authored)_
- **Bound labels:** appraised_value, market_value_opinion
- **Condition (`expects`):** _(empty — no predicate → auto-VERIFY)_
- **Found (extracted):** appraised_value="432500"; reconciliation value not present  |  **Expected:** Appraised value must match the Reconciliation section
- **Resolved values:** appraised_value=432500
- **Why VERIFY / reviewer line:** Appraised value provided but no reconciliation value to compare – please verify.

### EQ-11 — PUD and HOA

- **Section:** SUBJECT  |  **Scope:** cross_section  |  **Card group:** please_verify  |  **Bound by:** llm (conf 0.6)
- **Check language:** PUD and HOA — Per FNMA if HOA dues are mandatory, it's a PUD, proper information should filled out in PUD section. Make sure per year or per month is marked. \| Triggers: If HOA is given and PUD is not marked Verify with Client Engagement letter if Refinance or Purchase. If "Other" is marked, the transaction type must be filled in, in the space provided.
- **Rejection text:** HOA dues are noted as “$660” per year in the subject section however PUD box is not marked, please revise.
- **Bound labels:** hoa_dues, hoa_period, is_pud_checked, assignment_type
- **Condition (`expects`):** if hoa_dues present then is_pud_checked=True and hoa_period not empty
- **Conditional:** condition=['census_tract', 'fha_case_number', 'hoa_dues', 'hoa_monthly_assessment'] → consequence=['fha_case_number', 'air_conditioning_type', 'appraisal_report_type', 'assignment_type']
- **Found (extracted):** HOA dues $ 0, is_pud_checked No (PUD box not marked)  |  **Expected:** If HOA dues are mandatory, the PUD box must be marked (Yes)
- **Resolved values:** hoa_dues=$ 0, is_pud_checked=No, assignment_type=Purchase Transaction, census_tract=0030.06, hoa_monthly_assessment=0, air_conditioning_type=Patio/Deck Cov
- **Why VERIFY / reviewer line:** HOA dues present but PUD box not marked; condition ambiguous due to missing FHA case number.

### EQ-110 — Company Name

- **Section:** SIGNATURE  |  **Scope:** cross_document  |  **Card group:** please_verify  |  **Bound by:** manual (conf 0.9)
- **Check language:** Company Name — Must match the Client Engagement letter (Lender/client name)
- **Rejection text:** _(none authored)_
- **Bound labels:** lender_name, engagement.lender_name
- **Condition (`expects`):** lender_name == engagement.lender_name
- **Found (extracted):** lender_name="Cardinal Financial Company"; engagement.lender_name="Cardinal Financial Company, LP"  |  **Expected:** Company name must match the client engagement letter
- **Resolved values:** lender_name=Cardinal Financial Company, engagement.lender_name=Cardinal Financial Company, LP
- **Why VERIFY / reviewer line:** Lender name differs (missing ", LP") – recommend reject.

### EQ-111 — Company Address

- **Section:** SIGNATURE  |  **Scope:** cross_document  |  **Card group:** please_verify  |  **Bound by:** manual (conf 0.92)
- **Check language:** Company Address — Must match the Client Engagement letter (Lender/client address)
- **Rejection text:** _(none authored)_
- **Bound labels:** lender_address, engagement.lender_address
- **Condition (`expects`):** lender_address == engagement.lender_address
- **Found (extracted):** XML lender_address: "3530 Toringdon Way, Suite 200, Charlotte, NC 28277"; Engagement lender_address: "3530 Toringdon Way, Suite 200, Charlotte NC 28277" (missing comma after Charlotte)  |  **Expected:** Company address must exactly match the address in the Client Engagement letter
- **Resolved values:** lender_address=3530 Toringdon Way, Suite 200, Charlotte, engagement.lender_address=3530 Toringdon Way, Suite 200, Charlotte
- **Why VERIFY / reviewer line:** Expected identical address but XML includes a comma after Charlotte while Engagement version does not; recommend reject.

### EQ-113 — Inventory Analysis

- **Section:** MC_1004  |  **Scope:** cross_section  |  **Card group:** please_verify  |  **Bound by:** llm (conf 0.2)
- **Check language:** Inventory Analysis — All lightly shaded areas are required to be completed or a specific comment as to why they cannot be. Required blank spaces should be completed with a "0" if there are none or N/A.
- **Rejection text:** _(none authored)_
- **Bound labels:** _(none — unbound)_
- **Condition (`expects`):** _(empty — no predicate → auto-VERIFY)_
- **Conditional:** condition=['contract_analysis_comment', 'mca_neighborhood_analysis_comment', 'prior_sale_analysis_comment', 'site_area'] → consequence=['appraised_value', 'are_facilities_complete', 'commercial_space_pct', 'comp_count_present']
- **Found (extracted):** __NO_EXTRACTED_VALUE__  |  **Expected:** __NO_EXPECTED_VALUE__
- **Resolved values:** contract_analysis_comment=The appraiser has analyzed the contract , prior_sale_analysis_comment=The subject property is currently under , site_area=7841 sf, appraised_value=432500, comp_count_present=7
- **Why VERIFY / reviewer line:** Automated judgment was unavailable for this check — please review the values shown.

### EQ-114 — Total # of Comparables Sales (Settled)

- **Section:** MC_1004  |  **Scope:** comps  |  **Card group:** please_verify  |  **Bound by:** llm (conf 0.95)
- **Check language:** Total # of Comparables Sales (Settled) — All fields must total to the data provided on the top of the sales grid for Comparables sales in the subject neighborhood.
- **Rejection text:** _(none authored)_
- **Bound labels:** comp_count_present
- **Condition (`expects`):** comp_count_present == total comps in grid
- **Found (extracted):** comp_count_present = 7  |  **Expected:** Total # of Comparables Sales must match the total shown at the top of the sales grid for the subject neighborhood
- **Resolved values:** comp_count_present=7
- **Why VERIFY / reviewer line:** Expected total comparables count from the grid header, but only the present count of 7 is available; please verify the header total.

### EQ-115 — Total # of Comparable Active Listings

- **Section:** MC_1004  |  **Scope:** cross_section  |  **Card group:** please_verify  |  **Bound by:** llm (conf 0.6)
- **Check language:** Total # of Comparable Active Listings — If completed, all fields should match the information provided at the top of the sales grid for Comparable properties currently offered for sale. If all fields not complete, the Current‐3 months must match the data given at the top of the sales grid.
- **Rejection text:** _(none authored)_
- **Bound labels:** mca_active_listings_current_3
- **Condition (`expects`):** _(empty — no predicate → auto-VERIFY)_
- **Conditional:** condition=['comp_N_is_listing', 'comp_N_room_count_total', 'comp_count_present', 'land_use_total'] → consequence=['comp_count_present', 'appraised_value', 'comp_N_adjusted_sale_price', 'comp_N_data_source']
- **Found (extracted):** __NO_EXTRACTED_VALUE__  |  **Expected:** __NO_EXPECTED_VALUE__
- **Resolved values:** comp_count_present=7, appraised_value=432500, comp_1_adjusted_sale_price=420000, comp_2_adjusted_sale_price=432500, comp_3_adjusted_sale_price=432495, comp_4_adjusted_sale_price=451100
- **Why VERIFY / reviewer line:** Automated judgment was unavailable for this check — please review the values shown.

### EQ-116 — Median Sale & List Price, DOM, Sale/List %

- **Section:** MC_1004  |  **Scope:** subject  |  **Card group:** please_verify  |  **Bound by:** manual (conf 0.9)
- **Check language:** Median Sale & List Price, DOM, Sale/List % — All lightly shaded areas are required to be completed or a specific comment as to why they cannot be. Required blank spaces should be completed with a "0" if there are none or N/A. If dark shaded areas cannot be provided, N/A should be provided.
- **Rejection text:** _(none authored)_
- **Bound labels:** mca_median_sale_price_prior_7_12, mca_median_sale_price_prior_4_6, mca_median_sale_price_current_3, mca_median_list_price_prior_7_12, mca_median_list_price_prior_4_6, mca_median_list_price_current_3, mca_median_dom_prior_7_12, mca_median_dom_prior_4_6, mca_median_dom_current_3, mca_median_list_dom_prior_7_12, mca_median_list_dom_prior_4_6, mca_median_list_dom_current_3, mca_median_sale_list_ratio_prior_7_12, mca_median_sale_list_ratio_prior_4_6, mca_median_sale_list_ratio_current_3
- **Condition (`expects`):** SATISFIED when every bound field has ANY value. A currency ("$415,000"), percent ("98%"), integer, "0", or "N/A" all count as filled. Do not require a particular format. Only REVIEW if a listed field is genuinely blank/absent.
- **Found (extracted):** Missing field mca_median_sale_list_ratio_prior_7_12  |  **Expected:** All lightly shaded required fields must be completed or commented (or N/A/0)
- **Resolved values:** mca_median_sale_price_prior_7_12=$405,000, mca_median_sale_price_prior_4_6=$430,000, mca_median_sale_price_current_3=$415,000, mca_median_list_price_prior_7_12=$429,000, mca_median_list_price_prior_4_6=$424,778, mca_median_list_price_current_3=$449,999
- **Why VERIFY / reviewer line:** A required lightly shaded field is missing; please verify if it should be N/A or provided.

### EQ-119 — Condo/Co‐Op Projects

- **Section:** MC_1004  |  **Scope:** cross_section  |  **Card group:** please_verify  |  **Bound by:** llm (conf 0.6)
- **Check language:** Condo/Co‐Op Projects — All lightly shaded areas must be completed if the subject is a Condo Co‐ Op and deal specifically with the subject's project.
- **Rejection text:** _(none authored)_
- **Bound labels:** project_name, project_phase, unit_number
- **Condition (`expects`):** project_name && project_phase && unit_number
- **Conditional:** condition=['unit_number', 'comp_N_project_name', 'is_project_from_conversion', 'mca_project_months_supply_current_3'] → consequence=['unit_number', 'appraisal_subject_to', 'appraised_value', 'are_facilities_complete']
- **Found (extracted):** __NO_EXTRACTED_VALUE__  |  **Expected:** __NO_EXPECTED_VALUE__
- **Resolved values:** project_name=sufficient, appraisal_subject_to=As Is, appraised_value=432500
- **Why VERIFY / reviewer line:** Automated judgment was unavailable for this check — please review the values shown.

### EQ-12 — Property Rights Appraised

- **Section:** SUBJECT  |  **Scope:** subject  |  **Card group:** please_verify  |  **Bound by:** llm (conf 0.95)
- **Check language:** Property Rights Appraised — Only one checkbox mark is allow
- **Rejection text:** _(none authored)_
- **Bound labels:** property_rights
- **Condition (`expects`):** count(property_rights) == 1
- **Found (extracted):** __NO_EXTRACTED_VALUE__  |  **Expected:** __NO_EXPECTED_VALUE__
- **Resolved values:** property_rights=Fee Simple
- **Why VERIFY / reviewer line:** Automated judgment was unavailable for this check — please review the values shown.

### EQ-121 — Appraisal and report Identification

- **Section:** USPAP  |  **Scope:** subject  |  **Card group:** please_verify  |  **Bound by:** llm (conf 0.95)
- **Check language:** Appraisal and report Identification — Must be completed and only 2 choices should be available, Appraisal Report and Restricted Appraisal Report.
- **Rejection text:** _(none authored)_
- **Bound labels:** appraisal_report_type
- **Condition (`expects`):** value in {Appraisal Report, Restricted Appraisal Report}
- **Found (extracted):** No appraisal_report_type value present  |  **Expected:** Appraisal report type must be completed with one of two choices: "Appraisal Report" or "Restricted Appraisal Report"
- **Why VERIFY / reviewer line:** Required appraisal report identification is missing; expected one of two choices.

### EQ-122 — Reasonable Exposure Time

- **Section:** USPAP  |  **Scope:** subject  |  **Card group:** please_verify  |  **Bound by:** llm (conf 0.96)
- **Check language:** Reasonable Exposure Time — Must be provided as a single point or range in time. (i.e. 90 or 30‐60) Additional commentary is suggested but not required.
- **Rejection text:** _(none authored)_
- **Bound labels:** reasonable_exposure_time
- **Condition (`expects`):** len(reasonable_exposure_time) > 0
- **Found (extracted):** No reasonable_exposure_time value present  |  **Expected:** Reasonable Exposure Time must be provided as a single point or range
- **Why VERIFY / reviewer line:** Reasonable Exposure Time is required but not provided.

### EQ-123 — Additional Certifications

- **Section:** USPAP  |  **Scope:** cross_section  |  **Card group:** please_verify  |  **Bound by:** llm (conf 0.3)
- **Check language:** Additional Certifications — Must be provided, if the "I HAVE performed services" is checked, additional commentary is Required to state what those prior services are.
- **Rejection text:** _(none authored)_
- **Bound labels:** _(none — unbound)_
- **Condition (`expects`):** _(empty — no predicate → auto-VERIFY)_
- **Conditional:** condition=['appraiser_state_cert_number', 'appraiser_cert_expiration_date', 'appraiser_cert_state', 'supervisory_appraiser_cert_number'] → consequence=['prior_services_performed', 'is_pud_checked', 'is_seller_owner_of_record', 'prior_sale_analysis_comment']
- **Found (extracted):** __NO_EXTRACTED_VALUE__  |  **Expected:** __NO_EXPECTED_VALUE__
- **Resolved values:** appraiser_state_cert_number=A.0205574-CR, appraiser_cert_expiration_date=2026-12-31, appraiser_cert_state=#, is_pud_checked=No, is_seller_owner_of_record=Y, prior_sale_analysis_comment=The subject property is currently under
- **Why VERIFY / reviewer line:** Automated judgment was unavailable for this check — please review the values shown.

### EQ-124 — Subject Photo Pages

- **Section:** EXHIBITS  |  **Scope:** visual  |  **Card group:** manual_visual  |  **Bound by:** constant (conf 1.0)
- **Check language:** Subject Photo Pages — At a minimum, subject front, rear and street scene photos are required. Verify with client Engagement letter if additional side, street and address verification photos are required. If any obsolescence is observed in photos, commentary must be provided.
- **Rejection text:** _(none authored)_
- **Bound labels:** _(none — unbound)_
- **Condition (`expects`):** _(empty — no predicate → auto-VERIFY)_
- **Found (extracted):** __NO_EXTRACTED_VALUE__  |  **Expected:** __NO_EXPECTED_VALUE__
- **Why VERIFY / reviewer line:** Manual visual check: Subject Photo Pages — At a minimum, subject front, rear and street scene photos are required. Verify with client Engagement letter if additional side, street and address verificati — review the photos/sketch/map by eye.

### EQ-125 — Interior photos

- **Section:** EXHIBITS  |  **Scope:** unbound  |  **Card group:** manual_visual  |  **Bound by:** llm (conf 0.3)
- **Check language:** Interior photos — Photos of all rooms (Kitchen, living room, dining room, family room, bedrooms and all baths) are required for all interior inspection reports. Photos of any deferred maintenance must be provided. Photos must be labeled with the specific room name.
- **Rejection text:** _(none authored)_
- **Bound labels:** _(none — unbound)_
- **Condition (`expects`):** _(empty — no predicate → auto-VERIFY)_
- **Found (extracted):** __NO_EXTRACTED_VALUE__  |  **Expected:** __NO_EXPECTED_VALUE__
- **Why VERIFY / reviewer line:** Manual visual check: Interior photos — Photos of all rooms (Kitchen, living room, dining room, family room, bedrooms and all baths) are required for all interior inspection reports. Photos of any defer — review the photos/sketch/map by eye.

### EQ-126 — Additional Subject photos

- **Section:** EXHIBITS  |  **Scope:** cross_section  |  **Card group:** please_verify  |  **Bound by:** llm (conf 0.2)
- **Check language:** Additional Subject photos — Photos of all outbuildings and special features (pools, etc.) are required. All outbuildings must have interior photos as well as photos of any deferred maintenance for the subject. Photos of any exterior obsolescence should be provided. Photos containing people or interior personal pictures should be avoided if possible.
- **Rejection text:** _(none authored)_
- **Bound labels:** _(none — unbound)_
- **Condition (`expects`):** _(empty — no predicate → auto-VERIFY)_
- **Conditional:** condition=['photo_front', 'photo_rear', 'appraisal_subject_to', 'is_subject_to_ground_rent'] → consequence=['photo_front', 'photo_rear', 'appraisal_subject_to', 'contract_date']
- **Found (extracted):** appraisal_subject_to = "As Is" (present); photo_front, photo_rear, is_subject_to_ground_rent are absent  |  **Expected:** Photos of all outbuildings and special features (pools, etc.) with interior shots and deferred maintenance, plus exterior obsolescence; avoid people/personal pictures.
- **Resolved values:** appraisal_subject_to=As Is, contract_date=2026-06-30
- **Why VERIFY / reviewer line:** Expected Photos of all outbuildings and special features (pools, etc.) with interior shots and deferred maintenance, plus exterior obsolescence; avoid people/personal pictures.; found appraisal_subject_to = "As Is" (present); photo_front, p

### EQ-127 — Comparable Photos

- **Section:** EXHIBITS  |  **Scope:** unbound  |  **Card group:** please_verify  |  **Bound by:** llm (conf 0.2)
- **Check language:** Comparable Photos — For Convential loans, MLS photos are acceptable, however, there should be commentary in the report that states that they did in fact drive by them.
- **Rejection text:** _(none authored)_
- **Bound labels:** _(none — unbound)_
- **Condition (`expects`):** _(empty — no predicate → auto-VERIFY)_
- **Found (extracted):** No commentary or field indicating drive‑by of MLS photos found in the packet  |  **Expected:** Commentary stating that MLS photos were driven by
- **Why VERIFY / reviewer line:** The report lacks the required drive‑by commentary for MLS photos; please verify.

### EQ-128 — Sketch

- **Section:** EXHIBITS  |  **Scope:** visual  |  **Card group:** manual_visual  |  **Bound by:** constant (conf 1.0)
- **Check language:** Sketch — Sketch must be located on the Floor plan Sketch page that is provided in the appraisal software. Must have all floors. Exterior dimension must be provided and all rooms must be labeled and match the number of rooms reported in the sales grid. All outbuildings and garages or any other structure that contributes to value must be on the sketch with proper dimensions.
- **Rejection text:** _(none authored)_
- **Bound labels:** _(none — unbound)_
- **Condition (`expects`):** _(empty — no predicate → auto-VERIFY)_
- **Found (extracted):** __NO_EXTRACTED_VALUE__  |  **Expected:** __NO_EXPECTED_VALUE__
- **Why VERIFY / reviewer line:** Manual visual check: Sketch — Sketch must be located on the Floor plan Sketch page that is provided in the appraisal software. Must have all floors. Exterior dimension must be provided and all rooms mu — review the photos/sketch/map by eye.

### EQ-129 — Area Calculations

- **Section:** EXHIBITS  |  **Scope:** visual  |  **Card group:** manual_visual  |  **Bound by:** constant (conf 1.0)
- **Check language:** Area Calculations — Must be provided, usually found at the bottom of the sketch page.
- **Rejection text:** _(none authored)_
- **Bound labels:** _(none — unbound)_
- **Condition (`expects`):** _(empty — no predicate → auto-VERIFY)_
- **Found (extracted):** __NO_EXTRACTED_VALUE__  |  **Expected:** __NO_EXPECTED_VALUE__
- **Why VERIFY / reviewer line:** Manual visual check: Area Calculations — Must be provided, usually found at the bottom of the sketch page. — review the photos/sketch/map by eye.

### EQ-13 — Subject Listed/Sold within 12 Months

- **Section:** SUBJECT  |  **Scope:** cross_section  |  **Card group:** please_verify  |  **Bound by:** llm (conf 0.6)
- **Check language:** Subject Listed/Sold within 12 Months If there are no prior listings or current sale, this should be marked no and the appraiser MUST include the data source. Must state the MLS abreviated name for the area. IE. MXLMLS \| Trigger: If there are no prior listings or current sale No should be mark and include data source. If the subject IS listed or has a current sale, the field must be in this format: DOM #; Abbreviated MLS name and MLS #. Current list/sale price, current list/sale date. (THIS MUST BE ON PAGE 1) Any additional data can be included in the report addendum. If the subject has been listed but NOT a purchase, a comment must be provided if the opinion of market value varies by the most recent listing price by more than 3% \| Trigger: If currently listed marked as Yes
- **Rejection text:** Please provide Data sources in subject section for the question “Is the subject property currently offered for sale or has it been offered for sale in the twelve months prior to the effective date of this appraisal?” as per UAD requirement.
- **Bound labels:** data_source, days_on_market, list_price, list_date, mls_number
- **Condition (`expects`):** if offerred_for_sale_12mo == false then data_source present; if true then days_on_market, list_price, list_date, mls_number present
- **Conditional:** condition=['mca_median_sale_list_ratio_prior_7_12', 'prior_sale_data_source_subject', 'prior_sale_date_subject', 'prior_sale_effective_date_subject'] → consequence=['prior_sale_data_source_subject', 'prior_sale_date_subject', 'prior_sale_effective_date_subject', 'prior_sale_price_subject']
- **Found (extracted):** data_source present, prior_sale_data_source_subject present, prior_sale_date_subject 2025-12-16, prior_sale_effective_date_subject multiple dates; days_on_market, list_price, list_date absent.  |  **Expected:** If no prior listings or current sale, field must be marked No and include data source; otherwise list DOM, MLS name and number, price, date.
- **Resolved values:** data_source=used, offering price(s),, mls_number=details., prior_sale_data_source_subject=used, offering price(s),, prior_sale_date_subject=2025-12-16, prior_sale_effective_date_subject=07/08/2026 07/08/2026 07/08/2026 07/08/2
- **Why VERIFY / reviewer line:** Cannot determine if subject was listed/sold in 12 months because required condition fields are missing; please verify listing status and MLS details.

### EQ-130 — Aerial Map

- **Section:** EXHIBITS  |  **Scope:** visual  |  **Card group:** manual_visual  |  **Bound by:** constant (conf 1.0)
- **Check language:** Aerial Map — Aerial map must be provided. \| Triggers: If missing reject as : Please Provide Aerial Map In the Report.
- **Rejection text:** _(none authored)_
- **Bound labels:** _(none — unbound)_
- **Condition (`expects`):** _(empty — no predicate → auto-VERIFY)_
- **Found (extracted):** __NO_EXTRACTED_VALUE__  |  **Expected:** __NO_EXPECTED_VALUE__
- **Why VERIFY / reviewer line:** Manual visual check: Aerial Map — Aerial map must be provided. \| Triggers: If missing reject as : Please Provide Aerial Map In the Report. — review the photos/sketch/map by eye.

### EQ-131 — Location Map

- **Section:** EXHIBITS  |  **Scope:** visual  |  **Card group:** manual_visual  |  **Bound by:** constant (conf 1.0)
- **Check language:** Location Map — Location map must show the subject and all comparables with sufficient detail to identify their relative locations.
- **Rejection text:** _(none authored)_
- **Bound labels:** _(none — unbound)_
- **Condition (`expects`):** _(empty — no predicate → auto-VERIFY)_
- **Found (extracted):** __NO_EXTRACTED_VALUE__  |  **Expected:** __NO_EXPECTED_VALUE__
- **Why VERIFY / reviewer line:** Manual visual check: Location Map — Location map must show the subject and all comparables with sufficient detail to identify their relative locations. — review the photos/sketch/map by eye.

### EQ-132 — Plat Map

- **Section:** EXHIBITS  |  **Scope:** visual  |  **Card group:** manual_visual  |  **Bound by:** constant (conf 1.0)
- **Check language:** Plat Map — Is required if Site Dimensions can not be provided on page 1.
- **Rejection text:** _(none authored)_
- **Bound labels:** _(none — unbound)_
- **Condition (`expects`):** _(empty — no predicate → auto-VERIFY)_
- **Found (extracted):** __NO_EXTRACTED_VALUE__  |  **Expected:** __NO_EXPECTED_VALUE__
- **Why VERIFY / reviewer line:** Manual visual check: Plat Map — Is required if Site Dimensions can not be provided on page 1. — review the photos/sketch/map by eye.

### EQ-133 — Flood Map

- **Section:** EXHIBITS  |  **Scope:** visual  |  **Card group:** manual_visual  |  **Bound by:** constant (conf 1.0)
- **Check language:** Flood Map — Is required if the subject is located in a Flood Zone.
- **Rejection text:** _(none authored)_
- **Bound labels:** _(none — unbound)_
- **Condition (`expects`):** _(empty — no predicate → auto-VERIFY)_
- **Found (extracted):** __NO_EXTRACTED_VALUE__  |  **Expected:** __NO_EXPECTED_VALUE__
- **Why VERIFY / reviewer line:** Manual visual check: Flood Map — Is required if the subject is located in a Flood Zone. — review the photos/sketch/map by eye.

### EQ-134 — Appraisers License

- **Section:** EXHIBITS  |  **Scope:** cross_section  |  **Card group:** please_verify  |  **Bound by:** llm (conf 0.2)
- **Check language:** Appraisers License — Appraiser's License copy must be included in the report. And must match information with signature page. \| Triggers: If license is provided before the signature date reject as: 1. Please provide an updated copy of your License, as the copy provided in the report has expired.
- **Rejection text:** _(none authored)_
- **Bound labels:** _(none — unbound)_
- **Condition (`expects`):** _(empty — no predicate → auto-VERIFY)_
- **Conditional:** condition=['appraiser_cert_expiration_date', 'appraiser_cert_state', 'appraiser_company_address', 'appraiser_company_name'] → consequence=['contract_date', 'fha_case_number', 'date_of_signature', 'date_report_signed']
- **Found (extracted):** appraiser_cert_expiration_date = "2026-12-31"; appraiser_cert_state = "#"; appraiser_company_address = "9532 Chanticleer Ct, Las Vegas, NV 89129-7859"; appraiser_company_name = "Holliday Inc."  |  **Expected:** If the appraiser's license copy is provided before the signature date, it must be current; otherwise reject.
- **Resolved values:** appraiser_cert_expiration_date=2026-12-31, appraiser_cert_state=#, appraiser_company_address=9532 Chanticleer Ct, Las Vegas, NV 89129, appraiser_company_name=Holliday Inc., contract_date=2026-06-30, date_of_signature=2026-07-09
- **Why VERIFY / reviewer line:** Condition logic cannot be determined from the provided labels; please verify license timing and expiration.

### EQ-135 — E & O Insurance

- **Section:** EXHIBITS  |  **Scope:** cross_section  |  **Card group:** please_verify  |  **Bound by:** llm (conf 0.2)
- **Check language:** E & O Insurance — Is not required for every report, if not included, this is ok and will not need a revision.
- **Rejection text:** _(none authored)_
- **Bound labels:** _(none — unbound)_
- **Condition (`expects`):** _(empty — no predicate → auto-VERIFY)_
- **Conditional:** condition=[] → consequence=['appraisal_report_type', 'date_report_signed', 'remaining_economic_life']
- **Found (extracted):** No insurance-related field present in the packet.  |  **Expected:** E & O Insurance inclusion status (must be present if required, otherwise ok).
- **Resolved values:** date_report_signed=2026-07-09, remaining_economic_life=39
- **Why VERIFY / reviewer line:** Cannot determine insurance inclusion from available data; please check the report for E & O Insurance.

### EQ-15 — Contract Price & Date of Contract

- **Section:** CONTRACT  |  **Scope:** subject  |  **Card group:** please_verify  |  **Bound by:** llm (conf 0.96)
- **Check language:** Contract Price & Date of Contract — check contract date and contract price from Purchase agreement. \| Triggers: if contract price or contract date is different
- **Rejection text:** In the contract section Contract Price noted as this however in the purchase contract shows this, Please verify.
- **Bound labels:** contract_price, contract_date
- **Condition (`expects`):** contract_price present && contract_date present
- **Found (extracted):** __NO_EXTRACTED_VALUE__  |  **Expected:** __NO_EXPECTED_VALUE__
- **Resolved values:** contract_price=400000, contract_date=2026-06-30
- **Why VERIFY / reviewer line:** Automated judgment was unavailable for this check — please review the values shown.

### EQ-17 — Data Source(s)

- **Section:** CONTRACT  |  **Scope:** subject  |  **Card group:** please_verify  |  **Bound by:** llm (conf 0.85)
- **Check language:** Data Source(s) — Data source is compulsory \| Triggers: Is the property seller the owner of public record? if checkbox marked for yes and data source is missing
- **Rejection text:** Please provide data source for "Is the property seller the owner of public record?" under contract section
- **Bound labels:** data_source, is_seller_owner_of_record
- **Condition (`expects`):** data_source present when seller is owner of public record
- **Found (extracted):** __NO_EXTRACTED_VALUE__  |  **Expected:** __NO_EXPECTED_VALUE__
- **Resolved values:** data_source=used, offering price(s),, is_seller_owner_of_record=Y
- **Why VERIFY / reviewer line:** Automated judgment was unavailable for this check — please review the values shown.

### EQ-18 — Is there any financial assistance (loan charges, sale concessions, gift or downpayment assistance, etc.) to be paid by any party on behalf of the borrower?

- **Section:** CONTRACT  |  **Scope:** cross_section  |  **Card group:** please_verify  |  **Bound by:** llm (conf 0.6)
- **Check language:** Is there any financial assistance (loan charges, sale concessions, gift or downpayment assistance, etc.) to be paid by any party on behalf of the borrower? — Is there any financial assistance (loan charges, sale concessions, gift or downpayment assistance, etc.) to be paid by any party on behalf of the borrower? check yes or no checkbox. \| Triggers: If Yes, report the total dollar amount and describe the items to be paid. ( check from Purchase Agreement); If no, then report the total dollar amount and describe the items to be paid shoule apply "0" check from Purchase agreement. \| Trigger: if concession is given but different from purchase agreement
- **Rejection text:** _(none authored)_
- **Bound labels:** has_financial_assistance, financial_assistance_amount, financial_assistance_description
- **Condition (`expects`):** if has_financial_assistance then financial_assistance_amount > 0 and financial_assistance_description non-empty
- **Conditional:** condition=['financial_assistance_amount', 'concessions_amount', 'financial_assistance_description', 'has_financial_assistance'] → consequence=['stories_in_building', 'appraisal_report_type', 'comp_N_room_count_total', 'concessions_amount']
- **Found (extracted):** has_financial_assistance = Y, concessions_amount = 10000; financial_assistance_description absent.  |  **Expected:** If financial assistance is Yes, report total dollar amount and describe items; if No, report $0 and description.
- **Resolved values:** has_financial_assistance=Y, concessions_amount=10000
- **Why VERIFY / reviewer line:** Financial assistance is marked Yes with amount $10,000 but description is missing; verify required details.

### EQ-2 — Legal Description

- **Section:** SUBJECT  |  **Scope:** subject  |  **Card group:** please_verify  |  **Bound by:** llm (conf 0.96)
- **Check language:** Legal Description — This field should not be blank
- **Rejection text:** _(none authored)_
- **Bound labels:** legal_description
- **Condition (`expects`):** len(legal_description) > 0
- **Found (extracted):** __NO_EXTRACTED_VALUE__  |  **Expected:** __NO_EXPECTED_VALUE__
- **Resolved values:** legal_description=aware
- **Why VERIFY / reviewer line:** The form points to an addendum for this narrative but I could not find the matching text — please check the addendum pages by eye.

### EQ-21 — Unit Housing Price and Age

- **Section:** NEIGHBORHOOD  |  **Scope:** cross_section  |  **Card group:** please_verify  |  **Bound by:** llm (conf 0.6)
- **Check language:** Unit Housing Price and Age — Appraiser to provide and be aware of the high and low prices given. The unadjusted sales prices of the comparables used in the report must fall within the ranges unless comps are not located within the neighborhood (comment required). Comment required if the Market value differs from Predominant by more than 10%, over or under improved and does it affect marketability? Trend should match MC form or specific commentary is required.
- **Rejection text:** _(none authored)_
- **Bound labels:** price_high, price_low, predominant_price, market_value_opinion
- **Condition (`expects`):** price_high and price_low present; abs(market_value_opinion - predominant_price) <= 0.10 * predominant_price
- **Conditional:** condition=['appraised_value', 'comp_N_adjusted_sale_price', 'comp_N_sale_price', 'comp_count_present', 'year_built', 'effective_age'] → consequence=['market_conditions_commentary', 'appraised_value', 'is_seller_owner_of_record', 'market_value_opinion']
- **Found (extracted):** price_high=565, price_low=290, predominant_price=420, appraised_value=432500; no unadjusted sale price values or commentary fields present  |  **Expected:** Unadjusted sales prices of comparables must fall within high/low price range; comment required if not in neighborhood or market value differs >10%
- **Resolved values:** price_high=565, price_low=290, predominant_price=420, appraised_value=432500, comp_1_adjusted_sale_price=420000, comp_2_adjusted_sale_price=432500
- **Why VERIFY / reviewer line:** Expected unadjusted comparable prices within $290‑$565 and relevant comments, but those values/comments are missing; please verify.

### EQ-3 — Assessor's parcel #

- **Section:** SUBJECT  |  **Scope:** subject  |  **Card group:** please_verify  |  **Bound by:** llm (conf 0.96)
- **Check language:** Assessor's parcel # — This field should not be blank
- **Rejection text:** _(none authored)_
- **Bound labels:** assessors_parcel_number
- **Condition (`expects`):** len(assessors_parcel_number) > 0
- **Found (extracted):** __NO_EXTRACTED_VALUE__  |  **Expected:** __NO_EXPECTED_VALUE__
- **Resolved values:** assessors_parcel_number=138-34-712-041
- **Why VERIFY / reviewer line:** Automated judgment was unavailable for this check — please review the values shown.

### EQ-30 — Zoning Classification, Description and Compliance

- **Section:** SITE  |  **Scope:** cross_section  |  **Card group:** please_verify  |  **Bound by:** llm (conf 0.6)
- **Check language:** Zoning Classification, Description and Compliance — Zoning Compliance atleast one box should be checked. (legal, legal non-conferming and No zoning) \| Triggers: If legal checked no comment needed; if legal non-conferming or No zoning then add rejection:1. Zoning Compliance is marked on ’No Zoning’, please comment if the subject can be rebuilt if destroyed. \| Trigger: If illigal is marked Specific Zoning Classification and Zoning Description : should be fill up \| Trigger: if blank then add rejection
- **Rejection text:** _(none authored)_
- **Bound labels:** zoning_compliance, zoning_classification
- **Condition (`expects`):** if zoning_compliance != 'legal' then zoning_classification non-empty
- **Conditional:** condition=['zoning_classification', 'zoning_compliance', 'appraised_value', 'common_elements_description'] → consequence=['legal_description', 'zoning_classification', 'zoning_compliance', 'appraisal_subject_to']
- **Found (extracted):** __NO_EXTRACTED_VALUE__  |  **Expected:** __NO_EXPECTED_VALUE__
- **Resolved values:** zoning_compliance=Legal, zoning_classification=R-1, appraised_value=432500, legal_description=aware, appraisal_subject_to=As Is
- **Why VERIFY / reviewer line:** The form points to an addendum for this narrative but I could not find the matching text — please check the addendum pages by eye.

### EQ-31 — Highest and Best Use

- **Section:** SITE  |  **Scope:** subject  |  **Card group:** please_verify  |  **Bound by:** llm (conf 0.96)
- **Check language:** Highest and Best Use — Highest and Best use \| Triggers: if no, then Hold
- **Rejection text:** _(none authored)_
- **Bound labels:** highest_and_best_use
- **Condition (`expects`):** highest_and_best_use == false
- **Conditional:** condition=['highest_and_best_use'] → consequence=[]
- **Found (extracted):** Yes  |  **Expected:** If Highest and Best Use is No, then Hold; otherwise no action
- **Resolved values:** highest_and_best_use=Yes
- **Why VERIFY / reviewer line:** The condition depends on a 'No' value, but the report shows 'Yes'; unclear if the trigger applies.

### EQ-36 — General description should be fill up

- **Section:** IMPROVEMENTS  |  **Scope:** visual  |  **Card group:** manual_visual  |  **Bound by:** constant (conf 1.0)
- **Check language:** General description should be fill up — if one unit checkbox marked then photos, sketch and sales grid should match \| Triggers: if one with accesssory checkbox is marked then sales grid and sketch should reflects ADU
- **Rejection text:** _(none authored)_
- **Bound labels:** _(none — unbound)_
- **Condition (`expects`):** _(empty — no predicate → auto-VERIFY)_
- **Found (extracted):** __NO_EXTRACTED_VALUE__  |  **Expected:** __NO_EXPECTED_VALUE__
- **Why VERIFY / reviewer line:** Manual visual check: General description should be fill up — if one unit checkbox marked then photos, sketch and sales grid should match \| Triggers: if one with accesssory checkbox is marked then sales — review the photos/sketch/map by eye.

### EQ-39 — Type

- **Section:** IMPROVEMENTS  |  **Scope:** visual  |  **Card group:** manual_visual  |  **Bound by:** constant (conf 1.0)
- **Check language:** Type — Existing Proposed Under construction \| Trigger: If photo detected work is going on then this checkbox should be selected
- **Rejection text:** _(none authored)_
- **Bound labels:** _(none — unbound)_
- **Condition (`expects`):** _(empty — no predicate → auto-VERIFY)_
- **Found (extracted):** __NO_EXTRACTED_VALUE__  |  **Expected:** __NO_EXPECTED_VALUE__
- **Why VERIFY / reviewer line:** Manual visual check: Type — Existing Proposed Under construction \| Trigger: If photo detected work is going on then this checkbox should be selected — review the photos/sketch/map by eye.

### EQ-4 — Tax Year

- **Section:** SUBJECT  |  **Scope:** subject  |  **Card group:** please_verify  |  **Bound by:** llm (conf 0.95)
- **Check language:** Tax Year — Must be latest or last 2 year (This field should not be blank)
- **Rejection text:** _(none authored)_
- **Bound labels:** tax_year
- **Condition (`expects`):** tax_year not blank and tax_year >= current_year-2
- **Found (extracted):** __NO_EXTRACTED_VALUE__  |  **Expected:** __NO_EXPECTED_VALUE__
- **Resolved values:** tax_year=2026
- **Why VERIFY / reviewer line:** Automated judgment was unavailable for this check — please review the values shown.

### EQ-43 — Attic

- **Section:** IMPROVEMENTS  |  **Scope:** visual  |  **Card group:** manual_visual  |  **Bound by:** constant (conf 1.0)
- **Check language:** Attic — Attic atleast 1 checbox should be checked \| Triggers: if photo is provided of attic and None is marked in improvement section reject for checkbox
- **Rejection text:** Photo of attic is provided in the report however in the improvement section the attic box is not marked, please verify
- **Bound labels:** _(none — unbound)_
- **Condition (`expects`):** _(empty — no predicate → auto-VERIFY)_
- **Found (extracted):** __NO_EXTRACTED_VALUE__  |  **Expected:** __NO_EXPECTED_VALUE__
- **Why VERIFY / reviewer line:** Manual visual check: Attic — Attic atleast 1 checbox should be checked \| Triggers: if photo is provided of attic and None is marked in improvement section reject for checkbox — review the photos/sketch/map by eye.

### EQ-44 — Foundation

- **Section:** IMPROVEMENTS  |  **Scope:** cross_section  |  **Card group:** please_verify  |  **Bound by:** llm (conf 0.6)
- **Check language:** Foundation — FOUNDATION checkbox is compulsory \| Triggers: If Full basement or Partial Basement checbox is marked than basement area and Basement finished must be mentioned \| Trigger: if basement is marked as full or partial basement with Outside Entry/exit Evidence of Infestation, Dampness and Settlement \| Trigger: if checkbox is marked check commentary for adversity
- **Rejection text:** _(none authored)_
- **Bound labels:** foundation_type, adverse_conditions
- **Condition (`expects`):** foundation_type present && adverse_conditions present
- **Conditional:** condition=['appraised_value', 'comp_N_basement_gla', 'comp_count_present', 'did_analyze_contract'] → consequence=['comp_N_basement_gla', 'contract_analysis_comment', 'did_analyze_contract', 'fha_case_number']
- **Found (extracted):** foundation_type label is absent  |  **Expected:** Foundation checkbox must be present
- **Resolved values:** adverse_conditions=No, appraised_value=432500, comp_count_present=7, did_analyze_contract=Y, contract_analysis_comment=The appraiser has analyzed the contract
- **Why VERIFY / reviewer line:** Foundation type checkbox is missing; need to verify if it was marked.

### EQ-45 — Exterior and Interior Description should

- **Section:** IMPROVEMENTS  |  **Scope:** cross_section  |  **Card group:** please_verify  |  **Bound by:** llm (conf 0.6)
- **Check language:** Exterior and Interior Description should be completed with Material and Condition. Amenities checkbox should be marked \| Trigger: If improvement section shows Fireplace(s), Patio/Deck, Pool, Woodstove(s), Fence or porch than sales grid should reflect the same. Car Storage \| Trigger: if Car storage checkbox is for None then all area should be blank \| Trigger: If Garage or carport is marked then number of cars should be mentioned \| Trigger: If Garage or carport marked then attach detach or built in should be checked (atleast 1 checkbox )
- **Rejection text:** _(none authored)_
- **Bound labels:** exterior_walls, floor_material, condition_rating, fireplace_count, porch_patio_deck, number_of_cars, parking_space_number
- **Condition (`expects`):** exterior_walls, floor_material, condition_rating non-empty; fireplace_count matches improvement list; porch_patio_deck matches improvement list; if garage/carport then number_of_cars present; if car storage None then parking_space_number blank
- **Conditional:** condition=['common_elements_description', 'exterior_walls', 'financial_assistance_description', 'floor_location'] → consequence=['comp_count_present', 'is_pud_checked', 'porch_patio_deck', 'appraised_value']
- **Found (extracted):** exterior_walls, floor_material, condition_rating, porch_patio_deck present; condition_labels missing  |  **Expected:** Exterior and Interior Description should be completed with Material and Condition. Amenities checkbox should be marked ...
- **Resolved values:** exterior_walls=Blk/Siding/ave, floor_material=plan, condition_rating=C3, porch_patio_deck=Porch/CovPatio Porch/CovPatio Porch/Pati, number_of_cars=3, parking_space_number=3
- **Why VERIFY / reviewer line:** Check requires material and condition details plus amenities boxes, but condition labels are missing so cannot determine compliance.

### EQ-5 — R.E. Taxes $

- **Section:** SUBJECT  |  **Scope:** subject  |  **Card group:** please_verify  |  **Bound by:** llm (conf 0.96)
- **Check language:** R.E. Taxes $ — Not allow in decimals (This field should not be blank)
- **Rejection text:** _(none authored)_
- **Bound labels:** real_estate_taxes
- **Condition (`expects`):** non-blank integer currency
- **Found (extracted):** __NO_EXTRACTED_VALUE__  |  **Expected:** __NO_EXPECTED_VALUE__
- **Resolved values:** real_estate_taxes=$ 1,030
- **Why VERIFY / reviewer line:** Automated judgment was unavailable for this check — please review the values shown.

### EQ-54 — # of COMPARABLE Sales w/in 12 Months

- **Section:** SALES_COMPARISON  |  **Scope:** comps  |  **Card group:** please_verify  |  **Bound by:** llm (conf 0.9)
- **Check language:** # of COMPARABLE Sales w/in 12 Months — MUST only include competing sales. Verify that the comparables provided fall within this range. Range must be consistent with the comparable sales provided and match 1004MC form. Check also Predominant price ranges from page 1.
- **Rejection text:** _(none authored)_
- **Bound labels:** comparable_count
- **Condition (`expects`):** 3 <= comparable_count <= 6
- **Found (extracted):** comparable_count = 57  |  **Expected:** Only competing sales count, matching 1004MC form
- **Resolved values:** comparable_count=57
- **Why VERIFY / reviewer line:** Expected only competing sales count (matching 1004MC); found count 57 – need to verify inclusion criteria.

### EQ-55 — Address

- **Section:** SALES_COMPARISON  |  **Scope:** visual  |  **Card group:** manual_visual  |  **Bound by:** constant (conf 1.0)
- **Check language:** Address — Subject's and All comps address has to be reflected on sales grid \| Triggers: if missing: reject as Please update property address on sales grid or location map so it reflects as ____
- **Rejection text:** _(none authored)_
- **Bound labels:** _(none — unbound)_
- **Condition (`expects`):** _(empty — no predicate → auto-VERIFY)_
- **Found (extracted):** __NO_EXTRACTED_VALUE__  |  **Expected:** __NO_EXPECTED_VALUE__
- **Why VERIFY / reviewer line:** Manual visual check: Address — Subject's and All comps address has to be reflected on sales grid \| Triggers: if missing: reject as Please update property address on sales grid or location map so it ref — review the photos/sketch/map by eye.

### EQ-56 — Proximity to Subject

- **Section:** SALES_COMPARISON  |  **Scope:** visual  |  **Card group:** manual_visual  |  **Bound by:** constant (conf 1.0)
- **Check language:** Proximity to Subject — Must be provided as at least 0.01 miles and the proper direction, N, S, NW, NE, etc. Even if in the same complex. If blank, verify that the location Map is provided.
- **Rejection text:** _(none authored)_
- **Bound labels:** _(none — unbound)_
- **Condition (`expects`):** _(empty — no predicate → auto-VERIFY)_
- **Found (extracted):** __NO_EXTRACTED_VALUE__  |  **Expected:** __NO_EXPECTED_VALUE__
- **Why VERIFY / reviewer line:** Manual visual check: Proximity to Subject — Must be provided as at least 0.01 miles and the proper direction, N, S, NW, NE, etc. Even if in the same complex. If blank, verify that the location Map is p — review the photos/sketch/map by eye.

### EQ-61 — Location

- **Section:** SALES_COMPARISON  |  **Scope:** cross_section  |  **Card group:** please_verify  |  **Bound by:** llm (conf 0.6)
- **Check language:** Location — location must be one of N, B or A (refer site section) \| Triggers: IF subject mentioned as (A - Adverse) then if any of the comps with (N - Neutral) than value must be reflect in negative (-)
- **Rejection text:** _(none authored)_
- **Bound labels:** comp_N_location_rating
- **Condition (`expects`):** comp_N_location_rating in ['N','B','A']
- **Conditional:** condition=['comp_N_floor_location', 'comp_N_location_rating', 'floor_location', 'location'] → consequence=['adverse_site_conditions', 'appraised_value', 'fha_case_number', 'site_value_estimate']
- **Found (extracted):** location: Suburban; condition_labels missing for trigger evaluation  |  **Expected:** Location — location must be one of N, B or A (refer site section)
- **Resolved values:** comp_1_location_rating=N;Res;, comp_2_location_rating=N;Res;BsyRd, comp_3_location_rating=N;Res;, comp_4_location_rating=N;Res;, comp_5_location_rating=N;Res;, comp_6_location_rating=N;Res;
- **Why VERIFY / reviewer line:** Required location codes are not present (found 'Suburban'), and missing condition labels prevent clear judgment.

### EQ-62 — Leasehold/Fee Simple

- **Section:** SALES_COMPARISON  |  **Scope:** cross_section  |  **Card group:** please_verify  |  **Bound by:** llm (conf 0.6)
- **Check language:** Leasehold/Fee Simple — Must be provided, if Leasehold, similar comps must be provided. \| Triggers: If subject section shows Property Rights Appraised as fee simple then sales grid should be the reflect same; If subject section is leasehold and any of the comp shows fee simple then adjustment should be reflected.
- **Rejection text:** _(none authored)_
- **Bound labels:** property_rights
- **Condition (`expects`):** _(empty — no predicate → auto-VERIFY)_
- **Conditional:** condition=['lease_dates'] → consequence=['appraised_value', 'comp_count_present', 'prior_sale_data_source_subject', 'prior_sale_date_subject']
- **Found (extracted):** property_rights = "Fee Simple" (present); lease_dates absent  |  **Expected:** Property Rights must be provided; if Leasehold, comparable comps must be provided.
- **Resolved values:** property_rights=Fee Simple, appraised_value=432500, comp_count_present=7, prior_sale_data_source_subject=used, offering price(s),, prior_sale_date_subject=2025-12-16
- **Why VERIFY / reviewer line:** Expected Property Rights must be provided; if Leasehold, comparable comps must be provided.; found property_rights = "Fee Simple" (present); lease_dates absent. Please verify.

### EQ-64 — View

- **Section:** SALES_COMPARISON  |  **Scope:** visual  |  **Card group:** manual_visual  |  **Bound by:** constant (conf 1.0)
- **Check language:** View — If view is described as Beneficial (B) or Adverse (A) photo must be provided for the same.
- **Rejection text:** _(none authored)_
- **Bound labels:** _(none — unbound)_
- **Condition (`expects`):** _(empty — no predicate → auto-VERIFY)_
- **Found (extracted):** __NO_EXTRACTED_VALUE__  |  **Expected:** __NO_EXPECTED_VALUE__
- **Why VERIFY / reviewer line:** Manual visual check: View — If view is described as Beneficial (B) or Adverse (A) photo must be provided for the same. — review the photos/sketch/map by eye.

### EQ-67 — Actual Age

- **Section:** SALES_COMPARISON  |  **Scope:** comps  |  **Card group:** please_verify  |  **Bound by:** llm (conf 0.92)
- **Check language:** Actual Age — Verify actual age with year built \| Triggers: if different add rejection
- **Rejection text:** Per the improvement section subjects year built is 2023 and its actual age should be 1, however the sales comparison grid shows the actual age as 0. Please verify.
- **Bound labels:** comp_N_actual_age
- **Condition (`expects`):** comp_N_actual_age matches year built
- **Found (extracted):** Actual ages are 63, 58, 58, 62, 62, 62, 58  |  **Expected:** Actual age should match derived age of 59
- **Resolved values:** comp_1_actual_age=63, comp_2_actual_age=58, comp_3_actual_age=58, comp_4_actual_age=62, comp_5_actual_age=62, comp_6_actual_age=62
- **Why VERIFY / reviewer line:** Expected actual age 59 but found ages 63/58/62 etc., indicating a mismatch.

### EQ-68 — Condition

- **Section:** SALES_COMPARISON  |  **Scope:** comps  |  **Card group:** please_verify  |  **Bound by:** llm (conf 0.85)
- **Check language:** Condition — Verify condition rating matches with the photos provided in the report. check comments. \| Triggers: if different or inconsistent from other comps
- **Rejection text:** Please provide condition adjustment for comps# 2, 3 and 4 or comment why it was not warranted as compare to subject.
- **Bound labels:** comp_N_condition_rating
- **Condition (`expects`):** _(empty — no predicate → auto-VERIFY)_
- **Found (extracted):** Condition ratings provided (C4, C3, etc.) but no photo or comment comparison  |  **Expected:** Condition rating must match photos and comments
- **Resolved values:** comp_1_condition_rating=C4, comp_2_condition_rating=C3, comp_3_condition_rating=C3, comp_4_condition_rating=C3, comp_5_condition_rating=C3, comp_6_condition_rating=C3
- **Why VERIFY / reviewer line:** Condition ratings are present but cannot confirm they match photos/comments without additional evidence.

### EQ-69 — Above Grade/Room count/ and GLA

- **Section:** SALES_COMPARISON  |  **Scope:** visual  |  **Card group:** manual_visual  |  **Bound by:** constant (conf 1.0)
- **Check language:** Above Grade/Room count/ and GLA — Must be provided, verify all rooms and GLA match Sketch.
- **Rejection text:** _(none authored)_
- **Bound labels:** _(none — unbound)_
- **Condition (`expects`):** _(empty — no predicate → auto-VERIFY)_
- **Found (extracted):** __NO_EXTRACTED_VALUE__  |  **Expected:** __NO_EXPECTED_VALUE__
- **Why VERIFY / reviewer line:** Manual visual check: Above Grade/Room count/ and GLA — Must be provided, verify all rooms and GLA match Sketch. — review the photos/sketch/map by eye.

### EQ-7 — Map Reference

- **Section:** SUBJECT  |  **Scope:** visual  |  **Card group:** manual_visual  |  **Bound by:** constant (conf 1.0)
- **Check language:** Map Reference — Provided by the appraiser and must be current \| Triggers: IF Map Reference missing or blank
- **Rejection text:** _(none authored)_
- **Bound labels:** _(none — unbound)_
- **Condition (`expects`):** _(empty — no predicate → auto-VERIFY)_
- **Found (extracted):** __NO_EXTRACTED_VALUE__  |  **Expected:** __NO_EXPECTED_VALUE__
- **Why VERIFY / reviewer line:** Manual visual check: Map Reference — Provided by the appraiser and must be current \| Triggers: IF Map Reference missing or blank — review the photos/sketch/map by eye.

### EQ-70 — Basement & Finish/Rooms Below Grade

- **Section:** SALES_COMPARISON  |  **Scope:** cross_section  |  **Card group:** please_verify  |  **Bound by:** llm (conf 0.6)
- **Check language:** Basement & Finish/Rooms Below Grade — If Full basement or Partial Basement checbox is marked in the improvement section then basement area and Basement finished must be mentioned in two separate line in the sales grid (ex. Basement & Finished Rooms Below Grade)
- **Rejection text:** _(none authored)_
- **Bound labels:** comp_N_basement_gla
- **Condition (`expects`):** comp_N_basement_gla present
- **Conditional:** condition=['comp_N_basement_gla', 'comp_N_room_count_total', 'total_rooms', 'trim_finish_material'] → consequence=['comp_count_present', 'appraised_value', 'comp_N_adjusted_sale_price', 'comp_N_basement_gla']
- **Found (extracted):** No basement GLA or room count fields present; condition labels absent.  |  **Expected:** If a basement checkbox is marked, basement area and finished rooms must be listed in the sales grid.
- **Resolved values:** total_rooms=5, trim_finish_material=Wood/Paint/good, comp_count_present=7, appraised_value=432500, comp_1_adjusted_sale_price=420000, comp_2_adjusted_sale_price=432500
- **Why VERIFY / reviewer line:** Basement fields are missing, making it unclear whether the trigger applies; requires human review.

### EQ-71 — Functional Utility

- **Section:** SALES_COMPARISON  |  **Scope:** subject  |  **Card group:** please_verify  |  **Bound by:** llm (conf 0.96)
- **Check language:** Functional Utility — must be provided as Standard, Average or Typical
- **Rejection text:** _(none authored)_
- **Bound labels:** functional_utility
- **Condition (`expects`):** value in {'Standard','Average','Typical'}
- **Found (extracted):** none  |  **Expected:** Functional Utility must be Standard, Average, or Typical
- **Why VERIFY / reviewer line:** Functional Utility value is missing; cannot confirm if it meets Standard/Average/Typical.

### EQ-73 — Energy Efficient Items

- **Section:** SALES_COMPARISON  |  **Scope:** comps  |  **Card group:** please_verify  |  **Bound by:** llm (conf 0.8)
- **Check language:** Energy Efficient Items — Energy Efficient items need to be described. Differences from subject to comp NOT adjusted must have a 0 in grid adjustment field.
- **Rejection text:** _(none authored)_
- **Bound labels:** comp_N_net_adjustment
- **Condition (`expects`):** comp_N_net_adjustment == 0 when energy efficient items not described
- **Found (extracted):** No description or zero‑adjustment fields present  |  **Expected:** Energy Efficient items described; non‑adjusted differences have 0 adjustment
- **Resolved values:** comp_1_net_adjustment=60000, comp_2_net_adjustment=-17500, comp_3_net_adjustment=-7500, comp_4_net_adjustment=31100, comp_5_net_adjustment=4500, comp_6_net_adjustment=10000
- **Why VERIFY / reviewer line:** Required description and zero‑adjustment fields are missing, cannot evaluate compliance.

### EQ-74 — Garage/Carport

- **Section:** SALES_COMPARISON  |  **Scope:** cross_section  |  **Card group:** please_verify  |  **Bound by:** llm (conf 0.6)
- **Check language:** Garage/Carport — If in the improvement section Garage is marked then sales grid reflect the garage with driveway (ex. 1ga2dw) \| Triggers: If any of this is differnt with subject the adjustment or 0 is required.
- **Rejection text:** _(none authored)_
- **Bound labels:** comp_N_garage_carport
- **Condition (`expects`):** if subject garage marked then comp_N_garage_carport includes garage with driveway (e.g., contains 'ga' and 'dw')
- **Conditional:** condition=['comp_N_garage_carport'] → consequence=['comp_count_present', 'prior_sale_data_source_subject', 'prior_sale_date_subject', 'prior_sale_effective_date_subject']
- **Found (extracted):** comp_3_garage_carport="1ga2dw" with conflict "01ga2dw"; other comps show various codes  |  **Expected:** Garage marked in improvement section must be reflected in sales grid (e.g., 1ga2dw)
- **Resolved values:** comp_1_garage_carport=2dw, comp_2_garage_carport=2dw, comp_3_garage_carport=1ga2dw, comp_4_garage_carport=1gbi1dw, comp_5_garage_carport=1ga2dw, comp_6_garage_carport=1dw
- **Why VERIFY / reviewer line:** Expected garage code reflected in grid, but found conflicting values (1ga2dw vs 01ga2dw), please verify.

### EQ-77 — Net Adjustment (total)

- **Section:** SALES_COMPARISON  |  **Scope:** comps  |  **Card group:** please_verify  |  **Bound by:** llm (conf 0.92)
- **Check language:** Net Adjustment (total) — The Net Adjustment is the total of all adjustments. The result can be a positive or negative number. In residential appraisal, net adjustments generally may not exceed 15% of the sale price of the comparable sale. \| Triggers: If exceeds 15% reject as: Please address Comps 1, 3 and 4 exceeding 15% net adjustments.
- **Rejection text:** _(none authored)_
- **Bound labels:** comp_N_net_adjustment, comp_N_sale_price
- **Condition (`expects`):** abs(comp_N_net_adjustment) <= 0.15 * comp_N_sale_price
- **Found (extracted):** Comp 1 net adjustment 60000 exceeds 15% of its sale price 360000 (max 54000)  |  **Expected:** Net adjustment ≤15% of each comparable's sale price
- **Resolved values:** comp_1_net_adjustment=60000, comp_2_net_adjustment=-17500, comp_3_net_adjustment=-7500, comp_4_net_adjustment=31100, comp_5_net_adjustment=4500, comp_6_net_adjustment=10000
- **Why VERIFY / reviewer line:** Comp 1 net adjustment 60000 exceeds the 15% limit of its sale price (54000).

### EQ-78 — Adjusted Sale Price of Comparables

- **Section:** SALES_COMPARISON  |  **Scope:** comps  |  **Card group:** please_verify  |  **Bound by:** llm (conf 0.96)
- **Check language:** Adjusted Sale Price of Comparables — The adjusted sale price reflects the market's reaction to differences between the subject and sales and provides a more accurate range of value for the subject.
- **Rejection text:** _(none authored)_
- **Bound labels:** comp_N_adjusted_sale_price
- **Condition (`expects`):** count(comp_N_adjusted_sale_price present) >= 1
- **Found (extracted):** Adjusted sale prices are listed but no narrative evidence of market reaction  |  **Expected:** Adjusted sale price reflects market reaction
- **Resolved values:** comp_1_adjusted_sale_price=420000, comp_2_adjusted_sale_price=432500, comp_3_adjusted_sale_price=432495, comp_4_adjusted_sale_price=451100, comp_5_adjusted_sale_price=454500, comp_6_adjusted_sale_price=454999
- **Why VERIFY / reviewer line:** Adjusted sale prices are present but without supporting narrative, compliance cannot be assessed.

### EQ-80 — Subject Property 3 year sales or transfer history

- **Section:** PRIOR_SALES  |  **Scope:** cross_section  |  **Card group:** please_verify  |  **Bound by:** llm (conf 0.6)
- **Check language:** Subject Property 3 year sales or transfer history — If subject sold/transferred in 36 months than "My research did reveal any prior sales or transfers of the subject property" box must be marked \| Triggers: If subject sold/transferred in 36 months but did nox box marked than reject as: Prior Sales: Please check “Did” box for subject prior sales or transfers because your data revealed subject has been transferred within three years.; If sold in 36 months prior "Date of Prior Sale/Transfer and Price of Prior Sale/Transfer" must be included in the report.
- **Rejection text:** _(none authored)_
- **Bound labels:** sales_history_researched, prior_sale_date_subject, prior_sale_price_subject
- **Condition (`expects`):** if prior_sale_date_subject within 36 months then prior_sale_price_subject must be present and prior sales box marked
- **Conditional:** condition=['prior_sale_data_source_subject', 'prior_sale_date_subject', 'prior_sale_effective_date_subject', 'prior_sale_price_subject'] → consequence=['prior_sale_data_source_subject', 'prior_sale_date_subject', 'prior_sale_effective_date_subject', 'prior_sale_price_subject']
- **Found (extracted):** sales_history_researched="Yes"; prior_sale_date_subject="2025-12-16"; prior_sale_effective_date_subject="07/08/2026 ..."; prior_sale_price_subject absent  |  **Expected:** If subject transferred within 36 months, the "Did" box must be marked and prior sale details included
- **Resolved values:** sales_history_researched=Yes, prior_sale_date_subject=2025-12-16, prior_sale_data_source_subject=used, offering price(s),, prior_sale_effective_date_subject=07/08/2026 07/08/2026 07/08/2026 07/08/2
- **Why VERIFY / reviewer line:** Condition cannot be fully read due to missing prior sale price, please verify.

### EQ-81 — Comparables 12 month sales or transfer history

- **Section:** PRIOR_SALES  |  **Scope:** cross_section  |  **Card group:** please_verify  |  **Bound by:** llm (conf 0.6)
- **Check language:** Comparables 12 month sales or transfer history — If comparable sold/transferred in 12 months than "My research did reveal any prior sales or transfers of the comparable sales for the year prior to the date of sale of the comparable sale" box must be marked
- **Rejection text:** _(none authored)_
- **Bound labels:** prior_comp_N_sale_date
- **Condition (`expects`):** if(comp_N_sale_date within 12mo) then prior_comp_N_sale_date is null
- **Conditional:** condition=['prior_comp_N_sale_date', 'comp_N_sale_date', 'comp_count_present', 'prior_comp_N_sale_price'] → consequence=[]
- **Found (extracted):** Narrative indicates some comparables had transfers in 12 months, but prior_comp_N_sale_date label is absent  |  **Expected:** If any comparable sold/transferred in the past 12 months, the "no prior sales" box must be marked
- **Resolved values:** comp_1_sale_date=s06/26;c05/26, comp_2_sale_date=s05/26;c04/26, comp_3_sale_date=s07/26;c04/26, comp_4_sale_date=s04/26;c03/26, comp_5_sale_date=s09/25;c08/25, comp_6_sale_date=c06/26
- **Why VERIFY / reviewer line:** Check expects a marked box for no prior sales, but narrative shows mixed transfers and the required label is missing; please verify.

### EQ-83 — Price of Prior Sale/Transfer

- **Section:** PRIOR_SALES  |  **Scope:** cross_section  |  **Card group:** please_verify  |  **Bound by:** llm (conf 0.6)
- **Check language:** Price of Prior Sale/Transfer — Figure of last sale or transfer must be provided here. Only the most recent figure should be reported here, if there is more than 1, commentary must be provided.
- **Rejection text:** _(none authored)_
- **Bound labels:** prior_sale_price_subject
- **Condition (`expects`):** value_present
- **Conditional:** condition=['mca_median_sale_price_prior_4_6', 'mca_median_sale_price_prior_7_12', 'prior_comp_N_sale_price', 'prior_sale_price_subject'] → consequence=['market_conditions_commentary', 'appraisal_report_type', 'contract_analysis_comment', 'contract_date']
- **Found (extracted):** Only median prior sale price fields present; prior_sale_price_subject is absent  |  **Expected:** Figure of last sale or transfer must be provided
- **Resolved values:** mca_median_sale_price_prior_4_6=$430,000, mca_median_sale_price_prior_7_12=$405,000, market_conditions_commentary=Median price is stable over 12 months. S, contract_analysis_comment=The appraiser has analyzed the contract , contract_date=2026-06-30
- **Why VERIFY / reviewer line:** The check requires the most recent sale figure, but the specific prior sale price field is missing; please verify.

### EQ-9 — Occupant

- **Section:** SUBJECT  |  **Scope:** visual  |  **Card group:** manual_visual  |  **Bound by:** constant (conf 1.0)
- **Check language:** Occupant — If tenant: should verify lease dates and amount. If vacant: must state if utilities are on. \| Triggers: If occupancy is owner occupied photos should check photos.; If occupancy is vacant and photo shows occupied: Reject as: In subject section, occupancy is marked as vacant however as per photos subject property appears to be occupied, please revise or comment if it is a staged home.
- **Rejection text:** The subject section indicates that the property is owner occupied however the photos appear to show the property is currently vacant. Please revise or comment.
- **Bound labels:** _(none — unbound)_
- **Condition (`expects`):** _(empty — no predicate → auto-VERIFY)_
- **Found (extracted):** __NO_EXTRACTED_VALUE__  |  **Expected:** __NO_EXPECTED_VALUE__
- **Why VERIFY / reviewer line:** Manual visual check: Occupant — If tenant: should verify lease dates and amount. If vacant: must state if utilities are on. \| Triggers: If occupancy is owner occupied photos should check photos.; If oc — review the photos/sketch/map by eye.

### EQ-94 — INCOME APPROACH TO VALUE

- **Section:** COST  |  **Scope:** cross_section  |  **Card group:** please_verify  |  **Bound by:** llm (conf 0.2)
- **Check language:** INCOME APPROACH TO VALUE — If this section is blank than no need to add revision.
- **Rejection text:** _(none authored)_
- **Bound labels:** _(none — unbound)_
- **Condition (`expects`):** _(empty — no predicate → auto-VERIFY)_
- **Conditional:** condition=['indicated_value_income_approach', 'income_approach_monthly_rent', 'indicated_value_cost_approach', 'is_income_approach_used'] → consequence=[]
- **Found (extracted):** indicated_value_income_approach = "0" (not blank)  |  **Expected:** Income approach section should be blank; otherwise a revision is needed
- **Resolved values:** indicated_value_income_approach=0, indicated_value_cost_approach=300868
- **Why VERIFY / reviewer line:** Expected a blank income approach section but found a value of 0; please verify if revision is required.

### EQ-95 — Is Developer/builder in control?

- **Section:** PUD  |  **Scope:** cross_section  |  **Card group:** please_verify  |  **Bound by:** llm (conf 0.6)
- **Check language:** Is Developer/builder in control? — Should be completed for All PUD reports, check yes or no and Attached/Detached. \| Triggers: If attached and yes checkbox is marked then all pud information should be fill up
- **Rejection text:** _(none authored)_
- **Bound labels:** is_developer_controls_hoa
- **Condition (`expects`):** _(empty — no predicate → auto-VERIFY)_
- **Conditional:** condition=['is_developer_controls_hoa'] → consequence=['appraisal_report_type', 'appraised_value', 'are_facilities_complete', 'census_tract']
- **Found (extracted):** is_developer_controls_hoa label absent  |  **Expected:** Answer to "Is Developer/builder in control?" (yes/no) and attached/detached status
- **Resolved values:** appraised_value=432500, census_tract=0030.06
- **Why VERIFY / reviewer line:** Developer control answer missing; cannot determine if the check is satisfied.

### EQ-96 — Appraiser

- **Section:** SIGNATURE  |  **Scope:** cross_section  |  **Card group:** please_verify  |  **Bound by:** llm (conf 0.6)
- **Check language:** Appraiser — All reports must be signed by certified Appraiser. \| Triggers: If signature is missing reject as: 1. The Appraiser Signatures are missing throughout the report, please sign in all the designated spaces.
- **Rejection text:** _(none authored)_
- **Bound labels:** date_report_signed
- **Condition (`expects`):** presence(date_report_signed) == true
- **Conditional:** condition=['appraisal_report_type', 'appraiser_cert_expiration_date', 'appraiser_cert_state', 'appraiser_company_address'] → consequence=['appraiser_cert_expiration_date', 'appraiser_cert_state', 'appraiser_state_cert_number', 'date_report_signed']
- **Found (extracted):** date_report_signed present but no signature field found  |  **Expected:** Appraiser signature present on the report
- **Resolved values:** date_report_signed=2026-07-09, appraiser_cert_expiration_date=2026-12-31, appraiser_cert_state=#, appraiser_company_address=9532 Chanticleer Ct, Las Vegas, NV 89129, appraiser_state_cert_number=A.0205574-CR
- **Why VERIFY / reviewer line:** Signature field not found; need to confirm the appraiser signed the report.

### EQ-99 — Telephone number

- **Section:** SIGNATURE  |  **Scope:** cross_document  |  **Card group:** please_verify  |  **Bound by:** llm (conf 0.95)
- **Check language:** Telephone number — Should match the engagement letter
- **Rejection text:** _(none authored)_
- **Bound labels:** appraiser_phone
- **Condition (`expects`):** match(engagement_letter_phone)
- **Found (extracted):** appraiser_phone="(702) 419-2298"; engagement.appraiser_phone not present  |  **Expected:** Telephone number must match the engagement letter
- **Resolved values:** appraiser_phone=(702) 419-2298
- **Why VERIFY / reviewer line:** Phone present in report but engagement phone missing – please verify match.

### EQ-B — Transaction type

- **Section:** ORDER  |  **Scope:** subject  |  **Card group:** please_verify  |  **Bound by:** llm (conf 0.95)
- **Check language:** Transaction type — Loan type on order form match with Assignment Type
- **Rejection text:** _(none authored)_
- **Bound labels:** loan_type, assignment_type
- **Condition (`expects`):** loan_type == assignment_type
- **Found (extracted):** __NO_EXTRACTED_VALUE__  |  **Expected:** __NO_EXPECTED_VALUE__
- **Resolved values:** assignment_type=Purchase Transaction
- **Why VERIFY / reviewer line:** Automated judgment was unavailable for this check — please review the values shown.

### EQ-C — Property Address, City, State, Zip Code and County

- **Section:** SUBJECT  |  **Scope:** cross_section  |  **Card group:** please_verify  |  **Bound by:** llm (conf 0.95)
- **Check language:** Property Address, City, State, Zip Code and County — Must match the Client Engagement Letter exactly and be verified with USPS, if the USPS verification indicates the address differs from the client engagement letter, a comment must be provided. \| Triggers: If property address is different than order form
- **Rejection text:** Property Zip code does not match with order form. (For Zip code only first 5 digit should be match)
- **Bound labels:** property_address, city, state, zip_code, county
- **Condition (`expects`):** match(order_form_address) && comment_if_mismatch
- **Conditional:** condition=['property_address', 'city', 'state', 'zip_code', 'county'] → consequence=[]
- **Found (extracted):** property_address: 6901 Camp Fire Rd; city: Las Vegas; state: NV; zip_code: 89145; county: Clark  |  **Expected:** Property address, city, state, zip, and county must exactly match the Client Engagement Letter
- **Resolved values:** property_address=6901 Camp Fire Rd, city=Las Vegas, state=NV, zip_code=89145, county=Clark
- **Why VERIFY / reviewer line:** Expected address fields to match the engagement letter, but the letter data is unavailable – please verify the match.

### EQ-D — Borrower

- **Section:** SUBJECT  |  **Scope:** cross_section  |  **Card group:** please_verify  |  **Bound by:** llm (conf 0.85)
- **Check language:** Borrower — Must match Client Engagement letter exactly, watch commonly missed co‐borrower and spelling errors. Does not need to match Owner of Public Record. If transaction type is Refinance and the Owner of Record and the borrower do not match, a comment must be provided. \| Triggers: If report missed Co-borrower name.
- **Rejection text:** Please include Co-borrower name _______ as per order form.
- **Bound labels:** borrower_name, co_borrower_name, owner_of_public_record, loan_type
- **Condition (`expects`):** borrower_name must equal engagement‑letter borrower; co_borrower_name must be present if in letter; if loan_type=Refinance and owner_of_public_record ≠ borrower_name then a comment is required
- **Conditional:** condition=['loan_type', 'owner_of_public_record', 'borrower_name'] → consequence=[]
- **Found (extracted):** borrower_name: Alyssa M Smith & Kira M Smith; co_borrower_name: Kira M Smith; owner_of_public_record: Michael O Smith/Lee Ann Smith  |  **Expected:** Borrower name must match the Client Engagement Letter exactly; co‑borrower name must be present
- **Resolved values:** borrower_name=Alyssa M Smith & Kira M Smith, co_borrower_name=Kira M Smith, owner_of_public_record=Michael O Smith/Lee Ann Smith
- **Why VERIFY / reviewer line:** Expected Borrower name must match the Client Engagement Letter exactly; co‑borrower name must be present; found borrower_name: Alyssa M Smith & Kira M Smith; co_borrower_name: Kira M Smith; owner_of_public_record: Michael O Smith/Lee Ann Sm


## ESTX-0007568 — 7243 Foxtail Meadow Ct — 84 VERIFY items (qc_result 6)

### EQ-1 — Owner of Public record

- **Section:** SUBJECT  |  **Scope:** cross_section  |  **Card group:** please_verify  |  **Bound by:** llm (conf 0.9)
- **Check language:** Owner of Public record — Provided by the appraiser and be current. Owner of Public record does not have to match the borrower. If the transaction type is Refinance and the Owner of Record and the borrower do not match, a comment must be provided. \| Triggers: IF Owner of Public record does not match the borrower
- **Rejection text:** Assignment type of the report is noted as ‘Refinance’; however, the owner name and the borrower name are different, please revise or comment.
- **Bound labels:** owner_of_public_record, borrower_name
- **Condition (`expects`):** _(empty — no predicate → auto-VERIFY)_
- **Conditional:** condition=['owner_of_public_record', 'borrower_name'] → consequence=[]
- **Found (extracted):** owner_of_public_record: RATHNASEKARA KARUNARATNE; borrower_name: RATHNASEKARA KARUNARATNE; transaction type: absent  |  **Expected:** If transaction type is Refinance and Owner of Record differs from borrower, a comment must be provided
- **Resolved values:** owner_of_public_record=RATHNASEKARA KARUNARATNE, borrower_name=RATHNASEKARA KARUNARATNE
- **Why VERIFY / reviewer line:** Transaction type is not provided, so cannot assess whether a comment is required for mismatched owner/borrower.

### EQ-100 — Email Address

- **Section:** SIGNATURE  |  **Scope:** subject  |  **Card group:** please_verify  |  **Bound by:** llm (conf 0.92)
- **Check language:** Email Address — Should match the engagement letter
- **Rejection text:** _(none authored)_
- **Bound labels:** appraiser_email
- **Condition (`expects`):** appraiser_email matches engagement_letter_email
- **Found (extracted):** XML appraiser_email="mark@mca-appraisals.com"; engagement email not provided  |  **Expected:** Email address should match the engagement letter
- **Resolved values:** appraiser_email=mark@mca-appraisals.com
- **Why VERIFY / reviewer line:** Engagement letter email missing; cannot confirm match – please verify.

### EQ-107 — ADDRESS OF PROPERTY APPRAISED

- **Section:** SIGNATURE  |  **Scope:** subject  |  **Card group:** please_verify  |  **Bound by:** llm (conf 0.92)
- **Check language:** ADDRESS OF PROPERTY APPRAISED — Subject property address same as engagement letter or Subject section
- **Rejection text:** _(none authored)_
- **Bound labels:** property_address
- **Condition (`expects`):** _(empty — no predicate → auto-VERIFY)_
- **Found (extracted):** property_address="7243 Foxtail Meadow Ct"; engagement address not provided  |  **Expected:** Property address should match engagement letter or Subject section
- **Resolved values:** property_address=7243 Foxtail Meadow Ct
- **Why VERIFY / reviewer line:** Engagement address missing; cannot verify match – please verify.

### EQ-108 — APPRAISED VALUE OF SUBJECT PROPERTY $

- **Section:** SIGNATURE  |  **Scope:** cross_document  |  **Card group:** please_verify  |  **Bound by:** llm (conf 0.92)
- **Check language:** APPRAISED VALUE OF SUBJECT PROPERTY $ — Should match with Reconciliation section
- **Rejection text:** _(none authored)_
- **Bound labels:** appraised_value, market_value_opinion
- **Condition (`expects`):** _(empty — no predicate → auto-VERIFY)_
- **Found (extracted):** appraised_value "245000"; reconciliation value not present  |  **Expected:** Appraised value must match the Reconciliation section
- **Resolved values:** appraised_value=245000
- **Why VERIFY / reviewer line:** Appraised value is provided but no reconciliation value to compare; cannot determine compliance.

### EQ-11 — PUD and HOA

- **Section:** SUBJECT  |  **Scope:** cross_section  |  **Card group:** please_verify  |  **Bound by:** llm (conf 0.6)
- **Check language:** PUD and HOA — Per FNMA if HOA dues are mandatory, it's a PUD, proper information should filled out in PUD section. Make sure per year or per month is marked. \| Triggers: If HOA is given and PUD is not marked Verify with Client Engagement letter if Refinance or Purchase. If "Other" is marked, the transaction type must be filled in, in the space provided.
- **Rejection text:** HOA dues are noted as “$660” per year in the subject section however PUD box is not marked, please revise.
- **Bound labels:** hoa_dues, hoa_period, is_pud_checked, assignment_type
- **Condition (`expects`):** if hoa_dues present then is_pud_checked=True and hoa_period not empty
- **Conditional:** condition=['census_tract', 'fha_case_number', 'hoa_dues', 'hoa_monthly_assessment'] → consequence=['fha_case_number', 'air_conditioning_type', 'appraisal_report_type', 'assignment_type']
- **Found (extracted):** census_tract present, hoa_dues present, hoa_monthly_assessment present; fha_case_number absent  |  **Expected:** Condition requires census_tract, fha_case_number, hoa_dues, hoa_monthly_assessment to be present
- **Resolved values:** hoa_dues=360, hoa_period=Annually, is_pud_checked=Yes, assignment_type=Refinance Transaction, census_tract=2409.06, hoa_monthly_assessment=360
- **Why VERIFY / reviewer line:** Expected Condition requires census_tract, fha_case_number, hoa_dues, hoa_monthly_assessment to be present; found census_tract present, hoa_dues present, hoa_monthly_assessment present; fha_case_number absent. Please verify.

### EQ-111 — Company Address

- **Section:** SIGNATURE  |  **Scope:** cross_document  |  **Card group:** please_verify  |  **Bound by:** manual (conf 0.92)
- **Check language:** Company Address — Must match the Client Engagement letter (Lender/client address)
- **Rejection text:** _(none authored)_
- **Bound labels:** lender_address, engagement.lender_address
- **Condition (`expects`):** lender_address == engagement.lender_address
- **Found (extracted):** lender_address: "29444 Northwestern Hwy Suite 100, Southfield, MI 48034" vs engagement.lender_address: "29444 Northwestern Hwy Suite 100, Southfield MI 48034"  |  **Expected:** Company Address must match the Client Engagement letter address
- **Resolved values:** lender_address=29444 Northwestern Hwy Suite 100, Southf, engagement.lender_address=29444 Northwestern Hwy Suite 100, Southf
- **Why VERIFY / reviewer line:** Expected Company Address must match the Client Engagement letter address; found lender_address: "29444 Northwestern Hwy Suite 100, Southfield, MI 48034" vs engagement.lender_address: "29444 Northwestern Hwy Suite 100, Southfield MI 48034".

### EQ-113 — Inventory Analysis

- **Section:** MC_1004  |  **Scope:** cross_section  |  **Card group:** please_verify  |  **Bound by:** llm (conf 0.2)
- **Check language:** Inventory Analysis — All lightly shaded areas are required to be completed or a specific comment as to why they cannot be. Required blank spaces should be completed with a "0" if there are none or N/A.
- **Rejection text:** _(none authored)_
- **Bound labels:** _(none — unbound)_
- **Condition (`expects`):** _(empty — no predicate → auto-VERIFY)_
- **Conditional:** condition=['contract_analysis_comment', 'mca_neighborhood_analysis_comment', 'prior_sale_analysis_comment', 'site_area'] → consequence=['appraised_value', 'are_facilities_complete', 'commercial_space_pct', 'comp_count_present']
- **Found (extracted):** No data for contract_analysis_comment, mca_neighborhood_analysis_comment; other fields present.  |  **Expected:** All lightly shaded areas must be completed or commented; blanks as "0" or N/A.
- **Resolved values:** prior_sale_analysis_comment=The subject property was previously sold, site_area=4800 sf, appraised_value=245000, comp_count_present=7
- **Why VERIFY / reviewer line:** Condition cannot be fully evaluated due to missing contract and neighborhood comments; please verify compliance.

### EQ-114 — Total # of Comparables Sales (Settled)

- **Section:** MC_1004  |  **Scope:** comps  |  **Card group:** please_verify  |  **Bound by:** llm (conf 0.95)
- **Check language:** Total # of Comparables Sales (Settled) — All fields must total to the data provided on the top of the sales grid for Comparables sales in the subject neighborhood.
- **Rejection text:** _(none authored)_
- **Bound labels:** comp_count_present
- **Condition (`expects`):** comp_count_present == total comps in grid
- **Found (extracted):** comp_count_present = "7" (no top‑grid total provided in packet)  |  **Expected:** Total number of settled comparable sales should match the count shown at the top of the sales grid for the subject neighborhood.
- **Resolved values:** comp_count_present=7
- **Why VERIFY / reviewer line:** Expected total comparable count from top of grid, but only a count of 7 is present; verify the grid total.

### EQ-115 — Total # of Comparable Active Listings

- **Section:** MC_1004  |  **Scope:** cross_section  |  **Card group:** please_verify  |  **Bound by:** llm (conf 0.6)
- **Check language:** Total # of Comparable Active Listings — If completed, all fields should match the information provided at the top of the sales grid for Comparable properties currently offered for sale. If all fields not complete, the Current‐3 months must match the data given at the top of the sales grid.
- **Rejection text:** _(none authored)_
- **Bound labels:** mca_active_listings_current_3
- **Condition (`expects`):** _(empty — no predicate → auto-VERIFY)_
- **Conditional:** condition=['comp_N_is_listing', 'comp_N_room_count_total', 'comp_count_present', 'land_use_total'] → consequence=['comp_count_present', 'appraised_value', 'comp_N_adjusted_sale_price', 'comp_N_data_source']
- **Found (extracted):** Many listing and room count fields absent, preventing condition evaluation.  |  **Expected:** All fields for comparable active listings must match top of sales grid or current 3‑month data must match.
- **Resolved values:** comp_count_present=7, appraised_value=245000, comp_1_adjusted_sale_price=232560, comp_2_adjusted_sale_price=245195, comp_3_adjusted_sale_price=246780, comp_4_adjusted_sale_price=233816
- **Why VERIFY / reviewer line:** Missing required listing and room count data makes it unclear if the check is satisfied; please verify.

### EQ-116 — Median Sale & List Price, DOM, Sale/List %

- **Section:** MC_1004  |  **Scope:** subject  |  **Card group:** please_verify  |  **Bound by:** manual (conf 0.9)
- **Check language:** Median Sale & List Price, DOM, Sale/List % — All lightly shaded areas are required to be completed or a specific comment as to why they cannot be. Required blank spaces should be completed with a "0" if there are none or N/A. If dark shaded areas cannot be provided, N/A should be provided.
- **Rejection text:** _(none authored)_
- **Bound labels:** mca_median_sale_price_prior_7_12, mca_median_sale_price_prior_4_6, mca_median_sale_price_current_3, mca_median_list_price_prior_7_12, mca_median_list_price_prior_4_6, mca_median_list_price_current_3, mca_median_dom_prior_7_12, mca_median_dom_prior_4_6, mca_median_dom_current_3, mca_median_list_dom_prior_7_12, mca_median_list_dom_prior_4_6, mca_median_list_dom_current_3, mca_median_sale_list_ratio_prior_7_12, mca_median_sale_list_ratio_prior_4_6, mca_median_sale_list_ratio_current_3
- **Condition (`expects`):** SATISFIED when every bound field has ANY value. A currency ("$415,000"), percent ("98%"), integer, "0", or "N/A" all count as filled. Do not require a particular format. Only REVIEW if a listed field is genuinely blank/absent.
- **Found (extracted):** Various median values present; mca_median_sale_list_ratio_prior_7_12 missing  |  **Expected:** All lightly shaded fields must be completed or commented/N/A
- **Resolved values:** mca_median_sale_price_prior_7_12=$261,290, mca_median_sale_price_prior_4_6=$253,390, mca_median_sale_price_current_3=$263,770, mca_median_list_price_prior_7_12=$286,208, mca_median_list_price_prior_4_6=$317,490, mca_median_list_price_current_3=$308,573
- **Why VERIFY / reviewer line:** Most required fields are filled but one lightly shaded field is absent; please verify.

### EQ-118 — Commentary

- **Section:** MC_1004  |  **Scope:** narrative  |  **Card group:** please_verify  |  **Bound by:** llm (conf 0.92)
- **Check language:** Commentary — Must be completed for each section and adequately explain the data provided above. Must be specific to the report and no canned commentary is acceptable.
- **Rejection text:** _(none authored)_
- **Bound labels:** market_conditions_commentary
- **Condition (`expects`):** non_canned
- **Found (extracted):** Currently property values in the subject neighborhood are felt to be stable and competitively priced properties are felt to have a marketing time of 0-3 months. Currently there is a demand for single family residences in the area without an oversupply.  |  **Expected:** Commentary must be specific to the report and not canned
- **Resolved values:** market_conditions_commentary=Currently property values in the subject
- **Why VERIFY / reviewer line:** Expected report‑specific, non‑canned commentary; found generic market commentary – please verify originality.

### EQ-119 — Condo/Co‐Op Projects

- **Section:** MC_1004  |  **Scope:** cross_section  |  **Card group:** please_verify  |  **Bound by:** llm (conf 0.6)
- **Check language:** Condo/Co‐Op Projects — All lightly shaded areas must be completed if the subject is a Condo Co‐ Op and deal specifically with the subject's project.
- **Rejection text:** _(none authored)_
- **Bound labels:** project_name, project_phase, unit_number
- **Condition (`expects`):** project_name && project_phase && unit_number
- **Conditional:** condition=['unit_number', 'comp_N_project_name', 'is_project_from_conversion', 'mca_project_months_supply_current_3'] → consequence=['unit_number', 'appraisal_subject_to', 'appraised_value', 'are_facilities_complete']
- **Found (extracted):** Key project fields (unit_number, project names, conversion flag) are absent, so condition cannot be assessed.  |  **Expected:** All lightly shaded areas must be completed if subject is a Condo/Co‑Op and address the project.
- **Resolved values:** project_name=work,, appraisal_subject_to=As Is, appraised_value=245000
- **Why VERIFY / reviewer line:** Cannot determine if condo/co‑op sections are completed due to missing required fields; please review.

### EQ-120 — Commentary

- **Section:** MC_1004  |  **Scope:** narrative  |  **Card group:** please_verify  |  **Bound by:** llm (conf 0.92)
- **Check language:** Commentary — Must be completed for each section and adequately explain the data provided above. Must be specific to the report and no canned commentary is acceptable.
- **Rejection text:** _(none authored)_
- **Bound labels:** market_conditions_commentary
- **Condition (`expects`):** non_canned
- **Found (extracted):** Currently property values in the subject neighborhood are felt to be stable and competitively priced properties are felt to have a marketing time of 0-3 months. Currently there is a demand for single family residences in the area without an oversupply.  |  **Expected:** Commentary must be specific to the report and not canned
- **Resolved values:** market_conditions_commentary=Currently property values in the subject
- **Why VERIFY / reviewer line:** Expected report‑specific, non‑canned commentary; found generic market commentary – please verify originality.

### EQ-121 — Appraisal and report Identification

- **Section:** USPAP  |  **Scope:** subject  |  **Card group:** please_verify  |  **Bound by:** llm (conf 0.95)
- **Check language:** Appraisal and report Identification — Must be completed and only 2 choices should be available, Appraisal Report and Restricted Appraisal Report.
- **Rejection text:** _(none authored)_
- **Bound labels:** appraisal_report_type
- **Condition (`expects`):** value in {Appraisal Report, Restricted Appraisal Report}
- **Found (extracted):** (no appraisal_report_type value present)  |  **Expected:** Appraisal Report type must be completed with one of two choices
- **Why VERIFY / reviewer line:** Appraisal report type is missing; need to confirm if it was omitted or not captured.

### EQ-122 — Reasonable Exposure Time

- **Section:** USPAP  |  **Scope:** subject  |  **Card group:** please_verify  |  **Bound by:** llm (conf 0.96)
- **Check language:** Reasonable Exposure Time — Must be provided as a single point or range in time. (i.e. 90 or 30‐60) Additional commentary is suggested but not required.
- **Rejection text:** _(none authored)_
- **Bound labels:** reasonable_exposure_time
- **Condition (`expects`):** len(reasonable_exposure_time) > 0
- **Found (extracted):** (no reasonable_exposure_time value present)  |  **Expected:** Reasonable Exposure Time must be provided
- **Why VERIFY / reviewer line:** Reasonable exposure time is absent; please verify whether it was omitted.

### EQ-123 — Additional Certifications

- **Section:** USPAP  |  **Scope:** cross_section  |  **Card group:** please_verify  |  **Bound by:** llm (conf 0.3)
- **Check language:** Additional Certifications — Must be provided, if the "I HAVE performed services" is checked, additional commentary is Required to state what those prior services are.
- **Rejection text:** _(none authored)_
- **Bound labels:** _(none — unbound)_
- **Condition (`expects`):** _(empty — no predicate → auto-VERIFY)_
- **Conditional:** condition=['appraiser_state_cert_number', 'appraiser_cert_expiration_date', 'appraiser_cert_state', 'supervisory_appraiser_cert_number'] → consequence=['prior_services_performed', 'is_pud_checked', 'is_seller_owner_of_record', 'prior_sale_analysis_comment']
- **Found (extracted):** Supervisory_appraiser_cert_number is absent, preventing condition evaluation.  |  **Expected:** If "I HAVE performed services" is checked, additional commentary must state prior services.
- **Resolved values:** appraiser_state_cert_number=1323873-CR, appraiser_cert_expiration_date=2026-10-31, appraiser_cert_state=#, is_pud_checked=Yes, prior_sale_analysis_comment=The subject property was previously sold
- **Why VERIFY / reviewer line:** Condition cannot be fully read because supervisory certification is missing; verify if prior services comment is required.

### EQ-124 — Subject Photo Pages

- **Section:** EXHIBITS  |  **Scope:** visual  |  **Card group:** manual_visual  |  **Bound by:** constant (conf 1.0)
- **Check language:** Subject Photo Pages — At a minimum, subject front, rear and street scene photos are required. Verify with client Engagement letter if additional side, street and address verification photos are required. If any obsolescence is observed in photos, commentary must be provided.
- **Rejection text:** _(none authored)_
- **Bound labels:** _(none — unbound)_
- **Condition (`expects`):** _(empty — no predicate → auto-VERIFY)_
- **Found (extracted):** __NO_EXTRACTED_VALUE__  |  **Expected:** __NO_EXPECTED_VALUE__
- **Why VERIFY / reviewer line:** Manual visual check: Subject Photo Pages — At a minimum, subject front, rear and street scene photos are required. Verify with client Engagement letter if additional side, street and address verificati — review the photos/sketch/map by eye.

### EQ-125 — Interior photos

- **Section:** EXHIBITS  |  **Scope:** unbound  |  **Card group:** manual_visual  |  **Bound by:** llm (conf 0.3)
- **Check language:** Interior photos — Photos of all rooms (Kitchen, living room, dining room, family room, bedrooms and all baths) are required for all interior inspection reports. Photos of any deferred maintenance must be provided. Photos must be labeled with the specific room name.
- **Rejection text:** _(none authored)_
- **Bound labels:** _(none — unbound)_
- **Condition (`expects`):** _(empty — no predicate → auto-VERIFY)_
- **Found (extracted):** __NO_EXTRACTED_VALUE__  |  **Expected:** __NO_EXPECTED_VALUE__
- **Why VERIFY / reviewer line:** Manual visual check: Interior photos — Photos of all rooms (Kitchen, living room, dining room, family room, bedrooms and all baths) are required for all interior inspection reports. Photos of any defer — review the photos/sketch/map by eye.

### EQ-126 — Additional Subject photos

- **Section:** EXHIBITS  |  **Scope:** cross_section  |  **Card group:** please_verify  |  **Bound by:** llm (conf 0.2)
- **Check language:** Additional Subject photos — Photos of all outbuildings and special features (pools, etc.) are required. All outbuildings must have interior photos as well as photos of any deferred maintenance for the subject. Photos of any exterior obsolescence should be provided. Photos containing people or interior personal pictures should be avoided if possible.
- **Rejection text:** _(none authored)_
- **Bound labels:** _(none — unbound)_
- **Condition (`expects`):** _(empty — no predicate → auto-VERIFY)_
- **Conditional:** condition=['photo_front', 'photo_rear', 'appraisal_subject_to', 'is_subject_to_ground_rent'] → consequence=['photo_front', 'photo_rear', 'appraisal_subject_to', 'contract_date']
- **Found (extracted):** No photo fields (photo_front, photo_rear) present in packet.  |  **Expected:** Photos of all outbuildings and special features, interior photos of outbuildings, deferred maintenance, exterior obsolescence; avoid people/personal pictures.
- **Resolved values:** appraisal_subject_to=As Is
- **Why VERIFY / reviewer line:** Check requires multiple subject photos, but the packet contains no photo fields, so a human should verify the presence of required images.

### EQ-127 — Comparable Photos

- **Section:** EXHIBITS  |  **Scope:** unbound  |  **Card group:** please_verify  |  **Bound by:** llm (conf 0.2)
- **Check language:** Comparable Photos — For Convential loans, MLS photos are acceptable, however, there should be commentary in the report that states that they did in fact drive by them.
- **Rejection text:** _(none authored)_
- **Bound labels:** _(none — unbound)_
- **Condition (`expects`):** _(empty — no predicate → auto-VERIFY)_
- **Found (extracted):** No commentary on drive‑by inspection of MLS photos present  |  **Expected:** Commentary stating that MLS photos were drive‑by inspected for conventional loans
- **Why VERIFY / reviewer line:** The report lacks the required drive‑by commentary for MLS photos; please verify.

### EQ-128 — Sketch

- **Section:** EXHIBITS  |  **Scope:** visual  |  **Card group:** manual_visual  |  **Bound by:** constant (conf 1.0)
- **Check language:** Sketch — Sketch must be located on the Floor plan Sketch page that is provided in the appraisal software. Must have all floors. Exterior dimension must be provided and all rooms must be labeled and match the number of rooms reported in the sales grid. All outbuildings and garages or any other structure that contributes to value must be on the sketch with proper dimensions.
- **Rejection text:** _(none authored)_
- **Bound labels:** _(none — unbound)_
- **Condition (`expects`):** _(empty — no predicate → auto-VERIFY)_
- **Found (extracted):** __NO_EXTRACTED_VALUE__  |  **Expected:** __NO_EXPECTED_VALUE__
- **Why VERIFY / reviewer line:** Manual visual check: Sketch — Sketch must be located on the Floor plan Sketch page that is provided in the appraisal software. Must have all floors. Exterior dimension must be provided and all rooms mu — review the photos/sketch/map by eye.

### EQ-129 — Area Calculations

- **Section:** EXHIBITS  |  **Scope:** visual  |  **Card group:** manual_visual  |  **Bound by:** constant (conf 1.0)
- **Check language:** Area Calculations — Must be provided, usually found at the bottom of the sketch page.
- **Rejection text:** _(none authored)_
- **Bound labels:** _(none — unbound)_
- **Condition (`expects`):** _(empty — no predicate → auto-VERIFY)_
- **Found (extracted):** __NO_EXTRACTED_VALUE__  |  **Expected:** __NO_EXPECTED_VALUE__
- **Why VERIFY / reviewer line:** Manual visual check: Area Calculations — Must be provided, usually found at the bottom of the sketch page. — review the photos/sketch/map by eye.

### EQ-13 — Subject Listed/Sold within 12 Months

- **Section:** SUBJECT  |  **Scope:** cross_section  |  **Card group:** please_verify  |  **Bound by:** llm (conf 0.6)
- **Check language:** Subject Listed/Sold within 12 Months If there are no prior listings or current sale, this should be marked no and the appraiser MUST include the data source. Must state the MLS abreviated name for the area. IE. MXLMLS \| Trigger: If there are no prior listings or current sale No should be mark and include data source. If the subject IS listed or has a current sale, the field must be in this format: DOM #; Abbreviated MLS name and MLS #. Current list/sale price, current list/sale date. (THIS MUST BE ON PAGE 1) Any additional data can be included in the report addendum. If the subject has been listed but NOT a purchase, a comment must be provided if the opinion of market value varies by the most recent listing price by more than 3% \| Trigger: If currently listed marked as Yes
- **Rejection text:** Please provide Data sources in subject section for the question “Is the subject property currently offered for sale or has it been offered for sale in the twelve months prior to the effective date of this appraisal?” as per UAD requirement.
- **Bound labels:** data_source, days_on_market, list_price, list_date, mls_number
- **Condition (`expects`):** if offerred_for_sale_12mo == false then data_source present; if true then days_on_market, list_price, list_date, mls_number present
- **Conditional:** condition=['mca_median_sale_list_ratio_prior_7_12', 'prior_sale_data_source_subject', 'prior_sale_date_subject', 'prior_sale_effective_date_subject'] → consequence=['prior_sale_data_source_subject', 'prior_sale_date_subject', 'prior_sale_effective_date_subject', 'prior_sale_price_subject']
- **Found (extracted):** Condition labels include mca_median_sale_list_ratio_prior_7_12 (absent), prior_sale_data_source_subject (present), prior_sale_date_subject (present), prior_sale_effective_date_subject (present).  |  **Expected:** Condition must be evaluable; if prior sale data indicates no prior listings/sale, then data source must be provided, otherwise listing info formatted as DOM #; MLS name; MLS # etc.
- **Resolved values:** data_source=used, offering price(s),, mls_number=Houston, prior_sale_data_source_subject=used, offering price(s),, prior_sale_date_subject=2024-07-23, prior_sale_effective_date_subject=07/07/2026 07/07/2026 07/07/2026 07/07/2, prior_sale_price_subject=$240,000
- **Why VERIFY / reviewer line:** Expected Condition must be evaluable; if prior sale data indicates no prior listings/sale, then data source must be provided, otherwise listing info formatted as DOM #; MLS name; MLS # etc.; found Condition labels include mca_median_sale_li

### EQ-130 — Aerial Map

- **Section:** EXHIBITS  |  **Scope:** visual  |  **Card group:** manual_visual  |  **Bound by:** constant (conf 1.0)
- **Check language:** Aerial Map — Aerial map must be provided. \| Triggers: If missing reject as : Please Provide Aerial Map In the Report.
- **Rejection text:** _(none authored)_
- **Bound labels:** _(none — unbound)_
- **Condition (`expects`):** _(empty — no predicate → auto-VERIFY)_
- **Found (extracted):** __NO_EXTRACTED_VALUE__  |  **Expected:** __NO_EXPECTED_VALUE__
- **Why VERIFY / reviewer line:** Manual visual check: Aerial Map — Aerial map must be provided. \| Triggers: If missing reject as : Please Provide Aerial Map In the Report. — review the photos/sketch/map by eye.

### EQ-131 — Location Map

- **Section:** EXHIBITS  |  **Scope:** visual  |  **Card group:** manual_visual  |  **Bound by:** constant (conf 1.0)
- **Check language:** Location Map — Location map must show the subject and all comparables with sufficient detail to identify their relative locations.
- **Rejection text:** _(none authored)_
- **Bound labels:** _(none — unbound)_
- **Condition (`expects`):** _(empty — no predicate → auto-VERIFY)_
- **Found (extracted):** __NO_EXTRACTED_VALUE__  |  **Expected:** __NO_EXPECTED_VALUE__
- **Why VERIFY / reviewer line:** Manual visual check: Location Map — Location map must show the subject and all comparables with sufficient detail to identify their relative locations. — review the photos/sketch/map by eye.

### EQ-132 — Plat Map

- **Section:** EXHIBITS  |  **Scope:** visual  |  **Card group:** manual_visual  |  **Bound by:** constant (conf 1.0)
- **Check language:** Plat Map — Is required if Site Dimensions can not be provided on page 1.
- **Rejection text:** _(none authored)_
- **Bound labels:** _(none — unbound)_
- **Condition (`expects`):** _(empty — no predicate → auto-VERIFY)_
- **Found (extracted):** __NO_EXTRACTED_VALUE__  |  **Expected:** __NO_EXPECTED_VALUE__
- **Why VERIFY / reviewer line:** Manual visual check: Plat Map — Is required if Site Dimensions can not be provided on page 1. — review the photos/sketch/map by eye.

### EQ-133 — Flood Map

- **Section:** EXHIBITS  |  **Scope:** visual  |  **Card group:** manual_visual  |  **Bound by:** constant (conf 1.0)
- **Check language:** Flood Map — Is required if the subject is located in a Flood Zone.
- **Rejection text:** _(none authored)_
- **Bound labels:** _(none — unbound)_
- **Condition (`expects`):** _(empty — no predicate → auto-VERIFY)_
- **Found (extracted):** __NO_EXTRACTED_VALUE__  |  **Expected:** __NO_EXPECTED_VALUE__
- **Why VERIFY / reviewer line:** Manual visual check: Flood Map — Is required if the subject is located in a Flood Zone. — review the photos/sketch/map by eye.

### EQ-134 — Appraisers License

- **Section:** EXHIBITS  |  **Scope:** cross_section  |  **Card group:** please_verify  |  **Bound by:** llm (conf 0.2)
- **Check language:** Appraisers License — Appraiser's License copy must be included in the report. And must match information with signature page. \| Triggers: If license is provided before the signature date reject as: 1. Please provide an updated copy of your License, as the copy provided in the report has expired.
- **Rejection text:** _(none authored)_
- **Bound labels:** _(none — unbound)_
- **Condition (`expects`):** _(empty — no predicate → auto-VERIFY)_
- **Conditional:** condition=['appraiser_cert_expiration_date', 'appraiser_cert_state', 'appraiser_company_address', 'appraiser_company_name'] → consequence=['contract_date', 'fha_case_number', 'date_of_signature', 'date_report_signed']
- **Found (extracted):** License copy field not present in packet.  |  **Expected:** Appraiser's License copy must be included in the report.
- **Resolved values:** appraiser_cert_expiration_date=2026-10-31, appraiser_cert_state=#, appraiser_company_address=10219 Silver Leaf Lane, Tomball, TX 7737, appraiser_company_name=MCA Inc., date_of_signature=2026-07-08, date_report_signed=2026-07-08
- **Why VERIFY / reviewer line:** License copy is required but not found in the data; a reviewer should confirm whether it is included elsewhere.

### EQ-14 — Did & Did Not box

- **Section:** CONTRACT  |  **Scope:** cross_section  |  **Card group:** please_verify  |  **Bound by:** llm (conf 0.95)
- **Check language:** Did & Did Not box — I did did not analyze the contract for sale for the subject purchase transaction. Explain the results of the analysis of the contract for sale or why the analysis was not performed. \| Triggers: If Assignment Type is for Re-finance then contract section must be blank.
- **Rejection text:** _(none authored)_
- **Bound labels:** did_analyze_contract, contract_analysis_comment, assignment_type
- **Condition (`expects`):** _(empty — no predicate → auto-VERIFY)_
- **Conditional:** condition=['assignment_type'] → consequence=['did_analyze_contract', 'contract_analysis_comment']
- **Found (extracted):** did_analyze_contract = True (checked).  |  **Expected:** For a Refinance assignment, the contract analysis box must be blank (no analysis performed).
- **Resolved values:** did_analyze_contract=True, assignment_type=Refinance Transaction
- **Why VERIFY / reviewer line:** Expected no contract analysis for refinance, but found analysis box checked; recommend reject.

### EQ-17 — Data Source(s)

- **Section:** CONTRACT  |  **Scope:** subject  |  **Card group:** please_verify  |  **Bound by:** llm (conf 0.85)
- **Check language:** Data Source(s) — Data source is compulsory \| Triggers: Is the property seller the owner of public record? if checkbox marked for yes and data source is missing
- **Rejection text:** Please provide data source for "Is the property seller the owner of public record?" under contract section
- **Bound labels:** data_source, is_seller_owner_of_record
- **Condition (`expects`):** data_source present when seller is owner of public record
- **Found (extracted):** data_source present ("used, offering price(s),"); is_seller_owner_of_record label absent  |  **Expected:** Data source must be provided when "Is the property seller the owner of public record?" is checked Yes
- **Resolved values:** data_source=used, offering price(s),
- **Why VERIFY / reviewer line:** Cannot determine if seller ownership checkbox was Yes; data source is present but condition unknown, please verify.

### EQ-18 — Is there any financial assistance (loan charges, sale concessions, gift or downpayment assistance, etc.) to be paid by any party on behalf of the borrower?

- **Section:** CONTRACT  |  **Scope:** cross_section  |  **Card group:** please_verify  |  **Bound by:** llm (conf 0.6)
- **Check language:** Is there any financial assistance (loan charges, sale concessions, gift or downpayment assistance, etc.) to be paid by any party on behalf of the borrower? — Is there any financial assistance (loan charges, sale concessions, gift or downpayment assistance, etc.) to be paid by any party on behalf of the borrower? check yes or no checkbox. \| Triggers: If Yes, report the total dollar amount and describe the items to be paid. ( check from Purchase Agreement); If no, then report the total dollar amount and describe the items to be paid shoule apply "0" check from Purchase agreement. \| Trigger: if concession is given but different from purchase agreement
- **Rejection text:** _(none authored)_
- **Bound labels:** has_financial_assistance, financial_assistance_amount, financial_assistance_description
- **Condition (`expects`):** if has_financial_assistance then financial_assistance_amount > 0 and financial_assistance_description non-empty
- **Conditional:** condition=['financial_assistance_amount', 'concessions_amount', 'financial_assistance_description', 'has_financial_assistance'] → consequence=['stories_in_building', 'appraisal_report_type', 'comp_N_room_count_total', 'concessions_amount']
- **Found (extracted):** All condition labels (financial_assistance_amount, concessions_amount, financial_assistance_description, has_financial_assistance) are absent.  |  **Expected:** If financial assistance is present, report amount and description; if not, report $0.
- **Why VERIFY / reviewer line:** Missing financial assistance fields prevents evaluating the requirement; please verify presence and values.

### EQ-19 — Characteristcis & Housing Trends

- **Section:** NEIGHBORHOOD  |  **Scope:** cross_section  |  **Card group:** please_verify  |  **Bound by:** llm (conf 0.3)
- **Check language:** Characteristcis & Housing Trends — Neighborhood Characteristics and One-Unit Housing Trends At least 1 box should be checked \| Triggers: if checkbox is missing : reject as In the neighborhood section checbox is missing for _____, please revise.
- **Rejection text:** _(none authored)_
- **Bound labels:** location, built_up, growth_rate, property_values, demand_supply, marketing_time
- **Condition (`expects`):** count(comp_* present) >= 1
- **Conditional:** condition=['comp_N_unit_number', 'conforms_to_neighborhood', 'floor_location', 'land_use_2_4_unit'] → consequence=['is_pud_checked', 'conforms_to_neighborhood', 'did_analyze_contract', 'lease_dates']
- **Found (extracted):** No explicit checkbox labels are present; only selection fields like location, built_up, etc.  |  **Expected:** At least one neighborhood characteristics box must be checked.
- **Resolved values:** location=Suburban, built_up=Over 75%, growth_rate=Stable, property_values=Stable, demand_supply=In Balance, marketing_time=Under 3 mths
- **Why VERIFY / reviewer line:** No checkbox evidence found for neighborhood characteristics; please confirm a box is checked.

### EQ-21 — Unit Housing Price and Age

- **Section:** NEIGHBORHOOD  |  **Scope:** cross_section  |  **Card group:** please_verify  |  **Bound by:** llm (conf 0.6)
- **Check language:** Unit Housing Price and Age — Appraiser to provide and be aware of the high and low prices given. The unadjusted sales prices of the comparables used in the report must fall within the ranges unless comps are not located within the neighborhood (comment required). Comment required if the Market value differs from Predominant by more than 10%, over or under improved and does it affect marketability? Trend should match MC form or specific commentary is required.
- **Rejection text:** _(none authored)_
- **Bound labels:** price_high, price_low, predominant_price, market_value_opinion
- **Condition (`expects`):** price_high and price_low present; abs(market_value_opinion - predominant_price) <= 0.10 * predominant_price
- **Conditional:** condition=['appraised_value', 'comp_N_adjusted_sale_price', 'comp_N_sale_price', 'comp_count_present', 'year_built', 'effective_age'] → consequence=['market_conditions_commentary', 'appraised_value', 'is_seller_owner_of_record', 'market_value_opinion']
- **Found (extracted):** __NO_EXTRACTED_VALUE__  |  **Expected:** __NO_EXPECTED_VALUE__
- **Resolved values:** price_high=700, price_low=140, predominant_price=265, appraised_value=245000, comp_1_adjusted_sale_price=232560, comp_2_adjusted_sale_price=245195
- **Why VERIFY / reviewer line:** Automated judgment was unavailable for this check — please review the values shown.

### EQ-23 — Boundaries

- **Section:** NEIGHBORHOOD  |  **Scope:** cross_section  |  **Card group:** please_verify  |  **Bound by:** llm (conf 0.6)
- **Check language:** Boundaries — Neighborhood Boundaries : all boundaries should be described \| Triggers: If missing : reject as ____ boundary is missing under Neighborhood Boundries , please revise.
- **Rejection text:** _(none authored)_
- **Bound labels:** neighborhood_boundaries
- **Condition (`expects`):** neighborhood_boundaries present
- **Conditional:** condition=['neighborhood_boundaries', 'conforms_to_neighborhood', 'mca_neighborhood_analysis_comment', 'neighborhood_description'] → consequence=['conforms_to_neighborhood', 'lease_dates', 'mca_neighborhood_analysis_comment', 'neighborhood_boundaries']
- **Found (extracted):** __NO_EXTRACTED_VALUE__  |  **Expected:** __NO_EXPECTED_VALUE__
- **Resolved values:** neighborhood_boundaries=The subject area is bounded to the north, conforms_to_neighborhood=Yes, neighborhood_description=The subject property is located approxim
- **Why VERIFY / reviewer line:** Automated judgment was unavailable for this check — please review the values shown.

### EQ-30 — Zoning Classification, Description and Compliance

- **Section:** SITE  |  **Scope:** cross_section  |  **Card group:** please_verify  |  **Bound by:** llm (conf 0.6)
- **Check language:** Zoning Classification, Description and Compliance — Zoning Compliance atleast one box should be checked. (legal, legal non-conferming and No zoning) \| Triggers: If legal checked no comment needed; if legal non-conferming or No zoning then add rejection:1. Zoning Compliance is marked on ’No Zoning’, please comment if the subject can be rebuilt if destroyed. \| Trigger: If illigal is marked Specific Zoning Classification and Zoning Description : should be fill up \| Trigger: if blank then add rejection
- **Rejection text:** _(none authored)_
- **Bound labels:** zoning_compliance, zoning_classification
- **Condition (`expects`):** if zoning_compliance != 'legal' then zoning_classification non-empty
- **Conditional:** condition=['zoning_classification', 'zoning_compliance', 'appraised_value', 'common_elements_description'] → consequence=['legal_description', 'zoning_classification', 'zoning_compliance', 'appraisal_subject_to']
- **Found (extracted):** __NO_EXTRACTED_VALUE__  |  **Expected:** __NO_EXPECTED_VALUE__
- **Resolved values:** zoning_compliance=No Zoning, zoning_classification=Deed Restricted SFR, appraised_value=245000, common_elements_description=Foxwood Meadows HOA - common area landsc, legal_description=LT 4 BLK 1 FOXWOOD MEADOWS, appraisal_subject_to=As Is
- **Why VERIFY / reviewer line:** Automated judgment was unavailable for this check — please review the values shown.

### EQ-32 — Utilities/Off‐Site Improvement Type

- **Section:** SITE  |  **Scope:** cross_section  |  **Card group:** please_verify  |  **Bound by:** llm (conf 0.6)
- **Check language:** Utilities/Off‐Site Improvement Type — Utilities and Off-site Improvements - Type (Gas and Electricity checbok should be marked) \| Triggers: if street is marked as private then add rejection
- **Rejection text:** _(none authored)_
- **Bound labels:** utilities_gas, utilities_electricity
- **Condition (`expects`):** utilities_gas == True && utilities_electricity == True
- **Conditional:** condition=['utilities_electricity', 'adverse_site_conditions', 'air_conditioning_type', 'appraisal_report_type'] → consequence=['photo_street', 'property_address']
- **Found (extracted):** __NO_EXTRACTED_VALUE__  |  **Expected:** __NO_EXPECTED_VALUE__
- **Resolved values:** utilities_gas=Public, utilities_electricity=Public, adverse_site_conditions=No, air_conditioning_type=Patio/Deck Conc, property_address=7243 Foxtail Meadow Ct
- **Why VERIFY / reviewer line:** Automated judgment was unavailable for this check — please review the values shown.

### EQ-36 — General description should be fill up

- **Section:** IMPROVEMENTS  |  **Scope:** visual  |  **Card group:** manual_visual  |  **Bound by:** constant (conf 1.0)
- **Check language:** General description should be fill up — if one unit checkbox marked then photos, sketch and sales grid should match \| Triggers: if one with accesssory checkbox is marked then sales grid and sketch should reflects ADU
- **Rejection text:** _(none authored)_
- **Bound labels:** _(none — unbound)_
- **Condition (`expects`):** _(empty — no predicate → auto-VERIFY)_
- **Found (extracted):** __NO_EXTRACTED_VALUE__  |  **Expected:** __NO_EXPECTED_VALUE__
- **Why VERIFY / reviewer line:** Manual visual check: General description should be fill up — if one unit checkbox marked then photos, sketch and sales grid should match \| Triggers: if one with accesssory checkbox is marked then sales — review the photos/sketch/map by eye.

### EQ-39 — Type

- **Section:** IMPROVEMENTS  |  **Scope:** visual  |  **Card group:** manual_visual  |  **Bound by:** constant (conf 1.0)
- **Check language:** Type — Existing Proposed Under construction \| Trigger: If photo detected work is going on then this checkbox should be selected
- **Rejection text:** _(none authored)_
- **Bound labels:** _(none — unbound)_
- **Condition (`expects`):** _(empty — no predicate → auto-VERIFY)_
- **Found (extracted):** __NO_EXTRACTED_VALUE__  |  **Expected:** __NO_EXPECTED_VALUE__
- **Why VERIFY / reviewer line:** Manual visual check: Type — Existing Proposed Under construction \| Trigger: If photo detected work is going on then this checkbox should be selected — review the photos/sketch/map by eye.

### EQ-4 — Tax Year

- **Section:** SUBJECT  |  **Scope:** subject  |  **Card group:** please_verify  |  **Bound by:** llm (conf 0.95)
- **Check language:** Tax Year — Must be latest or last 2 year (This field should not be blank)
- **Rejection text:** _(none authored)_
- **Bound labels:** tax_year
- **Condition (`expects`):** tax_year not blank and tax_year >= current_year-2
- **Found (extracted):** tax_year = "2025"  |  **Expected:** Tax Year must be the latest or within the last 2 years and not blank
- **Resolved values:** tax_year=2025
- **Why VERIFY / reviewer line:** Tax Year is provided as 2025 but cannot confirm it is the latest or within the last two years; please verify.

### EQ-40 — Design (Style):

- **Section:** IMPROVEMENTS  |  **Scope:** subject  |  **Card group:** please_verify  |  **Bound by:** llm (conf 0.9)
- **Check language:** Design (Style): — Structural build type
- **Rejection text:** _(none authored)_
- **Bound labels:** design_style
- **Condition (`expects`):** design_style present
- **Found (extracted):** design_style = "Ranch"  |  **Expected:** Structural build type
- **Resolved values:** design_style=Ranch
- **Why VERIFY / reviewer line:** Expected a structural build type but only design style "Ranch" was found; please verify.

### EQ-43 — Attic

- **Section:** IMPROVEMENTS  |  **Scope:** visual  |  **Card group:** manual_visual  |  **Bound by:** constant (conf 1.0)
- **Check language:** Attic — Attic atleast 1 checbox should be checked \| Triggers: if photo is provided of attic and None is marked in improvement section reject for checkbox
- **Rejection text:** Photo of attic is provided in the report however in the improvement section the attic box is not marked, please verify
- **Bound labels:** _(none — unbound)_
- **Condition (`expects`):** _(empty — no predicate → auto-VERIFY)_
- **Found (extracted):** __NO_EXTRACTED_VALUE__  |  **Expected:** __NO_EXPECTED_VALUE__
- **Why VERIFY / reviewer line:** Manual visual check: Attic — Attic atleast 1 checbox should be checked \| Triggers: if photo is provided of attic and None is marked in improvement section reject for checkbox — review the photos/sketch/map by eye.

### EQ-44 — Foundation

- **Section:** IMPROVEMENTS  |  **Scope:** cross_section  |  **Card group:** please_verify  |  **Bound by:** llm (conf 0.6)
- **Check language:** Foundation — FOUNDATION checkbox is compulsory \| Triggers: If Full basement or Partial Basement checbox is marked than basement area and Basement finished must be mentioned \| Trigger: if basement is marked as full or partial basement with Outside Entry/exit Evidence of Infestation, Dampness and Settlement \| Trigger: if checkbox is marked check commentary for adversity
- **Rejection text:** _(none authored)_
- **Bound labels:** foundation_type, adverse_conditions
- **Condition (`expects`):** foundation_type present && adverse_conditions present
- **Conditional:** condition=['appraised_value', 'comp_N_basement_gla', 'comp_count_present', 'did_analyze_contract'] → consequence=['comp_N_basement_gla', 'contract_analysis_comment', 'did_analyze_contract', 'fha_case_number']
- **Found (extracted):** __NO_EXTRACTED_VALUE__  |  **Expected:** __NO_EXPECTED_VALUE__
- **Resolved values:** adverse_conditions=No, appraised_value=245000, comp_count_present=7, did_analyze_contract=True
- **Why VERIFY / reviewer line:** Automated judgment was unavailable for this check — please review the values shown.

### EQ-45 — Exterior and Interior Description should

- **Section:** IMPROVEMENTS  |  **Scope:** cross_section  |  **Card group:** please_verify  |  **Bound by:** llm (conf 0.6)
- **Check language:** Exterior and Interior Description should be completed with Material and Condition. Amenities checkbox should be marked \| Trigger: If improvement section shows Fireplace(s), Patio/Deck, Pool, Woodstove(s), Fence or porch than sales grid should reflect the same. Car Storage \| Trigger: if Car storage checkbox is for None then all area should be blank \| Trigger: If Garage or carport is marked then number of cars should be mentioned \| Trigger: If Garage or carport marked then attach detach or built in should be checked (atleast 1 checkbox )
- **Rejection text:** _(none authored)_
- **Bound labels:** exterior_walls, floor_material, condition_rating, fireplace_count, porch_patio_deck, number_of_cars, parking_space_number
- **Condition (`expects`):** exterior_walls, floor_material, condition_rating non-empty; fireplace_count matches improvement list; porch_patio_deck matches improvement list; if garage/carport then number_of_cars present; if car storage None then parking_space_number blank
- **Conditional:** condition=['common_elements_description', 'exterior_walls', 'financial_assistance_description', 'floor_location'] → consequence=['comp_count_present', 'is_pud_checked', 'porch_patio_deck', 'appraised_value']
- **Found (extracted):** __NO_EXTRACTED_VALUE__  |  **Expected:** __NO_EXPECTED_VALUE__
- **Resolved values:** exterior_walls=BVR/Gd, floor_material=Tile/Gd, condition_rating=C3, porch_patio_deck=CvPch/CvrdPtio CvPch/UncvPtio +2,500 CvP, number_of_cars=2, parking_space_number=4
- **Why VERIFY / reviewer line:** Automated judgment was unavailable for this check — please review the values shown.

### EQ-52 — Does Property Conform to Neighborhood

- **Section:** IMPROVEMENTS  |  **Scope:** subject  |  **Card group:** please_verify  |  **Bound by:** llm (conf 0.95)
- **Check language:** Does Property Conform to Neighborhood — Does the property generally conform to the neighborhood (functional utility, style, condition, use, construction, etc.)?
- **Rejection text:** _(none authored)_
- **Bound labels:** conforms_to_neighborhood
- **Condition (`expects`):** conforms_to_neighborhood == True
- **Found (extracted):** __NO_EXTRACTED_VALUE__  |  **Expected:** __NO_EXPECTED_VALUE__
- **Resolved values:** conforms_to_neighborhood=Yes
- **Why VERIFY / reviewer line:** Automated judgment was unavailable for this check — please review the values shown.

### EQ-53 — # of COMPARABLE Properties Currently Offered

- **Section:** SALES_COMPARISON  |  **Scope:** subject  |  **Card group:** please_verify  |  **Bound by:** llm (conf 0.92)
- **Check language:** # of COMPARABLE Properties Currently Offered — Top of page should be fill up
- **Rejection text:** _(none authored)_
- **Bound labels:** comp_count_present
- **Condition (`expects`):** comp_count_present >= 1
- **Found (extracted):** __NO_EXTRACTED_VALUE__  |  **Expected:** __NO_EXPECTED_VALUE__
- **Resolved values:** comp_count_present=7
- **Why VERIFY / reviewer line:** Automated judgment was unavailable for this check — please review the values shown.

### EQ-54 — # of COMPARABLE Sales w/in 12 Months

- **Section:** SALES_COMPARISON  |  **Scope:** comps  |  **Card group:** please_verify  |  **Bound by:** llm (conf 0.9)
- **Check language:** # of COMPARABLE Sales w/in 12 Months — MUST only include competing sales. Verify that the comparables provided fall within this range. Range must be consistent with the comparable sales provided and match 1004MC form. Check also Predominant price ranges from page 1.
- **Rejection text:** _(none authored)_
- **Bound labels:** comparable_count
- **Condition (`expects`):** 3 <= comparable_count <= 6
- **Found (extracted):** comparable_count = 40  |  **Expected:** Only competing sales should be counted; comparable count must reflect those.
- **Resolved values:** comparable_count=40
- **Why VERIFY / reviewer line:** Expected Only competing sales should be counted; comparable count must reflect those.; found comparable_count = 40. Please verify.

### EQ-55 — Address

- **Section:** SALES_COMPARISON  |  **Scope:** visual  |  **Card group:** manual_visual  |  **Bound by:** constant (conf 1.0)
- **Check language:** Address — Subject's and All comps address has to be reflected on sales grid \| Triggers: if missing: reject as Please update property address on sales grid or location map so it reflects as ____
- **Rejection text:** _(none authored)_
- **Bound labels:** _(none — unbound)_
- **Condition (`expects`):** _(empty — no predicate → auto-VERIFY)_
- **Found (extracted):** __NO_EXTRACTED_VALUE__  |  **Expected:** __NO_EXPECTED_VALUE__
- **Why VERIFY / reviewer line:** Manual visual check: Address — Subject's and All comps address has to be reflected on sales grid \| Triggers: if missing: reject as Please update property address on sales grid or location map so it ref — review the photos/sketch/map by eye.

### EQ-56 — Proximity to Subject

- **Section:** SALES_COMPARISON  |  **Scope:** visual  |  **Card group:** manual_visual  |  **Bound by:** constant (conf 1.0)
- **Check language:** Proximity to Subject — Must be provided as at least 0.01 miles and the proper direction, N, S, NW, NE, etc. Even if in the same complex. If blank, verify that the location Map is provided.
- **Rejection text:** _(none authored)_
- **Bound labels:** _(none — unbound)_
- **Condition (`expects`):** _(empty — no predicate → auto-VERIFY)_
- **Found (extracted):** __NO_EXTRACTED_VALUE__  |  **Expected:** __NO_EXPECTED_VALUE__
- **Why VERIFY / reviewer line:** Manual visual check: Proximity to Subject — Must be provided as at least 0.01 miles and the proper direction, N, S, NW, NE, etc. Even if in the same complex. If blank, verify that the location Map is p — review the photos/sketch/map by eye.

### EQ-57 — Data Sources

- **Section:** SALES_COMPARISON  |  **Scope:** cross_section  |  **Card group:** please_verify  |  **Bound by:** llm (conf 0.6)
- **Check language:** Data Sources — must have Specific MLS,the #, the MLS number/letters that apply. (i.e.. MISMLS#3546935;DOM12). DOM must be provided or Unk listed (commentary needed if unknown). \| Triggers: If missing : reject as Please have data source for ___ comp # under sales grid section.
- **Rejection text:** _(none authored)_
- **Bound labels:** comp_N_data_source
- **Condition (`expects`):** comp_N_data_source present for each comparable
- **Conditional:** condition=['comp_N_data_source', 'data_source', 'is_seller_owner_of_record', 'owner_record_data_source'] → consequence=['comp_count_present', 'is_seller_owner_of_record', 'prior_sale_data_source_subject', 'appraised_value']
- **Found (extracted):** __NO_EXTRACTED_VALUE__  |  **Expected:** __NO_EXPECTED_VALUE__
- **Resolved values:** comp_1_data_source=HMLS#83105442;DOM 160, comp_2_data_source=HMLS#78531618;DOM 50, comp_3_data_source=HMLS#24400513;DOM 6, comp_4_data_source=HMLS#97034376;DOM 56, comp_5_data_source=HMLS#45018351;DOM 43, comp_6_data_source=HMLS#36368237;DOM 39
- **Why VERIFY / reviewer line:** Automated judgment was unavailable for this check — please review the values shown.

### EQ-58 — Verification Sources

- **Section:** SALES_COMPARISON  |  **Scope:** cross_section  |  **Card group:** please_verify  |  **Bound by:** llm (conf 0.6)
- **Check language:** Verification Sources — At least 1 must be provided and the specific verification source must be reported in full \| Triggers: If missing : reject as Please have verification source for ___ comp # under sales grid section.
- **Rejection text:** _(none authored)_
- **Bound labels:** comp_N_verification_source
- **Condition (`expects`):** count(comp_* present) >= 1
- **Conditional:** condition=['comp_N_verification_source', 'comp_N_data_source', 'data_source', 'is_seller_owner_of_record'] → consequence=['comp_count_present', 'appraised_value', 'comp_N_verification_source', 'prior_sale_data_source_subject']
- **Found (extracted):** __NO_EXTRACTED_VALUE__  |  **Expected:** __NO_EXPECTED_VALUE__
- **Resolved values:** comp_1_verification_source=Agent/Tax Records, comp_2_verification_source=Agent/Tax Records, comp_3_verification_source=Agent/Tax Records, comp_4_verification_source=Agent/Tax Records, comp_5_verification_source=Agent/Tax Records, comp_6_verification_source=Agent/Tax Records
- **Why VERIFY / reviewer line:** Automated judgment was unavailable for this check — please review the values shown.

### EQ-59 — Sale or Financing Concessions

- **Section:** SALES_COMPARISON  |  **Scope:** unbound  |  **Card group:** please_verify  |  **Bound by:** llm (conf 0.2)
- **Check language:** Sale or Financing Concessions — IF concession is given in amount and didn't given an adjustment or applied 0 :
- **Rejection text:** Please provide "Sales or Financing Concessions" for comp 1, or comment why adjustment is not warranted.
- **Bound labels:** concessions_amount, has_financial_assistance
- **Condition (`expects`):** _(empty — no predicate → auto-VERIFY)_
- **Found (extracted):** No concessions_amount or has_financial_assistance fields present  |  **Expected:** Concession amount must be provided and if no adjustment is given it should be 0
- **Why VERIFY / reviewer line:** Expected a concession amount or note of no adjustment, but the report provides no concession data; please verify.

### EQ-61 — Location

- **Section:** SALES_COMPARISON  |  **Scope:** cross_section  |  **Card group:** please_verify  |  **Bound by:** llm (conf 0.6)
- **Check language:** Location — location must be one of N, B or A (refer site section) \| Triggers: IF subject mentioned as (A - Adverse) then if any of the comps with (N - Neutral) than value must be reflect in negative (-)
- **Rejection text:** _(none authored)_
- **Bound labels:** comp_N_location_rating
- **Condition (`expects`):** comp_N_location_rating in ['N','B','A']
- **Conditional:** condition=['comp_N_floor_location', 'comp_N_location_rating', 'floor_location', 'location'] → consequence=['adverse_site_conditions', 'appraised_value', 'fha_case_number', 'site_value_estimate']
- **Found (extracted):** comp_1_location_rating etc. all have value "N;Res;"; adverse_site_conditions = "No"  |  **Expected:** Location must be one of N, B or A; if subject is adverse and any comp is N then value must be negative
- **Resolved values:** comp_1_location_rating=N;Res;, comp_2_location_rating=N;Res;, comp_3_location_rating=N;Res;, comp_4_location_rating=N;Res;, comp_5_location_rating=N;Res;, comp_6_location_rating=N;Res;
- **Why VERIFY / reviewer line:** Check requires adverse subject with neutral comps to be negative, but adverse flag is missing; please verify condition logic.

### EQ-64 — View

- **Section:** SALES_COMPARISON  |  **Scope:** visual  |  **Card group:** manual_visual  |  **Bound by:** constant (conf 1.0)
- **Check language:** View — If view is described as Beneficial (B) or Adverse (A) photo must be provided for the same.
- **Rejection text:** _(none authored)_
- **Bound labels:** _(none — unbound)_
- **Condition (`expects`):** _(empty — no predicate → auto-VERIFY)_
- **Found (extracted):** __NO_EXTRACTED_VALUE__  |  **Expected:** __NO_EXPECTED_VALUE__
- **Why VERIFY / reviewer line:** Manual visual check: View — If view is described as Beneficial (B) or Adverse (A) photo must be provided for the same. — review the photos/sketch/map by eye.

### EQ-66 — Quality of Construction

- **Section:** SALES_COMPARISON  |  **Scope:** cross_document  |  **Card group:** please_verify  |  **Bound by:** llm (conf 0.85)
- **Check language:** Quality of Construction — Must be UAD Compliant, Q3, Q4, etc. Any difference from subject to comps NOT adjusted must have a 0 in grid adjustment field and commentary must be provided to address no adjustment given.
- **Rejection text:** _(none authored)_
- **Bound labels:** quality_rating, comp_N_quality_rating, comp_N_net_adjustment
- **Condition (`expects`):** if(comp_N_quality_rating != quality_rating) then comp_N_net_adjustment == 0
- **Found (extracted):** comp_1_net_adjustment "-17440" (and other non‑zero adjustments)  |  **Expected:** Any non‑adjusted quality difference must have a 0 net adjustment and commentary
- **Resolved values:** quality_rating=Q4, comp_1_quality_rating=Q4, comp_2_quality_rating=Q4, comp_3_quality_rating=Q4, comp_4_quality_rating=Q4, comp_5_quality_rating=Q4
- **Why VERIFY / reviewer line:** Adjustments are non‑zero despite no quality differences, violating the zero‑adjustment rule.

### EQ-67 — Actual Age

- **Section:** SALES_COMPARISON  |  **Scope:** comps  |  **Card group:** please_verify  |  **Bound by:** llm (conf 0.92)
- **Check language:** Actual Age — Verify actual age with year built \| Triggers: if different add rejection
- **Rejection text:** Per the improvement section subjects year built is 2023 and its actual age should be 1, however the sales comparison grid shows the actual age as 0. Please verify.
- **Bound labels:** comp_N_actual_age
- **Condition (`expects`):** comp_N_actual_age matches year built
- **Found (extracted):** Actual ages: 20, 20, 15, 16, 13, 9 (no 8 present)  |  **Expected:** Actual age should match derived age of 8 years.
- **Resolved values:** comp_1_actual_age=20, comp_2_actual_age=20, comp_3_actual_age=15, comp_4_actual_age=16, comp_5_actual_age=13, comp_7_actual_age=9
- **Why VERIFY / reviewer line:** Expected actual age 8 but found ages 20,20,15,16,13,9; reject recommended.

### EQ-68 — Condition

- **Section:** SALES_COMPARISON  |  **Scope:** comps  |  **Card group:** please_verify  |  **Bound by:** llm (conf 0.85)
- **Check language:** Condition — Verify condition rating matches with the photos provided in the report. check comments. \| Triggers: if different or inconsistent from other comps
- **Rejection text:** Please provide condition adjustment for comps# 2, 3 and 4 or comment why it was not warranted as compare to subject.
- **Bound labels:** comp_N_condition_rating
- **Condition (`expects`):** _(empty — no predicate → auto-VERIFY)_
- **Found (extracted):** Condition ratings: C4, C3, C3, C3, C3, C3, C3  |  **Expected:** Condition rating must match photos and comments.
- **Resolved values:** comp_1_condition_rating=C4, comp_2_condition_rating=C3, comp_3_condition_rating=C3, comp_4_condition_rating=C3, comp_5_condition_rating=C3, comp_6_condition_rating=C3
- **Why VERIFY / reviewer line:** Condition ratings are present but cannot verify consistency with photos/comments.

### EQ-69 — Above Grade/Room count/ and GLA

- **Section:** SALES_COMPARISON  |  **Scope:** visual  |  **Card group:** manual_visual  |  **Bound by:** constant (conf 1.0)
- **Check language:** Above Grade/Room count/ and GLA — Must be provided, verify all rooms and GLA match Sketch.
- **Rejection text:** _(none authored)_
- **Bound labels:** _(none — unbound)_
- **Condition (`expects`):** _(empty — no predicate → auto-VERIFY)_
- **Found (extracted):** __NO_EXTRACTED_VALUE__  |  **Expected:** __NO_EXPECTED_VALUE__
- **Why VERIFY / reviewer line:** Manual visual check: Above Grade/Room count/ and GLA — Must be provided, verify all rooms and GLA match Sketch. — review the photos/sketch/map by eye.

### EQ-7 — Map Reference

- **Section:** SUBJECT  |  **Scope:** visual  |  **Card group:** manual_visual  |  **Bound by:** constant (conf 1.0)
- **Check language:** Map Reference — Provided by the appraiser and must be current \| Triggers: IF Map Reference missing or blank
- **Rejection text:** _(none authored)_
- **Bound labels:** _(none — unbound)_
- **Condition (`expects`):** _(empty — no predicate → auto-VERIFY)_
- **Found (extracted):** __NO_EXTRACTED_VALUE__  |  **Expected:** __NO_EXPECTED_VALUE__
- **Why VERIFY / reviewer line:** Manual visual check: Map Reference — Provided by the appraiser and must be current \| Triggers: IF Map Reference missing or blank — review the photos/sketch/map by eye.

### EQ-71 — Functional Utility

- **Section:** SALES_COMPARISON  |  **Scope:** subject  |  **Card group:** please_verify  |  **Bound by:** llm (conf 0.96)
- **Check language:** Functional Utility — must be provided as Standard, Average or Typical
- **Rejection text:** _(none authored)_
- **Bound labels:** functional_utility
- **Condition (`expects`):** value in {'Standard','Average','Typical'}
- **Found (extracted):** __NO_EXTRACTED_VALUE__  |  **Expected:** __NO_EXPECTED_VALUE__
- **Resolved values:** functional_utility=Heating/Cooling Energy Efficient
- **Why VERIFY / reviewer line:** Automated judgment was unavailable for this check — please review the values shown.

### EQ-72 — Heating/Cooling

- **Section:** SALES_COMPARISON  |  **Scope:** cross_section  |  **Card group:** please_verify  |  **Bound by:** llm (conf 0.25)
- **Check language:** Heating/Cooling — Both must be provided and match with improvement section. If heating source is FWBB or FWA or Radiant at least 1 comp should be the same feature. \| Triggers: If cooling source marked as "Other" reject as: Subject property has no permanent heat source, please provide comment any impact on marketability.
- **Rejection text:** _(none authored)_
- **Bound labels:** _(none — unbound)_
- **Condition (`expects`):** count(comp_* present) >= 1
- **Conditional:** condition=['cooling', 'heating'] → consequence=['prior_sale_data_source_subject', 'appraisal_subject_to', 'appraised_value', 'comp_N_data_source']
- **Found (extracted):** heating = "FWA", cooling = "Central Air"; no improvement section data present  |  **Expected:** Both heating and cooling must be provided and match the improvement section; if cooling is "Other" reject.
- **Resolved values:** cooling=Central Air, heating=FWA, prior_sale_data_source_subject=used, offering price(s),, appraisal_subject_to=As Is, appraised_value=245000, comp_1_data_source=HMLS#83105442;DOM 160
- **Why VERIFY / reviewer line:** Heating and cooling are provided (FWA, Central Air) but improvement section data is missing, so cannot confirm match; please verify.

### EQ-73 — Energy Efficient Items

- **Section:** SALES_COMPARISON  |  **Scope:** comps  |  **Card group:** please_verify  |  **Bound by:** llm (conf 0.8)
- **Check language:** Energy Efficient Items — Energy Efficient items need to be described. Differences from subject to comp NOT adjusted must have a 0 in grid adjustment field.
- **Rejection text:** _(none authored)_
- **Bound labels:** comp_N_net_adjustment
- **Condition (`expects`):** comp_N_net_adjustment == 0 when energy efficient items not described
- **Found (extracted):** Net adjustments are non‑zero for all comps.  |  **Expected:** Energy efficient items described; non‑adjusted differences must have zero net adjustment.
- **Resolved values:** comp_1_net_adjustment=-17440, comp_2_net_adjustment=10195, comp_3_net_adjustment=-18220, comp_4_net_adjustment=-26184, comp_5_net_adjustment=180, comp_6_net_adjustment=-4356
- **Why VERIFY / reviewer line:** Cannot determine if energy‑efficient items were described or if zero adjustments apply.

### EQ-74 — Garage/Carport

- **Section:** SALES_COMPARISON  |  **Scope:** cross_section  |  **Card group:** please_verify  |  **Bound by:** llm (conf 0.6)
- **Check language:** Garage/Carport — If in the improvement section Garage is marked then sales grid reflect the garage with driveway (ex. 1ga2dw) \| Triggers: If any of this is differnt with subject the adjustment or 0 is required.
- **Rejection text:** _(none authored)_
- **Bound labels:** comp_N_garage_carport
- **Condition (`expects`):** if subject garage marked then comp_N_garage_carport includes garage with driveway (e.g., contains 'ga' and 'dw')
- **Conditional:** condition=['comp_N_garage_carport'] → consequence=['comp_count_present', 'prior_sale_data_source_subject', 'prior_sale_date_subject', 'prior_sale_effective_date_subject']
- **Found (extracted):** comp garage values: 2ga2dw, 1ga1dw, etc.; no improvement section garage data present  |  **Expected:** If garage is marked in improvement section, sales grid must reflect garage with driveway (e.g., 1ga2dw).
- **Resolved values:** comp_1_garage_carport=2ga2dw, comp_2_garage_carport=1ga1dw, comp_3_garage_carport=2ga2dw, comp_4_garage_carport=2ga2dw, comp_5_garage_carport=2ga2dw, comp_6_garage_carport=2ga2dw
- **Why VERIFY / reviewer line:** Garage values appear in comps but improvement section garage info is missing, so match cannot be verified; please check.

### EQ-75 — Porch/Patio/Deck

- **Section:** SALES_COMPARISON  |  **Scope:** cross_section  |  **Card group:** please_verify  |  **Bound by:** llm (conf 0.6)
- **Check language:** Porch/Patio/Deck — In the improvement section if porch, patio or deck marked then same must be reflected in the sales grid. \| Triggers: If any of the amenities are differnt with subject the adjustment or 0 is required.
- **Rejection text:** _(none authored)_
- **Bound labels:** porch_patio_deck
- **Condition (`expects`):** if porch_patio_deck present then sales grid reflects same amenity
- **Conditional:** condition=['porch_patio_deck'] → consequence=['comp_count_present', 'fha_case_number', 'prior_sale_data_source_subject', 'prior_sale_date_subject']
- **Found (extracted):** porch_patio_deck = "CvPch/CvrdPtio CvPch/UncvPtio +2,500 CvPch/CvrdPtio CvPch/CvrdPtio"; no sales grid porch data present  |  **Expected:** If porch/patio/deck is marked in improvement section, same must be reflected in sales grid.
- **Resolved values:** porch_patio_deck=CvPch/CvrdPtio CvPch/UncvPtio +2,500 CvP, comp_count_present=7, prior_sale_data_source_subject=used, offering price(s),, prior_sale_date_subject=2024-07-23
- **Why VERIFY / reviewer line:** Porch/patio/deck is noted but corresponding sales grid entries are absent; please verify consistency.

### EQ-78 — Adjusted Sale Price of Comparables

- **Section:** SALES_COMPARISON  |  **Scope:** comps  |  **Card group:** please_verify  |  **Bound by:** llm (conf 0.96)
- **Check language:** Adjusted Sale Price of Comparables — The adjusted sale price reflects the market's reaction to differences between the subject and sales and provides a more accurate range of value for the subject.
- **Rejection text:** _(none authored)_
- **Bound labels:** comp_N_adjusted_sale_price
- **Condition (`expects`):** count(comp_N_adjusted_sale_price present) >= 1
- **Found (extracted):** Adjusted sale prices are provided but no context to assess market reaction.  |  **Expected:** Adjusted sale price must reflect market reaction to differences.
- **Resolved values:** comp_1_adjusted_sale_price=232560, comp_2_adjusted_sale_price=245195, comp_3_adjusted_sale_price=246780, comp_4_adjusted_sale_price=233816, comp_5_adjusted_sale_price=240180, comp_6_adjusted_sale_price=255634
- **Why VERIFY / reviewer line:** Adjusted sale prices are present but cannot verify they reflect market reaction.

### EQ-79 — Research the sale or transfer history of subject

- **Section:** PRIOR_SALES  |  **Scope:** subject  |  **Card group:** please_verify  |  **Bound by:** llm (conf 0.92)
- **Check language:** Research the sale or transfer history of subject — In this section always I did research the sale or transfer history of the subject property and comparable sales must be marked.
- **Rejection text:** _(none authored)_
- **Bound labels:** sales_history_researched, prior_sale_date_subject, prior_sale_price_subject
- **Condition (`expects`):** prior_sale_date_subject and prior_sale_price_subject present
- **Found (extracted):** __NO_EXTRACTED_VALUE__  |  **Expected:** __NO_EXPECTED_VALUE__
- **Resolved values:** sales_history_researched=Yes, prior_sale_date_subject=2024-07-23, prior_sale_price_subject=$240,000
- **Why VERIFY / reviewer line:** Automated judgment was unavailable for this check — please review the values shown.

### EQ-81 — Comparables 12 month sales or transfer history

- **Section:** PRIOR_SALES  |  **Scope:** cross_section  |  **Card group:** please_verify  |  **Bound by:** llm (conf 0.6)
- **Check language:** Comparables 12 month sales or transfer history — If comparable sold/transferred in 12 months than "My research did reveal any prior sales or transfers of the comparable sales for the year prior to the date of sale of the comparable sale" box must be marked
- **Rejection text:** _(none authored)_
- **Bound labels:** prior_comp_N_sale_date
- **Condition (`expects`):** if(comp_N_sale_date within 12mo) then prior_comp_N_sale_date is null
- **Conditional:** condition=['prior_comp_N_sale_date', 'comp_N_sale_date', 'comp_count_present', 'prior_comp_N_sale_price'] → consequence=[]
- **Found (extracted):** No box value present in packet  |  **Expected:** Box "My research did reveal any prior sales or transfers of the comparable sales for the year prior to the date of sale of the comparable sale" must be marked when a comparable sold within 12 months
- **Resolved values:** prior_comp_N_sale_date=07/23/2024, comp_1_sale_date=s04/26;c03/26, comp_2_sale_date=s02/26;c01/26, comp_3_sale_date=s12/25;c11/25, comp_4_sale_date=s10/25;c10/25, comp_5_sale_date=s08/25;c07/25
- **Why VERIFY / reviewer line:** Expected box marked for recent comparable sale but no box value found – please verify.

### EQ-84 — Data Source(s)

- **Section:** PRIOR_SALES  |  **Scope:** cross_section  |  **Card group:** please_verify  |  **Bound by:** llm (conf 0.6)
- **Check language:** Data Source(s) — Must be provided. If last sale is report in Public Record, Doc # must be provided. If MLS sale, MLS name must be provided along with MLS #. Must be provided even if no sale or transfer is reported. Example: MFRMLS #T2321256
- **Rejection text:** _(none authored)_
- **Bound labels:** prior_sale_data_source_subject
- **Condition (`expects`):** len(prior_sale_data_source_subject) > 0
- **Conditional:** condition=['comp_N_data_source', 'data_source', 'is_seller_owner_of_record', 'owner_record_data_source'] → consequence=['contract_date', 'fha_case_number', 'owner_of_public_record', 'appraisal_report_type']
- **Found (extracted):** Condition label "is_seller_owner_of_record" is absent, preventing condition evaluation.  |  **Expected:** All required data source fields must be provided (e.g., MLS name and #, public record doc #).
- **Resolved values:** prior_sale_data_source_subject=used, offering price(s),, comp_1_data_source=HMLS#83105442;DOM 160, comp_2_data_source=HMLS#78531618;DOM 50, comp_3_data_source=HMLS#24400513;DOM 6, comp_4_data_source=HMLS#97034376;DOM 56, comp_5_data_source=HMLS#45018351;DOM 43
- **Why VERIFY / reviewer line:** Expected All required data source fields must be provided (e.g., MLS name and #, public record doc #).; found Condition label "is_seller_owner_of_record" is absent, preventing condition evaluation.. Please verify.

### EQ-85 — Effective Date of Data Source (s)

- **Section:** PRIOR_SALES  |  **Scope:** cross_section  |  **Card group:** please_verify  |  **Bound by:** llm (conf 0.6)
- **Check language:** Effective Date of Data Source (s) — Should be the date of findings. Must be provided even if no sale or transfer is reported.
- **Rejection text:** _(none authored)_
- **Bound labels:** prior_sale_effective_date_subject
- **Condition (`expects`):** date present
- **Conditional:** condition=['comp_N_data_source', 'data_source', 'effective_date', 'is_seller_owner_of_record'] → consequence=['comp_N_sale_date', 'contract_date', 'date_report_signed', 'prior_comp_N_sale_date']
- **Found (extracted):** Condition label "is_seller_owner_of_record" is absent, preventing condition evaluation.  |  **Expected:** Effective Date of Data Source(s) must be provided.
- **Resolved values:** prior_sale_effective_date_subject=07/07/2026 07/07/2026 07/07/2026 07/07/2, comp_1_data_source=HMLS#83105442;DOM 160, comp_2_data_source=HMLS#78531618;DOM 50, comp_3_data_source=HMLS#24400513;DOM 6, comp_4_data_source=HMLS#97034376;DOM 56, comp_5_data_source=HMLS#45018351;DOM 43
- **Why VERIFY / reviewer line:** Expected Effective Date of Data Source(s) must be provided.; found Condition label "is_seller_owner_of_record" is absent, preventing condition evaluation.. Please verify.

### EQ-86 — Analysis of prior sales or transfers

- **Section:** PRIOR_SALES  |  **Scope:** subject  |  **Card group:** please_verify  |  **Bound by:** llm (conf 0.9)
- **Check language:** Analysis of prior sales or transfers
- **Rejection text:** _(none authored)_
- **Bound labels:** prior_sale_analysis_comment
- **Condition (`expects`):** present(prior_sale_analysis_comment)
- **Found (extracted):** __NO_EXTRACTED_VALUE__  |  **Expected:** __NO_EXPECTED_VALUE__
- **Resolved values:** prior_sale_analysis_comment=The subject property was previously sold
- **Why VERIFY / reviewer line:** Automated judgment was unavailable for this check — please review the values shown.

### EQ-87 — Summary of Sales Comparison Approach

- **Section:** PRIOR_SALES  |  **Scope:** cross_section  |  **Card group:** please_verify  |  **Bound by:** llm (conf 0.6)
- **Check language:** Summary of Sales Comparison Approach — Appraiser must discuss the comparables provided specifically. Address distant comparables, adjustments given or the lack of. Your opinion of value should be bracketed by the unadjusted and adjusted sales prices. If unable to bracket, sufficient commentary must be provided.
- **Rejection text:** _(none authored)_
- **Bound labels:** comp_N_sale_price, comp_N_adjusted_sale_price, sales_comparison_summary
- **Condition (`expects`):** _(empty — no predicate → auto-VERIFY)_
- **Conditional:** condition=['sales_comparison_summary', 'appraised_value', 'comp_count_present', 'appraiser_cert_expiration_date'] → consequence=['appraised_value', 'comp_N_adjusted_sale_price', 'comp_N_sale_price', 'comp_count_present']
- **Found (extracted):** __NO_EXTRACTED_VALUE__  |  **Expected:** __NO_EXPECTED_VALUE__
- **Resolved values:** comp_1_sale_price=250000, comp_2_sale_price=235000, comp_3_sale_price=265000, comp_4_sale_price=260000, comp_5_sale_price=240000, comp_6_sale_price=259990
- **Why VERIFY / reviewer line:** The form points to an addendum for this narrative but I could not find the matching text — please check the addendum pages by eye.

### EQ-88 — Indicated value by sales comparison

- **Section:** PRIOR_SALES  |  **Scope:** subject  |  **Card group:** please_verify  |  **Bound by:** llm (conf 0.7)
- **Check language:** Indicated value by sales comparison — Must be provided and match the final value given.
- **Rejection text:** _(none authored)_
- **Bound labels:** indicated_value_sca
- **Condition (`expects`):** present and equals market_value_opinion
- **Found (extracted):** __NO_EXTRACTED_VALUE__  |  **Expected:** __NO_EXPECTED_VALUE__
- **Resolved values:** indicated_value_sca=245000
- **Why VERIFY / reviewer line:** Automated judgment was unavailable for this check — please review the values shown.

### EQ-89 — Indicated Value by Sales Comparison Appr

- **Section:** RECONCILIATION  |  **Scope:** cross_section  |  **Card group:** please_verify  |  **Bound by:** llm (conf 0.6)
- **Check language:** Indicated Value by Sales Comparison Approach value and as is value must be same \| Triggers: If values are different reject as: In reconciliation section, Indicated Market Value does not match with indicated value by Sales Comparison Approach. Please revise.
- **Rejection text:** _(none authored)_
- **Bound labels:** indicated_value_sca, market_value_opinion
- **Condition (`expects`):** indicated_value_sca == market_value_opinion
- **Conditional:** condition=['appraised_value', 'indicated_value_cost_approach', 'indicated_value_income_approach', 'comp_count_present'] → consequence=['appraised_value', 'indicated_monthly_market_rent', 'indicated_value_cost_approach', 'indicated_value_income_approach']
- **Found (extracted):** Condition label "indicated_value_income_approach" is absent, preventing condition evaluation.  |  **Expected:** Indicated Value by Sales Comparison Approach and As Is value must be the same.
- **Resolved values:** indicated_value_sca=245000, appraised_value=245000, indicated_value_cost_approach=241686, comp_count_present=7
- **Why VERIFY / reviewer line:** Expected Indicated Value by Sales Comparison Approach and As Is value must be the same.; found Condition label "indicated_value_income_approach" is absent, preventing condition evaluation.. Please verify.

### EQ-9 — Occupant

- **Section:** SUBJECT  |  **Scope:** visual  |  **Card group:** manual_visual  |  **Bound by:** constant (conf 1.0)
- **Check language:** Occupant — If tenant: should verify lease dates and amount. If vacant: must state if utilities are on. \| Triggers: If occupancy is owner occupied photos should check photos.; If occupancy is vacant and photo shows occupied: Reject as: In subject section, occupancy is marked as vacant however as per photos subject property appears to be occupied, please revise or comment if it is a staged home.
- **Rejection text:** The subject section indicates that the property is owner occupied however the photos appear to show the property is currently vacant. Please revise or comment.
- **Bound labels:** _(none — unbound)_
- **Condition (`expects`):** _(empty — no predicate → auto-VERIFY)_
- **Found (extracted):** __NO_EXTRACTED_VALUE__  |  **Expected:** __NO_EXPECTED_VALUE__
- **Why VERIFY / reviewer line:** Manual visual check: Occupant — If tenant: should verify lease dates and amount. If vacant: must state if utilities are on. \| Triggers: If occupancy is owner occupied photos should check photos.; If oc — review the photos/sketch/map by eye.

### EQ-91 — Appraisal: As Is or Subject To

- **Section:** RECONCILIATION  |  **Scope:** subject  |  **Card group:** please_verify  |  **Bound by:** llm (conf 0.95)
- **Check language:** Appraisal: As Is or Subject To — At least 1 box must be checked ""as is" or "subject to"
- **Rejection text:** _(none authored)_
- **Bound labels:** appraisal_subject_to
- **Condition (`expects`):** count(comp_* present) >= 1
- **Found (extracted):** __NO_EXTRACTED_VALUE__  |  **Expected:** __NO_EXPECTED_VALUE__
- **Resolved values:** appraisal_subject_to=As Is
- **Why VERIFY / reviewer line:** Automated judgment was unavailable for this check — please review the values shown.

### EQ-92 — Support for the Opinion of Site value

- **Section:** COST  |  **Scope:** cross_section  |  **Card group:** please_verify  |  **Bound by:** llm (conf 0.6)
- **Check language:** Support for the Opinion of Site value — Opinion Of Site Value is required in every report. \| Triggers: If missing reject as : Please provide an Opinion of site value in the report.
- **Rejection text:** _(none authored)_
- **Bound labels:** site_value_estimate
- **Condition (`expects`):** site_value_estimate present
- **Conditional:** condition=['market_value_opinion', 'site_value_estimate', 'adverse_site_conditions', 'appraised_value'] → consequence=['market_value_opinion', 'site_value_estimate', 'adverse_site_conditions', 'appraisal_report_type']
- **Found (extracted):** Condition label "market_value_opinion" is absent, preventing condition evaluation.  |  **Expected:** Opinion of Site Value must be provided in the report.
- **Resolved values:** site_value_estimate=50000, adverse_site_conditions=No, appraised_value=245000
- **Why VERIFY / reviewer line:** Expected Opinion of Site Value must be provided in the report.; found Condition label "market_value_opinion" is absent, preventing condition evaluation.. Please verify.

### EQ-93 — Estimated Remaining Economic Life (HUD and VA only)

- **Section:** COST  |  **Scope:** subject  |  **Card group:** please_verify  |  **Bound by:** llm (conf 0.95)
- **Check language:** Estimated Remaining Economic Life (HUD and VA only) — Not less than 30 years
- **Rejection text:** _(none authored)_
- **Bound labels:** remaining_economic_life
- **Condition (`expects`):** remaining_economic_life >= 30
- **Found (extracted):** __NO_EXTRACTED_VALUE__  |  **Expected:** __NO_EXPECTED_VALUE__
- **Resolved values:** remaining_economic_life=52
- **Why VERIFY / reviewer line:** Automated judgment was unavailable for this check — please review the values shown.

### EQ-94 — INCOME APPROACH TO VALUE

- **Section:** COST  |  **Scope:** cross_section  |  **Card group:** please_verify  |  **Bound by:** llm (conf 0.2)
- **Check language:** INCOME APPROACH TO VALUE — If this section is blank than no need to add revision.
- **Rejection text:** _(none authored)_
- **Bound labels:** _(none — unbound)_
- **Condition (`expects`):** _(empty — no predicate → auto-VERIFY)_
- **Conditional:** condition=['indicated_value_income_approach', 'income_approach_monthly_rent', 'indicated_value_cost_approach', 'is_income_approach_used'] → consequence=[]
- **Found (extracted):** indicated_value_income_approach absent; narrative states Income Approach was considered but not developed  |  **Expected:** Income Approach to Value section should be blank or omitted if not used
- **Resolved values:** indicated_value_cost_approach=241686
- **Why VERIFY / reviewer line:** Check expects a blank Income Approach section; narrative says it was not developed but the required fields are absent, so verify if this is acceptable

### EQ-95 — Is Developer/builder in control?

- **Section:** PUD  |  **Scope:** cross_section  |  **Card group:** please_verify  |  **Bound by:** llm (conf 0.6)
- **Check language:** Is Developer/builder in control? — Should be completed for All PUD reports, check yes or no and Attached/Detached. \| Triggers: If attached and yes checkbox is marked then all pud information should be fill up
- **Rejection text:** _(none authored)_
- **Bound labels:** is_developer_controls_hoa
- **Condition (`expects`):** _(empty — no predicate → auto-VERIFY)_
- **Conditional:** condition=['is_developer_controls_hoa'] → consequence=['appraisal_report_type', 'appraised_value', 'are_facilities_complete', 'census_tract']
- **Found (extracted):** is_developer_controls_hoa absent; no related values present  |  **Expected:** Answer whether Developer/builder is in control (yes/no) and attached/detached status
- **Resolved values:** appraised_value=245000, census_tract=2409.06
- **Why VERIFY / reviewer line:** The check requires a yes/no answer on developer control, but the relevant field is missing, please verify manually

### EQ-96 — Appraiser

- **Section:** SIGNATURE  |  **Scope:** cross_section  |  **Card group:** please_verify  |  **Bound by:** llm (conf 0.6)
- **Check language:** Appraiser — All reports must be signed by certified Appraiser. \| Triggers: If signature is missing reject as: 1. The Appraiser Signatures are missing throughout the report, please sign in all the designated spaces.
- **Rejection text:** _(none authored)_
- **Bound labels:** date_report_signed
- **Condition (`expects`):** presence(date_report_signed) == true
- **Conditional:** condition=['appraisal_report_type', 'appraiser_cert_expiration_date', 'appraiser_cert_state', 'appraiser_company_address'] → consequence=['appraiser_cert_expiration_date', 'appraiser_cert_state', 'appraiser_state_cert_number', 'date_report_signed']
- **Found (extracted):** No signature field present in packet  |  **Expected:** Appraiser signature must be present and signed
- **Resolved values:** date_report_signed=2026-07-08, appraiser_cert_expiration_date=2026-10-31, appraiser_cert_state=#, appraiser_company_address=10219 Silver Leaf Lane, Tomball, TX 7737, appraiser_state_cert_number=1323873-CR
- **Why VERIFY / reviewer line:** Signature data is not available in the packet, cannot determine compliance

### EQ-99 — Telephone number

- **Section:** SIGNATURE  |  **Scope:** cross_document  |  **Card group:** please_verify  |  **Bound by:** llm (conf 0.95)
- **Check language:** Telephone number — Should match the engagement letter
- **Rejection text:** _(none authored)_
- **Bound labels:** appraiser_phone
- **Condition (`expects`):** match(engagement_letter_phone)
- **Found (extracted):** appraiser_phone "(281) 205-7010"; engagement phone not present  |  **Expected:** Telephone number must match the engagement letter
- **Resolved values:** appraiser_phone=(281) 205-7010
- **Why VERIFY / reviewer line:** Phone number present in report but missing from engagement letter; need verification.

### EQ-A — Form Type (Product)

- **Section:** ORDER  |  **Scope:** cross_document  |  **Card group:** please_verify  |  **Bound by:** llm (conf 0.92)
- **Check language:** Form Type (Product) — Report must be provided same as ordered
- **Rejection text:** _(none authored)_
- **Bound labels:** report_form_number
- **Condition (`expects`):** assignment_type == ordered_form_type
- **Found (extracted):** report_form_number "1004"; engagement.report_form_number "1004 FHA"  |  **Expected:** Report form number must match the ordered form
- **Resolved values:** report_form_number=1004, engagement.report_form_number=1004 FHA
- **Why VERIFY / reviewer line:** Expected matching form numbers, but only "1004" and "1004 FHA" are present; cannot confirm compliance.

### EQ-B — Transaction type

- **Section:** ORDER  |  **Scope:** subject  |  **Card group:** please_verify  |  **Bound by:** llm (conf 0.95)
- **Check language:** Transaction type — Loan type on order form match with Assignment Type
- **Rejection text:** _(none authored)_
- **Bound labels:** loan_type, assignment_type
- **Condition (`expects`):** loan_type == assignment_type
- **Found (extracted):** assignment_type = "Refinance Transaction"; loan_type absent  |  **Expected:** Loan type on order form matches Assignment Type
- **Resolved values:** assignment_type=Refinance Transaction
- **Why VERIFY / reviewer line:** Expected Loan type on order form matches Assignment Type; found assignment_type = "Refinance Transaction"; loan_type absent. Please verify.

### EQ-C — Property Address, City, State, Zip Code and County

- **Section:** SUBJECT  |  **Scope:** cross_section  |  **Card group:** please_verify  |  **Bound by:** llm (conf 0.95)
- **Check language:** Property Address, City, State, Zip Code and County — Must match the Client Engagement Letter exactly and be verified with USPS, if the USPS verification indicates the address differs from the client engagement letter, a comment must be provided. \| Triggers: If property address is different than order form
- **Rejection text:** Property Zip code does not match with order form. (For Zip code only first 5 digit should be match)
- **Bound labels:** property_address, city, state, zip_code, county
- **Condition (`expects`):** match(order_form_address) && comment_if_mismatch
- **Conditional:** condition=['property_address', 'city', 'state', 'zip_code', 'county'] → consequence=[]
- **Found (extracted):** property_address: 7243 Foxtail Meadow Ct; city: Humble; state: TX; zip_code: 77338; county: Harris  |  **Expected:** Property Address, City, State, Zip Code and County must match the Client Engagement Letter exactly
- **Resolved values:** property_address=7243 Foxtail Meadow Ct, city=Humble, state=TX, zip_code=77338, county=Harris
- **Why VERIFY / reviewer line:** Expected address fields to match the client letter, but the client letter data is missing; please verify the match.

### EQ-D — Borrower

- **Section:** SUBJECT  |  **Scope:** cross_section  |  **Card group:** please_verify  |  **Bound by:** llm (conf 0.85)
- **Check language:** Borrower — Must match Client Engagement letter exactly, watch commonly missed co‐borrower and spelling errors. Does not need to match Owner of Public Record. If transaction type is Refinance and the Owner of Record and the borrower do not match, a comment must be provided. \| Triggers: If report missed Co-borrower name.
- **Rejection text:** Please include Co-borrower name _______ as per order form.
- **Bound labels:** borrower_name, co_borrower_name, owner_of_public_record, loan_type
- **Condition (`expects`):** borrower_name must equal engagement‑letter borrower; co_borrower_name must be present if in letter; if loan_type=Refinance and owner_of_public_record ≠ borrower_name then a comment is required
- **Conditional:** condition=['loan_type', 'owner_of_public_record', 'borrower_name'] → consequence=[]
- **Found (extracted):** borrower_name: RATHNASEKARA KARUNARATNE; owner_of_public_record: RATHNASEKARA KARUNARATNE; co_borrower_name: absent; loan_type: absent  |  **Expected:** Borrower must match Client Engagement letter exactly; if refinance and borrower differs from Owner of Record, comment required
- **Resolved values:** borrower_name=RATHNASEKARA KARUNARATNE, owner_of_public_record=RATHNASEKARA KARUNARATNE
- **Why VERIFY / reviewer line:** Loan type is absent, preventing determination of refinance condition; please verify borrower matching and co‑borrower presence.
