import json
import logging
import os
from typing import Any, Dict, Optional

import httpx
from app.models.difference_report import SubjectSectionExtract

logger = logging.getLogger(__name__)

SUBJECT_SECTION_PROMPT = """
You are an expert appraisal QC reviewer. Extract the following fields from the
appraisal document text below. Return ONLY a JSON object with this exact structure.
For each field, provide the extracted value AND a confidence score from 0.0 to 1.0.

{
  "property_address": {"value": "...", "confidence": 0.0},
  "borrower_name": {"value": "...", "confidence": 0.0},
  "city": {"value": "...", "confidence": 0.0},
  "zip_code": {"value": "...", "confidence": 0.0},
  "county": {"value": "...", "confidence": 0.0},
  "neighborhood_name": {"value": "...", "confidence": 0.0},
  "census_tract": {"value": "...", "confidence": 0.0},
  "apn": {"value": "...", "confidence": 0.0},
  "lender_name": {"value": "...", "confidence": 0.0},
  "occupant": {"value": "...", "confidence": 0.0}
}

Rules for confidence:
- 1.0 = field is clearly and unambiguously present in an expected format
- 0.8-0.99 = field present but minor formatting uncertainty
- 0.5-0.79 = field inferred or partially visible
- <0.5 = field missing or very unclear

Document text:
{document_text}
"""


class AIExtractionService:
    def __init__(self) -> None:
        self.enabled = os.getenv("USE_AI_EXTRACTION", "false").lower() == "true"
        self.provider = os.getenv("AI_PROVIDER", "ollama").lower()
        self.model = os.getenv("AI_MODEL", "llama3.1:8b")
        self.ollama_base_url = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434")
        self.threshold = float(os.getenv("CONFIDENCE_THRESHOLD", "0.95"))

    def is_available(self) -> bool:
        if not self.enabled:
            return False
        if self.provider != "ollama":
            logger.warning("Unsupported AI_PROVIDER=%s. Only local Ollama is allowed.", self.provider)
            return False
        return True

    def extract_subject_with_confidence(self, document_text: str) -> Dict[str, Any]:
        prompt = SUBJECT_SECTION_PROMPT.format(document_text=document_text[:4000])
        raw_text = self._call_model(prompt)
        parsed = self._parse_json_response(raw_text)

        auto_filled: Dict[str, Any] = {}
        needs_review: Dict[str, Any] = {}
        for field, result in parsed.items():
            confidence = float(result.get("confidence", 0.0))
            if confidence >= self.threshold:
                auto_filled[field] = result
            else:
                needs_review[field] = result

        return {
            "raw": parsed,
            "auto_filled": auto_filled,
            "needs_review": needs_review,
        }

    def _call_model(self, prompt: str) -> str:
        if self.provider != "ollama":
            raise RuntimeError("Only local Ollama extraction assist is allowed")
        return self._call_ollama(prompt)

    def _call_ollama(self, prompt: str) -> str:
        url = f"{self.ollama_base_url.rstrip('/')}/api/generate"
        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": 0},
        }
        with httpx.Client(timeout=120) as client:
            response = client.post(url, json=payload)
            response.raise_for_status()
            data = response.json()
            return data.get("response", "{}")

    @staticmethod
    def _parse_json_response(raw_text: str) -> Dict[str, Any]:
        text = raw_text.strip()
        if text.startswith("```"):
            # Strip markdown code fences from model output.
            text = text.strip("`")
            if text.startswith("json"):
                text = text[4:].strip()
        start = text.find("{")
        end = text.rfind("}")
        if start == -1 or end == -1 or end <= start:
            raise ValueError("LLM response did not contain JSON object")
        return json.loads(text[start : end + 1])

    def to_subject_extract(self, ai_result: Dict[str, Any]) -> SubjectSectionExtract:
        raw = ai_result.get("raw", {})
        return SubjectSectionExtract(
            property_address=self._value(raw, "property_address"),
            borrower_name=self._value(raw, "borrower_name"),
            city=self._value(raw, "city"),
            zip_code=self._value(raw, "zip_code"),
            county=self._value(raw, "county"),
            neighborhood_name=self._value(raw, "neighborhood_name"),
            census_tract=self._value(raw, "census_tract"),
            assessors_parcel_number=self._value(raw, "apn"),
            lender_name=self._value(raw, "lender_name"),
            occupant_status=self._value(raw, "occupant"),
        )

    @staticmethod
    def _value(raw: Dict[str, Any], field_name: str) -> Optional[str]:
        field = raw.get(field_name)
        if isinstance(field, dict):
            value = field.get("value")
            return str(value).strip() if value is not None else None
        return None


ai_extraction_service = AIExtractionService()
