# Apprisal Platform — AI Coding Assistant Guidance

> This file is read by the AI coding assistant on every session.
> It establishes the rules that govern all coding decisions and the long-term architectural vision
> that must inform every feature, refactor, and design choice.
> Keep this file current as the platform evolves.

---

## The Most Critical Rules for AI Coding Assistant to Follow

### Rule 1 — Never Use LLM for Structured Field Extraction

LLM must NEVER be used to extract structured fields from appraisal text.
Fields like address, borrower name, contract price, dates — always use regex plus spatial anchoring.

LLM is ONLY allowed for:

- Commentary quality analysis (canned vs specific)
- Market conditions narrative quality
- Reconciliation sufficiency evaluation

If the AI coding assistant suggests using LLM to extract a field, that is wrong. Correct it.

### Rule 2 — Checkbox Detection Uses Three-State Logic

Checkboxes in OCR text exist in three distinct states. Handle all three explicitly:

- A marked checkbox near a label → CHECKED (True)
- An empty checkbox near a label → UNCHECKED (False)
- Neither found → UNKNOWN (None) → return VERIFY status, never FAIL

Never return FAIL from an UNKNOWN checkbox state.
Never treat an explicit empty checkbox the same as a not-found checkbox.

When vision model analysis is available, run pixel analysis first. Only escalate to the vision model when pixel confidence is below 75%. Cache all vision model results by document, page, and bounding box.

### Rule 3 — Every Extracted Field Must Have Four Properties Populated

When extraction produces any field value, all four of these must be set. Never leave them as defaults:

- `confidence_score` (float 0.0–1.0) — compute it, never leave as 0.0
- `source_page` (int) — which page of the PDF this came from
- `extraction_method` — how it was found (spatial anchor, regex primary, regex fallback, not found)
- `raw_value` — what OCR literally produced before any correction

This data feeds the ML training loop. Missing it means the model cannot learn from that extraction.

### Rule 4 — Rules Must Never Crash the Whole Pipeline

Every rule function is wrapped in try/except at the engine level. If one rule raises any exception:

- That rule returns `status=SYSTEM_ERROR`
- All other rules continue running
- The error is logged with rule_id and request_id
- The full response still returns with all other rule results

Do not write rule functions that can propagate exceptions out of the try/except boundary.

### Rule 5 — Address Parsing Must Use Data Patterns, Not Label Words

The zip code parser must find the 5-digit number pattern, not search for the word "Code" or "Zip".
OCR mangles label words ("aP Code", "Zip Gode") but rarely mangles the actual 5-digit number.

Correct approach:
1. Find 5-digit number at end of address block → zip code
2. Find 2-letter uppercase before it → state
3. Find text between the city anchor keyword and the state → city
4. Find text before the city anchor → street

Never write a regex that depends on the word "Code" or "Zip" appearing correctly in OCR output.

### Rule 6 — Raw OCR Text Must Be Saved to Database

After every OCR operation, the raw text column must be inserted with the full unmodified OCR output.
This is the training signal for the correction ML model.
Do not skip this to save time or because the text seems unimportant or low quality.

### Rule 7 — Parallel Page Processing Always Uses a Thread Pool

OCR processes pages in parallel using a thread pool executor — never sequentially.
The worker count comes from an environment variable. Sequential page processing is a regression.
If you see a for loop iterating over pages in OCR processing code, fix it immediately.

### Rule 8 — File Hash Before OCR, Always

Before running OCR on any uploaded PDF:
1. Compute SHA-256 hash of the file bytes
2. Check the database for an existing hash match
3. If found: return cached extraction result — do not re-run OCR
4. If not found: run OCR, then save hash and results to database

This prevents repeating 14 seconds of OCR processing on retry requests for the same document.

### Rule 9 — LLM Calls Must Always Have a Fallback

Every call to the local LLM must have a fallback that activates on:

- Timeout beyond the configured limit
- Connection refused
- Invalid or unexpected response format
- Empty response

The fallback for commentary analysis is keyword-based matching.
The pipeline must never return a 500 error because the local LLM is down or slow.

### Rule 10 — Feedback Must Be Stored With Full Context

Every operator correction must include:

- `original_ocr_text` — what OCR produced
- `system_extracted_value` — what extraction produced from the OCR
- `operator_provided_value` — what the operator says is correct
- `rule_id` — which rule was involved
- `source_page` — which page the field came from

Missing any of these makes the training example useless for the ML model.

---

## Engineering Strategy Principles

> Derived from: *Apprisal Platform — Engineering Thinking and Development Strategy Guide*
> Prepared for: EagleX Info Solution PVT LTD
> These principles translate the strategy document into specific directives for AI coding assistant behavior.

---

### P-1 Define "Done" at Three Levels Before Starting Any Task

Every task — a new rule, a new extractor, a bug fix, a performance improvement — must have explicit done criteria at three levels before any code is written.

**Level 1 — Technically Done:** Code written, existing tests pass, no regressions.

**Level 2 — Functionally Done:** The feature does what it was designed to do on real documents. For an extraction change this means field-level accuracy is measured on all test documents with a documented rate. "Seems to work" is NOT functionally done. If you cannot state the accuracy rate, the work is not done.

**Level 3 — Operationally Done:** The change can be operated, monitored, and debugged by someone other than the implementer. This includes logging that explains what happened when something goes wrong, configuration values for any behavior that might need tuning, and the service restarts cleanly with the change applied.

Never mark a task complete if it has not passed all three levels.

---

### P-2 Read Existing Code Deeply Before Extending It

Before adding any new extraction logic, rule, or service layer, read the existing code with these specific questions:

1. **What does this code actually do?** Trace it on a real document. Not what comments say — what it does.
2. **What assumptions does it make?** Every regex that expects a specific label format, every confidence threshold that is hardcoded, every field that is assumed to be on a specific page — write these down. Each is a fragility.
3. **Where does it fail?** Run it on an unusual document and observe where it breaks.
4. **What would have to change to support a new AMC format?** If the answer is "many scattered files," the abstraction is insufficient.

If you skip this step and build on top of misunderstood code, the result will be inconsistent, fragile, and harder to maintain than what existed before.

---

### P-3 Separation of Concerns — One Sentence Test

Every function and class you write must pass the One Sentence Test: can you describe what it does in one sentence without using the word "and"?

If a function extracts a field and validates it and logs the result — it is doing three things and must be broken apart.

The pipeline boundaries are:

- OCR → returns text only. Knows nothing about fields.
- Phase 2 extraction → takes text, returns structured field results. Knows nothing about rules.
- Rule engine → takes a validation context, returns rule results. Knows nothing about OCR.
- QC processor → orchestrates. Knows nothing about extraction internals.

Never cross these boundaries. If you are about to add validation logic to an extractor, stop. If you are about to add extraction logic to a rule, stop.

---

### P-4 Configuration Over Hardcoding — Always

Any behavioral value that might need to change based on experience, AMC variation, or business requirements is a configuration value, not a hardcoded constant. Before hardcoding any value, ask: is this the same for all AMCs, in all conditions, forever?

Values that must be configuration:

- Confidence thresholds per field and per AMC
- Synonym lists for field labels
- Extraction method preference order
- Model names and timeouts
- Rule severity and execution order
- Retry counts and backoff timing for OCR jobs

When a business analyst needs to adjust a threshold, they should be able to do it without a developer. When an AMC onboards with unusual label wording, the synonym should be addable without a deployment.

---

### P-5 Keep Raw Inputs Alongside Every Output

Every extraction operation must preserve its inputs alongside its outputs. This is not optional and cannot be deferred.

When extraction produces a field value, all of the following must be stored:

- `raw_value` — what OCR literally produced
- `corrected_value` — after normalization
- `source_page` — which page
- `extraction_method` — how it was found
- `confidence_score` — computed, never default 0.0

When an output is wrong, you cannot debug, fix, or generate training data from it unless you kept the input. Discarding intermediate data makes the system permanently harder to improve. This is conceptual debt that compounds.

---

### P-6 Design for Graceful Degradation — Each Tier Fails Independently

Every stage in the extraction and rule pipeline must fail independently. A failure in one stage never blocks downstream stages or returns an error for the whole document.

The required behavior for every component:

- **OCR failure on one page** → skip that page, flag it, continue with other pages
- **LLM timeout** → disable further LLM calls for this request, use keyword fallback, continue
- **Extraction returns NOT_FOUND** → rule receives a data-missing signal, returns EXTRACTION_FAILED, pipeline continues
- **One rule crashes** → that rule returns SYSTEM_ERROR, all other rules continue
- **DB write fails on persist** → log error, return results to caller anyway

A document that produces partial results with honest confidence scores and REVIEW flags is always better than a document that fails completely and produces no results.

---

### P-7 Incremental Build — Never Build Everything at Once

The system must be built in deployable increments. Each increment:

1. Solves the current most pressing problem — not all imaginable future problems
2. Gets deployed to production and observed on real documents before the next increment starts
3. Stays small enough to deliver in days, not weeks

Real conditions always reveal things that test conditions do not. If an increment is not deployed and observed, the learning from it never happens. Do not combine increments to accelerate — staying disciplined about increment size is what makes each one reliable.

When implementing, choose the simplest correct approach first. Measure its behavior. Then improve based on what you actually observe, not what you predict.

---

### P-8 Define Measurement Before Building the Feature

Before implementing any improvement to extraction, enrichment, or rule logic, define:

- **What metric will be tracked?** (field-level accuracy, human correction rate, confidence calibration)
- **What constitutes meaningful improvement?** (specific numerical threshold)
- **What constitutes failure?** (regression in any previously passing case)

Do not define success criteria after the fact. Do not claim improvement without quantitative measurement. The test documents exist precisely for this purpose.

Before claiming that any enrichment or analysis layer improves results, measure the exact change in PASS/FAIL/REVIEW counts on all test documents. Future changes must be measured the same way.

---

### P-9 Pay Technical Debt Incrementally — Never Accumulate

Every time you touch existing code for any reason, pay a small amount of debt in that area:

- Modifying an extraction pattern → also move any nearby hardcoded threshold into configuration
- Debugging a rule → also add a unit test for that rule
- Adding a synonym → also add a test case for that synonym
- Reading a function to understand it → if it does two things, split it into two

Do not stop feature work to do "cleanup sprints" — that rarely produces lasting improvement. Do pay small debts continuously. This keeps the system healthy without disrupting delivery.

The most dangerous debt in this codebase is extraction patterns that assume specific label wording. Every regex anchored to a specific human-readable label is debt. The path forward is positional extraction and narrative inference — not more specific regexes.

---

### P-10 Reviewer Is a System Actor, Not a UI User

The reviewer is a processing component in the pipeline whose domain expertise cannot be automated. Design every reviewer-facing output with this in mind:

1. **Every field shown to the reviewer must include:** confidence score plus the exact source text from which it was extracted. A reviewer cannot correct what they cannot see the origin of.

2. **Corrections must be structured, not free-form.** When a reviewer changes a value, capture: was the OCR wrong, was the label not recognized, was the document format unusual? This structured feedback is training data.

3. **Minimize cognitive load.** High-confidence extractions → compact, scannable. Low-confidence or REVIEW status → prominent with clear plain-language explanation. Never use raw confidence numbers as the only signal — translate them.

4. **Reviewer corrections are the primary training signal** for improving extraction. Every feedback record that lacks original value, corrected value, rule ID, and source page is a lost training opportunity.

---

### P-11 Observability — Know What the System Is Doing

A system whose behavior is invisible is not a product-grade system. The following metrics must be tracked and visible at all times:

| Metric | Purpose |
|--------|---------|
| Field-level extraction accuracy by AMC | Is extraction improving or regressing? |
| Human correction rate by field type | Which fields need more work? |
| Confidence calibration (score vs actual accuracy) | Are confidence scores honest? |
| LLM call count and status | Is the model being called? Timing out? |
| Processing job durations by stage | Where is time being spent? |

When any metric changes unexpectedly, it signals that something in the system changed — new document format, model drift, real improvement, or regression. Without this visibility, you are guessing.

The structured JSON logging to the application log file is the foundation. Every major stage in the pipeline already logs its stage name and duration. Build on this, never remove it.

---

### P-12 Contracts Between Components — State Them Explicitly

Before building any new component or modifying an existing one, write down its contract:

- **Input:** format, required fields, valid ranges
- **Output:** format, guarantees
- **Errors:** what signals it may produce and what they mean
- **Timing:** is it expected to complete within a specific window?

When you upgrade a component — for example, improving an extraction pattern — the contract must remain stable. Upstream and downstream components must not need to change. If they do, the abstraction boundaries are wrong.

---

### P-13 Performance — Async for Bottlenecks, Measure Before Optimizing

The three bottlenecks in this system are OCR processing, LLM inference, and model training. All three must be async — they run as background tasks or thread pool workers, never blocking an HTTP request.

Never optimize a component you have not measured. The only valid approach is:

1. Deploy the simplest correct implementation
2. Measure actual throughput and latency on real documents under real load
3. Identify the actual bottleneck (not the predicted one)
4. Optimize specifically that bottleneck

Do not optimize LLM call latency by reducing context size, changing prompts, or batching calls until you have confirmed that LLM latency is the actual bottleneck for the specific workload. Measurement — not intuition — must drive optimization decisions.

---

### P-14 Dual-Model Strategy — Text vs Vision

This system uses two local model types with fundamentally different performance profiles:

- **Fast text model** (example: mistral:7b) — 1-3 seconds per call. Use for all commentary analysis, narrative quality assessment, and text-heavy field enrichment.
- **Vision model** (example: llava:13b) — 30-45 seconds per call. Use ONLY for image-based tasks such as checkbox detection and photograph analysis.

On constrained hardware, these models cannot run simultaneously. The pipeline routes to the correct model type based on the nature of the task. A helper function selects the fast text model for text analysis and the vision model for image tasks.

Never route a text-only task to the vision model. Never route an image task to the text model.

---

### P-15 The Long Game — How to Keep the System Healthy Over Years

Every design decision made today will be read, debugged, and extended by someone in two years. The discipline of long-game thinking:

1. **Write code for the next reader, not just the next execution.** Functions do what their names say. Variable names describe what they hold. The one-sentence rule is the test.

2. **Never leave a TODO in production code without a linked issue.** A TODO with no accountability is a debt note with no maturity date.

3. **Extraction patterns change as document formats evolve.** Every regex that assumes a specific label wording will eventually break. The path forward is AMC format profiles, synonym registries, and positional extraction — not more specific regexes.

4. **Model versions must be archived indefinitely.** When a model is retrained and deployed, every historical extraction result must remain traceable to the model version that produced it.

5. **Data is the most valuable long-term asset.** The raw OCR text, extracted fields, and feedback events stored in the database are more valuable than any code. Protect them — never truncate, never break the schema without migration, never delete without archiving.

---

*Last updated: 2026-05-15*
*Source: Apprisal Platform — Engineering Thinking and Development Strategy Guide (EagleX Info Solution PVT LTD)*

---

## Apprisal Platform — Adaptive & Future-Proof Document Extraction Architecture Guide

**Prepared for:** EagleX Info Solution PVT LTD
**Document Purpose:** Long-term strategic and architectural guidance for moving from regex-based extraction to intelligent, format-independent, context-aware document understanding
**Scope:** Engagement letters, appraisal reports, contact forms, AMC templates, QC documents, and all appraisal workflow documents
**Audience:** Platform architects, backend engineers, product owners

---

### Table of Contents

1. Understanding the Core Problem
2. Why Regex and Fixed Patterns Eventually Fail
3. The Philosophy of Format-Independent Extraction
4. The Five Layers of Intelligent Document Understanding
5. Layer One — Adaptive Document Ingestion and Preprocessing
6. Layer Two — Semantic Field Recognition and Entity Extraction
7. Layer Three — Context-Aware Validation and Cross-Document Reasoning
8. How Enterprise Systems Solve This Problem
9. The Right Technology Stack for Each Layer
10. Transition Roadmap — From Regex to Intelligence
11. Handling Multiple AMC Formats Without Breaking
12. The Confidence-Scoring System
13. Building the Feedback Loop
14. Data Quality and Training Data Strategy
15. Infrastructure Considerations Given Your Hardware
16. What to Build First, Second, and Third
17. Common Mistakes to Avoid
18. Final Architecture Summary

---

### 1. Understanding the Core Problem

Before designing any solution, it is essential to understand the exact nature of the problem at a deep level. The challenge you are facing is not a technical limitation of your current code. It is a fundamental mismatch between two very different things: the stability of meaning and the instability of format.

In every document your platform processes, the meaning is stable. Every engagement letter, regardless of which AMC sent it, regardless of how it was designed or formatted, is trying to communicate the same set of facts. There is a borrower. There is a property. There is a fee. There is an effective date. There is an AMC. These facts do not change. Their meaning does not change. What changes is only the way those facts are represented visually and textually on the page.

Your current regex-based system has essentially hardcoded the assumption that meaning and representation are the same thing. When your system looks for a specific string like "Borrower Name:" followed by a value, it is assuming that the word "Borrower" will always be used, that the colon will always appear, that the spacing will always follow the same pattern, and that the field will always appear in roughly the same location. Every one of those assumptions is a fragility point.

The long-term solution is to build a system that understands meaning independently of representation. This is the core principle that all enterprise-grade intelligent document processing platforms are built on. The system should be able to read any document that communicates appraisal-related information and extract the correct facts, regardless of how those facts happen to be expressed on that particular day, by that particular AMC, using that particular PDF template.

---

### 2. Why Regex and Fixed Patterns Eventually Fail

It is important to understand this failure mode clearly, because it will happen gradually and then suddenly. Regex-based extraction does not fail in a loud, obvious way. It fails silently. You may not notice for weeks or months. A new AMC sends documents in a slightly different format. Your system still extracts most fields correctly because many labels are the same. But a few key fields silently return empty values or wrong values. No error is thrown. The QC report is generated anyway. The reviewer does not immediately notice. The problem compounds.

There are six specific failure modes that will affect your platform if you stay on a purely regex-based approach.

**Label variation failure.** Different AMCs use different words for the same concept. "Borrower Name," "Client Name," "Applicant," "Customer," and "Loan Applicant" all mean the same thing. A regex pattern anchored to "Borrower Name" will silently fail on every AMC that uses different terminology. You will need to add every synonym to every pattern, which means the rule library becomes a maintenance burden that grows with every new AMC you onboard.

**Layout shift failure.** Even the same AMC may move fields around when they update their template. A field that was in the top-right corner last year may be in the middle of the page this year. Positional extraction or sequential text-based parsing will fail because the field is no longer where the pattern expects it to be.

**Table structure failure.** Comparable sales data, fee schedules, and condition ratings are often presented in tables. But different documents use different table structures — some use bordered tables, some use whitespace-separated columns, some use indentation. A regex pattern designed for one table format will produce garbled output when the table structure changes.

**Formatting variation failure.** The same field may appear with different punctuation, different capitalization, different line breaks, or different spacing depending on the PDF generation tool used by the AMC. "Effective Date:" and "EFFECTIVE DATE" and "Effective Date of Appraisal:" are all the same field. A case-sensitive or punctuation-sensitive pattern will only catch one of them.

**Multi-page scatter failure.** Some documents place related information across multiple pages. A borrower's name may appear on page one while their address appears on page three. Regex-based extraction typically works page by page, making it difficult to combine information that has been split across the document.

**Semantic ambiguity failure.** Some fields are ambiguous without context. The word "value" might refer to the appraised value, the contract price, the assessed value, or the loan amount depending on the surrounding text. A simple pattern match cannot distinguish between these. Only a system that understands context can correctly identify which value is being referenced.

Understanding these six failure modes tells you exactly what properties your future system must have. It must be label-flexible, position-independent, table-structure-agnostic, formatting-tolerant, document-spanning, and context-aware.

---

### 3. The Philosophy of Format-Independent Extraction

Format-independent extraction is not a single technology. It is a design philosophy that informs every decision you make about your extraction pipeline. The philosophy has four principles.

**Principle one: Extract meaning, not patterns.** Your extraction layer should ask the question "what does this text mean?" rather than "does this text match this pattern?" This shifts the fundamental operation from string matching to semantic understanding. When a piece of text says "The undersigned borrower hereby confirms their identity as John Smith," a meaning-based system understands that John Smith is the borrower, even though the phrase "Borrower Name:" never appeared.

**Principle two: Separate extraction from validation.** Your extraction layer should focus only on pulling values out of documents. Your validation layer should focus only on checking whether those values are correct, complete, and consistent. When these two concerns are mixed together — when extraction logic includes hardcoded business rules about what valid values look like — changing one requires modifying the other. Separating them makes both more maintainable and more testable.

**Principle three: Use confidence, not binary pass/fail.** Every extracted field should carry a confidence score. A field that was found by an exact label match with high-quality OCR text gets a high confidence score. A field that was inferred from surrounding context with noisy OCR text gets a lower confidence score. The downstream system uses confidence scores to decide whether to auto-accept the value, flag it for human review, or reject it entirely. This makes your system graceful rather than brittle.

**Principle four: Learn continuously from corrections.** Every time a human reviewer corrects an extracted value, that correction is a training signal. The system that learns from these corrections gets better over time. The system that does not learn repeats the same mistakes indefinitely. Building a feedback loop is not a nice-to-have feature. It is the mechanism by which your system becomes more accurate and more format-independent with every document it processes.

---

### 4. The Five Layers of Intelligent Document Understanding

Enterprise-grade document intelligence systems are almost always structured as a layered pipeline. Each layer has a specific responsibility and passes its output to the next layer. This structure is important because it allows each layer to be improved or replaced independently without affecting the others.

**Layer One** is adaptive document ingestion and preprocessing. This layer handles the physical transformation of the document from a PDF file into clean, structured text. It includes OCR, image preprocessing, text normalization, and document classification.

**Layer Two** is semantic field recognition and entity extraction. This layer transforms clean text into structured field-value pairs. It uses a combination of NLP techniques, local language models, and learned extractors to identify what each piece of text means.

**Layer Three** is context-aware validation and cross-document reasoning. This layer validates extracted fields against each other and against business rules. It understands that fields do not exist in isolation and that the validity of one field often depends on the values of other fields.

**Layer Four** is format registry and AMC profile management. This layer stores everything the system has learned about each AMC's document format, allowing it to apply that knowledge when processing future documents from the same AMC.

**Layer Five** is continuous learning and self-correction. This layer processes human feedback from reviewers, updates the system's internal models, and improves extraction accuracy over time.

---

### 5. Layer One — Adaptive Document Ingestion and Preprocessing

This layer is the foundation of your pipeline. Everything downstream depends on the quality of the text that this layer produces. A weakness at this layer — poor OCR output, garbled table extraction, misidentified document type — will cause every subsequent layer to produce incorrect results regardless of how sophisticated they are.

**Document Classification**

Before you can extract anything from a document, you need to know what kind of document it is. Is this an engagement letter or an appraisal report? Is this a UAD 1004 form or an AMC-specific template? Is this a contract or a QC checklist?

Document classification is the process of automatically identifying the document type. This matters because different document types have different field schemas, different extraction strategies, and different validation rules. A field that is mandatory in an engagement letter may not even exist in a comparable sale document.

Classification should happen at two levels. The first level is broad category classification — engagement letter, appraisal report, contract, QC document, supporting document. The second level is specific template classification — which AMC's engagement letter template is this, or which version of the standard form is this.

The best way to implement document classification initially is through a combination of keyword signature detection and structural fingerprinting. Keyword signatures are sets of words and phrases that reliably appear in one document type but not others. Structural fingerprinting involves measuring properties of the document such as the number of pages, the approximate locations of text blocks, the presence or absence of specific section headers, and the density of tabular content.

**Adaptive OCR Strategy**

Not all PDFs are the same. Some are natively digital, meaning the text is embedded and can be extracted directly without OCR. Others are scanned documents where every page is essentially a photograph. And some are hybrids where some pages are digital and some are scanned.

The OCR strategy should be chosen adaptively based on the actual content of each page individually, not based on assumptions about the whole document. The system should check the word count of embedded text on each page and use that to decide whether to extract text directly, run OCR, or use a hybrid approach.

The OCR quality improvement pipeline — grayscale conversion, denoising, thresholding, deskew correction, and table line removal — should be applied selectively. Applying these transformations to a natively digital page does not improve results and wastes processing time.

**Text Normalization and Cleaning**

Raw OCR output is noisy. Common OCR artifacts include character confusion (O/0, l/1/I), adjacent characters being merged, characters being split, and line breaks inserted mid-field. Text normalization should be a pipeline of small, composable transformations: whitespace normalization, common OCR error correction, special character normalization, and numeric pattern normalization. All transformations should be recorded so outputs remain debuggable and traceable to the original OCR text.

**Table Detection and Linearization**

Tables are one of the hardest challenges in document extraction. Appraisal documents are full of tables — comparable sale grids, adjustment tables, condition rating matrices, fee schedules. These tables contain some of the most important data in the document, but they are also the most likely to break when document formats change.

The output of table extraction should not be raw text. It should be a structured representation where each cell is labeled with its row identifier and column identifier. This structured representation is what allows the downstream extraction layer to correctly interpret table data regardless of how different AMC templates arrange it visually.

---

### 6. Layer Two — Semantic Field Recognition and Entity Extraction

This is the layer where the fundamental transformation from format-dependent to format-independent extraction happens. The goal is to transform clean, normalized text into a structured set of named fields with extracted values and confidence scores.

**The Three-Tier Extraction Architecture**

The most robust approach uses three tiers operating in order, with the first successful tier's result accepted:

Tier One — Enhanced rule-based extraction. Your existing regex and pattern-based system, upgraded to include synonym expansion, fuzzy matching, and contextual patterns rather than rigid exact patterns. This tier is computationally cheap, always available, and very precise when it works. It provides a reliable floor of extraction quality.

Tier Two — Semantic similarity matching. A set of embedding vectors representing each field's concept is pre-computed. At extraction time, each candidate text segment is also converted to an embedding vector, and the system finds the field whose embedding vector is most similar. This handles label variation because synonymous labels produce embedding vectors that are close to the same concept vector.

Tier Three — LLM-based semantic extraction. A local language model is given the normalized document text and instructed to extract specific fields in a structured format. This tier is the most powerful but also the most computationally expensive and the most prone to hallucination errors. It should only be invoked when lower tiers fail.

**Named Entity Recognition for Appraisal Concepts**

Named Entity Recognition identifies and classifies specific types of information in text. For this platform, you need a specialized NER model that recognizes appraisal-domain entities — property addresses, appraised values, AMC names, appraisal dates, UAD codes, comparable sale details, and so on.

Building a domain-specific NER model for appraisal documents is one of the highest-value long-term investments you can make. Unlike the general-purpose LLM, a lightweight specialized NER model can run very quickly, does not require significant GPU resources, and can be highly accurate for the specific types of entities it was trained to recognize. The key to building a good domain NER model is training data — every document that passes through your platform, with its correctly extracted fields verified by human reviewers, is a potential training example.

**Field Schema and Ontology**

Your platform needs a formal definition of every field that can be extracted from every document type. This formal definition is called a field schema or field ontology. The schema specifies the field name, the field's data type, the field's possible values or value range, whether the field is required or optional, how the field relates to other fields, and what synonymous labels might be used for the field in different document formats.

The schema is the authoritative reference for what your system knows how to extract. When a new document format introduces a new way of expressing a known field, you update the schema to add the new expression. When a new document type introduces entirely new fields, you extend the schema to define them.

**Handling AMC-Specific Terminology and Abbreviations**

Every AMC has its own internal vocabulary. They use abbreviations, proprietary terms, and field labels that are specific to their organization. The solution is a terminology normalization layer that maintains a mapping of AMC-specific terms to their canonical equivalents. When an AMC uses an abbreviation like "B/R" to mean "Borrower," the terminology normalizer translates this before the semantic field recognition layer processes the text. This mapping should be stored as a structured data file that can be updated without changing any code, making AMC onboarding a configuration task rather than a development task.

---

### 7. Layer Three — Context-Aware Validation and Cross-Document Reasoning

Extraction tells you what values are in the document. Validation tells you whether those values are correct, complete, consistent, and meaningful. The key word is "context-aware." A context-aware validation system does not check each field in isolation. It understands the relationships between fields and uses those relationships to detect errors that no single-field check could catch.

**The Difference Between Format Validation and Semantic Validation**

Format validation checks that a value is in the expected format — a date should look like a date, a dollar amount should look like a dollar amount. Semantic validation checks that a value makes sense in context — an appraised value that is two hundred percent of the contract price is suspicious even if it is a correctly formatted dollar amount.

Semantic validation requires understanding not just the value of a field but its meaning and its relationship to other fields. This is what separates intelligent validation from simple rule checking.

**Cross-Document Consistency Checking**

Many QC checks require comparing information across multiple documents. The borrower name in the engagement letter should match the borrower name in the appraisal report. The contract price in the sales contract should be consistent with the contract price referenced in the appraisal report. The property address should be the same across all documents.

Cross-document consistency checking is the process of extracting the same conceptual field from multiple documents and verifying that the values agree. Values may be expressed differently across documents — "123 Main Street" in one document and "123 Main St." in another refer to the same address. Your consistency checker must handle these superficial differences without flagging them as errors. Normalization of addresses, names, and numeric values before comparison is essential.

**Dependency-Aware Rule Execution**

Some rules can only be evaluated if certain other rules have already passed. If the address extraction rule fails, an address-comparison rule cannot produce a meaningful result. The rule engine must understand these dependencies and skip or defer rules when their prerequisites have not been satisfied.

Rule results should be represented as a directed graph where edges represent dependencies. The engine processes rules in topological order, respecting the dependency structure. When a prerequisite rule returns EXTRACTION_FAILED or SYSTEM_ERROR, all dependent rules are automatically marked SKIPPED with a clear explanation that identifies the prerequisite failure.

---

### 8. How Enterprise Systems Solve This Problem

Enterprise-grade intelligent document processing platforms — such as those offered by major cloud providers and specialized IDP vendors — all converge on the same fundamental architecture when solving the document understanding problem at scale. Understanding how they approach it reveals the principles that should guide the long-term development of this platform.

**The Foundation Model Plus Fine-Tuning Approach**

Every serious enterprise IDP platform uses a pre-trained foundation model as the base and then fine-tunes it on domain-specific data. The foundation model provides broad language understanding — it has seen billions of documents and understands how language works in general. The fine-tuning step adapts that broad knowledge to the specific vocabulary, document structures, and field definitions of the target domain.

For this platform, the equivalent of the foundation model is a general-purpose local LLM like Mistral or Llama. The equivalent of fine-tuning is building a training dataset from human-reviewed extractions and using it to train a lightweight domain-specific classifier or NER model. You do not need GPU clusters to do this — lightweight models trained on labeled examples run on ordinary hardware.

**The Human-in-the-Loop Architecture**

Enterprise IDP systems never attempt to eliminate human review. Instead, they minimize the scope of human review to only the cases where automation is genuinely uncertain. The system processes the easy cases automatically with high confidence. It routes the hard cases to human reviewers with complete context — the source text, the extracted value, the confidence score, and a plain-language explanation of why the system is uncertain.

This architecture is optimal for three reasons. First, it is economically efficient — human time is spent only where it adds value. Second, it is more accurate than either pure automation or pure human review — automation handles scale, humans handle edge cases. Third, every human correction becomes a training signal that improves the automation, creating a compounding improvement loop over time.

**Confidence-Based Routing**

The routing decision — auto-accept, flag for review, or reject — is based on confidence scores. Enterprise systems define explicit thresholds: values above the auto-accept threshold are processed without human involvement, values between the review threshold and the auto-accept threshold are presented to reviewers in a streamlined interface, values below the reject threshold are returned to the source for clarification.

These thresholds are not fixed. They are calibrated over time based on the measured accuracy of the system. As accuracy improves, the auto-accept threshold rises and less work requires human attention. This is the mechanism by which the system's operational cost decreases over time even as the document volume grows.

**Structured Feedback as a First-Class System Feature**

Enterprise IDP systems treat structured feedback as a first-class feature, not an afterthought. The feedback interface is designed to make corrections easy and to capture the structured information needed to generate training examples. Reviewers are not just accepting or rejecting values — they are generating labeled training data with every correction they make.

The feedback schema is carefully designed to capture not just the correct value but the reason the original extraction was wrong. Was the OCR text garbled? Was the label unrecognized? Was the document in an unusual format? This structured error classification is what allows the system to improve the right component when something goes wrong.

---

### 9. The Right Technology Stack for Each Layer

Choosing the right tool for each layer of the pipeline is critical. Using the wrong tool — even a very powerful wrong tool — produces worse results than using the right simpler tool. This section maps the pipeline layers to the technology choices that are most appropriate given this platform's requirements and hardware constraints.

**Layer One — Ingestion and Preprocessing**

For text extraction from digital PDFs, PyMuPDF is the correct choice. It is fast, produces clean text with layout information, and is well-maintained. For converting scanned pages to images for OCR, pdf2image with Poppler produces clean 300 DPI images reliably. For image preprocessing — denoising, thresholding, deskew — OpenCV is the industry standard and runs efficiently on CPU without GPU requirements. For OCR itself, Tesseract remains the best open-source option for structured document text; PaddleOCR is an alternative worth evaluating for documents with complex layouts or mixed language content. For table extraction from PDFs, Camelot handles bordered tables reliably; pdfplumber handles whitespace-separated tables. Neither handles all cases, so both should be available with adaptive selection based on document structure.

**Layer Two — Field Recognition and Entity Extraction**

For the rule-based extraction tier, the current regex plus spatial-anchor approach is appropriate and should be extended with synonym expansion rather than replaced. For the semantic similarity tier, sentence-transformers running locally produces high-quality embeddings for short text segments and runs comfortably on CPU. For the LLM tier, Ollama with a locally-hosted model is the right infrastructure choice — it keeps data on-premises, avoids per-token API costs, and provides deterministic results at temperature zero. For lightweight NER model training, spaCy's training pipeline is the appropriate choice — it produces small, fast models that can be retrained incrementally as new training data accumulates.

**Layer Three — Validation**

The current rule engine architecture is appropriate and should be extended rather than replaced. Rules should be stored in the database with their severity, dependency relationships, and AMC applicability. The engine should process rules in dependency order. Cross-document comparison logic should be a separate component that receives normalized field values from all documents and returns consistency results. Normalization of addresses and names for comparison should use established libraries rather than custom code.

**Layer Four — Format Registry**

AMC profiles should be stored as structured data in the database or as YAML files in a configuration directory that is included in version control but not in deployable code. Each profile specifies the synonym mappings, confidence thresholds, and layout hints for that AMC's document templates. A profile registry service loads and caches these profiles and provides them to the extraction layer. When a new document is received, the system identifies its AMC and loads the corresponding profile before extraction begins.

**Layer Five — Continuous Learning**

For lightweight model training, scikit-learn is appropriate for the initial phases — it is well-understood, produces small models, and retrains quickly on modest hardware. For more capable NER models, spaCy's training pipeline with pre-trained weights as starting points is the right step up. Model versioning should use simple file naming conventions with timestamps plus a JSON manifest that records the training dataset version and accuracy metrics. Training should run as a scheduled background job, never inline in a request.

---

### 10. Transition Roadmap — From Regex to Intelligence

The transition from pure regex extraction to intelligent, format-independent extraction cannot happen in a single step. Attempting to replace the entire extraction system at once would introduce too much risk and would not produce usable results until the new system had accumulated enough training data to be reliable. The transition must happen incrementally, with each step measured before the next begins.

**Phase A — Solidify and Instrument the Regex Foundation (Current)**

The first phase is to make the current regex-based system as solid as possible and to instrument it completely. Every extraction must have confidence scores, source pages, raw OCR values, and extraction methods recorded. Every failed extraction must be logged with enough detail to understand why it failed. The feedback loop must be operational so that every reviewer correction is captured with full context.

This phase is not glamorous, but it is the foundation that makes every subsequent phase possible. Without accurate logging of what the current system is doing and where it is failing, you cannot measure whether subsequent improvements are actually working.

**Phase B — Synonym Expansion and Fuzzy Matching**

The second phase adds synonym expansion and fuzzy matching to the existing regex patterns. Instead of a regex that only matches "Borrower Name:", the pattern expands to also match "Client Name:", "Applicant:", "Loan Applicant:", "Customer Name:", and any other synonyms observed in the document corpus. The synonym lists are stored as configuration, not as code, so new synonyms can be added without deployment.

Fuzzy matching handles the case where a label is present but slightly garbled by OCR. Instead of requiring an exact character match, the system accepts matches that are within a configurable edit distance of the target pattern. This alone handles a significant fraction of the label-variation failures described in Section 2.

**Phase C — Embedding-Based Semantic Search**

The third phase adds embedding-based semantic search as the second tier of the three-tier extraction architecture. For each field in the schema, a set of representative phrases is pre-computed into embedding vectors. At extraction time, candidate text segments are also converted to embedding vectors, and the closest matching field concept is identified.

This phase requires pre-computing and storing embedding vectors for all fields and all their synonymous expressions. It requires a lightweight embedding model that runs on CPU. And it requires a confidence threshold that determines when an embedding match is strong enough to accept versus when it should fall through to the LLM tier.

**Phase D — Domain NER Model Training**

The fourth phase begins training a domain-specific NER model on the labeled examples accumulated during Phases A through C. The model is trained to recognize appraisal-domain entities — borrower names, property addresses, appraised values, dates, UAD codes — regardless of the specific label wording used in the source document.

This phase requires having accumulated at least several hundred labeled examples per entity type. The NER model becomes an additional extraction tier that operates independently of label matching entirely. It reads the normalized document text and identifies entities by their semantic role in the text, not by the labels that precede them.

**Phase E — LLM Orchestration for Complex Inference**

The fifth phase uses the local LLM not just as a fallback for individual field extraction but as an orchestrator for complex multi-field inference. Some fields cannot be extracted in isolation — their correct value can only be determined by reading several paragraphs of context. The LLM is given a carefully constructed context window containing the relevant text and is asked to extract a structured set of fields simultaneously.

This phase should only begin once the earlier phases have been measured and confirmed to provide meaningful improvement. The LLM is powerful but expensive in inference time. It should only be invoked for the cases that genuinely require its capabilities.

---

### 11. Handling Multiple AMC Formats Without Breaking

Every new AMC that your platform onboards represents a potential source of extraction failures. Each AMC has its own document templates, its own terminology, its own field layout preferences. The naive approach is to add AMC-specific patterns to the existing extraction code — but this approach does not scale. After ten AMCs, the extraction code becomes a branching mess of special cases that is impossible to maintain.

**The AMC Profile System**

The correct approach is to build an AMC profile system. Each AMC has a profile — a structured data file that describes everything the system needs to know to extract fields from that AMC's documents correctly. The profile specifies synonym mappings (what this AMC calls each standard field), confidence thresholds (how certain the system needs to be before auto-accepting values for this AMC), layout hints (which pages typically contain which fields for this AMC), and any special parsing rules that apply only to this AMC's documents.

The profile is loaded at the beginning of document processing, before extraction begins. The extraction layer uses the profile to configure its synonym lookup and threshold decisions. The rule engine uses the profile to determine which rules are applicable to this AMC's document types.

When a new AMC is onboarded, the work is profile creation — reviewing sample documents, identifying terminology mappings, setting initial thresholds. This is a configuration task, not a development task. No code changes are needed to onboard a new AMC.

**Document Fingerprinting**

Document fingerprinting is the process of automatically identifying which AMC's template a document was created with. The fingerprint is derived from structural properties of the document — the positions of specific text blocks, the presence of AMC-specific boilerplate text, the layout of standard sections. When a document arrives without an explicit AMC identifier, the fingerprinting system compares its structural properties against the stored fingerprints of all known AMC templates and selects the closest match.

Fingerprinting should be confident before loading an AMC-specific profile. When fingerprinting confidence is below the acceptance threshold, the system falls back to a generic extraction profile that uses broad synonym lists and lower confidence thresholds. This produces lower confidence extraction results that require more human review, but it is better than applying the wrong AMC profile.

**Progressive Format Learning**

As the system processes more documents from each AMC, it should progressively learn and refine the AMC profile. New synonyms observed in reviewed documents should be candidate additions to the AMC's synonym list. Threshold adjustments that reduce human correction rates should be incorporated into the AMC profile. The profile is a living document that improves with every document the system processes from that AMC.

---

### 12. The Confidence-Scoring System

Confidence scores are the mechanism by which the system communicates its uncertainty to downstream components and to human reviewers. A confidence score that is not accurately calibrated — that says 0.9 when it is actually right only 60% of the time — is worse than no confidence score at all, because it misleads routing decisions and reviewer attention.

**How Confidence Is Computed**

Confidence scoring should be a function of multiple factors, each contributing to the final score:

- **Extraction tier used:** Exact label match from the regex tier produces the highest base confidence. Synonym match from the expanded regex tier produces slightly lower confidence. Embedding match from the semantic tier produces moderate confidence. LLM inference produces variable confidence based on the LLM's own output quality signals.

- **OCR quality on the source page:** A field extracted from a page where OCR confidence is high warrants higher extraction confidence. A field extracted from a noisy page warrants lower confidence regardless of how well the pattern matched.

- **Field value plausibility:** A date field that produces a date within a plausible range warrants higher confidence than one that produces an implausible date. A dollar amount within the expected range for the document type warrants higher confidence.

- **Agreement across extraction tiers:** When multiple extraction tiers independently produce the same value, confidence is higher than when only one tier finds the value.

**Confidence Calibration**

Calibration is the process of measuring whether the system's confidence scores are honest. A perfectly calibrated system is right 80% of the time when it says 0.80 confidence, right 60% of the time when it says 0.60 confidence, and so on.

Calibration measurement requires accumulating pairs of (confidence score at extraction time, was the extraction actually correct as judged by the reviewer). This data is available in the feedback system — every reviewer correction on a field is evidence that the extraction was wrong at whatever confidence the system reported. Calibration should be measured quarterly and confidence score formulas adjusted when systematic over- or under-confidence is detected.

**Confidence Thresholds and Routing**

Three thresholds govern routing decisions:

- **Auto-accept threshold:** Extractions above this threshold are accepted without human review. Set conservatively initially — as calibration improves, this threshold can be raised.
- **Review threshold:** Extractions between the review threshold and the auto-accept threshold are presented to human reviewers. The reviewer sees the extracted value, the source text, and a plain-language explanation of why the system is uncertain.
- **Reject threshold:** Extractions below the reject threshold are treated as not-found. The field is marked as requiring manual input.

These thresholds may be different per field type and per AMC. A field that is simple to extract reliably may have a higher auto-accept threshold than a complex narrative field. An AMC whose documents are consistently high quality may have higher thresholds than one whose documents arrive as low-resolution scans.

---

### 13. Building the Feedback Loop

The feedback loop is the mechanism by which every human correction makes the system smarter. Without a well-designed feedback loop, the system makes the same mistakes indefinitely. With a well-designed feedback loop, the system's accuracy improves continuously as document volume grows.

**The Feedback Event Schema**

Every feedback event must capture the complete context of the correction:

- The original OCR text from the source page
- The value the system extracted from that OCR text
- The value the reviewer determined is correct
- The rule or field type involved
- The page number where the source text appeared
- The AMC and document type
- The extraction method and confidence score at the time of extraction
- The reviewer's classification of the error type: OCR quality issue, label not recognized, document format unusual, system error, or other

The error type classification is particularly important. It tells you which component of the pipeline needs improvement. An OCR quality issue requires improving the preprocessing pipeline. A label not recognized issue requires adding a synonym to the AMC profile. A document format unusual issue requires creating or updating an AMC profile.

**From Corrections to Training Examples**

Not every feedback event is immediately useful as a training example. A feedback event becomes a training example when it meets three criteria: the original OCR text is available, the extracted value and the correct value are both recorded, and the error type has been classified.

Training examples should be deduplicated — multiple corrections of the same field type with the same root cause should be grouped rather than each producing an independent training example. The training example generation process should run as a background job that processes new feedback events periodically and produces a growing labeled dataset.

**Retraining Cadence**

Model retraining should happen on a defined schedule, not ad hoc. Weekly retraining for the OCR correction and field confidence models is appropriate once the feedback volume reaches a meaningful level. Monthly retraining for the commentary classifier is appropriate. Each retraining run should measure accuracy on a held-out validation set and refuse to deploy a new model version that is less accurate than the current one.

**Active Learning**

Active learning is an optimization of the feedback loop that maximizes the value of human reviewer time. Instead of routing all low-confidence extractions to reviewers, active learning prioritizes the corrections that will provide the most training value — typically the cases where the system is most uncertain or where errors are most concentrated in underrepresented document types. A simple implementation assigns higher review priority to fields where confidence is in the middle of the distribution, because those are the cases where the system is genuinely uncertain and where a correction provides the most information.

---

### 14. Data Quality and Training Data Strategy

The quality of the training data determines the ceiling of the system's accuracy. No model, however sophisticated, can exceed the accuracy of the data it was trained on. Managing data quality is therefore as important as managing code quality.

**What Makes a Good Training Example**

A good training example for this system has four properties: it is labeled correctly by a domain expert, it contains the complete raw OCR text (not just the extracted value), it covers a document type and field type that the system actually needs to handle, and it includes metadata about how it was generated (which document, which page, which AMC, which extraction method).

Incorrectly labeled training examples are worse than having no training examples. They teach the model wrong behaviors that are then difficult to diagnose and correct. Every labeled example should be reviewed by a domain expert before being added to the training dataset.

**Bootstrapping with Human-Labeled Documents**

In the early phase, before the feedback loop is generating training data, the training dataset must be bootstrapped with human-labeled documents. This means processing a representative set of documents from each supported AMC, having a domain expert review the extraction results, correcting all errors, and adding the correct extractions to the training dataset.

The bootstrapping set should cover the range of variation in your document corpus. It should include simple documents with clean OCR and clear labels, difficult documents with noisy OCR or unusual layouts, and edge cases that are rare but important. Approximately fifty examples per field type per document category is a reasonable initial target.

**Data Versioning**

The training dataset is code — it should be versioned, and every model version should be traceable to the exact training dataset version it was trained on. When a model produces an unexpected output on a new document type, you need to be able to answer the question: what training examples influenced this model's behavior for this type of input?

Dataset versioning does not require sophisticated tooling. A simple approach is to assign each training run a dataset version identifier and to record in the model manifest which dataset version was used for training. The dataset itself is stored as a set of labeled JSON files in a versioned directory.

**Protecting Against Training Data Contamination**

Training data contamination occurs when the same examples appear in both the training set and the validation set. This produces optimistic accuracy measurements that do not reflect real-world performance. The validation set must be strictly held out from training — it should consist of examples that the model has never seen during any training run.

Contamination is particularly dangerous with continuous learning systems, where new training data is added regularly. The validation set should be frozen at the time of the initial bootstrapping and never augmented with new examples. New labeled examples go into the training set, not the validation set.

---

### 15. Infrastructure Considerations Given Your Hardware

The architecture described in this document must be implemented on hardware that has real constraints. An 8GB M1 Mac running all services locally is not the same as a cloud environment with elastic compute. Understanding these constraints prevents architectural decisions that look good on paper but fail in practice.

**Memory and Model Loading**

The primary memory constraint is Ollama model loading. A 7-billion-parameter model requires approximately 4-5 GB of RAM. A 13-billion-parameter model requires approximately 8-9 GB of RAM. On an 8GB system, only one large model can be in memory at a time. The operating system, database, application server, and other services consume the remaining memory.

This means the dual-model strategy — fast text model for text tasks, vision model for image tasks — requires explicit model switching. When the pipeline needs to switch from text analysis to vision analysis, there will be a 10-15 second loading delay while Ollama swaps models. The pipeline must account for this delay in its timeout calculations and should never attempt to run both models simultaneously.

**Processing Throughput Estimates**

On an 8GB M1 Mac with the current architecture, realistic throughput expectations are:

- OCR with the parallel thread pool: 4-6 pages per second for embedded text extraction, 1-2 pages per second for Tesseract OCR
- Phase 2 field extraction after OCR: under 200 milliseconds per document for regex-based extraction
- Rule engine execution: under 100 milliseconds for all rules combined on cached documents
- LLM commentary analysis: 1-3 seconds per call with the fast text model, 30-45 seconds with the vision model
- End-to-end for a 30-page document without LLM: approximately 20-25 seconds cold, under 1 second cached

These numbers inform the timeout settings for each pipeline stage and the user experience expectations communicated to reviewers.

**When to Move to Cloud Infrastructure**

The current local infrastructure is appropriate for development and for initial production use at low document volumes. The decision to move to cloud infrastructure should be based on measured document throughput rather than predicted volume. When the local system is processing documents at its maximum throughput for sustained periods — meaning the queue is growing faster than it is being processed — it is time to move to cloud infrastructure.

The architecture described in this document is cloud-compatible without modification. The pipeline layers, the feedback loop, the model training infrastructure, and the AMC profile system all translate directly to cloud deployment. The primary change is replacing local Ollama with a GPU-backed inference endpoint and replacing the local file system with cloud object storage.

**Database Optimization**

PostgreSQL on local hardware performs well for the document volumes expected in the early phases of this platform. The critical indexes — on file hash for deduplication, on document ID for all related tables, on feedback training status — must exist from the beginning. Query patterns that scan large tables without index support will cause visible performance problems at even modest document volumes. Every query that appears in the hot path should be analyzed with EXPLAIN ANALYZE before deployment.

---

### 16. What to Build First, Second, and Third

The temptation in building an intelligent system is to try to build all of the intelligence at once. This never works. Intelligence requires training data, and training data requires a deployed system that is processing real documents and capturing feedback. The correct sequence is to deploy a working system first, collect data second, and build intelligence third.

**First: A Fully Instrumented, Correctly Calibrated Regex System**

The first priority is to make the current extraction system complete, correct, and fully instrumented. This means: every field has a confidence score, every extraction has a source page, every result has a raw OCR value recorded, every feedback event is captured with full context, and the feedback-to-training-example pipeline is operational.

This is the state the system should be in now or should reach within the next development increment. Until this is true, no subsequent phases can be measured accurately.

**Second: AMC Profile System and Synonym Expansion**

The second priority is to move all AMC-specific extraction knowledge out of code and into configurable profiles. This means building the profile loader, creating initial profiles for all current AMC templates based on observed document patterns, and replacing any hardcoded AMC-specific patterns in extraction code with profile-driven synonym lookup.

This phase produces immediate, measurable value: new AMC templates can be onboarded without code changes. It also produces a clean foundation for the semantic extraction tiers that come next, because the synonym registry is the starting point for the embedding-based field matching.

**Third: Embedding-Based Semantic Field Recognition**

The third priority is to add the embedding-based semantic tier. This means pre-computing embedding vectors for all fields and their synonymous expressions, building the candidate segment selection logic that identifies which parts of the document text are candidates for each field, and adding the confidence-weighted merging step that combines results from the regex tier and the embedding tier.

This phase handles the label-variation failure mode described in Section 2. Fields that the regex tier misses because the label wording is unfamiliar will be caught by the embedding tier. The improvement should be measurable as an increase in high-confidence extractions and a decrease in NOT_FOUND results on documents from AMC templates that have not been explicitly profiled.

**Subsequent Phases**

After these three phases are measured and stable, the logical next steps are: training a lightweight domain NER model on the accumulated labeled data, adding multi-document consistency checking as a validation layer, and building the AMC fingerprinting system for automatic profile selection. Each of these phases builds on the data and infrastructure created by earlier phases and should only begin once the measurement gate for the previous phase has been passed.

---

### 17. Common Mistakes to Avoid

These are the mistakes that most commonly slow down or derail intelligent document extraction projects. They are listed here because they are not obvious, and they tend to be discovered only after significant time has been invested in the wrong direction.

**Building the ML system before having enough training data.** A machine learning model trained on fewer than a few hundred examples per class will not outperform a well-tuned rule-based system. Do not invest engineering effort in training infrastructure until the feedback loop is generating at least several hundred labeled examples per field type. Until then, use the rule-based fallback.

**Optimizing for document formats you do not have yet.** Every engineering decision should be driven by documents you have actually processed or are processing now. Do not build extraction logic for AMC templates you have not seen. Do not add validation rules for field combinations you have not observed. Build for what exists, measure it, then expand to cover what you discover next.

**Using the LLM for structured field extraction.** This bears repeating because it is the most common mistake in systems like this. LLMs are powerful at understanding meaning in text but are unreliable for precise value extraction. They hallucinate, they paraphrase, they interpret ambiguous text differently on different runs. For fields where the exact value matters — addresses, dollar amounts, dates — always use regex with synonym expansion. Reserve the LLM for evaluative tasks where approximate understanding is sufficient.

**Ignoring the confidence calibration problem.** If you deploy a system that reports 0.9 confidence on extractions that are actually correct only 60% of the time, you will route too many incorrect extractions to the auto-accept path, and reviewers will begin to distrust the system. Calibration measurement is not optional — it should be a metric that is tracked from the beginning.

**Not versioning models.** When a retrained model produces worse results on a class of documents, you need to be able to roll back to the previous version immediately. If model versions are overwritten rather than versioned, rollback requires retraining, which may take hours. Always version models with timestamps and always retain at least the two previous versions in production-ready storage.

**Treating the reviewer interface as a secondary concern.** The reviewer interface is not a display layer — it is the mechanism by which training data is generated. A reviewer interface that makes corrections tedious or that fails to capture error context is actively degrading the quality of the training dataset. The reviewer interface should be designed with the same care as the extraction pipeline itself.

**Accumulating technical debt in extraction patterns.** Every regex anchored to a specific label wording is debt. Every hardcoded threshold is debt. Every AMC-specific pattern in code rather than in a profile is debt. This debt is invisible until you try to onboard a new AMC or handle a new document format, at which point it manifests as cascading failures. Pay this debt incrementally — move patterns to configuration, move thresholds to profiles, every time you touch extraction code.

---

### 18. Final Architecture Summary

The architecture described in this document is designed to remain valid for the life of the platform — not just for the next increment. It is designed to handle the extraction problem as it actually is: a fundamentally semantic challenge that cannot be permanently solved by pattern matching alone.

**The Five-Layer Summary**

Layer One handles the physical transformation from PDF to clean text. It is adaptive — it chooses the right OCR strategy per page, normalizes text consistently, and represents tables as structured data rather than raw strings. Its output is deterministic for a given document and is cached to avoid redundant processing.

Layer Two handles the semantic transformation from text to field values. It uses three tiers in order: enhanced regex with synonym expansion, embedding-based semantic matching, and LLM inference as a final fallback. Every extracted field carries confidence, source page, extraction method, and raw OCR value. Its output is always a complete field result, even when that result is "not found with zero confidence."

Layer Three handles validation and cross-document reasoning. It checks field values against each other, against business rules, and against the values in other documents in the same case. It understands field dependencies and processes rules in dependency order. Its output is the QC report — the authoritative list of rule results that drives reviewer attention.

Layer Four stores accumulated format knowledge. AMC profiles, synonym registries, confidence thresholds, and document fingerprints live here as configuration that can be updated without code changes. Its output is the configured extraction environment that Layer Two uses when processing a document.

Layer Five learns from human corrections. It captures every reviewer correction with full context, converts corrections to training examples, retrains models on a defined schedule, and measures accuracy before deploying new model versions. Its output is the continuously improving extraction capability that makes the system more accurate with every document it processes.

**The Learning Flywheel**

The long-term value of this architecture is not in any single component. It is in the flywheel: more documents processed means more reviewer corrections means more training data means better extraction accuracy means less human correction needed means more documents can be processed without increasing human costs. This flywheel only spins if the feedback loop is operational, the training data is high quality, and the model retraining pipeline is reliable.

Every engineering decision made on this platform should be evaluated against one question: does this help the flywheel spin faster, or does it slow it down? Features that improve extraction accuracy, improve reviewer efficiency, improve training data quality, or improve model reliability are aligned with the flywheel. Features that bypass the feedback loop, that produce hard-to-diagnose failures, or that make training data less accurate work against it.

**The Path from Where You Are to Where You Need to Be**

The platform has already completed the foundational work: the OCR pipeline is parallel and cached, field extraction produces confidence scores and source pages, the rule engine is stable and isolated, the feedback loop is operational. The next phase — AMC profile system and synonym expansion — is achievable in the near term and will produce measurable accuracy improvements on documents from AMC templates that are not yet explicitly handled.

Each subsequent phase — embedding-based semantic matching, domain NER model training, multi-document consistency checking — is achievable given the infrastructure that will be in place after the current phase. The architecture is designed so that each phase is a natural extension of the previous one, not a replacement.

The extraction accuracy ceiling is high. The platform has the right foundation, the right data strategy, and the right long-term architecture to reach it.

---

*Last updated: 2026-05-15*
*Source: Apprisal Platform — Adaptive & Future-Proof Document Extraction Architecture Guide*
*Prepared for: EagleX Info Solution PVT LTD*
