"""
Async LLM enrichment for semi-structured appraisal fields.

This runs after OCR/field extraction and before the rule engine so rules and
cross-field checks can consume normalized judgments instead of each rule making
its own sequential Ollama call.
"""

import asyncio
import json
import logging
import re
from typing import Any, Optional

from app.models.appraisal import ValidationContext
from app.services.ollama_service import gather_text_prompts, is_ollama_available

logger = logging.getLogger(__name__)

SYSTEM_JSON = (
    "You are a mortgage appraisal QC extraction assistant. "
    "Return only valid JSON. No markdown, no explanation."
)


def _json(response: Optional[str]) -> dict[str, Any]:
    if not response:
        return {"confidence": "low", "error": "no_response"}
    match = re.search(r"\{.*\}", response, re.DOTALL)
    raw = match.group(0) if match else response
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, dict):
            return parsed
    except Exception:
        pass
    return {"confidence": "low", "raw_response": response[:500], "error": "unparseable"}


def _confidence_score(value: Any) -> float:
    text = str(value or "").strip().lower()
    if text in {"high", "very high", "true"}:
        return 0.90
    if text in {"medium", "moderate"}:
        return 0.75
    return 0.60


def _page_excerpt(ctx: ValidationContext, terms: list[str], limit: int = 2200) -> str:
    text = ctx.raw_text or ""
    if not text:
        return ""
    lowered = text.lower()
    hits: list[str] = []
    for term in terms:
        pos = lowered.find(term.lower())
        if pos >= 0:
            hits.append(text[max(0, pos - 450):pos + 1000])
    excerpt = "\n\n".join(hits) if hits else text[:limit]
    return excerpt[:limit]


async def enrich_context(ctx: ValidationContext) -> dict[str, Any]:
    if not is_ollama_available():
        ctx.llm_enrichment = {"available": False, "reason": "ollama_unavailable"}
        return ctx.llm_enrichment

    subject = ctx.report.subject
    contract = ctx.report.contract
    neighborhood = ctx.report.neighborhood
    engagement = ctx.engagement_letter

    report_address = " ".join(v for v in [subject.address, subject.city, subject.state, subject.zip_code] if v)
    reference_address = " ".join(v for v in [
        engagement.property_address if engagement else None,
        engagement.city if engagement else None,
        engagement.state if engagement else None,
        engagement.zip_code if engagement else None,
    ] if v)

    neighborhood_text = (
        neighborhood.boundaries_description
        or neighborhood.description_commentary
        or _page_excerpt(ctx, ["neighborhood", "boundar", "north", "south"])
    )
    contract_text = _page_excerpt(ctx, ["contract", "signature", "sale price", "concession"])
    sca_text = _page_excerpt(ctx, ["sales comparison", "concession", "financing", "data source"])
    concession_source = (contract_text + "\n" + sca_text)[:2600]
    commentary_text = "\n\n".join(filter(None, [
        neighborhood.description_commentary,
        neighborhood.market_conditions_comment,
        ctx.report.sales_comparison.summary_commentary,
    ])) or _page_excerpt(ctx, ["comment", "analysis", "reconciliation", "market"])

    prompts: list[tuple[str, str, int]] = []
    keys: list[str] = []

    if report_address and reference_address:
        keys.append("address_normalization")
        prompts.append((f"""
Are these two addresses referring to the same physical location?
Address A from appraisal: {report_address}
Address B from reference document: {reference_address}
Return JSON: {{"same_location": true/false, "confidence": "high|medium|low", "reason": "short reason"}}
""".strip(), SYSTEM_JSON, 180))

    if neighborhood_text:
        keys.append("neighborhood_boundaries")
        prompts.append((f"""
Extract neighborhood boundaries from this appraisal text.
Text:
{neighborhood_text[:2200]}
Return JSON: {{"north": string|null, "south": string|null, "east": string|null, "west": string|null, "confidence": "high|medium|low"}}
""".strip(), SYSTEM_JSON, 220))

    if contract_text:
        keys.append("contract_last_signature_date")
        prompts.append((f"""
Identify the fully executed contract date, meaning the latest buyer/seller signature date.
Text:
{contract_text[:2200]}
Return JSON: {{"date": string|null, "confidence": "high|medium|low", "reason": "short reason"}}
""".strip(), SYSTEM_JSON, 180))

        keys.append("concession_analysis")
        prompts.append((f"""
Extract sale type, financing type, and concession amount from this contract or sales-comparison text.
Text:
{concession_source}
Return JSON: {{"sale_type": string|null, "financing_type": string|null, "concession_amount": number|null, "confidence": "high|medium|low", "concern": string|null}}
""".strip(), SYSTEM_JSON, 220))

    if commentary_text:
        keys.append("commentary_quality")
        prompts.append((f"""
Evaluate whether this appraisal commentary is property-specific and analytical.
Text:
{commentary_text[:2600]}
Return JSON: {{"has_property_specific_detail": true/false, "explains_comparable_selection": true/false, "explains_market_conditions": true/false, "explains_reconciliation": true/false, "confidence": "high|medium|low", "concern": string|null}}
""".strip(), SYSTEM_JSON, 220))

    if not prompts:
        ctx.llm_enrichment = {"available": True, "items": {}}
        return ctx.llm_enrichment

    responses = await gather_text_prompts(prompts)
    items: dict[str, Any] = {}
    for key, response in zip(keys, responses):
        parsed = _json(response)
        parsed["llm_confidence_score"] = _confidence_score(parsed.get("confidence"))
        items[key] = parsed

    _apply_enrichment(ctx, items)
    ctx.llm_enrichment = {"available": True, "items": items}
    return ctx.llm_enrichment


def enrich_context_sync(ctx: ValidationContext) -> dict[str, Any]:
    try:
        return asyncio.run(enrich_context(ctx))
    except RuntimeError:
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(enrich_context(ctx))
        finally:
            loop.close()
    except Exception as exc:
        logger.info("LLM enrichment not run: %s", exc)
        ctx.llm_enrichment = {"available": False, "reason": str(exc)}
        return ctx.llm_enrichment


def _apply_enrichment(ctx: ValidationContext, items: dict[str, Any]) -> None:
    boundaries = items.get("neighborhood_boundaries") or {}
    if any(boundaries.get(k) for k in ("north", "south", "east", "west")):
        ctx.report.neighborhood.boundaries_description = json.dumps({
            "north": boundaries.get("north"),
            "south": boundaries.get("south"),
            "east": boundaries.get("east"),
            "west": boundaries.get("west"),
        })

    contract_date = (items.get("contract_last_signature_date") or {}).get("date")
    if contract_date:
        ctx.report.contract.date_of_contract = str(contract_date)

    concession = items.get("concession_analysis") or {}
    if concession.get("concession_amount") is not None:
        try:
            ctx.report.contract.financial_assistance_amount = float(concession["concession_amount"])
            ctx.report.contract.financial_assistance = ctx.report.contract.financial_assistance_amount > 0
        except Exception:
            pass
    if concession.get("sale_type"):
        ctx.report.contract.sale_type = str(concession["sale_type"])
