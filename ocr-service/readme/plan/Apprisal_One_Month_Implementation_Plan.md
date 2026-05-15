# Apprisal Platform — One Month Implementation Plan
## Adaptive & Future-Proof Document Extraction System

**Prepared for:** EagleX Info Solution PVT LTD  
**Execution Window:** 30 Calendar Days  
**Goal:** Fully functional adaptive extraction system — from regex-only to three-tier intelligent extraction with confidence scoring, AMC profile registry, correction capture, and reviewer-facing dashboard  
**Constraint:** No code in this document. Every instruction is written in plain engineering language.  
**How to Use This Document:** Read the entire plan once before starting anything. Understand the dependency chain. Never start a task whose prerequisite is incomplete. Revisit this plan every morning.

---

## Before Day One — The Prerequisites Checklist

Before the thirty-day clock starts, the following must already be true. If any of these are not true, resolve them before Day One. Starting the plan with unresolved prerequisites is the single fastest way to miss the deadline.

**Hardware must be physically assembled and running.** The Ryzen 5 5600, RTX 3060 12GB, and 32GB RAM must be installed, Ubuntu must be booted, and the machine must be confirmed stable. Do not start implementation on development hardware that will be replaced later in the month.

**All existing code must be in a version control repository.** Every line of existing Python extraction code, every Java Spring Boot file, every Next.js frontend file must be committed and pushed to a remote repository. If this is not done, do it before Day One. The reason is that the implementation plan requires frequent branching, testing, and rollback capability. Without version control, a mistake on Day 12 can destroy weeks of work.

**The existing system must be running end-to-end in its current state.** Before you improve anything, you must be able to demonstrate that the current system — regex extraction, basic QC rules, reviewer dashboard — runs successfully on at least three real documents. This is your baseline. You will measure every improvement against this baseline.

**You must have access to at least twenty real documents from at least two different AMC formats.** These are your test corpus. Without real documents, you cannot measure whether your extraction improvements actually work. Collect these before Day One and store them safely. These documents are the most valuable asset you have for this project.

**All team members must read both the Architecture Guide and the Engineering Thinking Guide completely before Day One.** Not skim. Read. Every person who will write code for this project must understand the five-layer architecture, the three-tier extraction model, and the principle of separation of concerns before they write a single line.

**Ollama must be installed and the llama3:8b-instruct-q4_0 model must be downloaded and running locally.** LLM inference is the most time-sensitive component to get working because it takes time to download, configure, and verify. Do not let this block you on Day 8. Resolve it before Day One.

---

## The Thirty-Day Structure

The month is divided into five weeks, each with a specific theme and a specific set of deliverables. Each week builds entirely on the previous week. Nothing in Week Two is possible without Week One being complete.

**Week One — Foundation and Schema (Days 1–6)**  
Purpose: Build everything that everything else depends on. No extraction intelligence is added this week. Only architecture, data structures, and measurement infrastructure.

**Week Two — Layer One Complete (Days 7–12)**  
Purpose: The entire document ingestion and preprocessing pipeline must be working adaptively and correctly by the end of this week. OCR, normalization, table detection, and document classification must all be complete.

**Week Three — Layer Two Complete (Days 13–20)**  
Purpose: All three extraction tiers must be working and their outputs must be merged using confidence scores. This is the core intelligence week.

**Week Four — Layer Three and Four Complete (Days 21–26)**  
Purpose: Context-aware validation, cross-document consistency checking, AMC profile registry, and confidence-driven reviewer routing must all be working.

**Week Five — Layer Five, Integration, and Hardening (Days 27–30)**  
Purpose: Correction capture, feedback mechanism, end-to-end integration testing, error handling audit, and production readiness verification.

---

## Week One — Foundation and Schema
### Days 1 through 6

The entire purpose of this week is to build the invisible infrastructure that all future intelligence depends on. At the end of this week, you will have nothing new that is user-visible. You will have everything that makes user-visible improvements possible. Do not rush this week. A weak foundation means every layer above it is unstable.

---

### Day 1 — Field Schema Construction

The field schema is the single most important document you will produce in this entire project. Everything else references it. Spend the entire first day on it.

**What the field schema must contain.** For every field that your platform extracts from every document type, the schema must define the following. The canonical field name — this is the single authoritative name for the field and it never changes regardless of how different documents label it. For example, the canonical name might be "borrower_full_name" even though different documents use "Borrower Name," "Client Name," "Applicant," or "Customer." The data type — is this a string, a date, a currency amount, a numeric measurement, a UAD code, a boolean, or an enumerated list of allowed values? The required or optional status — is this field mandatory for a valid QC report, or is it supplementary information? The allowed value range or allowed value set — for a date field, what is the earliest plausible date and the latest plausible date? For a UAD condition code, what are the six allowed values? For a currency field, what is a reasonable minimum and maximum for the geographic market? The list of all known synonymous labels — every label variant you have ever seen used for this field, across all AMC formats you currently process. The source document authority — for each field, which document type is the most authoritative source? The borrower name is most authoritatively found in the engagement letter. The contract price is most authoritatively found in the sales contract. The effective date is most authoritatively found in the appraisal report.

**Document types to cover.** The schema must include sections for engagement letters, appraisal reports covering the full URAR UAD 1004 form, sales contracts, and QC checklist documents. For each document type, list every extractable field.

**How to build it today.** Start by printing or opening the actual documents you collected before Day One. Go through each document field by field. For every field you see, write its canonical name, its data type, and the label used in that specific document. After you have gone through all documents, consolidate fields that represent the same concept across different documents. The result is your field schema.

**What format to store it in.** Store the field schema as a structured configuration file that can be read by your Python extraction service. It must not be hardcoded inside any Python function. It must be a file that can be edited and reloaded without restarting any service. Use a format that is human-readable and easily editable.

**What done means for Day 1.** The field schema covers every field your platform currently extracts, plus any fields you have identified in your real document corpus that are not currently being extracted. Every field has all required attributes. The schema is stored as an external file, not hardcoded. A second team member has reviewed it and confirmed it is complete and accurate.

---

### Day 2 — Structured Extraction Result Format

Today you change how your extraction code reports its results. You are not changing what it extracts or how it extracts it. You are only changing what it returns.

**What the structured result must contain.** Every extraction attempt, for every field, must now return a result object that contains the following pieces of information. The canonical field name from the schema. The extracted value — the actual text or number or date that was found. The raw source text — the full text passage from which the value was extracted, not just the value itself. This is essential for debugging and for training data. The extraction method identifier — a label that says exactly which method found this value. Initially this will be a specific regex pattern name or function name. Later it will be "tier_one_llm," "tier_two_embedding," or "tier_three_pattern." The confidence score — initially this will be a simple value: one hundred for an exact pattern match, seventy-five for a fuzzy match, zero for not found. These initial values will be calibrated later but you need the field to exist now. The page number where the value was found. The character position within the page text where the value was found. A flag indicating whether the value was found or not found.

**Why this matters today.** When you add the LLM extraction tier in Week Three, it will return results in this same format. When you add the embedding tier, it will also return results in this same format. The merging logic in Week Three will combine results from all three tiers using this format. If you do not establish this format today, you will spend two or three days in Week Three trying to reconcile incompatible result formats from different extraction methods.

**Modifying your existing code.** Go through every extraction function in your existing Python code. Change each one so that instead of returning a raw string value, it returns a result object in the format described above. The logic inside the function does not change. The input the function receives does not change. Only the output format changes.

**Testing Day 2 work.** Run your existing extraction on three real documents. Verify that every field extraction returns the new format. Verify that the source text is being captured correctly. Verify that the page number is accurate.

**What done means for Day 2.** Every extraction function in the Python service returns the structured result format. Running the existing extraction pipeline on a real document produces a complete set of structured results with all required fields populated. The confidence score field exists and has an initial value for every result. No extraction logic has changed — only the output format.

---

### Day 3 — Database Schema for Training Data, Corrections, and AMC Profiles

Today you design and create the database structures that will store correction data, AMC profiles, and extraction results. These database tables will be used by every component built in Weeks Two through Five.

**The extraction results table.** This table stores the output of every extraction attempt for every document ever processed. It must store the document identifier, the AMC identifier, the document type, the field name, the extracted value, the raw source text, the extraction method identifier, the confidence score, the page number, the character position, the timestamp of extraction, and the model version identifier that was active when the extraction was performed. Every row in this table is a permanent record. Rows are never deleted, only superseded by newer extraction attempts for the same document and field.

**The corrections table.** This table stores every correction ever made by a human reviewer. It must store the document identifier, the field name, the original extracted value, the corrected value, the reviewer identifier, the timestamp of the correction, the reason category for the correction — wrong label matched, OCR error, value in wrong location, completely absent from document, ambiguous context, other — and a free text explanation field where the reviewer can write a detailed explanation. It must also store the extraction result identifier that this correction relates to, so you can join from a correction back to the original extraction attempt and understand exactly what the system did wrong.

**The AMC profiles table.** This table stores one row per AMC. It stores the AMC identifier, the AMC name, the date the profile was created, the date it was last updated, a document count showing how many documents from this AMC have been processed, and a maturity level — new, developing, or mature — based on how many documents have been processed. The profile also stores a serialized fingerprint object containing the keyword signatures and structural characteristics of this AMC's documents. The profile stores a serialized terminology mapping containing all known AMC-specific term translations. And it stores AMC-specific confidence threshold overrides for fields where this AMC's documents consistently require different thresholds than the default.

**The AMC template versions table.** This table stores one row per known template version for each AMC. As AMCs update their document formats, new rows are added here. Each row stores the AMC identifier, a version label, the date this version was first seen, the structural fingerprint that identifies this version, and whether this version is currently active.

**The field schema table.** Rather than relying only on the file created on Day 1, also store the field schema in the database. This allows you to query it programmatically and to track changes to the schema over time.

**Creating these tables.** Write the migration scripts and run them against your PostgreSQL database today. Verify that all tables are created correctly. Insert one test row into each table manually to verify the structure is correct.

**What done means for Day 3.** All database tables exist in PostgreSQL. Each table has been verified by manually inserting and querying test data. Every column in every table has a clear, documented purpose. The team understands what each table stores and why.

---

### Day 4 — Test Set Construction and Baseline Measurement

Today you build the measurement infrastructure that will tell you whether your extraction improvements are actually working.

**What the test set is.** The test set is a collection of real documents paired with their correct field extractions. For each document in the test set, you must manually verify every extracted field and record the correct value. This is labor-intensive work but it is the foundation of everything else. Without a test set, you are building in the dark.

**How many documents you need.** Aim for a minimum of fifteen documents across all document types and AMC formats you currently support. Ideally five engagement letters from at least two different AMC formats, five appraisal reports including at least one scanned document, three sales contracts, and two QC documents.

**How to create the correct extractions.** For each document in the test set, run your current extraction pipeline and capture the results. Then manually review every extracted field against the actual document. For each field, record whether the extracted value is correct, incorrect, or missing. For incorrect and missing fields, record the correct value. Store all of this in a structured format in the database.

**Running the baseline measurement.** Using the test set, run your current extraction pipeline on every test document and measure the following. Field-level accuracy: for each canonical field name, what percentage of test documents have that field extracted correctly? Document-level accuracy: for each document, what percentage of all required fields are extracted correctly? AMC-level accuracy: for each AMC represented in your test set, what is the overall accuracy rate?

**Recording the baseline.** Store these baseline numbers in a simple tracking document that you will update at the end of each week. This tracking document is how you prove that each week's work actually improved the system. The baseline is your starting point. Everything you build in the coming three weeks should move these numbers upward.

**Common baseline findings.** When teams do this exercise for the first time, they almost always discover that their current accuracy is lower than they believed. Fields that you thought were working reliably often fail on documents from the second AMC format. OCR errors that you did not know existed show up in the source text. Fields that appear to be extracted correctly turn out to have subtle errors — a date that is off by one day because of OCR misreading, or a dollar amount that is missing a digit. These discoveries are valuable. They tell you exactly where to focus your extraction improvements.

**What done means for Day 4.** Fifteen or more test documents with verified correct extractions exist in the database. Baseline accuracy measurements have been taken and recorded for field-level, document-level, and AMC-level accuracy. Every team member knows what the baseline numbers are.

---

### Day 5 — Correction Capture Interface in the Reviewer Dashboard

Today you add the ability for reviewers to record corrections through the Next.js frontend. This is the only user-visible change in Week One.

**What the correction interface must do.** For every extracted field displayed to the reviewer, the interface must show the extracted value alongside the source text from which it was extracted. When a reviewer changes an extracted value, the interface must capture the change and send it to the Java backend, which stores it in the corrections table created on Day 3. The interface must also show the confidence score for each field so reviewers know which fields the system is uncertain about.

**The reviewer experience.** Fields with high confidence should be visually presented in a way that allows rapid confirmation — the reviewer's eye should be able to scan them quickly and confirm without deep scrutiny. Fields with low confidence should be visually distinguished — a different background color, a warning indicator, or a prominent flag — so reviewers know to examine them carefully. When a reviewer clicks on a field to correct it, a correction reason selector should appear offering the reason categories defined in the corrections table schema. The reviewer selects the reason and optionally types an explanation, then saves the correction.

**The Java backend endpoint.** The Java service needs a new endpoint that receives a correction submission from the frontend. This endpoint validates the input, stores the correction in the corrections table, and updates the extraction result record to mark the field as having been reviewed and corrected.

**What to explicitly not build today.** Do not build any logic that uses corrections to update extraction patterns. Do not build any learning mechanism. Do not build any automatic feedback processing. Today is only about capturing corrections. The use of corrections comes in Week Five.

**What done means for Day 5.** A reviewer can open a processed document in the dashboard, see confidence scores alongside extracted values, click on any field to correct it, select a correction reason, and save the correction. The correction appears in the database with all required fields populated including the original value, the corrected value, the reason, and the source extraction result identifier.

---

### Day 6 — Week One Verification and Buffer

Use today to verify that everything built this week is working correctly together, to fix any problems discovered during verification, and to prepare for Week Two.

**Verification activities.** Run the full extraction pipeline on three real documents and verify that results are stored in the extraction results table with all required fields. Make a correction through the reviewer interface and verify it appears correctly in the corrections table. Run the baseline measurement again and confirm the numbers match what was recorded on Day 4. Review the field schema file and confirm that every field in your test documents is covered.

**Buffer purpose.** In any realistic development schedule, something takes longer than expected. Day 6 is the buffer that absorbs that overrun from Days 1 through 5 without pushing into Week Two. If all of Days 1 through 5 were completed exactly on time, use Day 6 to write documentation for the structures built this week — the field schema, the database tables, the extraction result format, and the correction capture interface. This documentation will be essential when you are tired and context-switching in Week Three.

**Week One exit criteria.** Before moving to Week Two, confirm that all of the following are true. The field schema covers all document types and all extractable fields. Every extraction function returns the structured result format. All database tables exist and have been tested. The test set has at least fifteen documents with verified correct extractions. Baseline accuracy numbers are recorded. The correction capture interface is functional in the reviewer dashboard.

If any of these are not true at the end of Day 6, do not start Week Two until they are. The Day 6 buffer exists precisely to handle this situation.

---

## Week Two — Layer One Complete
### Days 7 through 12

This week you make the document ingestion and preprocessing layer fully adaptive. By the end of this week, your system must correctly handle scanned documents, natively digital documents, and hybrid documents. It must classify documents by type. It must normalize text reliably. It must extract table structures in a format that downstream extraction can use.

---

### Day 7 — Adaptive OCR Strategy

Today you upgrade the OCR component so that it makes intelligent decisions about which processing path to use for each page, rather than applying a fixed strategy to all pages.

**The page-level assessment logic.** For each page of every incoming document, the system must first attempt direct text extraction using PyMuPDF. It then counts the words in the extracted text. If the word count is above a threshold — start with one hundred words as your threshold, adjust based on testing — the page is treated as a natively digital page and no image processing is needed. If the word count is below the threshold, the page is treated as a scanned page and the image preprocessing pipeline is invoked.

**The image quality assessment.** When a scanned page is detected, before running the full preprocessing pipeline, assess the image quality. Measure the estimated resolution of the scanned image by examining its pixel dimensions relative to the standard page size. If the resolution is below two hundred DPI equivalent, record a low-quality flag and increase the aggressiveness of the preprocessing steps. If the resolution is above four hundred DPI equivalent, downsample the image to three hundred DPI before processing to reduce computation time without losing accuracy.

**The preprocessing pipeline for scanned pages.** Apply these steps in order, checking the text quality after each step to decide whether additional steps are needed. First, grayscale conversion — always apply this. Second, Gaussian denoising — apply this when the image has visible noise or JPEG compression artifacts, which you can detect by measuring pixel variance in blank regions of the page. Third, Otsu thresholding — apply this to improve character contrast. Fourth, deskew correction — apply this when the page shows a measurable rotation angle, which you detect by analyzing the angle of text lines relative to horizontal. Fifth, table line removal — apply this when the page shows evidence of ruled lines, which you detect by looking for long horizontal and vertical continuous edge segments.

**Persisting OCR metadata.** For every page processed, store the following alongside the extracted text in the database. The OCR path used — direct extraction or image preprocessing. The image quality assessment results. Which preprocessing steps were applied. The overall text quality score — an estimate of how clean and accurate the extracted text is. This metadata will be used by the confidence scoring system to reduce confidence for fields extracted from low-quality OCR output.

**Testing Day 7 work.** Run your five appraisal report test documents through the new adaptive OCR. At least one of them should be a scanned document. Verify that the scanned document takes the image preprocessing path. Verify that the digital documents take the direct extraction path. Verify that the OCR metadata is stored correctly for each page. Compare the text quality of the extracted output to the baseline you collected on Day 4.

**What done means for Day 7.** The OCR component makes per-page decisions about processing path. Scanned pages go through image preprocessing. Digital pages skip directly to text output. OCR metadata is stored for every page. The text quality of scanned page output is measurably better than it was before, as evidenced by word count and character recognition accuracy in your test documents.

---

### Day 8 — Text Normalization Pipeline

Today you build the text normalization layer that sits between raw OCR output and the extraction layer.

**The normalization transformations to implement.** These must be implemented as individual, independent transformations applied in sequence. Each transformation takes text as input and returns text as output. This independence is essential — it allows you to add, remove, or reorder transformations without affecting the others.

Whitespace normalization collapses all sequences of multiple spaces into a single space, converts all tab characters into spaces, and normalizes line endings to a consistent format. It also removes leading and trailing whitespace from each line while preserving the line break structure of the document.

OCR character confusion correction uses a lookup table of common OCR character confusions specific to appraisal documents. The letter O confused with the digit zero in numeric contexts. The letter l confused with the digit one or the letter I in mixed contexts. Adjacent characters incorrectly merged together, particularly in currency amounts where the dollar sign may merge with the first digit. Characters incorrectly split apart, particularly in long property addresses where a single character may be rendered as two adjacent characters. Build this confusion lookup table based on errors you actually observed in your test set during Day 4.

Special character normalization converts typographic characters to their plain equivalents. Curly opening and closing quotation marks become straight quotation marks. The em dash and en dash become a hyphen. The non-breaking space character becomes a regular space. The ellipsis character becomes three periods. Fraction characters like the one-half and one-quarter glyphs become their text equivalents.

Numeric pattern normalization ensures that currency amounts, percentages, and measurements are represented consistently. Currency amounts should always have a dollar sign, no space between the sign and the first digit, commas as thousands separators, and a period as the decimal separator. Percentages should always have the percent sign immediately after the last digit. Measurements should have a space between the numeric value and the unit abbreviation.

Date format normalization converts all date representations to a single consistent internal format. Dates expressed as month-day-year with slashes, with dashes, with dots, spelled out as month name followed by day and year, or in other common formats should all be normalized to the same internal representation before being stored.

**Recording transformation history.** For every normalization transformation applied to any piece of text, store a record of what the original text was and what the transformation produced. This transformation history is stored alongside the OCR metadata in the database. It is the audit trail that allows you to explain to a reviewer exactly what the system did to arrive at a particular extracted value.

**What done means for Day 8.** All normalization transformations are implemented as independent pipeline stages. Every transformation records what it changed. Running your test documents through the normalization pipeline produces cleaner text than the raw OCR output. The transformation history is stored and queryable in the database.

---

### Day 9 — Document Classification

Today you implement the document classification component that identifies what type of document is being processed before any extraction begins.

**The two-level classification system.** Broad category classification identifies whether a document is an engagement letter, an appraisal report, a sales contract, a QC checklist, or an unknown supporting document. Template-level classification goes further and attempts to identify which specific AMC's template is being used, or which version of the URAR form is present.

**How broad category classification works.** Each document type has a set of keyword signatures — words and phrases that reliably appear in that document type and not in others. For engagement letters, keywords include phrases like "engagement," "fee schedule," "appraiser assignment," and "AMC." For appraisal reports, keywords include "URAR," "UAD," "subject property," "comparable sale," and "appraised value." For sales contracts, keywords include "purchase price," "closing date," "seller," "buyer," and "earnest money." For QC checklists, keywords include "quality control," "deficiency," "condition rating," and "compliance."

Build the keyword signature lists based on careful reading of your real test documents. Do not guess what keywords appear in each document type. Read the actual documents and note the words and phrases that are specific to each type.

Apply the keyword signatures by counting how many keywords from each document type's signature list appear in the first two pages of the document. The document type with the highest match count is the classification result. Store the match counts alongside the classification result so you can tune the thresholds later.

**How template-level classification works.** Once broad category is known, compare the document's structural fingerprint against the AMC profiles stored in the database from Day 3. The structural fingerprint includes the approximate number of pages, the distribution of text across the page, the presence or absence of specific section headers, and the density of tabular content. Compare the incoming document's fingerprint against all known AMC template version fingerprints and select the closest match. If the closest match falls below a similarity threshold, classify the AMC as "unknown" and create a new profile skeleton in the AMC profiles table.

**What done means for Day 9.** Every document that enters the system is classified by type before any extraction begins. The classification result is stored in the database. Your test documents are all classified correctly. When you process a document from an AMC that has no profile yet, a new skeleton profile is created automatically.

---

### Day 10 — Table Detection and Linearization

Today you build the table extraction component. This is the most technically challenging day of Week Two.

**What table detection must accomplish.** The component must identify regions of extracted text that contain tabular data, understand the row and column structure of those tables, and convert the table into a structured representation where each cell is labeled with its row identifier and column identifier. The output is not raw text. It is a structured table object that subsequent extraction code can query by row and column.

**The three detection strategies.** These three strategies are applied in order, with each building on the previous.

Rule-based line detection examines the document image for horizontal and vertical lines that form table borders and cell boundaries. When lines are found, use them to determine table boundaries and identify cells. This works well for bordered tables with clear visual structure.

Whitespace-based column detection analyzes the horizontal distribution of whitespace in paragraphs of text. When you find regions of consistent whitespace that separate columns of text, you have found a table structure even if no border lines are drawn. Measure the positions of whitespace gaps across multiple consecutive lines. If the same gaps appear consistently at the same horizontal positions across several lines, those positions are column separators. This works well for whitespace-aligned tables without borders.

Header-based structure inference looks for rows of text that appear to be column headers — typically bold, capitalized, or otherwise visually distinct from the data rows. Once column headers are identified, use them to label all cells in the corresponding column. For comparable sale tables, the headers are typically "Comparable 1," "Comparable 2," and "Comparable 3." Use these headers as the column identifiers in the structured table output.

**The structured table output format.** Every detected table must be converted to a structured representation. Each cell in the table has a row identifier, a column identifier, and a text value. The row identifier comes from the row header when present, or from the sequential row number when no row header exists. The column identifier comes from the column header when present, or from the sequential column number when no column header exists. Store this structured table representation in the database alongside the other OCR and normalization output.

**Handling table extraction failures gracefully.** Table detection will sometimes fail. The table structure may be too ambiguous, the OCR quality may be too poor, or the table may use a format that none of the three detection strategies handles well. When this happens, do not produce incorrect structured output. Instead, produce a table with a failure flag and store the raw text of the table region. The downstream extraction layer will see the failure flag and fall back to text-based extraction for that region, which will have lower confidence but will not produce structurally incorrect results.

**What done means for Day 10.** All three table detection strategies are implemented. Running your test appraisal reports through the table detection produces correct structured table objects for the comparable sale grids, adjustment tables, and fee schedules. Tables that cannot be reliably detected are flagged as failures rather than producing incorrect structured output.

---

### Day 11 — Synonym Expansion and Fuzzy Matching for Tier Three

Today you upgrade your existing regex-based extraction patterns with synonym expansion and approximate matching. This is the Tier Three extraction upgrade described in the architecture guide.

**Building the synonym list from the field schema.** On Day 1, you recorded all known synonymous labels for every field in the field schema. Today you connect that list to your extraction code. For each canonical field name, your extraction code must now try every synonym in the list, not just the single label it previously used.

**Replacing exact matching with approximate matching.** In your existing extraction code, wherever you match a label string exactly, replace that exact match with an approximate match. Approximate matching works by computing the similarity between the candidate text and the known label, rather than requiring character-for-character equality. Set a similarity threshold — start at eighty-five percent — below which a match is rejected and above which it is accepted. Test this threshold on your test documents and adjust it based on whether it produces too many false positives or too many missed matches.

**Case normalization before matching.** Before any label matching occurs, convert both the candidate text and the known label to lowercase and remove punctuation. This means "Borrower Name:" and "BORROWER NAME" and "borrower name" are all treated as the same label.

**Updating confidence scores for fuzzy matches.** An exact label match gets the full confidence score of one hundred. A fuzzy match at eighty-five percent similarity gets a confidence score of seventy-five. A fuzzy match at ninety-five percent similarity gets a confidence score of eighty-eight. Define a linear interpolation between the similarity percentage and the confidence score. The exact label for this relationship will be calibrated against your test set later.

**What done means for Day 11.** Every extraction pattern in your existing code uses synonym expansion and approximate matching. Running your test documents through the upgraded Tier Three extraction shows improved accuracy over baseline for documents that use label variants not previously handled. Confidence scores differ between exact matches and fuzzy matches.

---

### Day 12 — Week Two Verification and Measurement

Run the full Layer One pipeline — adaptive OCR, normalization, document classification, table detection, and upgraded Tier Three extraction — on all fifteen test documents. Measure accuracy against the test set and record the results.

**Expected accuracy improvement.** After Week Two, you should see measurable improvement in the fields that were previously failing due to label variation. Fuzzy matching and synonym expansion typically improve field-level accuracy by five to fifteen percentage points in the most affected field categories. If you see no improvement, something in the synonym list or the fuzzy matching threshold is not working correctly. Investigate before proceeding.

**What to verify specifically.** Confirm that every test document is classified correctly. Confirm that scanned documents are going through image preprocessing. Confirm that tables are being detected and producing structured output for the comparable sale grids. Confirm that fields that were previously failing due to label variation are now being found.

**Fixing problems before proceeding.** Any Layer One component that is producing incorrect output on your test documents must be fixed today. Week Three builds entirely on the assumption that Layer One output is clean and reliable. A defective Layer One will poison every extraction result in Week Three.

**Week Two exit criteria.** Document classification is working correctly on all test documents. Scanned documents are producing better OCR output than baseline. Table detection is producing structured output for the main tables in your test appraisal reports. Tier Three extraction with synonym expansion and fuzzy matching is showing measurable accuracy improvement over the Day 4 baseline. All Layer One output is stored in the database with complete metadata.

---

## Week Three — Layer Two Complete
### Days 13 through 20

This is the most important week of the project. You are building the core intelligence — the three-tier extraction ensemble with confidence merging. By the end of this week, your system will be extracting fields using LLM semantic understanding, embedding similarity, and enhanced pattern matching, with their outputs merged into a single confident result.

This week is allocated eight days instead of six because the work is harder and more likely to encounter unexpected complexity. Do not compress this week. If you rush it, you will produce a brittle three-tier system that fails in unexpected ways.

---

### Day 13 — Tier One LLM Extraction — Prompt Engineering

Today you build the LLM extraction tier. The most important thing to understand about this day is that the quality of the prompts you write determines seventy percent of the LLM's extraction accuracy. The model is already capable. Your job is to give it clear, specific instructions.

**How Tier One LLM extraction works.** The normalized, cleaned text of the document is sent to the Ollama LLM with a carefully crafted prompt. The prompt instructs the model to read the document text and extract specific fields, returning its results in the structured format that matches your extraction result schema. The model returns a response containing extracted values and their source text references.

**What the prompt must contain.** A clear statement of what the model is being asked to do — extract specific fields from an appraisal document. A list of the canonical field names it should extract, with a brief description of what each field represents. Explicit instructions about what to do when a field is not found in the document — return a not-found indicator, not a guess. Explicit instructions about what to do when a field is ambiguous — return the most likely value with a note about the ambiguity. Examples of how the same field may be labeled differently in different documents — three or four label variants for each of the most commonly variant fields. The exact output format the model should use, including the structure of the result object. A strict instruction that the model must not invent values that are not present in the document text.

**Handling the hallucination risk.** LLMs will sometimes return values that are not present in the source document. This is called hallucination and it is the primary risk of Tier One extraction. Your prompt must include explicit instructions against this. Additionally, every value returned by the LLM must be verified against the source text — the model should return the source text passage alongside the extracted value, and your code must confirm that the extracted value actually appears in or is a reasonable interpretation of the source passage. If the extracted value cannot be found in or near the source passage, reduce the confidence score significantly and flag it for review.

**Sending documents to Ollama.** Very long documents may exceed the LLM's context window. Develop a document chunking strategy that sends the document in sections — typically page by page or section by section — and aggregates the results. For each chunk, include a brief context header that tells the model where in the document this chunk comes from. This prevents the model from being confused by partial document content.

**What done means for Day 13.** The LLM extraction tier is calling Ollama successfully and returning structured results for your test documents. Prompts are finalized and documented. The hallucination detection logic is working — values that the model returns but that cannot be verified against the source text are being flagged. Results are being stored in the extraction results table with "tier_one_llm" as the extraction method identifier.

---

### Day 14 — Tier One LLM Extraction — Testing and Refinement

Today you spend the entire day measuring Tier One accuracy and refining the prompts based on what you find.

**Running Tier One on all test documents.** Process all fifteen test documents through the LLM extraction tier. For each document, compare the LLM's extracted values against the correct values from your test set. Identify every field where the LLM returned an incorrect value, a hallucinated value, or no value.

**Categorizing errors.** For every error, determine its cause. Wrong label interpretation means the LLM misidentified which label corresponds to which canonical field. Context confusion means the LLM returned the right type of value but from the wrong context — for example, returning the contract price when asked for the appraised value. Hallucination means the LLM returned a value not present in the document. Missing means the field exists in the document but the LLM failed to find it. Format error means the LLM found the correct value but returned it in the wrong format.

**Prompt refinements based on error categories.** Wrong label interpretation is fixed by adding more label examples to the prompt for the affected field. Context confusion is fixed by adding explicit disambiguation instructions — "The appraised value is the final opinion of value stated by the appraiser. It is different from the contract price, the assessed value, and the loan amount." Hallucination is fixed by strengthening the anti-hallucination instructions and improving the source text verification logic. Missing values are investigated by checking whether the field actually appears in the document and whether the document chunk containing the field is being sent to the LLM.

**What done means for Day 14.** Prompt refinements have been applied based on the error analysis. The LLM extraction tier is showing measurable improvement over the initial prompt version. The most common error categories have been addressed. The accuracy rate for the most important fields — appraised value, borrower name, property address, effective date, contract price — must be above seventy percent on the test set before proceeding.

---

### Day 15 — Tier Two Embedding Extraction — Setup and Field Vectors

Today you build the embedding-based extraction tier using sentence-transformers.

**Pre-computing field concept vectors.** For every canonical field name in your schema, you need a vector representation of the concept that field represents. This vector is computed from a set of representative label examples for the field. For the borrower name field, you provide all known synonymous labels — "Borrower Name," "Client Name," "Applicant Name," "Customer Name," "Loan Applicant," and any others in your schema. The embedding model converts each label into a high-dimensional vector, and you average these vectors to create the field concept vector. This pre-computed vector is stored in the database and does not need to be recomputed unless you add new synonyms.

**Building the candidate text segments.** For each page of the processed document, extract candidate text segments — short passages of text that might represent a field label and its value. A candidate segment is typically a sentence or a short paragraph, or a region of text within a table cell. The size of the segment matters: too short and it lacks context, too long and it contains too much information from multiple fields. Aim for segments of ten to fifty words.

**Similarity comparison.** For each candidate segment, compute its embedding vector using the same model used for field concept vectors. Then compute the cosine similarity between the candidate segment's vector and each field concept vector. The field with the highest similarity score above the threshold is the candidate match.

**Setting the similarity threshold.** The threshold determines when a similarity is considered a match versus a coincidence. Start with a threshold of seventy percent cosine similarity. Test this on your test documents. If you see many false positives — candidate segments being matched to the wrong field — raise the threshold. If you see many missed matches — candidate segments that should match a field but don't — lower the threshold. The right threshold for your domain will be between sixty-five and eighty percent.

**What done means for Day 15.** Field concept vectors are pre-computed and stored for all canonical fields. The candidate segment extraction is working on test documents. The similarity matching is producing candidate results that can be stored as Tier Two extraction results. Results are stored with "tier_two_embedding" as the extraction method identifier.

---

### Day 16 — Tier Two Embedding Extraction — Testing and Calibration

Today you measure Tier Two accuracy and calibrate the similarity threshold.

**Running Tier Two in isolation.** Process all test documents through Tier Two embedding extraction only, without Tier One LLM and without Tier Three pattern matching. Measure accuracy against the test set. This tells you what Tier Two contributes independently.

**Expected Tier Two strengths.** Embedding extraction typically performs best on fields with highly variable labels and fields where contextual meaning matters more than exact wording. It typically performs worst on fields with very specific numeric formats — dates, currency amounts — where semantic similarity is less useful than pattern matching.

**Calibrating thresholds.** Based on the test results, finalize the similarity threshold. Also determine per-field thresholds for fields where the general threshold produces too many errors. Critical fields like appraised value and borrower name may need higher thresholds to avoid false positives.

**What done means for Day 16.** Tier Two extraction is calibrated and producing reliable results for the fields where embedding-based matching works well. Per-field thresholds are defined and stored in the database configuration. The accuracy of Tier Two is measured and recorded.

---

### Day 17 — Confidence Score Merging Logic

Today you build the merging component that combines the outputs of all three tiers into a single extraction result per field.

**The merging algorithm.** For each canonical field name, collect all extraction results from all three tiers. Some fields may have results from all three tiers. Some may have results from only one or two.

When all three tiers agree on the same value, the merged confidence score is very high — ninety to ninety-five. The merged value is the agreed-upon value.

When two tiers agree and one disagrees, the merged confidence score depends on which two agree. If Tier One and Tier Three agree, confidence is high — eighty to eighty-five. If Tier One and Tier Two agree but Tier Three disagrees, confidence is moderately high — seventy-five to eighty. If Tier Two and Tier Three agree but Tier One disagrees, investigate: the LLM may be hallucinating and the other two tiers are correct, so use the agreed value with confidence of seventy.

When all three tiers disagree, or when only one tier has a result, confidence is low — below sixty. The value is taken from the tier with the highest individual confidence but is flagged as requiring human review.

When no tier produces a result, store a not-found result with zero confidence and flag it as requiring review if the field is required according to the schema.

**Storing the merged result.** The merged result is a new row in the extraction results table with "tier_merged" as the extraction method identifier. It stores the merged value, the merged confidence score, and a reference to all three individual tier results that contributed to it. This reference chain is the audit trail.

**Confidence score normalization.** Before merging, normalize the confidence scores from each tier to be on the same scale. Tier One LLM returns its own confidence estimates which may not be calibrated. Tier Two embedding returns cosine similarity percentages. Tier Three pattern matching returns scores based on match quality. Define a normalization function for each tier that converts its raw scores to a common scale.

**What done means for Day 17.** The merging component correctly combines results from all three tiers using the algorithm described above. Merged results are stored in the database. Confidence scores are normalized and calibrated against your test set results.

---

### Day 18 — Multi-Page Document Spanning

Today you handle the case where related information is spread across multiple pages of a document.

**The problem.** Your three-tier extraction currently operates on a per-page or per-section basis. But some fields in appraisal documents are split across pages. A borrower's name may appear on page one and their address on page three. The certification signatures may appear on the last page while the appraised value appears on page two.

**The solution.** After all three tiers have run on every page independently, run a document-spanning reconciliation pass. This pass looks at all extraction results across all pages for the same document and handles three cases.

The first case is duplicate field extractions, where the same field was extracted from multiple pages. When this happens, use the confidence scores to select the authoritative value. The highest-confidence result wins. Store the others as secondary references.

The second case is complementary field extractions, where different parts of a multi-part field appear on different pages. An address may have the street on one page and the city, state, and zip on another. The reconciliation pass must combine these into a single complete field value.

The third case is cross-page context validation, where a value on one page provides context for interpreting a value on another page. The effective date on the cover page of the appraisal report provides context for interpreting the comparable sale dates on the grid pages.

**What done means for Day 18.** The document-spanning reconciliation pass is implemented and tested on your test appraisal reports. Fields that previously required manual combination of information from multiple pages are now being assembled correctly.

---

### Day 19 — Week Three Integration Testing

Run the complete three-tier extraction pipeline on all fifteen test documents. Measure accuracy and record results.

**Measurement protocol.** For every canonical field in every test document, compare the merged extraction result against the correct value from the test set. Record field-level accuracy, document-level accuracy, and AMC-level accuracy. Compare against the Week One baseline and the Week Two measurements.

**Expected accuracy at this point.** After three-tier extraction, you should be seeing significant improvement over baseline, particularly in the fields that were previously failing due to label variation and contextual ambiguity. A realistic target is fifteen to thirty percentage points improvement over baseline across the most important fields.

**Investigating accuracy that falls short of expectations.** If certain fields are still performing poorly after three-tier extraction, investigate why. Is the LLM consistently misidentifying these fields? Is the embedding similarity producing false positives? Is the pattern matching still relying on labels that do not appear in some documents? Each failure type has a specific fix.

---

### Day 20 — Week Three Fixes and Buffer

Use today to fix any issues found during Day 19 testing and to prepare for Week Four.

**Priority of fixes.** Fix issues affecting the most important fields first — appraised value, borrower name, property address, effective date, contract price. These are the fields whose incorrect extraction has the most significant consequences. Issues affecting less important fields can be addressed later or accepted as known limitations.

**Week Three exit criteria.** All three extraction tiers are implemented and working. The merging logic correctly combines tier outputs. Merged confidence scores are calibrated against the test set. Accuracy measurement shows meaningful improvement over the baseline across the most important fields. All extraction results are stored in the database with complete audit trails.

---

## Week Four — Layer Three and Layer Four Complete
### Days 21 through 26

This week you build context-aware validation, cross-document consistency checking, the AMC profile registry, and the confidence-driven routing logic that decides which fields go to auto-acceptance and which go to human review.

---

### Day 21 — Context-Aware Validation Layer

Today you upgrade your existing rule engine from format validation to semantic validation.

**Format validation — what you likely already have.** Date fields are checked to be valid dates. Currency amounts are checked to have correct numeric formatting. UAD condition codes are checked against the list of six allowed values. Required fields are checked for presence. These checks should already exist in your Java rule engine.

**Semantic validation — what you are adding today.** Semantic validation checks that values make sense in context, not just that they are formatted correctly.

Appraised value versus contract price relationship. When the appraised value is more than twenty percent above or below the contract price, flag it with a specific QC rule result indicating a significant value-to-price discrepancy. This is not necessarily an error — it may be a legitimate appraisal outcome — but it must be reviewed.

Comparable sale date eligibility. Each comparable sale date must be within an acceptable window of the appraisal effective date. The standard window is twelve months, but some guidelines allow exceptions for rural markets or specific market conditions. Check each comparable sale date against the effective date and flag any that fall outside the standard window with the specific number of months by which they exceed the window.

Comparable sale distance. Each comparable sale location must be within an acceptable distance from the subject property. What constitutes acceptable distance varies by market density. Flag sales that appear to be unusually distant from the subject property.

GLA reasonableness. The gross living area of comparable sales should be within a reasonable range of the subject property's GLA. A comparable sale with GLA more than fifty percent larger or smaller than the subject is typically problematic. Check and flag.

Date sequence validation. The engagement date must precede the effective date. The effective date must precede the report date. The inspection date must fall within a reasonable window of the effective date. Check these sequences and flag violations.

**How semantic validation results are stored.** Every semantic validation check produces a result that includes the rule name, the fields involved, the specific values that triggered the rule, whether the result is a pass, fail, warning, or information notice, and a human-readable explanation of what the rule found. These results are stored in the database and included in the QC report sent to the reviewer.

**What done means for Day 21.** All semantic validation rules are implemented in the Java rule engine. Running test documents through the validation layer produces results that correctly identify the semantic issues present in the documents. Validation results are stored with complete field references and human-readable explanations.

---

### Day 22 — Cross-Document Consistency Checking

Today you add the logic that compares extracted fields across the engagement letter, appraisal report, and sales contract for the same appraisal transaction.

**The consistency checking architecture.** After all three documents in a transaction have been processed by the three-tier extraction, a consistency checker runs on the complete set of extraction results for the transaction. For each field that appears in more than one document, it compares the values.

**Normalization before comparison.** Before comparing values from different documents, normalize them to remove superficial differences. Address normalization expands abbreviations — "St" to "Street," "Ave" to "Avenue" — and standardizes formatting. Name normalization handles case differences and punctuation differences. Date normalization converts all dates to the internal format established on Day 8. Currency normalization removes formatting characters and compares numeric values.

**Fields that must match.** Borrower name in the engagement letter must match borrower name in the appraisal report. Property address in the engagement letter must match property address in the appraisal report and in the sales contract. Contract price in the sales contract must match contract price referenced in the appraisal report. AMC name in the engagement letter must match AMC name referenced in the appraisal report.

**Fields that need authoritative source identification.** When values do not match across documents, the consistency checker must identify which document is more authoritative for that field. Use the authority mapping defined in the field schema on Day 1. Report the value from the most authoritative source as the recommended value and flag the discrepancy with the values from both documents.

**Handling missing documents.** Not every transaction will have all three documents. Design the consistency checker to work on whatever documents are available. When a document is missing, flag the fields that would have been checked across documents as unverified rather than failing the consistency check.

**What done means for Day 22.** The cross-document consistency checker processes complete transactions and identifies all discrepancies between documents. Discrepancies are stored in the database with references to both the document and field that generated each side of the discrepancy. Running your test transactions through the checker produces correct discrepancy reports.

---

### Day 23 — Confidence-Driven Routing Logic

Today you implement the routing logic that decides, for each extracted field, whether it should be auto-accepted, flagged for optional review, or flagged for mandatory review.

**The routing thresholds.** Define two thresholds for each field: a mandatory review threshold and an auto-acceptance threshold. Fields with confidence below the mandatory review threshold are always sent to human review — the reviewer must explicitly confirm or correct the value before the QC report can be finalized. Fields with confidence above the auto-acceptance threshold are automatically accepted without requiring reviewer action. Fields in between are flagged for optional review — they appear in the reviewer's dashboard with a flag but the reviewer can choose to confirm without examining them in detail.

**Per-field threshold values.** Critical fields — appraised value, borrower name, property address, effective date — should have high auto-acceptance thresholds, around eighty-five, and low mandatory review thresholds, around fifty. This means the system is conservative about auto-accepting critical fields and liberal about sending them to review. Less critical fields — AMC internal file numbers, appraiser license state — can have lower auto-acceptance thresholds, around sixty-five, because errors in these fields have less significant consequences.

**Storing thresholds as configuration.** All threshold values must be stored in the database, not hardcoded. They should be configurable per field and per AMC. When you discover that a particular AMC's documents consistently produce lower confidence scores for a specific field, you can lower that field's threshold specifically for that AMC without changing the default thresholds.

**The routing decision output.** For every extracted field, the routing logic produces a routing decision that includes the field name, the extracted value, the confidence score, the routing outcome — auto-accept, optional review, or mandatory review — and the reason for the routing outcome when it is not auto-accept. This routing decision is stored in the database and sent to the Next.js frontend for display.

**What done means for Day 23.** The routing logic is implemented with correct per-field thresholds. Running test documents through the complete pipeline produces routing decisions for every field. Auto-accept, optional review, and mandatory review decisions are being made correctly based on confidence scores. Thresholds are stored in the database as configuration.

---

### Day 24 — AMC Profile Registry — Active Profile Building

Today you implement the logic that actively builds and updates AMC profiles based on processed documents.

**Profile fingerprint computation.** When a document is classified on Day 9, it generated a structural fingerprint. Today you implement the logic that compares this fingerprint to existing profile fingerprints in the database and either matches it to a known template version or creates a new template version record.

**Automatic terminology mapping updates.** When a reviewer makes a correction that indicates a label variant was missed, and that label variant is not in the current terminology mapping for that AMC, add it automatically. This is the fast-path learning described in the architecture guide — an immediate update that does not require model retraining.

**Profile maturity tracking.** Update the document count in the AMC profile every time a document from that AMC is processed. When the document count crosses ten, update the maturity level from "new" to "developing." When it crosses fifty, update to "mature." The maturity level is used by the extraction tiers to calibrate how much weight to give to AMC-specific prior knowledge when computing confidence scores.

**Profile-informed confidence adjustment.** For documents from AMCs with mature profiles, apply a confidence adjustment based on whether the extracted field location matches the expected location in the profile. A field found in the expected location for this AMC gets a small confidence boost. A field found in an unexpected location gets a small confidence reduction. This adjustment is small — at most ten points in either direction — because location prior should never override the content-based confidence from the extraction tiers.

**What done means for Day 24.** AMC profiles are being automatically updated as documents are processed. Terminology mappings are being extended automatically when reviewer corrections indicate new label variants. Profile maturity levels are being tracked. Profile-informed confidence adjustments are being applied to extraction results.

---

### Day 25 — Template Change Detection

Today you implement the detection logic that identifies when an AMC has updated their document template.

**How template change detection works.** When a new document's structural fingerprint does not match any known template version for its AMC within the similarity threshold, the system creates a new template version record and sets a "template change detected" flag. This flag triggers a notification to the operations team.

**The notification.** The notification must include the AMC name, the document identifier that triggered the detection, a side-by-side comparison of the new fingerprint against the most recent known fingerprint, and a recommendation to manually review the document to confirm whether the template has actually changed.

**Avoiding false positives.** Template change detection will occasionally fire for documents that are within the normal variation range of an existing template, particularly for AMCs with developing or new profiles. Reduce false positives by setting the similarity threshold higher for AMCs with mature profiles and lower for new profiles. Mature profiles have enough documents to establish reliable fingerprint statistics, so deviations are more significant.

**What done means for Day 25.** Template change detection is firing correctly when test documents with deliberately modified fingerprints are processed. Notifications are being generated and stored. False positive rate is acceptable for your test documents.

---

### Day 26 — Week Four Verification and Buffer

Run all test documents through the complete pipeline including validation, consistency checking, routing, profile building, and template change detection. Measure and record accuracy.

**Week Four exit criteria.** Semantic validation rules are correctly identifying known issues in test documents. Cross-document consistency checking is correctly identifying discrepancies between documents in the same transaction. Routing decisions are correctly categorizing fields as auto-accept, optional review, or mandatory review. AMC profiles are being built and updated correctly. Template change detection is working without excessive false positives.

---

## Week Five — Layer Five, Integration, and Hardening
### Days 27 through 30

This final week is about connecting everything together, making the system production-ready, and ensuring that every error condition is handled gracefully.

---

### Day 27 — Correction Capture to Feedback Connection

Today you connect the correction capture built on Day 5 to the actual system improvement mechanisms.

**Fast-path terminology updates.** When a reviewer makes a correction and selects "wrong label matched" as the correction reason, the system should check whether the label that was used in the source document is in the current terminology mapping for that AMC. If it is not, add it automatically. This fast-path update takes effect immediately — the next document from that AMC will benefit from the new label mapping without any model retraining required.

**Correction pattern analysis.** Implement a background job — using your existing Celery queue — that runs daily and analyzes the corrections accumulated during the previous day. The analysis identifies systematic patterns: the same field in the same AMC's documents being corrected repeatedly, indicating a systematic extraction error for that field and AMC. The output of this analysis is a report stored in the database that identifies the top correction patterns and suggests specific fixes.

**Threshold adjustment based on corrections.** When a field is being corrected at a high rate for a specific AMC, the system should automatically reduce the auto-acceptance threshold for that field for that AMC. This sends more instances of that field to human review until the correction rate drops, at which point the threshold can be raised again.

**What done means for Day 27.** Fast-path terminology updates are working — making a correction with the "wrong label" reason and reprocessing the document shows the new label being matched correctly. The correction pattern analysis job is running and producing pattern reports. Threshold adjustments based on correction rates are being applied.

---

### Day 28 — End-to-End Integration Testing and Error Handling Audit

Today you test the complete system end-to-end and conduct a thorough audit of every error condition.

**The end-to-end test protocol.** Upload a new document from each AMC in your test set through the Next.js frontend. Observe the complete journey: upload, classification, OCR, normalization, table detection, three-tier extraction, merging, validation, consistency checking, routing, and reviewer display. Verify that every stage completes correctly. Verify that the reviewer sees the correct confidence-driven display. Make a correction and verify it is captured correctly in the database.

**The error handling audit.** Go through every component in the pipeline and identify every failure mode. For each failure mode, verify that the system handles it gracefully. The following specific error conditions must all be tested.

OCR failure on a specific page: the system must continue processing the remaining pages and flag the failed page as unprocessable.

LLM timeout or Ollama unavailability: Tier One extraction must fail gracefully, the pipeline must continue with Tier Two and Tier Three only, and the resulting lower confidence scores must correctly trigger more human review.

Document with completely unknown format — no AMC match: the system must classify it as unknown, create a new AMC profile skeleton, process it with general extraction, and route most fields to human review due to low confidence.

Database write failure during extraction result storage: the pipeline must detect this failure, retry the write up to three times with exponential backoff, and if the retry fails, store the job in a failed state that can be resumed rather than lost.

Malformed PDF that cannot be opened: the system must reject the upload with a clear error message that identifies the problem and suggests remediation.

Document with zero extractable text after OCR: the system must detect this condition, classify the document as unprocessable, and notify the operations team with enough detail to investigate.

Extremely large document — more than one hundred pages: the system must handle this without running out of memory or timing out. If the document is too large for a single processing job, it must be split into sections automatically.

Concurrent processing of the same document submitted twice: the system must detect the duplicate and either reject it or queue it while the first processing completes.

Reviewer correction containing invalid data: the API endpoint must validate all input and return specific error messages identifying what was invalid.

**What done means for Day 28.** All error conditions above have been tested. Each one is handled gracefully without causing system failures or data loss. Error conditions are logged with enough detail to diagnose and resolve the underlying cause.

---

### Day 29 — Performance Verification and Observability

Today you verify that the system performs acceptably under realistic load and that you can observe its behavior through logging and metrics.

**Performance targets.** A natively digital appraisal document of thirty pages should be fully processed — from upload to reviewer-ready — within ninety seconds. A scanned appraisal document of the same length should be fully processed within three minutes. These targets may need adjustment based on your actual hardware performance, but establish concrete targets before measuring.

**Load testing.** Submit five documents simultaneously and measure how the system handles concurrent processing. With your Celery queue configuration and six-core CPU, two to three documents should be able to process in parallel. Verify that concurrent processing does not cause resource conflicts — GPU memory contention, database connection exhaustion, or file system locking issues.

**Logging completeness audit.** For every significant event in the pipeline, verify that a structured log entry is produced. Processing start and end times for each stage. The document identifier in every log entry. Error details when any component fails. Confidence scores for all merged results. Routing decisions for all fields. Corrections made by reviewers. If any of these log entries are missing, add them today.

**The operations dashboard.** Build a simple internal page in the Next.js frontend — not user-facing, accessible only to administrators — that shows the current state of the job queue, the number of documents processed today, the average confidence scores by document type and AMC, the correction rate by field and AMC, and any active alerts. This dashboard is what you look at every morning before starting development work.

**What done means for Day 29.** Performance targets are being met for both digital and scanned documents under realistic load. The logging audit confirms that all significant events are being logged. The operations dashboard shows accurate real-time information.

---

### Day 30 — Final Measurement, Documentation, and Handover

The last day is for measurement, documentation, and ensuring the system is ready to operate going forward.

**Final accuracy measurement.** Run all fifteen test documents through the complete system. Measure field-level accuracy, document-level accuracy, and AMC-level accuracy. Compare against the Day 4 baseline. Document the specific improvement achieved in each category.

**The minimum acceptable result.** After thirty days of development, the following accuracy thresholds should be met. The most critical fields — appraised value, borrower name, property address, effective date, contract price — should be extracted correctly in at least eighty-five percent of test documents. The auto-acceptance rate — the percentage of extracted fields that meet the confidence threshold and do not require human review — should be at least fifty percent, meaning reviewers spend their time on the fields that genuinely need attention rather than reviewing everything.

**Documentation to complete today.** The field schema must be finalized and annotated with any changes made during the month. The AMC profile records in the database must be documented with a summary of what is known about each AMC's format. The confidence threshold configuration must be documented with the rationale for each threshold value. The known limitations document must list every field type or document format where the system's extraction accuracy is still below target, along with the plan for addressing each limitation in the next development cycle.

**The known limitations principle.** It is better to have a documented list of known limitations than to have unknown limitations. A known limitation can be planned around — the confidence threshold for that field can be set conservatively so that it always goes to human review. An unknown limitation causes silent failures. By the end of Day 30, every area where your system's extraction is not reliable must be a known and documented limitation.

**System handover checklist.** Before declaring the one-month implementation complete, verify the following. The system is running and processing real documents. The reviewer interface is showing confidence scores and routing decisions correctly. Corrections are being captured and feeding into terminology updates. AMC profiles are being built and maintained. The operations dashboard is showing accurate metrics. Every error condition identified on Day 28 is handled gracefully. The documentation is complete and accessible to all team members. A second team member can operate the system independently without assistance from the primary developer.

---

## Risk Management Throughout the Month

**The highest-risk week is Week Three.** The three-tier extraction ensemble is the most complex component and the most likely to encounter unexpected problems. The eight-day allocation for Week Three exists specifically to handle this. If Week Three runs over into the Week Four buffer, prioritize getting Tier One and Tier Three working correctly before completing Tier Two. An accurate two-tier system deployed on time is better than a three-tier system deployed late.

**The highest-risk component is the LLM extraction.** LLM behavior is less predictable than pattern matching or embedding similarity. Prompt engineering takes longer than expected. Hallucination detection requires iteration. If the LLM is not producing acceptable accuracy after Day 14's refinement session, do not spend more time on prompting. Reduce its role — use it only for fields where Tier Three consistently fails and accept lower confidence scores for those fields.

**The second highest risk is hardware.** If the RTX 3060 encounters CUDA compatibility issues with your installed CUDA version, Ollama configuration problems, or driver instability, it can block LLM inference work for multiple days. Verify CUDA functionality and Ollama operation completely before Day 13 — ideally before Day One.

**Scope management is critical.** Every day of this month is allocated to specific work. When a new idea or a feature request appears during the month, do not implement it. Write it in a backlog document for the next development cycle. Adding unplanned work to an already tight schedule is the most common reason thirty-day projects become sixty-day projects.

**Daily standup discipline.** Every working day, before starting technical work, answer three questions in writing. What did I complete yesterday and does it match what was planned? What will I complete today? Is anything blocking me or at risk of blocking me? This discipline takes five minutes per day and prevents the common failure mode of discovering major delays only at the end of the week when it is too late to recover.

---

## What the System Will and Will Not Do After Thirty Days

**What it will do.** Process any combination of engagement letter, appraisal report, and sales contract from any AMC your system has previously encountered, extracting all required fields with confidence scores. Route low-confidence fields to human review automatically. Flag semantic validation issues and cross-document inconsistencies. Build and maintain AMC profiles that improve with each processed document. Capture reviewer corrections and immediately apply fast-path improvements. Detect when an AMC's document template has changed. Provide an operations dashboard with real-time metrics. Handle all error conditions gracefully without data loss.

**What it will not do after thirty days.** It will not automatically retrain extraction models from accumulated corrections — that is a Week Five stretch goal for the next development cycle. It will not provide high accuracy on documents from AMCs that have never been seen before — new AMC documents will go almost entirely to human review until a profile is built. It will not handle document types that were not included in the field schema — unknown document types will be flagged as unclassifiable. It will not self-optimize confidence thresholds — threshold optimization based on accumulated correction data is a future capability.

These limitations are not failures. They are the honest scope of what can be built in thirty days. Document them. Plan for them. Build the next development cycle to address them.

---

*Document Version 1.0 — EagleX Info Solution PVT LTD*  
*One-month implementation plan for the Apprisal adaptive extraction system.*  
*This document is the operational guide for the development team during the thirty-day implementation window.*  
*Read it completely before starting. Reference it every day. Update it when circumstances require plan changes.*
