"""
Day 15 — Tier Two Embedding Extraction

Uses sentence-transformers to match text segments to field concepts by
semantic similarity, without depending on exact label wording.

This tier handles the label-variation failure mode described in the
Architecture Guide section 2: "Label variation failure — Different AMCs
use different words for the same concept."

Architecture:
  1. Pre-compute concept vectors for each field from its synonym list
  2. For each document page, extract candidate text segments (10-50 words)
  3. Embed each candidate segment
  4. Cosine similarity → find the highest-scoring field match above threshold
  5. Extract the likely value from the matching segment using simple regex

Strengths vs other tiers:
  - Works on label variants not in the synonym list
  - Does not depend on exact spatial position
  - Handles paraphrased or abbreviated labels

Weaknesses:
  - Imprecise for exact numeric values (dates, dollar amounts)
  - May match narrative context to wrong field concept
  - Requires careful threshold tuning per field type

Per the plan (Day 16): run in isolation first, measure accuracy per field,
then calibrate per-field thresholds based on results.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, FrozenSet, List, Optional, Tuple

import numpy as np

from app.core.result import ExtractionMethod, ExtractionResult, ExtractionResultSet
from app.core.schema import FieldDefinition, schema_loader

logger = logging.getLogger(__name__)

_EMBEDDING_MODEL_NAME = "all-MiniLM-L6-v2"
_DEFAULT_SIMILARITY_THRESHOLD = 0.68
_HIGH_CONFIDENCE_THRESHOLD = 0.80
_BASE_CONFIDENCE_EMBEDDING = 0.68

# Per-field threshold overrides — critical fields need higher similarity to avoid false positives
_FIELD_THRESHOLDS: Dict[str, float] = {
    "appraised_value":    0.82,   # high — specific numeric meaning
    "contract_price":     0.82,
    "effective_date":     0.80,
    "borrower_name":      0.75,   # moderate — name fields have distinctive labels
    "lender_name":        0.75,
    "property_address":   0.78,
    "appraiser_name":     0.78,
    "market_conditions_commentary": 0.65,  # lower — narrative fields, broader matching
    "neighborhood_description":     0.65,
    "final_reconciliation_comment": 0.65,
}

# Fields that are NOT good candidates for embedding matching
# (exact pattern matching is strictly better for these)
_SKIP_FIELDS: FrozenSet[str] = frozenset([
    "zip_code", "state", "year_built", "tax_year",
    "gla", "stories_in_building", "elevators_count",
    "total_units_in_project", "hoa_monthly_assessment",
    "real_estate_taxes", "census_tract", "assessors_parcel_number",
])


# ---------------------------------------------------------------------------
# Segment extraction
# ---------------------------------------------------------------------------

def _extract_candidate_segments(
    page_text: str, page_number: int, target_length: int = 40
) -> List[Tuple[str, int]]:
    """
    Extract candidate text segments (10-50 words) from a page.
    Returns [(segment_text, approx_char_position), ...].

    Strategy:
    - Split by double newlines (paragraph boundaries)
    - Further split long paragraphs into ~40-word overlapping windows
    - Include single-line segments (form field rows)
    """
    segments: List[Tuple[str, int]] = []

    paragraphs = re.split(r"\n{2,}", page_text)
    char_pos = 0

    for para in paragraphs:
        para = para.strip()
        if not para or len(para.split()) < 3:
            char_pos += len(para) + 2
            continue

        words = para.split()
        word_count = len(words)

        if word_count <= target_length:
            # Short paragraph — use as-is
            segments.append((para, char_pos))
        else:
            # Long paragraph — sliding window with 50% overlap
            step = target_length // 2
            for i in range(0, word_count - 10, step):
                chunk = " ".join(words[i:i + target_length])
                segments.append((chunk, char_pos + sum(len(w) + 1 for w in words[:i])))

        char_pos += len(para) + 2

    return segments


# ---------------------------------------------------------------------------
# Embedding extractor
# ---------------------------------------------------------------------------

class EmbeddingTier2Extractor:
    """
    Day 15 — Embedding Tier 2 Extractor.

    Pre-computes concept vectors for each schema field from its synonym list.
    At extraction time, embeds candidate text segments and finds field matches
    by cosine similarity above a per-field threshold.

    Lazy loading: model is only loaded on first use (avoids 2-3s startup cost).
    """

    def __init__(self) -> None:
        self._schema = schema_loader
        self._model = None
        self._field_vectors: Optional[Dict[str, np.ndarray]] = None

    def _load_model(self) -> None:
        if self._model is None:
            from sentence_transformers import SentenceTransformer
            logger.info("Loading embedding model: %s", _EMBEDDING_MODEL_NAME)
            self._model = SentenceTransformer(_EMBEDDING_MODEL_NAME)
            logger.info("Embedding model loaded")

    def _get_field_vectors(self) -> Dict[str, np.ndarray]:
        """
        Compute or return cached field concept vectors.
        Each field's vector = average of its synonym embeddings.
        """
        if self._field_vectors is not None:
            return self._field_vectors

        self._load_model()
        field_vectors: Dict[str, np.ndarray] = {}

        for fd in self._schema.all_fields():
            if fd.canonical_name in _SKIP_FIELDS:
                continue
            # Build representative phrases from canonical name + synonyms + description
            phrases = [fd.canonical_name.replace("_", " ")]
            phrases.extend(fd.synonyms[:8])  # cap at 8 to stay fast

            if phrases:
                embeddings = self._model.encode(phrases, normalize_embeddings=True)
                avg = np.mean(embeddings, axis=0)
                # Re-normalize after averaging (averaging breaks unit length)
                norm = np.linalg.norm(avg)
                field_vectors[fd.canonical_name] = avg / norm if norm > 0 else avg

        self._field_vectors = field_vectors
        logger.info("Computed concept vectors for %d fields", len(field_vectors))
        return field_vectors

    def find_similar_fields(
        self,
        segment: str,
        threshold: float = _DEFAULT_SIMILARITY_THRESHOLD,
    ) -> List[Tuple[str, float]]:
        """
        Find fields whose concept vector is most similar to the segment embedding.
        Returns [(canonical_name, similarity_score), ...] sorted by similarity desc.
        """
        self._load_model()
        field_vectors = self._get_field_vectors()

        if not field_vectors:
            return []

        seg_vec = self._model.encode([segment], normalize_embeddings=True)[0]

        matches = []
        for fname, fvec in field_vectors.items():
            sim = float(np.dot(seg_vec, fvec))
            field_threshold = _FIELD_THRESHOLDS.get(fname, threshold)
            if sim >= field_threshold:
                matches.append((fname, sim))

        return sorted(matches, key=lambda x: -x[1])

    def extract_missing_fields(
        self,
        page_texts: Dict[int, str],
        document_type: str,
        already_found: Dict[str, ExtractionResult],
    ) -> Dict[str, ExtractionResult]:
        """
        Find fields not found by Tier 3 (spatial) using embedding similarity.
        Returns {canonical_name: ExtractionResult} for newly found fields.
        """
        self._load_model()
        field_vectors = self._get_field_vectors()

        # Which fields are still missing?
        missing = {
            fname for fname in field_vectors
            if fname not in already_found or not already_found[fname].found
        }
        if not missing:
            return {}

        results: Dict[str, ExtractionResult] = {}
        best_per_field: Dict[str, Tuple[float, str, str, int]] = {}
        # {fname: (score, segment_text, extracted_value, page_num)}

        for page_num, page_text in sorted(page_texts.items()):
            if not page_text.strip():
                continue

            segments = _extract_candidate_segments(page_text, page_num)

            for segment, char_pos in segments:
                if len(segment.split()) < 5:
                    continue

                # Embed segment and find matching fields
                seg_vec = self._model.encode([segment], normalize_embeddings=True)[0]

                for fname in missing:
                    if fname not in field_vectors:
                        continue
                    fvec = field_vectors[fname]
                    sim = float(np.dot(seg_vec, fvec))
                    field_threshold = _FIELD_THRESHOLDS.get(fname, _DEFAULT_SIMILARITY_THRESHOLD)

                    if sim >= field_threshold:
                        current = best_per_field.get(fname)
                        if current is None or sim > current[0]:
                            # Try to extract a value from the segment
                            fd = self._schema.get_field(fname)
                            value = self._extract_value_from_segment(segment, fd)
                            if value:
                                best_per_field[fname] = (sim, segment, value, page_num)

        # Convert best matches to ExtractionResults
        for fname, (score, segment, value, page_num) in best_per_field.items():
            conf = _BASE_CONFIDENCE_EMBEDDING + (score - _DEFAULT_SIMILARITY_THRESHOLD) * 0.5
            conf = min(conf, 0.85)

            results[fname] = ExtractionResult(
                canonical_name=fname,
                document_type=document_type,
                value=value,
                raw_source_text=segment[:300],
                extraction_method=ExtractionMethod.EMBEDDING_MATCH,
                confidence=round(conf, 3),
                source_page=page_num,
                normalization_applied=["embedding_tier2"],
            )
            logger.debug("Tier2 found: %s=%r sim=%.3f page=%d", fname, value[:30], score, page_num)

        return results

    @staticmethod
    def _extract_value_from_segment(segment: str, fd: Optional[FieldDefinition]) -> Optional[str]:
        """
        Extract the actual value from a matched segment.
        Uses the field's data type and allowed values to find the right content.
        """
        if fd is None:
            return None

        # For enum fields, look for allowed values in the segment
        if fd.data_type == "enum" and fd.allowed_values:
            seg_lower = segment.lower()
            for av in fd.allowed_values:
                if av.lower() in seg_lower:
                    return av
            return None

        # For boolean fields
        if fd.data_type == "boolean":
            seg_lower = segment.lower()
            if any(m in seg_lower for m in ["yes", "x ", "✓", "true", "checked"]):
                return "True"
            if any(m in seg_lower for m in ["no ", "☐", "false", "unchecked"]):
                return "False"
            return None

        # For UAD codes
        if fd.data_type == "uad_condition":
            m = re.search(r"\bC([1-6])\b", segment)
            if m:
                return f"C{m.group(1)}"
            return None
        if fd.data_type == "uad_quality":
            m = re.search(r"\bQ([1-6])\b", segment)
            if m:
                return f"Q{m.group(1)}"
            return None

        # For currency fields
        if fd.data_type == "currency":
            m = re.search(r"\$\s*([\d,]+(?:\.\d{1,2})?)", segment)
            if m:
                return m.group(0)
            return None

        # For string fields — return the segment itself (caller verifies context)
        # Only if segment is reasonably short (not a whole paragraph)
        words = segment.split()
        if 3 <= len(words) <= 20:
            return segment.strip()

        return None
