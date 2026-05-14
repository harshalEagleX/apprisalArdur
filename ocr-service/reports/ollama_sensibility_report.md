# Ollama Sensibility Analysis — Batch QC Report
Generated: 2026-05-14 18:58 UTC  |  Model: llava:13b  |  Provider: Ollama (local)

## Overview

| Batch | Label | Total Time | Pages | Rules Run | PASS | FAIL | VERIFY | Ollama Doc Extract |
|---|---|---|---|---|---|---|---|---|
| MSL | MSL (reference — used to build regex/rules) | 0s | 27 | 137 | 63 | 3 | 47 | addr: `—` |
| 2321525470 | #2321525470 (random/unknown — cross-format validation) | 0s | 30 | 137 | 54 | 7 | 57 | addr: `—` |

---

## Ollama Full-Document Extraction

Ollama's independent read of each document (no regex, no rules).

### MSL — MSL (reference — used to build regex/rules)

- **Property Address:** not extracted
- **Borrower:** not extracted
- **Contract Price:** not extracted
- **Appraised Value:** not extracted
- **Market Conditions Quality:** unknown
- **Form Type:** unknown
- **Overall Issues:** none identified
- **Commentary Issues:** none identified
- **Ollama Processing Time:** 46396 ms

### 2321525470 — #2321525470 (random/unknown — cross-format validation)

- **Property Address:** not extracted
- **Borrower:** not extracted
- **Contract Price:** not extracted
- **Appraised Value:** not extracted
- **Market Conditions Quality:** unknown
- **Form Type:** unknown
- **Overall Issues:** none identified
- **Commentary Issues:** none identified
- **Ollama Processing Time:** 46037 ms

---

## Per-Rule Comparison: Deterministic vs Ollama

Legend — Ollama Verdict:  ✅ AGREE  |  ❌ DISAGREE  |  ❓ UNCERTAIN  |  ⏭ SKIPPED

| Rule | MSL Det Status | MSL Ollama | MSL Finding | #2321525470 Det Status | #2321525470 Ollama | #2321525470 Finding | Agree? |
|---|---|---|---|---|---|---|---|
| `S-1` | `pass` | ⏭ | Ollama did not respond. | `fail` | ⏭ | Ollama did not respond. | ⚠️ |
| `S-2` | `pass` | ⏭ | Ollama did not respond. | `extraction_failed` | ❓ |  | ⚠️ |
| `S-3` | `pass` | ⏭ | Ollama did not respond. | `pass` | ⏭ | Ollama did not respond. | ✅ |
| `S-4` | `pass` | ⏭ | Ollama did not respond. | `pass` | ⏭ | Ollama did not respond. | ✅ |
| `S-5` | `pass` | ⏭ | Ollama did not respond. | `fail` | ⏭ | Ollama did not respond. | ⚠️ |
| `S-6` | `pass` | ⏭ | Ollama did not respond. | `pass` | ⏭ | Ollama did not respond. | ✅ |
| `C-1` | `pass` | ⏭ | Ollama did not respond. | `review` | ⏭ | Ollama did not respond. | ⚠️ |
| `C-2` | `extraction_failed` | ⏭ | Ollama did not respond. | `extraction_failed` | ⏭ | Ollama did not respond. | ✅ |
| `C-3` | `review` | ⏭ | Ollama did not respond. | `review` | ⏭ | Ollama did not respond. | ✅ |
| `S-7` | `pass` | ⏭ | Ollama did not respond. | `pass` | ⏭ | Ollama did not respond. | ✅ |
| `S-8` | `ocr_low_confidence` | ⏭ | Ollama did not respond. | `extraction_failed` | ❓ |  | ⚠️ |
| `S-9` | `ocr_low_confidence` | ⏭ | Ollama did not respond. | `extraction_failed` | ⏭ | Ollama did not respond. | ⚠️ |
| `S-10` | `extraction_failed` | ❓ |  | `extraction_failed` | ⏭ | Ollama did not respond. | ✅ |
| `S-11` | `pass` | ⏭ | Ollama did not respond. | `pass` | ⏭ | Ollama did not respond. | ✅ |
| `S-12` | `fail` | ⏭ | Ollama did not respond. | `fail` | ⏭ | Ollama did not respond. | ✅ |
| `C-4` | `pass` | ⏭ | Ollama did not respond. | `pass` | ⏭ | Ollama did not respond. | ✅ |
| `C-5` | `pass` | ⏭ | Ollama did not respond. | `fail` | ⏭ | Ollama did not respond. | ⚠️ |
| `N-1` | `review` | ⏭ | Ollama did not respond. | `review` | ⏭ | Ollama did not respond. | ✅ |
| `N-2` | `review` | ⏭ | Ollama did not respond. | `review` | ⏭ | Ollama did not respond. | ✅ |
| `N-3` | `review` | ⏭ | Ollama did not respond. | `review` | ⏭ | Ollama did not respond. | ✅ |
| `N-4` | `review` | ⏭ | Ollama did not respond. | `review` | ⏭ | Ollama did not respond. | ✅ |
| `N-5` | `review` | ⏭ | Ollama did not respond. | `review` | ⏭ | Ollama did not respond. | ✅ |
| `N-6` | `review` | ⏭ | Ollama did not respond. | `review` | ⏭ | Ollama did not respond. | ✅ |
| `N-7` | `review` | ⏭ | Ollama did not respond. | `pass` | ⏭ | Ollama did not respond. | ⚠️ |
| `ST-1` | `pass` | ⏭ | Ollama did not respond. | `pass` | ⏭ | Ollama did not respond. | ✅ |
| `ST-2` | `pass` | ⏭ | Ollama did not respond. | `pass` | ⏭ | Ollama did not respond. | ✅ |
| `ST-3` | `pass` | ⏭ | Ollama did not respond. | `review` | ⏭ | Ollama did not respond. | ⚠️ |
| `ST-4` | `pass` | ⏭ | Ollama did not respond. | `pass` | ⏭ | Ollama did not respond. | ✅ |
| `ST-5` | `pass` | ⏭ | Ollama did not respond. | `pass` | ⏭ | Ollama did not respond. | ✅ |
| `ST-6` | `pass` | ⏭ | Ollama did not respond. | `pass` | ⏭ | Ollama did not respond. | ✅ |
| `ST-7` | `pass` | ⏭ | Ollama did not respond. | `pass` | ⏭ | Ollama did not respond. | ✅ |
| `ST-8` | `pass` | ⏭ | Ollama did not respond. | `pass` | ⏭ | Ollama did not respond. | ✅ |
| `ST-9` | `pass` | ⏭ | Ollama did not respond. | `pass` | ⏭ | Ollama did not respond. | ✅ |
| `ST-10` | `pass` | ⏭ | Ollama did not respond. | `pass` | ⏭ | Ollama did not respond. | ✅ |
| `I-1` | `pass` | ⏭ | Ollama did not respond. | `review` | ⏭ | Ollama did not respond. | ⚠️ |
| `I-2` | `pass` | ⏭ | Ollama did not respond. | `pass` | ⏭ | Ollama did not respond. | ✅ |
| `I-3` | `pass` | ⏭ | Ollama did not respond. | `pass` | ⏭ | Ollama did not respond. | ✅ |
| `I-4` | `pass` | ⏭ | Ollama did not respond. | `pass` | ⏭ | Ollama did not respond. | ✅ |
| `I-5` | `pass` | ⏭ | Ollama did not respond. | `fail` | ⏭ | Ollama did not respond. | ⚠️ |
| `I-6` | `not_applicable` | ❓ |  | `not_applicable` | ❓ |  | ✅ |
| `I-7` | `review` | ⏭ | Ollama did not respond. | `review` | ⏭ | Ollama did not respond. | ✅ |
| `I-8` | `pass` | ⏭ | Ollama did not respond. | `pass` | ⏭ | Ollama did not respond. | ✅ |
| `I-9` | `pass` | ⏭ | Ollama did not respond. | `pass` | ⏭ | Ollama did not respond. | ✅ |
| `I-10` | `review` | ⏭ | Ollama did not respond. | `review` | ⏭ | Ollama did not respond. | ✅ |
| `I-11` | `pass` | ⏭ | Ollama did not respond. | `pass` | ⏭ | Ollama did not respond. | ✅ |
| `I-12` | `review` | ⏭ | Ollama did not respond. | `review` | ⏭ | Ollama did not respond. | ✅ |
| `I-13` | `review` | ⏭ | Ollama did not respond. | `review` | ⏭ | Ollama did not respond. | ✅ |
| `SCA-1` | `pass` | ⏭ | Ollama did not respond. | `pass` | ⏭ | Ollama did not respond. | ✅ |
| `SCA-2` | `fail` | ⏭ | Ollama did not respond. | `pass` | ⏭ | Ollama did not respond. | ⚠️ |
| `SCA-3` | `review` | ⏭ | Ollama did not respond. | `review` | ⏭ | Ollama did not respond. | ✅ |
| `SCA-4` | `pass` | ⏭ | Ollama did not respond. | `pass` | ⏭ | Ollama did not respond. | ✅ |
| `SCA-5` | `pass` | ⏭ | Ollama did not respond. | `pass` | ⏭ | Ollama did not respond. | ✅ |
| `SCA-6` | `pass` | ⏭ | Ollama did not respond. | `pass` | ⏭ | Ollama did not respond. | ✅ |
| `SCA-7` | `review` | ⏭ | Ollama did not respond. | `review` | ⏭ | Ollama did not respond. | ✅ |
| `SCA-8` | `review` | ⏭ | Ollama did not respond. | `review` | ⏭ | Ollama did not respond. | ✅ |
| `SCA-9` | `pass` | ⏭ | Ollama did not respond. | `pass` | ⏭ | Ollama did not respond. | ✅ |
| `SCA-10` | `pass` | ⏭ | Ollama did not respond. | `pass` | ⏭ | Ollama did not respond. | ✅ |
| `SCA-11` | `pass` | ⏭ | Ollama did not respond. | `pass` | ⏭ | Ollama did not respond. | ✅ |
| `SCA-12` | `review` | ⏭ | Ollama did not respond. | `review` | ⏭ | Ollama did not respond. | ✅ |
| `SCA-13` | `pass` | ⏭ | Ollama did not respond. | `pass` | ⏭ | Ollama did not respond. | ✅ |
| `SCA-14` | `pass` | ⏭ | Ollama did not respond. | `pass` | ⏭ | Ollama did not respond. | ✅ |
| `SCA-15` | `pass` | ⏭ | Ollama did not respond. | `pass` | ⏭ | Ollama did not respond. | ✅ |
| `SCA-16` | `pass` | ⏭ | Ollama did not respond. | `pass` | ⏭ | Ollama did not respond. | ✅ |
| `SCA-17` | `review` | ⏭ | Ollama did not respond. | `review` | ⏭ | Ollama did not respond. | ✅ |
| `SCA-18` | `review` | ⏭ | Ollama did not respond. | `review` | ⏭ | Ollama did not respond. | ✅ |
| `SCA-19` | `pass` | ⏭ | Ollama did not respond. | `pass` | ⏭ | Ollama did not respond. | ✅ |
| `SCA-20` | `pass` | ⏭ | Ollama did not respond. | `pass` | ⏭ | Ollama did not respond. | ✅ |
| `SCA-21` | `pass` | ⏭ | Ollama did not respond. | `pass` | ⏭ | Ollama did not respond. | ✅ |
| `SCA-22` | `pass` | ⏭ | Ollama did not respond. | `pass` | ⏭ | Ollama did not respond. | ✅ |
| `SCA-23` | `review` | ⏭ | Ollama did not respond. | `review` | ⏭ | Ollama did not respond. | ✅ |
| `SCA-24` | `review` | ⏭ | Ollama did not respond. | `review` | ⏭ | Ollama did not respond. | ✅ |
| `SCA-25` | `review` | ⏭ | Ollama did not respond. | `review` | ⏭ | Ollama did not respond. | ✅ |
| `SCA-26` | `review` | ⏭ | Ollama did not respond. | `review` | ⏭ | Ollama did not respond. | ✅ |
| `SCA-27` | `not_applicable` | ❓ |  | `not_applicable` | ❓ |  | ✅ |
| `R-1` | `pass` | ⏭ | Ollama did not respond. | `pass` | ⏭ | Ollama did not respond. | ✅ |
| `R-2` | `pass` | ⏭ | Ollama did not respond. | `pass` | ⏭ | Ollama did not respond. | ✅ |
| `CA-1` | `review` | ⏭ | Ollama did not respond. | `fail` | ⏭ | Ollama did not respond. | ⚠️ |
| `CA-2` | `pass` | ⏭ | Ollama did not respond. | `review` | ⏭ | Ollama did not respond. | ⚠️ |
| `IA-1` | `not_applicable` | ❓ |  | `not_applicable` | ❓ |  | ✅ |
| `IA-2` | `not_applicable` | ❓ |  | `not_applicable` | ❓ |  | ✅ |
| `ADD-1` | `review` | ⏭ | Ollama did not respond. | `review` | ⏭ | Ollama did not respond. | ✅ |
| `ADD-2` | `pass` | ⏭ | Ollama did not respond. | `pass` | ⏭ | Ollama did not respond. | ✅ |
| `ADD-3` | `review` | ⏭ | Ollama did not respond. | `review` | ⏭ | Ollama did not respond. | ✅ |
| `ADD-4` | `not_applicable` | ❓ |  | `not_applicable` | ❓ |  | ✅ |
| `ADD-5` | `not_applicable` | ❓ |  | `not_applicable` | ❓ |  | ✅ |
| `ADD-6` | `not_applicable` | ❓ |  | `not_applicable` | ❓ |  | ✅ |
| `ADD-7` | `review` | ⏭ | Ollama did not respond. | `review` | ⏭ | Ollama did not respond. | ✅ |
| `ADD-8` | `not_applicable` | ❓ |  | `review` | ⏭ | Ollama did not respond. | ⚠️ |
| `ADD-9` | `review` | ⏭ | Ollama did not respond. | `review` | ⏭ | Ollama did not respond. | ✅ |
| `DOC-1` | `review` | ⏭ | Ollama did not respond. | `review` | ⏭ | Ollama did not respond. | ✅ |
| `DOC-2` | `not_applicable` | ❓ |  | `not_applicable` | ❓ |  | ✅ |
| `DOC-3` | `pass` | ⏭ | Ollama did not respond. | `pass` | ⏭ | Ollama did not respond. | ✅ |
| `DOC-4` | `not_applicable` | ❓ |  | `not_applicable` | ❓ |  | ✅ |
| `SIG-1` | `pass` | ⏭ | Ollama did not respond. | `pass` | ⏭ | Ollama did not respond. | ✅ |
| `SIG-2` | `pass` | ⏭ | Ollama did not respond. | `pass` | ⏭ | Ollama did not respond. | ✅ |
| `SIG-3` | `review` | ⏭ | Ollama did not respond. | `review` | ⏭ | Ollama did not respond. | ✅ |
| `SIG-4` | `pass` | ⏭ | Ollama did not respond. | `pass` | ⏭ | Ollama did not respond. | ✅ |
| `PH-1` | `pass` | ⏭ | Ollama did not respond. | `pass` | ⏭ | Ollama did not respond. | ✅ |
| `PH-2` | `pass` | ⏭ | Ollama did not respond. | `review` | ⏭ | Ollama did not respond. | ⚠️ |
| `PH-3` | `review` | ⏭ | Ollama did not respond. | `review` | ⏭ | Ollama did not respond. | ✅ |
| `PH-4` | `not_applicable` | ❓ |  | `not_applicable` | ❓ |  | ✅ |
| `PH-5` | `not_applicable` | ❓ |  | `not_applicable` | ❓ |  | ✅ |
| `PH-6` | `review` | ⏭ | Ollama did not respond. | `review` | ⏭ | Ollama did not respond. | ✅ |
| `M-1` | `pass` | ⏭ | Ollama did not respond. | `pass` | ⏭ | Ollama did not respond. | ✅ |
| `M-2` | `pass` | ⏭ | Ollama did not respond. | `pass` | ⏭ | Ollama did not respond. | ✅ |
| `M-3` | `pass` | ⏭ | Ollama did not respond. | `pass` | ⏭ | Ollama did not respond. | ✅ |
| `M-4` | `pass` | ⏭ | Ollama did not respond. | `pass` | ⏭ | Ollama did not respond. | ✅ |
| `SK-1` | `pass` | ⏭ | Ollama did not respond. | `pass` | ⏭ | Ollama did not respond. | ✅ |
| `SK-2` | `review` | ⏭ | Ollama did not respond. | `review` | ⏭ | Ollama did not respond. | ✅ |
| `SK-3` | `pass` | ⏭ | Ollama did not respond. | `review` | ⏭ | Ollama did not respond. | ⚠️ |
| `SK-4` | `review` | ⏭ | Ollama did not respond. | `review` | ⏭ | Ollama did not respond. | ✅ |
| `SK-5` | `review` | ⏭ | Ollama did not respond. | `review` | ⏭ | Ollama did not respond. | ✅ |
| `FHA-1` | `not_applicable` | ❓ |  | `not_applicable` | ❓ |  | ✅ |
| `FHA-2` | `not_applicable` | ❓ |  | `not_applicable` | ❓ |  | ✅ |
| `FHA-3` | `not_applicable` | ❓ |  | `not_applicable` | ❓ |  | ✅ |
| `FHA-4` | `not_applicable` | ❓ |  | `not_applicable` | ❓ |  | ✅ |
| `FHA-5` | `not_applicable` | ❓ |  | `not_applicable` | ❓ |  | ✅ |
| `FHA-6` | `not_applicable` | ❓ |  | `not_applicable` | ❓ |  | ✅ |
| `FHA-7` | `not_applicable` | ❓ |  | `not_applicable` | ❓ |  | ✅ |
| `FHA-8` | `not_applicable` | ❓ |  | `not_applicable` | ❓ |  | ✅ |
| `FHA-9` | `not_applicable` | ❓ |  | `not_applicable` | ❓ |  | ✅ |
| `FHA-10` | `not_applicable` | ❓ |  | `not_applicable` | ❓ |  | ✅ |
| `FHA-11` | `not_applicable` | ❓ |  | `not_applicable` | ❓ |  | ✅ |
| `FHA-12` | `not_applicable` | ❓ |  | `not_applicable` | ❓ |  | ✅ |
| `FHA-13` | `not_applicable` | ❓ |  | `not_applicable` | ❓ |  | ✅ |
| `FHA-14` | `not_applicable` | ❓ |  | `not_applicable` | ❓ |  | ✅ |
| `USDA-1` | `not_applicable` | ❓ |  | `not_applicable` | ❓ |  | ✅ |
| `MF-1` | `review` | ⏭ | Ollama did not respond. | `review` | ⏭ | Ollama did not respond. | ✅ |
| `MF-2` | `review` | ⏭ | Ollama did not respond. | `review` | ⏭ | Ollama did not respond. | ✅ |
| `COM-1` | `review` | ⏭ | Ollama did not respond. | `review` | ⏭ | Ollama did not respond. | ✅ |
| `COM-2` | `fail` | ⏭ | Ollama did not respond. | `fail` | ⏭ | Ollama did not respond. | ✅ |
| `COM-3` | `review` | ⏭ | Ollama did not respond. | `review` | ⏭ | Ollama did not respond. | ✅ |
| `COM-4` | `pass` | ⏭ | Ollama did not respond. | `pass` | ⏭ | Ollama did not respond. | ✅ |
| `COM-5` | `pass` | ⏭ | Ollama did not respond. | `pass` | ⏭ | Ollama did not respond. | ✅ |
| `COM-6` | `pass` | ⏭ | Ollama did not respond. | `pass` | ⏭ | Ollama did not respond. | ✅ |
| `COM-7` | `review` | ⏭ | Ollama did not respond. | `review` | ⏭ | Ollama did not respond. | ✅ |
| `XF-4` | `review` | ❓ |  | `cross_doc_mismatch` | ❓ |  | ⚠️ |

---

## Timing Breakdown

### MSL — MSL (reference — used to build regex/rules)

| Rule | Det Status | Ollama Verdict | Ollama ms | Page |
|---|---|---|---|---|
| `S-1` | `pass` | UNCERTAIN | 0 | 3 |
| `S-2` | `pass` | UNCERTAIN | 0 | 2 |
| `S-3` | `pass` | UNCERTAIN | 0 | 3 |
| `S-4` | `pass` | UNCERTAIN | 0 | 3 |
| `S-5` | `pass` | UNCERTAIN | 0 | 3 |
| `S-6` | `pass` | UNCERTAIN | 0 | 3 |
| `C-1` | `pass` | UNCERTAIN | 0 | 3 |
| `C-2` | `extraction_failed` | UNCERTAIN | 0 | 3 |
| `C-3` | `review` | UNCERTAIN | 0 | 3 |
| `S-7` | `pass` | UNCERTAIN | 0 | 2 |
| `S-8` | `ocr_low_confidence` | UNCERTAIN | 0 | 3 |
| `S-9` | `ocr_low_confidence` | UNCERTAIN | 0 | 3 |
| `S-10` | `extraction_failed` | SKIPPED | cached/skip | 3 |
| `S-11` | `pass` | UNCERTAIN | 0 | 3 |
| `S-12` | `fail` | UNCERTAIN | 0 | 3 |
| `C-4` | `pass` | UNCERTAIN | 0 | 3 |
| `C-5` | `pass` | UNCERTAIN | 0 | 3 |
| `N-1` | `review` | UNCERTAIN | 0 | 3 |
| `N-2` | `review` | UNCERTAIN | 0 | 3 |
| `N-3` | `review` | UNCERTAIN | 0 | 3 |
| `N-4` | `review` | UNCERTAIN | 0 | 3 |
| `N-5` | `review` | UNCERTAIN | 0 | 3 |
| `N-6` | `review` | UNCERTAIN | 0 | 3 |
| `N-7` | `review` | UNCERTAIN | 0 | 3 |
| `ST-1` | `pass` | UNCERTAIN | 0 | 3 |
| `ST-2` | `pass` | UNCERTAIN | 0 | 2 |
| `ST-3` | `pass` | UNCERTAIN | 0 | 3 |
| `ST-4` | `pass` | UNCERTAIN | 0 | 3 |
| `ST-5` | `pass` | UNCERTAIN | 0 | 3 |
| `ST-6` | `pass` | UNCERTAIN | 0 | 3 |
| `ST-7` | `pass` | UNCERTAIN | 0 | 3 |
| `ST-8` | `pass` | UNCERTAIN | 0 | 3 |
| `ST-9` | `pass` | UNCERTAIN | 0 | 3 |
| `ST-10` | `pass` | UNCERTAIN | 0 | 2 |
| `I-1` | `pass` | UNCERTAIN | 0 | 3 |
| `I-2` | `pass` | UNCERTAIN | 0 | 2 |
| `I-3` | `pass` | UNCERTAIN | 0 | 3 |
| `I-4` | `pass` | UNCERTAIN | 0 | 2 |
| `I-5` | `pass` | UNCERTAIN | 0 | 3 |
| `I-6` | `not_applicable` | SKIPPED | cached/skip | — |
| `I-7` | `review` | UNCERTAIN | 0 | 16 |
| `I-8` | `pass` | UNCERTAIN | 0 | 2 |
| `I-9` | `pass` | UNCERTAIN | 0 | 2 |
| `I-10` | `review` | UNCERTAIN | 0 | 2 |
| `I-11` | `pass` | UNCERTAIN | 0 | 2 |
| `I-12` | `review` | UNCERTAIN | 0 | 2 |
| `I-13` | `review` | UNCERTAIN | 0 | 2 |
| `SCA-1` | `pass` | UNCERTAIN | 0 | 4 |
| `SCA-2` | `fail` | UNCERTAIN | 0 | 4 |
| `SCA-3` | `review` | UNCERTAIN | 0 | 4 |
| `SCA-4` | `pass` | UNCERTAIN | 0 | 4 |
| `SCA-5` | `pass` | UNCERTAIN | 0 | 3 |
| `SCA-6` | `pass` | UNCERTAIN | 0 | 4 |
| `SCA-7` | `review` | UNCERTAIN | 0 | 4 |
| `SCA-8` | `review` | UNCERTAIN | 0 | 4 |
| `SCA-9` | `pass` | UNCERTAIN | 0 | 4 |
| `SCA-10` | `pass` | UNCERTAIN | 0 | 4 |
| `SCA-11` | `pass` | UNCERTAIN | 0 | 4 |
| `SCA-12` | `review` | UNCERTAIN | 0 | 4 |
| `SCA-13` | `pass` | UNCERTAIN | 0 | 4 |
| `SCA-14` | `pass` | UNCERTAIN | 0 | 4 |
| `SCA-15` | `pass` | UNCERTAIN | 0 | 4 |
| `SCA-16` | `pass` | UNCERTAIN | 0 | 4 |
| `SCA-17` | `review` | UNCERTAIN | 0 | 4 |
| `SCA-18` | `review` | UNCERTAIN | 0 | 4 |
| `SCA-19` | `pass` | UNCERTAIN | 0 | 4 |
| `SCA-20` | `pass` | UNCERTAIN | 0 | 4 |
| `SCA-21` | `pass` | UNCERTAIN | 0 | 4 |
| `SCA-22` | `pass` | UNCERTAIN | 0 | 4 |
| `SCA-23` | `review` | UNCERTAIN | 0 | 4 |
| `SCA-24` | `review` | UNCERTAIN | 0 | 4 |
| `SCA-25` | `review` | UNCERTAIN | 0 | 4 |
| `SCA-26` | `review` | UNCERTAIN | 0 | 4 |
| `SCA-27` | `not_applicable` | SKIPPED | cached/skip | — |
| `R-1` | `pass` | UNCERTAIN | 0 | 4 |
| `R-2` | `pass` | UNCERTAIN | 0 | 4 |
| `CA-1` | `review` | UNCERTAIN | 0 | 4 |
| `CA-2` | `pass` | UNCERTAIN | 0 | 4 |
| `IA-1` | `not_applicable` | SKIPPED | cached/skip | 4 |
| `IA-2` | `not_applicable` | SKIPPED | cached/skip | 4 |
| `ADD-1` | `review` | UNCERTAIN | 0 | 4 |
| `ADD-2` | `pass` | UNCERTAIN | 0 | 4 |
| `ADD-3` | `review` | UNCERTAIN | 0 | 4 |
| `ADD-4` | `not_applicable` | SKIPPED | cached/skip | — |
| `ADD-5` | `not_applicable` | SKIPPED | cached/skip | — |
| `ADD-6` | `not_applicable` | SKIPPED | cached/skip | — |
| `ADD-7` | `review` | UNCERTAIN | 0 | 4 |
| `ADD-8` | `not_applicable` | SKIPPED | cached/skip | 4 |
| `ADD-9` | `review` | UNCERTAIN | 0 | 4 |
| `DOC-1` | `review` | UNCERTAIN | 0 | 1 |
| `DOC-2` | `not_applicable` | SKIPPED | cached/skip | 1 |
| `DOC-3` | `pass` | UNCERTAIN | 0 | 1 |
| `DOC-4` | `not_applicable` | SKIPPED | cached/skip | 1 |
| `SIG-1` | `pass` | UNCERTAIN | 0 | 1 |
| `SIG-2` | `pass` | UNCERTAIN | 0 | 1 |
| `SIG-3` | `review` | UNCERTAIN | 0 | 1 |
| `SIG-4` | `pass` | UNCERTAIN | 0 | 1 |
| `PH-1` | `pass` | UNCERTAIN | 0 | 16 |
| `PH-2` | `pass` | UNCERTAIN | 0 | 16 |
| `PH-3` | `review` | UNCERTAIN | 0 | 16 |
| `PH-4` | `not_applicable` | SKIPPED | cached/skip | — |
| `PH-5` | `not_applicable` | SKIPPED | cached/skip | 16 |
| `PH-6` | `review` | UNCERTAIN | 0 | 16 |
| `M-1` | `pass` | UNCERTAIN | 0 | 3 |
| `M-2` | `pass` | UNCERTAIN | 0 | 3 |
| `M-3` | `pass` | UNCERTAIN | 0 | 3 |
| `M-4` | `pass` | UNCERTAIN | 0 | 3 |
| `SK-1` | `pass` | UNCERTAIN | 0 | 6 |
| `SK-2` | `review` | UNCERTAIN | 0 | 5 |
| `SK-3` | `pass` | UNCERTAIN | 0 | 5 |
| `SK-4` | `review` | UNCERTAIN | 0 | 5 |
| `SK-5` | `review` | UNCERTAIN | 0 | 5 |
| `FHA-1` | `not_applicable` | SKIPPED | cached/skip | — |
| `FHA-2` | `not_applicable` | SKIPPED | cached/skip | — |
| `FHA-3` | `not_applicable` | SKIPPED | cached/skip | — |
| `FHA-4` | `not_applicable` | SKIPPED | cached/skip | — |
| `FHA-5` | `not_applicable` | SKIPPED | cached/skip | — |
| `FHA-6` | `not_applicable` | SKIPPED | cached/skip | — |
| `FHA-7` | `not_applicable` | SKIPPED | cached/skip | — |
| `FHA-8` | `not_applicable` | SKIPPED | cached/skip | — |
| `FHA-9` | `not_applicable` | SKIPPED | cached/skip | — |
| `FHA-10` | `not_applicable` | SKIPPED | cached/skip | — |
| `FHA-11` | `not_applicable` | SKIPPED | cached/skip | — |
| `FHA-12` | `not_applicable` | SKIPPED | cached/skip | — |
| `FHA-13` | `not_applicable` | SKIPPED | cached/skip | — |
| `FHA-14` | `not_applicable` | SKIPPED | cached/skip | — |
| `USDA-1` | `not_applicable` | SKIPPED | cached/skip | — |
| `MF-1` | `review` | UNCERTAIN | 0 | 2 |
| `MF-2` | `review` | UNCERTAIN | 0 | 2 |
| `COM-1` | `review` | UNCERTAIN | 0 | 4 |
| `COM-2` | `fail` | UNCERTAIN | 0 | 3 |
| `COM-3` | `review` | UNCERTAIN | 0 | 4 |
| `COM-4` | `pass` | UNCERTAIN | 0 | 4 |
| `COM-5` | `pass` | UNCERTAIN | 2 | 4 |
| `COM-6` | `pass` | UNCERTAIN | 0 | 10 |
| `COM-7` | `review` | UNCERTAIN | 0 | 3 |
| `XF-4` | `review` | SKIPPED | cached/skip | — |

Total Ollama enrichment time: **0.0s**  |  Total pipeline time: **0s**

### 2321525470 — #2321525470 (random/unknown — cross-format validation)

| Rule | Det Status | Ollama Verdict | Ollama ms | Page |
|---|---|---|---|---|
| `S-1` | `fail` | UNCERTAIN | 0 | 3 |
| `S-2` | `extraction_failed` | SKIPPED | cached/skip | — |
| `S-3` | `pass` | UNCERTAIN | 0 | 3 |
| `S-4` | `pass` | UNCERTAIN | 0 | 3 |
| `S-5` | `fail` | UNCERTAIN | 0 | 3 |
| `S-6` | `pass` | UNCERTAIN | 0 | 3 |
| `C-1` | `review` | UNCERTAIN | 0 | 3 |
| `C-2` | `extraction_failed` | UNCERTAIN | 0 | 3 |
| `C-3` | `review` | UNCERTAIN | 0 | 3 |
| `S-7` | `pass` | UNCERTAIN | 0 | 3 |
| `S-8` | `extraction_failed` | SKIPPED | cached/skip | 3 |
| `S-9` | `extraction_failed` | UNCERTAIN | 0 | 7 |
| `S-10` | `extraction_failed` | UNCERTAIN | 0 | 2 |
| `S-11` | `pass` | UNCERTAIN | 0 | 3 |
| `S-12` | `fail` | UNCERTAIN | 0 | 5 |
| `C-4` | `pass` | UNCERTAIN | 0 | 3 |
| `C-5` | `fail` | UNCERTAIN | 0 | 3 |
| `N-1` | `review` | UNCERTAIN | 0 | 3 |
| `N-2` | `review` | UNCERTAIN | 0 | 3 |
| `N-3` | `review` | UNCERTAIN | 0 | 3 |
| `N-4` | `review` | UNCERTAIN | 0 | 3 |
| `N-5` | `review` | UNCERTAIN | 0 | 3 |
| `N-6` | `review` | UNCERTAIN | 0 | 3 |
| `N-7` | `pass` | UNCERTAIN | 0 | 3 |
| `ST-1` | `pass` | UNCERTAIN | 0 | 7 |
| `ST-2` | `pass` | UNCERTAIN | 0 | 3 |
| `ST-3` | `review` | UNCERTAIN | 0 | 3 |
| `ST-4` | `pass` | UNCERTAIN | 0 | 3 |
| `ST-5` | `pass` | UNCERTAIN | 0 | 3 |
| `ST-6` | `pass` | UNCERTAIN | 0 | 3 |
| `ST-7` | `pass` | UNCERTAIN | 0 | 3 |
| `ST-8` | `pass` | UNCERTAIN | 0 | 3 |
| `ST-9` | `pass` | UNCERTAIN | 0 | 3 |
| `ST-10` | `pass` | UNCERTAIN | 0 | 3 |
| `I-1` | `review` | UNCERTAIN | 0 | 3 |
| `I-2` | `pass` | UNCERTAIN | 0 | 3 |
| `I-3` | `pass` | UNCERTAIN | 0 | 2 |
| `I-4` | `pass` | UNCERTAIN | 0 | 3 |
| `I-5` | `fail` | UNCERTAIN | 0 | 3 |
| `I-6` | `not_applicable` | SKIPPED | cached/skip | — |
| `I-7` | `review` | UNCERTAIN | 0 | 18 |
| `I-8` | `pass` | UNCERTAIN | 0 | 3 |
| `I-9` | `pass` | UNCERTAIN | 0 | 3 |
| `I-10` | `review` | UNCERTAIN | 0 | 3 |
| `I-11` | `pass` | UNCERTAIN | 0 | 3 |
| `I-12` | `review` | UNCERTAIN | 0 | 3 |
| `I-13` | `review` | UNCERTAIN | 0 | 3 |
| `SCA-1` | `pass` | UNCERTAIN | 0 | 4 |
| `SCA-2` | `pass` | UNCERTAIN | 0 | 4 |
| `SCA-3` | `review` | UNCERTAIN | 0 | 4 |
| `SCA-4` | `pass` | UNCERTAIN | 0 | 4 |
| `SCA-5` | `pass` | UNCERTAIN | 0 | 3 |
| `SCA-6` | `pass` | UNCERTAIN | 0 | 4 |
| `SCA-7` | `review` | UNCERTAIN | 0 | 4 |
| `SCA-8` | `review` | UNCERTAIN | 0 | 4 |
| `SCA-9` | `pass` | UNCERTAIN | 0 | 4 |
| `SCA-10` | `pass` | UNCERTAIN | 0 | 4 |
| `SCA-11` | `pass` | UNCERTAIN | 0 | 4 |
| `SCA-12` | `review` | UNCERTAIN | 0 | 4 |
| `SCA-13` | `pass` | UNCERTAIN | 0 | 4 |
| `SCA-14` | `pass` | UNCERTAIN | 0 | 4 |
| `SCA-15` | `pass` | UNCERTAIN | 0 | 4 |
| `SCA-16` | `pass` | UNCERTAIN | 0 | 4 |
| `SCA-17` | `review` | UNCERTAIN | 0 | 4 |
| `SCA-18` | `review` | UNCERTAIN | 0 | 4 |
| `SCA-19` | `pass` | UNCERTAIN | 0 | 4 |
| `SCA-20` | `pass` | UNCERTAIN | 0 | 4 |
| `SCA-21` | `pass` | UNCERTAIN | 0 | 4 |
| `SCA-22` | `pass` | UNCERTAIN | 0 | 4 |
| `SCA-23` | `review` | UNCERTAIN | 0 | 4 |
| `SCA-24` | `review` | UNCERTAIN | 0 | 4 |
| `SCA-25` | `review` | UNCERTAIN | 0 | 4 |
| `SCA-26` | `review` | UNCERTAIN | 0 | 4 |
| `SCA-27` | `not_applicable` | SKIPPED | cached/skip | — |
| `R-1` | `pass` | UNCERTAIN | 0 | 5 |
| `R-2` | `pass` | UNCERTAIN | 0 | 5 |
| `CA-1` | `fail` | UNCERTAIN | 0 | 10 |
| `CA-2` | `review` | UNCERTAIN | 0 | 10 |
| `IA-1` | `not_applicable` | SKIPPED | cached/skip | 5 |
| `IA-2` | `not_applicable` | SKIPPED | cached/skip | 5 |
| `ADD-1` | `review` | UNCERTAIN | 0 | 2 |
| `ADD-2` | `pass` | UNCERTAIN | 0 | 2 |
| `ADD-3` | `review` | UNCERTAIN | 0 | 2 |
| `ADD-4` | `not_applicable` | SKIPPED | cached/skip | — |
| `ADD-5` | `not_applicable` | SKIPPED | cached/skip | — |
| `ADD-6` | `not_applicable` | SKIPPED | cached/skip | — |
| `ADD-7` | `review` | UNCERTAIN | 0 | 2 |
| `ADD-8` | `review` | UNCERTAIN | 0 | 2 |
| `ADD-9` | `review` | UNCERTAIN | 0 | 2 |
| `DOC-1` | `review` | UNCERTAIN | 0 | 2 |
| `DOC-2` | `not_applicable` | SKIPPED | cached/skip | 2 |
| `DOC-3` | `pass` | UNCERTAIN | 0 | 2 |
| `DOC-4` | `not_applicable` | SKIPPED | cached/skip | 2 |
| `SIG-1` | `pass` | UNCERTAIN | 0 | 2 |
| `SIG-2` | `pass` | UNCERTAIN | 0 | 2 |
| `SIG-3` | `review` | UNCERTAIN | 0 | 9 |
| `SIG-4` | `pass` | UNCERTAIN | 0 | 2 |
| `PH-1` | `pass` | UNCERTAIN | 0 | 23 |
| `PH-2` | `review` | UNCERTAIN | 0 | 23 |
| `PH-3` | `review` | UNCERTAIN | 0 | 23 |
| `PH-4` | `not_applicable` | SKIPPED | cached/skip | — |
| `PH-5` | `not_applicable` | SKIPPED | cached/skip | 23 |
| `PH-6` | `review` | UNCERTAIN | 0 | 23 |
| `M-1` | `pass` | UNCERTAIN | 0 | 3 |
| `M-2` | `pass` | UNCERTAIN | 0 | 3 |
| `M-3` | `pass` | UNCERTAIN | 0 | 3 |
| `M-4` | `pass` | UNCERTAIN | 0 | 3 |
| `SK-1` | `pass` | UNCERTAIN | 0 | 7 |
| `SK-2` | `review` | UNCERTAIN | 0 | 7 |
| `SK-3` | `review` | UNCERTAIN | 0 | 7 |
| `SK-4` | `review` | UNCERTAIN | 0 | 7 |
| `SK-5` | `review` | UNCERTAIN | 0 | 7 |
| `FHA-1` | `not_applicable` | SKIPPED | cached/skip | — |
| `FHA-2` | `not_applicable` | SKIPPED | cached/skip | — |
| `FHA-3` | `not_applicable` | SKIPPED | cached/skip | — |
| `FHA-4` | `not_applicable` | SKIPPED | cached/skip | — |
| `FHA-5` | `not_applicable` | SKIPPED | cached/skip | — |
| `FHA-6` | `not_applicable` | SKIPPED | cached/skip | — |
| `FHA-7` | `not_applicable` | SKIPPED | cached/skip | — |
| `FHA-8` | `not_applicable` | SKIPPED | cached/skip | — |
| `FHA-9` | `not_applicable` | SKIPPED | cached/skip | — |
| `FHA-10` | `not_applicable` | SKIPPED | cached/skip | — |
| `FHA-11` | `not_applicable` | SKIPPED | cached/skip | — |
| `FHA-12` | `not_applicable` | SKIPPED | cached/skip | — |
| `FHA-13` | `not_applicable` | SKIPPED | cached/skip | — |
| `FHA-14` | `not_applicable` | SKIPPED | cached/skip | — |
| `USDA-1` | `not_applicable` | SKIPPED | cached/skip | — |
| `MF-1` | `review` | UNCERTAIN | 0 | 2 |
| `MF-2` | `review` | UNCERTAIN | 0 | 2 |
| `COM-1` | `review` | UNCERTAIN | 0 | 2 |
| `COM-2` | `fail` | UNCERTAIN | 0 | 3 |
| `COM-3` | `review` | UNCERTAIN | 0 | 2 |
| `COM-4` | `pass` | UNCERTAIN | 0 | 5 |
| `COM-5` | `pass` | UNCERTAIN | 0 | 5 |
| `COM-6` | `pass` | UNCERTAIN | 0 | 2 |
| `COM-7` | `review` | UNCERTAIN | 0 | 5 |
| `XF-4` | `cross_doc_mismatch` | SKIPPED | cached/skip | — |

Total Ollama enrichment time: **0.0s**  |  Total pipeline time: **0s**

---

## Sensibility Summary

### What Ollama Agreed With (deterministic rules it confirmed)

### Where Ollama Disagreed

No disagreements recorded.

### Cross-Format Consistency (MSL vs #2321525470)

Rules where the deterministic engine gave DIFFERENT results on the two documents (expected for a different property — this is a sanity check, not a bug):

- `ADD-8`: MSL=`not_applicable` vs #2321525470=`review`
- `C-1`: MSL=`pass` vs #2321525470=`review`
- `C-5`: MSL=`pass` vs #2321525470=`fail`
- `CA-1`: MSL=`review` vs #2321525470=`fail`
- `CA-2`: MSL=`pass` vs #2321525470=`review`
- `I-1`: MSL=`pass` vs #2321525470=`review`
- `I-5`: MSL=`pass` vs #2321525470=`fail`
- `N-7`: MSL=`review` vs #2321525470=`pass`
- `PH-2`: MSL=`pass` vs #2321525470=`review`
- `S-1`: MSL=`pass` vs #2321525470=`fail`
- `S-2`: MSL=`pass` vs #2321525470=`extraction_failed`
- `S-5`: MSL=`pass` vs #2321525470=`fail`
- `S-8`: MSL=`ocr_low_confidence` vs #2321525470=`extraction_failed`
- `S-9`: MSL=`ocr_low_confidence` vs #2321525470=`extraction_failed`
- `SCA-2`: MSL=`fail` vs #2321525470=`pass`
- `SK-3`: MSL=`pass` vs #2321525470=`review`
- `ST-3`: MSL=`pass` vs #2321525470=`review`
- `XF-4`: MSL=`review` vs #2321525470=`cross_doc_mismatch`

---

*Report generated by scripts/run_ollama_batch.py at 2026-05-14 18:58 UTC*
