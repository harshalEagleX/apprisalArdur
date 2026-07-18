# Raw Packet Analysis — ground truth vs extractor

History log of reading AMC-supplied source files **raw**, tag by tag, and diffing
what the file actually contains against what SHALqc extracts. Every claim below is
verified against the file, not inferred from code.

---

## Order 1 — ESMI-0049134 (2026-07-18)

**Files**: `testfiles/ESMI-0049134/apprisal/SC5060-0726.XML` (4.1 MB, mostly base64
images/signature), `SC5060-0726.pdf` (2.9 MB), `engagement/EngagementLetter (3).pdf`.
Note: folder is spelled `apprisal` — harmless, intake classifies by content not path.

### What this packet IS
| fact | raw value | consequence |
|---|---|---|
| `REPORT@AppraisalFormType` | `FNM1025` | Small Residential **Income** (2-4 unit), not 1004 URAR |
| `VALUATION_RESPONSE@MISMOVersionID` | `2.6` | errata profile, not `2.6GSE` |
| map file (XML comment) | `ACI.XMLMap.MISMO.v2.6errata` v1.1 | vendor ACI |
| `REPORT@AppraisalPurposeType` | `Purchase` | FHA per addendum |
| `STRUCTURE@LivingUnitCount` | `2` | two units |
| `STRUCTURE@GrossBuildingAreaSquareFeetCount` | `2963` | 1025 uses **GBA**; GLA is per-unit |
| `_UNIT_GROUP` | Unit1 GLA 1340.5 / Unit2 GLA 1622.5 | per-unit rooms+beds+baths+GLA |

Structure inventory: **86 unique element paths, 516 data nodes.**

### Blocks present that the 1004 assumption says shouldn't be
`AMENITY` (Porch/Fireplace×2/Balcony), `ATTIC/ATTIC_FEATURE` (Scuttle Y, Stairs Y),
`CAR_STORAGE/CAR_STORAGE_LOCATION` (Driveway 1, Garage 0, Carport 0),
`SITE_UTILITY` (Electricity/Gas/Water/SanitarySewer all `_PublicIndicator=Y`),
`KITCHEN_EQUIPMENT` (counts, not Y/N), `BASEMENT` (1340.5 sf, `_FinishedPercent=0`).

**→ The "1025 omits these blocks, so scope the rules off" theory is WRONG for this
packet. The data is all there. The extractor simply does not read it.**

### 1025-only blocks (no rules exist for them today)
`INCOME_ANALYSIS` (`GrossRentMultiplierFactor=89.34`,
`ValueIndicatedByIncomeApproachAmount=268020`, `EstimatedMarketMonthlyRentAmount=3000.00`),
`MULTIFAMILY_RENTALS/MULTIFAMILY_RENTAL` (+`RENTAL_UNIT`, `RENTAL_FEATURE`),
`RESIDENTIAL_RENT_SCHEDULE/RESIDENTIAL_RENTAL`, `MULTIFAMILY_RENT_SCHEDULE`,
comp grid `ROOM_ADJUSTMENT@UnitSequenceIdentifier` (per-unit), `_ValuePerUnitAmount`.

### Addendum pointer pattern (confirmed, 10 occurrences)
Form cells literally contain `"See Attached Addendum"`; real prose lives in
`FORM.AppraisalAddendumText` delimited by `-:SECTION NAME:-`. Sections found:
EXTRA COMMENTS, TWELVE MONTH LISTING HISTORY OF SUBJECT PROPERTY, ANALYSIS OF THE
SALES CONTRACT, MARKET CONDITIONS, HIGHEST AND BEST USE, CONDITION OF THE PROPERTY,
PRIOR SALES COMMENTS, COMMENTS ON SALES COMPARISON, CONDITIONS OF APPRAISAL,
COST APPROACH COMMENTS.

Pointer-bearing attributes: `SITE@HighestBestUseDescription`,
`NEIGHBORHOOD@_MarketConditionsDescription`, `SALES_CONTRACT@_ReviewComment`,
`LISTING_HISTORY@ListedWithinPreviousYearDescription`,
`PROPERTY_ANALYSIS[PropertyCondition|QualityAndAppearance]@_Comment`,
`SALES_COMPARISON@_Comment`, `@_CurrentSalesAgreementAnalysisComment`,
`COST_ANALYSIS@_Comment`.

---

## CORRECTION (same session)

A first pass claimed "55% of clean XML never reaches the judge". **That figure was
wrong** — it probed canonical names that don't exist in `config/field_schema.yaml`
(`basement_area` vs the real `basement_gla`, `attic` vs `attic_indicator`,
`occupancy` vs `occupant_status`, …). Re-probed with names verified against the
schema, the extractor reads **91%** of XML-present facts correctly across 15 packets
(86/94). The real defect is narrower and is described below. Lesson recorded: always
verify the canonical name exists before calling a field "missing".

## GAP TABLE — 33 verified facts (superseded by the CORRECTION above)

### Class B — XML path never read (9)
| canonical | raw XML that exists | check it breaks |
|---|---|---|
| `gross_building_area` | `STRUCTURE@GrossBuildingAreaSquareFeetCount=2963` | EQ-48/69 |
| `basement_area` | `BASEMENT@SquareFeetCount=1340.5` | EQ-70 |
| `basement_finish_percent` | `BASEMENT@_FinishedPercent=0` | EQ-44/70 |
| `attic` | `ATTIC_FEATURE` Scuttle=Y, Stairs=Y | EQ-43 |
| `garage_spaces` | `CAR_STORAGE_LOCATION[Garage]@ParkingSpacesCount=0` | EQ-74 |
| `driveway_spaces` | `CAR_STORAGE_LOCATION[Driveway]@ParkingSpacesCount=1` | EQ-74/75 |
| `appraiser_license_expiry` | `APPRAISER_LICENSE@_ExpirationDate=07/31/2027` | EQ-106 |
| `monthly_market_rent` | `INCOME_ANALYSIS@EstimatedMarketMonthlyRentAmount=3000.00` | 1025 income |
| `occupancy` | `PROPERTY@_CurrentOccupancyType=Vacant` | EQ-9 |

### Class A — only PDF garbage exists, correctly suppressed, leaving nothing (9)
| canonical | PDF junk that was suppressed | the real XML value not read |
|---|---|---|
| `gla` | `'calculations,'` | `_UNIT_GROUP@GrossLivingAreaSquareFeetCount` 1340.5/1622.5 |
| `data_source` | `'used, offering price(s),'` | `SALES_CONTRACT@DataSourceDescription='PA/Assessor'` |
| `owner_record_data_source` | same junk | same |
| `seller_concessions` | `'gift or downpayment'` | `SALES_CONTRACT@SalesConcessionAmount=10000` |
| `fireplace_count` | `'2 WoodStove(s) # 0 Driveway'` | `AMENITY[Fireplace]@_Count=2` |
| `appliance_refrigerator` | `'2'` rejected as not-yes/no | `KITCHEN_EQUIPMENT@_Count=2` — **type mismatch, count vs Y/N** |
| `appliance_dishwasher` | `'2'` | same |
| `real_estate_taxes` | `'$ 0.00'` rejected implausible | `_TAX@_TotalTaxAmount=0` — **0 is REAL (Detroit exemption)** |
| `units_count` | `'2'` | `STRUCTURE@LivingUnitCount=2` |

### Also mis-sourced (reads wrong attribute)
- EQ-57 data sources: reads `COMPARABLE_SALE@DataSourceDescription`
  (`'Assessor/Ext. Inspection'`) but the MLS#/DOM is in
  `@DataSourceVerificationDescription` (`'RCMLS#20251062061/DOM 0'`).
- EQ-59 concessions: `SALE_PRICE_ADJUSTMENT[FinancingConcessions]@_Description='Conv;0'`
  IS the zero entry; check reported "no adjustment or zero entry found".
- EQ-17 seller/owner data source: `SALES_CONTRACT@DataSourceDescription='PA/Assessor'` exists.

### Genuinely PDF-only (not in XML at all)
EQ-121 report-type checkbox, EQ-122 exposure time, EQ-123 USPAP prior-services,
EQ-134 license **image** (the license *data* is in XML; the required *copy* is a PDF image).

---

## THE ACTUAL ROOT CAUSE (verified, 2026-07-18)

Comparing **XML-only extraction** vs **post-merge** state, one pattern explains
almost every false REVIEW on this packet:

> For 8 canonical fields the XML value is **ABSENT** (the MISMO attribute is not
> mapped in `xml_extractor`). The field therefore falls through to the **PDF text
> layer**, which on this form yields garbage. Plausibility then **correctly** kills
> the garbage — leaving the check with **nothing**, so the judge can only say
> "not found" → REVIEW / false reject.

| canonical | XML-only | after merge | PDF junk that filled the hole | unmapped MISMO attribute that DOES exist |
|---|---|---|---|---|
| `gla` | ABSENT | SUPPRESSED | `'calculations,'` | `_UNIT_GROUP@GrossLivingAreaSquareFeetCount` (1340.5 / 1622.5) |
| `indicated_monthly_market_rent` | ABSENT | SUPPRESSED | `'5060 FEATURE S Clarendon'` | `INCOME_ANALYSIS@EstimatedMarketMonthlyRentAmount=3000.00` |
| `appliance_refrigerator` | ABSENT | SUPPRESSED | `'2'` (rejected: not Y/N) | `KITCHEN_EQUIPMENT[Refrigerator]@_Count=2` |
| `appliance_dishwasher` | ABSENT | SUPPRESSED | `'2'` | `KITCHEN_EQUIPMENT[Dishwasher]@_Count=2` |
| `real_estate_taxes` | ABSENT | SUPPRESSED | `'$ 0.00'` | `_TAX@_TotalTaxAmount=0` (**0 is REAL** — Detroit exemption) |
| `data_source` | ABSENT | SUPPRESSED | `'used, offering price(s),'` | `SALES_CONTRACT@DataSourceDescription='PA/Assessor'` |
| `seller_concessions` | ABSENT | SUPPRESSED | `'gift or downpayment'` | `SALES_CONTRACT@SalesConcessionAmount=10000` |
| `fireplace_count` | ABSENT | SUPPRESSED | `'2 WoodStove(s) # 0 Driveway'` | `AMENITY[Fireplace]@_Count=2` |
| `units_count` | **OK** | **SUPPRESSED** | — | genuine **merge regression**: XML value lost |

Plus 2 mis-sourced reads (attribute exists, wrong one used):
`COMPARABLE_SALE@DataSourceVerificationDescription` (`'RCMLS#…/DOM 0'`) holds the
MLS#/DOM that EQ-57 says is missing; `SALE_PRICE_ADJUSTMENT[FinancingConcessions]
@_Description='Conv;0'` is the zero entry EQ-59 says is absent.

## CROSS-PACKET STRUCTURE (15 packets read raw)

| form | packets | MISMO | vendors |
|---|---|---|---|
| FNM1004 | 10 | 2.6GSE | a la mode ×6, ACI ×3, ClickFORMS ×1 |
| FNM1004C (manufactured) | 2 | **2.6** errata | a la mode |
| FNM1073 (condo) | 2 | 2.6GSE | a la mode |
| FNM1025 (2-4 income) | 1 | **2.6** errata | ACI |

Path counts: 2.6GSE ≈ 150–169 paths; **2.6 errata ≈ 82–86** (roughly half — leaner
profile, but the *core* blocks are still present).

**Form-scoping theory disproved.** `AMENITY`, `CAR_STORAGE_LOCATION`, `SITE_UTILITY`,
`KITCHEN_EQUIPMENT`, `FLOOD_ZONE`, `_TAX`, `SALES_CONTRACT`, `_HOUSING`,
`_PRESENT_LAND_USE`, `INCOME_ANALYSIS`, `APPRAISER_LICENSE`, `PROJECT`,
`LISTING_HISTORY`, `PROPERTY_ANALYSIS`, `_RECONCILIATION` are present in **every**
form family including 1025. Scoping EQ-32/34/43/45/47/74/75 off for 1025 would
**disable checks that have perfectly good data**. Genuine form differences are only:
`_UNIT_GROUP` (1025 only), and 1073/condo lacking `BASEMENT`/`FOUNDATION`/
`COST_ANALYSIS`/`ATTIC` (1004C also lacks `ATTIC`) — those few should be N/A, not
a whole-form rule split.

## Fix order (by items unblocked per unit of work)
1. **Extend `xml_extractor` to read the 9 unread paths** (Class B) — pure additive mapping.
2. **Fix 3 type/plausibility rules** (Class A): appliance counts ≠ Y/N; tax `0` is a
   real value; `units_count` integer.
3. **Re-source 3 mis-read attributes**: EQ-57 verification desc, EQ-59 financing
   concessions, EQ-17 contract data source.
4. Addendum stitch/route — **already shipped** (see `packet_v2._stitch_addendum`).
5. 1025 income/rental rule pack — new checks, no existing rule covers them.

## IMPLEMENTED (2026-07-18) — verified across all 15 packets

| canonical | now populated | source added |
|---|---|---|
| `gla` | **15/15** | `_UNIT_GROUP@GrossLivingAreaSquareFeetCount` sum → falls back to GBA |
| `gross_building_area` | new | `STRUCTURE@GrossBuildingAreaSquareFeetCount` |
| `real_estate_taxes` | **15/15** | `_TAX@_TotalTaxAmount` + validator now accepts exact `0` |
| `tax_year` | new | `_TAX@_YearIdentifier` |
| `fireplace_count` | **15/15** | new `AMENITY` loop (was never read at all) |
| `air_conditioning_type` | **15/15** | `COOLING@_UnitDescription`/`_IndividualIndicator`/`_OtherIndicator` fallback |
| `market_conditions_commentary` | **15/15** (pointer in only 1) | falls back to `REPORT/FORM/MARKET@NeighborhoodMarketabilityFactorsDescription` |
| `data_source`, `owner_record_data_source` | 9/15 | `SALES_CONTRACT@DataSourceDescription` |
| `seller_concessions` | 8/15 (purchases only) | alias of `SalesConcessionAmount` |
| `appliance_*` | — | `KITCHEN_EQUIPMENT@_Count` (>0 → Yes, 0 → No) |
| `indicated_monthly_market_rent` | 7/15 (income forms) | `INCOME_ANALYSIS@EstimatedMarketMonthlyRentAmount` |
| `units_count` | 13/15 | schema enum widened Two/Three/Four + MISMO synonyms `2/3/4` |

ESMI-0049134 target fields: **12/12 now OK** (all were SUPPRESSED/ABSENT). Total
suppressions on that packet 47 → 31. Suite 248 pass.

New reusable helper: `_POINTER_RX` — detects "See Attached Addendum"-class cells so
a real narrative elsewhere can win the slot.

## STILL-UNMAPPED MISMO ATTRIBUTES (sweep across 15 packets)

Attributes carrying real data that `xml_extractor` never references. Ranked by how
many packets contain them — the remaining backlog:

| pkts | element@attribute | likely check |
|---|---|---|
| 12 | `SITE@HighestBestUseDescription` | EQ-31 (only the Y/N indicator is read, not the narrative) |
| 12 | `COST_ANALYSIS@SiteEstimatedValueComment` | EQ-92 site-value support |
| 11 | `MARKET@NeighborhoodMarketabilityFactorsDescription` | **now used as fallback** |
| 10 | `REPORT@USPAPReportDescription` | EQ-121 — **contradicts "report type is PDF-only"** |
| 10 | `DEPRECIATION@_PhysicalPercent` | cost approach |
| 8 | `CONDITION_DETAIL@GSEImprovementDescriptionType/AreaType/EstimateYearOfImprovementType` | EQ-50 updates/renovations |
| 8 | `COST_ANALYSIS@NewImprovementDepreciatedCostAmount` | cost approach |
| 7 | `CAR_STORAGE@_AttachmentType` | EQ-74 attached/detached garage |
| 7 | `MARKET@MarketTrendsReconciliationComment` | EQ-25 |
| 6 | `FOUNDATION@_ConditionDescription` | full vs partial basement |
| 5 | `ROOM_ADJUSTMENT@BathroomAdjustmentAmount` | grid adjustments |
| 5 | `COMPARISON_VIEW_DETAIL@GSEViewTypeOtherDescription` | view |
| 4 | `REPORT@LoanPurposeType` | EQ-B transaction type |
| 4 | `COMPARISON_DETAIL@GSEBelowGrade*RoomCount` | EQ-70 below-grade rooms |
| 4 | `COOLING@_IndividualIndicator` | **now used** |

Mis-sourced (attribute exists, wrong one read):
`COMPARABLE_SALE@DataSourceVerificationDescription` (holds `RCMLS#…/DOM 0` that
EQ-57 calls missing) and `SALE_PRICE_ADJUSTMENT[FinancingConcessions]@_Description`
(`'Conv;0'` — the zero entry EQ-59 calls absent).

## Log
- 2026-07-18 — read ESMI-0049134 XML raw (86 paths/516 nodes), built 33-fact gap
  table, confirmed 55% of clean XML unread. Prior shipped fixes: grid-bleed length
  guard, MISMO enum synonyms (Nonconforming/Basement), addendum section stitcher +
  content routing.
