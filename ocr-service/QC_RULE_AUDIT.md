# QC Rule Audit — all appraisal packages

_Generated 2026-07-03 · source: MISMO XML extractor → `run_qc` rule engine (XML-only path; the production pipeline additionally merges PDF-extracted fields)._

**Columns:** _Rule_ = id + name · _Status_ = engine verdict · _Extracted_ = the field values the rule actually read (from finding evidence; `∅` = blank/unread) · _How it was judged_ = the rule's own explanation.

## Summary

Status counts (FAIL/VERIFY/PASS/NA), then the **severity split** of the FAIL+VERIFY findings into hard-fail / advisory / manual-verify / extraction-gap. The extraction-gap column is noise that belongs in a re-extract queue, not the reviewer's defect list.

| Dir | File | FAIL | VERIFY | PASS | N/A || hard-fail | advisory | manual-verify | extraction-gap |
|-----|------|------|--------|------|-----||-----------|----------|---------------|----------------|
| 1 | ESCA-0019573.xml | 5 | 64 | 160 | 52 || 4 | 1 | 56 | 8 |
| 2 | 5807 Fox Hunt Trl.xml | 6 | 63 | 140 | 51 || 5 | 1 | 54 | 9 |
| 3 | MAGU96793.XML | 5 | 61 | 164 | 51 || 4 | 1 | 53 | 8 |
| 5 | 17354 SW 287th St.xml | 5 | 69 | 155 | 51 || 4 | 1 | 60 | 9 |
| 6 | 3825 Austin Rd.xml | 5 | 67 | 148 | 60 || 4 | 0 | 59 | 9 |
| 7 | 12619 Provincetowne Dr.xml | 4 | 65 | 150 | 60 || 3 | 1 | 55 | 10 |
| 8 | 9512 N Brooks St.xml | 4 | 67 | 152 | 61 || 3 | 0 | 58 | 10 |


---

## dir 1 — ESCA-0019573.xml

| Rule | Status | Bucket | Extracted (what the rule read) | How it was judged |
|------|--------|--------|-------------------------------|-------------------|
| **SUBJECT-HOLD** — subject | 🔴 FAIL | 🔴 hard-fail | — | 5 failures in the subject section indicate systematic problems (not isolated errors); the section is escalated for a full manual review. |
| **C-3** — Owner-of-record data source present | 🔴 FAIL | 🔴 hard-fail | `is_seller_owner_of_record`=∅; `owner_record_data_source`=∅ | Please provide a data source for the question about whether the seller is the owner of public record (in the contract section). |
| **G-0** — Engagement letter / order form present and extracted | 🔴 FAIL | 🟠 extraction-gap | `loan_type`=∅ | The engagement letter / order form was not extracted. All lender-overlay rules (comp count minimum, site value requirement, declining-market clause, A… |
| **S-12** — Prior-listing data source present | 🔴 FAIL | 🔴 hard-fail | `offered_for_sale_12mo`=∅; `data_source`=∅ | The checkbox about prior sale or listing activity in the past 12 months is missing a data source. Please provide the source used to answer this questi… |
| **S-3** — Owner of public record present | 🔴 FAIL | 🔴 hard-fail | `owner_of_public_record`=∅; `legal_description`=∅; `real_estate_taxes`=∅; `special_assessments`=∅ | The 'Owner of Public Record' field is blank. Please complete it. |
| **ADD-9** — USPAP addendum complete | 🟡 VERIFY | 🟠 extraction-gap | — | The USPAP addendum fields (report type, reasonable exposure time, prior services) could not be extracted; manual review required. |
| **C-1** — Contract analyzed (purchase) / section blank (refinance) | 🟡 VERIFY | 🟡 manual-verify | `did_analyze_contract`=∅ | The contract analysis is missing. Please complete the contract analysis or explain why it was not done. |
| **C-1** — Contract analyzed (purchase) / section blank (refinance) | 🟡 VERIFY | 🟡 manual-verify | `sale_type`=∅; `contract_analysis_comment`=∅ | The type of sale is not identified. Please note whether this is an Arm's-Length sale, REO, Short Sale, Court-Ordered Sale, or Non-Arm's-Length in the … |
| **C-4** — Concessions consistent and match purchase agreement | 🟡 VERIFY | 🟡 manual-verify | `has_financial_assistance`=∅; `financial_assistance_amount`=∅ | The seller concession checkbox (financial assistance) is not answered. Please mark Yes or No. |
| **C-4** — Concessions consistent and match purchase agreement | 🟡 VERIFY | 🟡 manual-verify | `financial_assistance_amount`=∅; `financial_assistance_description`=∅ | Seller-concessions cross-check. The appraisal report shows — Seller concessions / financial assistance not stated in the report; Concession descriptio… |
| **C-ANALYZE** — Contract analysis indicator consistency | 🟡 VERIFY | 🟡 manual-verify | `contract_analyzed`=Y@0.97 | The report says the contract was reviewed, but no purchase contract was included in the file. Please provide the contract or update the contract secti… |
| **CA-1** — Opinion of site value present | 🟡 VERIFY | 🟡 manual-verify | `site_value_estimate`=∅ | The cost approach is missing an opinion of site value. Please provide one. |
| **I-11** — Conforms to neighborhood | 🟡 VERIFY | 🟠 extraction-gap | `conforms_to_neighborhood`=∅ | Conformity to the neighborhood could not be read; please verify the improvements conform. |
| **I-34** — Materials/condition described | 🟡 VERIFY | 🟡 manual-verify | `exterior_walls`=∅; `roof_surface`=∅; `heating`=∅; `floor_material`=∅; `walls_material`=∅; `trim_finish_material`=∅ | The following materials/condition fields are missing in the improvements section: Exterior Walls, Roof Surface, Heating, Floors, Walls, Trim/Finish. P… |
| **I-5** — Heating and cooling described | 🟡 VERIFY | 🟡 manual-verify | `heating`=∅; `cooling`=∅ | The following heating/cooling fields are not described in the improvements section: Heating, Cooling. Please complete. |
| **I-6** — Appliances reported | 🟡 VERIFY | 🟡 manual-verify | `appliance_refrigerator`=∅; `appliance_range_oven`=∅; `appliance_disposal`=∅; `appliance_dishwasher`=∅; `appliance_microwave`=∅; `appliance_washer_dryer`=∅ | No kitchen appliances are listed in the improvements section. Please note which appliances are present. |
| **I-8** — Additional features described | 🟡 VERIFY | 🟡 manual-verify | `fireplace_count`=∅; `porch_patio_deck`=∅; `additional_features`=∅ | Please confirm any additional features (fireplace, porch/patio/deck, pool, etc.) are described in the improvements section, or state 'None'. |
| **I-9** — Condition rating UAD and consistent | 🟡 VERIFY | 🟠 extraction-gap | `condition_rating`=∅ | Condition could not be extracted from the document; manual review required. |
| **I-Q** — Quality rating UAD format | 🟡 VERIFY | 🟠 extraction-gap | `quality_rating`=∅ | Quality could not be extracted from the document; manual review required. |
| **I-SMCO** — Smoke/CO detector code compliance noted | 🟡 VERIFY | 🟡 manual-verify | `sales_comparison_summary`=∅ | No mention of smoke or CO detectors was found in the report. The client requires a note confirming detectors meet local code — please add one to the r… |
| **N-6** — Neighborhood description specific | 🟡 VERIFY | 🟡 manual-verify | `neighborhood_description`=See Attached Comment Addendum Page 6@0.97 | The Neighborhood Description is blank. Please write a description specific to this neighborhood. |
| **N-7** — Market conditions completed | 🟡 VERIFY | 🟡 manual-verify | `market_conditions_commentary`=See Attached Comment Addendum Page 6@0.97 | The market conditions section just says 'See 1004MC' instead of containing the actual analysis. Please put the market analysis directly in this sectio… |
| **PH-2** — Interior photos present | 🟡 VERIFY | 🟡 manual-verify | `photo_interior_rooms`=∅ | Interior photos are incomplete — missing: kitchen, living, bedroom, bathroom. Please include photos of the kitchen, living room, all bedrooms, and all… |
| **R-1** — SCA value matches market value | 🟡 VERIFY | 🟡 manual-verify | `indicated_value_sca`=∅; `appraised_value`=1240000@0.97 | The sales comparison value or final opinion of value could not be read. Please verify both numbers are present and agree. |
| **R-1b** — Reconciliation names the weighted approach | 🟡 VERIFY | 🟡 manual-verify | `final_reconciliation_comment`=∅ | The reconciliation must say which approach was relied on most (sales comparison, cost, or income) and briefly explain why. Please add that statement t… |
| **R-ASSIGN-COND** — Assignment condition vs report language consistency | 🟡 VERIFY | 🟡 manual-verify | `assignment_condition`=AsIs@0.97; `addendum_text`=Scope of Work:  The scope of work refers to the …@0.97; `limiting_conditions_text`=∅ | The assignment condition box (AsIs) doesn't match the language used in the report narrative. Please make sure the box and the written description agre… |
| **CG-TIME-CONSIST** — Time/market adjustment rate consistency | 🟡 VERIFY | 🟡 manual-verify | `comp_3_financing_adj`=-10000@0.97; `comp_3_sale_date`=s04/26;c03/26@0.97; `comp_4_financing_adj`=-30000@0.97; `comp_4_sale_date`=s04/26;c03/26@0.97 | CG-time-consist No supporting explanation for a large line/net/gross adjustment was found in the report narrative (time adjustment rates range from $5… |
| **SCA-10** — Comp property rights present + consistent | 🟡 VERIFY | 🟡 manual-verify | `comp_1_leasehold`=∅ | Please indicate the property rights (Fee Simple or Leasehold) for Comp 1 in the sales grid. |
| **SCA-10** — Comp property rights present + consistent | 🟡 VERIFY | 🟡 manual-verify | `comp_2_leasehold`=∅ | Please indicate the property rights (Fee Simple or Leasehold) for Comp 2 in the sales grid. |
| **SCA-10** — Comp property rights present + consistent | 🟡 VERIFY | 🟡 manual-verify | `comp_3_leasehold`=∅ | Please indicate the property rights (Fee Simple or Leasehold) for Comp 3 in the sales grid. |
| **SCA-10** — Comp property rights present + consistent | 🟡 VERIFY | 🟡 manual-verify | `comp_4_leasehold`=∅ | Please indicate the property rights (Fee Simple or Leasehold) for Comp 4 in the sales grid. |
| **SCA-10** — Comp property rights present + consistent | 🟡 VERIFY | 🟡 manual-verify | `comp_5_leasehold`=∅ | Please indicate the property rights (Fee Simple or Leasehold) for Comp 5 in the sales grid. |
| **SCA-10** — Comp property rights present + consistent | 🟡 VERIFY | 🟡 manual-verify | `comp_6_leasehold`=∅ | Please indicate the property rights (Fee Simple or Leasehold) for Comp 6 in the sales grid. |
| **SCA-16V** — Comp photo condition cross-check | 🟡 VERIFY | 🟠 extraction-gap | — | Please open the report and visually confirm that the front photo matches the subject property address. Automated photo review is not available for thi… |
| **SCA-17** — Above-grade GLA matches grid, improvements & sketch | 🟡 VERIFY | 🟡 manual-verify | `subject_grid_gla`=1391@0.97; `gla`=1391@0.97; `sketch_living_area`=∅ | The living area couldn't be confirmed across all sources (SCA grid 1391, improvements 1391, sketch n/a sf). Please verify the GLA in the sales grid ma… |
| **SCA-18** — Comp basement present | 🟡 VERIFY | 🟡 manual-verify | `comp_1_basement`=∅ | Basement and below-grade rooms are missing for Comp 1. Please fill this in (finished sq ft and room count, or 'None' if there is none). |
| **SCA-18** — Comp basement present | 🟡 VERIFY | 🟡 manual-verify | `comp_2_basement`=∅ | Basement and below-grade rooms are missing for Comp 2. Please fill this in (finished sq ft and room count, or 'None' if there is none). |
| **SCA-18** — Comp basement present | 🟡 VERIFY | 🟡 manual-verify | `comp_3_basement`=∅ | Basement and below-grade rooms are missing for Comp 3. Please fill this in (finished sq ft and room count, or 'None' if there is none). |
| **SCA-18** — Comp basement present | 🟡 VERIFY | 🟡 manual-verify | `comp_4_basement`=∅ | Basement and below-grade rooms are missing for Comp 4. Please fill this in (finished sq ft and room count, or 'None' if there is none). |
| **SCA-18** — Comp basement present | 🟡 VERIFY | 🟡 manual-verify | `comp_5_basement`=∅ | Basement and below-grade rooms are missing for Comp 5. Please fill this in (finished sq ft and room count, or 'None' if there is none). |
| **SCA-18** — Comp basement present | 🟡 VERIFY | 🟡 manual-verify | `comp_6_basement`=∅ | Basement and below-grade rooms are missing for Comp 6. Please fill this in (finished sq ft and room count, or 'None' if there is none). |
| **SCA-19** — Comp functional utility present | 🟡 VERIFY | 🟡 manual-verify | `comp_1_functional_utility`=∅ | Please add functional utility for Comp 1 in the sales grid. |
| **SCA-19** — Comp functional utility present | 🟡 VERIFY | 🟡 manual-verify | `comp_2_functional_utility`=∅ | Please add functional utility for Comp 2 in the sales grid. |
| **SCA-19** — Comp functional utility present | 🟡 VERIFY | 🟡 manual-verify | `comp_3_functional_utility`=∅ | Please add functional utility for Comp 3 in the sales grid. |
| **SCA-19** — Comp functional utility present | 🟡 VERIFY | 🟡 manual-verify | `comp_4_functional_utility`=∅ | Please add functional utility for Comp 4 in the sales grid. |
| **SCA-19** — Comp functional utility present | 🟡 VERIFY | 🟡 manual-verify | `comp_5_functional_utility`=∅ | Please add functional utility for Comp 5 in the sales grid. |
| **SCA-19** — Comp functional utility present | 🟡 VERIFY | 🟡 manual-verify | `comp_6_functional_utility`=∅ | Please add functional utility for Comp 6 in the sales grid. |
| **SCA-2** — Minimum comparable sales | 🟡 VERIFY | 🟡 manual-verify | `comp_1_sale_price`=1225000@0.97; `comp_2_sale_price`=1129000@0.97; `comp_3_sale_price`=1194000@0.97 | Comp 6 appear to be closed sales in the grid, but the settlement date or MLS status is missing or shows active/pending — Comp 6: settlement date blank… |
| **SCA-20** — Comp heating/cooling present | 🟡 VERIFY | 🟡 manual-verify | `comp_1_heating_cooling`=∅ | Please add the heating/cooling information for Comp 1 in the sales grid. |
| **SCA-20** — Comp heating/cooling present | 🟡 VERIFY | 🟡 manual-verify | `comp_2_heating_cooling`=∅ | Please add the heating/cooling information for Comp 2 in the sales grid. |
| **SCA-20** — Comp heating/cooling present | 🟡 VERIFY | 🟡 manual-verify | `comp_3_heating_cooling`=∅ | Please add the heating/cooling information for Comp 3 in the sales grid. |
| **SCA-20** — Comp heating/cooling present | 🟡 VERIFY | 🟡 manual-verify | `comp_4_heating_cooling`=∅ | Please add the heating/cooling information for Comp 4 in the sales grid. |
| **SCA-20** — Comp heating/cooling present | 🟡 VERIFY | 🟡 manual-verify | `comp_5_heating_cooling`=∅ | Please add the heating/cooling information for Comp 5 in the sales grid. |
| **SCA-20** — Comp heating/cooling present | 🟡 VERIFY | 🟡 manual-verify | `comp_6_heating_cooling`=∅ | Please add the heating/cooling information for Comp 6 in the sales grid. |
| **SCA-22** — Comp porch/patio/deck present | 🟡 VERIFY | 🟡 manual-verify | `comp_1_porch_patio_deck`=∅ | Please add the porch, patio, or deck information for Comp 1 in the sales grid. |
| **SCA-22** — Comp porch/patio/deck present | 🟡 VERIFY | 🟡 manual-verify | `comp_2_porch_patio_deck`=∅ | Please add the porch, patio, or deck information for Comp 2 in the sales grid. |
| **SCA-22** — Comp porch/patio/deck present | 🟡 VERIFY | 🟡 manual-verify | `comp_3_porch_patio_deck`=∅ | Please add the porch, patio, or deck information for Comp 3 in the sales grid. |
| **SCA-22** — Comp porch/patio/deck present | 🟡 VERIFY | 🟡 manual-verify | `comp_4_porch_patio_deck`=∅ | Please add the porch, patio, or deck information for Comp 4 in the sales grid. |
| **SCA-22** — Comp porch/patio/deck present | 🟡 VERIFY | 🟡 manual-verify | `comp_5_porch_patio_deck`=∅ | Please add the porch, patio, or deck information for Comp 5 in the sales grid. |
| **SCA-22** — Comp porch/patio/deck present | 🟡 VERIFY | 🟡 manual-verify | `comp_6_porch_patio_deck`=∅ | Please add the porch, patio, or deck information for Comp 6 in the sales grid. |
| **SCA-27** — Comparable photos present + type | 🟡 VERIFY | 🟡 manual-verify | `comp_photo_pages`=∅ | Photo check required — verify that comparable sale photos are present and match the correct properties. |
| **DOC-1** — License current at signature | 🟡 VERIFY | 🟡 manual-verify | `appraiser_cert_expiration_date`=2028-03-02@0.97; `date_of_signature`=∅ | The license expiration or signature date could not be read; please verify the license was current when the report was signed. |
| **SIG-4** — Appraiser email present | 🟡 VERIFY | 🟡 manual-verify | `appraiser_email`=∅ | The appraiser's email address is missing or unreadable. Please provide it. |
| **SIG-D** — Signature date >= effective date | 🟡 VERIFY | 🟡 manual-verify | `date_of_signature`=∅; `effective_date`=2026-06-19@0.97 | The signature date or effective date could not be read; please verify the signature date is on or after the effective date. |
| **ST-10** — Adverse site conditions addressed | 🟡 VERIFY | 🟠 extraction-gap | `adverse_site_conditions`=∅ | The adverse site conditions answer could not be extracted; manual review required. |
| **ST-8** — FEMA flood data complete; zone addressed | 🟡 VERIFY | 🟡 manual-verify | `fema_flood_hazard`=∅; `fema_flood_zone`=∅; `fema_map_date`=∅ | The flood zone information (zone, map number, and map date) must be completed in the site section — this is required even if the property is not in a … |
| **LISTING-CMNT** — Listing price vs appraised value commentary | 🟡 VERIFY | 🔵 advisory | `listing_history`=DOM 59;Subject property was offered for sale.;La…@0.97; `appraised_value`=1240000@0.97; `listed_past_year`=Y@0.97 | The most recent listing price ($1,199,000) differs from the final value ($1,240,000) by 3.3%. Please add a comment in the report explaining this diffe… |
| **S-4d** — Tax year current | 🟡 VERIFY | 🟡 manual-verify | `tax_year`=∅; `effective_date`=2026-06-19@0.97 | The tax year / effective date could not be extracted; please verify the tax year is within the last 2 years. |
| **S-6b** — Map reference numeric | 🟡 VERIFY | 🟠 extraction-gap | `map_reference`=∅ | Map Reference could not be extracted from the document; manual review required. |
| **ADD-5** — 1004MC inventory analysis complete | 🟢 PASS | — | `mca_total_sales_prior_7_12`=5@0.97; `mca_total_sales_prior_4_6`=5@0.97; `mca_total_sales_current_3`=6@0.97; `mca_absorption_rate_prior_7_12`=0.83@0.97 | Condition satisfied by the extracted value(s). |
| **ADD-X** — Addenda cross-reference resolution | 🟢 PASS | — | — | Condition satisfied by the extracted value(s). |
| **C-2a** — Contract price matches purchase agreement | 🟢 PASS | — | `contract_price`=1199000@0.97 | Condition satisfied by the extracted value(s). |
| **C-2b** — Contract date matches purchase agreement | 🟢 PASS | — | `contract_date`=2026-06-07@0.97 | Condition satisfied by the extracted value(s). |
| **TL-CONTRACT** — Contract date precedes appraisal effective date | 🟢 PASS | — | `contract_date`=2026-06-07@0.97; `effective_date`=2026-06-19@0.97 | Condition satisfied by the extracted value(s). |
| **I-1** — General description complete | 🟢 PASS | — | `units_count`=1@0.97; `stories`=1.0@0.97; `dwelling_type`=Detached@0.97; `design_style`=DT1;Ranch@0.97; `year_built`=1962@0.97; `effective_age`=10@0.97 | Condition satisfied by the extracted value(s). |
| **I-10** — Adverse livability conditions addressed | 🟢 PASS | — | `adverse_conditions`=No@0.97 | Condition satisfied by the extracted value(s). |
| **I-12** — Additions addressed | 🟢 PASS | — | — | Condition satisfied by the extracted value(s). |
| **I-2** — Foundation described | 🟢 PASS | — | `foundation_type`=Concrete / Average@0.97 | Condition satisfied by the extracted value(s). |
| **I-7** — Above-grade room count present | 🟢 PASS | — | `total_rooms`=6@0.97; `bedrooms`=3@0.97; `baths`=2.0@0.97; `gla`=1391@0.97 | Condition satisfied by the extracted value(s). |
| **I-AGE** — Effective age does not exceed actual age | 🟢 PASS | — | `effective_age`=10@0.97; `year_built`=1962@0.97; `effective_date`=2026-06-19@0.97 | Condition satisfied by the extracted value(s). |
| **I-YRBUILT** — Year built consistent with actual age | 🟢 PASS | — | `year_built`=1962@0.97; `effective_date`=2026-06-19@0.97; `effective_age`=10@0.97 | Condition satisfied by the extracted value(s). |
| **IM-2** — Bedroom / total-room count consistency | 🟢 PASS | — | `total_rooms`=6@0.97; `bedrooms`=3@0.97 | Condition satisfied by the extracted value(s). |
| **N-1** — Neighborhood characteristics marked | 🟢 PASS | — | `location`=Suburban@0.97 | Condition satisfied by the extracted value(s). |
| **N-1** — Neighborhood characteristics marked | 🟢 PASS | — | `built_up`=Over75Percent@0.97 | Condition satisfied by the extracted value(s). |
| **N-1** — Neighborhood characteristics marked | 🟢 PASS | — | `growth_rate`=Stable@0.97 | Condition satisfied by the extracted value(s). |
| **N-2** — Housing trends marked and consistent | 🟢 PASS | — | `property_values`=Stable@0.97 | Condition satisfied by the extracted value(s). |
| **N-2** — Housing trends marked and consistent | 🟢 PASS | — | `demand_supply`=InBalance@0.97 | Condition satisfied by the extracted value(s). |
| **N-2** — Housing trends marked and consistent | 🟢 PASS | — | `marketing_time`=UnderThreeMonths@0.97 | Condition satisfied by the extracted value(s). |
| **N-3** — Price/age ranges valid | 🟢 PASS | — | `price_low`=1129@0.97; `price_high`=1289@0.97 | Condition satisfied by the extracted value(s). |
| **N-3** — Price/age ranges valid | 🟢 PASS | — | `age_low`=62@0.97; `age_high`=67@0.97 | Condition satisfied by the extracted value(s). |
| **N-4** — Present land use sums to 100% | 🟢 PASS | — | `land_use_one_unit`=70@0.97; `land_use_2_4_unit`=20@0.97; `land_use_multi_family`=5@0.97; `land_use_commercial`=5@0.97; `land_use_other`=0@0.97 | Condition satisfied by the extracted value(s). |
| **N-5** — All four boundaries delineated | 🟢 PASS | — | `neighborhood_boundaries`=The defined market area boundaries for the subje…@0.97 | Condition satisfied by the extracted value(s). |
| **PH-1** — Subject front/rear/street photos | 🟢 PASS | — | `photo_front`=True@0.97; `photo_rear`=True@0.97; `photo_street`=True@0.97 | Condition satisfied by the extracted value(s). |
| **CA-ARITH** — Cost approach arithmetic cross-check | 🟢 PASS | — | `site_value`=800000@0.97; `total_improvements_cost`=490275@0.97; `total_depreciation`=89034@0.97; `cost_approach_value`=1241241@0.97 | Condition satisfied by the extracted value(s). |
| **R-2** — As-Is / Subject-To checked | 🟢 PASS | — | `appraisal_subject_to`=As Is@0.97 | Condition satisfied by the extracted value(s). |
| **R-2b** — Value equals contract price (bias advisory) | 🟢 PASS | — | `appraised_value`=1240000@0.97; `contract_price`=1199000@0.97 | Condition satisfied by the extracted value(s). |
| **R-EXPOSURE** — Exposure time stated as a specific period | 🟢 PASS | — | `addendum_text`=Scope of Work:  The scope of work refers to the …@0.97; `final_reconciliation_comment`=∅ | Condition satisfied by the extracted value(s). |
| **R-MKTTIME** — Marketing time consistent with neighborhood data | 🟢 PASS | — | `marketing_time_typical`=UnderThreeMonths@0.97; `addendum_text`=Scope of Work:  The scope of work refers to the …@0.97 | Condition satisfied by the extracted value(s). |
| **R-VALUE-RANGE** — Final value within range of developed approach values | 🟢 PASS | — | `appraised_value`=1240000@0.97; `final_value_sca`=1240000@0.97; `cost_approach_value`=1241241@0.97 | Condition satisfied by the extracted value(s). |
| **RECON-T** — Reconciliation forbidden terms | 🟢 PASS | — | `final_reconciliation_comment`=∅ | Condition satisfied by the extracted value(s). |
| **VAL-1** — Final opinion of value extraction integrity | 🟢 PASS | — | `appraised_value`=1240000@0.97; `contract_price`=1199000@0.97 | Condition satisfied by the extracted value(s). |
| **CG-CONC-DIR** — Concession adjustment wrong direction | 🟢 PASS | — | `comp_6_sale_price`=1134000@0.97; `comp_6_concessions`=Listing@0.97; `comp_6_financing_adj`=0@0.97 | Condition satisfied by the extracted value(s). |
| **CG-CONC-DIR** — Concession adjustment wrong direction | 🟢 PASS | — | `comp_7_sale_price`=1149000@0.97; `comp_7_concessions`=Listing@0.97; `comp_7_financing_adj`=0@0.97 | Condition satisfied by the extracted value(s). |
| **CG-COND-CONSIST** — Condition adjustment consistency across comps | 🟢 PASS | — | `comp_1_condition_adj`=∅; `comp_2_condition_adj`=100000@0.97; `comp_3_condition_adj`=50000@0.97 | Condition satisfied by the extracted value(s). |
| **CG-DIST** — Comp distance threshold by area type | 🟢 PASS | — | `comp_1_proximity`=1.48 miles NW@0.97; `comp_2_proximity`=0.33 miles NW@0.97; `comp_3_proximity`=0.81 miles W@0.97 | Condition satisfied by the extracted value(s). |
| **CG-GLA-BRACKET** — Subject GLA bracketed by comp GLAs | 🟢 PASS | — | `subject_grid_gla`=1391@0.97; `gla`=1391@0.97; `comp_1_gla`=1266@0.97; `comp_2_gla`=1430@0.97; `comp_3_gla`=1486@0.97 | Condition satisfied by the extracted value(s). |
| **CG-NET-BIAS** — Net adjustment directional bias | 🟢 PASS | — | `comp_1_net_adjustment`=15000@0.97; `comp_2_net_adjustment`=115000@0.97; `comp_3_net_adjustment`=45000@0.97 | Condition satisfied by the extracted value(s). |
| **CG-PRIOR-SALE** — Comp prior sale rapid appreciation flag | 🟢 PASS | — | `comp_1_prior_sale_date`=2025-12-25@0.97; `comp_2_prior_sale_date`=∅; `comp_3_prior_sale_date`=∅ | No comparable prior sales within the look-back window with material price changes. |
| **SCA-11** — Comp site size has unit | 🟢 PASS | — | `comp_1_site_size`=6500 sf@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-11** — Comp site size has unit | 🟢 PASS | — | `comp_2_site_size`=6936 sf@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-11** — Comp site size has unit | 🟢 PASS | — | `comp_3_site_size`=6000 sf@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-11** — Comp site size has unit | 🟢 PASS | — | `comp_4_site_size`=6000 sf@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-11** — Comp site size has unit | 🟢 PASS | — | `comp_5_site_size`=6000 sf@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-11** — Comp site size has unit | 🟢 PASS | — | `comp_6_site_size`=6000 sf@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-12** — Comp view UAD format | 🟢 PASS | — | `comp_1_view`=N;Res;@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-12** — Comp view UAD format | 🟢 PASS | — | `comp_2_view`=N;Res;@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-12** — Comp view UAD format | 🟢 PASS | — | `comp_3_view`=N;Res;@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-12** — Comp view UAD format | 🟢 PASS | — | `comp_4_view`=N;Res;@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-12** — Comp view UAD format | 🟢 PASS | — | `comp_5_view`=N;Res;@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-12** — Comp view UAD format | 🟢 PASS | — | `comp_6_view`=N;Res;@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-13** — Comp design present | 🟢 PASS | — | `comp_1_design`=DT1;Ranch@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-13** — Comp design present | 🟢 PASS | — | `comp_2_design`=DT1;Ranch@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-13** — Comp design present | 🟢 PASS | — | `comp_3_design`=DT1;Ranch@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-13** — Comp design present | 🟢 PASS | — | `comp_4_design`=DT1;Ranch@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-13** — Comp design present | 🟢 PASS | — | `comp_5_design`=DT1;Ranch@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-13** — Comp design present | 🟢 PASS | — | `comp_6_design`=DT1;Ranch@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-14** — Comp quality UAD rating + zero-adj | 🟢 PASS | — | `comp_1_quality_rating`=Q4@0.97; `quality_rating`=∅; `comp_1_quality_rating_adjustment`=∅ | Condition satisfied by the extracted value(s). |
| **SCA-14** — Comp quality UAD rating + zero-adj | 🟢 PASS | — | `comp_2_quality_rating`=Q4@0.97; `quality_rating`=∅; `comp_2_quality_rating_adjustment`=∅ | Condition satisfied by the extracted value(s). |
| **SCA-14** — Comp quality UAD rating + zero-adj | 🟢 PASS | — | `comp_3_quality_rating`=Q4@0.97; `quality_rating`=∅; `comp_3_quality_rating_adjustment`=∅ | Condition satisfied by the extracted value(s). |
| **SCA-14** — Comp quality UAD rating + zero-adj | 🟢 PASS | — | `comp_4_quality_rating`=Q4@0.97; `quality_rating`=∅; `comp_4_quality_rating_adjustment`=∅ | Condition satisfied by the extracted value(s). |
| **SCA-14** — Comp quality UAD rating + zero-adj | 🟢 PASS | — | `comp_5_quality_rating`=Q4@0.97; `quality_rating`=∅; `comp_5_quality_rating_adjustment`=∅ | Condition satisfied by the extracted value(s). |
| **SCA-14** — Comp quality UAD rating + zero-adj | 🟢 PASS | — | `comp_6_quality_rating`=Q4@0.97; `quality_rating`=∅; `comp_6_quality_rating_adjustment`=∅ | Condition satisfied by the extracted value(s). |
| **SCA-15** — Subject actual age vs year built | 🟢 PASS | — | `subject_grid_actual_age`=∅; `year_built`=1962@0.97 | Year built (1962) implies age of 64 years — consistent with effective date. |
| **SCA-16** — Comp condition UAD rating + zero-adj | 🟢 PASS | — | `comp_1_condition_rating`=C2@0.97; `condition_rating`=∅; `comp_1_condition_rating_adjustment`=∅ | Condition satisfied by the extracted value(s). |
| **SCA-16** — Comp condition UAD rating + zero-adj | 🟢 PASS | — | `comp_2_condition_rating`=C4@0.97; `condition_rating`=∅; `comp_2_condition_rating_adjustment`=∅ | Condition satisfied by the extracted value(s). |
| **SCA-16** — Comp condition UAD rating + zero-adj | 🟢 PASS | — | `comp_3_condition_rating`=C3@0.97; `condition_rating`=∅; `comp_3_condition_rating_adjustment`=∅ | Condition satisfied by the extracted value(s). |
| **SCA-16** — Comp condition UAD rating + zero-adj | 🟢 PASS | — | `comp_4_condition_rating`=C4@0.97; `condition_rating`=∅; `comp_4_condition_rating_adjustment`=∅ | Condition satisfied by the extracted value(s). |
| **SCA-16** — Comp condition UAD rating + zero-adj | 🟢 PASS | — | `comp_5_condition_rating`=C2@0.97; `condition_rating`=∅; `comp_5_condition_rating_adjustment`=∅ | Condition satisfied by the extracted value(s). |
| **SCA-16** — Comp condition UAD rating + zero-adj | 🟢 PASS | — | `comp_6_condition_rating`=C4@0.97; `condition_rating`=∅; `comp_6_condition_rating_adjustment`=∅ | Condition satisfied by the extracted value(s). |
| **SCA-17** — Above-grade GLA matches grid, improvements & sketch | 🟢 PASS | — | `comp_1_gla`=1266@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-17** — Above-grade GLA matches grid, improvements & sketch | 🟢 PASS | — | `comp_2_gla`=1430@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-17** — Above-grade GLA matches grid, improvements & sketch | 🟢 PASS | — | `comp_3_gla`=1486@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-17** — Above-grade GLA matches grid, improvements & sketch | 🟢 PASS | — | `comp_4_gla`=1332@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-17** — Above-grade GLA matches grid, improvements & sketch | 🟢 PASS | — | `comp_5_gla`=1380@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-17** — Above-grade GLA matches grid, improvements & sketch | 🟢 PASS | — | `comp_6_gla`=1575@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-21** — Comp garage/carport present | 🟢 PASS | — | `comp_1_garage_carport`=2ga2dw@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-21** — Comp garage/carport present | 🟢 PASS | — | `comp_2_garage_carport`=2ga2dw@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-21** — Comp garage/carport present | 🟢 PASS | — | `comp_3_garage_carport`=2ga2dw@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-21** — Comp garage/carport present | 🟢 PASS | — | `comp_4_garage_carport`=2ga2dw@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-21** — Comp garage/carport present | 🟢 PASS | — | `comp_5_garage_carport`=2ga2dw@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-21** — Comp garage/carport present | 🟢 PASS | — | `comp_6_garage_carport`=2ga2dw@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-26** — Subject GLA bracketed by comps | 🟢 PASS | — | `gla`=1391@0.97; `comp_1_gla`=1266@0.97; `comp_2_gla`=1430@0.97; `comp_3_gla`=1486@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-3** — Comp address present | 🟢 PASS | — | `comp_1_address`=11901 Saint Mark St, Garden Grove, CA@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-3** — Comp address present | 🟢 PASS | — | `comp_2_address`=6691 Killarney Ave, Garden Grove, CA@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-3** — Comp address present | 🟢 PASS | — | `comp_3_address`=6141 Trinette Ave, Garden Grove, CA@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-3** — Comp address present | 🟢 PASS | — | `comp_4_address`=12661 Saint Mark St, Garden Grove, CA@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-3** — Comp address present | 🟢 PASS | — | `comp_5_address`=12711 Tunstall St, Garden Grove, CA@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-3** — Comp address present | 🟢 PASS | — | `comp_6_address`=6801 Park Ave, Garden Grove, CA@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-4** — Comp proximity present | 🟢 PASS | — | `comp_1_proximity`=1.48 miles NW@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-4** — Comp proximity present | 🟢 PASS | — | `comp_2_proximity`=0.33 miles NW@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-4** — Comp proximity present | 🟢 PASS | — | `comp_3_proximity`=0.81 miles W@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-4** — Comp proximity present | 🟢 PASS | — | `comp_4_proximity`=1.40 miles W@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-4** — Comp proximity present | 🟢 PASS | — | `comp_5_proximity`=1.47 miles W@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-4** — Comp proximity present | 🟢 PASS | — | `comp_6_proximity`=0.15 miles W@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-5** — Comp data source present | 🟢 PASS | — | `comp_1_data_source`=SoCalMLS;DOM 5@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-5** — Comp data source present | 🟢 PASS | — | `comp_2_data_source`=SoCalMLS;DOM 8@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-5** — Comp data source present | 🟢 PASS | — | `comp_3_data_source`=SoCalMLS;DOM 12@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-5** — Comp data source present | 🟢 PASS | — | `comp_4_data_source`=SoCalMLS;DOM 11@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-5** — Comp data source present | 🟢 PASS | — | `comp_5_data_source`=SoCalMLS;DOM 10@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-5** — Comp data source present | 🟢 PASS | — | `comp_6_data_source`=SoCalMLS;DOM 42@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-6** — Comp verification source specific | 🟢 PASS | — | `comp_1_verification_source`=MLS# OC26075303, FARE System@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-6** — Comp verification source specific | 🟢 PASS | — | `comp_2_verification_source`=MLS# PW26047700, FARE System@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-6** — Comp verification source specific | 🟢 PASS | — | `comp_3_verification_source`=MLS# PW26044541, FARE System@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-6** — Comp verification source specific | 🟢 PASS | — | `comp_4_verification_source`=MLS# CV26035498, FARE System@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-6** — Comp verification source specific | 🟢 PASS | — | `comp_5_verification_source`=MLS# OC26057769, FARE System@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-6** — Comp verification source specific | 🟢 PASS | — | `comp_6_verification_source`=MLS# OC26093224, FARE System@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-8** — Comp date of sale sequencing | 🟢 PASS | — | `comp_1_sale_date`=s05/26;c04/26@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-8** — Comp date of sale sequencing | 🟢 PASS | — | `comp_2_sale_date`=s04/26;c03/26@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-8** — Comp date of sale sequencing | 🟢 PASS | — | `comp_3_sale_date`=s04/26;c03/26@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-8** — Comp date of sale sequencing | 🟢 PASS | — | `comp_4_sale_date`=s04/26;c03/26@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-8** — Comp date of sale sequencing | 🟢 PASS | — | `comp_5_sale_date`=s04/26;c03/26@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-9** — Comp location UAD format | 🟢 PASS | — | `comp_1_location_rating`=A;Res;FdrTrafficSt@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-9** — Comp location UAD format | 🟢 PASS | — | `comp_2_location_rating`=A;Res;CrnsTrafficSt@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-9** — Comp location UAD format | 🟢 PASS | — | `comp_3_location_rating`=N;Res;@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-9** — Comp location UAD format | 🟢 PASS | — | `comp_4_location_rating`=A;Res;FdrTrafficSt@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-9** — Comp location UAD format | 🟢 PASS | — | `comp_5_location_rating`=N;Res;@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-9** — Comp location UAD format | 🟢 PASS | — | `comp_6_location_rating`=N;Res;@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-BR** — Value bracketed by adjusted prices | 🟢 PASS | — | `appraised_value`=1240000@0.97; `comp_1_adjusted_sale_price`=1240000@0.97; `comp_2_adjusted_sale_price`=1244000@0.97; `comp_3_adjusted_sale_price`=1239000@0.97; `comp_4_adjusted_sale_price`=1245000@0.97; `comp_5_adjusted_sale_price`=1274000@0.97; `comp_6_adjusted_sale_price`=1210200@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-BR2** — Min comps with adjusted value at/above final opinion (lender overlay) | 🟢 PASS | — | `appraised_value`=1240000@0.97; `comp_1_adjusted_sale_price`=1240000@0.97; `comp_2_adjusted_sale_price`=1244000@0.97; `comp_3_adjusted_sale_price`=1239000@0.97; `comp_4_adjusted_sale_price`=1245000@0.97; `comp_5_adjusted_sale_price`=1274000@0.97; `comp_6_adjusted_sale_price`=1210200@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-DC** — Comp sale within date currency window | 🟢 PASS | — | `comp_1_sale_date`=s05/26;c04/26@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-DC** — Comp sale within date currency window | 🟢 PASS | — | `comp_2_sale_date`=s04/26;c03/26@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-DC** — Comp sale within date currency window | 🟢 PASS | — | `comp_3_sale_date`=s04/26;c03/26@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-DC** — Comp sale within date currency window | 🟢 PASS | — | `comp_4_sale_date`=s04/26;c03/26@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-DC** — Comp sale within date currency window | 🟢 PASS | — | `comp_5_sale_date`=s04/26;c03/26@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-DC** — Comp sale within date currency window | 🟢 PASS | — | `comp_6_sale_date`=c06/26@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-FLIP** — Comp rapid resale flag | 🟢 PASS | — | `comp_1_prior_sale_date`=2025-12-25@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-GROSS** — Gross adjustment per comp within 25% | 🟢 PASS | — | `comp_1_gross_adj_pct`=1@0.97; `comp_2_gross_adj_pct`=10@0.97; `comp_3_gross_adj_pct`=10@0.97; `comp_4_gross_adj_pct`=13@0.97; `comp_5_gross_adj_pct`=3@0.97; `comp_6_gross_adj_pct`=14@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-NET** — Net adjustment within 15% | 🟢 PASS | — | `comp_1_net_adjustment`=15000@0.97; `comp_2_net_adjustment`=115000@0.97; `comp_3_net_adjustment`=45000@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-PR** — Comp sale price bracket vs subject value | 🟢 PASS | — | `comp_1_sale_price`=1225000@0.97; `appraised_value`=1240000@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-PR** — Comp sale price bracket vs subject value | 🟢 PASS | — | `comp_2_sale_price`=1129000@0.97; `appraised_value`=1240000@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-PR** — Comp sale price bracket vs subject value | 🟢 PASS | — | `comp_3_sale_price`=1194000@0.97; `appraised_value`=1240000@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-PR** — Comp sale price bracket vs subject value | 🟢 PASS | — | `comp_4_sale_price`=1155000@0.97; `appraised_value`=1240000@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-PR** — Comp sale price bracket vs subject value | 🟢 PASS | — | `comp_5_sale_price`=1289000@0.97; `appraised_value`=1240000@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-PR** — Comp sale price bracket vs subject value | 🟢 PASS | — | `comp_6_sale_price`=1134000@0.97; `appraised_value`=1240000@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-PSH** — Subject prior sale analyzed | 🟢 PASS | — | `subject_grid_prior_sale_date`=∅; `effective_date`=2026-06-19@0.97 | Condition satisfied by the extracted value(s). |
| **SIG-1** — Appraiser signed / name present | 🟢 PASS | — | `appraiser_name`=Mark Iverson@0.97; `date_of_signature`=∅ | Condition satisfied by the extracted value(s). |
| **SIG-3** — Appraiser licensed in property state | 🟢 PASS | — | `appraiser_license_state`=CA@0.97; `state`=CA@0.97 | Condition satisfied by the extracted value(s). |
| **ST-GEO-COMP** — Appraiser geographic competency | 🟢 PASS | — | `appraiser_license_state`=CA@0.97; `state`=CA@0.97 | Condition satisfied by the extracted value(s). |
| **ST-1** — Site dimensions provided | 🟢 PASS | — | `site_dimensions`=60 X 100@0.97 | Condition satisfied by the extracted value(s). |
| **ST-2** — Site area has correct unit | 🟢 PASS | — | `site_area`=6000 sf@0.97; `site_area_unit`=∅ | Condition satisfied by the extracted value(s). |
| **ST-3** — Site shape provided | 🟢 PASS | — | `site_shape`=Rectangular@0.97 | Condition satisfied by the extracted value(s). |
| **ST-4** — View UAD compliant and consistent | 🟢 PASS | — | `site_view`=N;Res;@0.97 | Condition satisfied by the extracted value(s). |
| **ST-5** — Zoning compliance | 🟢 PASS | — | `zoning_compliance`=Legal@0.97 | Condition satisfied by the extracted value(s). |
| **ST-6** — Highest & best use is Yes | 🟢 PASS | — | `highest_and_best_use`=Yes@0.97 | Condition satisfied by the extracted value(s). |
| **ST-7** — Utilities marked; private systems addressed | 🟢 PASS | — | `utilities_electricity`=Public@0.97; `utilities_gas`=Public@0.97 | Condition satisfied by the extracted value(s). |
| **ST-9** — Utilities/off-site typical for market | 🟢 PASS | — | `utilities_water`=Public@0.97; `utilities_sewer`=Public@0.97 | Condition satisfied by the extracted value(s). |
| **ST-HBU** — Highest and best use stated and consistent | 🟢 PASS | — | `highest_and_best_use`=Yes@0.97; `highest_best_use_indicator`=∅; `highest_best_use_description`=∅ | Condition satisfied by the extracted value(s). |
| **ST-RIGHTS** — Leasehold property rights disclosure | 🟢 PASS | — | `property_rights`=FeeSimple@0.97; `addendum_text`=Scope of Work:  The scope of work refers to the …@0.97 | Condition satisfied by the extracted value(s). |
| **I-HOA-PUD** — HOA/PUD consistency | 🟢 PASS | — | `hoa_dues`=∅; `is_pud`=∅ | Condition satisfied by the extracted value(s). |
| **S-11** — Property rights appraised present | 🟢 PASS | — | `property_rights`=FeeSimple@0.97 | Condition satisfied by the extracted value(s). |
| **S-4b** — APN present and plausible | 🟢 PASS | — | `assessors_parcel_number`=217-251-07@0.97 | Condition satisfied by the extracted value(s). |
| **S-5** — Neighborhood name valid | 🟢 PASS | — | `neighborhood_name`=Garden Park@0.97 | Condition satisfied by the extracted value(s). |
| **S-6** — Census tract format | 🟢 PASS | — | `census_tract`=1100.04@0.97 | Condition satisfied by the extracted value(s). |
| **S-7** — Occupancy status marked | 🟢 PASS | — | `occupant_status`=Vacant@0.97 | Condition satisfied by the extracted value(s). |
| **S-7** — Occupancy status marked | 🟢 PASS | — | `occupant_status`=Vacant@0.97 | Condition satisfied by the extracted value(s). |
| **S-9** — HOA dues imply PUD marked | 🟢 PASS | — | `hoa_dues`=∅; `is_pud_checked`=∅ | Condition satisfied by the extracted value(s). |
| **ST-FORM-MATCH** — Form type matches property type | 🟢 PASS | — | `design_style`=DT1;Ranch@0.97 | Condition satisfied by the extracted value(s). |
| **ST-INTENDED** — Intended use and intended user stated | 🟢 PASS | — | `addendum_text`=Scope of Work:  The scope of work refers to the …@0.97 | Condition satisfied by the extracted value(s). |
| **ST-SCOPE** — Scope of work stated | 🟢 PASS | — | `addendum_text`=Scope of Work:  The scope of work refers to the …@0.97 | Condition satisfied by the extracted value(s). |
| **ADD-2** — Comparable selection commentary explains why | ⚪ N/A | — | — | No substantive sales-comparison narrative extracted. |
| **ADD-4** — 1004MC required for FHA/USDA | ⚪ N/A | — | — | Not applicable to this loan/transaction/form type. |
| **ADD-8** — 1004MC condo project section complete | ⚪ N/A | — | — | Not applicable to this loan/transaction/form type. |
| **C-5** — Personal property addressed | ⚪ N/A | — | — | Not applicable to this loan/transaction/form type. |
| **C-BUYER-MATCH** — Buyer names match borrower(s) on order | ⚪ N/A | — | — | Not applicable to this loan/transaction/form type. |
| **C-EXEC** — Contract fully executed by all parties | ⚪ N/A | — | `contract_analysis_comment`=∅ | No contract analysis commentary extracted; C-1 governs. |
| **C-PKG-EXEC** — Contract fully executed (manual verification) | ⚪ N/A | — | — | Not applicable to this loan/transaction/form type. |
| **ORD-ASSIGN-MATCH** — Assignment type in engagement letter matches appraisal report | ⚪ N/A | — | — | Not applicable to this loan/transaction/form type. |
| **ORD-EXEC-STOP** — Unsigned contract blocked by engagement letter policy | ⚪ N/A | — | — | Not applicable to this loan/transaction/form type. |
| **CA-2** — Remaining economic life >= 30 (FHA/VA) | ⚪ N/A | — | — | Not applicable to this loan/transaction/form type. |
| **FHA-1** — FHA Minimum Property Requirements confirmed | ⚪ N/A | — | — | Not applicable to this loan/transaction/form type. |
| **FHA-10** — FHA remaining economic life >= 30 | ⚪ N/A | — | — | Not applicable to this loan/transaction/form type. |
| **FHA-12** — FHA well/septic compliance | ⚪ N/A | — | — | Not applicable to this loan/transaction/form type. |
| **FHA-13** — FHA appliances present/operational | ⚪ N/A | — | — | Not applicable to this loan/transaction/form type. |
| **FHA-2** — FHA case number format + match | ⚪ N/A | — | — | Not applicable to this loan/transaction/form type. |
| **FHA-3** — FHA intended use/user statements | ⚪ N/A | — | — | Not applicable to this loan/transaction/form type. |
| **FHA-4** — FHA/HUD certification statement present | ⚪ N/A | — | — | Not applicable to this loan/transaction/form type. |
| **FHA-5** — FHA primary comps within 12 months | ⚪ N/A | — | — | Not applicable to this loan/transaction/form type. |
| **FHA-6** — FHA repairs reported subject-to | ⚪ N/A | — | — | Not applicable to this loan/transaction/form type. |
| **FHA-7** — FHA space heater not primary heat | ⚪ N/A | — | — | Not applicable to this loan/transaction/form type. |
| **FHA-9** — FHA four-side photos | ⚪ N/A | — | — | Not applicable to this loan/transaction/form type. |
| **G-1** — Loan-type consistency (engagement vs appraisal) | ⚪ N/A | — | `loan_type`=∅; `fha_case_number`=∅ | Engagement letter / order form not available. |
| **G-C56** — C5/C6 condition triggers AMC stop | ⚪ N/A | — | — | Not applicable to this loan/transaction/form type. |
| **G-LAVA** — Hawaiian lava zone triggers AMC stop | ⚪ N/A | — | — | Not applicable to this loan/transaction/form type. |
| **G-MFG** — Pre-1976 manufactured home triggers AMC stop | ⚪ N/A | — | — | Not applicable to this loan/transaction/form type. |
| **ORD-CONFLICT** — Engagement letter and XML disagree on order-level facts | ⚪ N/A | — | — | Not applicable to this loan/transaction/form type. |
| **IA-1** — Income approach rent matches rent schedule | ⚪ N/A | — | — | Income approach / rent schedule not developed. |
| **MF-1** — Multi-family requires income approach | ⚪ N/A | — | — | Not applicable to this loan/transaction/form type. |
| **R-INCOME-REQ** — Income approach developed when required | ⚪ N/A | — | `income_approach_value`=0@0.97; `occupancy_type`=Vacant@0.97 | Income approach not required for this occupancy type. |
| **CG-NONARMS** — Non-arms-length comp without commentary | ⚪ N/A | — | — | No non-arms-length distress indicators found in comparables. |
| **SCA-23** — Listing comp adjustment | ⚪ N/A | — | — | no listing/active comparables |
| **SCA-25** — New construction competing comp | ⚪ N/A | — | — | subject is not new construction |
| **SCA-PSH-Q** — Subject sale history analysis is substantive | ⚪ N/A | — | — | No prior sale/transfer within the look-back window; quality check not applicable. |
| **ORD-ENG-DATE** — Engagement letter predates appraisal report | ⚪ N/A | — | — | Not applicable to this loan/transaction/form type. |
| **SIG-2** — Appraiser name matches engagement | ⚪ N/A | — | — | Not applicable to this loan/transaction/form type. |
| **SIG-SUP** — Supervisory appraiser section complete | ⚪ N/A | — | — | Not applicable to this loan/transaction/form type. |
| **SIG-TRAINEE** — Trainee appraiser requires supervisory cosign | ⚪ N/A | — | `appraiser_license_type`=Certificate@0.97; `supervisory_appraiser_name`=∅; `supervisory_appraiser_cert_number`=∅ | Rule does not apply to this loan/form/transaction type. |
| **ST-PRIOR-SVC** — Prior services disclosure | ⚪ N/A | — | `prior_services_indicator`=∅; `prior_services_description`=∅; `addendum_text`=Scope of Work:  The scope of work refers to the …@0.97 | Rule does not apply to this loan/form/transaction type. |
| **TL-ENG** — Engagement letter date precedes report signature date | ⚪ N/A | — | — | Not applicable to this loan/transaction/form type. |
| **ST-1B** — Site area magnitude plausibility (multi-signal) | ⚪ N/A | — | `site_area`=6000 sf@0.97; `site_area_unit`=∅ | Rule does not apply to this loan/form/transaction type. |
| **ST-FLOOD-CMT** — Flood zone present — marketability commentary required | ⚪ N/A | — | — | Not applicable to this loan/transaction/form type. |
| **ST-ZONE-NC** — Zoning non-conformance commentary | ⚪ N/A | — | `zoning_compliance`=Legal@0.97; `addendum_text`=Scope of Work:  The scope of work refers to the …@0.97 | Rule does not apply to this loan/form/transaction type. |
| **ORD-COBORROWER** — Co-borrower from order appears in appraisal borrower field | ⚪ N/A | — | — | Not applicable to this loan/transaction/form type. |
| **ORD-FORM-MATCH** — Form type in report matches form type ordered | ⚪ N/A | — | — | Not applicable to this loan/transaction/form type. |
| **ORD-INSP-SCOPE** — Ordered inspection type matches report scope of work | ⚪ N/A | — | — | Not applicable to this loan/transaction/form type. |
| **S-1** — Property address matches order form | ⚪ N/A | — | `property_address`=6951 Stanford Ave@0.97 | Engagement letter / order form not available. |
| **S-1** — Property address matches order form | ⚪ N/A | — | `city`=Garden Grove@0.97 | Engagement letter / order form not available. |
| **S-1** — Property address matches order form | ⚪ N/A | — | `zip_code`=92845-2937@0.97 | Engagement letter / order form not available. |
| **S-10a** — Lender name matches order form | ⚪ N/A | — | `lender_name`=American Heritage Lending@0.97 | Engagement letter / order form not available. |
| **S-10b** — Lender address matches order form | ⚪ N/A | — | — | Engagement letter / order form not available. |
| **S-2** — Borrower matches order form | ⚪ N/A | — | — | Engagement letter / order form not available. |
| **USDA-1** — USDA cost approach required | ⚪ N/A | — | — | Not applicable to this loan/transaction/form type. |


---

## dir 2 — 5807 Fox Hunt Trl.xml

| Rule | Status | Bucket | Extracted (what the rule read) | How it was judged |
|------|--------|--------|-------------------------------|-------------------|
| **SUBJECT-HOLD** — subject | 🔴 FAIL | 🔴 hard-fail | — | 5 failures in the subject section indicate systematic problems (not isolated errors); the section is escalated for a full manual review. |
| **C-3** — Owner-of-record data source present | 🔴 FAIL | 🔴 hard-fail | `is_seller_owner_of_record`=∅; `owner_record_data_source`=∅ | Please provide a data source for the question about whether the seller is the owner of public record (in the contract section). |
| **G-0** — Engagement letter / order form present and extracted | 🔴 FAIL | 🟠 extraction-gap | `loan_type`=∅ | The engagement letter / order form was not extracted. All lender-overlay rules (comp count minimum, site value requirement, declining-market clause, A… |
| **SCA-BR2** — Min comps with adjusted value at/above final opinion (lender overlay) | 🔴 FAIL | 🔴 hard-fail | `appraised_value`=330000@0.97; `comp_1_adjusted_sale_price`=327000@0.97; `comp_2_adjusted_sale_price`=320500@0.97; `comp_3_adjusted_sale_price`=350000@0.97; `comp_4_adjusted_sale_price`=355600@0.97; `comp_5_adjusted_sale_price`=340700@0.97 | Only 1 of the comparable adjusted prices are at or above the final value of $330,000. The client requires at least 2. Please add a comp with an adjust… |
| **S-12** — Prior-listing data source present | 🔴 FAIL | 🔴 hard-fail | `offered_for_sale_12mo`=∅; `data_source`=∅ | The checkbox about prior sale or listing activity in the past 12 months is missing a data source. Please provide the source used to answer this questi… |
| **S-3** — Owner of public record present | 🔴 FAIL | 🔴 hard-fail | `owner_of_public_record`=∅; `legal_description`=∅; `real_estate_taxes`=∅; `special_assessments`=∅ | The 'Owner of Public Record' field is blank. Please complete it. |
| **ADD-9** — USPAP addendum complete | 🟡 VERIFY | 🟠 extraction-gap | — | The USPAP addendum fields (report type, reasonable exposure time, prior services) could not be extracted; manual review required. |
| **C-1** — Contract analyzed (purchase) / section blank (refinance) | 🟡 VERIFY | 🟡 manual-verify | `did_analyze_contract`=∅ | The contract analysis is missing. Please complete the contract analysis or explain why it was not done. |
| **C-1** — Contract analyzed (purchase) / section blank (refinance) | 🟡 VERIFY | 🟡 manual-verify | `sale_type`=∅; `contract_analysis_comment`=∅ | The type of sale is not identified. Please note whether this is an Arm's-Length sale, REO, Short Sale, Court-Ordered Sale, or Non-Arm's-Length in the … |
| **C-4** — Concessions consistent and match purchase agreement | 🟡 VERIFY | 🟡 manual-verify | `has_financial_assistance`=∅; `financial_assistance_amount`=∅ | The seller concession checkbox (financial assistance) is not answered. Please mark Yes or No. |
| **C-4** — Concessions consistent and match purchase agreement | 🟡 VERIFY | 🟡 manual-verify | `financial_assistance_amount`=∅; `financial_assistance_description`=∅ | Seller-concessions cross-check. The appraisal report shows — Seller concessions / financial assistance not stated in the report; Concession descriptio… |
| **C-ANALYZE** — Contract analysis indicator consistency | 🟡 VERIFY | 🟡 manual-verify | `contract_analyzed`=Y@0.97 | The report says the contract was reviewed, but no purchase contract was included in the file. Please provide the contract or update the contract secti… |
| **CA-1** — Opinion of site value present | 🟡 VERIFY | 🟡 manual-verify | `site_value_estimate`=∅ | The cost approach is missing an opinion of site value. Please provide one. |
| **I-11** — Conforms to neighborhood | 🟡 VERIFY | 🟠 extraction-gap | `conforms_to_neighborhood`=∅ | Conformity to the neighborhood could not be read; please verify the improvements conform. |
| **I-34** — Materials/condition described | 🟡 VERIFY | 🟡 manual-verify | `exterior_walls`=∅; `roof_surface`=∅; `heating`=∅; `floor_material`=∅; `walls_material`=∅; `trim_finish_material`=∅ | The following materials/condition fields are missing in the improvements section: Exterior Walls, Roof Surface, Heating, Floors, Walls, Trim/Finish. P… |
| **I-5** — Heating and cooling described | 🟡 VERIFY | 🟡 manual-verify | `heating`=∅; `cooling`=∅ | The following heating/cooling fields are not described in the improvements section: Heating, Cooling. Please complete. |
| **I-6** — Appliances reported | 🟡 VERIFY | 🟡 manual-verify | `appliance_refrigerator`=∅; `appliance_range_oven`=∅; `appliance_disposal`=∅; `appliance_dishwasher`=∅; `appliance_microwave`=∅; `appliance_washer_dryer`=∅ | No kitchen appliances are listed in the improvements section. Please note which appliances are present. |
| **I-8** — Additional features described | 🟡 VERIFY | 🟡 manual-verify | `fireplace_count`=∅; `porch_patio_deck`=∅; `additional_features`=∅ | Please confirm any additional features (fireplace, porch/patio/deck, pool, etc.) are described in the improvements section, or state 'None'. |
| **I-9** — Condition rating UAD and consistent | 🟡 VERIFY | 🟠 extraction-gap | `condition_rating`=∅ | Condition could not be extracted from the document; manual review required. |
| **I-Q** — Quality rating UAD format | 🟡 VERIFY | 🟠 extraction-gap | `quality_rating`=∅ | Quality could not be extracted from the document; manual review required. |
| **I-SMCO** — Smoke/CO detector code compliance noted | 🟡 VERIFY | 🟡 manual-verify | `sales_comparison_summary`=∅ | No mention of smoke or CO detectors was found in the report. The client requires a note confirming detectors meet local code — please add one to the r… |
| **N-6** — Neighborhood description specific | 🟡 VERIFY | 🟡 manual-verify | `neighborhood_description`=No unfavorable factors affecting the value or ma…@0.97 | The Neighborhood Description reads like a generic template. Please add specific details — like nearby streets, local landmarks, proximity to schools o… |
| **N-7** — Market conditions completed | 🟡 VERIFY | 🟡 manual-verify | `market_conditions_commentary`=According to MLS and public records statistics, …@0.97 | The market conditions section just says 'See 1004MC' instead of containing the actual analysis. Please put the market analysis directly in this sectio… |
| **PH-1** — Subject front/rear/street photos | 🟡 VERIFY | 🟡 manual-verify | `photo_front`=∅; `photo_rear`=∅; `photo_street`=∅ | Required photos are missing: front, rear, street scene. At minimum, please include a front photo, a rear photo, and a street scene. |
| **PH-2** — Interior photos present | 🟡 VERIFY | 🟡 manual-verify | `photo_interior_rooms`=∅ | Interior photos are incomplete — missing: kitchen, living, bedroom, bathroom. Please include photos of the kitchen, living room, all bedrooms, and all… |
| **R-1** — SCA value matches market value | 🟡 VERIFY | 🟡 manual-verify | `indicated_value_sca`=∅; `appraised_value`=330000@0.97 | The sales comparison value or final opinion of value could not be read. Please verify both numbers are present and agree. |
| **R-1b** — Reconciliation names the weighted approach | 🟡 VERIFY | 🟡 manual-verify | `final_reconciliation_comment`=∅ | The reconciliation must say which approach was relied on most (sales comparison, cost, or income) and briefly explain why. Please add that statement t… |
| **R-ASSIGN-COND** — Assignment condition vs report language consistency | 🟡 VERIFY | 🟡 manual-verify | `assignment_condition`=AsIs@0.97; `addendum_text`=∅; `limiting_conditions_text`=∅ | The assignment condition box (AsIs) doesn't match the language used in the report narrative. Please make sure the box and the written description agre… |
| **R-EXPOSURE** — Exposure time stated as a specific period | 🟡 VERIFY | 🟡 manual-verify | `addendum_text`=∅; `final_reconciliation_comment`=∅ | No specific exposure time period was found. Please add a statement like 'estimated exposure time of 3-6 months' in the reconciliation or addendum. |
| **R-MKTTIME** — Marketing time consistent with neighborhood data | 🟡 VERIFY | 🟡 manual-verify | `marketing_time_typical`=ThreeToSixMonths@0.97; `addendum_text`=∅ | The marketing time stated in the report appears inconsistent with the market data for this area. Please make sure the estimated selling time matches w… |
| **CG-TIME-CONSIST** — Time/market adjustment rate consistency | 🟡 VERIFY | 🟠 extraction-gap | — | Fewer than 2 comps with measurable time adjustments; rate consistency check skipped — manual review required. |
| **SCA-10** — Comp property rights present + consistent | 🟡 VERIFY | 🟡 manual-verify | `comp_1_leasehold`=∅ | Please indicate the property rights (Fee Simple or Leasehold) for Comp 1 in the sales grid. |
| **SCA-10** — Comp property rights present + consistent | 🟡 VERIFY | 🟡 manual-verify | `comp_2_leasehold`=∅ | Please indicate the property rights (Fee Simple or Leasehold) for Comp 2 in the sales grid. |
| **SCA-10** — Comp property rights present + consistent | 🟡 VERIFY | 🟡 manual-verify | `comp_3_leasehold`=∅ | Please indicate the property rights (Fee Simple or Leasehold) for Comp 3 in the sales grid. |
| **SCA-10** — Comp property rights present + consistent | 🟡 VERIFY | 🟡 manual-verify | `comp_4_leasehold`=∅ | Please indicate the property rights (Fee Simple or Leasehold) for Comp 4 in the sales grid. |
| **SCA-10** — Comp property rights present + consistent | 🟡 VERIFY | 🟡 manual-verify | `comp_5_leasehold`=∅ | Please indicate the property rights (Fee Simple or Leasehold) for Comp 5 in the sales grid. |
| **SCA-16V** — Comp photo condition cross-check | 🟡 VERIFY | 🟠 extraction-gap | — | Please open the report and visually confirm that the front photo matches the subject property address. Automated photo review is not available for thi… |
| **SCA-17** — Above-grade GLA matches grid, improvements & sketch | 🟡 VERIFY | 🟡 manual-verify | `subject_grid_gla`=1576@0.97; `gla`=1576@0.97; `sketch_living_area`=∅ | The living area couldn't be confirmed across all sources (SCA grid 1576, improvements 1576, sketch n/a sf). Please verify the GLA in the sales grid ma… |
| **SCA-18** — Comp basement present | 🟡 VERIFY | 🟡 manual-verify | `comp_1_basement`=∅ | Basement and below-grade rooms are missing for Comp 1. Please fill this in (finished sq ft and room count, or 'None' if there is none). |
| **SCA-18** — Comp basement present | 🟡 VERIFY | 🟡 manual-verify | `comp_2_basement`=∅ | Basement and below-grade rooms are missing for Comp 2. Please fill this in (finished sq ft and room count, or 'None' if there is none). |
| **SCA-18** — Comp basement present | 🟡 VERIFY | 🟡 manual-verify | `comp_3_basement`=∅ | Basement and below-grade rooms are missing for Comp 3. Please fill this in (finished sq ft and room count, or 'None' if there is none). |
| **SCA-18** — Comp basement present | 🟡 VERIFY | 🟡 manual-verify | `comp_4_basement`=∅ | Basement and below-grade rooms are missing for Comp 4. Please fill this in (finished sq ft and room count, or 'None' if there is none). |
| **SCA-18** — Comp basement present | 🟡 VERIFY | 🟡 manual-verify | `comp_5_basement`=∅ | Basement and below-grade rooms are missing for Comp 5. Please fill this in (finished sq ft and room count, or 'None' if there is none). |
| **SCA-19** — Comp functional utility present | 🟡 VERIFY | 🟡 manual-verify | `comp_1_functional_utility`=∅ | Please add functional utility for Comp 1 in the sales grid. |
| **SCA-19** — Comp functional utility present | 🟡 VERIFY | 🟡 manual-verify | `comp_2_functional_utility`=∅ | Please add functional utility for Comp 2 in the sales grid. |
| **SCA-19** — Comp functional utility present | 🟡 VERIFY | 🟡 manual-verify | `comp_3_functional_utility`=∅ | Please add functional utility for Comp 3 in the sales grid. |
| **SCA-19** — Comp functional utility present | 🟡 VERIFY | 🟡 manual-verify | `comp_4_functional_utility`=∅ | Please add functional utility for Comp 4 in the sales grid. |
| **SCA-19** — Comp functional utility present | 🟡 VERIFY | 🟡 manual-verify | `comp_5_functional_utility`=∅ | Please add functional utility for Comp 5 in the sales grid. |
| **SCA-20** — Comp heating/cooling present | 🟡 VERIFY | 🟡 manual-verify | `comp_1_heating_cooling`=∅ | Please add the heating/cooling information for Comp 1 in the sales grid. |
| **SCA-20** — Comp heating/cooling present | 🟡 VERIFY | 🟡 manual-verify | `comp_2_heating_cooling`=∅ | Please add the heating/cooling information for Comp 2 in the sales grid. |
| **SCA-20** — Comp heating/cooling present | 🟡 VERIFY | 🟡 manual-verify | `comp_3_heating_cooling`=∅ | Please add the heating/cooling information for Comp 3 in the sales grid. |
| **SCA-20** — Comp heating/cooling present | 🟡 VERIFY | 🟡 manual-verify | `comp_4_heating_cooling`=∅ | Please add the heating/cooling information for Comp 4 in the sales grid. |
| **SCA-20** — Comp heating/cooling present | 🟡 VERIFY | 🟡 manual-verify | `comp_5_heating_cooling`=∅ | Please add the heating/cooling information for Comp 5 in the sales grid. |
| **SCA-22** — Comp porch/patio/deck present | 🟡 VERIFY | 🟡 manual-verify | `comp_1_porch_patio_deck`=∅ | Please add the porch, patio, or deck information for Comp 1 in the sales grid. |
| **SCA-22** — Comp porch/patio/deck present | 🟡 VERIFY | 🟡 manual-verify | `comp_2_porch_patio_deck`=∅ | Please add the porch, patio, or deck information for Comp 2 in the sales grid. |
| **SCA-22** — Comp porch/patio/deck present | 🟡 VERIFY | 🟡 manual-verify | `comp_3_porch_patio_deck`=∅ | Please add the porch, patio, or deck information for Comp 3 in the sales grid. |
| **SCA-22** — Comp porch/patio/deck present | 🟡 VERIFY | 🟡 manual-verify | `comp_4_porch_patio_deck`=∅ | Please add the porch, patio, or deck information for Comp 4 in the sales grid. |
| **SCA-22** — Comp porch/patio/deck present | 🟡 VERIFY | 🟡 manual-verify | `comp_5_porch_patio_deck`=∅ | Please add the porch, patio, or deck information for Comp 5 in the sales grid. |
| **SCA-27** — Comparable photos present + type | 🟡 VERIFY | 🟡 manual-verify | `comp_photo_pages`=∅ | Photo check required — verify that comparable sale photos are present and match the correct properties. |
| **DOC-1** — License current at signature | 🟡 VERIFY | 🟡 manual-verify | `appraiser_cert_expiration_date`=2026-11-30@0.97; `date_of_signature`=∅ | The license expiration or signature date could not be read; please verify the license was current when the report was signed. |
| **SIG-4** — Appraiser email present | 🟡 VERIFY | 🟡 manual-verify | `appraiser_email`=∅ | The appraiser's email address is missing or unreadable. Please provide it. |
| **SIG-D** — Signature date >= effective date | 🟡 VERIFY | 🟡 manual-verify | `date_of_signature`=∅; `effective_date`=2026-06-23@0.97 | The signature date or effective date could not be read; please verify the signature date is on or after the effective date. |
| **ST-10** — Adverse site conditions addressed | 🟡 VERIFY | 🟠 extraction-gap | `adverse_site_conditions`=∅ | The adverse site conditions answer could not be extracted; manual review required. |
| **ST-8** — FEMA flood data complete; zone addressed | 🟡 VERIFY | 🟡 manual-verify | `fema_flood_hazard`=∅; `fema_flood_zone`=∅; `fema_map_date`=∅ | The flood zone information (zone, map number, and map date) must be completed in the site section — this is required even if the property is not in a … |
| **LISTING-CMNT** — Listing price vs appraised value commentary | 🟡 VERIFY | 🔵 advisory | `listing_history`=DOM 78;MLS, Public Records. The subject is liste…@0.97; `appraised_value`=330000@0.97; `listed_past_year`=Y@0.97 | The most recent listing price ($310,000) differs from the final value ($330,000) by 6.1%. Please add a comment in the report explaining this differenc… |
| **S-4d** — Tax year current | 🟡 VERIFY | 🟡 manual-verify | `tax_year`=∅; `effective_date`=2026-06-23@0.97 | The tax year / effective date could not be extracted; please verify the tax year is within the last 2 years. |
| **S-6b** — Map reference numeric | 🟡 VERIFY | 🟠 extraction-gap | `map_reference`=∅ | Map Reference could not be extracted from the document; manual review required. |
| **ST-INTENDED** — Intended use and intended user stated | 🟡 VERIFY | 🟡 manual-verify | `addendum_text`=∅ | The report must state what the appraisal is for (mortgage lending) and who it is for (the lender/client). Please confirm both of these statements are … |
| **ST-SCOPE** — Scope of work stated | 🟡 VERIFY | 🟡 manual-verify | `addendum_text`=∅ | The scope of work description could not be found. Please verify the report describes what type of inspection was performed and what the appraiser did … |
| **ADD-5** — 1004MC inventory analysis complete | 🟢 PASS | — | `mca_total_sales_prior_7_12`=111@0.97; `mca_total_sales_prior_4_6`=53@0.97; `mca_total_sales_current_3`=34@0.97; `mca_absorption_rate_prior_7_12`=18.50@0.97 | Condition satisfied by the extracted value(s). |
| **ADD-X** — Addenda cross-reference resolution | 🟢 PASS | — | — | Condition satisfied by the extracted value(s). |
| **C-2a** — Contract price matches purchase agreement | 🟢 PASS | — | `contract_price`=315000@0.97 | Condition satisfied by the extracted value(s). |
| **C-2b** — Contract date matches purchase agreement | 🟢 PASS | — | `contract_date`=2026-06-07@0.97 | Condition satisfied by the extracted value(s). |
| **TL-CONTRACT** — Contract date precedes appraisal effective date | 🟢 PASS | — | `contract_date`=2026-06-07@0.97; `effective_date`=2026-06-23@0.97 | Condition satisfied by the extracted value(s). |
| **I-1** — General description complete | 🟢 PASS | — | `units_count`=1@0.97; `stories`=1@0.97; `dwelling_type`=Detached@0.97; `design_style`=1-Sty ranch@0.97; `year_built`=1988@0.97; `effective_age`=15@0.97 | Condition satisfied by the extracted value(s). |
| **I-10** — Adverse livability conditions addressed | 🟢 PASS | — | `adverse_conditions`=No@0.97 | Condition satisfied by the extracted value(s). |
| **I-12** — Additions addressed | 🟢 PASS | — | — | Condition satisfied by the extracted value(s). |
| **I-2** — Foundation described | 🟢 PASS | — | `foundation_type`=Pour Concrete/Avg@0.97 | Condition satisfied by the extracted value(s). |
| **I-7** — Above-grade room count present | 🟢 PASS | — | `total_rooms`=6@0.97; `bedrooms`=3@0.97; `baths`=2.0@0.97; `gla`=1576@0.97 | Condition satisfied by the extracted value(s). |
| **I-AGE** — Effective age does not exceed actual age | 🟢 PASS | — | `effective_age`=15@0.97; `year_built`=1988@0.97; `effective_date`=2026-06-23@0.97 | Condition satisfied by the extracted value(s). |
| **I-YRBUILT** — Year built consistent with actual age | 🟢 PASS | — | `year_built`=1988@0.97; `effective_date`=2026-06-23@0.97; `effective_age`=15@0.97 | Condition satisfied by the extracted value(s). |
| **IM-2** — Bedroom / total-room count consistency | 🟢 PASS | — | `total_rooms`=6@0.97; `bedrooms`=3@0.97 | Condition satisfied by the extracted value(s). |
| **N-1** — Neighborhood characteristics marked | 🟢 PASS | — | `location`=Suburban@0.97 | Condition satisfied by the extracted value(s). |
| **N-1** — Neighborhood characteristics marked | 🟢 PASS | — | `built_up`=25To75Percent@0.97 | Condition satisfied by the extracted value(s). |
| **N-1** — Neighborhood characteristics marked | 🟢 PASS | — | `growth_rate`=Stable@0.97 | Condition satisfied by the extracted value(s). |
| **N-2** — Housing trends marked and consistent | 🟢 PASS | — | `property_values`=Stable@0.97 | Condition satisfied by the extracted value(s). |
| **N-2** — Housing trends marked and consistent | 🟢 PASS | — | `demand_supply`=InBalance@0.97 | Condition satisfied by the extracted value(s). |
| **N-2** — Housing trends marked and consistent | 🟢 PASS | — | `marketing_time`=ThreeToSixMonths@0.97 | Condition satisfied by the extracted value(s). |
| **N-3** — Price/age ranges valid | 🟢 PASS | — | `price_low`=225@0.97; `price_high`=400@0.97 | Condition satisfied by the extracted value(s). |
| **N-3** — Price/age ranges valid | 🟢 PASS | — | `age_low`=0@0.97; `age_high`=50@0.97 | Condition satisfied by the extracted value(s). |
| **N-4** — Present land use sums to 100% | 🟢 PASS | — | `land_use_one_unit`=80@0.97; `land_use_2_4_unit`=2@0.97; `land_use_multi_family`=3@0.97; `land_use_commercial`=5@0.97; `land_use_other`=10@0.97 | Condition satisfied by the extracted value(s). |
| **N-4** — Present land use sums to 100% | 🟢 PASS | — | `land_use_other`=10@0.97 | Condition satisfied by the extracted value(s). |
| **N-5** — All four boundaries delineated | 🟢 PASS | — | `neighborhood_boundaries`=Subject's market area is North of Hwy 414, South…@0.97 | Condition satisfied by the extracted value(s). |
| **CA-ARITH** — Cost approach arithmetic cross-check | 🟢 PASS | — | `site_value`=55000@0.97; `total_improvements_cost`=360612@0.97; `total_depreciation`=90153@0.97; `cost_approach_value`=330459@0.97 | Condition satisfied by the extracted value(s). |
| **R-2** — As-Is / Subject-To checked | 🟢 PASS | — | `appraisal_subject_to`=As Is@0.97 | Condition satisfied by the extracted value(s). |
| **R-2b** — Value equals contract price (bias advisory) | 🟢 PASS | — | `appraised_value`=330000@0.97; `contract_price`=315000@0.97 | Condition satisfied by the extracted value(s). |
| **R-VALUE-RANGE** — Final value within range of developed approach values | 🟢 PASS | — | `appraised_value`=330000@0.97; `final_value_sca`=330000@0.97; `cost_approach_value`=330459@0.97 | Condition satisfied by the extracted value(s). |
| **RECON-T** — Reconciliation forbidden terms | 🟢 PASS | — | `final_reconciliation_comment`=∅ | Condition satisfied by the extracted value(s). |
| **VAL-1** — Final opinion of value extraction integrity | 🟢 PASS | — | `appraised_value`=330000@0.97; `contract_price`=315000@0.97 | Condition satisfied by the extracted value(s). |
| **CG-CONC-DIR** — Concession adjustment wrong direction | 🟢 PASS | — | `comp_4_sale_price`=324500@0.97; `comp_4_concessions`=Listing@0.97; `comp_4_financing_adj`=0@0.97 | Condition satisfied by the extracted value(s). |
| **CG-CONC-DIR** — Concession adjustment wrong direction | 🟢 PASS | — | `comp_5_sale_price`=360000@0.97; `comp_5_concessions`=Listing@0.97; `comp_5_financing_adj`=0@0.97 | Condition satisfied by the extracted value(s). |
| **CG-COND-CONSIST** — Condition adjustment consistency across comps | 🟢 PASS | — | `comp_1_condition_adj`=∅; `comp_2_condition_adj`=∅; `comp_3_condition_adj`=∅ | Condition satisfied by the extracted value(s). |
| **CG-DIST** — Comp distance threshold by area type | 🟢 PASS | — | `comp_1_proximity`=0.22 miles NW@0.97; `comp_2_proximity`=0.79 miles NE@0.97; `comp_3_proximity`=0.88 miles E@0.97 | Condition satisfied by the extracted value(s). |
| **CG-GLA-BRACKET** — Subject GLA bracketed by comp GLAs | 🟢 PASS | — | `subject_grid_gla`=1576@0.97; `gla`=1576@0.97; `comp_1_gla`=1436@0.97; `comp_2_gla`=1467@0.97; `comp_3_gla`=1593@0.97 | Condition satisfied by the extracted value(s). |
| **CG-NET-BIAS** — Net adjustment directional bias | 🟢 PASS | — | `comp_1_net_adjustment`=17000@0.97; `comp_2_net_adjustment`=5500@0.97; `comp_3_net_adjustment`=0@0.97 | Condition satisfied by the extracted value(s). |
| **CG-PRIOR-SALE** — Comp prior sale rapid appreciation flag | 🟢 PASS | — | `comp_1_prior_sale_date`=∅; `comp_2_prior_sale_date`=∅; `comp_3_prior_sale_date`=∅ | No comparable prior sales within the look-back window with material price changes. |
| **SCA-11** — Comp site size has unit | 🟢 PASS | — | `comp_1_site_size`=8579 sf@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-11** — Comp site size has unit | 🟢 PASS | — | `comp_2_site_size`=12996 sf@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-11** — Comp site size has unit | 🟢 PASS | — | `comp_3_site_size`=10187 sf@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-11** — Comp site size has unit | 🟢 PASS | — | `comp_4_site_size`=17672 sf@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-11** — Comp site size has unit | 🟢 PASS | — | `comp_5_site_size`=10801 sf@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-12** — Comp view UAD format | 🟢 PASS | — | `comp_1_view`=N;Res;@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-12** — Comp view UAD format | 🟢 PASS | — | `comp_2_view`=N;Res;@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-12** — Comp view UAD format | 🟢 PASS | — | `comp_3_view`=N;Res;@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-12** — Comp view UAD format | 🟢 PASS | — | `comp_4_view`=N;Res;@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-12** — Comp view UAD format | 🟢 PASS | — | `comp_5_view`=N;Res;@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-13** — Comp design present | 🟢 PASS | — | `comp_1_design`=DT1;1-Sty ranch@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-13** — Comp design present | 🟢 PASS | — | `comp_2_design`=DT1;1-Sty ranch@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-13** — Comp design present | 🟢 PASS | — | `comp_3_design`=DT1;1-Sty ranch@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-13** — Comp design present | 🟢 PASS | — | `comp_4_design`=DT1;1-Sty ranch@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-13** — Comp design present | 🟢 PASS | — | `comp_5_design`=DT1;1-Sty ranch@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-14** — Comp quality UAD rating + zero-adj | 🟢 PASS | — | `comp_1_quality_rating`=Q4@0.97; `quality_rating`=∅; `comp_1_quality_rating_adjustment`=∅ | Condition satisfied by the extracted value(s). |
| **SCA-14** — Comp quality UAD rating + zero-adj | 🟢 PASS | — | `comp_2_quality_rating`=Q4@0.97; `quality_rating`=∅; `comp_2_quality_rating_adjustment`=∅ | Condition satisfied by the extracted value(s). |
| **SCA-14** — Comp quality UAD rating + zero-adj | 🟢 PASS | — | `comp_3_quality_rating`=Q4@0.97; `quality_rating`=∅; `comp_3_quality_rating_adjustment`=∅ | Condition satisfied by the extracted value(s). |
| **SCA-14** — Comp quality UAD rating + zero-adj | 🟢 PASS | — | `comp_4_quality_rating`=Q4@0.97; `quality_rating`=∅; `comp_4_quality_rating_adjustment`=∅ | Condition satisfied by the extracted value(s). |
| **SCA-14** — Comp quality UAD rating + zero-adj | 🟢 PASS | — | `comp_5_quality_rating`=Q4@0.97; `quality_rating`=∅; `comp_5_quality_rating_adjustment`=∅ | Condition satisfied by the extracted value(s). |
| **SCA-15** — Subject actual age vs year built | 🟢 PASS | — | `subject_grid_actual_age`=∅; `year_built`=1988@0.97 | Year built (1988) implies age of 38 years — consistent with effective date. |
| **SCA-16** — Comp condition UAD rating + zero-adj | 🟢 PASS | — | `comp_1_condition_rating`=C3@0.97; `condition_rating`=∅; `comp_1_condition_rating_adjustment`=∅ | Condition satisfied by the extracted value(s). |
| **SCA-16** — Comp condition UAD rating + zero-adj | 🟢 PASS | — | `comp_2_condition_rating`=C3@0.97; `condition_rating`=∅; `comp_2_condition_rating_adjustment`=∅ | Condition satisfied by the extracted value(s). |
| **SCA-16** — Comp condition UAD rating + zero-adj | 🟢 PASS | — | `comp_3_condition_rating`=C3@0.97; `condition_rating`=∅; `comp_3_condition_rating_adjustment`=∅ | Condition satisfied by the extracted value(s). |
| **SCA-16** — Comp condition UAD rating + zero-adj | 🟢 PASS | — | `comp_4_condition_rating`=C3@0.97; `condition_rating`=∅; `comp_4_condition_rating_adjustment`=∅ | Condition satisfied by the extracted value(s). |
| **SCA-16** — Comp condition UAD rating + zero-adj | 🟢 PASS | — | `comp_5_condition_rating`=C3@0.97; `condition_rating`=∅; `comp_5_condition_rating_adjustment`=∅ | Condition satisfied by the extracted value(s). |
| **SCA-17** — Above-grade GLA matches grid, improvements & sketch | 🟢 PASS | — | `comp_1_gla`=1436@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-17** — Above-grade GLA matches grid, improvements & sketch | 🟢 PASS | — | `comp_2_gla`=1467@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-17** — Above-grade GLA matches grid, improvements & sketch | 🟢 PASS | — | `comp_3_gla`=1593@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-17** — Above-grade GLA matches grid, improvements & sketch | 🟢 PASS | — | `comp_4_gla`=1155@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-17** — Above-grade GLA matches grid, improvements & sketch | 🟢 PASS | — | `comp_5_gla`=1961@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-2** — Minimum comparable sales | 🟢 PASS | — | `comp_1_sale_price`=310000@0.97; `comp_2_sale_price`=315000@0.97; `comp_3_sale_price`=350000@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-21** — Comp garage/carport present | 🟢 PASS | — | `comp_1_garage_carport`=2ga2dw@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-21** — Comp garage/carport present | 🟢 PASS | — | `comp_2_garage_carport`=2ga2dw@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-21** — Comp garage/carport present | 🟢 PASS | — | `comp_3_garage_carport`=2ga2dw@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-21** — Comp garage/carport present | 🟢 PASS | — | `comp_4_garage_carport`=2ga2dw@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-21** — Comp garage/carport present | 🟢 PASS | — | `comp_5_garage_carport`=2ga2dw@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-23** — Listing comp adjustment | 🟢 PASS | — | `comp_4_sale_date`=Active@0.97; `comp_4_net_adjustment`=31100@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-23** — Listing comp adjustment | 🟢 PASS | — | `comp_5_sale_date`=Active@0.97; `comp_5_net_adjustment`=-19300@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-26** — Subject GLA bracketed by comps | 🟢 PASS | — | `gla`=1576@0.97; `comp_1_gla`=1436@0.97; `comp_2_gla`=1467@0.97; `comp_3_gla`=1593@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-3** — Comp address present | 🟢 PASS | — | `comp_1_address`=5502 Park Hurst Dr, Orlando, FL@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-3** — Comp address present | 🟢 PASS | — | `comp_2_address`=5555 Caurus Ct, Orlando, FL@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-3** — Comp address present | 🟢 PASS | — | `comp_3_address`=5417 Lighthouse Rd, Orlando, FL@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-3** — Comp address present | 🟢 PASS | — | `comp_4_address`=6245 Fox Hunt Trl, Orlando, FL@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-3** — Comp address present | 🟢 PASS | — | `comp_5_address`=4922 Briar Oaks Cir, Orlando, FL@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-4** — Comp proximity present | 🟢 PASS | — | `comp_1_proximity`=0.22 miles NW@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-4** — Comp proximity present | 🟢 PASS | — | `comp_2_proximity`=0.79 miles NE@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-4** — Comp proximity present | 🟢 PASS | — | `comp_3_proximity`=0.88 miles E@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-4** — Comp proximity present | 🟢 PASS | — | `comp_4_proximity`=0.38 miles W@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-4** — Comp proximity present | 🟢 PASS | — | `comp_5_proximity`=1.58 miles E@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-5** — Comp data source present | 🟢 PASS | — | `comp_1_data_source`=MFRMLS S5137635;DOM 5@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-5** — Comp data source present | 🟢 PASS | — | `comp_2_data_source`=MFRMLS O6305005;DOM 11@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-5** — Comp data source present | 🟢 PASS | — | `comp_3_data_source`=MRFMLS TB8441350;DOM 93@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-5** — Comp data source present | 🟢 PASS | — | `comp_4_data_source`=MFRMLS S5148140;DOM 66@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-5** — Comp data source present | 🟢 PASS | — | `comp_5_data_source`=MFRMLS O6414887;DOM 6@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-6** — Comp verification source specific | 🟢 PASS | — | `comp_1_verification_source`=Public Records/Tax Card@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-6** — Comp verification source specific | 🟢 PASS | — | `comp_2_verification_source`=PublicRecords/Tax Card@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-6** — Comp verification source specific | 🟢 PASS | — | `comp_3_verification_source`=Tax Card/Field Insp /Pub Rec@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-6** — Comp verification source specific | 🟢 PASS | — | `comp_4_verification_source`=PublicRecords/Tax Card@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-6** — Comp verification source specific | 🟢 PASS | — | `comp_5_verification_source`=PublicRecords/Tax Card@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-8** — Comp date of sale sequencing | 🟢 PASS | — | `comp_1_sale_date`=s02/26;c12/25@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-8** — Comp date of sale sequencing | 🟢 PASS | — | `comp_2_sale_date`=s06/25;c05/25@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-8** — Comp date of sale sequencing | 🟢 PASS | — | `comp_3_sale_date`=s03/26;c01/26@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-9** — Comp location UAD format | 🟢 PASS | — | `comp_1_location_rating`=N;Res;@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-9** — Comp location UAD format | 🟢 PASS | — | `comp_2_location_rating`=N;Res;@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-9** — Comp location UAD format | 🟢 PASS | — | `comp_3_location_rating`=N;Res;@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-9** — Comp location UAD format | 🟢 PASS | — | `comp_4_location_rating`=N;Res;@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-9** — Comp location UAD format | 🟢 PASS | — | `comp_5_location_rating`=N;Res;@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-BR** — Value bracketed by adjusted prices | 🟢 PASS | — | `appraised_value`=330000@0.97; `comp_1_adjusted_sale_price`=327000@0.97; `comp_2_adjusted_sale_price`=320500@0.97; `comp_3_adjusted_sale_price`=350000@0.97; `comp_4_adjusted_sale_price`=355600@0.97; `comp_5_adjusted_sale_price`=340700@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-DC** — Comp sale within date currency window | 🟢 PASS | — | `comp_1_sale_date`=s02/26;c12/25@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-DC** — Comp sale within date currency window | 🟢 PASS | — | `comp_2_sale_date`=s06/25;c05/25@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-DC** — Comp sale within date currency window | 🟢 PASS | — | `comp_3_sale_date`=s03/26;c01/26@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-FLIP** — Comp rapid resale flag | 🟢 PASS | — | `comp_1_prior_sale_date`=∅ | Condition satisfied by the extracted value(s). |
| **SCA-GROSS** — Gross adjustment per comp within 25% | 🟢 PASS | — | `comp_1_gross_adj_pct`=5.5@0.97; `comp_2_gross_adj_pct`=1.7@0.97; `comp_3_gross_adj_pct`=0.0@0.97; `comp_4_gross_adj_pct`=9.6@0.97; `comp_5_gross_adj_pct`=5.4@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-NET** — Net adjustment within 15% | 🟢 PASS | — | `comp_1_net_adjustment`=17000@0.97; `comp_2_net_adjustment`=5500@0.97; `comp_3_net_adjustment`=0@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-PR** — Comp sale price bracket vs subject value | 🟢 PASS | — | `comp_1_sale_price`=310000@0.97; `appraised_value`=330000@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-PR** — Comp sale price bracket vs subject value | 🟢 PASS | — | `comp_2_sale_price`=315000@0.97; `appraised_value`=330000@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-PR** — Comp sale price bracket vs subject value | 🟢 PASS | — | `comp_3_sale_price`=350000@0.97; `appraised_value`=330000@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-PR** — Comp sale price bracket vs subject value | 🟢 PASS | — | `comp_4_sale_price`=324500@0.97; `appraised_value`=330000@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-PR** — Comp sale price bracket vs subject value | 🟢 PASS | — | `comp_5_sale_price`=360000@0.97; `appraised_value`=330000@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-PSH** — Subject prior sale analyzed | 🟢 PASS | — | `subject_grid_prior_sale_date`=∅; `effective_date`=2026-06-23@0.97 | Condition satisfied by the extracted value(s). |
| **SIG-1** — Appraiser signed / name present | 🟢 PASS | — | `appraiser_name`=Timothy Michael Fortune@0.97; `date_of_signature`=∅ | Condition satisfied by the extracted value(s). |
| **SIG-3** — Appraiser licensed in property state | 🟢 PASS | — | `appraiser_license_state`=FL@0.97; `state`=FL@0.97 | Condition satisfied by the extracted value(s). |
| **ST-GEO-COMP** — Appraiser geographic competency | 🟢 PASS | — | `appraiser_license_state`=FL@0.97; `state`=FL@0.97 | Condition satisfied by the extracted value(s). |
| **ST-1** — Site dimensions provided | 🟢 PASS | — | `site_dimensions`=75x125 (Sub to Survey)@0.97 | Condition satisfied by the extracted value(s). |
| **ST-2** — Site area has correct unit | 🟢 PASS | — | `site_area`=9375 sf@0.97; `site_area_unit`=∅ | Condition satisfied by the extracted value(s). |
| **ST-3** — Site shape provided | 🟢 PASS | — | `site_shape`=Rectangular@0.97 | Condition satisfied by the extracted value(s). |
| **ST-4** — View UAD compliant and consistent | 🟢 PASS | — | `site_view`=N;Res;@0.97 | Condition satisfied by the extracted value(s). |
| **ST-5** — Zoning compliance | 🟢 PASS | — | `zoning_compliance`=Legal@0.97 | Condition satisfied by the extracted value(s). |
| **ST-6** — Highest & best use is Yes | 🟢 PASS | — | `highest_and_best_use`=Yes@0.97 | Condition satisfied by the extracted value(s). |
| **ST-7** — Utilities marked; private systems addressed | 🟢 PASS | — | `utilities_electricity`=Public@0.97; `utilities_gas`=None@0.97 | Condition satisfied by the extracted value(s). |
| **ST-9** — Utilities/off-site typical for market | 🟢 PASS | — | `utilities_water`=Public@0.97; `utilities_sewer`=Public@0.97 | Condition satisfied by the extracted value(s). |
| **ST-HBU** — Highest and best use stated and consistent | 🟢 PASS | — | `highest_and_best_use`=Yes@0.97; `highest_best_use_indicator`=∅; `highest_best_use_description`=∅ | Condition satisfied by the extracted value(s). |
| **ST-RIGHTS** — Leasehold property rights disclosure | 🟢 PASS | — | `property_rights`=FeeSimple@0.97; `addendum_text`=∅ | Condition satisfied by the extracted value(s). |
| **I-HOA-PUD** — HOA/PUD consistency | 🟢 PASS | — | `hoa_dues`=∅; `is_pud`=∅ | Condition satisfied by the extracted value(s). |
| **S-11** — Property rights appraised present | 🟢 PASS | — | `property_rights`=FeeSimple@0.97 | Condition satisfied by the extracted value(s). |
| **S-4b** — APN present and plausible | 🟢 PASS | — | `assessors_parcel_number`=01-22-28-7350-00-220@0.97 | Condition satisfied by the extracted value(s). |
| **S-5** — Neighborhood name valid | 🟢 PASS | — | `neighborhood_name`=Regency Park@0.97 | Condition satisfied by the extracted value(s). |
| **S-6** — Census tract format | 🟢 PASS | — | `census_tract`=0123.06@0.97 | Condition satisfied by the extracted value(s). |
| **S-7** — Occupancy status marked | 🟢 PASS | — | `occupant_status`=Vacant@0.97 | Condition satisfied by the extracted value(s). |
| **S-7** — Occupancy status marked | 🟢 PASS | — | `occupant_status`=Vacant@0.97 | Condition satisfied by the extracted value(s). |
| **S-9** — HOA dues imply PUD marked | 🟢 PASS | — | `hoa_dues`=∅; `is_pud_checked`=∅ | Condition satisfied by the extracted value(s). |
| **ST-FORM-MATCH** — Form type matches property type | 🟢 PASS | — | `design_style`=1-Sty ranch@0.97 | Condition satisfied by the extracted value(s). |
| **ADD-2** — Comparable selection commentary explains why | ⚪ N/A | — | — | No substantive sales-comparison narrative extracted. |
| **ADD-4** — 1004MC required for FHA/USDA | ⚪ N/A | — | — | Not applicable to this loan/transaction/form type. |
| **ADD-8** — 1004MC condo project section complete | ⚪ N/A | — | — | Not applicable to this loan/transaction/form type. |
| **C-5** — Personal property addressed | ⚪ N/A | — | — | Not applicable to this loan/transaction/form type. |
| **C-BUYER-MATCH** — Buyer names match borrower(s) on order | ⚪ N/A | — | — | Not applicable to this loan/transaction/form type. |
| **C-EXEC** — Contract fully executed by all parties | ⚪ N/A | — | `contract_analysis_comment`=∅ | No contract analysis commentary extracted; C-1 governs. |
| **C-PKG-EXEC** — Contract fully executed (manual verification) | ⚪ N/A | — | — | Not applicable to this loan/transaction/form type. |
| **ORD-ASSIGN-MATCH** — Assignment type in engagement letter matches appraisal report | ⚪ N/A | — | — | Not applicable to this loan/transaction/form type. |
| **ORD-EXEC-STOP** — Unsigned contract blocked by engagement letter policy | ⚪ N/A | — | — | Not applicable to this loan/transaction/form type. |
| **CA-2** — Remaining economic life >= 30 (FHA/VA) | ⚪ N/A | — | — | Not applicable to this loan/transaction/form type. |
| **FHA-1** — FHA Minimum Property Requirements confirmed | ⚪ N/A | — | — | Not applicable to this loan/transaction/form type. |
| **FHA-10** — FHA remaining economic life >= 30 | ⚪ N/A | — | — | Not applicable to this loan/transaction/form type. |
| **FHA-12** — FHA well/septic compliance | ⚪ N/A | — | — | Not applicable to this loan/transaction/form type. |
| **FHA-13** — FHA appliances present/operational | ⚪ N/A | — | — | Not applicable to this loan/transaction/form type. |
| **FHA-2** — FHA case number format + match | ⚪ N/A | — | — | Not applicable to this loan/transaction/form type. |
| **FHA-3** — FHA intended use/user statements | ⚪ N/A | — | — | Not applicable to this loan/transaction/form type. |
| **FHA-4** — FHA/HUD certification statement present | ⚪ N/A | — | — | Not applicable to this loan/transaction/form type. |
| **FHA-5** — FHA primary comps within 12 months | ⚪ N/A | — | — | Not applicable to this loan/transaction/form type. |
| **FHA-6** — FHA repairs reported subject-to | ⚪ N/A | — | — | Not applicable to this loan/transaction/form type. |
| **FHA-7** — FHA space heater not primary heat | ⚪ N/A | — | — | Not applicable to this loan/transaction/form type. |
| **FHA-9** — FHA four-side photos | ⚪ N/A | — | — | Not applicable to this loan/transaction/form type. |
| **G-1** — Loan-type consistency (engagement vs appraisal) | ⚪ N/A | — | `loan_type`=∅; `fha_case_number`=∅ | Engagement letter / order form not available. |
| **G-C56** — C5/C6 condition triggers AMC stop | ⚪ N/A | — | — | Not applicable to this loan/transaction/form type. |
| **G-LAVA** — Hawaiian lava zone triggers AMC stop | ⚪ N/A | — | — | Not applicable to this loan/transaction/form type. |
| **G-MFG** — Pre-1976 manufactured home triggers AMC stop | ⚪ N/A | — | — | Not applicable to this loan/transaction/form type. |
| **ORD-CONFLICT** — Engagement letter and XML disagree on order-level facts | ⚪ N/A | — | — | Not applicable to this loan/transaction/form type. |
| **IA-1** — Income approach rent matches rent schedule | ⚪ N/A | — | — | Income approach / rent schedule not developed. |
| **MF-1** — Multi-family requires income approach | ⚪ N/A | — | — | Not applicable to this loan/transaction/form type. |
| **R-INCOME-REQ** — Income approach developed when required | ⚪ N/A | — | `income_approach_value`=∅; `occupancy_type`=Vacant@0.97 | Income approach not required for this occupancy type. |
| **CG-NONARMS** — Non-arms-length comp without commentary | ⚪ N/A | — | — | No non-arms-length distress indicators found in comparables. |
| **SCA-25** — New construction competing comp | ⚪ N/A | — | — | subject is not new construction |
| **SCA-PSH-Q** — Subject sale history analysis is substantive | ⚪ N/A | — | — | No prior sale/transfer within the look-back window; quality check not applicable. |
| **ORD-ENG-DATE** — Engagement letter predates appraisal report | ⚪ N/A | — | — | Not applicable to this loan/transaction/form type. |
| **SIG-2** — Appraiser name matches engagement | ⚪ N/A | — | — | Not applicable to this loan/transaction/form type. |
| **SIG-SUP** — Supervisory appraiser section complete | ⚪ N/A | — | — | Not applicable to this loan/transaction/form type. |
| **SIG-TRAINEE** — Trainee appraiser requires supervisory cosign | ⚪ N/A | — | `appraiser_license_type`=Certificate@0.97; `supervisory_appraiser_name`=∅; `supervisory_appraiser_cert_number`=∅ | Rule does not apply to this loan/form/transaction type. |
| **ST-PRIOR-SVC** — Prior services disclosure | ⚪ N/A | — | `prior_services_indicator`=∅; `prior_services_description`=∅; `addendum_text`=∅ | Rule does not apply to this loan/form/transaction type. |
| **TL-ENG** — Engagement letter date precedes report signature date | ⚪ N/A | — | — | Not applicable to this loan/transaction/form type. |
| **ST-1B** — Site area magnitude plausibility (multi-signal) | ⚪ N/A | — | `site_area`=9375 sf@0.97; `site_area_unit`=∅ | Rule does not apply to this loan/form/transaction type. |
| **ST-FLOOD-CMT** — Flood zone present — marketability commentary required | ⚪ N/A | — | — | Not applicable to this loan/transaction/form type. |
| **ST-ZONE-NC** — Zoning non-conformance commentary | ⚪ N/A | — | `zoning_compliance`=Legal@0.97; `addendum_text`=∅ | Rule does not apply to this loan/form/transaction type. |
| **ORD-COBORROWER** — Co-borrower from order appears in appraisal borrower field | ⚪ N/A | — | — | Not applicable to this loan/transaction/form type. |
| **ORD-FORM-MATCH** — Form type in report matches form type ordered | ⚪ N/A | — | — | Not applicable to this loan/transaction/form type. |
| **ORD-INSP-SCOPE** — Ordered inspection type matches report scope of work | ⚪ N/A | — | — | Not applicable to this loan/transaction/form type. |
| **S-1** — Property address matches order form | ⚪ N/A | — | `property_address`=5807 Fox Hunt Trl@0.97 | Engagement letter / order form not available. |
| **S-1** — Property address matches order form | ⚪ N/A | — | `city`=Orlando@0.97 | Engagement letter / order form not available. |
| **S-1** — Property address matches order form | ⚪ N/A | — | `zip_code`=32808@0.97 | Engagement letter / order form not available. |
| **S-10a** — Lender name matches order form | ⚪ N/A | — | `lender_name`=Reach Home Loans LLC@0.97 | Engagement letter / order form not available. |
| **S-10b** — Lender address matches order form | ⚪ N/A | — | — | Engagement letter / order form not available. |
| **S-2** — Borrower matches order form | ⚪ N/A | — | — | Engagement letter / order form not available. |
| **USDA-1** — USDA cost approach required | ⚪ N/A | — | — | Not applicable to this loan/transaction/form type. |


---

## dir 3 — MAGU96793.XML

| Rule | Status | Bucket | Extracted (what the rule read) | How it was judged |
|------|--------|--------|-------------------------------|-------------------|
| **SUBJECT-HOLD** — subject | 🔴 FAIL | 🔴 hard-fail | — | 5 failures in the subject section indicate systematic problems (not isolated errors); the section is escalated for a full manual review. |
| **C-3** — Owner-of-record data source present | 🔴 FAIL | 🔴 hard-fail | `is_seller_owner_of_record`=∅; `owner_record_data_source`=∅ | Please provide a data source for the question about whether the seller is the owner of public record (in the contract section). |
| **G-0** — Engagement letter / order form present and extracted | 🔴 FAIL | 🟠 extraction-gap | `loan_type`=∅ | The engagement letter / order form was not extracted. All lender-overlay rules (comp count minimum, site value requirement, declining-market clause, A… |
| **S-12** — Prior-listing data source present | 🔴 FAIL | 🔴 hard-fail | `offered_for_sale_12mo`=∅; `data_source`=∅ | The checkbox about prior sale or listing activity in the past 12 months is missing a data source. Please provide the source used to answer this questi… |
| **S-3** — Owner of public record present | 🔴 FAIL | 🔴 hard-fail | `owner_of_public_record`=∅; `legal_description`=∅; `real_estate_taxes`=∅; `special_assessments`=∅ | The 'Owner of Public Record' field is blank. Please complete it. |
| **ADD-9** — USPAP addendum complete | 🟡 VERIFY | 🟠 extraction-gap | — | The USPAP addendum fields (report type, reasonable exposure time, prior services) could not be extracted; manual review required. |
| **C-1** — Contract analyzed (purchase) / section blank (refinance) | 🟡 VERIFY | 🟡 manual-verify | `did_analyze_contract`=∅ | The contract analysis is missing. Please complete the contract analysis or explain why it was not done. |
| **C-1** — Contract analyzed (purchase) / section blank (refinance) | 🟡 VERIFY | 🟡 manual-verify | `sale_type`=∅; `contract_analysis_comment`=∅ | The type of sale is not identified. Please note whether this is an Arm's-Length sale, REO, Short Sale, Court-Ordered Sale, or Non-Arm's-Length in the … |
| **C-4** — Concessions consistent and match purchase agreement | 🟡 VERIFY | 🟡 manual-verify | `has_financial_assistance`=∅; `financial_assistance_amount`=∅ | The seller concession checkbox (financial assistance) is not answered. Please mark Yes or No. |
| **C-4** — Concessions consistent and match purchase agreement | 🟡 VERIFY | 🟡 manual-verify | `financial_assistance_amount`=∅; `financial_assistance_description`=∅ | Seller-concessions cross-check. The appraisal report shows — Seller concessions / financial assistance not stated in the report; Concession descriptio… |
| **C-ANALYZE** — Contract analysis indicator consistency | 🟡 VERIFY | 🟡 manual-verify | `contract_analyzed`=Y@0.97 | The report says the contract was reviewed, but no purchase contract was included in the file. Please provide the contract or update the contract secti… |
| **CA-1** — Opinion of site value present | 🟡 VERIFY | 🟡 manual-verify | `site_value_estimate`=∅ | The cost approach is missing an opinion of site value. Please provide one. |
| **I-11** — Conforms to neighborhood | 🟡 VERIFY | 🟠 extraction-gap | `conforms_to_neighborhood`=∅ | Conformity to the neighborhood could not be read; please verify the improvements conform. |
| **I-34** — Materials/condition described | 🟡 VERIFY | 🟡 manual-verify | `exterior_walls`=∅; `roof_surface`=∅; `heating`=∅; `floor_material`=∅; `walls_material`=∅; `trim_finish_material`=∅ | The following materials/condition fields are missing in the improvements section: Exterior Walls, Roof Surface, Heating, Floors, Walls, Trim/Finish. P… |
| **I-5** — Heating and cooling described | 🟡 VERIFY | 🟡 manual-verify | `heating`=∅; `cooling`=∅ | The following heating/cooling fields are not described in the improvements section: Heating, Cooling. Please complete. |
| **I-6** — Appliances reported | 🟡 VERIFY | 🟡 manual-verify | `appliance_refrigerator`=∅; `appliance_range_oven`=∅; `appliance_disposal`=∅; `appliance_dishwasher`=∅; `appliance_microwave`=∅; `appliance_washer_dryer`=∅ | No kitchen appliances are listed in the improvements section. Please note which appliances are present. |
| **I-8** — Additional features described | 🟡 VERIFY | 🟡 manual-verify | `fireplace_count`=∅; `porch_patio_deck`=∅; `additional_features`=∅ | Please confirm any additional features (fireplace, porch/patio/deck, pool, etc.) are described in the improvements section, or state 'None'. |
| **I-9** — Condition rating UAD and consistent | 🟡 VERIFY | 🟠 extraction-gap | `condition_rating`=∅ | Condition could not be extracted from the document; manual review required. |
| **I-Q** — Quality rating UAD format | 🟡 VERIFY | 🟠 extraction-gap | `quality_rating`=∅ | Quality could not be extracted from the document; manual review required. |
| **I-SMCO** — Smoke/CO detector code compliance noted | 🟡 VERIFY | 🟡 manual-verify | `sales_comparison_summary`=∅ | No mention of smoke or CO detectors was found in the report. The client requires a note confirming detectors meet local code — please add one to the r… |
| **PH-1** — Subject front/rear/street photos | 🟡 VERIFY | 🟡 manual-verify | `photo_front`=∅; `photo_rear`=∅; `photo_street`=∅ | Required photos are missing: front, rear, street scene. At minimum, please include a front photo, a rear photo, and a street scene. |
| **PH-2** — Interior photos present | 🟡 VERIFY | 🟡 manual-verify | `photo_interior_rooms`=∅ | Interior photos are incomplete — missing: kitchen, living, bedroom, bathroom. Please include photos of the kitchen, living room, all bedrooms, and all… |
| **R-1** — SCA value matches market value | 🟡 VERIFY | 🟡 manual-verify | `indicated_value_sca`=∅; `appraised_value`=650000@0.97 | The sales comparison value or final opinion of value could not be read. Please verify both numbers are present and agree. |
| **R-1b** — Reconciliation names the weighted approach | 🟡 VERIFY | 🟡 manual-verify | `final_reconciliation_comment`=∅ | The reconciliation must say which approach was relied on most (sales comparison, cost, or income) and briefly explain why. Please add that statement t… |
| **CG-TIME-CONSIST** — Time/market adjustment rate consistency | 🟡 VERIFY | 🟡 manual-verify | `comp_4_financing_adj`=-10000@0.97; `comp_4_sale_date`=s03/26;c02/26@0.97 | Fewer than 2 comps with measurable time adjustments; rate consistency check skipped — manual review required. |
| **SCA-10** — Comp property rights present + consistent | 🟡 VERIFY | 🟡 manual-verify | `comp_1_leasehold`=∅ | Please indicate the property rights (Fee Simple or Leasehold) for Comp 1 in the sales grid. |
| **SCA-10** — Comp property rights present + consistent | 🟡 VERIFY | 🟡 manual-verify | `comp_2_leasehold`=∅ | Please indicate the property rights (Fee Simple or Leasehold) for Comp 2 in the sales grid. |
| **SCA-10** — Comp property rights present + consistent | 🟡 VERIFY | 🟡 manual-verify | `comp_3_leasehold`=∅ | Please indicate the property rights (Fee Simple or Leasehold) for Comp 3 in the sales grid. |
| **SCA-10** — Comp property rights present + consistent | 🟡 VERIFY | 🟡 manual-verify | `comp_4_leasehold`=∅ | Please indicate the property rights (Fee Simple or Leasehold) for Comp 4 in the sales grid. |
| **SCA-10** — Comp property rights present + consistent | 🟡 VERIFY | 🟡 manual-verify | `comp_5_leasehold`=∅ | Please indicate the property rights (Fee Simple or Leasehold) for Comp 5 in the sales grid. |
| **SCA-10** — Comp property rights present + consistent | 🟡 VERIFY | 🟡 manual-verify | `comp_6_leasehold`=∅ | Please indicate the property rights (Fee Simple or Leasehold) for Comp 6 in the sales grid. |
| **SCA-16V** — Comp photo condition cross-check | 🟡 VERIFY | 🟠 extraction-gap | — | Please open the report and visually confirm that the front photo matches the subject property address. Automated photo review is not available for thi… |
| **SCA-17** — Above-grade GLA matches grid, improvements & sketch | 🟡 VERIFY | 🟡 manual-verify | `subject_grid_gla`=948@0.97; `gla`=948@0.97; `sketch_living_area`=∅ | The living area couldn't be confirmed across all sources (SCA grid 948, improvements 948, sketch n/a sf). Please verify the GLA in the sales grid matc… |
| **SCA-18** — Comp basement present | 🟡 VERIFY | 🟡 manual-verify | `comp_1_basement`=∅ | Basement and below-grade rooms are missing for Comp 1. Please fill this in (finished sq ft and room count, or 'None' if there is none). |
| **SCA-18** — Comp basement present | 🟡 VERIFY | 🟡 manual-verify | `comp_2_basement`=∅ | Basement and below-grade rooms are missing for Comp 2. Please fill this in (finished sq ft and room count, or 'None' if there is none). |
| **SCA-18** — Comp basement present | 🟡 VERIFY | 🟡 manual-verify | `comp_3_basement`=∅ | Basement and below-grade rooms are missing for Comp 3. Please fill this in (finished sq ft and room count, or 'None' if there is none). |
| **SCA-18** — Comp basement present | 🟡 VERIFY | 🟡 manual-verify | `comp_4_basement`=∅ | Basement and below-grade rooms are missing for Comp 4. Please fill this in (finished sq ft and room count, or 'None' if there is none). |
| **SCA-18** — Comp basement present | 🟡 VERIFY | 🟡 manual-verify | `comp_5_basement`=∅ | Basement and below-grade rooms are missing for Comp 5. Please fill this in (finished sq ft and room count, or 'None' if there is none). |
| **SCA-18** — Comp basement present | 🟡 VERIFY | 🟡 manual-verify | `comp_6_basement`=∅ | Basement and below-grade rooms are missing for Comp 6. Please fill this in (finished sq ft and room count, or 'None' if there is none). |
| **SCA-19** — Comp functional utility present | 🟡 VERIFY | 🟡 manual-verify | `comp_1_functional_utility`=∅ | Please add functional utility for Comp 1 in the sales grid. |
| **SCA-19** — Comp functional utility present | 🟡 VERIFY | 🟡 manual-verify | `comp_2_functional_utility`=∅ | Please add functional utility for Comp 2 in the sales grid. |
| **SCA-19** — Comp functional utility present | 🟡 VERIFY | 🟡 manual-verify | `comp_3_functional_utility`=∅ | Please add functional utility for Comp 3 in the sales grid. |
| **SCA-19** — Comp functional utility present | 🟡 VERIFY | 🟡 manual-verify | `comp_4_functional_utility`=∅ | Please add functional utility for Comp 4 in the sales grid. |
| **SCA-19** — Comp functional utility present | 🟡 VERIFY | 🟡 manual-verify | `comp_5_functional_utility`=∅ | Please add functional utility for Comp 5 in the sales grid. |
| **SCA-19** — Comp functional utility present | 🟡 VERIFY | 🟡 manual-verify | `comp_6_functional_utility`=∅ | Please add functional utility for Comp 6 in the sales grid. |
| **SCA-20** — Comp heating/cooling present | 🟡 VERIFY | 🟡 manual-verify | `comp_1_heating_cooling`=∅ | Please add the heating/cooling information for Comp 1 in the sales grid. |
| **SCA-20** — Comp heating/cooling present | 🟡 VERIFY | 🟡 manual-verify | `comp_2_heating_cooling`=∅ | Please add the heating/cooling information for Comp 2 in the sales grid. |
| **SCA-20** — Comp heating/cooling present | 🟡 VERIFY | 🟡 manual-verify | `comp_3_heating_cooling`=∅ | Please add the heating/cooling information for Comp 3 in the sales grid. |
| **SCA-20** — Comp heating/cooling present | 🟡 VERIFY | 🟡 manual-verify | `comp_4_heating_cooling`=∅ | Please add the heating/cooling information for Comp 4 in the sales grid. |
| **SCA-20** — Comp heating/cooling present | 🟡 VERIFY | 🟡 manual-verify | `comp_5_heating_cooling`=∅ | Please add the heating/cooling information for Comp 5 in the sales grid. |
| **SCA-20** — Comp heating/cooling present | 🟡 VERIFY | 🟡 manual-verify | `comp_6_heating_cooling`=∅ | Please add the heating/cooling information for Comp 6 in the sales grid. |
| **SCA-22** — Comp porch/patio/deck present | 🟡 VERIFY | 🟡 manual-verify | `comp_1_porch_patio_deck`=∅ | Please add the porch, patio, or deck information for Comp 1 in the sales grid. |
| **SCA-22** — Comp porch/patio/deck present | 🟡 VERIFY | 🟡 manual-verify | `comp_2_porch_patio_deck`=∅ | Please add the porch, patio, or deck information for Comp 2 in the sales grid. |
| **SCA-22** — Comp porch/patio/deck present | 🟡 VERIFY | 🟡 manual-verify | `comp_3_porch_patio_deck`=∅ | Please add the porch, patio, or deck information for Comp 3 in the sales grid. |
| **SCA-22** — Comp porch/patio/deck present | 🟡 VERIFY | 🟡 manual-verify | `comp_4_porch_patio_deck`=∅ | Please add the porch, patio, or deck information for Comp 4 in the sales grid. |
| **SCA-22** — Comp porch/patio/deck present | 🟡 VERIFY | 🟡 manual-verify | `comp_5_porch_patio_deck`=∅ | Please add the porch, patio, or deck information for Comp 5 in the sales grid. |
| **SCA-22** — Comp porch/patio/deck present | 🟡 VERIFY | 🟡 manual-verify | `comp_6_porch_patio_deck`=∅ | Please add the porch, patio, or deck information for Comp 6 in the sales grid. |
| **SCA-27** — Comparable photos present + type | 🟡 VERIFY | 🟡 manual-verify | `comp_photo_pages`=∅ | Photo check required — verify that comparable sale photos are present and match the correct properties. |
| **DOC-1** — License current at signature | 🟡 VERIFY | 🟡 manual-verify | `appraiser_cert_expiration_date`=2027-12-31@0.97; `date_of_signature`=∅ | The license expiration or signature date could not be read; please verify the license was current when the report was signed. |
| **SIG-4** — Appraiser email present | 🟡 VERIFY | 🟡 manual-verify | `appraiser_email`=∅ | The appraiser's email address is missing or unreadable. Please provide it. |
| **SIG-D** — Signature date >= effective date | 🟡 VERIFY | 🟡 manual-verify | `date_of_signature`=∅; `effective_date`=2026-06-17@0.97 | The signature date or effective date could not be read; please verify the signature date is on or after the effective date. |
| **ST-10** — Adverse site conditions addressed | 🟡 VERIFY | 🟠 extraction-gap | `adverse_site_conditions`=∅ | The adverse site conditions answer could not be extracted; manual review required. |
| **ST-8** — FEMA flood data complete; zone addressed | 🟡 VERIFY | 🟡 manual-verify | `fema_flood_hazard`=∅; `fema_flood_zone`=∅; `fema_map_date`=∅ | The flood zone information (zone, map number, and map date) must be completed in the site section — this is required even if the property is not in a … |
| **LISTING-CMNT** — Listing price vs appraised value commentary | 🟡 VERIFY | 🔵 advisory | `listing_history`=Pending RAM-MLS #409603  -  $699,000  -  05/13/2…@0.97; `appraised_value`=650000@0.97; `listed_past_year`=Y@0.97 | The most recent listing price ($699,000) differs from the final value ($650,000) by 7.5%. Please add a comment in the report explaining this differenc… |
| **S-4d** — Tax year current | 🟡 VERIFY | 🟡 manual-verify | `tax_year`=∅; `effective_date`=2026-06-17@0.97 | The tax year / effective date could not be extracted; please verify the tax year is within the last 2 years. |
| **S-6b** — Map reference numeric | 🟡 VERIFY | 🟠 extraction-gap | `map_reference`=∅ | Map Reference could not be extracted from the document; manual review required. |
| **ADD-5** — 1004MC inventory analysis complete | 🟢 PASS | — | `mca_total_sales_prior_7_12`=10@0.97; `mca_total_sales_prior_4_6`=5@0.97; `mca_total_sales_current_3`=3@0.97; `mca_absorption_rate_prior_7_12`=1.67@0.97 | Condition satisfied by the extracted value(s). |
| **ADD-X** — Addenda cross-reference resolution | 🟢 PASS | — | — | Condition satisfied by the extracted value(s). |
| **C-2a** — Contract price matches purchase agreement | 🟢 PASS | — | `contract_price`=650000@0.97 | Condition satisfied by the extracted value(s). |
| **C-2b** — Contract date matches purchase agreement | 🟢 PASS | — | `contract_date`=2026-06-05@0.97 | Condition satisfied by the extracted value(s). |
| **TL-CONTRACT** — Contract date precedes appraisal effective date | 🟢 PASS | — | `contract_date`=2026-06-05@0.97; `effective_date`=2026-06-17@0.97 | Condition satisfied by the extracted value(s). |
| **I-1** — General description complete | 🟢 PASS | — | `units_count`=1@0.97; `stories`=1@0.97; `dwelling_type`=Detached@0.97; `design_style`=Plantation@0.97; `year_built`=1934@0.97; `effective_age`=40@0.97 | Condition satisfied by the extracted value(s). |
| **I-10** — Adverse livability conditions addressed | 🟢 PASS | — | `adverse_conditions`=No@0.97 | Condition satisfied by the extracted value(s). |
| **I-12** — Additions addressed | 🟢 PASS | — | — | Condition satisfied by the extracted value(s). |
| **I-2** — Foundation described | 🟢 PASS | — | `foundation_type`=Post & Pier / Avg@0.97 | Condition satisfied by the extracted value(s). |
| **I-7** — Above-grade room count present | 🟢 PASS | — | `total_rooms`=5@0.97; `bedrooms`=3@0.97; `baths`=1.0@0.97; `gla`=948@0.97 | Condition satisfied by the extracted value(s). |
| **I-AGE** — Effective age does not exceed actual age | 🟢 PASS | — | `effective_age`=40@0.97; `year_built`=1934@0.97; `effective_date`=2026-06-17@0.97 | Condition satisfied by the extracted value(s). |
| **I-YRBUILT** — Year built consistent with actual age | 🟢 PASS | — | `year_built`=1934@0.97; `effective_date`=2026-06-17@0.97; `effective_age`=40@0.97 | Condition satisfied by the extracted value(s). |
| **IM-2** — Bedroom / total-room count consistency | 🟢 PASS | — | `total_rooms`=5@0.97; `bedrooms`=3@0.97 | Condition satisfied by the extracted value(s). |
| **N-1** — Neighborhood characteristics marked | 🟢 PASS | — | `location`=Suburban@0.97 | Condition satisfied by the extracted value(s). |
| **N-1** — Neighborhood characteristics marked | 🟢 PASS | — | `built_up`=Over75Percent@0.97 | Condition satisfied by the extracted value(s). |
| **N-1** — Neighborhood characteristics marked | 🟢 PASS | — | `growth_rate`=Stable@0.97 | Condition satisfied by the extracted value(s). |
| **N-2** — Housing trends marked and consistent | 🟢 PASS | — | `property_values`=Stable@0.97 | Condition satisfied by the extracted value(s). |
| **N-2** — Housing trends marked and consistent | 🟢 PASS | — | `demand_supply`=InBalance@0.97 | Condition satisfied by the extracted value(s). |
| **N-2** — Housing trends marked and consistent | 🟢 PASS | — | `marketing_time`=UnderThreeMonths@0.97 | Condition satisfied by the extracted value(s). |
| **N-3** — Price/age ranges valid | 🟢 PASS | — | `price_low`=422@0.97; `price_high`=985@0.97 | Condition satisfied by the extracted value(s). |
| **N-3** — Price/age ranges valid | 🟢 PASS | — | `age_low`=0@0.97; `age_high`=135@0.97 | Condition satisfied by the extracted value(s). |
| **N-3** — Price/age ranges valid | 🟢 PASS | — | `appraised_value`=650000@0.97; `predominant_price`=780@0.97 | Condition satisfied by the extracted value(s). |
| **N-4** — Present land use sums to 100% | 🟢 PASS | — | `land_use_one_unit`=45@0.97; `land_use_2_4_unit`=5@0.97; `land_use_multi_family`=10@0.97; `land_use_commercial`=15@0.97; `land_use_other`=25@0.97 | Condition satisfied by the extracted value(s). |
| **N-4** — Present land use sums to 100% | 🟢 PASS | — | `land_use_other`=25@0.97 | Condition satisfied by the extracted value(s). |
| **N-5** — All four boundaries delineated | 🟢 PASS | — | `neighborhood_boundaries`=Subject is bounded on the North by Malaihi Road,…@0.97 | Condition satisfied by the extracted value(s). |
| **N-6** — Neighborhood description specific | 🟢 PASS | — | `neighborhood_description`=. The subject property is located in central Mau…@0.97 | Condition satisfied by the extracted value(s). |
| **N-7** — Market conditions completed | 🟢 PASS | — | `market_conditions_commentary`=. The neighborhood values appear to stablelized …@0.97 | Condition satisfied by the extracted value(s). |
| **CA-ARITH** — Cost approach arithmetic cross-check | 🟢 PASS | — | `site_value`=450000@0.97; `total_improvements_cost`=343230@0.97; `total_depreciation`=150714@0.97; `cost_approach_value`=652500@0.97 | Condition satisfied by the extracted value(s). |
| **R-2** — As-Is / Subject-To checked | 🟢 PASS | — | `appraisal_subject_to`=As Is@0.97 | Condition satisfied by the extracted value(s). |
| **R-2b** — Value equals contract price (bias advisory) | 🟢 PASS | — | `appraised_value`=650000@0.97; `contract_price`=650000@0.97 | Value equals contract price (noted for bias awareness; high-confidence extraction). |
| **R-ASSIGN-COND** — Assignment condition vs report language consistency | 🟢 PASS | — | `assignment_condition`=AsIs@0.97; `addendum_text`=-:NEIGHBORHOOD DESCRIPTION:- The subject propert…@0.97; `limiting_conditions_text`=∅ | Condition satisfied by the extracted value(s). |
| **R-EXPOSURE** — Exposure time stated as a specific period | 🟢 PASS | — | `addendum_text`=-:NEIGHBORHOOD DESCRIPTION:- The subject propert…@0.97; `final_reconciliation_comment`=∅ | Condition satisfied by the extracted value(s). |
| **R-MKTTIME** — Marketing time consistent with neighborhood data | 🟢 PASS | — | `marketing_time_typical`=UnderThreeMonths@0.97; `addendum_text`=-:NEIGHBORHOOD DESCRIPTION:- The subject propert…@0.97 | Condition satisfied by the extracted value(s). |
| **R-VALUE-RANGE** — Final value within range of developed approach values | 🟢 PASS | — | `appraised_value`=650000@0.97; `final_value_sca`=650000@0.97; `cost_approach_value`=652500@0.97 | Condition satisfied by the extracted value(s). |
| **RECON-T** — Reconciliation forbidden terms | 🟢 PASS | — | `final_reconciliation_comment`=∅ | Condition satisfied by the extracted value(s). |
| **VAL-1** — Final opinion of value extraction integrity | 🟢 PASS | — | `appraised_value`=650000@0.97; `contract_price`=650000@0.97 | Condition satisfied by the extracted value(s). |
| **CG-CONC-DIR** — Concession adjustment wrong direction | 🟢 PASS | — | `comp_5_sale_price`=730000@0.97; `comp_5_concessions`=Listing@0.97; `comp_5_financing_adj`=0@0.97 | Condition satisfied by the extracted value(s). |
| **CG-CONC-DIR** — Concession adjustment wrong direction | 🟢 PASS | — | `comp_6_sale_price`=800000@0.97; `comp_6_concessions`=Listing@0.97; `comp_6_financing_adj`=0@0.97 | Condition satisfied by the extracted value(s). |
| **CG-COND-CONSIST** — Condition adjustment consistency across comps | 🟢 PASS | — | `comp_1_condition_adj`=∅; `comp_2_condition_adj`=25000@0.97; `comp_3_condition_adj`=50000@0.97 | Condition satisfied by the extracted value(s). |
| **CG-DIST** — Comp distance threshold by area type | 🟢 PASS | — | `comp_1_proximity`=0.13 miles NE@0.97; `comp_2_proximity`=1.24 miles SW@0.97; `comp_3_proximity`=1.24 miles SW@0.97 | Condition satisfied by the extracted value(s). |
| **CG-GLA-BRACKET** — Subject GLA bracketed by comp GLAs | 🟢 PASS | — | `subject_grid_gla`=948@0.97; `gla`=948@0.97; `comp_1_gla`=1080@0.97; `comp_2_gla`=964@0.97; `comp_3_gla`=904@0.97 | Condition satisfied by the extracted value(s). |
| **CG-NET-BIAS** — Net adjustment directional bias | 🟢 PASS | — | `comp_1_net_adjustment`=11200@0.97; `comp_2_net_adjustment`=25000@0.97; `comp_3_net_adjustment`=55000@0.97 | Condition satisfied by the extracted value(s). |
| **CG-PRIOR-SALE** — Comp prior sale rapid appreciation flag | 🟢 PASS | — | `comp_1_prior_sale_date`=∅; `comp_2_prior_sale_date`=∅; `comp_3_prior_sale_date`=∅ | No comparable prior sales within the look-back window with material price changes. |
| **SCA-11** — Comp site size has unit | 🟢 PASS | — | `comp_1_site_size`=3877 sf@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-11** — Comp site size has unit | 🟢 PASS | — | `comp_2_site_size`=4352 sf@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-11** — Comp site size has unit | 🟢 PASS | — | `comp_3_site_size`=4352 sf@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-11** — Comp site size has unit | 🟢 PASS | — | `comp_4_site_size`=4853 sf@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-11** — Comp site size has unit | 🟢 PASS | — | `comp_5_site_size`=4143 sf@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-11** — Comp site size has unit | 🟢 PASS | — | `comp_6_site_size`=4709 sf@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-12** — Comp view UAD format | 🟢 PASS | — | `comp_1_view`=N;Mtn;@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-12** — Comp view UAD format | 🟢 PASS | — | `comp_2_view`=N;Mtn;@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-12** — Comp view UAD format | 🟢 PASS | — | `comp_3_view`=N;Mtn;@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-12** — Comp view UAD format | 🟢 PASS | — | `comp_4_view`=N;Mtn;@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-12** — Comp view UAD format | 🟢 PASS | — | `comp_5_view`=N;Mtn;@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-12** — Comp view UAD format | 🟢 PASS | — | `comp_6_view`=N;Mtn;@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-13** — Comp design present | 🟢 PASS | — | `comp_1_design`=DT1;Plantation@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-13** — Comp design present | 🟢 PASS | — | `comp_2_design`=DT1;Plantation@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-13** — Comp design present | 🟢 PASS | — | `comp_3_design`=DT1;Plantation@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-13** — Comp design present | 🟢 PASS | — | `comp_4_design`=DT1;Plantation@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-13** — Comp design present | 🟢 PASS | — | `comp_5_design`=DT1;Plantation@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-13** — Comp design present | 🟢 PASS | — | `comp_6_design`=DT1;Plantation@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-14** — Comp quality UAD rating + zero-adj | 🟢 PASS | — | `comp_1_quality_rating`=Q4@0.97; `quality_rating`=∅; `comp_1_quality_rating_adjustment`=∅ | Condition satisfied by the extracted value(s). |
| **SCA-14** — Comp quality UAD rating + zero-adj | 🟢 PASS | — | `comp_2_quality_rating`=Q4@0.97; `quality_rating`=∅; `comp_2_quality_rating_adjustment`=∅ | Condition satisfied by the extracted value(s). |
| **SCA-14** — Comp quality UAD rating + zero-adj | 🟢 PASS | — | `comp_3_quality_rating`=Q4@0.97; `quality_rating`=∅; `comp_3_quality_rating_adjustment`=∅ | Condition satisfied by the extracted value(s). |
| **SCA-14** — Comp quality UAD rating + zero-adj | 🟢 PASS | — | `comp_4_quality_rating`=Q4@0.97; `quality_rating`=∅; `comp_4_quality_rating_adjustment`=∅ | Condition satisfied by the extracted value(s). |
| **SCA-14** — Comp quality UAD rating + zero-adj | 🟢 PASS | — | `comp_5_quality_rating`=Q4@0.97; `quality_rating`=∅; `comp_5_quality_rating_adjustment`=∅ | Condition satisfied by the extracted value(s). |
| **SCA-14** — Comp quality UAD rating + zero-adj | 🟢 PASS | — | `comp_6_quality_rating`=Q4@0.97; `quality_rating`=∅; `comp_6_quality_rating_adjustment`=∅ | Condition satisfied by the extracted value(s). |
| **SCA-15** — Subject actual age vs year built | 🟢 PASS | — | `subject_grid_actual_age`=∅; `year_built`=1934@0.97 | Year built (1934) implies age of 92 years — consistent with effective date. |
| **SCA-16** — Comp condition UAD rating + zero-adj | 🟢 PASS | — | `comp_1_condition_rating`=C3@0.97; `condition_rating`=∅; `comp_1_condition_rating_adjustment`=∅ | Condition satisfied by the extracted value(s). |
| **SCA-16** — Comp condition UAD rating + zero-adj | 🟢 PASS | — | `comp_2_condition_rating`=C4@0.97; `condition_rating`=∅; `comp_2_condition_rating_adjustment`=∅ | Condition satisfied by the extracted value(s). |
| **SCA-16** — Comp condition UAD rating + zero-adj | 🟢 PASS | — | `comp_3_condition_rating`=C5@0.97; `condition_rating`=∅; `comp_3_condition_rating_adjustment`=∅ | Condition satisfied by the extracted value(s). |
| **SCA-16** — Comp condition UAD rating + zero-adj | 🟢 PASS | — | `comp_4_condition_rating`=C3@0.97; `condition_rating`=∅; `comp_4_condition_rating_adjustment`=∅ | Condition satisfied by the extracted value(s). |
| **SCA-16** — Comp condition UAD rating + zero-adj | 🟢 PASS | — | `comp_5_condition_rating`=C4@0.97; `condition_rating`=∅; `comp_5_condition_rating_adjustment`=∅ | Condition satisfied by the extracted value(s). |
| **SCA-16** — Comp condition UAD rating + zero-adj | 🟢 PASS | — | `comp_6_condition_rating`=C3@0.97; `condition_rating`=∅; `comp_6_condition_rating_adjustment`=∅ | Condition satisfied by the extracted value(s). |
| **SCA-17** — Above-grade GLA matches grid, improvements & sketch | 🟢 PASS | — | `comp_1_gla`=1080@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-17** — Above-grade GLA matches grid, improvements & sketch | 🟢 PASS | — | `comp_2_gla`=964@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-17** — Above-grade GLA matches grid, improvements & sketch | 🟢 PASS | — | `comp_3_gla`=904@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-17** — Above-grade GLA matches grid, improvements & sketch | 🟢 PASS | — | `comp_4_gla`=954@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-17** — Above-grade GLA matches grid, improvements & sketch | 🟢 PASS | — | `comp_5_gla`=982@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-17** — Above-grade GLA matches grid, improvements & sketch | 🟢 PASS | — | `comp_6_gla`=1070@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-2** — Minimum comparable sales | 🟢 PASS | — | `comp_1_sale_price`=655000@0.97; `comp_2_sale_price`=665000@0.97; `comp_3_sale_price`=550000@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-21** — Comp garage/carport present | 🟢 PASS | — | `comp_1_garage_carport`=None@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-21** — Comp garage/carport present | 🟢 PASS | — | `comp_2_garage_carport`=None@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-21** — Comp garage/carport present | 🟢 PASS | — | `comp_3_garage_carport`=1cp@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-21** — Comp garage/carport present | 🟢 PASS | — | `comp_4_garage_carport`=2cp@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-21** — Comp garage/carport present | 🟢 PASS | — | `comp_5_garage_carport`=None@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-21** — Comp garage/carport present | 🟢 PASS | — | `comp_6_garage_carport`=1ga@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-23** — Listing comp adjustment | 🟢 PASS | — | `comp_5_sale_date`=Active@0.97; `comp_5_net_adjustment`=35000@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-23** — Listing comp adjustment | 🟢 PASS | — | `comp_6_sale_date`=Active@0.97; `comp_6_net_adjustment`=26100@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-26** — Subject GLA bracketed by comps | 🟢 PASS | — | `gla`=948@0.97; `comp_1_gla`=1080@0.97; `comp_2_gla`=964@0.97; `comp_3_gla`=904@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-3** — Comp address present | 🟢 PASS | — | `comp_1_address`=223 Momi Place C, Wailuku, HI@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-3** — Comp address present | 🟢 PASS | — | `comp_2_address`=1972 Kalawi Place, Wailuku, HI@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-3** — Comp address present | 🟢 PASS | — | `comp_3_address`=1982 Kalawi Place, Wailuku, HI@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-3** — Comp address present | 🟢 PASS | — | `comp_4_address`=249 Kanoa Street, Wailuku, HI@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-3** — Comp address present | 🟢 PASS | — | `comp_5_address`=45 Puahau Place, Wailuku, HI@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-3** — Comp address present | 🟢 PASS | — | `comp_6_address`=1855 Mill Street, Wailuku, HI@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-4** — Comp proximity present | 🟢 PASS | — | `comp_1_proximity`=0.13 miles NE@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-4** — Comp proximity present | 🟢 PASS | — | `comp_2_proximity`=1.24 miles SW@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-4** — Comp proximity present | 🟢 PASS | — | `comp_3_proximity`=1.24 miles SW@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-4** — Comp proximity present | 🟢 PASS | — | `comp_4_proximity`=1.09 miles SW@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-4** — Comp proximity present | 🟢 PASS | — | `comp_5_proximity`=1.24 miles SW@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-4** — Comp proximity present | 🟢 PASS | — | `comp_6_proximity`=0.78 miles SW@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-5** — Comp data source present | 🟢 PASS | — | `comp_1_data_source`=RAM-MLS #407892;DOM 148@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-5** — Comp data source present | 🟢 PASS | — | `comp_2_data_source`=RAM-MLS #407933;DOM 61@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-5** — Comp data source present | 🟢 PASS | — | `comp_3_data_source`=RAM-MLS #407136;DOM 60@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-5** — Comp data source present | 🟢 PASS | — | `comp_4_data_source`=RAM-MLS #408744;DOM 34@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-5** — Comp data source present | 🟢 PASS | — | `comp_5_data_source`=RAM-MLS #408629;DOM 137@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-5** — Comp data source present | 🟢 PASS | — | `comp_6_data_source`=RAM-MLS #409946;DOM 2@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-6** — Comp verification source specific | 🟢 PASS | — | `comp_1_verification_source`=RealQuest #A9608000408@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-6** — Comp verification source specific | 🟢 PASS | — | `comp_2_verification_source`=RealQuest #A9525000035@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-6** — Comp verification source specific | 🟢 PASS | — | `comp_3_verification_source`=RealQuest #A9449000261@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-6** — Comp verification source specific | 🟢 PASS | — | `comp_4_verification_source`=RealQuest #A9574000521@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-6** — Comp verification source specific | 🟢 PASS | — | `comp_5_verification_source`=RealQuest@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-6** — Comp verification source specific | 🟢 PASS | — | `comp_6_verification_source`=RealQuest@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-8** — Comp date of sale sequencing | 🟢 PASS | — | `comp_1_sale_date`=s04/26;c02/26@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-8** — Comp date of sale sequencing | 🟢 PASS | — | `comp_2_sale_date`=s01/26;c12/25@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-8** — Comp date of sale sequencing | 🟢 PASS | — | `comp_3_sale_date`=s11/25;c10/25@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-8** — Comp date of sale sequencing | 🟢 PASS | — | `comp_4_sale_date`=s03/26;c02/26@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-9** — Comp location UAD format | 🟢 PASS | — | `comp_1_location_rating`=A;Res;@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-9** — Comp location UAD format | 🟢 PASS | — | `comp_2_location_rating`=A;Res;@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-9** — Comp location UAD format | 🟢 PASS | — | `comp_3_location_rating`=A;Res;@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-9** — Comp location UAD format | 🟢 PASS | — | `comp_4_location_rating`=N;Res;@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-9** — Comp location UAD format | 🟢 PASS | — | `comp_5_location_rating`=A;Res;@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-9** — Comp location UAD format | 🟢 PASS | — | `comp_6_location_rating`=A;Res;@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-BR** — Value bracketed by adjusted prices | 🟢 PASS | — | `appraised_value`=650000@0.97; `comp_1_adjusted_sale_price`=643800@0.97; `comp_2_adjusted_sale_price`=690000@0.97; `comp_3_adjusted_sale_price`=605000@0.97; `comp_4_adjusted_sale_price`=673500@0.97; `comp_5_adjusted_sale_price`=765000@0.97; `comp_6_adjusted_sale_price`=773900@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-BR2** — Min comps with adjusted value at/above final opinion (lender overlay) | 🟢 PASS | — | `appraised_value`=650000@0.97; `comp_1_adjusted_sale_price`=643800@0.97; `comp_2_adjusted_sale_price`=690000@0.97; `comp_3_adjusted_sale_price`=605000@0.97; `comp_4_adjusted_sale_price`=673500@0.97; `comp_5_adjusted_sale_price`=765000@0.97; `comp_6_adjusted_sale_price`=773900@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-DC** — Comp sale within date currency window | 🟢 PASS | — | `comp_1_sale_date`=s04/26;c02/26@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-DC** — Comp sale within date currency window | 🟢 PASS | — | `comp_2_sale_date`=s01/26;c12/25@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-DC** — Comp sale within date currency window | 🟢 PASS | — | `comp_3_sale_date`=s11/25;c10/25@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-DC** — Comp sale within date currency window | 🟢 PASS | — | `comp_4_sale_date`=s03/26;c02/26@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-FLIP** — Comp rapid resale flag | 🟢 PASS | — | `comp_1_prior_sale_date`=∅ | Condition satisfied by the extracted value(s). |
| **SCA-GROSS** — Gross adjustment per comp within 25% | 🟢 PASS | — | `comp_1_gross_adj_pct`=4.8@0.97; `comp_2_gross_adj_pct`=6.8@0.97; `comp_3_gross_adj_pct`=10.0@0.97; `comp_4_gross_adj_pct`=5.8@0.97; `comp_5_gross_adj_pct`=4.8@0.97; `comp_6_gross_adj_pct`=3.3@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-NET** — Net adjustment within 15% | 🟢 PASS | — | `comp_1_net_adjustment`=11200@0.97; `comp_2_net_adjustment`=25000@0.97; `comp_3_net_adjustment`=55000@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-PR** — Comp sale price bracket vs subject value | 🟢 PASS | — | `comp_1_sale_price`=655000@0.97; `appraised_value`=650000@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-PR** — Comp sale price bracket vs subject value | 🟢 PASS | — | `comp_2_sale_price`=665000@0.97; `appraised_value`=650000@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-PR** — Comp sale price bracket vs subject value | 🟢 PASS | — | `comp_3_sale_price`=550000@0.97; `appraised_value`=650000@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-PR** — Comp sale price bracket vs subject value | 🟢 PASS | — | `comp_4_sale_price`=715000@0.97; `appraised_value`=650000@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-PR** — Comp sale price bracket vs subject value | 🟢 PASS | — | `comp_5_sale_price`=730000@0.97; `appraised_value`=650000@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-PR** — Comp sale price bracket vs subject value | 🟢 PASS | — | `comp_6_sale_price`=800000@0.97; `appraised_value`=650000@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-PSH** — Subject prior sale analyzed | 🟢 PASS | — | `subject_grid_prior_sale_date`=∅; `effective_date`=2026-06-17@0.97 | Condition satisfied by the extracted value(s). |
| **SIG-1** — Appraiser signed / name present | 🟢 PASS | — | `appraiser_name`=Igor Medo@0.97; `date_of_signature`=∅ | Condition satisfied by the extracted value(s). |
| **SIG-3** — Appraiser licensed in property state | 🟢 PASS | — | `appraiser_license_state`=HI@0.97; `state`=HI@0.97 | Condition satisfied by the extracted value(s). |
| **ST-GEO-COMP** — Appraiser geographic competency | 🟢 PASS | — | `appraiser_license_state`=HI@0.97; `state`=HI@0.97 | Condition satisfied by the extracted value(s). |
| **ST-1** — Site dimensions provided | 🟢 PASS | — | `site_dimensions`=75' x 47'@0.97 | Condition satisfied by the extracted value(s). |
| **ST-2** — Site area has correct unit | 🟢 PASS | — | `site_area`=3562 sf@0.97; `site_area_unit`=∅ | Condition satisfied by the extracted value(s). |
| **ST-3** — Site shape provided | 🟢 PASS | — | `site_shape`=Rectangular@0.97 | Condition satisfied by the extracted value(s). |
| **ST-4** — View UAD compliant and consistent | 🟢 PASS | — | `site_view`=N;Mtn;@0.97 | Condition satisfied by the extracted value(s). |
| **ST-5** — Zoning compliance | 🟢 PASS | — | `zoning_compliance`=Legal@0.97 | Condition satisfied by the extracted value(s). |
| **ST-6** — Highest & best use is Yes | 🟢 PASS | — | `highest_and_best_use`=Yes@0.97 | Condition satisfied by the extracted value(s). |
| **ST-7** — Utilities marked; private systems addressed | 🟢 PASS | — | `utilities_electricity`=Public@0.97; `utilities_gas`=None@0.97 | Condition satisfied by the extracted value(s). |
| **ST-9** — Utilities/off-site typical for market | 🟢 PASS | — | `utilities_water`=Public@0.97; `utilities_sewer`=Public@0.97 | Condition satisfied by the extracted value(s). |
| **ST-HBU** — Highest and best use stated and consistent | 🟢 PASS | — | `highest_and_best_use`=Yes@0.97; `highest_best_use_indicator`=∅; `highest_best_use_description`=∅ | Condition satisfied by the extracted value(s). |
| **ST-RIGHTS** — Leasehold property rights disclosure | 🟢 PASS | — | `property_rights`=FeeSimple@0.97; `addendum_text`=-:NEIGHBORHOOD DESCRIPTION:- The subject propert…@0.97 | Condition satisfied by the extracted value(s). |
| **I-HOA-PUD** — HOA/PUD consistency | 🟢 PASS | — | `hoa_dues`=∅; `is_pud`=∅ | Condition satisfied by the extracted value(s). |
| **S-11** — Property rights appraised present | 🟢 PASS | — | `property_rights`=FeeSimple@0.97 | Condition satisfied by the extracted value(s). |
| **S-4b** — APN present and plausible | 🟢 PASS | — | `assessors_parcel_number`=2-3-4-024-026-0000@0.97 | Condition satisfied by the extracted value(s). |
| **S-5** — Neighborhood name valid | 🟢 PASS | — | `neighborhood_name`=Wailuku@0.97 | Condition satisfied by the extracted value(s). |
| **S-6** — Census tract format | 🟢 PASS | — | `census_tract`=0309.02@0.97 | Condition satisfied by the extracted value(s). |
| **S-7** — Occupancy status marked | 🟢 PASS | — | `occupant_status`=Vacant@0.97 | Condition satisfied by the extracted value(s). |
| **S-7** — Occupancy status marked | 🟢 PASS | — | `occupant_status`=Vacant@0.97 | Condition satisfied by the extracted value(s). |
| **S-9** — HOA dues imply PUD marked | 🟢 PASS | — | `hoa_dues`=∅; `is_pud_checked`=∅ | Condition satisfied by the extracted value(s). |
| **ST-FORM-MATCH** — Form type matches property type | 🟢 PASS | — | `design_style`=Plantation@0.97 | Condition satisfied by the extracted value(s). |
| **ST-INTENDED** — Intended use and intended user stated | 🟢 PASS | — | `addendum_text`=-:NEIGHBORHOOD DESCRIPTION:- The subject propert…@0.97 | Condition satisfied by the extracted value(s). |
| **ST-SCOPE** — Scope of work stated | 🟢 PASS | — | `addendum_text`=-:NEIGHBORHOOD DESCRIPTION:- The subject propert…@0.97 | Condition satisfied by the extracted value(s). |
| **ADD-2** — Comparable selection commentary explains why | ⚪ N/A | — | — | No substantive sales-comparison narrative extracted. |
| **ADD-4** — 1004MC required for FHA/USDA | ⚪ N/A | — | — | Not applicable to this loan/transaction/form type. |
| **ADD-8** — 1004MC condo project section complete | ⚪ N/A | — | — | Not applicable to this loan/transaction/form type. |
| **C-5** — Personal property addressed | ⚪ N/A | — | — | Not applicable to this loan/transaction/form type. |
| **C-BUYER-MATCH** — Buyer names match borrower(s) on order | ⚪ N/A | — | — | Not applicable to this loan/transaction/form type. |
| **C-EXEC** — Contract fully executed by all parties | ⚪ N/A | — | `contract_analysis_comment`=∅ | No contract analysis commentary extracted; C-1 governs. |
| **C-PKG-EXEC** — Contract fully executed (manual verification) | ⚪ N/A | — | — | Not applicable to this loan/transaction/form type. |
| **ORD-ASSIGN-MATCH** — Assignment type in engagement letter matches appraisal report | ⚪ N/A | — | — | Not applicable to this loan/transaction/form type. |
| **ORD-EXEC-STOP** — Unsigned contract blocked by engagement letter policy | ⚪ N/A | — | — | Not applicable to this loan/transaction/form type. |
| **CA-2** — Remaining economic life >= 30 (FHA/VA) | ⚪ N/A | — | — | Not applicable to this loan/transaction/form type. |
| **FHA-1** — FHA Minimum Property Requirements confirmed | ⚪ N/A | — | — | Not applicable to this loan/transaction/form type. |
| **FHA-10** — FHA remaining economic life >= 30 | ⚪ N/A | — | — | Not applicable to this loan/transaction/form type. |
| **FHA-12** — FHA well/septic compliance | ⚪ N/A | — | — | Not applicable to this loan/transaction/form type. |
| **FHA-13** — FHA appliances present/operational | ⚪ N/A | — | — | Not applicable to this loan/transaction/form type. |
| **FHA-2** — FHA case number format + match | ⚪ N/A | — | — | Not applicable to this loan/transaction/form type. |
| **FHA-3** — FHA intended use/user statements | ⚪ N/A | — | — | Not applicable to this loan/transaction/form type. |
| **FHA-4** — FHA/HUD certification statement present | ⚪ N/A | — | — | Not applicable to this loan/transaction/form type. |
| **FHA-5** — FHA primary comps within 12 months | ⚪ N/A | — | — | Not applicable to this loan/transaction/form type. |
| **FHA-6** — FHA repairs reported subject-to | ⚪ N/A | — | — | Not applicable to this loan/transaction/form type. |
| **FHA-7** — FHA space heater not primary heat | ⚪ N/A | — | — | Not applicable to this loan/transaction/form type. |
| **FHA-9** — FHA four-side photos | ⚪ N/A | — | — | Not applicable to this loan/transaction/form type. |
| **G-1** — Loan-type consistency (engagement vs appraisal) | ⚪ N/A | — | `loan_type`=∅; `fha_case_number`=∅ | Engagement letter / order form not available. |
| **G-C56** — C5/C6 condition triggers AMC stop | ⚪ N/A | — | — | Not applicable to this loan/transaction/form type. |
| **G-LAVA** — Hawaiian lava zone triggers AMC stop | ⚪ N/A | — | — | Not applicable to this loan/transaction/form type. |
| **G-MFG** — Pre-1976 manufactured home triggers AMC stop | ⚪ N/A | — | — | Not applicable to this loan/transaction/form type. |
| **ORD-CONFLICT** — Engagement letter and XML disagree on order-level facts | ⚪ N/A | — | — | Not applicable to this loan/transaction/form type. |
| **IA-1** — Income approach rent matches rent schedule | ⚪ N/A | — | — | Income approach / rent schedule not developed. |
| **MF-1** — Multi-family requires income approach | ⚪ N/A | — | — | Not applicable to this loan/transaction/form type. |
| **R-INCOME-REQ** — Income approach developed when required | ⚪ N/A | — | `income_approach_value`=0@0.97; `occupancy_type`=Vacant@0.97 | Income approach not required for this occupancy type. |
| **CG-NONARMS** — Non-arms-length comp without commentary | ⚪ N/A | — | — | No non-arms-length distress indicators found in comparables. |
| **SCA-25** — New construction competing comp | ⚪ N/A | — | — | subject is not new construction |
| **SCA-PSH-Q** — Subject sale history analysis is substantive | ⚪ N/A | — | — | No prior sale/transfer within the look-back window; quality check not applicable. |
| **ORD-ENG-DATE** — Engagement letter predates appraisal report | ⚪ N/A | — | — | Not applicable to this loan/transaction/form type. |
| **SIG-2** — Appraiser name matches engagement | ⚪ N/A | — | — | Not applicable to this loan/transaction/form type. |
| **SIG-SUP** — Supervisory appraiser section complete | ⚪ N/A | — | — | Not applicable to this loan/transaction/form type. |
| **SIG-TRAINEE** — Trainee appraiser requires supervisory cosign | ⚪ N/A | — | `appraiser_license_type`=Certificate@0.97; `supervisory_appraiser_name`=∅; `supervisory_appraiser_cert_number`=∅ | Rule does not apply to this loan/form/transaction type. |
| **ST-PRIOR-SVC** — Prior services disclosure | ⚪ N/A | — | `prior_services_indicator`=∅; `prior_services_description`=∅; `addendum_text`=-:NEIGHBORHOOD DESCRIPTION:- The subject propert…@0.97 | Rule does not apply to this loan/form/transaction type. |
| **TL-ENG** — Engagement letter date precedes report signature date | ⚪ N/A | — | — | Not applicable to this loan/transaction/form type. |
| **ST-1B** — Site area magnitude plausibility (multi-signal) | ⚪ N/A | — | `site_area`=3562 sf@0.97; `site_area_unit`=∅ | Rule does not apply to this loan/form/transaction type. |
| **ST-FLOOD-CMT** — Flood zone present — marketability commentary required | ⚪ N/A | — | — | Not applicable to this loan/transaction/form type. |
| **ST-ZONE-NC** — Zoning non-conformance commentary | ⚪ N/A | — | `zoning_compliance`=Legal@0.97; `addendum_text`=-:NEIGHBORHOOD DESCRIPTION:- The subject propert…@0.97 | Rule does not apply to this loan/form/transaction type. |
| **ORD-COBORROWER** — Co-borrower from order appears in appraisal borrower field | ⚪ N/A | — | — | Not applicable to this loan/transaction/form type. |
| **ORD-FORM-MATCH** — Form type in report matches form type ordered | ⚪ N/A | — | — | Not applicable to this loan/transaction/form type. |
| **ORD-INSP-SCOPE** — Ordered inspection type matches report scope of work | ⚪ N/A | — | — | Not applicable to this loan/transaction/form type. |
| **S-1** — Property address matches order form | ⚪ N/A | — | `property_address`=220 Hala Place@0.97 | Engagement letter / order form not available. |
| **S-1** — Property address matches order form | ⚪ N/A | — | `city`=Wailuku@0.97 | Engagement letter / order form not available. |
| **S-1** — Property address matches order form | ⚪ N/A | — | `zip_code`=96793@0.97 | Engagement letter / order form not available. |
| **S-10a** — Lender name matches order form | ⚪ N/A | — | `lender_name`=Guild Mortgage Company@0.97 | Engagement letter / order form not available. |
| **S-10b** — Lender address matches order form | ⚪ N/A | — | — | Engagement letter / order form not available. |
| **S-2** — Borrower matches order form | ⚪ N/A | — | — | Engagement letter / order form not available. |
| **USDA-1** — USDA cost approach required | ⚪ N/A | — | — | Not applicable to this loan/transaction/form type. |


---

## dir 5 — 17354 SW 287th St.xml

| Rule | Status | Bucket | Extracted (what the rule read) | How it was judged |
|------|--------|--------|-------------------------------|-------------------|
| **SUBJECT-HOLD** — subject | 🔴 FAIL | 🔴 hard-fail | — | 5 failures in the subject section indicate systematic problems (not isolated errors); the section is escalated for a full manual review. |
| **C-3** — Owner-of-record data source present | 🔴 FAIL | 🔴 hard-fail | `is_seller_owner_of_record`=∅; `owner_record_data_source`=∅ | Please provide a data source for the question about whether the seller is the owner of public record (in the contract section). |
| **G-0** — Engagement letter / order form present and extracted | 🔴 FAIL | 🟠 extraction-gap | `loan_type`=∅ | The engagement letter / order form was not extracted. All lender-overlay rules (comp count minimum, site value requirement, declining-market clause, A… |
| **S-12** — Prior-listing data source present | 🔴 FAIL | 🔴 hard-fail | `offered_for_sale_12mo`=∅; `data_source`=∅ | The checkbox about prior sale or listing activity in the past 12 months is missing a data source. Please provide the source used to answer this questi… |
| **S-3** — Owner of public record present | 🔴 FAIL | 🔴 hard-fail | `owner_of_public_record`=∅; `legal_description`=∅; `real_estate_taxes`=∅; `special_assessments`=∅ | The 'Owner of Public Record' field is blank. Please complete it. |
| **ADD-9** — USPAP addendum complete | 🟡 VERIFY | 🟠 extraction-gap | — | The USPAP addendum fields (report type, reasonable exposure time, prior services) could not be extracted; manual review required. |
| **C-1** — Contract analyzed (purchase) / section blank (refinance) | 🟡 VERIFY | 🟡 manual-verify | `did_analyze_contract`=∅ | The contract analysis is missing. Please complete the contract analysis or explain why it was not done. |
| **C-1** — Contract analyzed (purchase) / section blank (refinance) | 🟡 VERIFY | 🟡 manual-verify | `sale_type`=∅; `contract_analysis_comment`=∅ | The type of sale is not identified. Please note whether this is an Arm's-Length sale, REO, Short Sale, Court-Ordered Sale, or Non-Arm's-Length in the … |
| **C-4** — Concessions consistent and match purchase agreement | 🟡 VERIFY | 🟡 manual-verify | `has_financial_assistance`=∅; `financial_assistance_amount`=∅ | The seller concession checkbox (financial assistance) is not answered. Please mark Yes or No. |
| **C-4** — Concessions consistent and match purchase agreement | 🟡 VERIFY | 🟡 manual-verify | `financial_assistance_amount`=∅; `financial_assistance_description`=∅ | Seller-concessions cross-check. The appraisal report shows — Seller concessions / financial assistance not stated in the report; Concession descriptio… |
| **C-ANALYZE** — Contract analysis indicator consistency | 🟡 VERIFY | 🟡 manual-verify | `contract_analyzed`=Y@0.97 | The report says the contract was reviewed, but no purchase contract was included in the file. Please provide the contract or update the contract secti… |
| **CA-1** — Opinion of site value present | 🟡 VERIFY | 🟡 manual-verify | `site_value_estimate`=∅ | The cost approach is missing an opinion of site value. Please provide one. |
| **I-11** — Conforms to neighborhood | 🟡 VERIFY | 🟠 extraction-gap | `conforms_to_neighborhood`=∅ | Conformity to the neighborhood could not be read; please verify the improvements conform. |
| **I-34** — Materials/condition described | 🟡 VERIFY | 🟡 manual-verify | `exterior_walls`=∅; `roof_surface`=∅; `heating`=∅; `floor_material`=∅; `walls_material`=∅; `trim_finish_material`=∅ | The following materials/condition fields are missing in the improvements section: Exterior Walls, Roof Surface, Heating, Floors, Walls, Trim/Finish. P… |
| **I-5** — Heating and cooling described | 🟡 VERIFY | 🟡 manual-verify | `heating`=∅; `cooling`=∅ | The following heating/cooling fields are not described in the improvements section: Heating, Cooling. Please complete. |
| **I-6** — Appliances reported | 🟡 VERIFY | 🟡 manual-verify | `appliance_refrigerator`=∅; `appliance_range_oven`=∅; `appliance_disposal`=∅; `appliance_dishwasher`=∅; `appliance_microwave`=∅; `appliance_washer_dryer`=∅ | No kitchen appliances are listed in the improvements section. Please note which appliances are present. |
| **I-8** — Additional features described | 🟡 VERIFY | 🟡 manual-verify | `fireplace_count`=∅; `porch_patio_deck`=∅; `additional_features`=∅ | Please confirm any additional features (fireplace, porch/patio/deck, pool, etc.) are described in the improvements section, or state 'None'. |
| **I-9** — Condition rating UAD and consistent | 🟡 VERIFY | 🟠 extraction-gap | `condition_rating`=∅ | Condition could not be extracted from the document; manual review required. |
| **I-Q** — Quality rating UAD format | 🟡 VERIFY | 🟠 extraction-gap | `quality_rating`=∅ | Quality could not be extracted from the document; manual review required. |
| **I-SMCO** — Smoke/CO detector code compliance noted | 🟡 VERIFY | 🟡 manual-verify | `sales_comparison_summary`=∅ | No mention of smoke or CO detectors was found in the report. The client requires a note confirming detectors meet local code — please add one to the r… |
| **N-6** — Neighborhood description specific | 🟡 VERIFY | 🟡 manual-verify | `neighborhood_description`=The subject's market area can be considered an e…@0.97 | The Neighborhood Description reads like a generic template. Please add specific details — like nearby streets, local landmarks, proximity to schools o… |
| **PH-1** — Subject front/rear/street photos | 🟡 VERIFY | 🟡 manual-verify | `photo_front`=∅; `photo_rear`=∅; `photo_street`=∅ | Required photos are missing: front, rear, street scene. At minimum, please include a front photo, a rear photo, and a street scene. |
| **PH-2** — Interior photos present | 🟡 VERIFY | 🟡 manual-verify | `photo_interior_rooms`=∅ | Interior photos are incomplete — missing: kitchen, living, bedroom, bathroom. Please include photos of the kitchen, living room, all bedrooms, and all… |
| **CA-ARITH** — Cost approach arithmetic cross-check | 🟡 VERIFY | 🟡 manual-verify | `site_value`=360000@0.97; `total_improvements_cost`=799496@0.97; `total_depreciation`=∅; `cost_approach_value`=1209496@0.97 | Cost approach arithmetic cannot be evaluated; the following field(s) could not be extracted: total_depreciation — manual review required. |
| **R-1** — SCA value matches market value | 🟡 VERIFY | 🟡 manual-verify | `indicated_value_sca`=∅; `appraised_value`=1200000@0.97 | The sales comparison value or final opinion of value could not be read. Please verify both numbers are present and agree. |
| **R-1b** — Reconciliation names the weighted approach | 🟡 VERIFY | 🟡 manual-verify | `final_reconciliation_comment`=∅ | The reconciliation must say which approach was relied on most (sales comparison, cost, or income) and briefly explain why. Please add that statement t… |
| **R-ASSIGN-COND** — Assignment condition vs report language consistency | 🟡 VERIFY | 🟡 manual-verify | `assignment_condition`=AsIs@0.97; `addendum_text`=∅; `limiting_conditions_text`=∅ | The assignment condition box (AsIs) doesn't match the language used in the report narrative. Please make sure the box and the written description agre… |
| **R-EXPOSURE** — Exposure time stated as a specific period | 🟡 VERIFY | 🟡 manual-verify | `addendum_text`=∅; `final_reconciliation_comment`=∅ | No specific exposure time period was found. Please add a statement like 'estimated exposure time of 3-6 months' in the reconciliation or addendum. |
| **R-MKTTIME** — Marketing time consistent with neighborhood data | 🟡 VERIFY | 🟡 manual-verify | `marketing_time_typical`=UnderThreeMonths@0.97; `addendum_text`=∅ | The marketing time stated in the report appears inconsistent with the market data for this area. Please make sure the estimated selling time matches w… |
| **CG-TIME-CONSIST** — Time/market adjustment rate consistency | 🟡 VERIFY | 🟠 extraction-gap | — | Fewer than 2 comps with measurable time adjustments; rate consistency check skipped — manual review required. |
| **SCA-10** — Comp property rights present + consistent | 🟡 VERIFY | 🟡 manual-verify | `comp_1_leasehold`=∅ | Please indicate the property rights (Fee Simple or Leasehold) for Comp 1 in the sales grid. |
| **SCA-10** — Comp property rights present + consistent | 🟡 VERIFY | 🟡 manual-verify | `comp_2_leasehold`=∅ | Please indicate the property rights (Fee Simple or Leasehold) for Comp 2 in the sales grid. |
| **SCA-10** — Comp property rights present + consistent | 🟡 VERIFY | 🟡 manual-verify | `comp_3_leasehold`=∅ | Please indicate the property rights (Fee Simple or Leasehold) for Comp 3 in the sales grid. |
| **SCA-10** — Comp property rights present + consistent | 🟡 VERIFY | 🟡 manual-verify | `comp_4_leasehold`=∅ | Please indicate the property rights (Fee Simple or Leasehold) for Comp 4 in the sales grid. |
| **SCA-10** — Comp property rights present + consistent | 🟡 VERIFY | 🟡 manual-verify | `comp_5_leasehold`=∅ | Please indicate the property rights (Fee Simple or Leasehold) for Comp 5 in the sales grid. |
| **SCA-10** — Comp property rights present + consistent | 🟡 VERIFY | 🟡 manual-verify | `comp_6_leasehold`=∅ | Please indicate the property rights (Fee Simple or Leasehold) for Comp 6 in the sales grid. |
| **SCA-16V** — Comp photo condition cross-check | 🟡 VERIFY | 🟠 extraction-gap | — | Please open the report and visually confirm that the front photo matches the subject property address. Automated photo review is not available for thi… |
| **SCA-17** — Above-grade GLA matches grid, improvements & sketch | 🟡 VERIFY | 🟡 manual-verify | `subject_grid_gla`=3365@0.97; `gla`=3365@0.97; `sketch_living_area`=∅ | The living area couldn't be confirmed across all sources (SCA grid 3365, improvements 3365, sketch n/a sf). Please verify the GLA in the sales grid ma… |
| **SCA-18** — Comp basement present | 🟡 VERIFY | 🟡 manual-verify | `comp_1_basement`=∅ | Basement and below-grade rooms are missing for Comp 1. Please fill this in (finished sq ft and room count, or 'None' if there is none). |
| **SCA-18** — Comp basement present | 🟡 VERIFY | 🟡 manual-verify | `comp_2_basement`=∅ | Basement and below-grade rooms are missing for Comp 2. Please fill this in (finished sq ft and room count, or 'None' if there is none). |
| **SCA-18** — Comp basement present | 🟡 VERIFY | 🟡 manual-verify | `comp_3_basement`=∅ | Basement and below-grade rooms are missing for Comp 3. Please fill this in (finished sq ft and room count, or 'None' if there is none). |
| **SCA-18** — Comp basement present | 🟡 VERIFY | 🟡 manual-verify | `comp_4_basement`=∅ | Basement and below-grade rooms are missing for Comp 4. Please fill this in (finished sq ft and room count, or 'None' if there is none). |
| **SCA-18** — Comp basement present | 🟡 VERIFY | 🟡 manual-verify | `comp_5_basement`=∅ | Basement and below-grade rooms are missing for Comp 5. Please fill this in (finished sq ft and room count, or 'None' if there is none). |
| **SCA-18** — Comp basement present | 🟡 VERIFY | 🟡 manual-verify | `comp_6_basement`=∅ | Basement and below-grade rooms are missing for Comp 6. Please fill this in (finished sq ft and room count, or 'None' if there is none). |
| **SCA-19** — Comp functional utility present | 🟡 VERIFY | 🟡 manual-verify | `comp_1_functional_utility`=∅ | Please add functional utility for Comp 1 in the sales grid. |
| **SCA-19** — Comp functional utility present | 🟡 VERIFY | 🟡 manual-verify | `comp_2_functional_utility`=∅ | Please add functional utility for Comp 2 in the sales grid. |
| **SCA-19** — Comp functional utility present | 🟡 VERIFY | 🟡 manual-verify | `comp_3_functional_utility`=∅ | Please add functional utility for Comp 3 in the sales grid. |
| **SCA-19** — Comp functional utility present | 🟡 VERIFY | 🟡 manual-verify | `comp_4_functional_utility`=∅ | Please add functional utility for Comp 4 in the sales grid. |
| **SCA-19** — Comp functional utility present | 🟡 VERIFY | 🟡 manual-verify | `comp_5_functional_utility`=∅ | Please add functional utility for Comp 5 in the sales grid. |
| **SCA-19** — Comp functional utility present | 🟡 VERIFY | 🟡 manual-verify | `comp_6_functional_utility`=∅ | Please add functional utility for Comp 6 in the sales grid. |
| **SCA-20** — Comp heating/cooling present | 🟡 VERIFY | 🟡 manual-verify | `comp_1_heating_cooling`=∅ | Please add the heating/cooling information for Comp 1 in the sales grid. |
| **SCA-20** — Comp heating/cooling present | 🟡 VERIFY | 🟡 manual-verify | `comp_2_heating_cooling`=∅ | Please add the heating/cooling information for Comp 2 in the sales grid. |
| **SCA-20** — Comp heating/cooling present | 🟡 VERIFY | 🟡 manual-verify | `comp_3_heating_cooling`=∅ | Please add the heating/cooling information for Comp 3 in the sales grid. |
| **SCA-20** — Comp heating/cooling present | 🟡 VERIFY | 🟡 manual-verify | `comp_4_heating_cooling`=∅ | Please add the heating/cooling information for Comp 4 in the sales grid. |
| **SCA-20** — Comp heating/cooling present | 🟡 VERIFY | 🟡 manual-verify | `comp_5_heating_cooling`=∅ | Please add the heating/cooling information for Comp 5 in the sales grid. |
| **SCA-20** — Comp heating/cooling present | 🟡 VERIFY | 🟡 manual-verify | `comp_6_heating_cooling`=∅ | Please add the heating/cooling information for Comp 6 in the sales grid. |
| **SCA-22** — Comp porch/patio/deck present | 🟡 VERIFY | 🟡 manual-verify | `comp_1_porch_patio_deck`=∅ | Please add the porch, patio, or deck information for Comp 1 in the sales grid. |
| **SCA-22** — Comp porch/patio/deck present | 🟡 VERIFY | 🟡 manual-verify | `comp_2_porch_patio_deck`=∅ | Please add the porch, patio, or deck information for Comp 2 in the sales grid. |
| **SCA-22** — Comp porch/patio/deck present | 🟡 VERIFY | 🟡 manual-verify | `comp_3_porch_patio_deck`=∅ | Please add the porch, patio, or deck information for Comp 3 in the sales grid. |
| **SCA-22** — Comp porch/patio/deck present | 🟡 VERIFY | 🟡 manual-verify | `comp_4_porch_patio_deck`=∅ | Please add the porch, patio, or deck information for Comp 4 in the sales grid. |
| **SCA-22** — Comp porch/patio/deck present | 🟡 VERIFY | 🟡 manual-verify | `comp_5_porch_patio_deck`=∅ | Please add the porch, patio, or deck information for Comp 5 in the sales grid. |
| **SCA-22** — Comp porch/patio/deck present | 🟡 VERIFY | 🟡 manual-verify | `comp_6_porch_patio_deck`=∅ | Please add the porch, patio, or deck information for Comp 6 in the sales grid. |
| **SCA-25** — New construction competing comp | 🟡 VERIFY | 🟡 manual-verify | `year_built`=2026@0.97; `condition_rating`=∅ | The subject appears to be new construction. Please confirm at least one comparable is from a competing development, or explain why that wasn't possibl… |
| **SCA-27** — Comparable photos present + type | 🟡 VERIFY | 🟡 manual-verify | `comp_photo_pages`=∅ | Photo check required — verify that comparable sale photos are present and match the correct properties. |
| **DOC-1** — License current at signature | 🟡 VERIFY | 🟡 manual-verify | `appraiser_cert_expiration_date`=2026-11-30@0.97; `date_of_signature`=∅ | The license expiration or signature date could not be read; please verify the license was current when the report was signed. |
| **SIG-4** — Appraiser email present | 🟡 VERIFY | 🟡 manual-verify | `appraiser_email`=∅ | The appraiser's email address is missing or unreadable. Please provide it. |
| **SIG-D** — Signature date >= effective date | 🟡 VERIFY | 🟡 manual-verify | `date_of_signature`=∅; `effective_date`=2026-06-23@0.97 | The signature date or effective date could not be read; please verify the signature date is on or after the effective date. |
| **ST-10** — Adverse site conditions addressed | 🟡 VERIFY | 🟠 extraction-gap | `adverse_site_conditions`=∅ | The adverse site conditions answer could not be extracted; manual review required. |
| **ST-8** — FEMA flood data complete; zone addressed | 🟡 VERIFY | 🟡 manual-verify | `fema_flood_hazard`=∅; `fema_flood_zone`=∅; `fema_map_date`=∅ | The flood zone information (zone, map number, and map date) must be completed in the site section — this is required even if the property is not in a … |
| **LISTING-CMNT** — Listing price vs appraised value commentary | 🟡 VERIFY | 🔵 advisory | `listing_history`=DOM 202;The subject was offered for sale on 10/0…@0.97; `appraised_value`=1200000@0.97; `listed_past_year`=Y@0.97 | The most recent listing price ($1,300,000) differs from the final value ($1,200,000) by 8.3%. Please add a comment in the report explaining this diffe… |
| **S-4d** — Tax year current | 🟡 VERIFY | 🟡 manual-verify | `tax_year`=∅; `effective_date`=2026-06-23@0.97 | The tax year / effective date could not be extracted; please verify the tax year is within the last 2 years. |
| **S-6b** — Map reference numeric | 🟡 VERIFY | 🟠 extraction-gap | `map_reference`=∅ | Map Reference could not be extracted from the document; manual review required. |
| **ST-INTENDED** — Intended use and intended user stated | 🟡 VERIFY | 🟡 manual-verify | `addendum_text`=∅ | The report must state what the appraisal is for (mortgage lending) and who it is for (the lender/client). Please confirm both of these statements are … |
| **ST-SCOPE** — Scope of work stated | 🟡 VERIFY | 🟡 manual-verify | `addendum_text`=∅ | The scope of work description could not be found. Please verify the report describes what type of inspection was performed and what the appraiser did … |
| **ADD-X** — Addenda cross-reference resolution | 🟢 PASS | — | — | Condition satisfied by the extracted value(s). |
| **C-2a** — Contract price matches purchase agreement | 🟢 PASS | — | `contract_price`=1200000@0.97 | Condition satisfied by the extracted value(s). |
| **C-2b** — Contract date matches purchase agreement | 🟢 PASS | — | `contract_date`=2026-06-10@0.97 | Condition satisfied by the extracted value(s). |
| **TL-CONTRACT** — Contract date precedes appraisal effective date | 🟢 PASS | — | `contract_date`=2026-06-10@0.97; `effective_date`=2026-06-23@0.97 | Condition satisfied by the extracted value(s). |
| **I-1** — General description complete | 🟢 PASS | — | `units_count`=1@0.97; `stories`=1@0.97; `dwelling_type`=Detached@0.97; `design_style`=Modern@0.97; `year_built`=2026@0.97; `effective_age`=0@0.97 | Condition satisfied by the extracted value(s). |
| **I-10** — Adverse livability conditions addressed | 🟢 PASS | — | `adverse_conditions`=No@0.97 | Condition satisfied by the extracted value(s). |
| **I-12** — Additions addressed | 🟢 PASS | — | — | Condition satisfied by the extracted value(s). |
| **I-2** — Foundation described | 🟢 PASS | — | `foundation_type`=Concrete/Good@0.97 | Condition satisfied by the extracted value(s). |
| **I-7** — Above-grade room count present | 🟢 PASS | — | `total_rooms`=10@0.97; `bedrooms`=5@0.97; `baths`=4.1@0.97; `gla`=3365@0.97 | Condition satisfied by the extracted value(s). |
| **I-AGE** — Effective age does not exceed actual age | 🟢 PASS | — | `effective_age`=0@0.97; `year_built`=2026@0.97; `effective_date`=2026-06-23@0.97 | Condition satisfied by the extracted value(s). |
| **I-YRBUILT** — Year built consistent with actual age | 🟢 PASS | — | `year_built`=2026@0.97; `effective_date`=2026-06-23@0.97; `effective_age`=0@0.97 | Condition satisfied by the extracted value(s). |
| **IM-2** — Bedroom / total-room count consistency | 🟢 PASS | — | `total_rooms`=10@0.97; `bedrooms`=5@0.97 | Condition satisfied by the extracted value(s). |
| **N-1** — Neighborhood characteristics marked | 🟢 PASS | — | `location`=Suburban@0.97 | Condition satisfied by the extracted value(s). |
| **N-1** — Neighborhood characteristics marked | 🟢 PASS | — | `built_up`=Over75Percent@0.97 | Condition satisfied by the extracted value(s). |
| **N-1** — Neighborhood characteristics marked | 🟢 PASS | — | `growth_rate`=Stable@0.97 | Condition satisfied by the extracted value(s). |
| **N-2** — Housing trends marked and consistent | 🟢 PASS | — | `property_values`=Stable@0.97 | Condition satisfied by the extracted value(s). |
| **N-2** — Housing trends marked and consistent | 🟢 PASS | — | `demand_supply`=InBalance@0.97 | Condition satisfied by the extracted value(s). |
| **N-2** — Housing trends marked and consistent | 🟢 PASS | — | `marketing_time`=UnderThreeMonths@0.97 | Condition satisfied by the extracted value(s). |
| **N-3** — Price/age ranges valid | 🟢 PASS | — | `price_low`=250@0.97; `price_high`=2350@0.97 | Condition satisfied by the extracted value(s). |
| **N-3** — Price/age ranges valid | 🟢 PASS | — | `age_low`=0@0.97; `age_high`=113@0.97 | Condition satisfied by the extracted value(s). |
| **N-4** — Present land use sums to 100% | 🟢 PASS | — | `land_use_one_unit`=70@0.97; `land_use_commercial`=10@0.97; `land_use_other`=20@0.97 | Condition satisfied by the extracted value(s). |
| **N-4** — Present land use sums to 100% | 🟢 PASS | — | `land_use_other`=20@0.97 | Condition satisfied by the extracted value(s). |
| **N-5** — All four boundaries delineated | 🟢 PASS | — | `neighborhood_boundaries`=North of sw 264th st, south of 308th st, east of…@0.97 | Condition satisfied by the extracted value(s). |
| **N-7** — Market conditions completed | 🟢 PASS | — | `market_conditions_commentary`=The general market condition of similar competin…@0.97 | Condition satisfied by the extracted value(s). |
| **R-2** — As-Is / Subject-To checked | 🟢 PASS | — | `appraisal_subject_to`=As Is@0.97 | Condition satisfied by the extracted value(s). |
| **R-2b** — Value equals contract price (bias advisory) | 🟢 PASS | — | `appraised_value`=1200000@0.97; `contract_price`=1200000@0.97 | Value equals contract price (noted for bias awareness; high-confidence extraction). |
| **R-VALUE-RANGE** — Final value within range of developed approach values | 🟢 PASS | — | `appraised_value`=1200000@0.97; `final_value_sca`=1200000@0.97; `cost_approach_value`=1209496@0.97 | Condition satisfied by the extracted value(s). |
| **RECON-T** — Reconciliation forbidden terms | 🟢 PASS | — | `final_reconciliation_comment`=∅ | Condition satisfied by the extracted value(s). |
| **VAL-1** — Final opinion of value extraction integrity | 🟢 PASS | — | `appraised_value`=1200000@0.97; `contract_price`=1200000@0.97 | Condition satisfied by the extracted value(s). |
| **CG-CONC-DIR** — Concession adjustment wrong direction | 🟢 PASS | — | `comp_5_sale_price`=1299990@0.97; `comp_5_concessions`=Listing@0.97; `comp_5_financing_adj`=∅ | Condition satisfied by the extracted value(s). |
| **CG-CONC-DIR** — Concession adjustment wrong direction | 🟢 PASS | — | `comp_6_sale_price`=930000@0.97; `comp_6_concessions`=Listing@0.97; `comp_6_financing_adj`=∅ | Condition satisfied by the extracted value(s). |
| **CG-COND-CONSIST** — Condition adjustment consistency across comps | 🟢 PASS | — | `comp_1_condition_adj`=∅; `comp_2_condition_adj`=∅; `comp_3_condition_adj`=∅ | Condition satisfied by the extracted value(s). |
| **CG-DIST** — Comp distance threshold by area type | 🟢 PASS | — | `comp_1_proximity`=0.04 miles S@0.97; `comp_2_proximity`=0.22 miles E@0.97; `comp_3_proximity`=0.07 miles E@0.97 | Condition satisfied by the extracted value(s). |
| **CG-GLA-BRACKET** — Subject GLA bracketed by comp GLAs | 🟢 PASS | — | `subject_grid_gla`=3365@0.97; `gla`=3365@0.97; `comp_1_gla`=3365@0.97; `comp_2_gla`=3365@0.97; `comp_3_gla`=3365@0.97 | Condition satisfied by the extracted value(s). |
| **CG-NET-BIAS** — Net adjustment directional bias | 🟢 PASS | — | `comp_1_net_adjustment`=2800@0.97; `comp_2_net_adjustment`=2400@0.97; `comp_3_net_adjustment`=0@0.97 | Condition satisfied by the extracted value(s). |
| **CG-PRIOR-SALE** — Comp prior sale rapid appreciation flag | 🟢 PASS | — | `comp_1_prior_sale_date`=∅; `comp_2_prior_sale_date`=∅; `comp_3_prior_sale_date`=∅ | No comparable prior sales within the look-back window with material price changes. |
| **SCA-11** — Comp site size has unit | 🟢 PASS | — | `comp_1_site_size`=18059 sf@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-11** — Comp site size has unit | 🟢 PASS | — | `comp_2_site_size`=18169 sf@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-11** — Comp site size has unit | 🟢 PASS | — | `comp_3_site_size`=16000 sf@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-11** — Comp site size has unit | 🟢 PASS | — | `comp_4_site_size`=21842 sf@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-11** — Comp site size has unit | 🟢 PASS | — | `comp_5_site_size`=20946 sf@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-11** — Comp site size has unit | 🟢 PASS | — | `comp_6_site_size`=12503 sf@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-12** — Comp view UAD format | 🟢 PASS | — | `comp_1_view`=N;Res;@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-12** — Comp view UAD format | 🟢 PASS | — | `comp_2_view`=N;Res;@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-12** — Comp view UAD format | 🟢 PASS | — | `comp_3_view`=N;Res;@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-12** — Comp view UAD format | 🟢 PASS | — | `comp_4_view`=N;Res;@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-12** — Comp view UAD format | 🟢 PASS | — | `comp_5_view`=N;Res;@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-12** — Comp view UAD format | 🟢 PASS | — | `comp_6_view`=N;Res;@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-13** — Comp design present | 🟢 PASS | — | `comp_1_design`=DT1;Modern@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-13** — Comp design present | 🟢 PASS | — | `comp_2_design`=DT1;Modern@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-13** — Comp design present | 🟢 PASS | — | `comp_3_design`=DT1;Modern@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-13** — Comp design present | 🟢 PASS | — | `comp_4_design`=DT1;Modern@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-13** — Comp design present | 🟢 PASS | — | `comp_5_design`=DT1;Modern@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-13** — Comp design present | 🟢 PASS | — | `comp_6_design`=DT1;Modern@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-14** — Comp quality UAD rating + zero-adj | 🟢 PASS | — | `comp_1_quality_rating`=Q3@0.97; `quality_rating`=∅; `comp_1_quality_rating_adjustment`=∅ | Condition satisfied by the extracted value(s). |
| **SCA-14** — Comp quality UAD rating + zero-adj | 🟢 PASS | — | `comp_2_quality_rating`=Q3@0.97; `quality_rating`=∅; `comp_2_quality_rating_adjustment`=∅ | Condition satisfied by the extracted value(s). |
| **SCA-14** — Comp quality UAD rating + zero-adj | 🟢 PASS | — | `comp_3_quality_rating`=Q3@0.97; `quality_rating`=∅; `comp_3_quality_rating_adjustment`=∅ | Condition satisfied by the extracted value(s). |
| **SCA-14** — Comp quality UAD rating + zero-adj | 🟢 PASS | — | `comp_4_quality_rating`=Q3@0.97; `quality_rating`=∅; `comp_4_quality_rating_adjustment`=∅ | Condition satisfied by the extracted value(s). |
| **SCA-14** — Comp quality UAD rating + zero-adj | 🟢 PASS | — | `comp_5_quality_rating`=Q3@0.97; `quality_rating`=∅; `comp_5_quality_rating_adjustment`=∅ | Condition satisfied by the extracted value(s). |
| **SCA-14** — Comp quality UAD rating + zero-adj | 🟢 PASS | — | `comp_6_quality_rating`=Q3@0.97; `quality_rating`=∅; `comp_6_quality_rating_adjustment`=∅ | Condition satisfied by the extracted value(s). |
| **SCA-15** — Subject actual age vs year built | 🟢 PASS | — | `subject_grid_actual_age`=∅; `year_built`=2026@0.97 | Year built (2026) implies age of 0 years — consistent with effective date. |
| **SCA-16** — Comp condition UAD rating + zero-adj | 🟢 PASS | — | `comp_1_condition_rating`=C1@0.97; `condition_rating`=∅; `comp_1_condition_rating_adjustment`=∅ | Condition satisfied by the extracted value(s). |
| **SCA-16** — Comp condition UAD rating + zero-adj | 🟢 PASS | — | `comp_2_condition_rating`=C1@0.97; `condition_rating`=∅; `comp_2_condition_rating_adjustment`=∅ | Condition satisfied by the extracted value(s). |
| **SCA-16** — Comp condition UAD rating + zero-adj | 🟢 PASS | — | `comp_3_condition_rating`=C1@0.97; `condition_rating`=∅; `comp_3_condition_rating_adjustment`=∅ | Condition satisfied by the extracted value(s). |
| **SCA-16** — Comp condition UAD rating + zero-adj | 🟢 PASS | — | `comp_4_condition_rating`=C2@0.97; `condition_rating`=∅; `comp_4_condition_rating_adjustment`=∅ | Condition satisfied by the extracted value(s). |
| **SCA-16** — Comp condition UAD rating + zero-adj | 🟢 PASS | — | `comp_5_condition_rating`=C2@0.97; `condition_rating`=∅; `comp_5_condition_rating_adjustment`=∅ | Condition satisfied by the extracted value(s). |
| **SCA-16** — Comp condition UAD rating + zero-adj | 🟢 PASS | — | `comp_6_condition_rating`=C2@0.97; `condition_rating`=∅; `comp_6_condition_rating_adjustment`=∅ | Condition satisfied by the extracted value(s). |
| **SCA-17** — Above-grade GLA matches grid, improvements & sketch | 🟢 PASS | — | `comp_1_gla`=3365@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-17** — Above-grade GLA matches grid, improvements & sketch | 🟢 PASS | — | `comp_2_gla`=3365@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-17** — Above-grade GLA matches grid, improvements & sketch | 🟢 PASS | — | `comp_3_gla`=3365@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-17** — Above-grade GLA matches grid, improvements & sketch | 🟢 PASS | — | `comp_4_gla`=3371@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-17** — Above-grade GLA matches grid, improvements & sketch | 🟢 PASS | — | `comp_5_gla`=3644@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-17** — Above-grade GLA matches grid, improvements & sketch | 🟢 PASS | — | `comp_6_gla`=2838@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-2** — Minimum comparable sales | 🟢 PASS | — | `comp_1_sale_price`=1200000@0.97; `comp_2_sale_price`=1200000@0.97; `comp_3_sale_price`=1150000@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-21** — Comp garage/carport present | 🟢 PASS | — | `comp_1_garage_carport`=2gbi2dw@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-21** — Comp garage/carport present | 🟢 PASS | — | `comp_2_garage_carport`=2gbi2dw@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-21** — Comp garage/carport present | 🟢 PASS | — | `comp_3_garage_carport`=2gbi2dw@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-21** — Comp garage/carport present | 🟢 PASS | — | `comp_4_garage_carport`=2gbi2dw@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-21** — Comp garage/carport present | 🟢 PASS | — | `comp_5_garage_carport`=2gbi2dw@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-21** — Comp garage/carport present | 🟢 PASS | — | `comp_6_garage_carport`=2gbi2dw@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-23** — Listing comp adjustment | 🟢 PASS | — | `comp_5_sale_date`=Active@0.97; `comp_5_net_adjustment`=-38780@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-23** — Listing comp adjustment | 🟢 PASS | — | `comp_6_sale_date`=Active@0.97; `comp_6_net_adjustment`=91140@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-26** — Subject GLA bracketed by comps | 🟢 PASS | — | `gla`=3365@0.97; `comp_1_gla`=3365@0.97; `comp_2_gla`=3365@0.97; `comp_3_gla`=3365@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-3** — Comp address present | 🟢 PASS | — | `comp_1_address`=17373 SW 288th St, Homestead, FL@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-3** — Comp address present | 🟢 PASS | — | `comp_2_address`=17205 SW 288th St, Homestead, FL@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-3** — Comp address present | 🟢 PASS | — | `comp_3_address`=17300 SW 287th St, Homestead, FL@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-3** — Comp address present | 🟢 PASS | — | `comp_4_address`=18645 SW 294th Ter, Homestead, FL@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-3** — Comp address present | 🟢 PASS | — | `comp_5_address`=29215 SW 167th Ct, Homestead, FL@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-3** — Comp address present | 🟢 PASS | — | `comp_6_address`=16910 SW 288th Ter, Homestead, FL@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-4** — Comp proximity present | 🟢 PASS | — | `comp_1_proximity`=0.04 miles S@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-4** — Comp proximity present | 🟢 PASS | — | `comp_2_proximity`=0.22 miles E@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-4** — Comp proximity present | 🟢 PASS | — | `comp_3_proximity`=0.07 miles E@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-4** — Comp proximity present | 🟢 PASS | — | `comp_4_proximity`=1.37 miles W@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-4** — Comp proximity present | 🟢 PASS | — | `comp_5_proximity`=0.96 miles NE@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-4** — Comp proximity present | 🟢 PASS | — | `comp_6_proximity`=0.45 miles E@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-5** — Comp data source present | 🟢 PASS | — | `comp_1_data_source`=SEFMLS #A11920955;DOM 86@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-5** — Comp data source present | 🟢 PASS | — | `comp_2_data_source`=SEFMLS #A11899135;DOM 4@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-5** — Comp data source present | 🟢 PASS | — | `comp_3_data_source`=SEFMLS #A11875837;DOM 1@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-5** — Comp data source present | 🟢 PASS | — | `comp_4_data_source`=SEFMLS #A11796533;DOM 61@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-5** — Comp data source present | 🟢 PASS | — | `comp_5_data_source`=SEFMLS #A11995392;DOM 67@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-5** — Comp data source present | 🟢 PASS | — | `comp_6_data_source`=SEFMLS #B26020704;DOM 58@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-6** — Comp verification source specific | 🟢 PASS | — | `comp_1_verification_source`=Doc#35057-1637Realist@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-6** — Comp verification source specific | 🟢 PASS | — | `comp_2_verification_source`=Doc#35068-2170Realist@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-6** — Comp verification source specific | 🟢 PASS | — | `comp_3_verification_source`=Doc#35088-3082Realist@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-6** — Comp verification source specific | 🟢 PASS | — | `comp_4_verification_source`=Doc#34884-2435Realist@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-6** — Comp verification source specific | 🟢 PASS | — | `comp_5_verification_source`=Realist@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-6** — Comp verification source specific | 🟢 PASS | — | `comp_6_verification_source`=Realist@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-8** — Comp date of sale sequencing | 🟢 PASS | — | `comp_1_sale_date`=s11/25;c10/25@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-8** — Comp date of sale sequencing | 🟢 PASS | — | `comp_2_sale_date`=s12/25;c10/25@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-8** — Comp date of sale sequencing | 🟢 PASS | — | `comp_3_sale_date`=s12/25;c08/25@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-8** — Comp date of sale sequencing | 🟢 PASS | — | `comp_4_sale_date`=s07/25;c07/25@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-9** — Comp location UAD format | 🟢 PASS | — | `comp_1_location_rating`=N;Res;BsyRd@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-9** — Comp location UAD format | 🟢 PASS | — | `comp_2_location_rating`=N;Res;BsyRd@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-9** — Comp location UAD format | 🟢 PASS | — | `comp_3_location_rating`=N;Res;@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-9** — Comp location UAD format | 🟢 PASS | — | `comp_4_location_rating`=N;Res;@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-9** — Comp location UAD format | 🟢 PASS | — | `comp_5_location_rating`=N;Res;@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-9** — Comp location UAD format | 🟢 PASS | — | `comp_6_location_rating`=N;Res;@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-BR** — Value bracketed by adjusted prices | 🟢 PASS | — | `appraised_value`=1200000@0.97; `comp_1_adjusted_sale_price`=1202800@0.97; `comp_2_adjusted_sale_price`=1202400@0.97; `comp_3_adjusted_sale_price`=1150000@0.97; `comp_4_adjusted_sale_price`=1124600@0.97; `comp_5_adjusted_sale_price`=1261210@0.97; `comp_6_adjusted_sale_price`=1021140@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-BR2** — Min comps with adjusted value at/above final opinion (lender overlay) | 🟢 PASS | — | `appraised_value`=1200000@0.97; `comp_1_adjusted_sale_price`=1202800@0.97; `comp_2_adjusted_sale_price`=1202400@0.97; `comp_3_adjusted_sale_price`=1150000@0.97; `comp_4_adjusted_sale_price`=1124600@0.97; `comp_5_adjusted_sale_price`=1261210@0.97; `comp_6_adjusted_sale_price`=1021140@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-DC** — Comp sale within date currency window | 🟢 PASS | — | `comp_1_sale_date`=s11/25;c10/25@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-DC** — Comp sale within date currency window | 🟢 PASS | — | `comp_2_sale_date`=s12/25;c10/25@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-DC** — Comp sale within date currency window | 🟢 PASS | — | `comp_3_sale_date`=s12/25;c08/25@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-DC** — Comp sale within date currency window | 🟢 PASS | — | `comp_4_sale_date`=s07/25;c07/25@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-FLIP** — Comp rapid resale flag | 🟢 PASS | — | `comp_1_prior_sale_date`=∅ | Condition satisfied by the extracted value(s). |
| **SCA-GROSS** — Gross adjustment per comp within 25% | 🟢 PASS | — | `comp_1_gross_adj_pct`=1.4@0.97; `comp_2_gross_adj_pct`=1.5@0.97; `comp_3_gross_adj_pct`=0.0@0.97; `comp_4_gross_adj_pct`=5.9@0.97; `comp_5_gross_adj_pct`=6.8@0.97; `comp_6_gross_adj_pct`=11.8@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-NET** — Net adjustment within 15% | 🟢 PASS | — | `comp_1_net_adjustment`=2800@0.97; `comp_2_net_adjustment`=2400@0.97; `comp_3_net_adjustment`=0@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-PR** — Comp sale price bracket vs subject value | 🟢 PASS | — | `comp_1_sale_price`=1200000@0.97; `appraised_value`=1200000@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-PR** — Comp sale price bracket vs subject value | 🟢 PASS | — | `comp_2_sale_price`=1200000@0.97; `appraised_value`=1200000@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-PR** — Comp sale price bracket vs subject value | 🟢 PASS | — | `comp_3_sale_price`=1150000@0.97; `appraised_value`=1200000@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-PR** — Comp sale price bracket vs subject value | 🟢 PASS | — | `comp_4_sale_price`=1100000@0.97; `appraised_value`=1200000@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-PR** — Comp sale price bracket vs subject value | 🟢 PASS | — | `comp_5_sale_price`=1299990@0.97; `appraised_value`=1200000@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-PR** — Comp sale price bracket vs subject value | 🟢 PASS | — | `comp_6_sale_price`=930000@0.97; `appraised_value`=1200000@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-PSH** — Subject prior sale analyzed | 🟢 PASS | — | `subject_grid_prior_sale_date`=∅; `effective_date`=2026-06-23@0.97 | Condition satisfied by the extracted value(s). |
| **SIG-1** — Appraiser signed / name present | 🟢 PASS | — | `appraiser_name`=Juan Mendoza@0.97; `date_of_signature`=∅ | Condition satisfied by the extracted value(s). |
| **SIG-3** — Appraiser licensed in property state | 🟢 PASS | — | `appraiser_license_state`=FL@0.97; `state`=FL@0.97 | Condition satisfied by the extracted value(s). |
| **ST-GEO-COMP** — Appraiser geographic competency | 🟢 PASS | — | `appraiser_license_state`=FL@0.97; `state`=FL@0.97 | Condition satisfied by the extracted value(s). |
| **ST-1** — Site dimensions provided | 🟢 PASS | — | `site_dimensions`=Approximately 128 x 125@0.97 | Condition satisfied by the extracted value(s). |
| **ST-2** — Site area has correct unit | 🟢 PASS | — | `site_area`=16000 sf@0.97; `site_area_unit`=∅ | Condition satisfied by the extracted value(s). |
| **ST-3** — Site shape provided | 🟢 PASS | — | `site_shape`=Rectangular@0.97 | Condition satisfied by the extracted value(s). |
| **ST-4** — View UAD compliant and consistent | 🟢 PASS | — | `site_view`=N;Res;@0.97 | Condition satisfied by the extracted value(s). |
| **ST-5** — Zoning compliance | 🟢 PASS | — | `zoning_compliance`=Legal@0.97 | Condition satisfied by the extracted value(s). |
| **ST-6** — Highest & best use is Yes | 🟢 PASS | — | `highest_and_best_use`=Yes@0.97 | Condition satisfied by the extracted value(s). |
| **ST-7** — Utilities marked; private systems addressed | 🟢 PASS | — | `utilities_electricity`=Public@0.97; `utilities_gas`=None@0.97 | Condition satisfied by the extracted value(s). |
| **ST-9** — Utilities/off-site typical for market | 🟢 PASS | — | `utilities_water`=Public@0.97; `utilities_sewer`=Public@0.97 | Condition satisfied by the extracted value(s). |
| **ST-HBU** — Highest and best use stated and consistent | 🟢 PASS | — | `highest_and_best_use`=Yes@0.97; `highest_best_use_indicator`=∅; `highest_best_use_description`=∅ | Condition satisfied by the extracted value(s). |
| **ST-RIGHTS** — Leasehold property rights disclosure | 🟢 PASS | — | `property_rights`=FeeSimple@0.97; `addendum_text`=∅ | Condition satisfied by the extracted value(s). |
| **I-HOA-PUD** — HOA/PUD consistency | 🟢 PASS | — | `hoa_dues`=∅; `is_pud`=∅ | Condition satisfied by the extracted value(s). |
| **S-11** — Property rights appraised present | 🟢 PASS | — | `property_rights`=FeeSimple@0.97 | Condition satisfied by the extracted value(s). |
| **S-4b** — APN present and plausible | 🟢 PASS | — | `assessors_parcel_number`=30-7906-011-0020@0.97 | Condition satisfied by the extracted value(s). |
| **S-5** — Neighborhood name valid | 🟢 PASS | — | `neighborhood_name`=Estates Of Biscayne@0.97 | Condition satisfied by the extracted value(s). |
| **S-6** — Census tract format | 🟢 PASS | — | `census_tract`=0111.06@0.97 | Condition satisfied by the extracted value(s). |
| **S-7** — Occupancy status marked | 🟢 PASS | — | `occupant_status`=Vacant@0.97 | Condition satisfied by the extracted value(s). |
| **S-7** — Occupancy status marked | 🟢 PASS | — | `occupant_status`=Vacant@0.97 | Condition satisfied by the extracted value(s). |
| **S-9** — HOA dues imply PUD marked | 🟢 PASS | — | `hoa_dues`=∅; `is_pud_checked`=∅ | Condition satisfied by the extracted value(s). |
| **ST-FORM-MATCH** — Form type matches property type | 🟢 PASS | — | `design_style`=Modern@0.97 | Condition satisfied by the extracted value(s). |
| **ADD-2** — Comparable selection commentary explains why | ⚪ N/A | — | — | No substantive sales-comparison narrative extracted. |
| **ADD-4** — 1004MC required for FHA/USDA | ⚪ N/A | — | — | Not applicable to this loan/transaction/form type. |
| **ADD-5** — 1004MC inventory analysis complete | ⚪ N/A | — | — | Not applicable to this loan/transaction/form type. |
| **ADD-8** — 1004MC condo project section complete | ⚪ N/A | — | — | Not applicable to this loan/transaction/form type. |
| **C-5** — Personal property addressed | ⚪ N/A | — | — | Not applicable to this loan/transaction/form type. |
| **C-BUYER-MATCH** — Buyer names match borrower(s) on order | ⚪ N/A | — | — | Not applicable to this loan/transaction/form type. |
| **C-EXEC** — Contract fully executed by all parties | ⚪ N/A | — | `contract_analysis_comment`=∅ | No contract analysis commentary extracted; C-1 governs. |
| **C-PKG-EXEC** — Contract fully executed (manual verification) | ⚪ N/A | — | — | Not applicable to this loan/transaction/form type. |
| **ORD-ASSIGN-MATCH** — Assignment type in engagement letter matches appraisal report | ⚪ N/A | — | — | Not applicable to this loan/transaction/form type. |
| **ORD-EXEC-STOP** — Unsigned contract blocked by engagement letter policy | ⚪ N/A | — | — | Not applicable to this loan/transaction/form type. |
| **CA-2** — Remaining economic life >= 30 (FHA/VA) | ⚪ N/A | — | — | Not applicable to this loan/transaction/form type. |
| **FHA-1** — FHA Minimum Property Requirements confirmed | ⚪ N/A | — | — | Not applicable to this loan/transaction/form type. |
| **FHA-10** — FHA remaining economic life >= 30 | ⚪ N/A | — | — | Not applicable to this loan/transaction/form type. |
| **FHA-12** — FHA well/septic compliance | ⚪ N/A | — | — | Not applicable to this loan/transaction/form type. |
| **FHA-13** — FHA appliances present/operational | ⚪ N/A | — | — | Not applicable to this loan/transaction/form type. |
| **FHA-2** — FHA case number format + match | ⚪ N/A | — | — | Not applicable to this loan/transaction/form type. |
| **FHA-3** — FHA intended use/user statements | ⚪ N/A | — | — | Not applicable to this loan/transaction/form type. |
| **FHA-4** — FHA/HUD certification statement present | ⚪ N/A | — | — | Not applicable to this loan/transaction/form type. |
| **FHA-5** — FHA primary comps within 12 months | ⚪ N/A | — | — | Not applicable to this loan/transaction/form type. |
| **FHA-6** — FHA repairs reported subject-to | ⚪ N/A | — | — | Not applicable to this loan/transaction/form type. |
| **FHA-7** — FHA space heater not primary heat | ⚪ N/A | — | — | Not applicable to this loan/transaction/form type. |
| **FHA-9** — FHA four-side photos | ⚪ N/A | — | — | Not applicable to this loan/transaction/form type. |
| **G-1** — Loan-type consistency (engagement vs appraisal) | ⚪ N/A | — | `loan_type`=∅; `fha_case_number`=∅ | Engagement letter / order form not available. |
| **G-C56** — C5/C6 condition triggers AMC stop | ⚪ N/A | — | — | Not applicable to this loan/transaction/form type. |
| **G-LAVA** — Hawaiian lava zone triggers AMC stop | ⚪ N/A | — | — | Not applicable to this loan/transaction/form type. |
| **G-MFG** — Pre-1976 manufactured home triggers AMC stop | ⚪ N/A | — | — | Not applicable to this loan/transaction/form type. |
| **ORD-CONFLICT** — Engagement letter and XML disagree on order-level facts | ⚪ N/A | — | — | Not applicable to this loan/transaction/form type. |
| **IA-1** — Income approach rent matches rent schedule | ⚪ N/A | — | — | Income approach / rent schedule not developed. |
| **MF-1** — Multi-family requires income approach | ⚪ N/A | — | — | Not applicable to this loan/transaction/form type. |
| **R-INCOME-REQ** — Income approach developed when required | ⚪ N/A | — | `income_approach_value`=∅; `occupancy_type`=Vacant@0.97 | Income approach not required for this occupancy type. |
| **CG-NONARMS** — Non-arms-length comp without commentary | ⚪ N/A | — | — | No non-arms-length distress indicators found in comparables. |
| **SCA-PSH-Q** — Subject sale history analysis is substantive | ⚪ N/A | — | — | No prior sale/transfer within the look-back window; quality check not applicable. |
| **ORD-ENG-DATE** — Engagement letter predates appraisal report | ⚪ N/A | — | — | Not applicable to this loan/transaction/form type. |
| **SIG-2** — Appraiser name matches engagement | ⚪ N/A | — | — | Not applicable to this loan/transaction/form type. |
| **SIG-SUP** — Supervisory appraiser section complete | ⚪ N/A | — | — | Not applicable to this loan/transaction/form type. |
| **SIG-TRAINEE** — Trainee appraiser requires supervisory cosign | ⚪ N/A | — | `appraiser_license_type`=Certificate@0.97; `supervisory_appraiser_name`=∅; `supervisory_appraiser_cert_number`=∅ | Rule does not apply to this loan/form/transaction type. |
| **ST-PRIOR-SVC** — Prior services disclosure | ⚪ N/A | — | `prior_services_indicator`=∅; `prior_services_description`=∅; `addendum_text`=∅ | Rule does not apply to this loan/form/transaction type. |
| **TL-ENG** — Engagement letter date precedes report signature date | ⚪ N/A | — | — | Not applicable to this loan/transaction/form type. |
| **ST-1B** — Site area magnitude plausibility (multi-signal) | ⚪ N/A | — | `site_area`=16000 sf@0.97; `site_area_unit`=∅ | Rule does not apply to this loan/form/transaction type. |
| **ST-FLOOD-CMT** — Flood zone present — marketability commentary required | ⚪ N/A | — | — | Not applicable to this loan/transaction/form type. |
| **ST-ZONE-NC** — Zoning non-conformance commentary | ⚪ N/A | — | `zoning_compliance`=Legal@0.97; `addendum_text`=∅ | Rule does not apply to this loan/form/transaction type. |
| **ORD-COBORROWER** — Co-borrower from order appears in appraisal borrower field | ⚪ N/A | — | — | Not applicable to this loan/transaction/form type. |
| **ORD-FORM-MATCH** — Form type in report matches form type ordered | ⚪ N/A | — | — | Not applicable to this loan/transaction/form type. |
| **ORD-INSP-SCOPE** — Ordered inspection type matches report scope of work | ⚪ N/A | — | — | Not applicable to this loan/transaction/form type. |
| **S-1** — Property address matches order form | ⚪ N/A | — | `property_address`=17354 SW 287th St@0.97 | Engagement letter / order form not available. |
| **S-1** — Property address matches order form | ⚪ N/A | — | `city`=Homestead@0.97 | Engagement letter / order form not available. |
| **S-1** — Property address matches order form | ⚪ N/A | — | `zip_code`=33030@0.97 | Engagement letter / order form not available. |
| **S-10a** — Lender name matches order form | ⚪ N/A | — | `lender_name`=See attached addenda.@0.97 | Engagement letter / order form not available. |
| **S-10b** — Lender address matches order form | ⚪ N/A | — | — | Engagement letter / order form not available. |
| **S-2** — Borrower matches order form | ⚪ N/A | — | — | Engagement letter / order form not available. |
| **USDA-1** — USDA cost approach required | ⚪ N/A | — | — | Not applicable to this loan/transaction/form type. |


---

## dir 6 — 3825 Austin Rd.xml

| Rule | Status | Bucket | Extracted (what the rule read) | How it was judged |
|------|--------|--------|-------------------------------|-------------------|
| **SUBJECT-HOLD** — subject | 🔴 FAIL | 🔴 hard-fail | — | 5 failures in the subject section indicate systematic problems (not isolated errors); the section is escalated for a full manual review. |
| **G-0** — Engagement letter / order form present and extracted | 🔴 FAIL | 🟠 extraction-gap | `loan_type`=∅ | The engagement letter / order form was not extracted. All lender-overlay rules (comp count minimum, site value requirement, declining-market clause, A… |
| **SCA-2** — Minimum comparable sales | 🔴 FAIL | 🔴 hard-fail | `comp_1_sale_price`=172000@0.97; `comp_2_sale_price`=201000@0.97; `comp_3_sale_price`=285000@0.97 | Only 0 active listing comparable(s) were found (6 closed sales). The client requires at least 1 active listing(s). Please add one or explain in the re… |
| **S-12** — Prior-listing data source present | 🔴 FAIL | 🔴 hard-fail | `offered_for_sale_12mo`=∅; `data_source`=∅ | The checkbox about prior sale or listing activity in the past 12 months is missing a data source. Please provide the source used to answer this questi… |
| **S-3** — Owner of public record present | 🔴 FAIL | 🔴 hard-fail | `owner_of_public_record`=∅; `legal_description`=∅; `real_estate_taxes`=∅; `special_assessments`=∅ | The 'Owner of Public Record' field is blank. Please complete it. |
| **ADD-9** — USPAP addendum complete | 🟡 VERIFY | 🟠 extraction-gap | — | The USPAP addendum fields (report type, reasonable exposure time, prior services) could not be extracted; manual review required. |
| **C-ANALYZE** — Contract analysis indicator consistency | 🟡 VERIFY | 🟠 extraction-gap | `contract_analyzed`=∅ | The contract_analyzed indicator could not be extracted; rule cannot evaluate — manual review required. |
| **CA-1** — Opinion of site value present | 🟡 VERIFY | 🟡 manual-verify | `site_value_estimate`=∅ | The cost approach is missing an opinion of site value. Please provide one. |
| **I-10** — Adverse livability conditions addressed | 🟡 VERIFY | 🟡 manual-verify | `adverse_conditions`=Yes@0.97 | A physical deficiency or adverse condition is indicated. Please confirm this is addressed in the report with specific commentary on how it affects the… |
| **I-11** — Conforms to neighborhood | 🟡 VERIFY | 🟠 extraction-gap | `conforms_to_neighborhood`=∅ | Conformity to the neighborhood could not be read; please verify the improvements conform. |
| **I-34** — Materials/condition described | 🟡 VERIFY | 🟡 manual-verify | `exterior_walls`=∅; `roof_surface`=∅; `heating`=∅; `floor_material`=∅; `walls_material`=∅; `trim_finish_material`=∅ | The following materials/condition fields are missing in the improvements section: Exterior Walls, Roof Surface, Heating, Floors, Walls, Trim/Finish. P… |
| **I-5** — Heating and cooling described | 🟡 VERIFY | 🟡 manual-verify | `heating`=∅; `cooling`=∅ | The following heating/cooling fields are not described in the improvements section: Heating, Cooling. Please complete. |
| **I-6** — Appliances reported | 🟡 VERIFY | 🟡 manual-verify | `appliance_refrigerator`=∅; `appliance_range_oven`=∅; `appliance_disposal`=∅; `appliance_dishwasher`=∅; `appliance_microwave`=∅; `appliance_washer_dryer`=∅ | No kitchen appliances are listed in the improvements section. Please note which appliances are present. |
| **I-8** — Additional features described | 🟡 VERIFY | 🟡 manual-verify | `fireplace_count`=∅; `porch_patio_deck`=∅; `additional_features`=∅ | Please confirm any additional features (fireplace, porch/patio/deck, pool, etc.) are described in the improvements section, or state 'None'. |
| **I-9** — Condition rating UAD and consistent | 🟡 VERIFY | 🟠 extraction-gap | `condition_rating`=∅ | Condition could not be extracted from the document; manual review required. |
| **I-Q** — Quality rating UAD format | 🟡 VERIFY | 🟠 extraction-gap | `quality_rating`=∅ | Quality could not be extracted from the document; manual review required. |
| **I-SMCO** — Smoke/CO detector code compliance noted | 🟡 VERIFY | 🟡 manual-verify | `sales_comparison_summary`=∅ | No mention of smoke or CO detectors was found in the report. The client requires a note confirming detectors meet local code — please add one to the r… |
| **N-6** — Neighborhood description specific | 🟡 VERIFY | 🟡 manual-verify | `neighborhood_description`=THE SUBJECT IS LOCATED IN A SEMI RURAL RESIDENTI…@0.97 | The Neighborhood Description reads like a generic template. Please add specific details — like nearby streets, local landmarks, proximity to schools o… |
| **N-7** — Market conditions completed | 🟡 VERIFY | 🟡 manual-verify | `market_conditions_commentary`=THE SUBJECT IS LOCATED IN A STABLE MARKET, BUT B…@0.97 | The market conditions commentary only restates the checkbox answers in paragraph form. Please add real numbers — like average days on market, months o… |
| **PH-1** — Subject front/rear/street photos | 🟡 VERIFY | 🟡 manual-verify | `photo_front`=∅; `photo_rear`=∅; `photo_street`=∅ | Required photos are missing: front, rear, street scene. At minimum, please include a front photo, a rear photo, and a street scene. |
| **PH-2** — Interior photos present | 🟡 VERIFY | 🟡 manual-verify | `photo_interior_rooms`=∅ | Interior photos are incomplete — missing: kitchen, living, bedroom, bathroom. Please include photos of the kitchen, living room, all bedrooms, and all… |
| **R-1** — SCA value matches market value | 🟡 VERIFY | 🟡 manual-verify | `indicated_value_sca`=∅; `appraised_value`=240000@0.97 | The sales comparison value or final opinion of value could not be read. Please verify both numbers are present and agree. |
| **R-1b** — Reconciliation names the weighted approach | 🟡 VERIFY | 🟡 manual-verify | `final_reconciliation_comment`=∅ | The reconciliation must say which approach was relied on most (sales comparison, cost, or income) and briefly explain why. Please add that statement t… |
| **R-ASSIGN-COND** — Assignment condition vs report language consistency | 🟡 VERIFY | 🟡 manual-verify | `assignment_condition`=AsIs@0.97; `addendum_text`=∅; `limiting_conditions_text`=∅ | The assignment condition box (AsIs) doesn't match the language used in the report narrative. Please make sure the box and the written description agre… |
| **R-EXPOSURE** — Exposure time stated as a specific period | 🟡 VERIFY | 🟡 manual-verify | `addendum_text`=∅; `final_reconciliation_comment`=∅ | No specific exposure time period was found. Please add a statement like 'estimated exposure time of 3-6 months' in the reconciliation or addendum. |
| **R-MKTTIME** — Marketing time consistent with neighborhood data | 🟡 VERIFY | 🟡 manual-verify | `marketing_time_typical`=UnderThreeMonths@0.97; `addendum_text`=∅ | The marketing time stated in the report appears inconsistent with the market data for this area. Please make sure the estimated selling time matches w… |
| **SCA-10** — Comp property rights present + consistent | 🟡 VERIFY | 🟡 manual-verify | `comp_1_leasehold`=∅ | Please indicate the property rights (Fee Simple or Leasehold) for Comp 1 in the sales grid. |
| **SCA-10** — Comp property rights present + consistent | 🟡 VERIFY | 🟡 manual-verify | `comp_2_leasehold`=∅ | Please indicate the property rights (Fee Simple or Leasehold) for Comp 2 in the sales grid. |
| **SCA-10** — Comp property rights present + consistent | 🟡 VERIFY | 🟡 manual-verify | `comp_3_leasehold`=∅ | Please indicate the property rights (Fee Simple or Leasehold) for Comp 3 in the sales grid. |
| **SCA-10** — Comp property rights present + consistent | 🟡 VERIFY | 🟡 manual-verify | `comp_4_leasehold`=∅ | Please indicate the property rights (Fee Simple or Leasehold) for Comp 4 in the sales grid. |
| **SCA-10** — Comp property rights present + consistent | 🟡 VERIFY | 🟡 manual-verify | `comp_5_leasehold`=∅ | Please indicate the property rights (Fee Simple or Leasehold) for Comp 5 in the sales grid. |
| **SCA-10** — Comp property rights present + consistent | 🟡 VERIFY | 🟡 manual-verify | `comp_6_leasehold`=∅ | Please indicate the property rights (Fee Simple or Leasehold) for Comp 6 in the sales grid. |
| **SCA-16V** — Comp photo condition cross-check | 🟡 VERIFY | 🟠 extraction-gap | — | Please open the report and visually confirm that the front photo matches the subject property address. Automated photo review is not available for thi… |
| **SCA-17** — Above-grade GLA matches grid, improvements & sketch | 🟡 VERIFY | 🟡 manual-verify | `subject_grid_gla`=1934@0.97; `gla`=1934@0.97; `sketch_living_area`=∅ | The living area couldn't be confirmed across all sources (SCA grid 1934, improvements 1934, sketch n/a sf). Please verify the GLA in the sales grid ma… |
| **SCA-18** — Comp basement present | 🟡 VERIFY | 🟡 manual-verify | `comp_1_basement`=∅ | Basement and below-grade rooms are missing for Comp 1. Please fill this in (finished sq ft and room count, or 'None' if there is none). |
| **SCA-18** — Comp basement present | 🟡 VERIFY | 🟡 manual-verify | `comp_2_basement`=∅ | Basement and below-grade rooms are missing for Comp 2. Please fill this in (finished sq ft and room count, or 'None' if there is none). |
| **SCA-18** — Comp basement present | 🟡 VERIFY | 🟡 manual-verify | `comp_3_basement`=∅ | Basement and below-grade rooms are missing for Comp 3. Please fill this in (finished sq ft and room count, or 'None' if there is none). |
| **SCA-18** — Comp basement present | 🟡 VERIFY | 🟡 manual-verify | `comp_4_basement`=∅ | Basement and below-grade rooms are missing for Comp 4. Please fill this in (finished sq ft and room count, or 'None' if there is none). |
| **SCA-18** — Comp basement present | 🟡 VERIFY | 🟡 manual-verify | `comp_5_basement`=∅ | Basement and below-grade rooms are missing for Comp 5. Please fill this in (finished sq ft and room count, or 'None' if there is none). |
| **SCA-18** — Comp basement present | 🟡 VERIFY | 🟡 manual-verify | `comp_6_basement`=∅ | Basement and below-grade rooms are missing for Comp 6. Please fill this in (finished sq ft and room count, or 'None' if there is none). |
| **SCA-19** — Comp functional utility present | 🟡 VERIFY | 🟡 manual-verify | `comp_1_functional_utility`=∅ | Please add functional utility for Comp 1 in the sales grid. |
| **SCA-19** — Comp functional utility present | 🟡 VERIFY | 🟡 manual-verify | `comp_2_functional_utility`=∅ | Please add functional utility for Comp 2 in the sales grid. |
| **SCA-19** — Comp functional utility present | 🟡 VERIFY | 🟡 manual-verify | `comp_3_functional_utility`=∅ | Please add functional utility for Comp 3 in the sales grid. |
| **SCA-19** — Comp functional utility present | 🟡 VERIFY | 🟡 manual-verify | `comp_4_functional_utility`=∅ | Please add functional utility for Comp 4 in the sales grid. |
| **SCA-19** — Comp functional utility present | 🟡 VERIFY | 🟡 manual-verify | `comp_5_functional_utility`=∅ | Please add functional utility for Comp 5 in the sales grid. |
| **SCA-19** — Comp functional utility present | 🟡 VERIFY | 🟡 manual-verify | `comp_6_functional_utility`=∅ | Please add functional utility for Comp 6 in the sales grid. |
| **SCA-20** — Comp heating/cooling present | 🟡 VERIFY | 🟡 manual-verify | `comp_1_heating_cooling`=∅ | Please add the heating/cooling information for Comp 1 in the sales grid. |
| **SCA-20** — Comp heating/cooling present | 🟡 VERIFY | 🟡 manual-verify | `comp_2_heating_cooling`=∅ | Please add the heating/cooling information for Comp 2 in the sales grid. |
| **SCA-20** — Comp heating/cooling present | 🟡 VERIFY | 🟡 manual-verify | `comp_3_heating_cooling`=∅ | Please add the heating/cooling information for Comp 3 in the sales grid. |
| **SCA-20** — Comp heating/cooling present | 🟡 VERIFY | 🟡 manual-verify | `comp_4_heating_cooling`=∅ | Please add the heating/cooling information for Comp 4 in the sales grid. |
| **SCA-20** — Comp heating/cooling present | 🟡 VERIFY | 🟡 manual-verify | `comp_5_heating_cooling`=∅ | Please add the heating/cooling information for Comp 5 in the sales grid. |
| **SCA-20** — Comp heating/cooling present | 🟡 VERIFY | 🟡 manual-verify | `comp_6_heating_cooling`=∅ | Please add the heating/cooling information for Comp 6 in the sales grid. |
| **SCA-22** — Comp porch/patio/deck present | 🟡 VERIFY | 🟡 manual-verify | `comp_1_porch_patio_deck`=∅ | Please add the porch, patio, or deck information for Comp 1 in the sales grid. |
| **SCA-22** — Comp porch/patio/deck present | 🟡 VERIFY | 🟡 manual-verify | `comp_2_porch_patio_deck`=∅ | Please add the porch, patio, or deck information for Comp 2 in the sales grid. |
| **SCA-22** — Comp porch/patio/deck present | 🟡 VERIFY | 🟡 manual-verify | `comp_3_porch_patio_deck`=∅ | Please add the porch, patio, or deck information for Comp 3 in the sales grid. |
| **SCA-22** — Comp porch/patio/deck present | 🟡 VERIFY | 🟡 manual-verify | `comp_4_porch_patio_deck`=∅ | Please add the porch, patio, or deck information for Comp 4 in the sales grid. |
| **SCA-22** — Comp porch/patio/deck present | 🟡 VERIFY | 🟡 manual-verify | `comp_5_porch_patio_deck`=∅ | Please add the porch, patio, or deck information for Comp 5 in the sales grid. |
| **SCA-22** — Comp porch/patio/deck present | 🟡 VERIFY | 🟡 manual-verify | `comp_6_porch_patio_deck`=∅ | Please add the porch, patio, or deck information for Comp 6 in the sales grid. |
| **SCA-27** — Comparable photos present + type | 🟡 VERIFY | 🟡 manual-verify | `comp_photo_pages`=∅ | Photo check required — verify that comparable sale photos are present and match the correct properties. |
| **SCA-FLIP** — Comp rapid resale flag | 🟡 VERIFY | 🟡 manual-verify | `comp_5_prior_sale_date`=04/21/2025@0.97; `comp_5_sale_date`=s02/26;c01/26@0.97 | Comp 5 resold within 10 month(s). Please confirm this was an arm's-length transaction and add a comment on the quick turnaround. No supporting explana… |
| **SCA-GROSS** — Gross adjustment per comp within 25% | 🟡 VERIFY | 🟡 manual-verify | `comp_1_gross_adj_pct`=32.6@0.97; `comp_2_gross_adj_pct`=34.2@0.97; `comp_3_gross_adj_pct`=18.2@0.97; `comp_4_gross_adj_pct`=21.1@0.97; `comp_5_gross_adj_pct`=19.8@0.97; `comp_6_gross_adj_pct`=13.9@0.97 | Comps 1, 2 have gross adjustments over 25%, which suggests they may be quite different from the subject. Please explain why they were used, or conside… |
| **SCA-PR** — Comp sale price bracket vs subject value | 🟡 VERIFY | 🟡 manual-verify | `comp_1_sale_price`=172000@0.97; `appraised_value`=240000@0.97 | Comp 1's sale price ($172000) is quite far from the subject value ($240000). Please confirm this comparable is appropriate for the assignment. No supp… |
| **DOC-1** — License current at signature | 🟡 VERIFY | 🟡 manual-verify | `appraiser_cert_expiration_date`=2027-06-09@0.97; `date_of_signature`=∅ | The license expiration or signature date could not be read; please verify the license was current when the report was signed. |
| **SIG-4** — Appraiser email present | 🟡 VERIFY | 🟡 manual-verify | `appraiser_email`=∅ | The appraiser's email address is missing or unreadable. Please provide it. |
| **SIG-D** — Signature date >= effective date | 🟡 VERIFY | 🟡 manual-verify | `date_of_signature`=∅; `effective_date`=2026-06-22@0.97 | The signature date or effective date could not be read; please verify the signature date is on or after the effective date. |
| **ST-10** — Adverse site conditions addressed | 🟡 VERIFY | 🟠 extraction-gap | `adverse_site_conditions`=∅ | The adverse site conditions answer could not be extracted; manual review required. |
| **ST-8** — FEMA flood data complete; zone addressed | 🟡 VERIFY | 🟡 manual-verify | `fema_flood_hazard`=∅; `fema_flood_zone`=∅; `fema_map_date`=∅ | The flood zone information (zone, map number, and map date) must be completed in the site section — this is required even if the property is not in a … |
| **ST-9** — Utilities/off-site typical for market | 🟡 VERIFY | 🟡 manual-verify | `utilities_water`=Public@0.97; `utilities_sewer`=SEPTIC/TYPICAL@0.97 | Please confirm the utilities and off-site improvements are typical for the market area. If not, describe and comment on marketability. The appraiser's… |
| **S-4d** — Tax year current | 🟡 VERIFY | 🟡 manual-verify | `tax_year`=∅; `effective_date`=2026-06-22@0.97 | The tax year / effective date could not be extracted; please verify the tax year is within the last 2 years. |
| **S-6b** — Map reference numeric | 🟡 VERIFY | 🟠 extraction-gap | `map_reference`=∅ | Map Reference could not be extracted from the document; manual review required. |
| **ST-INTENDED** — Intended use and intended user stated | 🟡 VERIFY | 🟡 manual-verify | `addendum_text`=∅ | The report must state what the appraisal is for (mortgage lending) and who it is for (the lender/client). Please confirm both of these statements are … |
| **ST-SCOPE** — Scope of work stated | 🟡 VERIFY | 🟡 manual-verify | `addendum_text`=∅ | The scope of work description could not be found. Please verify the report describes what type of inspection was performed and what the appraiser did … |
| **ADD-5** — 1004MC inventory analysis complete | 🟢 PASS | — | `mca_total_sales_prior_7_12`=13@0.97; `mca_total_sales_prior_4_6`=8@0.97; `mca_total_sales_current_3`=2@0.97; `mca_absorption_rate_prior_7_12`=2.17@0.97 | Condition satisfied by the extracted value(s). |
| **ADD-X** — Addenda cross-reference resolution | 🟢 PASS | — | — | Condition satisfied by the extracted value(s). |
| **C-1** — Contract analyzed (purchase) / section blank (refinance) | 🟢 PASS | — | — | Condition satisfied by the extracted value(s). |
| **I-1** — General description complete | 🟢 PASS | — | `units_count`=1@0.97; `stories`=1.5@0.97; `dwelling_type`=Detached@0.97; `design_style`=Bungalow@0.97; `year_built`=1945@0.97; `effective_age`=30@0.97 | Condition satisfied by the extracted value(s). |
| **I-12** — Additions addressed | 🟢 PASS | — | — | Condition satisfied by the extracted value(s). |
| **I-2** — Foundation described | 🟢 PASS | — | `foundation_type`=CONC BLOCK/AVG@0.97 | Condition satisfied by the extracted value(s). |
| **I-7** — Above-grade room count present | 🟢 PASS | — | `total_rooms`=8@0.97; `bedrooms`=3@0.97; `baths`=2.0@0.97; `gla`=1934@0.97 | Condition satisfied by the extracted value(s). |
| **I-AGE** — Effective age does not exceed actual age | 🟢 PASS | — | `effective_age`=30@0.97; `year_built`=1945@0.97; `effective_date`=2026-06-22@0.97 | Condition satisfied by the extracted value(s). |
| **I-YRBUILT** — Year built consistent with actual age | 🟢 PASS | — | `year_built`=1945@0.97; `effective_date`=2026-06-22@0.97; `effective_age`=30@0.97 | Condition satisfied by the extracted value(s). |
| **IM-2** — Bedroom / total-room count consistency | 🟢 PASS | — | `total_rooms`=8@0.97; `bedrooms`=3@0.97 | Condition satisfied by the extracted value(s). |
| **N-1** — Neighborhood characteristics marked | 🟢 PASS | — | `location`=Rural@0.97 | Condition satisfied by the extracted value(s). |
| **N-1** — Neighborhood characteristics marked | 🟢 PASS | — | `built_up`=25To75Percent@0.97 | Condition satisfied by the extracted value(s). |
| **N-1** — Neighborhood characteristics marked | 🟢 PASS | — | `growth_rate`=Stable@0.97 | Condition satisfied by the extracted value(s). |
| **N-2** — Housing trends marked and consistent | 🟢 PASS | — | `property_values`=Stable@0.97 | Condition satisfied by the extracted value(s). |
| **N-2** — Housing trends marked and consistent | 🟢 PASS | — | `demand_supply`=Shortage@0.97 | Condition satisfied by the extracted value(s). |
| **N-2** — Housing trends marked and consistent | 🟢 PASS | — | `marketing_time`=UnderThreeMonths@0.97 | Condition satisfied by the extracted value(s). |
| **N-3** — Price/age ranges valid | 🟢 PASS | — | `price_low`=150@0.97; `price_high`=400@0.97 | Condition satisfied by the extracted value(s). |
| **N-3** — Price/age ranges valid | 🟢 PASS | — | `age_low`=30@0.97; `age_high`=145@0.97 | Condition satisfied by the extracted value(s). |
| **N-4** — Present land use sums to 100% | 🟢 PASS | — | `land_use_one_unit`=55@0.97; `land_use_2_4_unit`=5@0.97; `land_use_multi_family`=0@0.97; `land_use_commercial`=10@0.97; `land_use_other`=30@0.97 | Condition satisfied by the extracted value(s). |
| **N-4** — Present land use sums to 100% | 🟢 PASS | — | `land_use_other`=30@0.97 | Condition satisfied by the extracted value(s). |
| **N-5** — All four boundaries delineated | 🟢 PASS | — | `neighborhood_boundaries`=SOUTH OF LAKE ERIE, NORTH OF I 90, EAST OF WEST …@0.97 | Condition satisfied by the extracted value(s). |
| **CA-ARITH** — Cost approach arithmetic cross-check | 🟢 PASS | — | `site_value`=60000@0.97; `total_improvements_cost`=353539@0.97; `total_depreciation`=141416@0.97; `cost_approach_value`=297123@0.97 | Condition satisfied by the extracted value(s). |
| **R-2** — As-Is / Subject-To checked | 🟢 PASS | — | `appraisal_subject_to`=As Is@0.97 | Condition satisfied by the extracted value(s). |
| **R-VALUE-RANGE** — Final value within range of developed approach values | 🟢 PASS | — | `appraised_value`=240000@0.97; `final_value_sca`=240000@0.97; `cost_approach_value`=297123@0.97 | Condition satisfied by the extracted value(s). |
| **RECON-T** — Reconciliation forbidden terms | 🟢 PASS | — | `final_reconciliation_comment`=∅ | Condition satisfied by the extracted value(s). |
| **VAL-1** — Final opinion of value extraction integrity | 🟢 PASS | — | `appraised_value`=240000@0.97; `contract_price`=∅ | Condition satisfied by the extracted value(s). |
| **CG-COND-CONSIST** — Condition adjustment consistency across comps | 🟢 PASS | — | `comp_1_condition_adj`=-17500@0.97; `comp_2_condition_adj`=-17500@0.97; `comp_3_condition_adj`=-17500@0.97 | Condition satisfied by the extracted value(s). |
| **CG-DIST** — Comp distance threshold by area type | 🟢 PASS | — | `comp_1_proximity`=0.16 miles NE@0.97; `comp_2_proximity`=1.44 miles SE@0.97; `comp_3_proximity`=0.56 miles SW@0.97 | Condition satisfied by the extracted value(s). |
| **CG-GLA-BRACKET** — Subject GLA bracketed by comp GLAs | 🟢 PASS | — | `subject_grid_gla`=1934@0.97; `gla`=1934@0.97; `comp_1_gla`=1612@0.97; `comp_2_gla`=1520@0.97; `comp_3_gla`=2276@0.97 | Condition satisfied by the extracted value(s). |
| **CG-NET-BIAS** — Net adjustment directional bias | 🟢 PASS | — | `comp_1_net_adjustment`=20000@0.97; `comp_2_net_adjustment`=21750@0.97; `comp_3_net_adjustment`=-20750@0.97 | Condition satisfied by the extracted value(s). |
| **CG-PRIOR-SALE** — Comp prior sale rapid appreciation flag | 🟢 PASS | — | `comp_5_prior_sale_date`=04/21/2025@0.97; `comp_5_prior_sale_price`=119900@0.97; `comp_5_sale_price`=235000@0.97; `comp_5_sale_date`=s02/26;c01/26@0.97 | Condition satisfied by the extracted value(s). |
| **CG-TIME-CONSIST** — Time/market adjustment rate consistency | 🟢 PASS | — | `comp_2_financing_adj`=-6000@0.97; `comp_2_sale_date`=s12/25;c10/25@0.97; `comp_4_financing_adj`=-8680@0.97; `comp_4_sale_date`=s10/25;c09/25@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-11** — Comp site size has unit | 🟢 PASS | — | `comp_1_site_size`=1.00 ac@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-11** — Comp site size has unit | 🟢 PASS | — | `comp_2_site_size`=38768 sf@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-11** — Comp site size has unit | 🟢 PASS | — | `comp_3_site_size`=1.82 ac@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-11** — Comp site size has unit | 🟢 PASS | — | `comp_4_site_size`=33106 sf@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-11** — Comp site size has unit | 🟢 PASS | — | `comp_5_site_size`=1.60 ac@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-11** — Comp site size has unit | 🟢 PASS | — | `comp_6_site_size`=35719 sf@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-12** — Comp view UAD format | 🟢 PASS | — | `comp_1_view`=N;Res;@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-12** — Comp view UAD format | 🟢 PASS | — | `comp_2_view`=N;Res;@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-12** — Comp view UAD format | 🟢 PASS | — | `comp_3_view`=N;Res;@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-12** — Comp view UAD format | 🟢 PASS | — | `comp_4_view`=N;Res;@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-12** — Comp view UAD format | 🟢 PASS | — | `comp_5_view`=N;Res;@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-12** — Comp view UAD format | 🟢 PASS | — | `comp_6_view`=N;Res;@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-13** — Comp design present | 🟢 PASS | — | `comp_1_design`=DT1;Ranch@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-13** — Comp design present | 🟢 PASS | — | `comp_2_design`=DT2;Colonial@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-13** — Comp design present | 🟢 PASS | — | `comp_3_design`=DT1.5;Bungalow@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-13** — Comp design present | 🟢 PASS | — | `comp_4_design`=DT1.5;Bungalow@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-13** — Comp design present | 🟢 PASS | — | `comp_5_design`=DT1.5;Bungalow@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-13** — Comp design present | 🟢 PASS | — | `comp_6_design`=DT2;Colonial@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-14** — Comp quality UAD rating + zero-adj | 🟢 PASS | — | `comp_1_quality_rating`=Q4@0.97; `quality_rating`=∅; `comp_1_quality_rating_adjustment`=∅ | Condition satisfied by the extracted value(s). |
| **SCA-14** — Comp quality UAD rating + zero-adj | 🟢 PASS | — | `comp_2_quality_rating`=Q4@0.97; `quality_rating`=∅; `comp_2_quality_rating_adjustment`=∅ | Condition satisfied by the extracted value(s). |
| **SCA-14** — Comp quality UAD rating + zero-adj | 🟢 PASS | — | `comp_3_quality_rating`=Q4@0.97; `quality_rating`=∅; `comp_3_quality_rating_adjustment`=∅ | Condition satisfied by the extracted value(s). |
| **SCA-14** — Comp quality UAD rating + zero-adj | 🟢 PASS | — | `comp_4_quality_rating`=Q4@0.97; `quality_rating`=∅; `comp_4_quality_rating_adjustment`=∅ | Condition satisfied by the extracted value(s). |
| **SCA-14** — Comp quality UAD rating + zero-adj | 🟢 PASS | — | `comp_5_quality_rating`=Q4@0.97; `quality_rating`=∅; `comp_5_quality_rating_adjustment`=∅ | Condition satisfied by the extracted value(s). |
| **SCA-14** — Comp quality UAD rating + zero-adj | 🟢 PASS | — | `comp_6_quality_rating`=Q4@0.97; `quality_rating`=∅; `comp_6_quality_rating_adjustment`=∅ | Condition satisfied by the extracted value(s). |
| **SCA-15** — Subject actual age vs year built | 🟢 PASS | — | `subject_grid_actual_age`=∅; `year_built`=1945@0.97 | Year built (1945) implies age of 81 years — consistent with effective date. |
| **SCA-16** — Comp condition UAD rating + zero-adj | 🟢 PASS | — | `comp_1_condition_rating`=C3@0.97; `condition_rating`=∅; `comp_1_condition_rating_adjustment`=∅ | Condition satisfied by the extracted value(s). |
| **SCA-16** — Comp condition UAD rating + zero-adj | 🟢 PASS | — | `comp_2_condition_rating`=C3@0.97; `condition_rating`=∅; `comp_2_condition_rating_adjustment`=∅ | Condition satisfied by the extracted value(s). |
| **SCA-16** — Comp condition UAD rating + zero-adj | 🟢 PASS | — | `comp_3_condition_rating`=C3@0.97; `condition_rating`=∅; `comp_3_condition_rating_adjustment`=∅ | Condition satisfied by the extracted value(s). |
| **SCA-16** — Comp condition UAD rating + zero-adj | 🟢 PASS | — | `comp_4_condition_rating`=C4@0.97; `condition_rating`=∅; `comp_4_condition_rating_adjustment`=∅ | Condition satisfied by the extracted value(s). |
| **SCA-16** — Comp condition UAD rating + zero-adj | 🟢 PASS | — | `comp_5_condition_rating`=C3@0.97; `condition_rating`=∅; `comp_5_condition_rating_adjustment`=∅ | Condition satisfied by the extracted value(s). |
| **SCA-16** — Comp condition UAD rating + zero-adj | 🟢 PASS | — | `comp_6_condition_rating`=C4@0.97; `condition_rating`=∅; `comp_6_condition_rating_adjustment`=∅ | Condition satisfied by the extracted value(s). |
| **SCA-17** — Above-grade GLA matches grid, improvements & sketch | 🟢 PASS | — | `comp_1_gla`=1612@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-17** — Above-grade GLA matches grid, improvements & sketch | 🟢 PASS | — | `comp_2_gla`=1520@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-17** — Above-grade GLA matches grid, improvements & sketch | 🟢 PASS | — | `comp_3_gla`=2276@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-17** — Above-grade GLA matches grid, improvements & sketch | 🟢 PASS | — | `comp_4_gla`=1900@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-17** — Above-grade GLA matches grid, improvements & sketch | 🟢 PASS | — | `comp_5_gla`=1636@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-17** — Above-grade GLA matches grid, improvements & sketch | 🟢 PASS | — | `comp_6_gla`=2020@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-21** — Comp garage/carport present | 🟢 PASS | — | `comp_1_garage_carport`=2gd2dw@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-21** — Comp garage/carport present | 🟢 PASS | — | `comp_2_garage_carport`=1gd2dw@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-21** — Comp garage/carport present | 🟢 PASS | — | `comp_3_garage_carport`=2gd2dw@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-21** — Comp garage/carport present | 🟢 PASS | — | `comp_4_garage_carport`=2gd2dw@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-21** — Comp garage/carport present | 🟢 PASS | — | `comp_5_garage_carport`=2gd2dw@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-21** — Comp garage/carport present | 🟢 PASS | — | `comp_6_garage_carport`=2ga2dw@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-26** — Subject GLA bracketed by comps | 🟢 PASS | — | `gla`=1934@0.97; `comp_1_gla`=1612@0.97; `comp_2_gla`=1520@0.97; `comp_3_gla`=2276@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-3** — Comp address present | 🟢 PASS | — | `comp_1_address`=3906 Austin Rd, Geneva, OH@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-3** — Comp address present | 🟢 PASS | — | `comp_2_address`=4530 N Ridge Rd E, Geneva, OH@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-3** — Comp address present | 🟢 PASS | — | `comp_3_address`=5396 W Maple Rd, Geneva, OH@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-3** — Comp address present | 🟢 PASS | — | `comp_4_address`=470 3rd St, Geneva, OH@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-3** — Comp address present | 🟢 PASS | — | `comp_5_address`=3410 N Broadway, Geneva, OH@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-3** — Comp address present | 🟢 PASS | — | `comp_6_address`=1025 S Ridge Rd E, Geneva, OH@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-4** — Comp proximity present | 🟢 PASS | — | `comp_1_proximity`=0.16 miles NE@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-4** — Comp proximity present | 🟢 PASS | — | `comp_2_proximity`=1.44 miles SE@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-4** — Comp proximity present | 🟢 PASS | — | `comp_3_proximity`=0.56 miles SW@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-4** — Comp proximity present | 🟢 PASS | — | `comp_4_proximity`=1.37 miles SW@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-4** — Comp proximity present | 🟢 PASS | — | `comp_5_proximity`=0.83 miles SW@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-4** — Comp proximity present | 🟢 PASS | — | `comp_6_proximity`=2.10 miles S@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-5** — Comp data source present | 🟢 PASS | — | `comp_1_data_source`=MLS NOW # 5172067;DOM 3@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-5** — Comp data source present | 🟢 PASS | — | `comp_2_data_source`=MLS NOW # 5137507;DOM 149@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-5** — Comp data source present | 🟢 PASS | — | `comp_3_data_source`=MLS NOW # 5158048;DOM 42@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-5** — Comp data source present | 🟢 PASS | — | `comp_4_data_source`=MLS NOW # 5142599;DOM 76@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-5** — Comp data source present | 🟢 PASS | — | `comp_5_data_source`=MLS NOW # 5173422;DOM 62@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-5** — Comp data source present | 🟢 PASS | — | `comp_6_data_source`=MLS NOW # 5163356;DOM 112@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-6** — Comp verification source specific | 🟢 PASS | — | `comp_1_verification_source`=REALIST/INSPCTN/CNTY AUDITOR@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-6** — Comp verification source specific | 🟢 PASS | — | `comp_2_verification_source`=REALIST/INSPCTN/CNTY AUDITOR@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-6** — Comp verification source specific | 🟢 PASS | — | `comp_3_verification_source`=REALIST/INSPCTN/CNTY AUDITOR@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-6** — Comp verification source specific | 🟢 PASS | — | `comp_4_verification_source`=REALIST/INSPCTN/CNTY AUDITOR@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-6** — Comp verification source specific | 🟢 PASS | — | `comp_5_verification_source`=REALIST/INSPCTN/CNTY AUDITOR@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-6** — Comp verification source specific | 🟢 PASS | — | `comp_6_verification_source`=REALIST/INSPCTN/CNTY AUDITOR@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-8** — Comp date of sale sequencing | 🟢 PASS | — | `comp_1_sale_date`=s12/25;c11/25@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-8** — Comp date of sale sequencing | 🟢 PASS | — | `comp_2_sale_date`=s12/25;c10/25@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-8** — Comp date of sale sequencing | 🟢 PASS | — | `comp_3_sale_date`=s11/25;c10/25@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-8** — Comp date of sale sequencing | 🟢 PASS | — | `comp_4_sale_date`=s10/25;c09/25@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-8** — Comp date of sale sequencing | 🟢 PASS | — | `comp_5_sale_date`=s02/26;c01/26@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-8** — Comp date of sale sequencing | 🟢 PASS | — | `comp_6_sale_date`=s12/25;c11/25@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-9** — Comp location UAD format | 🟢 PASS | — | `comp_1_location_rating`=N;Res;@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-9** — Comp location UAD format | 🟢 PASS | — | `comp_2_location_rating`=A;Res;BsyRd@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-9** — Comp location UAD format | 🟢 PASS | — | `comp_3_location_rating`=N;Res;@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-9** — Comp location UAD format | 🟢 PASS | — | `comp_4_location_rating`=N;Res;@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-9** — Comp location UAD format | 🟢 PASS | — | `comp_5_location_rating`=A;Res;BsyRd@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-9** — Comp location UAD format | 🟢 PASS | — | `comp_6_location_rating`=A;Res;BsyRd@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-BR** — Value bracketed by adjusted prices | 🟢 PASS | — | `appraised_value`=240000@0.97; `comp_1_adjusted_sale_price`=192000@0.97; `comp_2_adjusted_sale_price`=222750@0.97; `comp_3_adjusted_sale_price`=264250@0.97; `comp_4_adjusted_sale_price`=224320@0.97; `comp_5_adjusted_sale_price`=245500@0.97; `comp_6_adjusted_sale_price`=246000@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-BR2** — Min comps with adjusted value at/above final opinion (lender overlay) | 🟢 PASS | — | `appraised_value`=240000@0.97; `comp_1_adjusted_sale_price`=192000@0.97; `comp_2_adjusted_sale_price`=222750@0.97; `comp_3_adjusted_sale_price`=264250@0.97; `comp_4_adjusted_sale_price`=224320@0.97; `comp_5_adjusted_sale_price`=245500@0.97; `comp_6_adjusted_sale_price`=246000@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-DC** — Comp sale within date currency window | 🟢 PASS | — | `comp_1_sale_date`=s12/25;c11/25@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-DC** — Comp sale within date currency window | 🟢 PASS | — | `comp_2_sale_date`=s12/25;c10/25@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-DC** — Comp sale within date currency window | 🟢 PASS | — | `comp_3_sale_date`=s11/25;c10/25@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-DC** — Comp sale within date currency window | 🟢 PASS | — | `comp_4_sale_date`=s10/25;c09/25@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-DC** — Comp sale within date currency window | 🟢 PASS | — | `comp_5_sale_date`=s02/26;c01/26@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-DC** — Comp sale within date currency window | 🟢 PASS | — | `comp_6_sale_date`=s12/25;c11/25@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-NET** — Net adjustment within 15% | 🟢 PASS | — | `comp_1_net_adjustment`=20000@0.97; `comp_2_net_adjustment`=21750@0.97; `comp_3_net_adjustment`=-20750@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-PR** — Comp sale price bracket vs subject value | 🟢 PASS | — | `comp_2_sale_price`=201000@0.97; `appraised_value`=240000@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-PR** — Comp sale price bracket vs subject value | 🟢 PASS | — | `comp_3_sale_price`=285000@0.97; `appraised_value`=240000@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-PR** — Comp sale price bracket vs subject value | 🟢 PASS | — | `comp_4_sale_price`=217000@0.97; `appraised_value`=240000@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-PR** — Comp sale price bracket vs subject value | 🟢 PASS | — | `comp_5_sale_price`=235000@0.97; `appraised_value`=240000@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-PR** — Comp sale price bracket vs subject value | 🟢 PASS | — | `comp_6_sale_price`=230000@0.97; `appraised_value`=240000@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-PSH** — Subject prior sale analyzed | 🟢 PASS | — | `subject_grid_prior_sale_date`=∅; `effective_date`=2026-06-22@0.97 | Condition satisfied by the extracted value(s). |
| **SIG-1** — Appraiser signed / name present | 🟢 PASS | — | `appraiser_name`=DARRYL E PETTREY@0.97; `date_of_signature`=∅ | Condition satisfied by the extracted value(s). |
| **SIG-3** — Appraiser licensed in property state | 🟢 PASS | — | `appraiser_license_state`=OH@0.97; `state`=OH@0.97 | Condition satisfied by the extracted value(s). |
| **ST-GEO-COMP** — Appraiser geographic competency | 🟢 PASS | — | `appraiser_license_state`=OH@0.97; `state`=OH@0.97 | Condition satisfied by the extracted value(s). |
| **ST-1** — Site dimensions provided | 🟢 PASS | — | `site_dimensions`=200 X 641 X 203 X 642@0.97 | Condition satisfied by the extracted value(s). |
| **ST-2** — Site area has correct unit | 🟢 PASS | — | `site_area`=2.94 ac@0.97; `site_area_unit`=∅ | Condition satisfied by the extracted value(s). |
| **ST-3** — Site shape provided | 🟢 PASS | — | `site_shape`=RECTANGULAR@0.97 | Condition satisfied by the extracted value(s). |
| **ST-4** — View UAD compliant and consistent | 🟢 PASS | — | `site_view`=N;Res;@0.97 | Condition satisfied by the extracted value(s). |
| **ST-5** — Zoning compliance | 🟢 PASS | — | `zoning_compliance`=Legal@0.97 | Condition satisfied by the extracted value(s). |
| **ST-6** — Highest & best use is Yes | 🟢 PASS | — | `highest_and_best_use`=Yes@0.97 | Condition satisfied by the extracted value(s). |
| **ST-7** — Utilities marked; private systems addressed | 🟢 PASS | — | `utilities_electricity`=Public@0.97; `utilities_gas`=Public@0.97 | Condition satisfied by the extracted value(s). |
| **ST-7** — Utilities marked; private systems addressed | 🟢 PASS | — | `utilities_water`=Public@0.97; `utilities_sewer`=SEPTIC/TYPICAL@0.97 | Condition satisfied by the extracted value(s). |
| **ST-HBU** — Highest and best use stated and consistent | 🟢 PASS | — | `highest_and_best_use`=Yes@0.97; `highest_best_use_indicator`=∅; `highest_best_use_description`=∅ | Condition satisfied by the extracted value(s). |
| **ST-RIGHTS** — Leasehold property rights disclosure | 🟢 PASS | — | `property_rights`=FeeSimple@0.97; `addendum_text`=∅ | Condition satisfied by the extracted value(s). |
| **I-HOA-PUD** — HOA/PUD consistency | 🟢 PASS | — | `hoa_dues`=∅; `is_pud`=∅ | Condition satisfied by the extracted value(s). |
| **S-11** — Property rights appraised present | 🟢 PASS | — | `property_rights`=FeeSimple@0.97 | Condition satisfied by the extracted value(s). |
| **S-4b** — APN present and plausible | 🟢 PASS | — | `assessors_parcel_number`=170160001600@0.97 | Condition satisfied by the extracted value(s). |
| **S-5** — Neighborhood name valid | 🟢 PASS | — | `neighborhood_name`=CONNECTICUT WESTERN RESERVE@0.97 | Condition satisfied by the extracted value(s). |
| **S-6** — Census tract format | 🟢 PASS | — | `census_tract`=0008.01@0.97 | Condition satisfied by the extracted value(s). |
| **S-7** — Occupancy status marked | 🟢 PASS | — | `occupant_status`=OwnerOccupied@0.97 | Condition satisfied by the extracted value(s). |
| **S-9** — HOA dues imply PUD marked | 🟢 PASS | — | `hoa_dues`=∅; `is_pud_checked`=∅ | Condition satisfied by the extracted value(s). |
| **ST-FORM-MATCH** — Form type matches property type | 🟢 PASS | — | `design_style`=Bungalow@0.97 | Condition satisfied by the extracted value(s). |
| **ADD-2** — Comparable selection commentary explains why | ⚪ N/A | — | — | No substantive sales-comparison narrative extracted. |
| **ADD-4** — 1004MC required for FHA/USDA | ⚪ N/A | — | — | Not applicable to this loan/transaction/form type. |
| **ADD-8** — 1004MC condo project section complete | ⚪ N/A | — | — | Not applicable to this loan/transaction/form type. |
| **C-2a** — Contract price matches purchase agreement | ⚪ N/A | — | — | Not applicable to this loan/transaction/form type. |
| **C-2b** — Contract date matches purchase agreement | ⚪ N/A | — | — | Not applicable to this loan/transaction/form type. |
| **C-3** — Owner-of-record data source present | ⚪ N/A | — | — | Not applicable to this loan/transaction/form type. |
| **C-4** — Concessions consistent and match purchase agreement | ⚪ N/A | — | — | Not applicable to this loan/transaction/form type. |
| **C-5** — Personal property addressed | ⚪ N/A | — | — | Not applicable to this loan/transaction/form type. |
| **C-BUYER-MATCH** — Buyer names match borrower(s) on order | ⚪ N/A | — | — | Not applicable to this loan/transaction/form type. |
| **C-EXEC** — Contract fully executed by all parties | ⚪ N/A | — | — | Not applicable to this loan/transaction/form type. |
| **C-PKG-EXEC** — Contract fully executed (manual verification) | ⚪ N/A | — | — | Not applicable to this loan/transaction/form type. |
| **ORD-ASSIGN-MATCH** — Assignment type in engagement letter matches appraisal report | ⚪ N/A | — | — | Not applicable to this loan/transaction/form type. |
| **ORD-EXEC-STOP** — Unsigned contract blocked by engagement letter policy | ⚪ N/A | — | — | Not applicable to this loan/transaction/form type. |
| **TL-CONTRACT** — Contract date precedes appraisal effective date | ⚪ N/A | — | — | Not applicable to this loan/transaction/form type. |
| **CA-2** — Remaining economic life >= 30 (FHA/VA) | ⚪ N/A | — | — | Not applicable to this loan/transaction/form type. |
| **FHA-1** — FHA Minimum Property Requirements confirmed | ⚪ N/A | — | — | Not applicable to this loan/transaction/form type. |
| **FHA-10** — FHA remaining economic life >= 30 | ⚪ N/A | — | — | Not applicable to this loan/transaction/form type. |
| **FHA-12** — FHA well/septic compliance | ⚪ N/A | — | — | Not applicable to this loan/transaction/form type. |
| **FHA-13** — FHA appliances present/operational | ⚪ N/A | — | — | Not applicable to this loan/transaction/form type. |
| **FHA-2** — FHA case number format + match | ⚪ N/A | — | — | Not applicable to this loan/transaction/form type. |
| **FHA-3** — FHA intended use/user statements | ⚪ N/A | — | — | Not applicable to this loan/transaction/form type. |
| **FHA-4** — FHA/HUD certification statement present | ⚪ N/A | — | — | Not applicable to this loan/transaction/form type. |
| **FHA-5** — FHA primary comps within 12 months | ⚪ N/A | — | — | Not applicable to this loan/transaction/form type. |
| **FHA-6** — FHA repairs reported subject-to | ⚪ N/A | — | — | Not applicable to this loan/transaction/form type. |
| **FHA-7** — FHA space heater not primary heat | ⚪ N/A | — | — | Not applicable to this loan/transaction/form type. |
| **FHA-9** — FHA four-side photos | ⚪ N/A | — | — | Not applicable to this loan/transaction/form type. |
| **G-1** — Loan-type consistency (engagement vs appraisal) | ⚪ N/A | — | `loan_type`=∅; `fha_case_number`=∅ | Engagement letter / order form not available. |
| **G-C56** — C5/C6 condition triggers AMC stop | ⚪ N/A | — | — | Not applicable to this loan/transaction/form type. |
| **G-LAVA** — Hawaiian lava zone triggers AMC stop | ⚪ N/A | — | — | Not applicable to this loan/transaction/form type. |
| **G-MFG** — Pre-1976 manufactured home triggers AMC stop | ⚪ N/A | — | — | Not applicable to this loan/transaction/form type. |
| **ORD-CONFLICT** — Engagement letter and XML disagree on order-level facts | ⚪ N/A | — | — | Not applicable to this loan/transaction/form type. |
| **IA-1** — Income approach rent matches rent schedule | ⚪ N/A | — | — | Income approach / rent schedule not developed. |
| **MF-1** — Multi-family requires income approach | ⚪ N/A | — | — | Not applicable to this loan/transaction/form type. |
| **R-INCOME-REQ** — Income approach developed when required | ⚪ N/A | — | `income_approach_value`=0@0.97; `occupancy_type`=OwnerOccupied@0.97 | Income approach not required for this occupancy type. |
| **R-2b** — Value equals contract price (bias advisory) | ⚪ N/A | — | — | Not applicable to this loan/transaction/form type. |
| **CG-CONC-DIR** — Concession adjustment wrong direction | ⚪ N/A | — | — | No seller concessions noted across comparables; concession-direction check not applicable. |
| **CG-NONARMS** — Non-arms-length comp without commentary | ⚪ N/A | — | — | No non-arms-length distress indicators found in comparables. |
| **SCA-23** — Listing comp adjustment | ⚪ N/A | — | — | no listing/active comparables |
| **SCA-25** — New construction competing comp | ⚪ N/A | — | — | subject is not new construction |
| **SCA-PSH-Q** — Subject sale history analysis is substantive | ⚪ N/A | — | — | No prior sale/transfer within the look-back window; quality check not applicable. |
| **ORD-ENG-DATE** — Engagement letter predates appraisal report | ⚪ N/A | — | — | Not applicable to this loan/transaction/form type. |
| **SIG-2** — Appraiser name matches engagement | ⚪ N/A | — | — | Not applicable to this loan/transaction/form type. |
| **SIG-SUP** — Supervisory appraiser section complete | ⚪ N/A | — | — | Not applicable to this loan/transaction/form type. |
| **SIG-TRAINEE** — Trainee appraiser requires supervisory cosign | ⚪ N/A | — | `appraiser_license_type`=Certificate@0.97; `supervisory_appraiser_name`=∅; `supervisory_appraiser_cert_number`=∅ | Rule does not apply to this loan/form/transaction type. |
| **ST-PRIOR-SVC** — Prior services disclosure | ⚪ N/A | — | `prior_services_indicator`=∅; `prior_services_description`=∅; `addendum_text`=∅ | Rule does not apply to this loan/form/transaction type. |
| **TL-ENG** — Engagement letter date precedes report signature date | ⚪ N/A | — | — | Not applicable to this loan/transaction/form type. |
| **ST-1B** — Site area magnitude plausibility (multi-signal) | ⚪ N/A | — | `site_area`=2.94 ac@0.97; `site_area_unit`=∅ | Rule does not apply to this loan/form/transaction type. |
| **ST-FLOOD-CMT** — Flood zone present — marketability commentary required | ⚪ N/A | — | — | Not applicable to this loan/transaction/form type. |
| **ST-ZONE-NC** — Zoning non-conformance commentary | ⚪ N/A | — | `zoning_compliance`=Legal@0.97; `addendum_text`=∅ | Rule does not apply to this loan/form/transaction type. |
| **LISTING-CMNT** — Listing price vs appraised value commentary | ⚪ N/A | — | — | Not applicable to this loan/transaction/form type. |
| **ORD-COBORROWER** — Co-borrower from order appears in appraisal borrower field | ⚪ N/A | — | — | Not applicable to this loan/transaction/form type. |
| **ORD-FORM-MATCH** — Form type in report matches form type ordered | ⚪ N/A | — | — | Not applicable to this loan/transaction/form type. |
| **ORD-INSP-SCOPE** — Ordered inspection type matches report scope of work | ⚪ N/A | — | — | Not applicable to this loan/transaction/form type. |
| **S-1** — Property address matches order form | ⚪ N/A | — | `property_address`=3825 Austin Rd@0.97 | Engagement letter / order form not available. |
| **S-1** — Property address matches order form | ⚪ N/A | — | `city`=Geneva@0.97 | Engagement letter / order form not available. |
| **S-1** — Property address matches order form | ⚪ N/A | — | `zip_code`=44041@0.97 | Engagement letter / order form not available. |
| **S-10a** — Lender name matches order form | ⚪ N/A | — | `lender_name`=UNITED WHOLESALE MORTGAGE ISAOA, ATIMA@0.97 | Engagement letter / order form not available. |
| **S-10b** — Lender address matches order form | ⚪ N/A | — | — | Engagement letter / order form not available. |
| **S-2** — Borrower matches order form | ⚪ N/A | — | — | Engagement letter / order form not available. |
| **USDA-1** — USDA cost approach required | ⚪ N/A | — | — | Not applicable to this loan/transaction/form type. |


---

## dir 7 — 12619 Provincetowne Dr.xml

| Rule | Status | Bucket | Extracted (what the rule read) | How it was judged |
|------|--------|--------|-------------------------------|-------------------|
| **SUBJECT-HOLD** — subject | 🔴 FAIL | 🔴 hard-fail | — | 5 failures in the subject section indicate systematic problems (not isolated errors); the section is escalated for a full manual review. |
| **G-0** — Engagement letter / order form present and extracted | 🔴 FAIL | 🟠 extraction-gap | `loan_type`=∅ | The engagement letter / order form was not extracted. All lender-overlay rules (comp count minimum, site value requirement, declining-market clause, A… |
| **S-12** — Prior-listing data source present | 🔴 FAIL | 🔴 hard-fail | `offered_for_sale_12mo`=∅; `data_source`=∅ | The checkbox about prior sale or listing activity in the past 12 months is missing a data source. Please provide the source used to answer this questi… |
| **S-3** — Owner of public record present | 🔴 FAIL | 🔴 hard-fail | `owner_of_public_record`=∅; `legal_description`=∅; `real_estate_taxes`=∅; `special_assessments`=∅ | The 'Owner of Public Record' field is blank. Please complete it. |
| **ADD-9** — USPAP addendum complete | 🟡 VERIFY | 🟠 extraction-gap | — | The USPAP addendum fields (report type, reasonable exposure time, prior services) could not be extracted; manual review required. |
| **C-ANALYZE** — Contract analysis indicator consistency | 🟡 VERIFY | 🟠 extraction-gap | `contract_analyzed`=∅ | The contract_analyzed indicator could not be extracted; rule cannot evaluate — manual review required. |
| **CA-1** — Opinion of site value present | 🟡 VERIFY | 🟡 manual-verify | `site_value_estimate`=∅ | The cost approach is missing an opinion of site value. Please provide one. |
| **I-11** — Conforms to neighborhood | 🟡 VERIFY | 🟠 extraction-gap | `conforms_to_neighborhood`=∅ | Conformity to the neighborhood could not be read; please verify the improvements conform. |
| **I-34** — Materials/condition described | 🟡 VERIFY | 🟡 manual-verify | `exterior_walls`=∅; `roof_surface`=∅; `heating`=∅; `floor_material`=∅; `walls_material`=∅; `trim_finish_material`=∅ | The following materials/condition fields are missing in the improvements section: Exterior Walls, Roof Surface, Heating, Floors, Walls, Trim/Finish. P… |
| **I-5** — Heating and cooling described | 🟡 VERIFY | 🟡 manual-verify | `heating`=∅; `cooling`=∅ | The following heating/cooling fields are not described in the improvements section: Heating, Cooling. Please complete. |
| **I-6** — Appliances reported | 🟡 VERIFY | 🟡 manual-verify | `appliance_refrigerator`=∅; `appliance_range_oven`=∅; `appliance_disposal`=∅; `appliance_dishwasher`=∅; `appliance_microwave`=∅; `appliance_washer_dryer`=∅ | No kitchen appliances are listed in the improvements section. Please note which appliances are present. |
| **I-8** — Additional features described | 🟡 VERIFY | 🟡 manual-verify | `fireplace_count`=∅; `porch_patio_deck`=∅; `additional_features`=∅ | Please confirm any additional features (fireplace, porch/patio/deck, pool, etc.) are described in the improvements section, or state 'None'. |
| **I-9** — Condition rating UAD and consistent | 🟡 VERIFY | 🟠 extraction-gap | `condition_rating`=∅ | Condition could not be extracted from the document; manual review required. |
| **I-Q** — Quality rating UAD format | 🟡 VERIFY | 🟠 extraction-gap | `quality_rating`=∅ | Quality could not be extracted from the document; manual review required. |
| **I-SMCO** — Smoke/CO detector code compliance noted | 🟡 VERIFY | 🟡 manual-verify | `sales_comparison_summary`=∅ | No mention of smoke or CO detectors was found in the report. The client requires a note confirming detectors meet local code — please add one to the r… |
| **N-6** — Neighborhood description specific | 🟡 VERIFY | 🟡 manual-verify | `neighborhood_description`=No adverse neighborhood factors were noted. The …@0.97 | The Neighborhood Description reads like a generic template. Please add specific details — like nearby streets, local landmarks, proximity to schools o… |
| **PH-1** — Subject front/rear/street photos | 🟡 VERIFY | 🟡 manual-verify | `photo_front`=∅; `photo_rear`=∅; `photo_street`=∅ | Required photos are missing: front, rear, street scene. At minimum, please include a front photo, a rear photo, and a street scene. |
| **PH-2** — Interior photos present | 🟡 VERIFY | 🟡 manual-verify | `photo_interior_rooms`=∅ | Interior photos are incomplete — missing: kitchen, living, bedroom, bathroom. Please include photos of the kitchen, living room, all bedrooms, and all… |
| **CA-ARITH** — Cost approach arithmetic cross-check | 🟡 VERIFY | 🟡 manual-verify | `site_value`=125000@0.97; `total_improvements_cost`=∅; `total_depreciation`=∅; `cost_approach_value`=0@0.97 | Cost approach arithmetic cannot be evaluated; the following field(s) could not be extracted: total_improvements_cost, total_depreciation — manual revi… |
| **R-1** — SCA value matches market value | 🟡 VERIFY | 🟡 manual-verify | `indicated_value_sca`=∅; `appraised_value`=815000@0.97 | The sales comparison value or final opinion of value could not be read. Please verify both numbers are present and agree. |
| **R-1b** — Reconciliation names the weighted approach | 🟡 VERIFY | 🟡 manual-verify | `final_reconciliation_comment`=∅ | The reconciliation must say which approach was relied on most (sales comparison, cost, or income) and briefly explain why. Please add that statement t… |
| **R-ASSIGN-COND** — Assignment condition vs report language consistency | 🟡 VERIFY | 🟡 manual-verify | `assignment_condition`=AsIs@0.97; `addendum_text`=∅; `limiting_conditions_text`=∅ | The assignment condition box (AsIs) doesn't match the language used in the report narrative. Please make sure the box and the written description agre… |
| **R-EXPOSURE** — Exposure time stated as a specific period | 🟡 VERIFY | 🟡 manual-verify | `addendum_text`=∅; `final_reconciliation_comment`=∅ | No specific exposure time period was found. Please add a statement like 'estimated exposure time of 3-6 months' in the reconciliation or addendum. |
| **R-MKTTIME** — Marketing time consistent with neighborhood data | 🟡 VERIFY | 🟡 manual-verify | `marketing_time_typical`=UnderThreeMonths@0.97; `addendum_text`=∅ | The marketing time stated in the report appears inconsistent with the market data for this area. Please make sure the estimated selling time matches w… |
| **CG-NET-BIAS** — Net adjustment directional bias | 🟡 VERIFY | 🔵 advisory | `comp_1_net_adjustment`=11300@0.97; `comp_2_net_adjustment`=43600@0.97; `comp_3_net_adjustment`=11660@0.97 | CG-net-bias No supporting explanation for the selection of this comparable was found in the report narrative (all 6 comparable net adjustments are pos… |
| **CG-TIME-CONSIST** — Time/market adjustment rate consistency | 🟡 VERIFY | 🟠 extraction-gap | — | Fewer than 2 comps with measurable time adjustments; rate consistency check skipped — manual review required. |
| **SCA-10** — Comp property rights present + consistent | 🟡 VERIFY | 🟡 manual-verify | `comp_1_leasehold`=∅ | Please indicate the property rights (Fee Simple or Leasehold) for Comp 1 in the sales grid. |
| **SCA-10** — Comp property rights present + consistent | 🟡 VERIFY | 🟡 manual-verify | `comp_2_leasehold`=∅ | Please indicate the property rights (Fee Simple or Leasehold) for Comp 2 in the sales grid. |
| **SCA-10** — Comp property rights present + consistent | 🟡 VERIFY | 🟡 manual-verify | `comp_3_leasehold`=∅ | Please indicate the property rights (Fee Simple or Leasehold) for Comp 3 in the sales grid. |
| **SCA-10** — Comp property rights present + consistent | 🟡 VERIFY | 🟡 manual-verify | `comp_4_leasehold`=∅ | Please indicate the property rights (Fee Simple or Leasehold) for Comp 4 in the sales grid. |
| **SCA-10** — Comp property rights present + consistent | 🟡 VERIFY | 🟡 manual-verify | `comp_5_leasehold`=∅ | Please indicate the property rights (Fee Simple or Leasehold) for Comp 5 in the sales grid. |
| **SCA-10** — Comp property rights present + consistent | 🟡 VERIFY | 🟡 manual-verify | `comp_6_leasehold`=∅ | Please indicate the property rights (Fee Simple or Leasehold) for Comp 6 in the sales grid. |
| **SCA-16V** — Comp photo condition cross-check | 🟡 VERIFY | 🟠 extraction-gap | — | Please open the report and visually confirm that the front photo matches the subject property address. Automated photo review is not available for thi… |
| **SCA-17** — Above-grade GLA matches grid, improvements & sketch | 🟡 VERIFY | 🟡 manual-verify | `subject_grid_gla`=2987@0.97; `gla`=2987@0.97; `sketch_living_area`=∅ | The living area couldn't be confirmed across all sources (SCA grid 2987, improvements 2987, sketch n/a sf). Please verify the GLA in the sales grid ma… |
| **SCA-18** — Comp basement present | 🟡 VERIFY | 🟡 manual-verify | `comp_1_basement`=∅ | Basement and below-grade rooms are missing for Comp 1. Please fill this in (finished sq ft and room count, or 'None' if there is none). |
| **SCA-18** — Comp basement present | 🟡 VERIFY | 🟡 manual-verify | `comp_2_basement`=∅ | Basement and below-grade rooms are missing for Comp 2. Please fill this in (finished sq ft and room count, or 'None' if there is none). |
| **SCA-18** — Comp basement present | 🟡 VERIFY | 🟡 manual-verify | `comp_3_basement`=∅ | Basement and below-grade rooms are missing for Comp 3. Please fill this in (finished sq ft and room count, or 'None' if there is none). |
| **SCA-18** — Comp basement present | 🟡 VERIFY | 🟡 manual-verify | `comp_4_basement`=∅ | Basement and below-grade rooms are missing for Comp 4. Please fill this in (finished sq ft and room count, or 'None' if there is none). |
| **SCA-18** — Comp basement present | 🟡 VERIFY | 🟡 manual-verify | `comp_5_basement`=∅ | Basement and below-grade rooms are missing for Comp 5. Please fill this in (finished sq ft and room count, or 'None' if there is none). |
| **SCA-18** — Comp basement present | 🟡 VERIFY | 🟡 manual-verify | `comp_6_basement`=∅ | Basement and below-grade rooms are missing for Comp 6. Please fill this in (finished sq ft and room count, or 'None' if there is none). |
| **SCA-19** — Comp functional utility present | 🟡 VERIFY | 🟡 manual-verify | `comp_1_functional_utility`=∅ | Please add functional utility for Comp 1 in the sales grid. |
| **SCA-19** — Comp functional utility present | 🟡 VERIFY | 🟡 manual-verify | `comp_2_functional_utility`=∅ | Please add functional utility for Comp 2 in the sales grid. |
| **SCA-19** — Comp functional utility present | 🟡 VERIFY | 🟡 manual-verify | `comp_3_functional_utility`=∅ | Please add functional utility for Comp 3 in the sales grid. |
| **SCA-19** — Comp functional utility present | 🟡 VERIFY | 🟡 manual-verify | `comp_4_functional_utility`=∅ | Please add functional utility for Comp 4 in the sales grid. |
| **SCA-19** — Comp functional utility present | 🟡 VERIFY | 🟡 manual-verify | `comp_5_functional_utility`=∅ | Please add functional utility for Comp 5 in the sales grid. |
| **SCA-19** — Comp functional utility present | 🟡 VERIFY | 🟡 manual-verify | `comp_6_functional_utility`=∅ | Please add functional utility for Comp 6 in the sales grid. |
| **SCA-2** — Minimum comparable sales | 🟡 VERIFY | 🟡 manual-verify | `comp_1_sale_price`=790000@0.97; `comp_2_sale_price`=785000@0.97; `comp_3_sale_price`=820000@0.97 | Comp 5 appear to be closed sales in the grid, but the settlement date or MLS status is missing or shows active/pending — Comp 5: settlement date blank… |
| **SCA-20** — Comp heating/cooling present | 🟡 VERIFY | 🟡 manual-verify | `comp_1_heating_cooling`=∅ | Please add the heating/cooling information for Comp 1 in the sales grid. |
| **SCA-20** — Comp heating/cooling present | 🟡 VERIFY | 🟡 manual-verify | `comp_2_heating_cooling`=∅ | Please add the heating/cooling information for Comp 2 in the sales grid. |
| **SCA-20** — Comp heating/cooling present | 🟡 VERIFY | 🟡 manual-verify | `comp_3_heating_cooling`=∅ | Please add the heating/cooling information for Comp 3 in the sales grid. |
| **SCA-20** — Comp heating/cooling present | 🟡 VERIFY | 🟡 manual-verify | `comp_4_heating_cooling`=∅ | Please add the heating/cooling information for Comp 4 in the sales grid. |
| **SCA-20** — Comp heating/cooling present | 🟡 VERIFY | 🟡 manual-verify | `comp_5_heating_cooling`=∅ | Please add the heating/cooling information for Comp 5 in the sales grid. |
| **SCA-20** — Comp heating/cooling present | 🟡 VERIFY | 🟡 manual-verify | `comp_6_heating_cooling`=∅ | Please add the heating/cooling information for Comp 6 in the sales grid. |
| **SCA-22** — Comp porch/patio/deck present | 🟡 VERIFY | 🟡 manual-verify | `comp_1_porch_patio_deck`=∅ | Please add the porch, patio, or deck information for Comp 1 in the sales grid. |
| **SCA-22** — Comp porch/patio/deck present | 🟡 VERIFY | 🟡 manual-verify | `comp_2_porch_patio_deck`=∅ | Please add the porch, patio, or deck information for Comp 2 in the sales grid. |
| **SCA-22** — Comp porch/patio/deck present | 🟡 VERIFY | 🟡 manual-verify | `comp_3_porch_patio_deck`=∅ | Please add the porch, patio, or deck information for Comp 3 in the sales grid. |
| **SCA-22** — Comp porch/patio/deck present | 🟡 VERIFY | 🟡 manual-verify | `comp_4_porch_patio_deck`=∅ | Please add the porch, patio, or deck information for Comp 4 in the sales grid. |
| **SCA-22** — Comp porch/patio/deck present | 🟡 VERIFY | 🟡 manual-verify | `comp_5_porch_patio_deck`=∅ | Please add the porch, patio, or deck information for Comp 5 in the sales grid. |
| **SCA-22** — Comp porch/patio/deck present | 🟡 VERIFY | 🟡 manual-verify | `comp_6_porch_patio_deck`=∅ | Please add the porch, patio, or deck information for Comp 6 in the sales grid. |
| **SCA-27** — Comparable photos present + type | 🟡 VERIFY | 🟡 manual-verify | `comp_photo_pages`=∅ | Photo check required — verify that comparable sale photos are present and match the correct properties. |
| **DOC-1** — License current at signature | 🟡 VERIFY | 🟡 manual-verify | `appraiser_cert_expiration_date`=2027-06-30@0.97; `date_of_signature`=∅ | The license expiration or signature date could not be read; please verify the license was current when the report was signed. |
| **SIG-4** — Appraiser email present | 🟡 VERIFY | 🟡 manual-verify | `appraiser_email`=∅ | The appraiser's email address is missing or unreadable. Please provide it. |
| **SIG-D** — Signature date >= effective date | 🟡 VERIFY | 🟡 manual-verify | `date_of_signature`=∅; `effective_date`=2026-06-30@0.97 | The signature date or effective date could not be read; please verify the signature date is on or after the effective date. |
| **ST-10** — Adverse site conditions addressed | 🟡 VERIFY | 🟠 extraction-gap | `adverse_site_conditions`=∅ | The adverse site conditions answer could not be extracted; manual review required. |
| **ST-8** — FEMA flood data complete; zone addressed | 🟡 VERIFY | 🟡 manual-verify | `fema_flood_hazard`=∅; `fema_flood_zone`=∅; `fema_map_date`=∅ | The flood zone information (zone, map number, and map date) must be completed in the site section — this is required even if the property is not in a … |
| **S-4d** — Tax year current | 🟡 VERIFY | 🟡 manual-verify | `tax_year`=∅; `effective_date`=2026-06-30@0.97 | The tax year / effective date could not be extracted; please verify the tax year is within the last 2 years. |
| **S-6b** — Map reference numeric | 🟡 VERIFY | 🟠 extraction-gap | `map_reference`=∅ | Map Reference could not be extracted from the document; manual review required. |
| **ST-INTENDED** — Intended use and intended user stated | 🟡 VERIFY | 🟡 manual-verify | `addendum_text`=∅ | The report must state what the appraisal is for (mortgage lending) and who it is for (the lender/client). Please confirm both of these statements are … |
| **ST-SCOPE** — Scope of work stated | 🟡 VERIFY | 🟡 manual-verify | `addendum_text`=∅ | The scope of work description could not be found. Please verify the report describes what type of inspection was performed and what the appraiser did … |
| **ADD-5** — 1004MC inventory analysis complete | 🟢 PASS | — | `mca_total_sales_prior_7_12`=16@0.97; `mca_total_sales_prior_4_6`=4@0.97; `mca_total_sales_current_3`=7@0.97; `mca_absorption_rate_prior_7_12`=2.67@0.97 | Condition satisfied by the extracted value(s). |
| **ADD-X** — Addenda cross-reference resolution | 🟢 PASS | — | — | Condition satisfied by the extracted value(s). |
| **C-1** — Contract analyzed (purchase) / section blank (refinance) | 🟢 PASS | — | — | Condition satisfied by the extracted value(s). |
| **I-1** — General description complete | 🟢 PASS | — | `units_count`=1@0.97; `stories`=2@0.97; `dwelling_type`=Detached@0.97; `design_style`=Traditional@0.97; `year_built`=2002@0.97; `effective_age`=10@0.97 | Condition satisfied by the extracted value(s). |
| **I-10** — Adverse livability conditions addressed | 🟢 PASS | — | `adverse_conditions`=No@0.97 | Condition satisfied by the extracted value(s). |
| **I-12** — Additions addressed | 🟢 PASS | — | — | Condition satisfied by the extracted value(s). |
| **I-2** — Foundation described | 🟢 PASS | — | `foundation_type`=Concrete,Avg@0.97 | Condition satisfied by the extracted value(s). |
| **I-7** — Above-grade room count present | 🟢 PASS | — | `total_rooms`=10@0.97; `bedrooms`=5@0.97; `baths`=3.1@0.97; `gla`=2987@0.97 | Condition satisfied by the extracted value(s). |
| **I-AGE** — Effective age does not exceed actual age | 🟢 PASS | — | `effective_age`=10@0.97; `year_built`=2002@0.97; `effective_date`=2026-06-30@0.97 | Condition satisfied by the extracted value(s). |
| **I-YRBUILT** — Year built consistent with actual age | 🟢 PASS | — | `year_built`=2002@0.97; `effective_date`=2026-06-30@0.97; `effective_age`=10@0.97 | Condition satisfied by the extracted value(s). |
| **IM-2** — Bedroom / total-room count consistency | 🟢 PASS | — | `total_rooms`=10@0.97; `bedrooms`=5@0.97 | Condition satisfied by the extracted value(s). |
| **N-1** — Neighborhood characteristics marked | 🟢 PASS | — | `location`=Suburban@0.97 | Condition satisfied by the extracted value(s). |
| **N-1** — Neighborhood characteristics marked | 🟢 PASS | — | `built_up`=Over75Percent@0.97 | Condition satisfied by the extracted value(s). |
| **N-1** — Neighborhood characteristics marked | 🟢 PASS | — | `growth_rate`=Stable@0.97 | Condition satisfied by the extracted value(s). |
| **N-2** — Housing trends marked and consistent | 🟢 PASS | — | `property_values`=Stable@0.97 | Condition satisfied by the extracted value(s). |
| **N-2** — Housing trends marked and consistent | 🟢 PASS | — | `demand_supply`=InBalance@0.97 | Condition satisfied by the extracted value(s). |
| **N-2** — Housing trends marked and consistent | 🟢 PASS | — | `marketing_time`=UnderThreeMonths@0.97 | Condition satisfied by the extracted value(s). |
| **N-3** — Price/age ranges valid | 🟢 PASS | — | `price_low`=520@0.97; `price_high`=820@0.97 | Condition satisfied by the extracted value(s). |
| **N-3** — Price/age ranges valid | 🟢 PASS | — | `age_low`=7@0.97; `age_high`=35@0.97 | Condition satisfied by the extracted value(s). |
| **N-3** — Price/age ranges valid | 🟢 PASS | — | `price_low`=520@0.97; `price_high`=820@0.97 | Condition satisfied by the extracted value(s). |
| **N-4** — Present land use sums to 100% | 🟢 PASS | — | `land_use_one_unit`=70@0.97; `land_use_2_4_unit`=5@0.97; `land_use_multi_family`=5@0.97; `land_use_commercial`=10@0.97; `land_use_other`=10@0.97 | Condition satisfied by the extracted value(s). |
| **N-4** — Present land use sums to 100% | 🟢 PASS | — | `land_use_other`=10@0.97 | Condition satisfied by the extracted value(s). |
| **N-5** — All four boundaries delineated | 🟢 PASS | — | `neighborhood_boundaries`=The neighborhood is boundaried by Route 16 to th…@0.97 | Condition satisfied by the extracted value(s). |
| **N-7** — Market conditions completed | 🟢 PASS | — | `market_conditions_commentary`=The current market appears to be active with sta…@0.97 | Condition satisfied by the extracted value(s). |
| **R-2** — As-Is / Subject-To checked | 🟢 PASS | — | `appraisal_subject_to`=As Is@0.97 | Condition satisfied by the extracted value(s). |
| **RECON-T** — Reconciliation forbidden terms | 🟢 PASS | — | `final_reconciliation_comment`=∅ | Condition satisfied by the extracted value(s). |
| **VAL-1** — Final opinion of value extraction integrity | 🟢 PASS | — | `appraised_value`=815000@0.97; `contract_price`=∅ | Condition satisfied by the extracted value(s). |
| **CG-CONC-DIR** — Concession adjustment wrong direction | 🟢 PASS | — | `comp_5_sale_price`=874900@0.97; `comp_5_concessions`=Listing@0.97; `comp_5_financing_adj`=∅ | Condition satisfied by the extracted value(s). |
| **CG-CONC-DIR** — Concession adjustment wrong direction | 🟢 PASS | — | `comp_6_sale_price`=849000@0.97; `comp_6_concessions`=Listing@0.97; `comp_6_financing_adj`=∅ | Condition satisfied by the extracted value(s). |
| **CG-COND-CONSIST** — Condition adjustment consistency across comps | 🟢 PASS | — | `comp_1_condition_adj`=∅; `comp_2_condition_adj`=∅; `comp_3_condition_adj`=∅ | Condition satisfied by the extracted value(s). |
| **CG-DIST** — Comp distance threshold by area type | 🟢 PASS | — | `comp_1_proximity`=0.85 miles NW@0.97; `comp_2_proximity`=0.43 miles NW@0.97; `comp_3_proximity`=0.47 miles S@0.97 | Condition satisfied by the extracted value(s). |
| **CG-GLA-BRACKET** — Subject GLA bracketed by comp GLAs | 🟢 PASS | — | `subject_grid_gla`=2987@0.97; `gla`=2987@0.97; `comp_1_gla`=3300@0.97; `comp_2_gla`=2575@0.97; `comp_3_gla`=2621@0.97 | Condition satisfied by the extracted value(s). |
| **CG-PRIOR-SALE** — Comp prior sale rapid appreciation flag | 🟢 PASS | — | `comp_1_prior_sale_date`=∅; `comp_2_prior_sale_date`=∅; `comp_3_prior_sale_date`=∅ | No comparable prior sales within the look-back window with material price changes. |
| **SCA-11** — Comp site size has unit | 🟢 PASS | — | `comp_1_site_size`=13068 sf@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-11** — Comp site size has unit | 🟢 PASS | — | `comp_2_site_size`=11326 sf@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-11** — Comp site size has unit | 🟢 PASS | — | `comp_3_site_size`=11326 sf@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-11** — Comp site size has unit | 🟢 PASS | — | `comp_4_site_size`=7405 sf@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-11** — Comp site size has unit | 🟢 PASS | — | `comp_5_site_size`=13939 sf@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-11** — Comp site size has unit | 🟢 PASS | — | `comp_6_site_size`=22651 sf@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-12** — Comp view UAD format | 🟢 PASS | — | `comp_1_view`=N;Res;@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-12** — Comp view UAD format | 🟢 PASS | — | `comp_2_view`=N;Res;@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-12** — Comp view UAD format | 🟢 PASS | — | `comp_3_view`=N;Res;@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-12** — Comp view UAD format | 🟢 PASS | — | `comp_4_view`=N;Res;@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-12** — Comp view UAD format | 🟢 PASS | — | `comp_5_view`=N;Res;@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-12** — Comp view UAD format | 🟢 PASS | — | `comp_6_view`=N;Res;@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-13** — Comp design present | 🟢 PASS | — | `comp_1_design`=DT2;Traditional@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-13** — Comp design present | 🟢 PASS | — | `comp_2_design`=DT2;Traditional@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-13** — Comp design present | 🟢 PASS | — | `comp_3_design`=DT2;Traditional@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-13** — Comp design present | 🟢 PASS | — | `comp_4_design`=DT2;Traditional@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-13** — Comp design present | 🟢 PASS | — | `comp_5_design`=DT2;Traditional@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-13** — Comp design present | 🟢 PASS | — | `comp_6_design`=DT2;Traditional@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-14** — Comp quality UAD rating + zero-adj | 🟢 PASS | — | `comp_1_quality_rating`=Q3@0.97; `quality_rating`=∅; `comp_1_quality_rating_adjustment`=∅ | Condition satisfied by the extracted value(s). |
| **SCA-14** — Comp quality UAD rating + zero-adj | 🟢 PASS | — | `comp_2_quality_rating`=Q3@0.97; `quality_rating`=∅; `comp_2_quality_rating_adjustment`=∅ | Condition satisfied by the extracted value(s). |
| **SCA-14** — Comp quality UAD rating + zero-adj | 🟢 PASS | — | `comp_3_quality_rating`=Q3@0.97; `quality_rating`=∅; `comp_3_quality_rating_adjustment`=∅ | Condition satisfied by the extracted value(s). |
| **SCA-14** — Comp quality UAD rating + zero-adj | 🟢 PASS | — | `comp_4_quality_rating`=Q3@0.97; `quality_rating`=∅; `comp_4_quality_rating_adjustment`=∅ | Condition satisfied by the extracted value(s). |
| **SCA-14** — Comp quality UAD rating + zero-adj | 🟢 PASS | — | `comp_5_quality_rating`=Q3@0.97; `quality_rating`=∅; `comp_5_quality_rating_adjustment`=∅ | Condition satisfied by the extracted value(s). |
| **SCA-14** — Comp quality UAD rating + zero-adj | 🟢 PASS | — | `comp_6_quality_rating`=Q3@0.97; `quality_rating`=∅; `comp_6_quality_rating_adjustment`=∅ | Condition satisfied by the extracted value(s). |
| **SCA-15** — Subject actual age vs year built | 🟢 PASS | — | `subject_grid_actual_age`=∅; `year_built`=2002@0.97 | Year built (2002) implies age of 24 years — consistent with effective date. |
| **SCA-16** — Comp condition UAD rating + zero-adj | 🟢 PASS | — | `comp_1_condition_rating`=C3@0.97; `condition_rating`=∅; `comp_1_condition_rating_adjustment`=∅ | Condition satisfied by the extracted value(s). |
| **SCA-16** — Comp condition UAD rating + zero-adj | 🟢 PASS | — | `comp_2_condition_rating`=C3@0.97; `condition_rating`=∅; `comp_2_condition_rating_adjustment`=∅ | Condition satisfied by the extracted value(s). |
| **SCA-16** — Comp condition UAD rating + zero-adj | 🟢 PASS | — | `comp_3_condition_rating`=C3@0.97; `condition_rating`=∅; `comp_3_condition_rating_adjustment`=∅ | Condition satisfied by the extracted value(s). |
| **SCA-16** — Comp condition UAD rating + zero-adj | 🟢 PASS | — | `comp_4_condition_rating`=C3@0.97; `condition_rating`=∅; `comp_4_condition_rating_adjustment`=∅ | Condition satisfied by the extracted value(s). |
| **SCA-16** — Comp condition UAD rating + zero-adj | 🟢 PASS | — | `comp_5_condition_rating`=C3@0.97; `condition_rating`=∅; `comp_5_condition_rating_adjustment`=∅ | Condition satisfied by the extracted value(s). |
| **SCA-16** — Comp condition UAD rating + zero-adj | 🟢 PASS | — | `comp_6_condition_rating`=C3@0.97; `condition_rating`=∅; `comp_6_condition_rating_adjustment`=∅ | Condition satisfied by the extracted value(s). |
| **SCA-17** — Above-grade GLA matches grid, improvements & sketch | 🟢 PASS | — | `comp_1_gla`=3300@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-17** — Above-grade GLA matches grid, improvements & sketch | 🟢 PASS | — | `comp_2_gla`=2575@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-17** — Above-grade GLA matches grid, improvements & sketch | 🟢 PASS | — | `comp_3_gla`=2621@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-17** — Above-grade GLA matches grid, improvements & sketch | 🟢 PASS | — | `comp_4_gla`=3362@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-17** — Above-grade GLA matches grid, improvements & sketch | 🟢 PASS | — | `comp_5_gla`=3382@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-17** — Above-grade GLA matches grid, improvements & sketch | 🟢 PASS | — | `comp_6_gla`=2854@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-21** — Comp garage/carport present | 🟢 PASS | — | `comp_1_garage_carport`=2ga2dw@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-21** — Comp garage/carport present | 🟢 PASS | — | `comp_2_garage_carport`=2ga2dw@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-21** — Comp garage/carport present | 🟢 PASS | — | `comp_3_garage_carport`=2ga2dw@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-21** — Comp garage/carport present | 🟢 PASS | — | `comp_4_garage_carport`=2ga2dw@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-21** — Comp garage/carport present | 🟢 PASS | — | `comp_5_garage_carport`=2ga2dw@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-21** — Comp garage/carport present | 🟢 PASS | — | `comp_6_garage_carport`=2ga2dw@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-23** — Listing comp adjustment | 🟢 PASS | — | `comp_6_sale_date`=Active@0.97; `comp_6_net_adjustment`=7000@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-26** — Subject GLA bracketed by comps | 🟢 PASS | — | `gla`=2987@0.97; `comp_1_gla`=3300@0.97; `comp_2_gla`=2575@0.97; `comp_3_gla`=2621@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-3** — Comp address present | 🟢 PASS | — | `comp_1_address`=11511 Essex Fells Dr, Charlotte, NC@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-3** — Comp address present | 🟢 PASS | — | `comp_2_address`=8137 Noland Woods Dr, Charlotte, NC@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-3** — Comp address present | 🟢 PASS | — | `comp_3_address`=8707 Darcy Hopkins Dr, Charlotte, NC@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-3** — Comp address present | 🟢 PASS | — | `comp_4_address`=5917 Cactus Valley Rd, Charlotte, NC@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-3** — Comp address present | 🟢 PASS | — | `comp_5_address`=4814 King Arthur Dr, Charlotte, NC@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-3** — Comp address present | 🟢 PASS | — | `comp_6_address`=12227 Provincetowne Dr, Charlotte, NC@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-4** — Comp proximity present | 🟢 PASS | — | `comp_1_proximity`=0.85 miles NW@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-4** — Comp proximity present | 🟢 PASS | — | `comp_2_proximity`=0.43 miles NW@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-4** — Comp proximity present | 🟢 PASS | — | `comp_3_proximity`=0.47 miles S@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-4** — Comp proximity present | 🟢 PASS | — | `comp_4_proximity`=0.89 miles NE@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-4** — Comp proximity present | 🟢 PASS | — | `comp_5_proximity`=0.82 miles N@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-4** — Comp proximity present | 🟢 PASS | — | `comp_6_proximity`=0.32 miles N@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-5** — Comp data source present | 🟢 PASS | — | `comp_1_data_source`=CMLS#4370375;DOM 2@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-5** — Comp data source present | 🟢 PASS | — | `comp_2_data_source`=CMLS#4304699;DOM 1@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-5** — Comp data source present | 🟢 PASS | — | `comp_3_data_source`=CMLS#4251875;DOM 0@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-5** — Comp data source present | 🟢 PASS | — | `comp_4_data_source`=CMLS#4290407;DOM 55@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-5** — Comp data source present | 🟢 PASS | — | `comp_5_data_source`=CMLS#4391428;DOM 9@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-5** — Comp data source present | 🟢 PASS | — | `comp_6_data_source`=CMLS#4373650;DOM 60@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-6** — Comp verification source specific | 🟢 PASS | — | `comp_1_verification_source`=Assessors/Drive-by@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-6** — Comp verification source specific | 🟢 PASS | — | `comp_2_verification_source`=Assessors/Drive-by@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-6** — Comp verification source specific | 🟢 PASS | — | `comp_3_verification_source`=Assessors/Drive-by@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-6** — Comp verification source specific | 🟢 PASS | — | `comp_4_verification_source`=Assessors/Drive-by@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-6** — Comp verification source specific | 🟢 PASS | — | `comp_5_verification_source`=Assessors/Drive-by@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-6** — Comp verification source specific | 🟢 PASS | — | `comp_6_verification_source`=Assessors/Drive-by@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-8** — Comp date of sale sequencing | 🟢 PASS | — | `comp_1_sale_date`=s05/26;c04/26@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-8** — Comp date of sale sequencing | 🟢 PASS | — | `comp_2_sale_date`=s11/25;c09/25@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-8** — Comp date of sale sequencing | 🟢 PASS | — | `comp_3_sale_date`=s06/25;c05/25@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-8** — Comp date of sale sequencing | 🟢 PASS | — | `comp_4_sale_date`=s10/25;c10/25@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-9** — Comp location UAD format | 🟢 PASS | — | `comp_1_location_rating`=N;Res;@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-9** — Comp location UAD format | 🟢 PASS | — | `comp_2_location_rating`=N;Res;@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-9** — Comp location UAD format | 🟢 PASS | — | `comp_3_location_rating`=N;Res;@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-9** — Comp location UAD format | 🟢 PASS | — | `comp_4_location_rating`=N;Res;@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-9** — Comp location UAD format | 🟢 PASS | — | `comp_5_location_rating`=N;Res;@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-9** — Comp location UAD format | 🟢 PASS | — | `comp_6_location_rating`=N;Res;@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-BR** — Value bracketed by adjusted prices | 🟢 PASS | — | `appraised_value`=815000@0.97; `comp_1_adjusted_sale_price`=801300@0.97; `comp_2_adjusted_sale_price`=828600@0.97; `comp_3_adjusted_sale_price`=831660@0.97; `comp_4_adjusted_sale_price`=800450@0.97; `comp_5_adjusted_sale_price`=882045@0.97; `comp_6_adjusted_sale_price`=856000@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-BR2** — Min comps with adjusted value at/above final opinion (lender overlay) | 🟢 PASS | — | `appraised_value`=815000@0.97; `comp_1_adjusted_sale_price`=801300@0.97; `comp_2_adjusted_sale_price`=828600@0.97; `comp_3_adjusted_sale_price`=831660@0.97; `comp_4_adjusted_sale_price`=800450@0.97; `comp_5_adjusted_sale_price`=882045@0.97; `comp_6_adjusted_sale_price`=856000@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-DC** — Comp sale within date currency window | 🟢 PASS | — | `comp_1_sale_date`=s05/26;c04/26@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-DC** — Comp sale within date currency window | 🟢 PASS | — | `comp_2_sale_date`=s11/25;c09/25@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-DC** — Comp sale within date currency window | 🟢 PASS | — | `comp_3_sale_date`=s06/25;c05/25@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-DC** — Comp sale within date currency window | 🟢 PASS | — | `comp_4_sale_date`=s10/25;c10/25@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-DC** — Comp sale within date currency window | 🟢 PASS | — | `comp_5_sale_date`=c06/26@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-FLIP** — Comp rapid resale flag | 🟢 PASS | — | `comp_1_prior_sale_date`=∅ | Condition satisfied by the extracted value(s). |
| **SCA-GROSS** — Gross adjustment per comp within 25% | 🟢 PASS | — | `comp_1_gross_adj_pct`=8.6@0.97; `comp_2_gross_adj_pct`=5.6@0.97; `comp_3_gross_adj_pct`=11.4@0.97; `comp_4_gross_adj_pct`=10.6@0.97; `comp_5_gross_adj_pct`=9.5@0.97; `comp_6_gross_adj_pct`=3.2@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-NET** — Net adjustment within 15% | 🟢 PASS | — | `comp_1_net_adjustment`=11300@0.97; `comp_2_net_adjustment`=43600@0.97; `comp_3_net_adjustment`=11660@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-PR** — Comp sale price bracket vs subject value | 🟢 PASS | — | `comp_1_sale_price`=790000@0.97; `appraised_value`=815000@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-PR** — Comp sale price bracket vs subject value | 🟢 PASS | — | `comp_2_sale_price`=785000@0.97; `appraised_value`=815000@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-PR** — Comp sale price bracket vs subject value | 🟢 PASS | — | `comp_3_sale_price`=820000@0.97; `appraised_value`=815000@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-PR** — Comp sale price bracket vs subject value | 🟢 PASS | — | `comp_4_sale_price`=785000@0.97; `appraised_value`=815000@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-PR** — Comp sale price bracket vs subject value | 🟢 PASS | — | `comp_5_sale_price`=874900@0.97; `appraised_value`=815000@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-PR** — Comp sale price bracket vs subject value | 🟢 PASS | — | `comp_6_sale_price`=849000@0.97; `appraised_value`=815000@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-PSH** — Subject prior sale analyzed | 🟢 PASS | — | `subject_grid_prior_sale_date`=∅; `effective_date`=2026-06-30@0.97 | Condition satisfied by the extracted value(s). |
| **SIG-1** — Appraiser signed / name present | 🟢 PASS | — | `appraiser_name`=Kevin C. Marcuse@0.97; `date_of_signature`=∅ | Condition satisfied by the extracted value(s). |
| **SIG-3** — Appraiser licensed in property state | 🟢 PASS | — | `appraiser_license_state`=NC@0.97; `state`=NC@0.97 | Condition satisfied by the extracted value(s). |
| **ST-GEO-COMP** — Appraiser geographic competency | 🟢 PASS | — | `appraiser_license_state`=NC@0.97; `state`=NC@0.97 | Condition satisfied by the extracted value(s). |
| **ST-1** — Site dimensions provided | 🟢 PASS | — | `site_dimensions`=See Plat Map@0.97 | Condition satisfied by the extracted value(s). |
| **ST-2** — Site area has correct unit | 🟢 PASS | — | `site_area`=12850 sf@0.97; `site_area_unit`=∅ | Condition satisfied by the extracted value(s). |
| **ST-3** — Site shape provided | 🟢 PASS | — | `site_shape`=Rectangular@0.97 | Condition satisfied by the extracted value(s). |
| **ST-4** — View UAD compliant and consistent | 🟢 PASS | — | `site_view`=N;Res;@0.97 | Condition satisfied by the extracted value(s). |
| **ST-5** — Zoning compliance | 🟢 PASS | — | `zoning_compliance`=Legal@0.97 | Condition satisfied by the extracted value(s). |
| **ST-6** — Highest & best use is Yes | 🟢 PASS | — | `highest_and_best_use`=Yes@0.97 | Condition satisfied by the extracted value(s). |
| **ST-7** — Utilities marked; private systems addressed | 🟢 PASS | — | `utilities_electricity`=Public@0.97; `utilities_gas`=Public@0.97 | Condition satisfied by the extracted value(s). |
| **ST-9** — Utilities/off-site typical for market | 🟢 PASS | — | `utilities_water`=Public@0.97; `utilities_sewer`=Public@0.97 | Condition satisfied by the extracted value(s). |
| **ST-HBU** — Highest and best use stated and consistent | 🟢 PASS | — | `highest_and_best_use`=Yes@0.97; `highest_best_use_indicator`=∅; `highest_best_use_description`=∅ | Condition satisfied by the extracted value(s). |
| **ST-RIGHTS** — Leasehold property rights disclosure | 🟢 PASS | — | `property_rights`=FeeSimple@0.97; `addendum_text`=∅ | Condition satisfied by the extracted value(s). |
| **I-HOA-PUD** — HOA/PUD consistency | 🟢 PASS | — | `hoa_dues`=∅; `is_pud`=∅ | Condition satisfied by the extracted value(s). |
| **S-11** — Property rights appraised present | 🟢 PASS | — | `property_rights`=FeeSimple@0.97 | Condition satisfied by the extracted value(s). |
| **S-4b** — APN present and plausible | 🟢 PASS | — | `assessors_parcel_number`=229-114-16@0.97 | Condition satisfied by the extracted value(s). |
| **S-5** — Neighborhood name valid | 🟢 PASS | — | `neighborhood_name`=Reavencrest Ph 04 Map 03@0.97 | Condition satisfied by the extracted value(s). |
| **S-6** — Census tract format | 🟢 PASS | — | `census_tract`=0058.62@0.97 | Condition satisfied by the extracted value(s). |
| **S-7** — Occupancy status marked | 🟢 PASS | — | `occupant_status`=OwnerOccupied@0.97 | Condition satisfied by the extracted value(s). |
| **S-9** — HOA dues imply PUD marked | 🟢 PASS | — | `hoa_dues`=∅; `is_pud_checked`=∅ | Condition satisfied by the extracted value(s). |
| **ST-FORM-MATCH** — Form type matches property type | 🟢 PASS | — | `design_style`=Traditional@0.97 | Condition satisfied by the extracted value(s). |
| **ADD-2** — Comparable selection commentary explains why | ⚪ N/A | — | — | No substantive sales-comparison narrative extracted. |
| **ADD-4** — 1004MC required for FHA/USDA | ⚪ N/A | — | — | Not applicable to this loan/transaction/form type. |
| **ADD-8** — 1004MC condo project section complete | ⚪ N/A | — | — | Not applicable to this loan/transaction/form type. |
| **C-2a** — Contract price matches purchase agreement | ⚪ N/A | — | — | Not applicable to this loan/transaction/form type. |
| **C-2b** — Contract date matches purchase agreement | ⚪ N/A | — | — | Not applicable to this loan/transaction/form type. |
| **C-3** — Owner-of-record data source present | ⚪ N/A | — | — | Not applicable to this loan/transaction/form type. |
| **C-4** — Concessions consistent and match purchase agreement | ⚪ N/A | — | — | Not applicable to this loan/transaction/form type. |
| **C-5** — Personal property addressed | ⚪ N/A | — | — | Not applicable to this loan/transaction/form type. |
| **C-BUYER-MATCH** — Buyer names match borrower(s) on order | ⚪ N/A | — | — | Not applicable to this loan/transaction/form type. |
| **C-EXEC** — Contract fully executed by all parties | ⚪ N/A | — | — | Not applicable to this loan/transaction/form type. |
| **C-PKG-EXEC** — Contract fully executed (manual verification) | ⚪ N/A | — | — | Not applicable to this loan/transaction/form type. |
| **ORD-ASSIGN-MATCH** — Assignment type in engagement letter matches appraisal report | ⚪ N/A | — | — | Not applicable to this loan/transaction/form type. |
| **ORD-EXEC-STOP** — Unsigned contract blocked by engagement letter policy | ⚪ N/A | — | — | Not applicable to this loan/transaction/form type. |
| **TL-CONTRACT** — Contract date precedes appraisal effective date | ⚪ N/A | — | — | Not applicable to this loan/transaction/form type. |
| **CA-2** — Remaining economic life >= 30 (FHA/VA) | ⚪ N/A | — | — | Not applicable to this loan/transaction/form type. |
| **CA-3** — Cost approach arithmetic and depreciation | ⚪ N/A | — | — | Not applicable to this loan/transaction/form type. |
| **FHA-1** — FHA Minimum Property Requirements confirmed | ⚪ N/A | — | — | Not applicable to this loan/transaction/form type. |
| **FHA-10** — FHA remaining economic life >= 30 | ⚪ N/A | — | — | Not applicable to this loan/transaction/form type. |
| **FHA-12** — FHA well/septic compliance | ⚪ N/A | — | — | Not applicable to this loan/transaction/form type. |
| **FHA-13** — FHA appliances present/operational | ⚪ N/A | — | — | Not applicable to this loan/transaction/form type. |
| **FHA-2** — FHA case number format + match | ⚪ N/A | — | — | Not applicable to this loan/transaction/form type. |
| **FHA-3** — FHA intended use/user statements | ⚪ N/A | — | — | Not applicable to this loan/transaction/form type. |
| **FHA-4** — FHA/HUD certification statement present | ⚪ N/A | — | — | Not applicable to this loan/transaction/form type. |
| **FHA-5** — FHA primary comps within 12 months | ⚪ N/A | — | — | Not applicable to this loan/transaction/form type. |
| **FHA-6** — FHA repairs reported subject-to | ⚪ N/A | — | — | Not applicable to this loan/transaction/form type. |
| **FHA-7** — FHA space heater not primary heat | ⚪ N/A | — | — | Not applicable to this loan/transaction/form type. |
| **FHA-9** — FHA four-side photos | ⚪ N/A | — | — | Not applicable to this loan/transaction/form type. |
| **G-1** — Loan-type consistency (engagement vs appraisal) | ⚪ N/A | — | `loan_type`=∅; `fha_case_number`=∅ | Engagement letter / order form not available. |
| **G-C56** — C5/C6 condition triggers AMC stop | ⚪ N/A | — | — | Not applicable to this loan/transaction/form type. |
| **G-LAVA** — Hawaiian lava zone triggers AMC stop | ⚪ N/A | — | — | Not applicable to this loan/transaction/form type. |
| **G-MFG** — Pre-1976 manufactured home triggers AMC stop | ⚪ N/A | — | — | Not applicable to this loan/transaction/form type. |
| **ORD-CONFLICT** — Engagement letter and XML disagree on order-level facts | ⚪ N/A | — | — | Not applicable to this loan/transaction/form type. |
| **IA-1** — Income approach rent matches rent schedule | ⚪ N/A | — | — | Income approach / rent schedule not developed. |
| **MF-1** — Multi-family requires income approach | ⚪ N/A | — | — | Not applicable to this loan/transaction/form type. |
| **R-INCOME-REQ** — Income approach developed when required | ⚪ N/A | — | `income_approach_value`=0@0.97; `occupancy_type`=OwnerOccupied@0.97 | Income approach not required for this occupancy type. |
| **R-2b** — Value equals contract price (bias advisory) | ⚪ N/A | — | — | Not applicable to this loan/transaction/form type. |
| **R-VALUE-RANGE** — Final value within range of developed approach values | ⚪ N/A | — | `appraised_value`=815000@0.97; `final_value_sca`=815000@0.97; `cost_approach_value`=0@0.97 | Only one approach value developed; single-approach reconciliation handled by R-1. |
| **CG-NONARMS** — Non-arms-length comp without commentary | ⚪ N/A | — | — | No non-arms-length distress indicators found in comparables. |
| **SCA-25** — New construction competing comp | ⚪ N/A | — | — | subject is not new construction |
| **SCA-PSH-Q** — Subject sale history analysis is substantive | ⚪ N/A | — | — | No prior sale/transfer within the look-back window; quality check not applicable. |
| **ORD-ENG-DATE** — Engagement letter predates appraisal report | ⚪ N/A | — | — | Not applicable to this loan/transaction/form type. |
| **SIG-2** — Appraiser name matches engagement | ⚪ N/A | — | — | Not applicable to this loan/transaction/form type. |
| **SIG-SUP** — Supervisory appraiser section complete | ⚪ N/A | — | — | Not applicable to this loan/transaction/form type. |
| **SIG-TRAINEE** — Trainee appraiser requires supervisory cosign | ⚪ N/A | — | `appraiser_license_type`=Certificate@0.97; `supervisory_appraiser_name`=∅; `supervisory_appraiser_cert_number`=∅ | Rule does not apply to this loan/form/transaction type. |
| **ST-PRIOR-SVC** — Prior services disclosure | ⚪ N/A | — | `prior_services_indicator`=∅; `prior_services_description`=∅; `addendum_text`=∅ | Rule does not apply to this loan/form/transaction type. |
| **TL-ENG** — Engagement letter date precedes report signature date | ⚪ N/A | — | — | Not applicable to this loan/transaction/form type. |
| **ST-1B** — Site area magnitude plausibility (multi-signal) | ⚪ N/A | — | `site_area`=12850 sf@0.97; `site_area_unit`=∅ | Rule does not apply to this loan/form/transaction type. |
| **ST-FLOOD-CMT** — Flood zone present — marketability commentary required | ⚪ N/A | — | — | Not applicable to this loan/transaction/form type. |
| **ST-ZONE-NC** — Zoning non-conformance commentary | ⚪ N/A | — | `zoning_compliance`=Legal@0.97; `addendum_text`=∅ | Rule does not apply to this loan/form/transaction type. |
| **LISTING-CMNT** — Listing price vs appraised value commentary | ⚪ N/A | — | — | Not applicable to this loan/transaction/form type. |
| **ORD-COBORROWER** — Co-borrower from order appears in appraisal borrower field | ⚪ N/A | — | — | Not applicable to this loan/transaction/form type. |
| **ORD-FORM-MATCH** — Form type in report matches form type ordered | ⚪ N/A | — | — | Not applicable to this loan/transaction/form type. |
| **ORD-INSP-SCOPE** — Ordered inspection type matches report scope of work | ⚪ N/A | — | — | Not applicable to this loan/transaction/form type. |
| **S-1** — Property address matches order form | ⚪ N/A | — | `property_address`=12619 Provincetowne Dr@0.97 | Engagement letter / order form not available. |
| **S-1** — Property address matches order form | ⚪ N/A | — | `city`=Charlotte@0.97 | Engagement letter / order form not available. |
| **S-1** — Property address matches order form | ⚪ N/A | — | `zip_code`=28277@0.97 | Engagement letter / order form not available. |
| **S-10a** — Lender name matches order form | ⚪ N/A | — | `lender_name`=Reliable Holdings Manager LLC, DBA Lendz Financi…@0.97 | Engagement letter / order form not available. |
| **S-10b** — Lender address matches order form | ⚪ N/A | — | — | Engagement letter / order form not available. |
| **S-2** — Borrower matches order form | ⚪ N/A | — | — | Engagement letter / order form not available. |
| **USDA-1** — USDA cost approach required | ⚪ N/A | — | — | Not applicable to this loan/transaction/form type. |


---

## dir 8 — 9512 N Brooks St.xml

| Rule | Status | Bucket | Extracted (what the rule read) | How it was judged |
|------|--------|--------|-------------------------------|-------------------|
| **SUBJECT-HOLD** — subject | 🔴 FAIL | 🔴 hard-fail | — | 5 failures in the subject section indicate systematic problems (not isolated errors); the section is escalated for a full manual review. |
| **G-0** — Engagement letter / order form present and extracted | 🔴 FAIL | 🟠 extraction-gap | `loan_type`=∅ | The engagement letter / order form was not extracted. All lender-overlay rules (comp count minimum, site value requirement, declining-market clause, A… |
| **S-12** — Prior-listing data source present | 🔴 FAIL | 🔴 hard-fail | `offered_for_sale_12mo`=∅; `data_source`=∅ | The checkbox about prior sale or listing activity in the past 12 months is missing a data source. Please provide the source used to answer this questi… |
| **S-3** — Owner of public record present | 🔴 FAIL | 🔴 hard-fail | `owner_of_public_record`=∅; `legal_description`=∅; `real_estate_taxes`=∅; `special_assessments`=∅ | The 'Owner of Public Record' field is blank. Please complete it. |
| **ADD-9** — USPAP addendum complete | 🟡 VERIFY | 🟠 extraction-gap | — | The USPAP addendum fields (report type, reasonable exposure time, prior services) could not be extracted; manual review required. |
| **C-ANALYZE** — Contract analysis indicator consistency | 🟡 VERIFY | 🟠 extraction-gap | `contract_analyzed`=∅ | The contract_analyzed indicator could not be extracted; rule cannot evaluate — manual review required. |
| **CA-1** — Opinion of site value present | 🟡 VERIFY | 🟡 manual-verify | `site_value_estimate`=∅ | The cost approach is missing an opinion of site value. Please provide one. |
| **I-11** — Conforms to neighborhood | 🟡 VERIFY | 🟠 extraction-gap | `conforms_to_neighborhood`=∅ | Conformity to the neighborhood could not be read; please verify the improvements conform. |
| **I-34** — Materials/condition described | 🟡 VERIFY | 🟡 manual-verify | `exterior_walls`=∅; `roof_surface`=∅; `heating`=∅; `floor_material`=∅; `walls_material`=∅; `trim_finish_material`=∅ | The following materials/condition fields are missing in the improvements section: Exterior Walls, Roof Surface, Heating, Floors, Walls, Trim/Finish. P… |
| **I-5** — Heating and cooling described | 🟡 VERIFY | 🟡 manual-verify | `heating`=∅; `cooling`=∅ | The following heating/cooling fields are not described in the improvements section: Heating, Cooling. Please complete. |
| **I-6** — Appliances reported | 🟡 VERIFY | 🟡 manual-verify | `appliance_refrigerator`=∅; `appliance_range_oven`=∅; `appliance_disposal`=∅; `appliance_dishwasher`=∅; `appliance_microwave`=∅; `appliance_washer_dryer`=∅ | No kitchen appliances are listed in the improvements section. Please note which appliances are present. |
| **I-8** — Additional features described | 🟡 VERIFY | 🟡 manual-verify | `fireplace_count`=∅; `porch_patio_deck`=∅; `additional_features`=∅ | Please confirm any additional features (fireplace, porch/patio/deck, pool, etc.) are described in the improvements section, or state 'None'. |
| **I-9** — Condition rating UAD and consistent | 🟡 VERIFY | 🟠 extraction-gap | `condition_rating`=∅ | Condition could not be extracted from the document; manual review required. |
| **I-Q** — Quality rating UAD format | 🟡 VERIFY | 🟠 extraction-gap | `quality_rating`=∅ | Quality could not be extracted from the document; manual review required. |
| **I-SMCO** — Smoke/CO detector code compliance noted | 🟡 VERIFY | 🟡 manual-verify | `sales_comparison_summary`=∅ | No mention of smoke or CO detectors was found in the report. The client requires a note confirming detectors meet local code — please add one to the r… |
| **N-7** — Market conditions completed | 🟡 VERIFY | 🟡 manual-verify | `market_conditions_commentary`=See attached addenda. The appraiser is not an ec…@0.97 | The market conditions section just says 'See 1004MC' instead of containing the actual analysis. Please put the market analysis directly in this sectio… |
| **PH-1** — Subject front/rear/street photos | 🟡 VERIFY | 🟡 manual-verify | `photo_front`=∅; `photo_rear`=∅; `photo_street`=∅ | Required photos are missing: front, rear, street scene. At minimum, please include a front photo, a rear photo, and a street scene. |
| **PH-2** — Interior photos present | 🟡 VERIFY | 🟡 manual-verify | `photo_interior_rooms`=∅ | Interior photos are incomplete — missing: kitchen, living, bedroom, bathroom. Please include photos of the kitchen, living room, all bedrooms, and all… |
| **CA-ARITH** — Cost approach arithmetic cross-check | 🟡 VERIFY | 🟡 manual-verify | `site_value`=80000@0.97; `total_improvements_cost`=∅; `total_depreciation`=∅; `cost_approach_value`=0@0.97 | Cost approach arithmetic cannot be evaluated; the following field(s) could not be extracted: total_improvements_cost, total_depreciation — manual revi… |
| **R-1** — SCA value matches market value | 🟡 VERIFY | 🟡 manual-verify | `indicated_value_sca`=∅; `appraised_value`=373000@0.97 | The sales comparison value or final opinion of value could not be read. Please verify both numbers are present and agree. |
| **R-1b** — Reconciliation names the weighted approach | 🟡 VERIFY | 🟡 manual-verify | `final_reconciliation_comment`=∅ | The reconciliation must say which approach was relied on most (sales comparison, cost, or income) and briefly explain why. Please add that statement t… |
| **R-ASSIGN-COND** — Assignment condition vs report language consistency | 🟡 VERIFY | 🟡 manual-verify | `assignment_condition`=AsIs@0.97; `addendum_text`=∅; `limiting_conditions_text`=∅ | The assignment condition box (AsIs) doesn't match the language used in the report narrative. Please make sure the box and the written description agre… |
| **R-MKTTIME** — Marketing time consistent with neighborhood data | 🟡 VERIFY | 🟡 manual-verify | `marketing_time_typical`=UnderThreeMonths@0.97; `addendum_text`=∅ | The marketing time stated in the report appears inconsistent with the market data for this area. Please make sure the estimated selling time matches w… |
| **CG-TIME-CONSIST** — Time/market adjustment rate consistency | 🟡 VERIFY | 🟠 extraction-gap | — | Fewer than 2 comps with measurable time adjustments; rate consistency check skipped — manual review required. |
| **SCA-10** — Comp property rights present + consistent | 🟡 VERIFY | 🟡 manual-verify | `comp_1_leasehold`=∅ | Please indicate the property rights (Fee Simple or Leasehold) for Comp 1 in the sales grid. |
| **SCA-10** — Comp property rights present + consistent | 🟡 VERIFY | 🟡 manual-verify | `comp_2_leasehold`=∅ | Please indicate the property rights (Fee Simple or Leasehold) for Comp 2 in the sales grid. |
| **SCA-10** — Comp property rights present + consistent | 🟡 VERIFY | 🟡 manual-verify | `comp_3_leasehold`=∅ | Please indicate the property rights (Fee Simple or Leasehold) for Comp 3 in the sales grid. |
| **SCA-10** — Comp property rights present + consistent | 🟡 VERIFY | 🟡 manual-verify | `comp_4_leasehold`=∅ | Please indicate the property rights (Fee Simple or Leasehold) for Comp 4 in the sales grid. |
| **SCA-10** — Comp property rights present + consistent | 🟡 VERIFY | 🟡 manual-verify | `comp_5_leasehold`=∅ | Please indicate the property rights (Fee Simple or Leasehold) for Comp 5 in the sales grid. |
| **SCA-10** — Comp property rights present + consistent | 🟡 VERIFY | 🟡 manual-verify | `comp_6_leasehold`=∅ | Please indicate the property rights (Fee Simple or Leasehold) for Comp 6 in the sales grid. |
| **SCA-16V** — Comp photo condition cross-check | 🟡 VERIFY | 🟠 extraction-gap | — | Please open the report and visually confirm that the front photo matches the subject property address. Automated photo review is not available for thi… |
| **SCA-17** — Above-grade GLA matches grid, improvements & sketch | 🟡 VERIFY | 🟡 manual-verify | `subject_grid_gla`=1408@0.97; `gla`=1408@0.97; `sketch_living_area`=∅ | The living area couldn't be confirmed across all sources (SCA grid 1408, improvements 1408, sketch n/a sf). Please verify the GLA in the sales grid ma… |
| **SCA-18** — Comp basement present | 🟡 VERIFY | 🟡 manual-verify | `comp_1_basement`=∅ | Basement and below-grade rooms are missing for Comp 1. Please fill this in (finished sq ft and room count, or 'None' if there is none). |
| **SCA-18** — Comp basement present | 🟡 VERIFY | 🟡 manual-verify | `comp_2_basement`=∅ | Basement and below-grade rooms are missing for Comp 2. Please fill this in (finished sq ft and room count, or 'None' if there is none). |
| **SCA-18** — Comp basement present | 🟡 VERIFY | 🟡 manual-verify | `comp_3_basement`=∅ | Basement and below-grade rooms are missing for Comp 3. Please fill this in (finished sq ft and room count, or 'None' if there is none). |
| **SCA-18** — Comp basement present | 🟡 VERIFY | 🟡 manual-verify | `comp_4_basement`=∅ | Basement and below-grade rooms are missing for Comp 4. Please fill this in (finished sq ft and room count, or 'None' if there is none). |
| **SCA-18** — Comp basement present | 🟡 VERIFY | 🟡 manual-verify | `comp_5_basement`=∅ | Basement and below-grade rooms are missing for Comp 5. Please fill this in (finished sq ft and room count, or 'None' if there is none). |
| **SCA-18** — Comp basement present | 🟡 VERIFY | 🟡 manual-verify | `comp_6_basement`=∅ | Basement and below-grade rooms are missing for Comp 6. Please fill this in (finished sq ft and room count, or 'None' if there is none). |
| **SCA-19** — Comp functional utility present | 🟡 VERIFY | 🟡 manual-verify | `comp_1_functional_utility`=∅ | Please add functional utility for Comp 1 in the sales grid. |
| **SCA-19** — Comp functional utility present | 🟡 VERIFY | 🟡 manual-verify | `comp_2_functional_utility`=∅ | Please add functional utility for Comp 2 in the sales grid. |
| **SCA-19** — Comp functional utility present | 🟡 VERIFY | 🟡 manual-verify | `comp_3_functional_utility`=∅ | Please add functional utility for Comp 3 in the sales grid. |
| **SCA-19** — Comp functional utility present | 🟡 VERIFY | 🟡 manual-verify | `comp_4_functional_utility`=∅ | Please add functional utility for Comp 4 in the sales grid. |
| **SCA-19** — Comp functional utility present | 🟡 VERIFY | 🟡 manual-verify | `comp_5_functional_utility`=∅ | Please add functional utility for Comp 5 in the sales grid. |
| **SCA-19** — Comp functional utility present | 🟡 VERIFY | 🟡 manual-verify | `comp_6_functional_utility`=∅ | Please add functional utility for Comp 6 in the sales grid. |
| **SCA-2** — Minimum comparable sales | 🟡 VERIFY | 🟡 manual-verify | `comp_1_sale_price`=385000@0.97; `comp_2_sale_price`=360000@0.97; `comp_3_sale_price`=420000@0.97 | Only 0 active listing comparable(s) were found (6 closed sales). The client requires at least 1 active listing(s). Please add one or explain in the re… |
| **SCA-20** — Comp heating/cooling present | 🟡 VERIFY | 🟡 manual-verify | `comp_1_heating_cooling`=∅ | Please add the heating/cooling information for Comp 1 in the sales grid. |
| **SCA-20** — Comp heating/cooling present | 🟡 VERIFY | 🟡 manual-verify | `comp_2_heating_cooling`=∅ | Please add the heating/cooling information for Comp 2 in the sales grid. |
| **SCA-20** — Comp heating/cooling present | 🟡 VERIFY | 🟡 manual-verify | `comp_3_heating_cooling`=∅ | Please add the heating/cooling information for Comp 3 in the sales grid. |
| **SCA-20** — Comp heating/cooling present | 🟡 VERIFY | 🟡 manual-verify | `comp_4_heating_cooling`=∅ | Please add the heating/cooling information for Comp 4 in the sales grid. |
| **SCA-20** — Comp heating/cooling present | 🟡 VERIFY | 🟡 manual-verify | `comp_5_heating_cooling`=∅ | Please add the heating/cooling information for Comp 5 in the sales grid. |
| **SCA-20** — Comp heating/cooling present | 🟡 VERIFY | 🟡 manual-verify | `comp_6_heating_cooling`=∅ | Please add the heating/cooling information for Comp 6 in the sales grid. |
| **SCA-22** — Comp porch/patio/deck present | 🟡 VERIFY | 🟡 manual-verify | `comp_1_porch_patio_deck`=∅ | Please add the porch, patio, or deck information for Comp 1 in the sales grid. |
| **SCA-22** — Comp porch/patio/deck present | 🟡 VERIFY | 🟡 manual-verify | `comp_2_porch_patio_deck`=∅ | Please add the porch, patio, or deck information for Comp 2 in the sales grid. |
| **SCA-22** — Comp porch/patio/deck present | 🟡 VERIFY | 🟡 manual-verify | `comp_3_porch_patio_deck`=∅ | Please add the porch, patio, or deck information for Comp 3 in the sales grid. |
| **SCA-22** — Comp porch/patio/deck present | 🟡 VERIFY | 🟡 manual-verify | `comp_4_porch_patio_deck`=∅ | Please add the porch, patio, or deck information for Comp 4 in the sales grid. |
| **SCA-22** — Comp porch/patio/deck present | 🟡 VERIFY | 🟡 manual-verify | `comp_5_porch_patio_deck`=∅ | Please add the porch, patio, or deck information for Comp 5 in the sales grid. |
| **SCA-22** — Comp porch/patio/deck present | 🟡 VERIFY | 🟡 manual-verify | `comp_6_porch_patio_deck`=∅ | Please add the porch, patio, or deck information for Comp 6 in the sales grid. |
| **SCA-27** — Comparable photos present + type | 🟡 VERIFY | 🟡 manual-verify | `comp_photo_pages`=∅ | Photo check required — verify that comparable sale photos are present and match the correct properties. |
| **SCA-FLIP** — Comp rapid resale flag | 🟡 VERIFY | 🟡 manual-verify | `comp_4_prior_sale_date`=02/12/2026@0.97; `comp_4_sale_date`=s06/26;c05/26@0.97 | Comp 4 resold within 4 month(s). Please confirm this was an arm's-length transaction and add a comment on the quick turnaround. The appraiser's narrat… |
| **SCA-FLIP** — Comp rapid resale flag | 🟡 VERIFY | 🟡 manual-verify | `comp_5_prior_sale_date`=04/04/2025@0.97; `comp_5_sale_date`=s07/25;c07/25@0.97 | Comp 5 resold within 3 month(s). Please confirm this was an arm's-length transaction and add a comment on the quick turnaround. The appraiser's narrat… |
| **SCA-FLIP** — Comp rapid resale flag | 🟡 VERIFY | 🟡 manual-verify | `comp_6_prior_sale_date`=08/21/2025@0.97; `comp_6_sale_date`=s06/26;c05/26@0.97 | Comp 6 resold within 10 month(s). Please confirm this was an arm's-length transaction and add a comment on the quick turnaround. The appraiser's narra… |
| **SCA-NET** — Net adjustment within 15% | 🟡 VERIFY | 🟡 manual-verify | `comp_1_net_adjustment`=-10380@0.97; `comp_2_net_adjustment`=-5665@0.97; `comp_3_net_adjustment`=-29020@0.97 | Comps 6 have net adjustments over 15%. Please explain in the report why these comparables are still appropriate. No supporting explanation for a large… |
| **DOC-1** — License current at signature | 🟡 VERIFY | 🟡 manual-verify | `appraiser_cert_expiration_date`=2026-11-30@0.97; `date_of_signature`=∅ | The license expiration or signature date could not be read; please verify the license was current when the report was signed. |
| **SIG-4** — Appraiser email present | 🟡 VERIFY | 🟡 manual-verify | `appraiser_email`=∅ | The appraiser's email address is missing or unreadable. Please provide it. |
| **SIG-D** — Signature date >= effective date | 🟡 VERIFY | 🟡 manual-verify | `date_of_signature`=∅; `effective_date`=2026-06-24@0.97 | The signature date or effective date could not be read; please verify the signature date is on or after the effective date. |
| **ST-10** — Adverse site conditions addressed | 🟡 VERIFY | 🟠 extraction-gap | `adverse_site_conditions`=∅ | The adverse site conditions answer could not be extracted; manual review required. |
| **ST-8** — FEMA flood data complete; zone addressed | 🟡 VERIFY | 🟡 manual-verify | `fema_flood_hazard`=∅; `fema_flood_zone`=∅; `fema_map_date`=∅ | The flood zone information (zone, map number, and map date) must be completed in the site section — this is required even if the property is not in a … |
| **S-4d** — Tax year current | 🟡 VERIFY | 🟡 manual-verify | `tax_year`=∅; `effective_date`=2026-06-24@0.97 | The tax year / effective date could not be extracted; please verify the tax year is within the last 2 years. |
| **S-6b** — Map reference numeric | 🟡 VERIFY | 🟠 extraction-gap | `map_reference`=∅ | Map Reference could not be extracted from the document; manual review required. |
| **ST-INTENDED** — Intended use and intended user stated | 🟡 VERIFY | 🟡 manual-verify | `addendum_text`=∅ | The report must state what the appraisal is for (mortgage lending) and who it is for (the lender/client). Please confirm both of these statements are … |
| **ST-SCOPE** — Scope of work stated | 🟡 VERIFY | 🟡 manual-verify | `addendum_text`=∅ | The scope of work description could not be found. Please verify the report describes what type of inspection was performed and what the appraiser did … |
| **ADD-5** — 1004MC inventory analysis complete | 🟢 PASS | — | `mca_total_sales_prior_7_12`=17@0.97; `mca_total_sales_prior_4_6`=7@0.97; `mca_total_sales_current_3`=12@0.97; `mca_absorption_rate_prior_7_12`=2.83@0.97 | Condition satisfied by the extracted value(s). |
| **ADD-X** — Addenda cross-reference resolution | 🟢 PASS | — | — | Condition satisfied by the extracted value(s). |
| **I-1** — General description complete | 🟢 PASS | — | `units_count`=1@0.97; `stories`=1@0.97; `dwelling_type`=Detached@0.97; `design_style`=Florida@0.97; `year_built`=2006@0.97; `effective_age`=8@0.97 | Condition satisfied by the extracted value(s). |
| **I-10** — Adverse livability conditions addressed | 🟢 PASS | — | `adverse_conditions`=No@0.97 | Condition satisfied by the extracted value(s). |
| **I-12** — Additions addressed | 🟢 PASS | — | — | Condition satisfied by the extracted value(s). |
| **I-2** — Foundation described | 🟢 PASS | — | `foundation_type`=ConcSlab/C3@0.97 | Condition satisfied by the extracted value(s). |
| **I-7** — Above-grade room count present | 🟢 PASS | — | `total_rooms`=7@0.97; `bedrooms`=3@0.97; `baths`=2.0@0.97; `gla`=1408@0.97 | Condition satisfied by the extracted value(s). |
| **I-AGE** — Effective age does not exceed actual age | 🟢 PASS | — | `effective_age`=8@0.97; `year_built`=2006@0.97; `effective_date`=2026-06-24@0.97 | Condition satisfied by the extracted value(s). |
| **I-YRBUILT** — Year built consistent with actual age | 🟢 PASS | — | `year_built`=2006@0.97; `effective_date`=2026-06-24@0.97; `effective_age`=8@0.97 | Condition satisfied by the extracted value(s). |
| **IM-2** — Bedroom / total-room count consistency | 🟢 PASS | — | `total_rooms`=7@0.97; `bedrooms`=3@0.97 | Condition satisfied by the extracted value(s). |
| **N-1** — Neighborhood characteristics marked | 🟢 PASS | — | `location`=Suburban@0.97 | Condition satisfied by the extracted value(s). |
| **N-1** — Neighborhood characteristics marked | 🟢 PASS | — | `built_up`=Over75Percent@0.97 | Condition satisfied by the extracted value(s). |
| **N-1** — Neighborhood characteristics marked | 🟢 PASS | — | `growth_rate`=Stable@0.97 | Condition satisfied by the extracted value(s). |
| **N-2** — Housing trends marked and consistent | 🟢 PASS | — | `property_values`=Stable@0.97 | Condition satisfied by the extracted value(s). |
| **N-2** — Housing trends marked and consistent | 🟢 PASS | — | `demand_supply`=InBalance@0.97 | Condition satisfied by the extracted value(s). |
| **N-2** — Housing trends marked and consistent | 🟢 PASS | — | `marketing_time`=UnderThreeMonths@0.97 | Condition satisfied by the extracted value(s). |
| **N-3** — Price/age ranges valid | 🟢 PASS | — | `price_low`=270@0.97; `price_high`=460@0.97 | Condition satisfied by the extracted value(s). |
| **N-3** — Price/age ranges valid | 🟢 PASS | — | `age_low`=0@0.97; `age_high`=46@0.97 | Condition satisfied by the extracted value(s). |
| **N-4** — Present land use sums to 100% | 🟢 PASS | — | `land_use_one_unit`=60@0.97; `land_use_2_4_unit`=10@0.97; `land_use_multi_family`=10@0.97; `land_use_commercial`=15@0.97; `land_use_other`=5@0.97 | Condition satisfied by the extracted value(s). |
| **N-4** — Present land use sums to 100% | 🟢 PASS | — | `land_use_other`=5@0.97 | Condition satisfied by the extracted value(s). |
| **N-5** — All four boundaries delineated | 🟢 PASS | — | `neighborhood_boundaries`=E 109th Ave North, E Sitka Ave South, N 30th St …@0.97 | Condition satisfied by the extracted value(s). |
| **N-6** — Neighborhood description specific | 🟢 PASS | — | `neighborhood_description`=See attached addenda. The subject is located in …@0.97 | Condition satisfied by the extracted value(s). |
| **R-2** — As-Is / Subject-To checked | 🟢 PASS | — | `appraisal_subject_to`=As Is@0.97 | Condition satisfied by the extracted value(s). |
| **R-EXPOSURE** — Exposure time stated as a specific period | 🟢 PASS | — | `addendum_text`=∅; `final_reconciliation_comment`=∅ | Condition satisfied by the extracted value(s). |
| **R-VALUE-RANGE** — Final value within range of developed approach values | 🟢 PASS | — | `appraised_value`=373000@0.97; `final_value_sca`=373000@0.97; `cost_approach_value`=0@0.97 | Condition satisfied by the extracted value(s). |
| **RECON-T** — Reconciliation forbidden terms | 🟢 PASS | — | `final_reconciliation_comment`=∅ | Condition satisfied by the extracted value(s). |
| **VAL-1** — Final opinion of value extraction integrity | 🟢 PASS | — | `appraised_value`=373000@0.97; `contract_price`=∅ | Condition satisfied by the extracted value(s). |
| **CG-CONC-DIR** — Concession adjustment wrong direction | 🟢 PASS | — | `comp_7_sale_price`=398000@0.97; `comp_7_concessions`=Listing@0.97; `comp_7_financing_adj`=∅ | Condition satisfied by the extracted value(s). |
| **CG-CONC-DIR** — Concession adjustment wrong direction | 🟢 PASS | — | `comp_8_sale_price`=350000@0.97; `comp_8_concessions`=Listing@0.97; `comp_8_financing_adj`=∅ | Condition satisfied by the extracted value(s). |
| **CG-COND-CONSIST** — Condition adjustment consistency across comps | 🟢 PASS | — | `comp_1_condition_adj`=∅; `comp_2_condition_adj`=∅; `comp_3_condition_adj`=∅ | Condition satisfied by the extracted value(s). |
| **CG-DIST** — Comp distance threshold by area type | 🟢 PASS | — | `comp_1_proximity`=0.70 miles SE@0.97; `comp_2_proximity`=0.81 miles E@0.97; `comp_3_proximity`=0.36 miles SW@0.97 | Condition satisfied by the extracted value(s). |
| **CG-GLA-BRACKET** — Subject GLA bracketed by comp GLAs | 🟢 PASS | — | `subject_grid_gla`=1408@0.97; `gla`=1408@0.97; `comp_1_gla`=1508@0.97; `comp_2_gla`=1386@0.97; `comp_3_gla`=1400@0.97 | Condition satisfied by the extracted value(s). |
| **CG-NET-BIAS** — Net adjustment directional bias | 🟢 PASS | — | `comp_1_net_adjustment`=-10380@0.97; `comp_2_net_adjustment`=-5665@0.97; `comp_3_net_adjustment`=-29020@0.97 | Condition satisfied by the extracted value(s). |
| **CG-PRIOR-SALE** — Comp prior sale rapid appreciation flag | 🟢 PASS | — | `comp_4_prior_sale_date`=02/12/2026@0.97; `comp_4_prior_sale_price`=235000@0.97; `comp_4_sale_price`=360000@0.97; `comp_4_sale_date`=s06/26;c05/26@0.97 | Condition satisfied by the extracted value(s). |
| **CG-PRIOR-SALE** — Comp prior sale rapid appreciation flag | 🟢 PASS | — | `comp_5_prior_sale_date`=04/04/2025@0.97; `comp_5_prior_sale_price`=210000@0.97; `comp_5_sale_price`=330000@0.97; `comp_5_sale_date`=s07/25;c07/25@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-11** — Comp site size has unit | 🟢 PASS | — | `comp_1_site_size`=5000 sf@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-11** — Comp site size has unit | 🟢 PASS | — | `comp_2_site_size`=7875 sf@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-11** — Comp site size has unit | 🟢 PASS | — | `comp_3_site_size`=5300 sf@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-11** — Comp site size has unit | 🟢 PASS | — | `comp_4_site_size`=5250 sf@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-11** — Comp site size has unit | 🟢 PASS | — | `comp_5_site_size`=7515 sf@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-11** — Comp site size has unit | 🟢 PASS | — | `comp_6_site_size`=5000 sf@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-12** — Comp view UAD format | 🟢 PASS | — | `comp_1_view`=N;Res;@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-12** — Comp view UAD format | 🟢 PASS | — | `comp_2_view`=N;Res;@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-12** — Comp view UAD format | 🟢 PASS | — | `comp_3_view`=N;Res;@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-12** — Comp view UAD format | 🟢 PASS | — | `comp_4_view`=N;Res;@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-12** — Comp view UAD format | 🟢 PASS | — | `comp_5_view`=N;Res;@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-12** — Comp view UAD format | 🟢 PASS | — | `comp_6_view`=N;Res;@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-13** — Comp design present | 🟢 PASS | — | `comp_1_design`=DT1;Flrda@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-13** — Comp design present | 🟢 PASS | — | `comp_2_design`=DT1;Flrda@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-13** — Comp design present | 🟢 PASS | — | `comp_3_design`=DT1;Flrda@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-13** — Comp design present | 🟢 PASS | — | `comp_4_design`=DT1;Flrda@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-13** — Comp design present | 🟢 PASS | — | `comp_5_design`=DT1;Flrda@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-13** — Comp design present | 🟢 PASS | — | `comp_6_design`=DT1;Flrda@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-14** — Comp quality UAD rating + zero-adj | 🟢 PASS | — | `comp_1_quality_rating`=Q4@0.97; `quality_rating`=∅; `comp_1_quality_rating_adjustment`=∅ | Condition satisfied by the extracted value(s). |
| **SCA-14** — Comp quality UAD rating + zero-adj | 🟢 PASS | — | `comp_2_quality_rating`=Q4@0.97; `quality_rating`=∅; `comp_2_quality_rating_adjustment`=∅ | Condition satisfied by the extracted value(s). |
| **SCA-14** — Comp quality UAD rating + zero-adj | 🟢 PASS | — | `comp_3_quality_rating`=Q4@0.97; `quality_rating`=∅; `comp_3_quality_rating_adjustment`=∅ | Condition satisfied by the extracted value(s). |
| **SCA-14** — Comp quality UAD rating + zero-adj | 🟢 PASS | — | `comp_4_quality_rating`=Q4@0.97; `quality_rating`=∅; `comp_4_quality_rating_adjustment`=∅ | Condition satisfied by the extracted value(s). |
| **SCA-14** — Comp quality UAD rating + zero-adj | 🟢 PASS | — | `comp_5_quality_rating`=Q4@0.97; `quality_rating`=∅; `comp_5_quality_rating_adjustment`=∅ | Condition satisfied by the extracted value(s). |
| **SCA-14** — Comp quality UAD rating + zero-adj | 🟢 PASS | — | `comp_6_quality_rating`=Q4@0.97; `quality_rating`=∅; `comp_6_quality_rating_adjustment`=∅ | Condition satisfied by the extracted value(s). |
| **SCA-15** — Subject actual age vs year built | 🟢 PASS | — | `subject_grid_actual_age`=∅; `year_built`=2006@0.97 | Year built (2006) implies age of 20 years — consistent with effective date. |
| **SCA-16** — Comp condition UAD rating + zero-adj | 🟢 PASS | — | `comp_1_condition_rating`=C3@0.97; `condition_rating`=∅; `comp_1_condition_rating_adjustment`=∅ | Condition satisfied by the extracted value(s). |
| **SCA-16** — Comp condition UAD rating + zero-adj | 🟢 PASS | — | `comp_2_condition_rating`=C3@0.97; `condition_rating`=∅; `comp_2_condition_rating_adjustment`=∅ | Condition satisfied by the extracted value(s). |
| **SCA-16** — Comp condition UAD rating + zero-adj | 🟢 PASS | — | `comp_3_condition_rating`=C3@0.97; `condition_rating`=∅; `comp_3_condition_rating_adjustment`=∅ | Condition satisfied by the extracted value(s). |
| **SCA-16** — Comp condition UAD rating + zero-adj | 🟢 PASS | — | `comp_4_condition_rating`=C3@0.97; `condition_rating`=∅; `comp_4_condition_rating_adjustment`=∅ | Condition satisfied by the extracted value(s). |
| **SCA-16** — Comp condition UAD rating + zero-adj | 🟢 PASS | — | `comp_5_condition_rating`=C3@0.97; `condition_rating`=∅; `comp_5_condition_rating_adjustment`=∅ | Condition satisfied by the extracted value(s). |
| **SCA-16** — Comp condition UAD rating + zero-adj | 🟢 PASS | — | `comp_6_condition_rating`=C4@0.97; `condition_rating`=∅; `comp_6_condition_rating_adjustment`=∅ | Condition satisfied by the extracted value(s). |
| **SCA-17** — Above-grade GLA matches grid, improvements & sketch | 🟢 PASS | — | `comp_1_gla`=1508@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-17** — Above-grade GLA matches grid, improvements & sketch | 🟢 PASS | — | `comp_2_gla`=1386@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-17** — Above-grade GLA matches grid, improvements & sketch | 🟢 PASS | — | `comp_3_gla`=1400@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-17** — Above-grade GLA matches grid, improvements & sketch | 🟢 PASS | — | `comp_4_gla`=1206@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-17** — Above-grade GLA matches grid, improvements & sketch | 🟢 PASS | — | `comp_5_gla`=1200@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-17** — Above-grade GLA matches grid, improvements & sketch | 🟢 PASS | — | `comp_6_gla`=1200@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-21** — Comp garage/carport present | 🟢 PASS | — | `comp_1_garage_carport`=2ga2dw@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-21** — Comp garage/carport present | 🟢 PASS | — | `comp_2_garage_carport`=1cp1dw@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-21** — Comp garage/carport present | 🟢 PASS | — | `comp_3_garage_carport`=2ga2dw@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-21** — Comp garage/carport present | 🟢 PASS | — | `comp_4_garage_carport`=2ga2dw@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-21** — Comp garage/carport present | 🟢 PASS | — | `comp_5_garage_carport`=2dw@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-21** — Comp garage/carport present | 🟢 PASS | — | `comp_6_garage_carport`=1dw@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-26** — Subject GLA bracketed by comps | 🟢 PASS | — | `gla`=1408@0.97; `comp_1_gla`=1508@0.97; `comp_2_gla`=1386@0.97; `comp_3_gla`=1400@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-3** — Comp address present | 🟢 PASS | — | `comp_1_address`=1819 E Eskimo Ave, Tampa, FL@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-3** — Comp address present | 🟢 PASS | — | `comp_2_address`=2222 E 99th Ave, Tampa, FL@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-3** — Comp address present | 🟢 PASS | — | `comp_3_address`=1014 1/2 E Okaloosa Ave, Tampa, FL@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-3** — Comp address present | 🟢 PASS | — | `comp_4_address`=8725 N 13th St, Tampa, FL@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-3** — Comp address present | 🟢 PASS | — | `comp_5_address`=1801 E Navajo Ave, Tampa, FL@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-3** — Comp address present | 🟢 PASS | — | `comp_6_address`=8512 N Dixon Ave, Tampa, FL@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-4** — Comp proximity present | 🟢 PASS | — | `comp_1_proximity`=0.70 miles SE@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-4** — Comp proximity present | 🟢 PASS | — | `comp_2_proximity`=0.81 miles E@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-4** — Comp proximity present | 🟢 PASS | — | `comp_3_proximity`=0.36 miles SW@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-4** — Comp proximity present | 🟢 PASS | — | `comp_4_proximity`=0.38 miles S@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-4** — Comp proximity present | 🟢 PASS | — | `comp_5_proximity`=0.62 miles NE@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-4** — Comp proximity present | 🟢 PASS | — | `comp_6_proximity`=0.92 miles SW@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-5** — Comp data source present | 🟢 PASS | — | `comp_1_data_source`=StellarMLS #TB8451006;DOM 157@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-5** — Comp data source present | 🟢 PASS | — | `comp_2_data_source`=StellarMLS #TB8504877;DOM 26@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-5** — Comp data source present | 🟢 PASS | — | `comp_3_data_source`=StellarMLS #TB8489025;DOM 27@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-5** — Comp data source present | 🟢 PASS | — | `comp_4_data_source`=StellarMLS #TB8501982;DOM 19@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-5** — Comp data source present | 🟢 PASS | — | `comp_5_data_source`=StellarMLS #TB8385441;DOM 19@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-5** — Comp data source present | 🟢 PASS | — | `comp_6_data_source`=StellarMLS #TB8505739;DOM 9@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-6** — Comp verification source specific | 🟢 PASS | — | `comp_1_verification_source`=Doc #222563/Realist@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-6** — Comp verification source specific | 🟢 PASS | — | `comp_2_verification_source`=Doc #377244/Realist@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-6** — Comp verification source specific | 🟢 PASS | — | `comp_3_verification_source`=Doc #212673/Realist@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-6** — Comp verification source specific | 🟢 PASS | — | `comp_4_verification_source`=Doc #299541/Realist@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-6** — Comp verification source specific | 🟢 PASS | — | `comp_5_verification_source`=Doc #335873/Realist@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-6** — Comp verification source specific | 🟢 PASS | — | `comp_6_verification_source`=Doc #10532-1315/Realist@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-8** — Comp date of sale sequencing | 🟢 PASS | — | `comp_1_sale_date`=s06/26;c05/26@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-8** — Comp date of sale sequencing | 🟢 PASS | — | `comp_2_sale_date`=s06/26;c06/26@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-8** — Comp date of sale sequencing | 🟢 PASS | — | `comp_3_sale_date`=s05/26;c04/26@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-8** — Comp date of sale sequencing | 🟢 PASS | — | `comp_4_sale_date`=s06/26;c05/26@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-8** — Comp date of sale sequencing | 🟢 PASS | — | `comp_5_sale_date`=s07/25;c07/25@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-8** — Comp date of sale sequencing | 🟢 PASS | — | `comp_6_sale_date`=s06/26;c05/26@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-9** — Comp location UAD format | 🟢 PASS | — | `comp_1_location_rating`=A;Adj. to RXR;@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-9** — Comp location UAD format | 🟢 PASS | — | `comp_2_location_rating`=N;Res;@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-9** — Comp location UAD format | 🟢 PASS | — | `comp_3_location_rating`=A;Comm;@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-9** — Comp location UAD format | 🟢 PASS | — | `comp_4_location_rating`=N;Res;@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-9** — Comp location UAD format | 🟢 PASS | — | `comp_5_location_rating`=N;Res;@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-9** — Comp location UAD format | 🟢 PASS | — | `comp_6_location_rating`=A;BsyRd;@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-BR** — Value bracketed by adjusted prices | 🟢 PASS | — | `appraised_value`=373000@0.97; `comp_1_adjusted_sale_price`=374620@0.97; `comp_2_adjusted_sale_price`=354335@0.97; `comp_3_adjusted_sale_price`=390980@0.97; `comp_4_adjusted_sale_price`=368660@0.97; `comp_5_adjusted_sale_price`=364667@0.97; `comp_6_adjusted_sale_price`=383040@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-BR2** — Min comps with adjusted value at/above final opinion (lender overlay) | 🟢 PASS | — | `appraised_value`=373000@0.97; `comp_1_adjusted_sale_price`=374620@0.97; `comp_2_adjusted_sale_price`=354335@0.97; `comp_3_adjusted_sale_price`=390980@0.97; `comp_4_adjusted_sale_price`=368660@0.97; `comp_5_adjusted_sale_price`=364667@0.97; `comp_6_adjusted_sale_price`=383040@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-DC** — Comp sale within date currency window | 🟢 PASS | — | `comp_1_sale_date`=s06/26;c05/26@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-DC** — Comp sale within date currency window | 🟢 PASS | — | `comp_2_sale_date`=s06/26;c06/26@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-DC** — Comp sale within date currency window | 🟢 PASS | — | `comp_3_sale_date`=s05/26;c04/26@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-DC** — Comp sale within date currency window | 🟢 PASS | — | `comp_4_sale_date`=s06/26;c05/26@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-DC** — Comp sale within date currency window | 🟢 PASS | — | `comp_5_sale_date`=s07/25;c07/25@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-DC** — Comp sale within date currency window | 🟢 PASS | — | `comp_6_sale_date`=s06/26;c05/26@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-GROSS** — Gross adjustment per comp within 25% | 🟢 PASS | — | `comp_1_gross_adj_pct`=14.4@0.97; `comp_2_gross_adj_pct`=15.2@0.97; `comp_3_gross_adj_pct`=15.2@0.97; `comp_4_gross_adj_pct`=19.1@0.97; `comp_5_gross_adj_pct`=20.2@0.97; `comp_6_gross_adj_pct`=20.4@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-PR** — Comp sale price bracket vs subject value | 🟢 PASS | — | `comp_1_sale_price`=385000@0.97; `appraised_value`=373000@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-PR** — Comp sale price bracket vs subject value | 🟢 PASS | — | `comp_2_sale_price`=360000@0.97; `appraised_value`=373000@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-PR** — Comp sale price bracket vs subject value | 🟢 PASS | — | `comp_3_sale_price`=420000@0.97; `appraised_value`=373000@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-PR** — Comp sale price bracket vs subject value | 🟢 PASS | — | `comp_4_sale_price`=360000@0.97; `appraised_value`=373000@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-PR** — Comp sale price bracket vs subject value | 🟢 PASS | — | `comp_5_sale_price`=330000@0.97; `appraised_value`=373000@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-PR** — Comp sale price bracket vs subject value | 🟢 PASS | — | `comp_6_sale_price`=319900@0.97; `appraised_value`=373000@0.97 | Condition satisfied by the extracted value(s). |
| **SCA-PSH** — Subject prior sale analyzed | 🟢 PASS | — | `subject_grid_prior_sale_date`=∅; `effective_date`=2026-06-24@0.97 | Condition satisfied by the extracted value(s). |
| **SIG-1** — Appraiser signed / name present | 🟢 PASS | — | `appraiser_name`=Micheal J Kosto@0.97; `date_of_signature`=∅ | Condition satisfied by the extracted value(s). |
| **SIG-3** — Appraiser licensed in property state | 🟢 PASS | — | `appraiser_license_state`=FL@0.97; `state`=FL@0.97 | Condition satisfied by the extracted value(s). |
| **ST-GEO-COMP** — Appraiser geographic competency | 🟢 PASS | — | `appraiser_license_state`=FL@0.97; `state`=FL@0.97 | Condition satisfied by the extracted value(s). |
| **ST-1** — Site dimensions provided | 🟢 PASS | — | `site_dimensions`=48x100@0.97 | Condition satisfied by the extracted value(s). |
| **ST-2** — Site area has correct unit | 🟢 PASS | — | `site_area`=4800 sf@0.97; `site_area_unit`=∅ | Condition satisfied by the extracted value(s). |
| **ST-3** — Site shape provided | 🟢 PASS | — | `site_shape`=Rectangular@0.97 | Condition satisfied by the extracted value(s). |
| **ST-4** — View UAD compliant and consistent | 🟢 PASS | — | `site_view`=N;Res;@0.97 | Condition satisfied by the extracted value(s). |
| **ST-5** — Zoning compliance | 🟢 PASS | — | `zoning_compliance`=Legal@0.97 | Condition satisfied by the extracted value(s). |
| **ST-6** — Highest & best use is Yes | 🟢 PASS | — | `highest_and_best_use`=Yes@0.97 | Condition satisfied by the extracted value(s). |
| **ST-7** — Utilities marked; private systems addressed | 🟢 PASS | — | `utilities_electricity`=Public@0.97; `utilities_gas`=Public@0.97 | Condition satisfied by the extracted value(s). |
| **ST-9** — Utilities/off-site typical for market | 🟢 PASS | — | `utilities_water`=Public@0.97; `utilities_sewer`=Public@0.97 | Condition satisfied by the extracted value(s). |
| **ST-HBU** — Highest and best use stated and consistent | 🟢 PASS | — | `highest_and_best_use`=Yes@0.97; `highest_best_use_indicator`=∅; `highest_best_use_description`=∅ | Condition satisfied by the extracted value(s). |
| **ST-RIGHTS** — Leasehold property rights disclosure | 🟢 PASS | — | `property_rights`=FeeSimple@0.97; `addendum_text`=∅ | Condition satisfied by the extracted value(s). |
| **I-HOA-PUD** — HOA/PUD consistency | 🟢 PASS | — | `hoa_dues`=∅; `is_pud`=∅ | Condition satisfied by the extracted value(s). |
| **S-11** — Property rights appraised present | 🟢 PASS | — | `property_rights`=FeeSimple@0.97 | Condition satisfied by the extracted value(s). |
| **S-4b** — APN present and plausible | 🟢 PASS | — | `assessors_parcel_number`=A-19-28-19-45O-000003-00024.0@0.97 | Condition satisfied by the extracted value(s). |
| **S-5** — Neighborhood name valid | 🟢 PASS | — | `neighborhood_name`=Fairview Terrace@0.97 | Condition satisfied by the extracted value(s). |
| **S-6** — Census tract format | 🟢 PASS | — | `census_tract`=0003.01@0.97 | Condition satisfied by the extracted value(s). |
| **S-7** — Occupancy status marked | 🟢 PASS | — | `occupant_status`=OwnerOccupied@0.97 | Condition satisfied by the extracted value(s). |
| **S-9** — HOA dues imply PUD marked | 🟢 PASS | — | `hoa_dues`=∅; `is_pud_checked`=∅ | Condition satisfied by the extracted value(s). |
| **ST-FORM-MATCH** — Form type matches property type | 🟢 PASS | — | `design_style`=Florida@0.97 | Condition satisfied by the extracted value(s). |
| **ADD-2** — Comparable selection commentary explains why | ⚪ N/A | — | — | No substantive sales-comparison narrative extracted. |
| **ADD-4** — 1004MC required for FHA/USDA | ⚪ N/A | — | — | Not applicable to this loan/transaction/form type. |
| **ADD-8** — 1004MC condo project section complete | ⚪ N/A | — | — | Not applicable to this loan/transaction/form type. |
| **C-1** — Contract analyzed (purchase) / section blank (refinance) | ⚪ N/A | — | — | Transaction type not purchase/refinance. |
| **C-2a** — Contract price matches purchase agreement | ⚪ N/A | — | — | Not applicable to this loan/transaction/form type. |
| **C-2b** — Contract date matches purchase agreement | ⚪ N/A | — | — | Not applicable to this loan/transaction/form type. |
| **C-3** — Owner-of-record data source present | ⚪ N/A | — | — | Not applicable to this loan/transaction/form type. |
| **C-4** — Concessions consistent and match purchase agreement | ⚪ N/A | — | — | Not applicable to this loan/transaction/form type. |
| **C-5** — Personal property addressed | ⚪ N/A | — | — | Not applicable to this loan/transaction/form type. |
| **C-BUYER-MATCH** — Buyer names match borrower(s) on order | ⚪ N/A | — | — | Not applicable to this loan/transaction/form type. |
| **C-EXEC** — Contract fully executed by all parties | ⚪ N/A | — | — | Not applicable to this loan/transaction/form type. |
| **C-PKG-EXEC** — Contract fully executed (manual verification) | ⚪ N/A | — | — | Not applicable to this loan/transaction/form type. |
| **ORD-ASSIGN-MATCH** — Assignment type in engagement letter matches appraisal report | ⚪ N/A | — | — | Not applicable to this loan/transaction/form type. |
| **ORD-EXEC-STOP** — Unsigned contract blocked by engagement letter policy | ⚪ N/A | — | — | Not applicable to this loan/transaction/form type. |
| **TL-CONTRACT** — Contract date precedes appraisal effective date | ⚪ N/A | — | — | Not applicable to this loan/transaction/form type. |
| **CA-2** — Remaining economic life >= 30 (FHA/VA) | ⚪ N/A | — | — | Not applicable to this loan/transaction/form type. |
| **CA-3** — Cost approach arithmetic and depreciation | ⚪ N/A | — | — | Not applicable to this loan/transaction/form type. |
| **FHA-1** — FHA Minimum Property Requirements confirmed | ⚪ N/A | — | — | Not applicable to this loan/transaction/form type. |
| **FHA-10** — FHA remaining economic life >= 30 | ⚪ N/A | — | — | Not applicable to this loan/transaction/form type. |
| **FHA-12** — FHA well/septic compliance | ⚪ N/A | — | — | Not applicable to this loan/transaction/form type. |
| **FHA-13** — FHA appliances present/operational | ⚪ N/A | — | — | Not applicable to this loan/transaction/form type. |
| **FHA-2** — FHA case number format + match | ⚪ N/A | — | — | Not applicable to this loan/transaction/form type. |
| **FHA-3** — FHA intended use/user statements | ⚪ N/A | — | — | Not applicable to this loan/transaction/form type. |
| **FHA-4** — FHA/HUD certification statement present | ⚪ N/A | — | — | Not applicable to this loan/transaction/form type. |
| **FHA-5** — FHA primary comps within 12 months | ⚪ N/A | — | — | Not applicable to this loan/transaction/form type. |
| **FHA-6** — FHA repairs reported subject-to | ⚪ N/A | — | — | Not applicable to this loan/transaction/form type. |
| **FHA-7** — FHA space heater not primary heat | ⚪ N/A | — | — | Not applicable to this loan/transaction/form type. |
| **FHA-9** — FHA four-side photos | ⚪ N/A | — | — | Not applicable to this loan/transaction/form type. |
| **G-1** — Loan-type consistency (engagement vs appraisal) | ⚪ N/A | — | `loan_type`=∅; `fha_case_number`=∅ | Engagement letter / order form not available. |
| **G-C56** — C5/C6 condition triggers AMC stop | ⚪ N/A | — | — | Not applicable to this loan/transaction/form type. |
| **G-LAVA** — Hawaiian lava zone triggers AMC stop | ⚪ N/A | — | — | Not applicable to this loan/transaction/form type. |
| **G-MFG** — Pre-1976 manufactured home triggers AMC stop | ⚪ N/A | — | — | Not applicable to this loan/transaction/form type. |
| **ORD-CONFLICT** — Engagement letter and XML disagree on order-level facts | ⚪ N/A | — | — | Not applicable to this loan/transaction/form type. |
| **IA-1** — Income approach rent matches rent schedule | ⚪ N/A | — | — | Income approach / rent schedule not developed. |
| **MF-1** — Multi-family requires income approach | ⚪ N/A | — | — | Not applicable to this loan/transaction/form type. |
| **R-INCOME-REQ** — Income approach developed when required | ⚪ N/A | — | `income_approach_value`=362340@0.97; `occupancy_type`=OwnerOccupied@0.97 | Income approach not required for this occupancy type. |
| **R-2b** — Value equals contract price (bias advisory) | ⚪ N/A | — | — | Not applicable to this loan/transaction/form type. |
| **CG-NONARMS** — Non-arms-length comp without commentary | ⚪ N/A | — | — | No non-arms-length distress indicators found in comparables. |
| **SCA-23** — Listing comp adjustment | ⚪ N/A | — | — | no listing/active comparables |
| **SCA-25** — New construction competing comp | ⚪ N/A | — | — | subject is not new construction |
| **SCA-PSH-Q** — Subject sale history analysis is substantive | ⚪ N/A | — | — | No prior sale/transfer within the look-back window; quality check not applicable. |
| **ORD-ENG-DATE** — Engagement letter predates appraisal report | ⚪ N/A | — | — | Not applicable to this loan/transaction/form type. |
| **SIG-2** — Appraiser name matches engagement | ⚪ N/A | — | — | Not applicable to this loan/transaction/form type. |
| **SIG-SUP** — Supervisory appraiser section complete | ⚪ N/A | — | — | Not applicable to this loan/transaction/form type. |
| **SIG-TRAINEE** — Trainee appraiser requires supervisory cosign | ⚪ N/A | — | `appraiser_license_type`=Certificate@0.97; `supervisory_appraiser_name`=∅; `supervisory_appraiser_cert_number`=∅ | Rule does not apply to this loan/form/transaction type. |
| **ST-PRIOR-SVC** — Prior services disclosure | ⚪ N/A | — | `prior_services_indicator`=∅; `prior_services_description`=∅; `addendum_text`=∅ | Rule does not apply to this loan/form/transaction type. |
| **TL-ENG** — Engagement letter date precedes report signature date | ⚪ N/A | — | — | Not applicable to this loan/transaction/form type. |
| **ST-1B** — Site area magnitude plausibility (multi-signal) | ⚪ N/A | — | `site_area`=4800 sf@0.97; `site_area_unit`=∅ | Rule does not apply to this loan/form/transaction type. |
| **ST-FLOOD-CMT** — Flood zone present — marketability commentary required | ⚪ N/A | — | — | Not applicable to this loan/transaction/form type. |
| **ST-ZONE-NC** — Zoning non-conformance commentary | ⚪ N/A | — | `zoning_compliance`=Legal@0.97; `addendum_text`=∅ | Rule does not apply to this loan/form/transaction type. |
| **LISTING-CMNT** — Listing price vs appraised value commentary | ⚪ N/A | — | — | Not applicable to this loan/transaction/form type. |
| **ORD-COBORROWER** — Co-borrower from order appears in appraisal borrower field | ⚪ N/A | — | — | Not applicable to this loan/transaction/form type. |
| **ORD-FORM-MATCH** — Form type in report matches form type ordered | ⚪ N/A | — | — | Not applicable to this loan/transaction/form type. |
| **ORD-INSP-SCOPE** — Ordered inspection type matches report scope of work | ⚪ N/A | — | — | Not applicable to this loan/transaction/form type. |
| **S-1** — Property address matches order form | ⚪ N/A | — | `property_address`=9512 N Brooks St@0.97 | Engagement letter / order form not available. |
| **S-1** — Property address matches order form | ⚪ N/A | — | `city`=Tampa@0.97 | Engagement letter / order form not available. |
| **S-1** — Property address matches order form | ⚪ N/A | — | `zip_code`=33612@0.97 | Engagement letter / order form not available. |
| **S-10a** — Lender name matches order form | ⚪ N/A | — | `lender_name`=Michigan Mutual@0.97 | Engagement letter / order form not available. |
| **S-10b** — Lender address matches order form | ⚪ N/A | — | — | Engagement letter / order form not available. |
| **S-2** — Borrower matches order form | ⚪ N/A | — | — | Engagement letter / order form not available. |
| **USDA-1** — USDA cost approach required | ⚪ N/A | — | — | Not applicable to this loan/transaction/form type. |
