"""
Ollama Enrichment — independent llava:13b analysis for every QC rule.

After the deterministic rule engine runs, this service sends the relevant
document text + rule outcome to Ollama and asks for an independent verdict.

Two modes:
  1. per_rule()   — called once per rule; 600-char focused snippet + rule outcome
  2. full_doc()   — called once per document; broad Ollama extraction of key facts

Results stored in rule_result.details under:
  ollama_verdict    : "AGREE" | "DISAGREE" | "UNCERTAIN"
  ollama_finding    : one-sentence Ollama explanation
  ollama_confidence : 0.0–1.0
  ollama_ms         : wall-clock time in milliseconds
  ollama_skipped    : True when Ollama unavailable or text too short
"""

import hashlib
import json
import logging
import re
import time
from typing import Dict, Optional, Tuple

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Section extraction — pull relevant text for each rule family
# ---------------------------------------------------------------------------

# Rule prefix → ordered list of section header keywords to search for
_SECTION_ANCHORS: Dict[str, list] = {
    "S":   ["SUBJECT", "PROPERTY ADDRESS", "BORROWER"],
    "C":   ["CONTRACT", "PURCHASE", "SALE PRICE", "CONTRACT PRICE"],
    "N":   ["NEIGHBORHOOD", "MARKET CONDITIONS", "HOUSING TRENDS"],
    "ST":  ["SITE", "DIMENSIONS", "ZONING", "UTILITIES", "FLOOD"],
    "I":   ["IMPROVEMENTS", "GENERAL DESCRIPTION", "FOUNDATION", "EXTERIOR"],
    "SCA": ["SALES COMPARISON", "COMPARABLE", "SUBJECT", "SALE PRICE"],
    "R":   ["RECONCILIATION", "FINAL VALUE", "OPINION OF VALUE"],
    "CA":  ["COST APPROACH", "DEPRECIATION", "SITE VALUE"],
    "IA":  ["INCOME APPROACH", "GROSS RENT", "INDICATED VALUE"],
    "ADD": ["ADDENDUM", "ADDITIONAL COMMENTS", "SUPPLEMENTAL"],
    "COM": ["NEIGHBORHOOD DESCRIPTION", "MARKET CONDITIONS", "RECONCILIATION"],
    "PH":  ["PHOTOGRAPH", "PHOTO", "SUBJECT FRONT", "SUBJECT REAR"],
    "SK":  ["SKETCH", "FLOOR PLAN", "GROSS LIVING"],
    "M":   ["MAP", "PLAT", "AERIAL"],
    "SIG": ["CERTIFICATION", "SIGNATURE", "APPRAISER"],
    "DOC": ["CERTIFICATION", "LIMITING CONDITIONS"],
    "FHA": ["FHA", "CASE NUMBER", "MIP"],
    "USDA":["USDA", "RURAL"],
    "MF":  ["MULTI-FAMILY", "UNITS", "RENTAL"],
    "XF":  ["SUBJECT", "COMPARABLE"],
}


def _extract_section(raw_text: str, rule_id: str, max_chars: int = 700) -> str:
    """Pull the most relevant text slice for a given rule."""
    if not raw_text:
        return ""

    prefix = (rule_id or "").split("-")[0].upper()
    anchors = _SECTION_ANCHORS.get(prefix, [])

    # Find earliest anchor occurrence
    best_pos = len(raw_text)
    for anchor in anchors:
        idx = raw_text.upper().find(anchor)
        if 0 <= idx < best_pos:
            best_pos = idx

    if best_pos == len(raw_text):
        # No anchor found — return start of document
        return raw_text[:max_chars]

    # Return up to max_chars from anchor position
    snippet = raw_text[best_pos: best_pos + max_chars]
    return snippet.strip()


# ---------------------------------------------------------------------------
# Prompt templates
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = (
    "You are a mortgage appraisal quality control (QC) expert. "
    "Your task is to review a snippet from an appraisal document and "
    "evaluate a QC rule assessment. "
    "Respond ONLY with valid JSON — no markdown, no prose outside the JSON."
)

_RULE_EVAL_TEMPLATE = """\
RULE: {rule_id} — {rule_name}
DESCRIPTION: {description}
SYSTEM RESULT: {status}
SYSTEM MESSAGE: {message}

DOCUMENT SNIPPET:
\"\"\"
{snippet}
\"\"\"

Evaluate whether the system result ({status}) is correct based on the document snippet.
Respond with ONLY this JSON:
{{"agree": true|false, "confidence": 0.0-1.0, "finding": "<one sentence>"}}"""


_FULL_DOC_SYSTEM = (
    "You are a senior mortgage appraisal QC reviewer. "
    "Analyze the appraisal document text below and extract key facts "
    "and identify potential issues. "
    "Respond ONLY with valid JSON."
)

_FULL_DOC_TEMPLATE = """\
Appraisal document text (first {chars} characters):
\"\"\"
{text}
\"\"\"

Extract and analyze. Respond with ONLY this JSON:
{{
  "property_address": "<extracted address or null>",
  "borrower": "<extracted borrower name or null>",
  "contract_price": "<extracted contract price or null>",
  "appraised_value": "<extracted final appraised value or null>",
  "market_conditions_quality": "good|poor|unknown",
  "commentary_issues": ["<issue1>", ...],
  "overall_issues": ["<issue1>", ...],
  "form_type": "<UAD 1004|Condo|Multi-family|unknown>"
}}"""


# ---------------------------------------------------------------------------
# Ollama call helpers
# ---------------------------------------------------------------------------

def _call_ollama(prompt: str, system: str, max_tokens: int = 256) -> Tuple[Optional[str], float]:
    """
    Direct synchronous Ollama call (bypasses request-level disabled flag).

    Uses httpx directly so that a timeout in an unrelated pre-rule enrichment
    stage does not silently suppress per-rule Ollama calls.
    """
    try:
        import httpx
        from app.services.ollama_service import OLLAMA_BASE_URL, get_active_text_model, OLLAMA_TEXT_KEEP_ALIVE
        model = get_active_text_model()
        payload = {
            "model": model,
            "prompt": prompt,
            "system": system,
            "stream": False,
            "keep_alive": OLLAMA_TEXT_KEEP_ALIVE,
            "options": {
                "temperature": 0.0,
                "num_ctx": 512,
                "num_predict": max_tokens,
                "top_k": 1,
            },
        }
        t0 = time.monotonic()
        r = httpx.post(f"{OLLAMA_BASE_URL}/api/generate", json=payload, timeout=60.0)
        r.raise_for_status()
        response = r.json().get("response", "").strip()
        elapsed_ms = (time.monotonic() - t0) * 1000
        return response, elapsed_ms
    except Exception as e:
        logger.debug("Ollama enrichment call failed: %s", e)
        return None, 0.0


def _parse_json_response(response: Optional[str]) -> Optional[dict]:
    if not response:
        return None
    m = re.search(r"\{.*\}", response, re.DOTALL)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except json.JSONDecodeError:
        return None


def _llm_cache_key(task: str, text: str) -> str:
    return hashlib.sha256(f"{task}::{text}".encode()).hexdigest()


def _get_cached(task: str, text: str) -> Optional[str]:
    try:
        from app.services.llm_cache import get_cached_llm
        return get_cached_llm(task, text)
    except Exception:
        return None


def _save_cached(task: str, text: str, response: str) -> None:
    try:
        from app.services.llm_cache import save_llm_response
        from app.services.ollama_service import get_active_text_model
        save_llm_response(task, text, response, get_active_text_model())
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Per-rule enrichment
# ---------------------------------------------------------------------------

# Human-readable description for each rule family
_RULE_DESCRIPTIONS: Dict[str, str] = {
    "S-1":  "Subject property address must match engagement letter exactly.",
    "S-2":  "Borrower name must match engagement letter.",
    "S-3":  "Owner of public record must be stated.",
    "S-4":  "Legal description, APN, and tax information must be complete.",
    "S-5":  "Neighborhood name must be provided.",
    "S-6":  "Map reference and census tract must be filled.",
    "S-7":  "Occupant status (Owner/Tenant/Vacant) must be checked.",
    "S-8":  "Special assessments amount must be present.",
    "S-9":  "HOA dues and PUD status must be indicated.",
    "S-10": "Lender/client name must be present.",
    "S-11": "Property rights (Fee Simple/Leasehold) must be indicated.",
    "S-12": "Prior listing/sale history (offered within 12 months) must be disclosed.",
    "C-1":  "Appraiser must indicate whether they analyzed the purchase contract.",
    "C-2":  "Contract price and date must match purchase agreement.",
    "C-3":  "Owner of record and data source must be identified.",
    "C-4":  "Financial assistance/concessions must be disclosed with amount.",
    "C-5":  "Personal property included in the sale must be addressed.",
    "N-1":  "Neighborhood characteristic checkboxes (location, built-up, growth) must all be completed.",
    "N-2":  "Market trend indicators (values, demand, marketing time) must be checked.",
    "N-3":  "One-unit housing price and age ranges must be populated.",
    "N-4":  "Present land use percentages must total 100%.",
    "N-5":  "Neighborhood boundaries (N/S/E/W) must be described.",
    "N-6":  "Neighborhood description commentary must be specific, not boilerplate.",
    "N-7":  "Market conditions commentary must contain real market analysis.",
    "ST-1": "Site dimensions must be stated.",
    "ST-2": "Site area (sf or acres) must be stated.",
    "ST-3": "Site shape must be described.",
    "ST-4": "View must be described.",
    "ST-5": "Zoning classification and compliance must be stated.",
    "ST-6": "Highest and best use determination must be made.",
    "ST-7": "Utilities (electric/gas/water/sewer) must be indicated.",
    "ST-8": "FEMA flood zone and map date must be stated.",
    "I-1":  "Effective age of improvements must be stated.",
    "I-3":  "Roof surface type must be stated.",
    "I-5":  "Utilities inspection notes must be complete.",
    "I-7":  "Above-grade GLA (Gross Living Area) must be stated.",
    "SCA-1":"At least 3 comparable sales must be analyzed.",
    "SCA-2":"Comparable sale prices must be stated for all comparables.",
    "SCA-5":"Data sources for comparable sales (MLS, DOM) must be cited.",
    "R-1":  "Reconciliation must address all approaches to value used.",
    "R-2":  "Final appraised value must be stated.",
    "COM-1":"Neighborhood description commentary must be specific to the subject area.",
    "COM-2":"Market conditions commentary must contain real analysis, not just 'See 1004MC'.",
    "COM-3":"Comparable selection rationale must be explained.",
    "COM-4":"Adjustments in the sales grid must be explained.",
    "COM-5":"Reconciliation commentary must explain why the final value was chosen.",
    "COM-6":"Addenda must not contradict main report values.",
    "COM-7":"Prior sales of the subject must be disclosed and analyzed.",
    "SIG-1":"Appraiser signature and license number must be present.",
    "PH-1": "Subject photographs (front, rear, street) must be present.",
    "FHA-1":"FHA case number must be present for FHA appraisals.",
}


def per_rule(
    rule_id: str,
    rule_name: str,
    status: str,
    message: str,
    raw_text: str,
    engagement_text: str = "",
    contract_text: str = "",
) -> dict:
    """
    Run Ollama enrichment for a single rule result.

    Returns a dict with keys:
      ollama_verdict    : "AGREE" | "DISAGREE" | "UNCERTAIN"
      ollama_finding    : str
      ollama_confidence : float
      ollama_ms         : float
      ollama_skipped    : bool
    """
    # Check availability
    try:
        from app.services.ollama_service import is_ollama_available
        if not is_ollama_available():
            return {"ollama_skipped": True, "ollama_verdict": "UNCERTAIN", "ollama_ms": 0.0}
    except Exception:
        return {"ollama_skipped": True, "ollama_verdict": "UNCERTAIN", "ollama_ms": 0.0}

    prefix = (rule_id or "").split("-")[0].upper()
    description = _RULE_DESCRIPTIONS.get(rule_id, f"Check {rule_name}")

    # Build combined text: appraisal snippet + engagement snippet for cross-doc rules
    snippet = _extract_section(raw_text, rule_id, max_chars=500)
    if engagement_text and prefix in {"S", "C"}:
        eng_snippet = _extract_section(engagement_text, rule_id, max_chars=150)
        if eng_snippet:
            snippet = f"[APPRAISAL]\n{snippet}\n[ENGAGEMENT LETTER]\n{eng_snippet}"
    if contract_text and prefix == "C":
        con_snippet = _extract_section(contract_text, "C", max_chars=150)
        if con_snippet:
            snippet = f"{snippet}\n[CONTRACT]\n{con_snippet}"

    if len(snippet.strip()) < 20:
        return {"ollama_skipped": True, "ollama_verdict": "UNCERTAIN", "ollama_ms": 0.0,
                "ollama_finding": "Insufficient text to evaluate."}

    # Cache lookup
    cache_input = f"{rule_id}::{status}::{snippet[:400]}"
    cached = _get_cached(f"enrich_{rule_id}", cache_input)
    if cached:
        parsed = _parse_json_response(cached)
        if parsed:
            agree = parsed.get("agree", None)
            verdict = "AGREE" if agree is True else ("DISAGREE" if agree is False else "UNCERTAIN")
            return {
                "ollama_verdict": verdict,
                "ollama_finding": str(parsed.get("finding", ""))[:200],
                "ollama_confidence": float(parsed.get("confidence", 0.5)),
                "ollama_ms": 0.0,
                "ollama_cached": True,
                "ollama_skipped": False,
            }

    prompt = _RULE_EVAL_TEMPLATE.format(
        rule_id=rule_id,
        rule_name=rule_name,
        description=description,
        status=status,
        message=message[:200],
        snippet=snippet[:500],
    )

    response, elapsed_ms = _call_ollama(prompt, system=_SYSTEM_PROMPT, max_tokens=128)

    if not response:
        return {"ollama_skipped": True, "ollama_verdict": "UNCERTAIN",
                "ollama_ms": elapsed_ms, "ollama_finding": "Ollama did not respond."}

    parsed = _parse_json_response(response)
    if not parsed:
        # Try simple keyword parse
        upper = response.upper()
        if "AGREE" in upper and "DISAGREE" not in upper:
            verdict, conf = "AGREE", 0.6
        elif "DISAGREE" in upper:
            verdict, conf = "DISAGREE", 0.6
        else:
            verdict, conf = "UNCERTAIN", 0.4
        result = {
            "ollama_verdict": verdict,
            "ollama_confidence": conf,
            "ollama_finding": response.strip()[:200],
            "ollama_ms": elapsed_ms,
            "ollama_skipped": False,
        }
        _save_cached(f"enrich_{rule_id}", cache_input, response)
        return result

    _save_cached(f"enrich_{rule_id}", cache_input, json.dumps(parsed))

    agree = parsed.get("agree", None)
    verdict = "AGREE" if agree is True else ("DISAGREE" if agree is False else "UNCERTAIN")
    return {
        "ollama_verdict": verdict,
        "ollama_finding": str(parsed.get("finding", ""))[:200],
        "ollama_confidence": float(parsed.get("confidence", 0.5)),
        "ollama_ms": elapsed_ms,
        "ollama_skipped": False,
    }


# ---------------------------------------------------------------------------
# Full-document Ollama analysis
# ---------------------------------------------------------------------------

def full_doc(
    appraisal_text: str,
    engagement_text: str = "",
    contract_text: str = "",
) -> dict:
    """
    One Ollama call that covers the full appraisal document.

    Extracts key facts independently of the regex pipeline so we can
    compare Ollama's extraction against the deterministic extraction.

    Returns dict with keys from _FULL_DOC_TEMPLATE + ollama_ms, ollama_skipped.
    """
    try:
        from app.services.ollama_service import is_ollama_available
        if not is_ollama_available():
            return {"ollama_skipped": True, "ollama_ms": 0.0}
    except Exception:
        return {"ollama_skipped": True, "ollama_ms": 0.0}

    # Use first 1800 chars of appraisal + 400 of engagement + 400 of contract
    combined = appraisal_text[:1800]
    if engagement_text:
        combined += f"\n\n[ENGAGEMENT LETTER]\n{engagement_text[:400]}"
    if contract_text:
        combined += f"\n\n[CONTRACT]\n{contract_text[:400]}"

    cache_input = combined[:800]
    cached = _get_cached("full_doc_analysis", cache_input)
    if cached:
        parsed = _parse_json_response(cached)
        if parsed:
            parsed["ollama_cached"] = True
            parsed["ollama_skipped"] = False
            parsed["ollama_ms"] = 0.0
            return parsed

    prompt = _FULL_DOC_TEMPLATE.format(
        chars=len(combined),
        text=combined[:2000],
    )

    response, elapsed_ms = _call_ollama(
        prompt, system=_FULL_DOC_SYSTEM, max_tokens=400
    )

    if not response:
        return {"ollama_skipped": True, "ollama_ms": elapsed_ms}

    parsed = _parse_json_response(response) or {}
    _save_cached("full_doc_analysis", cache_input, response)

    parsed["ollama_ms"] = elapsed_ms
    parsed["ollama_skipped"] = False
    return parsed
