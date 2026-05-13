# Appraisal QC — Deep Training: Field Explanation with Logic

> **Purpose**: This document provides deep domain-level understanding of every key field in a residential mortgage appraisal report. It is designed as the implementation companion to the *OPUS Rules Documentation* QC checklist. Where the OPUS doc defines *what to check*, this document defines *why it matters*, *what the risks are*, and *how an automated system should reason about each field*.

---

## Table of Contents

1. [How to Use This Document](#how-to-use-this-document)
2. [Subject Section — Deep Field Logic](#subject-section--deep-field-logic)
   - [Occupancy](#1-occupancy)
   - [Special Assessments](#2-special-assessments)
   - [HOA — Homeowners Association](#3-hoa--homeowners-association)
   - [Property Rights Appraised](#4-property-rights-appraised)
   - [Assignment Type](#5-assignment-type)
3. [Contract Section — Deep Field Logic](#contract-section--deep-field-logic)
   - [Currently Offered for Sale / 12-Month History](#1-currently-offered-for-sale--12-month-history)
   - [Data Sources](#2-data-sources)
   - [List Price](#3-list-price)
   - [Date of Listing / Days on Market (DOM)](#4-date-of-listing--days-on-market-dom)
   - [Is Property Under Contract](#5-is-property-under-contract)
   - [Contract Price](#6-contract-price)
   - [Date of Contract](#7-date-of-contract)
   - [Is Seller the Owner of Public Record](#8-is-seller-the-owner-of-public-record)
   - [Arm's Length Transaction](#9-arms-length-transaction)
   - [Financial Assistance / Concessions](#10-financial-assistance--concessions)
   - [Contract Analysis — Appraiser Comments](#11-contract-analysis--appraiser-comments)
4. [Neighborhood Section — Deep Field Logic](#neighborhood-section--deep-field-logic)
   - [Location Type](#1-location-type)
   - [Built-Up Percentage](#2-built-up-percentage)
   - [Growth Rate](#3-growth-rate)
   - [Property Values Trend](#4-property-values-trend)
   - [Demand / Supply](#5-demand--supply)
   - [Marketing Time](#6-marketing-time)
5. [Site Section — Deep Field Logic](#site-section--deep-field-logic)
   - [Lot Size](#1-lot-size)
   - [Shape](#2-shape)
   - [Cul-de-Sac](#3-cul-de-sac)
   - [Zoning](#4-zoning)
   - [Highest and Best Use](#5-highest-and-best-use)
   - [Flood Zone](#6-flood-zone)
   - [Utilities](#7-utilities)
   - [Adverse Site Conditions](#8-adverse-site-conditions)
6. [Improvements Section — Deep Field Logic](#improvements-section--deep-field-logic)
   - [Year Built vs. Effective Age](#1-year-built-vs-effective-age)
   - [GLA — Gross Living Area](#2-gla--gross-living-area)
   - [Room / Bedroom / Bath Count](#3-room--bedroom--bath-count)
   - [Construction Quality (Q Rating)](#4-construction-quality-q-rating)
   - [Condition (C Rating)](#5-condition-c-rating)
   - [Amenities](#6-amenities)
   - [Garage / Parking](#7-garage--parking)
7. [Risk Reasoning Matrix](#risk-reasoning-matrix)
8. [Cross-Field Consistency Rules](#cross-field-consistency-rules)
9. [AI / Automated System Implementation Notes](#ai--automated-system-implementation-notes)

---

## How to Use This Document

Each field section is structured as:

| Block | Purpose |
|-------|---------|
| **What It Is** | Plain-English definition of the field |
| **Domain Logic** | Why lenders and appraisers care about this field |
| **Types / Values** | Enumerated options with meaning |
| **Risk Level** | Low / Medium / High / Critical |
| **QC Rules (from OPUS)** | Referenced rules from the main checklist |
| **Automated Reasoning** | How an AI/NLP/OCR system should interpret and flag this field |
| **Rejection Triggers** | Conditions that must generate a QC flag or rejection comment |

---

## Subject Section — Deep Field Logic

---

### 1. Occupancy

**What It Is**

The occupancy field records *who is currently living in the property* at the time of the appraisal inspection. It is not about ownership — it is about physical presence.

**Domain Logic**

Lenders use occupancy to assess risk. A property that is owner-occupied is generally well-maintained because the owner has personal incentive to care for it. A property that is tenant-occupied or vacant carries additional underwriting risk.

**Types / Values**

| Occupancy Type | Meaning | Domain Interpretation |
|----------------|---------|----------------------|
| **Owner Occupied** | Owner lives in the property | Primary residence. Lowest risk. Most preferred by lenders. Usually well-maintained. |
| **Tenant Occupied** | A renter lives in the property | Investment / rental property. Lease agreement should exist. Rental income may be a factor. May affect loan type eligibility. |
| **Vacant** | No one is living there | Highest risk category. Potential for deferred maintenance, vandalism, utilities off. Requires extra scrutiny. |

**Risk Level**

| Type | Risk |
|------|------|
| Owner Occupied | Low |
| Tenant Occupied | Medium |
| Vacant | High |

**QC Rules (from OPUS)**

- Rule S-7: Occupant status must be verified against photos
- If **Tenant**: Verify and state lease dates and rental amount in commentary
- If **Vacant**: Must state whether utilities are ON at time of inspection
- Photo cross-check: If report says "Owner Occupied" but photos show empty rooms → Flag
- Photo cross-check: If report says "Vacant" but photos show personal belongings → Flag

**Automated Reasoning**

```
IF occupancy = "Vacant"
  THEN check: utilities_on_stated? → if NO → FLAG (utilities status missing)
  AND check: photo_analysis.occupancy_indicators = "vacant"? → if MISMATCH → FLAG
  AND raise risk_level = HIGH

IF occupancy = "Tenant Occupied"
  THEN check: lease_dates_mentioned? → if NO → FLAG
  AND check: rental_amount_mentioned? → if NO → FLAG

IF occupancy = "Owner Occupied"
  AND photo_analysis.occupancy_indicators = "vacant"
  THEN FLAG: "Photos appear inconsistent with owner-occupied status"
```

**Rejection Triggers**

- Photos show vacancy but report states owner-occupied → Reject with comment
- Photos show occupancy but report states vacant → Reject with comment
- Tenant occupied but no lease dates or rental amount → Flag for revision
- Vacant but no utility status stated → Flag for revision

---

### 2. Special Assessments

**What It Is**

A special assessment is an *extra charge imposed by a local government* on property owners for a specific public improvement project in the area. It is separate from regular property taxes.

**Domain Logic**

When a city or municipality improves infrastructure (roads, sidewalks, drainage, parks) near a property, it may divide the cost among affected property owners. This creates a *mandatory financial obligation* that directly impacts the true cost of owning the property. Lenders need to know about this because it affects the borrower's monthly obligations and therefore their debt-to-income ratio.

**Common Special Assessment Causes**

- Road construction or repaving
- Sidewalk installation
- Drainage improvements
- Utility line extensions
- Parks or landscaping projects
- Sewer system upgrades

**Risk Level**: Medium to High (if unpaid or large amount)

**QC Rules (from OPUS)**

- Rule S-8: Field must not be blank. If none exist → value must be "0"
- If assessments exist → dollar amount AND purpose must be stated
- System must flag if field is blank

**Automated Reasoning**

```
IF special_assessment_field = BLANK
  THEN FLAG: "Special assessment field cannot be blank — must be 0 or stated amount"

IF special_assessment_value > 0
  THEN check: purpose_mentioned? → if NO → FLAG
  AND check: paid_or_unpaid_stated? → if NO → FLAG
  AND check: temporary_or_ongoing_stated? → if NO → FLAG
```

**Rejection Triggers**

- Field is blank → Reject
- Amount present but no explanation of what it is for → Reject with template: *"Please specify what the special assessment of $[amount] is for."*
- Large unpaid assessment with no comment on impact → Flag for escalation

---

### 3. HOA — Homeowners Association

**What It Is**

An HOA (Homeowners Association) is a governing organization for a residential community that manages shared spaces, enforces community rules, and collects fees from property owners to fund maintenance and services.

**Domain Logic**

HOA fees are a *mandatory monthly or annual financial obligation*. Lenders must factor HOA dues into the borrower's total housing payment (PITI + HOA). An unreported or incorrect HOA fee can cause the debt-to-income ratio calculation to be wrong, creating a compliance risk.

**What HOA Controls**

| Category | Examples |
|----------|---------|
| Maintenance | Roads within community, landscaping, cleaning of common areas |
| Amenities | Swimming pool, gym, clubhouse, parks |
| Security | Gated entry, security guards, CCTV |
| Rules | Exterior appearance standards, parking rules, noise restrictions, pet policies |

**HOA Fee Types**

| Frequency | Notes |
|-----------|-------|
| Monthly | Most common |
| Quarterly | Less common |
| Annually | Some communities |

**PUD Connection (Critical)**

If HOA dues are **mandatory**, the **PUD (Planned Unit Development)** checkbox on the subject section **must be marked**. This is a direct cross-field dependency.

**Risk Level**: Medium (if undisclosed or PUD not marked)

**QC Rules (from OPUS)**

- Rule S-9: If HOA dues are mandatory → PUD checkbox MUST be marked
- HOA fees must state "Per Year" OR "Per Month"
- PUD section must be completed if PUD is marked

**Automated Reasoning**

```
IF hoa_dues > 0
  THEN check: PUD_checkbox_marked? → if NO → FLAG
  AND check: frequency_stated (per_month OR per_year)? → if NO → FLAG

IF PUD_checkbox = MARKED
  THEN check: PUD_section_completed? → if NO → FLAG
```

**Rejection Triggers**

- HOA dues present but PUD box not checked → Reject with template: *"HOA dues are noted as $[X] per [year/month]; however, PUD box is not marked. Please revise."*
- HOA dues present but no frequency (per month/per year) stated → Flag

---

### 4. Property Rights Appraised

**What It Is**

This field defines *what legal ownership rights* are being valued in the appraisal. The appraiser is not just valuing bricks and land — they are valuing a bundle of legal rights.

**Domain Logic**

In real estate, value is inseparable from legal rights. Two identical houses can have very different values if one sits on owned land and the other sits on leased land. The appraisal must be clear about which rights are being appraised so the lender knows exactly what they are financing.

**Types**

| Type | Description | Domain Importance |
|------|-------------|------------------|
| **Fee Simple** | Full ownership of land + building + all legal rights. Owner can sell, rent, modify (per zoning). Most common type. | Highest value. Most lender-preferred. No restrictions from any landlord. |
| **Leasehold** | Ownership of the building only. The land is leased from another party (lease may have expiration). | Lower value. More complex. Lender must evaluate remaining lease term vs. loan term. |
| **De Minimis PUD** | A form of PUD ownership where the owner's interest in common areas is minimal. | Treated similarly to Fee Simple for most purposes. |

**Critical Rule**: Only ONE checkbox may be marked. Marking multiple rights is an error.

**Risk Level**: Critical if Leasehold (requires special underwriting review)

**QC Rules (from OPUS)**

- Rule S-11: Only one checkbox may be marked
- If Leasehold: comparables must also be leasehold (Rule SCA-10)

**Automated Reasoning**

```
IF multiple_property_rights_checked = TRUE
  THEN FLAG: "Only one property rights checkbox may be selected"

IF property_rights = "Leasehold"
  THEN check: comparable_sales_are_leasehold? → if NO → FLAG
  AND raise risk_level = HIGH
  AND HOLD for escalation review
```

**Rejection Triggers**

- Multiple checkboxes marked → Error
- Leasehold selected but comparable sales are fee simple without commentary → Flag

---

### 5. Assignment Type

**What It Is**

Assignment type defines *why the appraisal is being done* — the purpose of the valuation engagement.

**Domain Logic**

The assignment type fundamentally changes what sections of the report are required, what data must be analyzed, and what the appraiser's scope of work is. Mixing up assignment logic is one of the most common QC failure points.

**Types**

#### Purchase

| Attribute | Detail |
|-----------|--------|
| Definition | A new buyer is purchasing the property |
| What triggers it | Buyer and seller have agreed on a price (contract exists) |
| Lender need | Verify that the agreed contract price is supported by market value |
| Contract section | **MUST be completed** |
| Key checks | Contract price vs. appraised value; concessions; arm's length |

**QC Focus for Purchase:**
- Contract details present and complete?
- Contract price supported by comparable sales?
- DOM reasonable for the market?
- Any concessions disclosed and properly adjusted?

#### Refinance

| Attribute | Detail |
|-----------|--------|
| Definition | Current owner replaces existing loan with a new loan (not selling) |
| What triggers it | Owner wants better rate, cash-out, or loan modification |
| Lender need | Verify current market value of property |
| Contract section | **MUST be BLANK** — no purchase agreement exists |
| Key checks | No contract data; owner = borrower (if different → comment required) |

**QC Focus for Refinance:**
- Contract section is completely empty?
- If owner of record ≠ borrower → explanation provided?

#### Other

| Attribute | Detail |
|-----------|--------|
| Definition | Any assignment not purchase or refinance (estate valuation, divorce, tax appeal, etc.) |
| Contract section | Typically not required |
| Key checks | Purpose clearly stated; correct form used; any special instructions followed |

**Risk Level**

| Assignment Type | Risk if Mishandled |
|----------------|-------------------|
| Purchase | High — wrong value can cause lending loss |
| Refinance | Medium — contract section errors create compliance issues |
| Other | Varies by specific purpose |

**QC Rules (from OPUS)**

- Rule C-1: Purchase → Contract MUST be analyzed
- Rule C-1: Refinance → Contract section MUST be blank
- Rejection template: *"Assignment is meant for a refinance transaction; per UAD requirements, the contract section should be left blank."*

**Automated Reasoning**

```
IF assignment_type = "Refinance"
  AND contract_section_has_data = TRUE
  THEN FLAG: "Contract section must be blank for refinance assignments"

IF assignment_type = "Purchase"
  AND contract_section_blank = TRUE
  THEN FLAG: "Contract section must be completed for purchase assignments"

IF assignment_type = "Purchase"
  AND owner_of_record ≠ borrower_name
  AND no_comment_provided = TRUE
  THEN FLAG: "Borrower and owner of record differ — comment required"
```

---

## Contract Section — Deep Field Logic

> **Critical Gate**: The entire contract section applies ONLY to Purchase assignments. For Refinance, every field in this section must be blank. An automated system must check assignment type before processing any contract field.

---

### 1. Currently Offered for Sale / 12-Month History

**What It Is**

This field asks whether the property is currently listed for sale, or has been listed within the past 12 months prior to the effective date of the appraisal.

**Domain Logic**

Market exposure is fundamental to establishing credibility of the contract price. If a property was listed publicly, the price was tested against actual market demand. If it was never listed (off-market deal), the price was determined privately — which increases the risk of a price that doesn't reflect true market value.

**Possible Answers and Implications**

| Answer | Implication | Risk |
|--------|-------------|------|
| YES — currently listed | Price is actively market-tested | Low |
| YES — listed in past 12 months | Price has recent market exposure | Low-Medium |
| NO — never listed | Off-market / private deal; no market price test | High |

**QC Rules (from OPUS)**

- Rule S-12: If NO → appraiser must include data source (MLS abbreviated name)
- If YES → must include: DOM, MLS name, MLS #, list/sale price, list/sale date
- If listed but NOT a purchase and market value differs from listing price by >3% → Comment required

**Automated Reasoning**

```
IF currently_offered_for_sale = "No"
  THEN check: data_source_provided? → if NO → FLAG
  AND raise risk_level = MEDIUM (off-market deal)

IF currently_offered_for_sale = "Yes"
  THEN check: DOM_provided? → if NO → FLAG
  AND check: MLS_name_provided? → if NO → FLAG
  AND check: MLS_number_provided? → if NO → FLAG
  AND check: list_price_provided? → if NO → FLAG
  AND check: list_date_provided? → if NO → FLAG
```

---

### 2. Data Sources

**What It Is**

The data source tells us where the appraiser obtained the sale or listing information they used in their analysis.

**Domain Logic**

The reliability of an appraisal is only as strong as its data sources. MLS (Multiple Listing Service) data is considered the gold standard because it is third-party verified, publicly accessible, and contains standardized fields. Data provided directly by an owner or builder is less reliable because it lacks independent verification.

**Source Reliability Hierarchy**

| Source | Reliability | Notes |
|--------|-------------|-------|
| MLS | Highest | Third-party verified, standardized |
| Public Records / Assessor | High | Government records |
| Builder Records | Medium | Unverified, may omit concessions |
| Owner-Provided | Low | No independent verification |

**Automated Reasoning**

```
IF data_source = "Owner" OR "Builder" (only, no MLS)
  THEN FLAG: "Data source relies on non-MLS data — reduced reliability"
  AND raise risk_level = MEDIUM

IF data_source = BLANK
  THEN FLAG: "Data source must be provided"
```

---

### 3. List Price

**What It Is**

The price at which the property was advertised to buyers on the open market.

**Domain Logic**

The list price reveals the seller's initial expectation of value. Comparing the list price to the contract price tells us how negotiations went and whether the seller had to reduce their price (suggesting the market didn't support it) or whether they got full price (suggesting strong demand).

**Analysis Matrix**

| Relationship | Interpretation |
|--------------|---------------|
| Contract Price = List Price | Full price offer — strong demand |
| Contract Price slightly below List | Normal negotiation |
| Contract Price significantly below List | Weak demand, price reduction needed, or property issues |
| Contract Price above List | Multiple offers / bidding war — hot market |

**Automated Reasoning**

```
delta = list_price - contract_price
delta_pct = delta / list_price * 100

IF delta_pct > 10%
  THEN FLAG: "Significant discount from list price — comment on why required"

IF contract_price > list_price
  THEN check: multiple_offers_mentioned? → if NO → FLAG: "Contract above list — comment required"
```

---

### 4. Date of Listing / Days on Market (DOM)

**What It Is**

DOM (Days on Market) is the number of days the property was listed before going under contract.

**Domain Logic**

DOM is one of the most powerful single-number indicators of market health for a specific property. It tells you whether buyers wanted this property quickly, were indifferent, or avoided it. DOM must be interpreted in context of the neighborhood's typical marketing time.

**DOM Interpretation Table**

| DOM Range | Market Signal | QC Action |
|-----------|--------------|-----------|
| 0–10 days | Extremely strong demand | Verify no pressure on price — buyers may have overpaid |
| 10–60 days | Normal, healthy market | Baseline — compare to neighborhood marketing time |
| 60–90 days | Softening — above average | Flag if neighborhood marketing time is under 3 months |
| 90+ days | Weak demand or overpriced | High risk — comment required; verify no price reductions |
| Unknown | Not disclosed | Must state "Unk" with explanation |

**QC Rules (from OPUS)**

- Rule SCA-5: DOM must be provided or stated as "Unk" with commentary
- DOM for majority of comparables should reflect marketing time stated on Page 1
- If inconsistent → commentary required

**Automated Reasoning**

```
IF DOM > 90
  THEN FLAG: "Extended DOM — comment explaining market conditions required"
  AND cross_check: neighborhood_marketing_time matches? → if inconsistent → FLAG

IF DOM = BLANK AND "Unk" NOT stated
  THEN FLAG: "DOM missing — must provide or state 'Unk' with commentary"
```

---

### 5. Is Property Under Contract

**What It Is**

A checkbox confirming whether the buyer has formally agreed to purchase the property.

**Domain Logic**

For a purchase appraisal, the property should always be under contract — otherwise the appraisal would be speculative. This is a fundamental validation checkpoint.

**Automated Reasoning**

```
IF assignment_type = "Purchase"
  AND under_contract = "No"
  THEN FLAG: "Purchase assignment requires property to be under contract"
```

---

### 6. Contract Price

**What It Is**

The final agreed-upon purchase price between buyer and seller, as documented in the fully executed purchase agreement.

**Domain Logic**

The contract price is the single most important data point in a purchase appraisal. The lender ordered the appraisal specifically to verify that the agreed price reflects actual market value. If the appraised value comes in below the contract price, the lender may not finance the full loan amount.

**The Contract Price Triangle**

```
Contract Price
      ↕
Appraised Value   ←→   Comparable Sales
```

All three must be reconciled. If any leg of this triangle is significantly different from the others, commentary is mandatory.

**Scenario Analysis**

| Scenario | Meaning | Action Required |
|----------|---------|----------------|
| Appraised Value = Contract Price | Perfect — lender confidence | None |
| Appraised Value > Contract Price | Buyer is getting a deal | Note, but no issue |
| Appraised Value < Contract Price | Property worth less than agreed | Critical — detailed reconciliation REQUIRED |

**Risk Level**: Critical

**QC Rules (from OPUS)**

- Rule C-2: Must match purchase agreement exactly
- Rule C-1: Appraiser must provide reasoning if appraised value differs from contract price

**Automated Reasoning**

```
variance = abs(appraised_value - contract_price) / contract_price * 100

IF variance > 3%
  THEN FLAG: "Contract price and appraised value differ by [X]% — reconciliation comment required"

IF variance > 10%
  THEN HOLD: "Major value gap — escalate for review"

IF contract_price ≠ purchase_agreement_price (OCR extracted)
  THEN FLAG: "Contract price in report does not match purchase agreement"
```

---

### 7. Date of Contract

**What It Is**

The date the purchase agreement was fully executed — meaning the date of the *last* signature on the contract (buyer or seller, whichever signed last).

**Domain Logic**

An old contract in a rising market is a risk signal. If a buyer agreed to pay $500,000 six months ago when prices were lower, the property may now be worth significantly more — but the appraisal must reflect current market value, not the contract date value. Conversely, in a declining market, an old contract may be above current values.

**Contract Date Rule**

> Contract Date = Date of LAST signature (fully executed). Example: Seller signs March 1, Buyer signs April 2 → Contract Date = April 2.

**Risk Signals**

| Scenario | Risk |
|----------|------|
| Contract < 60 days old | Normal |
| Contract 60–120 days old | Verify market hasn't moved significantly |
| Contract > 120 days old | Comment required — market conditions analysis needed |

**QC Rules (from OPUS)**

- Rule C-2: Contract date = date of last signature
- Rule SCA-8: Commentary required for contract dates beyond 90 days, 6 months, over 12 months

---

### 8. Is Seller the Owner of Public Record

**What It Is**

A verification check confirming that the person selling the property is the legal owner according to public records (county assessor, tax records).

**Domain Logic**

If the seller is not the owner of public record, it is a fraud risk signal. Legitimate exceptions exist (estate sales, corporate sellers, assignment contracts) but they all require explanation. Without verification, the lender risks financing a transaction where the seller has no legal right to sell.

**Scenarios**

| Situation | Meaning | Risk |
|-----------|---------|------|
| Seller = Owner of Record | Standard — seller owns what they're selling | Low |
| Seller ≠ Owner of Record (explained) | Estate, trust, LLC, or assignment — documented | Medium |
| Seller ≠ Owner of Record (unexplained) | Potential fraud, flipping scheme | Critical |

**Automated Reasoning**

```
IF seller ≠ owner_of_public_record
  THEN check: commentary_explains_difference? → if NO → HOLD and FLAG for fraud review
  AND raise risk_level = CRITICAL
```

---

### 9. Arm's Length Transaction

**What It Is**

An arm's length transaction is a sale between two parties who have no pre-existing relationship, are acting independently, and are not under any duress or unusual pressure to complete the sale.

**Domain Logic**

Arm's length transactions are the foundation of market value. When a sale is not arm's length, the price paid does not necessarily reflect what the market would pay — it reflects a personal or business relationship. Lenders require arm's length transactions because non-arm's length prices can be artificially inflated or deflated.

**Non-Arm's Length Examples**

| Scenario | Type | Issue |
|----------|------|-------|
| Father selling to son below market | Family relationship | Price may be discounted |
| Employee buying from employer | Business relationship | Price may be manipulated |
| Distressed seller forced to sell quickly | Duress | Price may be below market |
| REO / Bank-Owned Sale | Institutional motivation | May differ from open market |
| Court-Ordered Sale | Legal compulsion | Price set by legal process |

**Risk Level**: High if non-arm's length (requires detailed explanation)

**Automated Reasoning**

```
IF arms_length = "No"
  THEN check: sale_type_explanation_provided? → if NO → FLAG
  AND raise risk_level = HIGH
  AND verify: comparables_used_are_arms_length? → if NO → FLAG
```

---

### 10. Financial Assistance / Concessions

**What It Is**

Any financial help given to the buyer as part of the transaction — typically from the seller — that reduces the buyer's out-of-pocket costs but may artificially inflate the contract price.

**Domain Logic**

Concessions distort the true price. If a seller agrees to pay $10,000 of the buyer's closing costs, the buyer effectively paid $10,000 less than the contract price. An appraiser must account for this to determine the true market value. Lenders need the "real" price net of concessions for accurate LTV calculations.

**Types of Concessions**

| Type | Example |
|------|---------|
| Seller-paid closing costs | Seller pays $8,000 toward buyer's loan fees |
| Repair credits | Seller credits $5,000 for roof repair |
| Rate buydown | Seller pays to permanently reduce mortgage rate |
| Personal property included | Seller includes furniture, appliances at above-market value |
| Gift funds | Third-party gift contribution |

**Concession Math**

```
True Market Value = Contract Price - Excess Concessions

Example:
  Contract Price:          $500,000
  Seller Concession:        $10,000
  Effective Price Paid:    $490,000
```

**QC Rules (from OPUS)**

- Rule C-4: Yes or No must be marked; if Yes → total dollar amount and description required
- Rule C-5: Personal property items must be identified and their value contribution stated
- Cross-check with purchase agreement for accuracy

**Automated Reasoning**

```
IF concessions_checkbox = BLANK
  THEN FLAG: "Concession checkbox must be marked Yes or No"

IF concessions = "Yes"
  AND (amount = BLANK OR description = BLANK)
  THEN FLAG: "Concession amount and description required when Yes is marked"

IF OCR_purchase_agreement.concession ≠ report.concession
  THEN FLAG: "Concession amount mismatch between report and purchase agreement"
```

---

### 11. Contract Analysis — Appraiser Comments

**What It Is**

The appraiser's written analysis of the purchase contract, including their professional opinion on whether the contract price is reasonable and supported by market data.

**Domain Logic**

The contract analysis is the appraiser's professional narrative connecting the data to a conclusion. It should not merely restate the contract fields — it must explain whether the price makes sense relative to market evidence, note any unusual terms, and explicitly state the sale type (arm's length, REO, etc.).

**Required Elements**

| Element | What to Look For |
|---------|-----------------|
| Sale type stated | "This is an arm's length transaction" / "REO Sale" / etc. |
| Price reasonableness | Commentary on whether contract price reflects market |
| Comparable support | Reference to sales supporting (or not supporting) the price |
| Concession impact | If concessions exist — their effect on value stated |
| Any unusual terms | Escalation clauses, contingencies, personal property |

**NLP Red Flags (Canned Commentary)**

The following phrases indicate generic, non-specific commentary and should be flagged:

- "The contract price reflects market value."
- "Price is supported by comparable sales."
- "No unusual conditions were noted."

Without supporting specifics (which comparables? why? by how much?), these statements are meaningless placeholders.

---

## Neighborhood Section — Deep Field Logic

---

### 1. Location Type

**What It Is**

Classification of the subject property's location environment.

| Type | Definition | Value Impact |
|------|------------|-------------|
| Urban | Dense city area, high walkability, close to commercial/transit | Typically highest price per SF; strong demand |
| Suburban | Residential communities outside city core | Most common loan type; balanced demand |
| Rural | Low density, agricultural or remote areas | Lower comparables pool; more conservative valuation |

**Domain Logic**

Location type sets the baseline expectation for everything else in the report. Urban properties compare to urban sales. Rural properties have different demand dynamics, longer marketing times, and fewer comparable sales. An appraiser calling a dense suburban area "Rural" would be using the wrong analytical lens for the entire report.

---

### 2. Built-Up Percentage

**What It Is**

The percentage of available land in the neighborhood that has already been developed.

| Range | Label | Meaning |
|-------|-------|---------|
| Over 75% | Over 75% | Mature neighborhood; limited new construction land |
| 25–75% | 25–75% | Growing area; mix of developed and undeveloped |
| Under 25% | Under 25% | Early-stage development; mostly vacant land |

**Cross-Check Rule**: Built-up percentage must be consistent with Present Land Use percentages. If land use shows 80% residential, built-up should not be "Under 25%".

---

### 3. Growth Rate

**What It Is**

The rate at which the neighborhood is developing or changing.

| Rate | Meaning | Market Signal |
|------|---------|--------------|
| Rapid | Fast development, new construction | Rising demand; values trending up |
| Stable | Steady, balanced — most common | Predictable market; reliable comps |
| Slow | Minimal new development | Declining interest; potential value risk |

**Risk Logic**

A "Slow" growth designation does not automatically mean values are declining — but it warrants closer review of property value trends and marketing times.

---

### 4. Property Values Trend

**What It Is**

The directional trend of property values in the neighborhood over the recent period.

| Trend | Meaning | QC Implication |
|-------|---------|---------------|
| Increasing | Prices moving up | Time adjustments in sales grid must be POSITIVE |
| Stable | Prices flat | No time adjustment required |
| Declining | Prices falling | Time adjustments in sales grid must be NEGATIVE; higher lender scrutiny |

**Critical Cross-Reference**

This field must be consistent with:
- 1004MC Market Conditions Addendum data
- Time adjustments (or lack thereof) in the Sales Comparison grid
- Marketing time field

If "Increasing" or "Declining" is checked but no time adjustments were made in the sales grid → comment is mandatory.

---

### 5. Demand / Supply

**What It Is**

The balance between buyer demand and available property inventory.

| Status | Meaning | Price Effect |
|--------|---------|-------------|
| Shortage | More buyers than homes available | Prices rising, multiple offers common |
| In Balance | Supply meets demand | Stable prices, normal marketing time |
| Over Supply | More homes than buyers | Prices declining, extended DOM |

**Market Logic**

```
Shortage → DOM ↓, Prices ↑, Marketing Time < 3 months
In Balance → DOM stable, Prices stable, Marketing Time 3-6 months
Over Supply → DOM ↑, Prices ↓, Marketing Time > 6 months
```

---

### 6. Marketing Time

**What It Is**

The estimated time it would take to sell a typical property in the neighborhood.

| Range | Market Label | Risk |
|-------|-------------|------|
| Under 3 months | Hot market | Low |
| 3–6 months | Normal | Low-Medium |
| Over 6 months | Slow market | High — requires scrutiny |

**Cross-Reference Rules**

Marketing time must align with:
- Demand/Supply field
- DOM values of comparable sales
- Property value trend

**Automated Reasoning**

```
IF marketing_time = "Over 6 months"
  AND demand_supply = "Shortage"
  THEN FLAG: "Marketing time and demand/supply are contradictory"

IF marketing_time = "Under 3 months"
  AND property_values = "Declining"
  THEN FLAG: "Marketing time and value trend are contradictory"
```

---

## Site Section — Deep Field Logic

---

### 1. Lot Size

**What It Is**

The total land area of the subject property's site.

**Domain Logic**

Lot size is a direct value driver. Larger lots provide more usable space, privacy, and potential for expansion or improvement. In many markets, land value constitutes a significant portion of total property value. An incorrect lot size can materially impact value.

**Format Rules (from OPUS)**

| Lot Size | Format Required |
|----------|----------------|
| Less than 1 acre | Square feet with "sf" designation |
| 1 acre or more | Acreage with "ac" designation |

---

### 2. Shape

**What It Is**

The geometric configuration of the lot.

| Shape | Description | Value Impact |
|-------|-------------|-------------|
| Regular | Rectangular or square | Full usable area, standard value |
| Irregular | Non-standard shape (flag lot, triangular, L-shaped) | Reduced functional area; slight value adjustment possible |

**If Irregular**: A plat map MUST be provided with the subject property clearly marked (Rule ST-1).

---

### 3. Cul-de-Sac

**What It Is**

A dead-end street that ends in a circular turnaround, with homes arranged around the circle.

**Domain Logic**

Cul-de-sac location is generally a positive value factor:
- Reduced through traffic → safer for families
- More privacy
- Quieter environment
- Often preferred by buyers with children

However, cul-de-sac lots are often pie-shaped (wider at rear, narrow at street) which can reduce functional yard usability.

---

### 4. Zoning

**What It Is**

The legal classification that defines how the property may be used under local government regulation.

**Domain Logic**

Zoning is a legal constraint. The appraisal must reflect the legally permitted use of the property. If the current use of the property does not conform to zoning, the property has a legal non-conformity issue that affects its value and marketability.

**Common Zoning Classifications**

| Code | Typical Meaning |
|------|----------------|
| R-1 | Single-family residential |
| R-2 | Single-family residential (slightly denser) |
| R-3 / R-4 | Multi-family residential |
| C-1 / C-2 | Commercial |
| A-1 | Agricultural |
| M-1 | Light industrial |

**Zoning Compliance Types (from OPUS Rule ST-5)**

| Status | Meaning | QC Action |
|--------|---------|-----------|
| Legal | Current use is fully permitted | No additional comment needed |
| Legal Non-Conforming | Use predates current zoning; grandfathered | Comment required: can it be rebuilt if >50% destroyed? |
| No Zoning | Area has no zoning regulations | Comment required: can it be rebuilt? |
| Illegal | Current use violates zoning | **HOLD — escalate immediately** |

**Critical Rule**: Zoning ≠ current use = major issue requiring immediate escalation

---

### 5. Highest and Best Use

**What It Is**

The legally permissible, physically possible, financially feasible, and maximally productive use of the property — i.e., the best possible use that delivers the highest value.

**The Four Tests (All Must Be Met)**

| Test | Question |
|------|---------|
| Legally Permissible | Does zoning allow this use? |
| Physically Possible | Can the site support this use? |
| Financially Feasible | Does this use generate positive returns? |
| Maximally Productive | Does this use deliver the highest value? |

**Expected Answer**: In the vast majority of residential appraisals, the answer to "Is existing use the highest and best use?" is **YES**.

If the answer is **NO** → This is a critical flag requiring immediate hold and escalation (Rule ST-6).

---

### 6. Flood Zone

**What It Is**

FEMA (Federal Emergency Management Agency) designation indicating the flood risk level for the property.

**Flood Zone Classifications**

| Zone | Risk Level | Insurance | QC Action |
|------|-----------|-----------|-----------|
| Zone X | Minimal risk | Not required | Low risk — standard processing |
| Zone A | High risk — 1% annual chance | **Required** | Comment on marketability impact |
| Zone AE | High risk — detailed study | **Required** | Comment on marketability impact |
| Zone V | Coastal high-velocity flood | **Required** | Comment on marketability impact |
| Zone AH / AO | Shallow flooding | **Required** | Comment on marketability impact |

**Required Elements When in Flood Zone**

- FEMA Map Number and Date (Rule ST-8)
- Flood Map must be included in the report
- Comment on impact to marketability
- Note which comparable sales (if any) are also in flood zone

---

### 7. Utilities

**What It Is**

The availability and type of public or private utilities serving the property.

**Utility Types**

| Utility | Public (Preferred) | Private (Flag) |
|---------|-------------------|---------------|
| Water | Municipal water | Private well |
| Sewer | Public sewer | Septic system |
| Electricity | Public utility | Generator / none |
| Gas | Public utility | Propane / none |

**Private Well / Septic Rules (from OPUS Rule ST-7)**

When private well or septic is present, appraiser must comment on:
1. Is it typical for the market area?
2. Is public connection available (and at what cost)?
3. Impact on marketability and value

**Automated Reasoning**

```
IF water_source = "Private Well" OR sewer_type = "Septic"
  THEN check: commentary_addresses_market_typicality? → if NO → FLAG
  AND check: commentary_addresses_public_availability? → if NO → FLAG
  AND check: commentary_addresses_marketability_impact? → if NO → FLAG
```

---

### 8. Adverse Site Conditions

**What It Is**

Physical or legal conditions affecting the site that may negatively impact value or marketability.

**Common Adverse Conditions**

| Condition | Type | Value Impact |
|-----------|------|-------------|
| Easements | Legal | Restricts use of part of property |
| Encroachments | Physical/Legal | Another party's structure on your land |
| Environmental hazards | Physical | Contamination, underground tanks |
| Proximity to commercial | External | Noise, traffic, visual blight |
| Power lines / towers | External | Safety concern, visual impact |
| High-traffic street | External | Noise, safety, reduced desirability |

**External Obsolescence Rule**

If the property suffers value loss due to external factors (not fixable by the owner), the appraiser must:
1. Explain the obsolescence in the addendum
2. Quantify the marketability impact
3. Provide comparable sales with similar conditions for support

---

## Improvements Section — Deep Field Logic

---

### 1. Year Built vs. Effective Age

**What It Is**

- **Year Built**: The actual calendar year construction was completed
- **Effective Age**: The appraiser's estimate of the property's apparent age based on its current condition — not necessarily its actual age

**Domain Logic**

A house built in 1980 that has been completely renovated may have an effective age of 10 years. A house built in 2010 that has been severely neglected may have an effective age of 30 years. Effective age is a condition-based judgment, not a mathematical calculation.

**Relationship to Condition Rating**

| Condition | Expected Effective Age Logic |
|-----------|------------------------------|
| C1 / C2 | Effective age ≈ 0–5 years (new or nearly new) |
| C3 | Effective age may be lower than actual age (well-maintained or updated) |
| C4 | Effective age ≈ actual age |
| C5 / C6 | Effective age may be higher than actual age (deferred maintenance) |

**Automated Reasoning**

```
IF condition = "C3" AND effective_age > actual_age
  THEN FLAG: "C3 condition suggests effective age should be ≤ actual age — verify"

IF condition = "C5" AND effective_age < actual_age
  THEN FLAG: "C5 condition suggests effective age should exceed actual age — verify"
```

---

### 2. GLA — Gross Living Area

**What It Is**

The total above-grade finished living area of the property, measured in square feet.

**Domain Logic**

GLA is the single most important physical characteristic in determining property value. Appraisers make direct dollar adjustments per square foot when comparable sales differ in GLA from the subject. Even a 50 SF discrepancy can cause a material value difference in high-cost markets.

**GLA Rules**

| Rule | Detail |
|------|--------|
| Above grade only | Basement or below-grade areas are EXCLUDED from GLA |
| Finished only | Unfinished spaces are excluded |
| Sketch must match | GLA in the report must match the floor plan sketch calculation |
| Comparable grid must match | GLA in sales comparison grid must match improvements section |

**High Priority Cross-Checks**

```
GLA (Improvements Section) = GLA (Sales Comparison Grid) = GLA (Sketch Calculation)

IF any mismatch between these three sources
  THEN FLAG: "GLA inconsistency detected across report sections"
```

---

### 3. Room / Bedroom / Bath Count

**What It Is**

The count of total rooms, bedrooms, and bathrooms in the above-grade living area.

**Domain Logic**

Room counts affect functional utility and comparability. A 3-bedroom comparable to a 4-bedroom subject will require a bedroom adjustment in the sales grid. Below-grade bedrooms and bathrooms must NOT be included in the above-grade count.

**Bath Count Convention**

| Bath Type | Count |
|-----------|-------|
| Full bath (toilet + sink + tub/shower) | 1.0 |
| Half bath (toilet + sink only) | 0.5 (reported as .1 in some systems) |
| Three-quarter bath (toilet + sink + shower, no tub) | 0.75 |

---

### 4. Construction Quality (Q Rating)

**What It Is**

A UAD-standardized rating (Q1–Q6) that describes the quality of materials, craftsmanship, and design used in constructing the property.

**Quality Rating Reference Table**

| Rating | Description | Examples |
|--------|-------------|---------|
| Q1 | Unique, architect-designed custom home | One-of-a-kind luxury estate |
| Q2 | Custom quality; high-end upgraded materials | Custom builder, premium finishes throughout |
| Q3 | Improved quality; above-average finishes | Builder upgrades; hardwood, granite, custom cabinetry |
| Q4 | Standard/typical builder quality | Production builder; standard finishes |
| Q5 | Economy construction; minimal features | Low-cost production; basic finishes |
| Q6 | Below minimum standards; basic quality | Substandard construction |

**AI Image Analysis Connection**

Computer vision should analyze:
- Kitchen finishes (countertops, cabinets, appliances)
- Bathroom fixtures and tile quality
- Flooring materials (hardwood vs. laminate vs. carpet)
- Exterior materials (brick, stone, vinyl siding)
- Architectural design complexity

---

### 5. Condition (C Rating)

**What It Is**

A UAD-standardized rating (C1–C6) describing the current physical condition and maintenance level of the property.

**Condition Rating Reference Table**

| Rating | Description | Typical Effective Age |
|--------|-------------|----------------------|
| C1 | Brand new; never occupied; no wear | 0 |
| C2 | Virtually new; recently constructed or fully renovated; minimal wear | 0–5 years |
| C3 | Well-maintained; limited deferred maintenance; normal wear for age | Below or equal to actual age |
| C4 | Adequately maintained; some deferred maintenance; some outdated systems | Near actual age |
| C5 | Obvious deferred maintenance; items affecting livability; cosmetic/functional issues | Exceeds actual age |
| C6 | Substantial damage; major repairs required; items severely affecting safety/livability | Significantly exceeds actual age |

**FHA Threshold**: C5 or C6 typically requires "Subject To" appraisal with cost-to-cure estimates.

**AI Image Processing — Condition Indicators**

| Rating | Visual Indicators to Detect |
|--------|-----------------------------|
| C1/C2 | New materials, pristine surfaces, modern fixtures, no wear visible |
| C3 | Minor scuffs, clean, updated areas, well-painted |
| C4 | Normal wear, some dated finishes, functional but not updated |
| C5 | Peeling paint, damaged flooring, stained ceilings, missing fixtures |
| C6 | Structural damage, mold, broken windows, major system failures visible |

**Health and Safety Flags (Always Escalate)**

- Visible mold or water damage stains
- Cracked or deteriorated foundation
- Missing stair railings
- Exposed electrical wiring
- Damaged roof structure visible
- Fire damage evidence
- Broken exterior windows or doors

---

### 6. Amenities

**What It Is**

Physical features of the property beyond the basic structure that add value or utility.

**Common Value-Adding Amenities**

| Amenity | Value Impact | Notes |
|---------|-------------|-------|
| Fireplace | Positive | Number and type matter |
| Swimming Pool | Market-dependent | Can be positive or neutral depending on area |
| Finished Basement | Positive (separate from GLA) | Reported below-grade finished area |
| Patio / Deck | Positive | Material and size affect adjustment |
| Outbuildings (barn, shed) | Positive if contributory | Must be on sketch; condition matters |
| Solar Panels | Positive | Leased vs. owned affects value significantly |

---

### 7. Garage / Parking

**What It Is**

The type, size, and condition of vehicle storage at the property.

**Garage Types**

| Type | Description |
|------|-------------|
| Attached | Garage connected to main structure |
| Detached | Separate garage building |
| Built-In | Garage under living area |
| Carport | Covered but open-sided |
| None | No vehicle storage |

**UAD Format**: `# of cars;Type` (e.g., `2ga` = 2-car garage attached)

**Important Rule**: If "None" is selected for car storage → all car count fields must be 0 and driveway surface must be blank. A property with a driveway cannot have car storage = "None".

---

## Risk Reasoning Matrix

> Use this matrix for automated risk scoring when multiple field signals are present simultaneously.

| Field Combination | Combined Risk | Recommended Action |
|-------------------|--------------|-------------------|
| Vacant + High DOM (90+) + Declining Values | Critical | Hold; full escalation review |
| Non-Arm's Length + Seller ≠ Owner of Record | Critical | Hold; fraud review |
| Leasehold + No leasehold comparables | High | Reject; request leasehold comps |
| Illegal Zoning Compliance | Critical | Hold immediately; do not process |
| Contract Price >> Appraised Value (>10%) | High | Hold; require reconciliation |
| Flood Zone + No marketability comment | High | Reject; request comment |
| C5/C6 Condition + No "Subject To" designation (FHA) | Critical | Reject; FHA compliance failure |
| Concessions > 5% of contract price + No adjustment | High | Flag; value may be overstated |
| DOM < 5 days + No multiple offer comment | Medium | Flag for review |
| Owner Occupied + Photos show vacancy | High | Reject; request revision |
| Special Assessment > $5,000 + No explanation | Medium | Reject; request explanation |
| Marketing Time > 6 months + Demand = "Shortage" | High | Reject; internal contradiction |

---

## Cross-Field Consistency Rules

> These are automated logic checks that must be performed across multiple fields simultaneously.

```
# Neighborhood ↔ Sales Grid Consistency
IF neighborhood.property_values = "Increasing"
  AND sales_grid.time_adjustments_applied = FALSE
  THEN FLAG: "Increasing market requires time adjustments in sales grid"

# Built-Up ↔ Land Use Consistency
IF neighborhood.built_up = "Over 75%"
  AND land_use.vacant_land_percent > 30%
  THEN FLAG: "Built-up percentage conflicts with high vacant land percentage"

# Condition ↔ Effective Age Consistency
IF condition_rating IN ["C1", "C2"]
  AND effective_age > 10
  THEN FLAG: "Condition rating inconsistent with effective age"

# Occupancy ↔ Photo Analysis Consistency
IF occupancy = "Owner Occupied"
  AND photo_analysis.room_occupancy_indicators = "vacant"
  THEN FLAG: "Occupancy mismatch between report and photos"

# Assignment Type ↔ Contract Section Consistency
IF assignment_type = "Refinance"
  AND contract_section.any_field_populated = TRUE
  THEN FLAG: "Contract section must be blank for refinance"

# HOA ↔ PUD Consistency
IF hoa_dues > 0
  AND PUD_checkbox = FALSE
  THEN FLAG: "HOA dues present but PUD not checked"

# Contract Price ↔ Appraised Value
IF abs(contract_price - appraised_value) / contract_price > 0.03
  THEN FLAG: "Contract price and appraised value differ by more than 3%"

# Marketing Time ↔ DOM Consistency
IF marketing_time = "Under 3 months"
  AND comparable_DOM_average > 90
  THEN FLAG: "Marketing time conflicts with comparable DOM averages"

# GLA Cross-Section Consistency
IF GLA_improvements ≠ GLA_sales_grid OR GLA_improvements ≠ GLA_sketch
  THEN FLAG: "GLA is inconsistent across report sections"

# Flood Zone ↔ Insurance Comment
IF FEMA_flood_zone IN ["A", "AE", "V", "AH", "AO"]
  AND marketability_comment_provided = FALSE
  THEN FLAG: "Flood zone requires marketability comment"

# Zoning Compliance ↔ Current Use
IF zoning_compliance = "Illegal"
  THEN HOLD_AND_ESCALATE: "Illegal zoning compliance — do not process"

# FHA + Condition
IF loan_type = "FHA"
  AND condition_rating IN ["C5", "C6"]
  AND appraisal_not_subject_to = TRUE
  THEN FLAG: "FHA appraisal with C5/C6 condition must be 'Subject To'"
```

---

## AI / Automated System Implementation Notes

### OCR Extraction Priority Fields

| Priority | Field | Source Document | Validation Target |
|----------|-------|----------------|------------------|
| P1 | Contract Price | Purchase Agreement | Report Contract Section |
| P1 | Concession Amount | Purchase Agreement | Report Concession Field |
| P1 | Contract Date | Purchase Agreement | Report Contract Date |
| P1 | Property Address | Engagement Letter | All report pages |
| P1 | Borrower Name | Engagement Letter | Subject Section |
| P2 | HOA Dues | HOA Documents | Subject Section |
| P2 | Special Assessment | Tax Records | Subject Section |
| P2 | Legal Description | County Records | Subject Section |

### NLP Commentary Quality Checks

When analyzing appraiser commentary, flag as "canned/generic" if:
- No property-specific data is referenced (no addresses, no dollar amounts)
- Commentary could apply to any report in any market
- Headers are present but content is only one sentence
- "See attached" or "See addendum" without actual content
- Commentary length < 50 words for complex issues (flood zone, non-arm's length, declining market, etc.)

### Photo AI Processing Workflow

```
For each photo:
  1. Classify photo type (front, rear, interior, kitchen, etc.)
  2. Assess visible condition indicators → map to C1-C6
  3. Detect occupancy indicators (furniture, personal items, empty)
  4. Identify health/safety issues (mold, structural, electrical)
  5. Detect external obsolescence (power lines, commercial, traffic)
  6. Compare detected condition to reported condition rating
  7. Compare detected occupancy to reported occupancy
  8. Flag any mismatches with confidence score
```

### Risk Scoring Framework

Assign each flagged item a severity weight:

| Severity | Weight | Examples |
|----------|--------|---------|
| Critical | 10 | Illegal zoning, fraud indicators, FHA compliance failure |
| High | 7 | Contract/value mismatch >10%, non-arm's length unexplained |
| Medium | 4 | Missing commentary, field inconsistencies, DOM concerns |
| Low | 1 | Minor formatting issues, optional field missing |

```
Total Risk Score = sum of all flag weights

IF Total Risk Score >= 20 → HOLD — Senior Review Required
IF Total Risk Score 10-19 → Condition — Revisions Required
IF Total Risk Score < 10 → Pass with Comments
```

---

> **Document Version**: 1.0
> **Companion To**: Appraisal QC Checklist — OPUS Rules Documentation
> **Purpose**: Domain knowledge implementation guide for deep field-level QC reasoning, automated risk scoring, NLP commentary validation, and AI image processing integration
