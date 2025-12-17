# QC Decision Matrix - Subject & Contract Sections

> **Based on**: `apex rejection (2).docx` and `New Rejections 2018 (1).docx`  
> **Scope**: Subject Section + Contract Section ONLY

---

## Decision Logic

```
┌─────────────────────────────────────────────────────────────┐
│                    DECISION PRIORITY                        │
├─────────────────────────────────────────────────────────────┤
│  1. Any AUTO_FAIL condition → Result: AUTO_FAIL             │
│  2. Any TO_VERIFY condition (no AUTO_FAIL) → Result: TO_VERIFY │
│  3. All conditions pass → Result: AUTO_PASS                 │
└─────────────────────────────────────────────────────────────┘
```

---

## SUBJECT SECTION Rules

### AUTO_FAIL Conditions (Critical - Immediate Rejection)

| Rule ID | Check | Rejection Message | Auto-Checkable |
|---------|-------|-------------------|----------------|
| S-LEGAL-BLANK | Legal Description is blank | "Legal description is required and cannot be blank." | ✅ Yes |
| S-APN-BLANK | Assessor's Parcel # is blank | "Assessor's Parcel Number is required and cannot be blank." | ✅ Yes |
| S-TAX-DECIMAL | RE Taxes contains decimal | "R.E. Taxes field cannot contain decimal values." | ✅ Yes |
| S-NEIGHBORHOOD-INVALID | Neighborhood = "N/A", "None", "Unknown", blank | "The neighborhood name in subject section is mentioned as N/A. Per UAD requirements..." | ✅ Yes |
| S-CENSUS-FORMAT | Census Tract not in XXXX.XX format | "Census Tract format is invalid. Expected format: XXXX.XX" | ✅ Yes |

### TO_VERIFY Conditions (Needs Reviewer Confirmation)

| Rule ID | Check | Rejection Message | What Reviewer Sees |
|---------|-------|-------------------|-------------------|
| S-ADDR-MISMATCH | Property address ≠ Engagement Letter | "Property address does not match with order form." | Expected vs Actual |
| S-CITY-MISMATCH | City ≠ Engagement Letter | "Property City name does not match with order form." | Expected vs Actual |
| S-ZIP-MISMATCH | ZIP (first 5) ≠ Engagement Letter | "Property Zip code does not match with order form. (First 5 digits must match)" | Expected vs Actual |
| S-COUNTY-MISMATCH | County ≠ Engagement Letter | "Property county does not match with order form." | Expected vs Actual |
| S-BORROWER-MISMATCH | Borrower ≠ Engagement Letter | "Incorrect borrower name provided, please correct." | Expected vs Actual |
| S-LENDER-NAME | Lender name ≠ Engagement Letter | "Incorrect Lender name provided, please correct." | Expected vs Actual |
| S-LENDER-ADDR | Lender address incomplete/wrong | "Incomplete lender address provided under company address, please correct." | Expected vs Actual |
| S-APN-MISMATCH | APN ≠ Public Record | "Assessor's Parcel ID does not match with public record, please correct." | Expected vs Actual |
| S-OWNER-MISMATCH | Owner ≠ Public Record | "Owner name does not match with public records, please correct or comment." | Expected vs Actual |
| S-TAX-YEAR-OLD | Tax year > 2 years old | "Tax Year must be within the last 2 years." | Show tax year |
| S-REFI-OWNER-DIFF | Refinance + Owner ≠ Borrower | "Assignment type is 'Refinance'; however, owner name and borrower name are different, please revise or comment." | Owner vs Borrower |

---

## CONTRACT SECTION Rules

### AUTO_FAIL Conditions (Critical - Immediate Rejection)

| Rule ID | Check | Rejection Message | Auto-Checkable |
|---------|-------|-------------------|----------------|
| C-REFINANCE-NOT-BLANK | Is Refinance but Contract section filled | "Assignment is meant for a refinance transaction; per UAD requirements, the contract section should be left blank." | ✅ Yes |
| C-NO-CONTRACT-COPY | Purchase but no contract attached | "Contract copy has not been provided, please provide." | ✅ Yes (check file exists) |
| C-NOT-ANALYZED | Purchase but "Did Analyze" = No | "Contract must be analyzed for purchase transactions." | ✅ Yes |

### TO_VERIFY Conditions (Needs Reviewer Confirmation)

| Rule ID | Check | Rejection Message | What Reviewer Sees |
|---------|-------|-------------------|-------------------|
| C-PRICE-MISMATCH | Contract price ≠ Purchase Agreement | "Price of contract does not match with the Price in the contract copy, please correct." | Report $ vs Contract $ |
| C-DATE-MISMATCH | Contract date ≠ Purchase Agreement | "Contract date does not match purchase agreement." | Report date vs Contract date |
| C-CONCESSION-MISMATCH | Concessions ≠ Purchase Agreement | "Purchase agreement shows concession as $XXX; however, report shows concession as $YYY. Please verify." | Report $ vs Contract $ |
| C-SELLER-NOT-OWNER | Seller ≠ Owner of Record, no comment | "Seller is not the owner of public record. Please provide commentary." | Seller name vs Owner |
| C-VALUE-VS-PRICE | Appraised value significantly differs from contract | "Appraised value is more than contract price, please have a look." | Value vs Price |

---

## AUTO_PASS Conditions

A file gets **AUTO_PASS** when ALL of the following are true:

### Subject Section:
- ✅ Legal Description is not blank
- ✅ APN is not blank
- ✅ RE Taxes has no decimals
- ✅ Neighborhood name is valid (not N/A, None, Unknown)
- ✅ Census Tract format is valid (XXXX.XX)
- ✅ Property address matches Engagement Letter
- ✅ City matches Engagement Letter
- ✅ ZIP (first 5) matches Engagement Letter
- ✅ County matches Engagement Letter
- ✅ Borrower matches Engagement Letter
- ✅ Lender name matches Engagement Letter
- ✅ Tax year is within 2 years
- ✅ If Refinance: Owner = Borrower OR comment exists

### Contract Section:
- ✅ If Refinance: Section is blank
- ✅ If Purchase: Contract copy exists
- ✅ If Purchase: "Did Analyze" = Yes
- ✅ Contract price matches Purchase Agreement
- ✅ Contract date matches Purchase Agreement
- ✅ Concessions match Purchase Agreement

---

## Implementation in Python Rules

Your existing Python rules already map to these:

| Rejection Doc Rule | Python Rule | Status Returned |
|--------------------|-------------|-----------------|
| S-LEGAL-BLANK | S-4 | FAIL |
| S-APN-BLANK | S-4 | FAIL |
| S-NEIGHBORHOOD-INVALID | S-5 | FAIL |
| S-ADDR-MISMATCH | S-1 | FAIL (should be WARNING) |
| S-BORROWER-MISMATCH | S-2 | FAIL (should be WARNING) |
| C-REFINANCE-NOT-BLANK | C-1 | FAIL |
| C-PRICE-MISMATCH | C-2 | FAIL (should be WARNING) |

### Recommended Python Updates

Some rules in your Python code return `FAIL` but should return `WARNING` (TO_VERIFY) based on the rejection docs:

```python
# In subject_rules.py - S-1 should return WARNING not FAIL for mismatches
# Because reviewer can verify if it's a typo vs actual error

if subj.address.strip().upper() != eng.property_address.strip().upper():
    return RuleResult(
        rule_id="S-1",
        status=RuleStatus.WARNING,  # Changed from FAIL
        message="Property address does not match with order form.",
        ...
    )
```

---

## Summary Table

| Decision | Count | Type |
|----------|-------|------|
| **AUTO_FAIL** | 8 rules | Missing required fields, format errors, refinance with contract data |
| **TO_VERIFY** | 11 rules | Data mismatches requiring human verification |
| **AUTO_PASS** | - | All checks pass |

---

## Reviewer Questions (for TO_VERIFY items)

When a file has `TO_VERIFY` status, reviewer sees questions like:

1. **Address Verification**
   > "Does the property address '123 Main St' match the engagement letter address '123 Main Street'?"
   > [YES - Minor difference, acceptable] [NO - Reject]

2. **Borrower Name Verification**
   > "Report shows 'JOHN SMITH' but engagement letter shows 'John A. Smith'. Is this acceptable?"
   > [YES - Same person] [NO - Different person, reject]

3. **Contract Price Verification**
   > "Report shows $350,000 but contract shows $350,500. Is this acceptable?"
   > [YES - Acceptable variance] [NO - Must match exactly, reject]
