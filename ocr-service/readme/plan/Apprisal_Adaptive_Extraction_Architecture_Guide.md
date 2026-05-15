# Apprisal Platform — Adaptive & Future-Proof Document Extraction Architecture Guide

**Prepared for:** EagleX Info Solution PVT LTD  
**Document Purpose:** Long-term strategic and architectural guidance for moving from regex-based extraction to intelligent, format-independent, context-aware document understanding  
**Scope:** Engagement letters, appraisal reports, contact forms, AMC templates, QC documents, and all appraisal workflow documents  
**Audience:** Platform architects, backend engineers, product owners

---

## Table of Contents

1. Understanding the Core Problem
2. Why Regex and Fixed Patterns Eventually Fail
3. The Philosophy of Format-Independent Extraction
4. The Five Layers of Intelligent Document Understanding
5. Layer One — Adaptive Document Ingestion and Preprocessing
6. Layer Two — Semantic Field Recognition and Entity Extraction
7. Layer Three — Context-Aware Validation and Cross-Document Reasoning
8. Layer Four — Format Registry and AMC Profile Management
9. Layer Five — Continuous Learning and Self-Correction
10. How Enterprise Systems Solve This Problem
11. The Right Technology Stack for Each Layer
12. Transition Roadmap — From Regex to Intelligence
13. Handling Multiple AMC Formats Without Breaking
14. The Confidence-Scoring System
15. Building the Feedback Loop
16. Data Quality and Training Data Strategy
17. Infrastructure Considerations Given Your Hardware
18. What to Build First, Second, and Third
19. Common Mistakes to Avoid
20. Final Architecture Summary

---

## 1. Understanding the Core Problem

Before designing any solution, it is essential to understand the exact nature of the problem at a deep level. The challenge you are facing is not a technical limitation of your current code. It is a fundamental mismatch between two very different things: the stability of meaning and the instability of format.

In every document your platform processes, the meaning is stable. Every engagement letter, regardless of which AMC sent it, regardless of how it was designed or formatted, is trying to communicate the same set of facts. There is a borrower. There is a property. There is a fee. There is an effective date. There is an AMC. These facts do not change. Their meaning does not change. What changes is only the way those facts are represented visually and textually on the page.

Your current regex-based system has essentially hardcoded the assumption that meaning and representation are the same thing. When your system looks for a specific string like "Borrower Name:" followed by a value, it is assuming that the word "Borrower" will always be used, that the colon will always appear, that the spacing will always follow the same pattern, and that the field will always appear in roughly the same location. Every one of those assumptions is a fragility point.

The long-term solution is to build a system that understands meaning independently of representation. This is the core principle that all enterprise-grade intelligent document processing platforms are built on. The system should be able to read any document that communicates appraisal-related information and extract the correct facts, regardless of how those facts happen to be expressed on that particular day, by that particular AMC, using that particular PDF template.

---

## 2. Why Regex and Fixed Patterns Eventually Fail

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

## 3. The Philosophy of Format-Independent Extraction

Format-independent extraction is not a single technology. It is a design philosophy that informs every decision you make about your extraction pipeline. The philosophy has four principles.

**Principle one: Extract meaning, not patterns.** Your extraction layer should ask the question "what does this text mean?" rather than "does this text match this pattern?" This shifts the fundamental operation from string matching to semantic understanding. When a piece of text says "The undersigned borrower hereby confirms their identity as John Smith," a meaning-based system understands that John Smith is the borrower, even though the word "Borrower Name:" never appeared.

**Principle two: Separate extraction from validation.** Your extraction layer should focus only on pulling values out of documents. Your validation layer should focus only on checking whether those values are correct, complete, and consistent. When these two concerns are mixed together — when extraction logic includes hardcoded business rules about what valid values look like — changing one requires modifying the other. Separating them makes both more maintainable and more testable.

**Principle three: Use confidence, not binary pass/fail.** Every extracted field should carry a confidence score. A field that was found by an exact label match with high-quality OCR text gets a high confidence score. A field that was inferred from surrounding context with noisy OCR text gets a lower confidence score. The downstream system uses confidence scores to decide whether to auto-accept the value, flag it for human review, or reject it entirely. This makes your system graceful rather than brittle. Instead of failing catastrophically when a field cannot be found, it simply returns a low-confidence empty value and routes the document to a human reviewer.

**Principle four: Learn continuously from corrections.** Every time a human reviewer corrects an extracted value, that correction is a training signal. The system that learns from these corrections gets better over time. The system that does not learn repeats the same mistakes indefinitely. Building a feedback loop is not a nice-to-have feature. It is the mechanism by which your system becomes more accurate and more format-independent with every document it processes.

---

## 4. The Five Layers of Intelligent Document Understanding

Enterprise-grade document intelligence systems are almost always structured as a layered pipeline. Each layer has a specific responsibility and passes its output to the next layer. This structure is important because it allows each layer to be improved or replaced independently without affecting the others.

The five layers are as follows, and the sections that follow will explain each one in depth.

**Layer One** is adaptive document ingestion and preprocessing. This layer handles the physical transformation of the document from a PDF file into clean, structured text. It includes OCR, image preprocessing, text normalization, and document classification.

**Layer Two** is semantic field recognition and entity extraction. This layer transforms clean text into structured field-value pairs. It uses a combination of NLP techniques, local language models, and learned extractors to identify what each piece of text means.

**Layer Three** is context-aware validation and cross-document reasoning. This layer validates extracted fields against each other and against business rules. It understands that fields do not exist in isolation and that the validity of one field often depends on the values of other fields.

**Layer Four** is format registry and AMC profile management. This layer stores everything the system has learned about each AMC's document format, allowing it to apply that knowledge when processing future documents from the same AMC.

**Layer Five** is continuous learning and self-correction. This layer processes human feedback from reviewers, updates the system's internal models, and improves extraction accuracy over time.

---

## 5. Layer One — Adaptive Document Ingestion and Preprocessing

This layer is the foundation of your pipeline. Everything downstream depends on the quality of the text that this layer produces. A weakness at this layer — poor OCR output, garbled table extraction, misidentified document type — will cause every subsequent layer to produce incorrect results regardless of how sophisticated they are.

### Document Classification

Before you can extract anything from a document, you need to know what kind of document it is. Is this an engagement letter or an appraisal report? Is this a UAD 1004 form or an AMC-specific template? Is this a contract or a QC checklist?

Document classification is the process of automatically identifying the document type. This matters because different document types have different field schemas, different extraction strategies, and different validation rules. A field that is mandatory in an engagement letter may not even exist in a comparable sale document.

Classification should happen at two levels. The first level is broad category classification — engagement letter, appraisal report, contract, QC document, supporting document. The second level is specific template classification — which AMC's engagement letter template is this, or which version of the URAR form is this.

The best way to implement document classification initially is through a combination of keyword signature detection and structural fingerprinting. Keyword signatures are sets of words and phrases that reliably appear in one document type but not others. Structural fingerprinting involves measuring properties of the document such as the number of pages, the approximate locations of text blocks, the presence or absence of specific section headers, and the density of tabular content. Together, keyword signatures and structural fingerprinting can accurately classify most documents without requiring a GPU or a large language model.

As your system matures and you accumulate training data, you can upgrade classification to a lightweight machine learning model that has been trained on real examples of each document type in your corpus.

### Adaptive OCR Strategy

Not all PDFs are the same. Some are natively digital, meaning the text is embedded in the PDF and can be extracted directly without any OCR. Others are scanned documents where every page is essentially a photograph. And some are hybrids where some pages are digital and some are scanned.

Your current system already handles this distinction with its fast path and fallback path. The important architectural point is that the OCR strategy should be chosen adaptively based on the actual content of the document, not based on assumptions. Specifically, the system should check each page individually rather than assuming the entire document is one type or the other.

The OCR quality improvement pipeline — grayscale conversion, denoising, thresholding, deskew correction, and table line removal — should be applied selectively. Applying these transformations to a natively digital PDF does not improve results and wastes processing time. The system should detect the text quality of the raw extraction and only invoke image preprocessing when the quality falls below an acceptable threshold.

A critical and often overlooked aspect of OCR preprocessing is resolution calibration. Documents scanned at low resolution — less than 200 DPI — produce blurry images that cause high OCR error rates. Documents scanned at unnecessarily high resolution — above 400 DPI — produce large files that slow processing without meaningful accuracy improvement. Three hundred DPI is the industry-standard sweet spot and your current choice of 300 DPI is correct. However, the system should be able to detect the effective resolution of a scanned document and adjust accordingly.

### Text Normalization and Cleaning

Raw OCR output is noisy. Even high-quality OCR produces errors. Common OCR artifacts include the letter "O" being read as the digit "0," the letter "l" being read as the digit "1" or the letter "I," adjacent characters being merged into a single character, characters being split into multiple characters, and line breaks being inserted in the middle of a field value.

Text normalization is the process of cleaning these artifacts before the text reaches your extraction layer. Normalization should not be a single monolithic function. It should be a pipeline of small, composable transformations, each with a specific responsibility. Transformations include whitespace normalization, which collapses multiple spaces and irregular line breaks into clean single spaces. They include common OCR error correction, which uses a dictionary of known OCR confusion pairs to fix systematic character recognition errors. They include special character normalization, which converts curly quotes to straight quotes, em dashes to hyphens, and non-breaking spaces to regular spaces. And they include numeric pattern normalization, which ensures that dollar amounts, dates, percentages, and measurement values are always represented in a consistent format regardless of how they appeared in the original document.

An important principle in text normalization is that all normalization transformations should be recorded. When a transformation changes the text, the system should keep a record of what the original text was and what transformation was applied. This audit trail is important both for debugging extraction errors and for demonstrating to reviewers how a value was derived.

### Table Detection and Linearization

Tables are one of the hardest challenges in document extraction. Appraisal documents are full of tables — comparable sale grids, adjustment tables, condition rating matrices, fee schedules, and certification checklists. These tables contain some of the most important data in the document, but they are also the most likely to break when document formats change.

Table detection is the process of identifying regions of the document that contain tabular data, understanding the row and column structure of those tables, and linearizing the table into a text representation that preserves the relationships between cells.

The key insight about tables is that the visual structure of a table — its borders, its column spacing, its header rows — is just a presentation choice. The underlying data relationships are what matter. A system that understands "this cell is in the same row as that cell and in a column labeled Comparable 1" can handle changes to the visual presentation of the table as long as the data relationships are preserved.

There are three approaches to table extraction that work well in combination. The first is rule-based line detection, where you look for horizontal and vertical lines in the document and use them to identify table boundaries and cell boundaries. The second is whitespace-based column detection, where you analyze the distribution of whitespace in a region of text to infer column boundaries even when no visible lines are present. The third is header-based structure inference, where you look for row or column headers and use them to label the cells in each row and column.

The output of table extraction should not be raw text. It should be a structured representation where each cell is labeled with its row identifier and column identifier. This structured representation is what allows your downstream extraction layer to correctly interpret "the Adjusted Sale Price of Comparable 2 is $285,000" even when different AMC templates arrange this information differently.

---

## 6. Layer Two — Semantic Field Recognition and Entity Extraction

This is the layer where the fundamental transformation from format-dependent to format-independent extraction happens. The goal of this layer is to transform clean, normalized text into a structured set of named fields with extracted values and confidence scores.

### The Problem with Label-Based Extraction

Traditional extraction systems work by looking for a label followed by a value. The label might be "Borrower Name:" and the value is the text that follows the colon. This approach works well when labels are consistent, but fails when they vary.

The limitation is that it treats extraction as a pattern-matching problem rather than an understanding problem. A label-based system can only extract a field if it knows in advance what label that field will have. It cannot handle novel labels that mean the same thing, and it cannot handle cases where no explicit label is present and the value must be inferred from context.

Semantic field recognition approaches the problem differently. Instead of asking "does this text match a known label?", it asks "does this text express a concept that corresponds to a known field?" This is a fundamentally more powerful question because it can be answered correctly even when the specific words used are unfamiliar.

### The Three-Tier Extraction Architecture

The most robust approach to semantic field extraction uses three tiers operating in parallel, with a confidence-based merging step that combines their outputs.

**Tier One — LLM-based semantic extraction.** A local language model is given the normalized document text and instructed to extract specific fields in a structured format. The model's training allows it to understand synonymous labels, to infer values from context, and to handle a wide variety of phrasings and document structures. The model returns a structured output with field names, extracted values, and confidence indicators. This tier is the most powerful but also the most computationally expensive and the most prone to hallucination errors.

**Tier Two — Semantic similarity matching.** A set of embedding vectors representing each field's concept is pre-computed. At extraction time, each candidate text segment is also converted to an embedding vector, and the system finds the field whose embedding vector is most similar. This approach handles label variation because "Borrower Name," "Client Name," "Applicant Name," and "Customer Name" will all produce embedding vectors that are close to the embedding vector for the "borrower name" concept, even if none of those exact phrases were seen during training.

**Tier Three — Enhanced rule-based extraction.** Your existing regex and pattern-based system, upgraded to include synonym expansion, fuzzy matching, and contextual patterns rather than rigid exact patterns. This tier is computationally cheap, always available, and very precise when it works. It provides a high-confidence floor of extraction quality that can always be relied upon.

The merging step takes the outputs of all three tiers and resolves conflicts using confidence scores. When two tiers agree on a value, confidence is high. When they disagree, the conflict is flagged for human review. When only one tier finds a value, that value is returned with moderate confidence and flagged for potential review depending on the importance of the field.

### Named Entity Recognition for Appraisal Concepts

Named Entity Recognition, commonly abbreviated as NER, is an NLP technique that identifies and classifies specific types of information in text. Traditional NER models recognize general entities like person names, organization names, locations, and dates. For your platform, you need a specialized NER model that recognizes appraisal-domain entities — property addresses, appraised values, AMC names, appraisal dates, UAD codes, comparable sale details, and so on.

Building a domain-specific NER model for appraisal documents is one of the highest-value long-term investments you can make. Unlike the general-purpose LLM, a lightweight specialized NER model can be run very quickly, does not require significant GPU resources, and can be highly accurate for the specific types of entities it was trained to recognize.

The key to building a good domain NER model is training data. Every document that passes through your platform, with its correctly extracted fields verified by human reviewers, is a potential training example. Over time, your accumulated training data allows you to build a specialized extractor that outperforms general-purpose models on your specific document types.

### Field Schema and Ontology

Your platform needs a formal definition of every field that can be extracted from every document type. This formal definition is called a field schema or field ontology. The schema specifies the field name, the field's data type, the field's possible values or value range, whether the field is required or optional, how the field relates to other fields, and what synonymous labels might be used for the field in different document formats.

The schema is the authoritative reference for what your system knows how to extract. When a new document format introduces a new way of expressing a known field, you update the schema to add the new expression. When a new document type introduces entirely new fields, you extend the schema to define them.

The field schema has a second important function. It allows your system to recognize when a field is missing entirely from a document, rather than simply failing to find it. If the schema says that a field is required and the extraction layer returns nothing for that field, the system can take an appropriate action — flag the document for review, request clarification, or look for the field in a secondary location.

### Handling AMC-Specific Terminology and Abbreviations

Every AMC has its own internal vocabulary. They use abbreviations, proprietary terms, and field labels that are specific to their organization. A system that only understands industry-standard terminology will struggle with AMC-specific documents.

The solution is a terminology normalization layer that sits between raw text extraction and semantic field recognition. This layer maintains a mapping of AMC-specific terms to their canonical equivalents. When an AMC uses the abbreviation "B/R" to mean "Borrower," the terminology normalizer translates this to "Borrower" before the semantic field recognition layer processes the text.

Building this terminology mapping initially requires manual effort — reviewing documents from each AMC and identifying their specific terminology. But once the mapping is built, it becomes a durable asset that benefits all future documents from that AMC. The terminology mapping should be stored as a structured data file that can be updated without changing any code, making AMC onboarding a configuration task rather than a development task.

---

## 7. Layer Three — Context-Aware Validation and Cross-Document Reasoning

Extraction tells you what values are in the document. Validation tells you whether those values are correct, complete, consistent, and meaningful. The key word in the layer name is "context-aware." A context-aware validation system does not check each field in isolation. It understands the relationships between fields and uses those relationships to detect errors that no single-field check could catch.

### The Difference Between Format Validation and Semantic Validation

Format validation checks that a value is in the expected format. A date should look like a date. A dollar amount should look like a dollar amount. A UAD condition code should be one of the six allowed codes. Format validation is straightforward and your current rule engine likely already handles most of it.

Semantic validation checks that a value makes sense in context. An appraised value that is two hundred percent of the contract price is suspicious even if it is a correctly formatted dollar amount. A comparable sale that occurred three years before the effective date of the appraisal is suspicious even if the date is formatted correctly. A property with a gross living area that is twice the average for comparable sales in the same neighborhood is suspicious even if the area measurement is a valid number.

Semantic validation requires understanding not just the value of a field but its meaning and its relationship to other fields. This is what separates intelligent validation from simple rule checking.

### Cross-Document Consistency Checking

Many QC checks require comparing information across multiple documents. The borrower name in the engagement letter should match the borrower name in the appraisal report. The contract price in the sales contract should be consistent with the contract price referenced in the appraisal report. The property address should be the same across all three documents.

Cross-document consistency checking is the process of extracting the same conceptual field from multiple documents and verifying that the values agree. This sounds simple, but it has important nuances.

First, values may be expressed differently across documents. "123 Main Street" in one document and "123 Main St." in another document refer to the same address. Your consistency checker must handle these superficial differences without flagging them as errors.

Second, values may legitimately differ for good reasons. The appraised value and the contract price are intentionally different fields even though both are dollar amounts. Your consistency checker must understand which fields should match and which fields are allowed to differ.

Third, when values do not match, the system should not simply flag an error. It should express a level of confidence in each value and indicate which document is more likely to be authoritative for that particular field. An engagement letter is more authoritative for the AMC's name than an appraisal report is. A sales contract is more authoritative for the contract price than an appraisal report is.

### Temporal and Sequential Reasoning

Appraisal documents contain many temporal relationships that must be validated. The effective date of the appraisal must be before the date the appraisal was signed. Comparable sales must have occurred within acceptable time windows relative to the effective date. The engagement date must precede the effective date.

These temporal relationships are not simple field format checks. They require the system to understand the relative order of events and to check whether the ordering is valid according to appraisal guidelines. Your rule engine already handles some of these, but as you move toward semantic validation, these checks become richer and more nuanced.

For example, a context-aware temporal validator would not just check whether a comparable sale occurred within twelve months. It would also consider whether the local market was active enough to make older sales acceptable, whether the appraisal guidelines in effect for that file allow an exception, and whether the appraiser provided adequate explanation for using the older sale.

### Confidence-Driven Escalation

One of the most important design decisions in your validation layer is how it handles uncertainty. A binary pass/fail system forces every field into one of two categories. But real-world document extraction produces a spectrum of confidence levels. Some fields are extracted with very high confidence and do not need human review. Some fields are extracted with low confidence and should always be reviewed. And many fields fall in between.

Confidence-driven escalation is the mechanism by which your system decides what to do with each extracted value based on its confidence level. You define confidence thresholds for each field, and the system routes documents accordingly. A field with confidence above the high threshold is auto-accepted. A field with confidence below the low threshold is flagged for mandatory review. A field in between is flagged for optional review, with a clear explanation of why confidence is reduced.

This mechanism makes your system dramatically more useful in practice. Human reviewers do not need to check every extracted value — only the ones that the system is uncertain about. This focuses human attention where it is most needed and allows the platform to scale to higher document volumes without proportionally increasing review workload.

---

## 8. Layer Four — Format Registry and AMC Profile Management

This layer is what allows your system to become progressively smarter with each new AMC and each new document format it encounters. The format registry is a database of everything your system has learned about each document format it has processed.

### What the Format Registry Stores

For each AMC or document template that your system has processed, the format registry stores a profile that includes the following information.

The document fingerprint is a set of structural characteristics that identify this AMC's template. It includes keyword signatures, approximate page count, typical section ordering, table structures, and any other distinctive features that allow the system to recognize this template when it appears again.

The field location model is a learned mapping of where each field typically appears in this AMC's template. Even though your system is moving away from positional extraction, field location information is still useful as a tiebreaker when two candidate values have similar confidence scores. The value that appears in the expected location for this AMC gets a slight confidence boost.

The terminology mapping is the AMC-specific vocabulary dictionary described earlier. It maps this AMC's terms and abbreviations to their canonical equivalents.

The extraction history is a summary of how accurately your system has extracted each field from this AMC's documents in the past, including which fields have been corrected by human reviewers and how frequently.

The validation profile contains any AMC-specific validation rules that supplement the standard rule set. Some AMCs have specific requirements that are not part of the general industry standard.

### Progressive Profile Building

When your system encounters a document from an AMC for the first time, it creates a new profile with minimal information. It classifies the document using general classification methods, applies the full extraction pipeline with no AMC-specific prior knowledge, and records all extraction results and confidence scores.

As more documents from the same AMC are processed, the profile becomes richer. The system learns which extraction approaches work best for this AMC's templates, which fields appear in which locations, which terminology is used, and what validation patterns are typical. Each new document is processed using the accumulated profile knowledge, and the results are used to further refine the profile.

After processing enough documents from an AMC — the exact number depends on the consistency of their templates, but somewhere between ten and fifty is typical — the profile reaches a mature state where the system can extract documents from that AMC with high confidence and low review rates.

### Profile Versioning

AMCs update their document templates periodically. When a template update occurs, the field location model and other structural characteristics in the profile may no longer be accurate. The system must be able to detect when it is seeing a new version of a known template and create a new profile version rather than applying the old profile's assumptions.

Template change detection works by comparing a new document's structural fingerprint to the known fingerprints of all existing profile versions. If the fingerprint matches a known version, the corresponding profile is used. If the fingerprint does not match any known version, a new profile version is created and the document is processed with reduced AMC-specific prior knowledge.

Profile versioning ensures that your system does not apply outdated assumptions to new document formats. It also maintains a historical record of how each AMC's templates have evolved over time, which is valuable for understanding trends and anticipating future changes.

---

## 9. Layer Five — Continuous Learning and Self-Correction

This is the layer that transforms your system from a static extractor into a learning system. Every correction made by a human reviewer is a training signal. The learning layer captures these signals and uses them to improve extraction accuracy over time.

### The Reviewer Feedback Interface

For the learning loop to work, reviewers must be able to provide feedback easily and consistently. This means your reviewer interface must be designed specifically to capture correction data, not just to display extracted results.

When a reviewer changes an extracted value, the system should record the original extracted value, the corrected value, the field name, the document identifier, the AMC, the document type, and the reviewer's identity. It should also record the reason for the correction if the reviewer provides one. And it should record all contextual information about the extraction — which extraction tier produced the original value, what the confidence score was, and what the surrounding text looked like.

This detailed correction record is what makes the learning layer possible. Without it, you know that a correction was made but you do not know why or how to prevent the same error in the future. With it, you can identify patterns — certain fields in certain document types from certain AMCs consistently need correction, indicating a systematic extraction error that should be addressed.

### Learning from Corrections

Corrections can improve your system in several ways depending on which extraction tier produced the incorrect value.

If a rule-based extraction pattern produced the incorrect value, the correction indicates that the pattern is too broad, too narrow, or based on incorrect assumptions. The correction data can be used to identify which pattern fired and to update it so that it no longer makes the same error.

If the LLM produced the incorrect value, the correction can be used to improve the LLM's prompting strategy. Often, LLM extraction errors happen because the prompt does not give the model sufficient context to distinguish between two similar concepts. Adding a clarifying instruction to the prompt can eliminate an entire category of errors.

If a semantic similarity match produced the incorrect value, the correction indicates that the embedding representation of either the candidate text or the target field concept needs to be improved. This is more complex to fix but can be addressed by fine-tuning the embedding model on domain-specific data.

If all tiers produced the incorrect value, the correction indicates a more fundamental gap — either a new type of document structure that the system has not encountered before, or a field whose concept is not well-represented in any of the extraction tiers. These cases require deeper investigation and potentially new training data.

### Automated Retraining

As correction data accumulates, it should be used to periodically retrain the extraction models. This retraining is not a manual process. It should be automated and should run on a schedule — weekly or monthly depending on the volume of corrections.

The automated retraining pipeline takes the accumulated correction data, transforms it into training examples, runs the training process, evaluates the retrained model against a held-out test set, and deploys the new model if it performs better than the current model. If it performs worse — which can happen if the training data contains errors or is not representative — the retrained model is rejected and the current model is retained.

The evaluation step is critical. You must have a test set of documents with known correct extractions that you can use to measure model performance objectively. Without a test set, you cannot know whether retraining is actually improving things or accidentally making them worse.

---

## 10. How Enterprise Systems Solve This Problem

Understanding how large enterprise document processing platforms approach this problem will help you calibrate your own expectations and design decisions.

### What Major Platforms Do

Large enterprise document intelligence platforms such as those used in banking, insurance, healthcare, and legal industries all share common architectural patterns that are worth understanding.

They always separate document classification from field extraction. They never try to extract fields without first knowing what type of document they are processing. This separation allows them to apply document-type-specific extraction strategies while maintaining a common extraction framework.

They always use confidence scoring at every step. No single extraction attempt is treated as definitively correct. Confidence scores flow through the entire pipeline and are used to make routing decisions, trigger human review, and measure system performance over time.

They always maintain document-type-specific schemas. The set of fields that can be extracted, the rules that govern those fields, and the validation logic that checks them are all defined per document type. There is no single universal field list that applies to all documents.

They always combine multiple extraction approaches. No single extraction technique — whether rule-based, machine learning, or LLM-based — performs well on all document types and all field types. The winning approach is always an ensemble that combines multiple techniques and merges their outputs intelligently.

They always build feedback loops. Human reviewers are not just a safety net. They are an integral part of the system's improvement mechanism. Every review is a training opportunity, and the system is designed to capture and learn from every correction.

They always version their extraction models. When a new model version is deployed, the old version is retained. If the new version causes problems, the system can roll back to the old version. This prevents a bad model update from disrupting production.

### Lessons for Your Platform

The most important lesson from enterprise platforms is that you do not need to solve the entire problem at once. Enterprise platforms were built incrementally over years. They started with a narrow set of document types and a relatively simple extraction approach, then expanded and improved over time.

What you need to get right from the beginning is the architecture — the separation of concerns, the confidence scoring framework, the feedback loop, the format registry, and the field schema. If these architectural foundations are in place, you can add more sophisticated extraction techniques over time without rebuilding the system from scratch.

The second most important lesson is that data is more valuable than any particular algorithm. The platform that has the most correctly labeled training data wins, not the platform that has the most sophisticated model. Building and curating your training data is a strategic priority, not a secondary concern.

---

## 11. The Right Technology Stack for Each Layer

This section describes the technology choices for each layer, explained in terms of what each technology does and why it is appropriate — not in terms of code.

### For Document Classification

The right approach initially is a lightweight classifier trained on document structural features combined with keyword signatures. This does not require a GPU and can run quickly enough to classify documents in near real time. As your document corpus grows, you can upgrade to a fine-tuned BERT-class model that achieves higher accuracy on edge cases.

Tesseract with OpenCV preprocessing handles the text extraction that feeds document classification. Your existing investment in this pipeline is correct and should be retained.

### For Semantic Field Extraction

The local Ollama LLM running llama3:8b or a similar model is the right choice for the Tier One extraction role. The key to making this work well is prompt engineering — the instructions you give the model matter enormously. A well-crafted prompt that explains the appraisal domain, gives examples of the kinds of fields being extracted, and specifies the exact output format can dramatically improve extraction quality without changing the model itself.

The sentence-transformers library provides the embedding models needed for Tier Two semantic similarity matching. The all-MiniLM-L6-v2 model you already have is a good starting point. For better domain accuracy, you can fine-tune this model on a dataset of appraisal field labels and their synonyms.

Your existing extraction code, upgraded with synonym expansion and fuzzy matching, handles Tier Three. The key upgrade is replacing exact string matching with approximate matching that tolerates minor variations in spelling, capitalization, and punctuation.

### For Validation

Your existing Java Spring Boot rule engine is the right foundation for validation. The key upgrade is adding confidence-driven escalation logic and cross-document consistency checking. Neither of these requires changing the fundamental architecture of the rule engine — they are additions to the existing framework.

For semantic validation that goes beyond simple rule checking, the local LLM can again be useful. You can send it a summary of extracted fields from a document and ask it to identify potential inconsistencies or anomalies that might not be caught by rules.

### For the Format Registry and Profile Management

A structured database is the right choice for the format registry. PostgreSQL, which you already use, is entirely adequate. The profile data is structured and relational — it relates AMC identifiers to template fingerprints, field location models, and terminology mappings. All of this fits naturally in a relational schema.

The key is designing the schema carefully to support efficient lookup by document fingerprint and to support versioning of profiles over time.

### For Continuous Learning

The learning pipeline is a batch process that runs periodically, not a real-time system. It reads correction records from the database, transforms them into training examples, runs model training, evaluates the trained model, and updates the model store. Celery, which you already have, is the right mechanism for orchestrating this batch process.

Model storage needs to be versioned. Each trained model should be stored with its version number, training date, training data summary, and evaluation metrics. This record allows you to trace any extraction result back to the model version that produced it, which is important for audit purposes.

---

## 12. Transition Roadmap — From Regex to Intelligence

Transitioning from regex-based extraction to intelligent extraction should not happen all at once. A big-bang replacement of your extraction layer carries enormous risk. The right approach is a phased transition that gradually introduces more intelligent extraction while maintaining the reliability of your existing system.

### Phase Zero — Foundation (Before New Hardware)

Before doing anything else, establish the foundations that all future work depends on. These foundations are architectural, not algorithmic. They do not require new hardware or new models.

The first foundation is a comprehensive field schema. Document every field that your system currently extracts from every document type. Give each field a canonical name, a data type, allowed values or ranges, and a set of known synonymous labels. This schema does not change any existing code. It is a documentation artifact that will guide all future development.

The second foundation is a structured extraction result format. Every extraction attempt should produce a result that includes the field name, the extracted value, a confidence score, the extraction method that was used, and the source text from which the value was extracted. If your current extraction code does not produce this format, modifying it to do so is the first code change to make. This change has no risk because it only adds information to existing outputs — it does not change any logic.

The third foundation is a correction capture mechanism. Add the ability for reviewers to record corrections to extracted values. This does not need to be sophisticated at first — even a simple log of field name, original value, corrected value, and document identifier is enough to start building the training data corpus.

The fourth foundation is a format registry skeleton. Create the database tables that will store AMC profiles. Start populating them manually with information about the AMC formats you already know. This prepares the infrastructure for automated profile building later.

### Phase One — Synonym Expansion and Fuzzy Matching (Immediately After Hardware Arrives)

This phase makes your existing extraction significantly more robust without introducing new technology. The approach is to take every pattern in your existing extraction code and expand it with synonyms, case variations, and approximate matching.

For each field label pattern, create a list of all known synonymous labels from your field schema. For each pattern, replace exact string matching with approximate matching that tolerates minor spelling variations and punctuation differences.

This phase does not require the GPU, does not require the LLM, and can be completed quickly. It will immediately improve extraction accuracy for documents that use slightly different labels than the ones your current patterns expect.

The measurable outcome of this phase is a reduction in the frequency of empty fields in extracted results — fields that exist in the document but were not found because the label was slightly different from what the pattern expected.

### Phase Two — LLM-Assisted Extraction Layer (One to Two Months After Hardware)

With the new hardware in place, you can add the LLM as a Tier One extraction layer. The approach is to run the LLM in parallel with your existing extraction code on every document. Compare the LLM's extractions to your existing extractions for each field. When they agree, increase the confidence score. When they disagree, flag the field for review.

In this phase, the LLM does not replace your existing extraction. It augments it. The merged result uses the existing extraction as the primary value and the LLM result as a validation check. This gives you the benefits of LLM-based extraction — better handling of novel labels and complex contexts — while maintaining the reliability of your existing patterns for the fields they handle correctly.

After running in this dual mode for several weeks, you will have data on which fields the LLM handles better than your patterns and which fields your patterns handle better than the LLM. Use this data to decide which extraction tier to trust for each field type.

### Phase Three — Semantic Similarity Matching (Two to Four Months After Hardware)

Add the semantic similarity matching tier using sentence-transformers. This tier is particularly valuable for fields where neither your existing patterns nor the LLM is consistently reliable — typically fields with highly variable labels or fields that appear in unexpected locations.

To implement this tier, you need embedding vectors for each field concept in your schema. These vectors are computed once from a set of representative label examples for each field and stored in a vector database. At extraction time, each candidate text segment is embedded and compared to all field concept vectors. The closest match above a similarity threshold is treated as a candidate extraction.

The combination of all three tiers — pattern matching, LLM extraction, and semantic similarity — provides much better coverage and accuracy than any single tier alone.

### Phase Four — Active Profile Building and Format Registry (Four to Six Months)

With extraction working well and correction data accumulating, you can begin actively building AMC profiles. Build tooling that automatically processes the correction data to identify systematic extraction errors for specific AMCs and update the AMC profile accordingly.

Implement the document fingerprinting system and use it to classify incoming documents by AMC and template version. Apply the AMC-specific profile knowledge — field location priors, terminology mappings — as an additional input to the extraction confidence calculation.

At this point, your system is beginning to learn from experience. Extraction quality should be measurably improving month over month.

### Phase Five — Automated Retraining and Full Learning Loop (Six to Twelve Months)

Implement the automated retraining pipeline. This connects the correction data that has been accumulating through all previous phases into a systematic process for improving extraction models. The retraining pipeline runs on a schedule, evaluates its outputs against a test set, and deploys improvements automatically.

At this point, your system is self-improving. Human reviewer time is focused on genuinely difficult cases rather than routine corrections. The extraction accuracy for known AMC formats approaches very high levels, and even new formats are handled reasonably well from the first document.

---

## 13. Supporting Multiple AMC Formats Reliably

Supporting multiple AMC formats is not primarily a technology challenge. It is primarily an operational challenge. The technology can handle multiple formats if it is designed correctly. The harder part is the process by which you onboard new AMC formats, validate that extraction works correctly, and maintain quality as AMC templates evolve.

### The AMC Onboarding Process

Every time you start receiving documents from a new AMC, you should follow a structured onboarding process. This process does not need to be elaborate, but it should be consistent.

The first step is to collect a representative sample of documents from the new AMC. Ten to twenty documents covering the full range of document types you expect to receive from them is typically sufficient for initial onboarding. If possible, get documents from different time periods to capture any template variations.

The second step is to run these sample documents through your extraction pipeline and review the results carefully. Identify every field where extraction is incorrect or missing. Document these as known gaps for this AMC's format.

The third step is to update your field schema and terminology mapping to address the identified gaps. Add the AMC's specific label variants as synonyms for the appropriate canonical fields. If the AMC uses field structures or layouts that your system has not encountered before, document these as known format characteristics.

The fourth step is to create an initial AMC profile in the format registry with the information gathered in steps two and three. Set confidence thresholds for this AMC's documents to be somewhat more conservative than your default thresholds, reflecting the limited experience your system has with this AMC's formats.

The fifth step is to process a second batch of documents using the updated configuration and measure whether extraction quality has improved. Iterate until extraction quality reaches an acceptable level for the most important fields.

The sixth step is to document the known limitations for this AMC — fields that are still not extracting reliably, edge cases that require human review, and any special validation considerations.

### Maintaining Quality as AMC Templates Evolve

AMCs update their templates for various reasons — regulatory changes, software upgrades, rebranding, or simple redesign. When a template update causes your extraction to regress, you need a process for detecting and addressing the regression quickly.

Template change detection is the automated part of this process. When a document's fingerprint does not match any known version of the AMC's template, the system flags it as a potentially new template version. This flag triggers a notification to the operations team, who review the document manually and update the AMC profile if a template change is confirmed.

Regression monitoring is the continuous part of this process. Track extraction confidence scores and human correction rates for each AMC over time. A sudden increase in correction rates or decrease in confidence scores for a particular AMC is a reliable signal that something has changed — either a new template version or a new document type from that AMC.

---

## 14. The Confidence-Scoring System

Confidence scoring is the mechanism that holds the entire system together. Every extraction result has a confidence score. Every validation check has a confidence score. Every routing decision is made based on confidence scores. Getting confidence scoring right is one of the most important design decisions you will make.

### What Confidence Scores Express

A confidence score expresses the system's degree of certainty that a particular extraction result is correct. It is not a binary right-or-wrong judgment. It is a probability estimate — the probability that the extracted value matches the true value in the source document.

Confidence scores should be calibrated. A score of 90% should mean that approximately 90% of fields with that score are actually correct. If your system gives high confidence scores to fields that are frequently wrong, the scores are not calibrated and cannot be used to make reliable routing decisions.

Calibration is achieved through measurement and adjustment. After accumulating a sufficient corpus of extracted fields with known correct answers, you can measure the actual accuracy rate at each confidence level and adjust the scoring to match observed reality.

### What Factors Affect Confidence

Many factors contribute to the confidence score for an extracted field. Understanding these factors helps you design a confidence scoring system that accurately reflects extraction uncertainty.

OCR quality is a major factor. A field extracted from clean digital text has inherently higher confidence than the same field extracted from noisy OCR output. OCR quality metrics such as character-level confidence scores from Tesseract can be incorporated into the field confidence score.

Label match quality affects confidence. A field extracted from an exact label match — "Borrower Name:" followed by the value — has higher confidence than a field extracted from a fuzzy label match or inferred from context.

Tier agreement increases confidence. When multiple extraction tiers independently produce the same value for a field, confidence in that value is high. When tiers disagree, confidence is low.

Value plausibility affects confidence. A dollar value that falls within the expected range for the document's geographic market has higher confidence than one that is far outside the typical range. A date that falls within the expected time window for the appraisal process has higher confidence than one that is years in the past or future.

AMC profile knowledge increases confidence. For documents from AMCs with mature profiles, the system has prior knowledge about where fields appear and what formats they use. When the extracted value matches these expectations, confidence is higher.

### Confidence Thresholds and Routing

Your routing logic should use separate confidence thresholds for different fields based on their importance. The appraised value is a critical field — errors in it have significant consequences. Its auto-acceptance threshold should be high, meaning the system is more conservative about auto-accepting appraised values than other fields. A non-critical administrative field like an AMC's internal file number can have a lower auto-acceptance threshold because an error in it has limited downstream impact.

Thresholds should be configurable per field and per AMC, not hardcoded. This allows you to adjust routing behavior based on experience without modifying code.

---

## 15. Building the Feedback Loop

The feedback loop is what transforms your system from a static tool into an improving system. Building it correctly requires thinking about it as a system-wide design concern, not as a feature of any individual component.

### What Must Be Captured

For the feedback loop to work, every correction must be captured with sufficient context to be actionable. The minimum required context for each correction is the field name, the document identifier, the document type, the AMC identifier, the original extracted value, the corrected value, the extraction tier that produced the original value, the confidence score that was assigned to the original value, and the source text from which the original value was extracted.

Optional but highly valuable context includes the reviewer's explanation for the correction, the time taken by the reviewer to make the correction, and whether the reviewer considered the extraction close or completely wrong.

### How Corrections Are Used

Corrections serve three functions in the feedback loop.

The first function is immediate improvement through terminology and profile updates. When a correction indicates that a particular label variant is being missed, that variant is added to the AMC's terminology mapping and the extraction rules immediately. This is a fast path that does not require any model retraining.

The second function is batch improvement through model fine-tuning. When enough corrections of a particular type accumulate, they are used to update the relevant extraction model. The exact threshold for triggering a fine-tuning run depends on the model and the volume of corrections, but as a rule of thumb, significant changes to extraction patterns require dozens to hundreds of examples to be reliable.

The third function is quality measurement. The overall rate of corrections is a direct measure of extraction quality. Tracking this rate over time, broken down by document type, AMC, and field, gives you a continuous measurement of whether your system is improving, regressing, or staying stable.

### Preventing Feedback Poisoning

A feedback loop can be corrupted if the training signals it receives are incorrect. This happens when reviewers make mistakes — applying an incorrect value as a correction — or when corrections reflect a policy disagreement rather than an extraction error. Applying these incorrect corrections as training signals teaches the system to make the same mistake intentionally.

Preventing feedback poisoning requires two things. First, quality control on corrections — occasional review of a sample of corrections by a second reviewer to catch systematic mistakes. Second, outlier detection — automated identification of corrections that are unusual compared to similar documents, which triggers a review before the correction is used as a training signal.

---

## 16. Data Quality and Training Data Strategy

The performance of your intelligent extraction system will ultimately be limited by the quality and quantity of your training data. This section outlines the strategy for building and maintaining a high-quality training data corpus.

### What Training Data Looks Like

Training data for document extraction consists of documents paired with their correct field extractions. Each document in the training set has a corresponding record that specifies the correct value for every extractable field. These correct values are the ground truth against which your models are trained and evaluated.

Building training data is labor-intensive. You cannot fully automate it because automation requires the very extraction capability you are trying to train. The initial training data must be produced by human reviewers who manually verify every extracted field for a set of documents.

### Sources of Training Data

You have three primary sources of training data.

The first is historical documents that have already been processed by human reviewers. Any document where a reviewer verified the extraction results — even if no corrections were made — is a potential training example. The challenge is that this data may not have been captured in a format suitable for training. Retrofitting your historical data into training format requires effort but is worth doing because it is the fastest way to build a large corpus.

The second is the ongoing correction stream. Every correction made by a reviewer adds to your training data corpus. This source grows continuously as your platform processes more documents and builds a richer corpus over time.

The third is synthetic data generation. You can create synthetic training examples by generating variations of real documents with slightly different formatting, labeling, and layout. This is particularly useful for fields and document types where you have limited real examples. Synthetic data should be used carefully — it supplements real data but does not replace it.

### Training Data Annotation Standards

Consistent annotation standards are essential for high-quality training data. If different reviewers annotate the same field differently, the training data contains contradictions that confuse the model. You need clear written guidelines that specify how to annotate every field type, how to handle ambiguous cases, and how to record missing values.

Annotation standards should be tested through inter-annotator agreement studies — having two reviewers independently annotate the same document and measuring how often they agree. High agreement means the standards are clear and consistent. Low agreement means the standards need clarification.

### Data Governance

Training data is a valuable and sensitive asset. It contains information extracted from real appraisal documents, which may include personally identifiable information and confidential financial data. Your data governance practices must address how training data is stored, who can access it, how long it is retained, and how it is protected.

This is not only an ethical requirement. It is also a regulatory requirement for a platform that handles financial documents. Understanding and complying with applicable data protection requirements is essential before building any system that stores or processes document content.

---

## 17. Infrastructure Considerations Given Your Hardware

Your incoming hardware — Ryzen 5 5600 with six cores, RTX 3060 12GB, and 32GB RAM — is sufficient to run the full extraction pipeline described in this document. This section explains how to allocate resources across the pipeline components to get the best performance from the available hardware.

### GPU Resource Allocation

The GPU is the most constrained resource because multiple components want to use it simultaneously. Ollama holding the LLM in VRAM requires approximately 4.5GB. OpenCV CUDA processing for active OCR jobs requires approximately 1GB. Sentence-transformers embedding generation requires approximately 0.5GB. The total active GPU memory requirement is approximately 6GB, well within the 12GB capacity.

However, these three components should not all run simultaneously in an uncontrolled way. You need a GPU resource scheduler — a component that knows what is currently using the GPU and coordinates access to prevent out-of-memory errors. The Celery task queue is the natural place to implement this coordination, by controlling the concurrency of tasks that use the GPU.

### CPU Resource Allocation

With six cores and twelve threads, you can run the following concurrently without significant contention. The FastAPI server handling HTTP requests from reviewers needs one to two threads at typical load. The Java Spring Boot backend needs one to two cores for its JVM. PostgreSQL needs one core for query execution. Two to three Celery workers can run OCR jobs in parallel, each consuming a core for Tesseract processing. One Celery worker handles the LLM inference coordination.

This allocation leaves one to two cores available as headroom for burst workloads and system processes. As document volumes increase, adding more physical CPU cores is the first scaling step.

### Memory Allocation Strategy

With 32GB RAM, your allocation should be roughly as follows. The operating system and system processes need approximately 2GB. The Java JVM for Spring Boot needs approximately 4GB. PostgreSQL needs approximately 4GB for its buffer pool. The Python OCR service processes need approximately 4GB each, and with two workers running simultaneously that is 8GB. Docker container overhead and Redis need approximately 2GB. Training pipeline batch operations need up to 6GB when running. This leaves approximately 6GB as headroom, which is adequate for avoiding out-of-memory conditions during normal operations.

If you run training pipeline jobs and OCR jobs simultaneously, memory pressure increases significantly. Schedule training jobs during off-peak hours when fewer OCR workers are active.

### Scaling Beyond Single Machine

The architecture described in this document is designed to scale horizontally. When document volumes exceed what a single machine can handle, you can add additional processing nodes. The Celery task queue allows OCR and extraction work to be distributed across multiple workers on multiple machines. The GPU-intensive work — LLM inference — can be isolated on a dedicated GPU server while CPU-intensive work runs on additional cheaper machines.

This horizontal scaling path is why investing in the correct architecture from the beginning is important. A monolithic system that runs all processing in a single process cannot scale horizontally. A queue-based system with separated concerns can.

---

## 18. What to Build First, Second, and Third

Given everything described above, this section provides a clear prioritized sequence for what to build at each stage.

### Build First — The Foundation

Before implementing any new extraction intelligence, ensure the following foundations are in place. A comprehensive and documented field schema covering all document types. A structured extraction result format that includes confidence scores and source text references. A correction capture mechanism that records reviewer changes with full context. A format registry with initial AMC profiles for the AMCs you currently process. A test set of documents with known correct extractions that can be used to measure system performance.

These foundations take time to build but they make everything else possible. Without them, you cannot measure whether improvements are actually helping, and you cannot learn from corrections in any systematic way.

### Build Second — Enhanced Extraction

With the foundations in place, enhance the extraction layer. Implement synonym expansion and fuzzy matching for your existing extraction patterns. Add the LLM as a Tier One extraction layer running in parallel with your existing extraction. Implement confidence score merging from multiple extraction tiers. Build the AMC terminology mapping for your current AMC partners.

This phase will produce measurable improvement in extraction accuracy for novel document formats while maintaining the reliability of your existing system for the formats it already handles well.

### Build Third — Learning and Adaptation

With enhanced extraction running and correction data accumulating, build the learning layer. Implement automated profile updating based on correction patterns. Build the retraining pipeline for extraction models. Implement template change detection and notification. Build the regression monitoring dashboard.

This phase transforms your system from one that was improved by human developers into one that improves itself through experience. It is the phase that makes your extraction system truly future-proof.

---

## 19. Common Mistakes to Avoid

Based on how enterprise document extraction systems typically fail, here are the most common mistakes to avoid.

**Do not try to solve everything with the LLM.** Local LLMs are powerful but they have limitations. They can hallucinate values that do not exist in the document. They can be confused by unusual document structures. They are slow compared to rule-based extraction. The right role for the LLM is as one tier in an ensemble, not as the sole extraction mechanism.

**Do not skip confidence scoring.** Building an extraction system without confidence scores may seem simpler, but it creates a binary system that cannot gracefully handle uncertainty. Every significant extraction decision should be expressed as a confidence level, not a binary answer.

**Do not build a monolithic extraction function.** If all your extraction logic is in a single function or a single file, it becomes impossible to improve individual components without risking the whole system. Separate each extraction strategy into its own module with a clean interface.

**Do not neglect the test set.** Building a good test set requires effort and seems like overhead. But without it, you cannot tell whether your system is improving or degrading as you make changes. The test set is your safety net.

**Do not assume that high LLM confidence equals high extraction accuracy.** LLMs can express high confidence in wrong answers. Their self-reported confidence does not correlate well with actual accuracy for specific extraction tasks. Calibrate your confidence scoring based on actual measured accuracy, not on the LLM's self-assessment.

**Do not onboard new AMCs without a structured process.** Ad-hoc AMC onboarding leads to inconsistent quality and undocumented workarounds. Every new AMC should go through the same structured onboarding process that creates a documented profile and establishes measurable quality baselines.

**Do not let correction data accumulate without using it.** If corrections are being captured but not fed back into the system, you are collecting data but not learning from it. Ensure the learning pipeline runs regularly and that improvements from corrections are systematically applied.

**Do not conflate extraction errors with validation errors.** When a QC check fails, it may be because the extracted value is wrong or because the actual document contains a genuine QC issue. Conflating these two cases leads to incorrect assessment of extraction quality. Your system must be able to distinguish between "we extracted the wrong value" and "we extracted the correct value and it reveals a problem in the document."

---

## 20. Final Architecture Summary

The architecture described in this document has a clear structure that can be summarized in a way that is easy to remember and communicate to new team members.

Every document that enters your platform passes through five layers. The first layer, adaptive ingestion, turns raw PDF files into clean structured text using OCR, preprocessing, and normalization. The second layer, semantic extraction, turns clean text into structured field-value pairs using a three-tier ensemble of rule-based, LLM-based, and similarity-based extractors. The third layer, context-aware validation, checks extracted fields against business rules, cross-document consistency requirements, and semantic plausibility constraints, producing a confidence-weighted QC report. The fourth layer, format registry, stores and applies everything the system has learned about each AMC's document formats, making extraction for known formats progressively more accurate. The fifth layer, continuous learning, captures human reviewer corrections and uses them to systematically improve all previous layers over time.

The entire pipeline is governed by three principles. Confidence scores flow through every step and drive routing decisions. Human feedback is treated as a first-class input that continuously improves system quality. Document formats are treated as variable presentation choices rather than fixed assumptions, and the system is designed to work correctly across the full range of format variation it will encounter in the real world.

This architecture does not require solving every problem at once. It provides a stable foundation that can be built incrementally, with each phase delivering immediate value while preparing for the next phase. Starting from your current regex-based system, you can progress through synonym expansion, LLM augmentation, semantic similarity matching, active profile learning, and automated retraining — each phase improving on the last without requiring you to discard what you have already built.

The result is a document extraction platform that does not break when formats change, does not need to be rewritten for every new AMC, and becomes more accurate month after month through systematic learning from experience. This is exactly the long-term reliability and adaptability you are aiming for.

---

*Document Version 1.0 — EagleX Info Solution PVT LTD*  
*Architecture guidance prepared for the Apprisal platform extraction layer transition.*  
*This document should be treated as a living reference and updated as the platform evolves.*
