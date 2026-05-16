"""
Days 24–25 — AMC Profile Active Building and Template Change Detection

Day 24 (Plan): "Implement the logic that actively builds and updates AMC profiles
based on processed documents. Profile maturity tracking. Profile-informed confidence
adjustment. Automatic terminology mapping updates."

Day 25 (Plan): "Implement the detection logic that identifies when an AMC has
updated their document template. When a new document's structural fingerprint does
not match any known template version, create a new template version record and set
a 'template change detected' flag."

Architecture Guide §8 (Layer Four): "The format registry is a database of everything
your system has learned about each document format it has processed."

The profile stores:
  - fingerprint_json: structural features for template matching
  - terminology_mapping_json: AMC-specific label → canonical field mappings
  - confidence_threshold_overrides_json: per-field threshold adjustments for this AMC
  - document_count + maturity_level: new (1-9) | developing (10-49) | mature (50+)
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

_FINGERPRINT_SIMILARITY_MATURE = 0.85    # high threshold for mature profiles
_FINGERPRINT_SIMILARITY_DEVELOPING = 0.70
_FINGERPRINT_SIMILARITY_NEW = 0.55


def update_profile_from_document(
    amc_id: str,
    document_type: str,
    fingerprint: dict,
    field_location_priors: Optional[Dict[str, int]] = None,
) -> Tuple[bool, bool]:
    """
    Day 24: Update AMC profile after processing a document.
    Returns (profile_updated: bool, template_change_detected: bool).

    Architecture Guide §8: "As more documents from the same AMC are processed,
    the profile becomes richer. Each new document is processed using the accumulated
    profile knowledge, and the results are used to further refine the profile."
    """
    try:
        from app.database import get_db
        from app.models.db_models import AmcProfileRow, AmcTemplateVersionRow

        with get_db() as session:
            profile = session.query(AmcProfileRow).filter_by(amc_id=amc_id).first()

            if profile is None:
                # First document from this AMC — create profile
                profile = AmcProfileRow(
                    amc_id=amc_id,
                    amc_name=amc_id.replace("_", " ").title(),
                    document_count=1,
                    maturity_level="new",
                    fingerprint_json=json.dumps(fingerprint),
                    terminology_mapping_json=json.dumps({}),
                    confidence_threshold_overrides_json=json.dumps({}),
                )
                session.add(profile)
                session.flush()

                # Create initial template version
                version = AmcTemplateVersionRow(
                    profile_id=profile.id,
                    amc_id=amc_id,
                    version_label="v1.0",
                    structural_fingerprint_json=json.dumps(fingerprint),
                    is_active=True,
                    document_count=1,
                )
                session.add(version)
                logger.info("Created AMC profile: %s (first document)", amc_id)
                return True, False

            # Update existing profile
            profile.document_count += 1
            _update_maturity(profile)
            profile.fingerprint_json = json.dumps(_merge_fingerprints(
                json.loads(profile.fingerprint_json or "{}"), fingerprint
            ))

            # Day 25: Template change detection
            template_change = _detect_template_change(
                session, profile, amc_id, fingerprint
            )
            return True, template_change

    except Exception as exc:
        logger.warning("AMC profile update failed (non-fatal): %s", exc)
        return False, False


def update_terminology_from_correction(
    amc_id: str,
    label_used: str,
    canonical_field: str,
) -> bool:
    """
    Day 27 prerequisite (fast-path learning): When a reviewer corrects a field
    with reason 'wrong_label_matched', add the label to the AMC's terminology mapping.
    Plan (Day 27): 'This fast-path update takes effect immediately.'
    """
    try:
        from app.database import get_db
        from app.models.db_models import AmcProfileRow

        with get_db() as session:
            profile = session.query(AmcProfileRow).filter_by(amc_id=amc_id).first()
            if not profile:
                return False

            term_map = json.loads(profile.terminology_mapping_json or "{}")
            if label_used not in term_map:
                term_map[label_used] = canonical_field
                profile.terminology_mapping_json = json.dumps(term_map)
                logger.info(
                    "Fast-path terminology update: AMC=%s label=%r → %s",
                    amc_id, label_used, canonical_field,
                )
                return True
    except Exception as exc:
        logger.warning("Terminology update failed: %s", exc)
    return False


def get_amc_terminology(amc_id: str) -> Dict[str, str]:
    """Load the AMC's label→canonical field mapping."""
    try:
        from app.database import get_db
        from app.models.db_models import AmcProfileRow
        with get_db() as session:
            profile = session.query(AmcProfileRow).filter_by(amc_id=amc_id).first()
            if profile:
                return json.loads(profile.terminology_mapping_json or "{}")
    except Exception:
        pass
    return {}


def apply_amc_confidence_adjustment(
    confidence: float, field_name: str, amc_id: str, page_number: int
) -> float:
    """
    Day 24: Profile-informed confidence adjustment.
    Plan (Day 24): "A field found in the expected location for this AMC gets a
    small confidence boost (+0.05). A field found in an unexpected location gets
    a small confidence reduction (-0.05). This adjustment is small — at most ten
    points — because location prior should never override content-based confidence."
    """
    # This is a foundation — full location prior learning in Phase Four
    # For now, apply ±0.05 based on confidence threshold overrides in profile
    try:
        from app.database import get_db
        from app.models.db_models import AmcProfileRow
        with get_db() as session:
            profile = session.query(AmcProfileRow).filter_by(amc_id=amc_id).first()
            if not profile:
                return confidence
            overrides = json.loads(profile.confidence_threshold_overrides_json or "{}")
            field_override = overrides.get(field_name)
            if field_override:
                adjustment = float(field_override.get("confidence_boost", 0.0))
                return min(1.0, max(0.0, confidence + adjustment))
    except Exception:
        pass
    return confidence


# ---------------------------------------------------------------------------
# Day 25 — Template change detection
# ---------------------------------------------------------------------------

def _detect_template_change(session, profile, amc_id: str, new_fingerprint: dict) -> bool:
    """
    Compare new document fingerprint to known template versions.
    If similarity is below threshold → new template version detected.
    """
    from app.models.db_models import AmcTemplateVersionRow

    existing_versions = session.query(AmcTemplateVersionRow).filter_by(
        amc_id=amc_id, is_active=True
    ).all()

    if not existing_versions:
        return False

    # Compute similarity against the most recent active version
    latest = max(existing_versions, key=lambda v: v.first_seen_date)
    known_fp = json.loads(latest.structural_fingerprint_json or "{}")
    similarity = _fingerprint_similarity(known_fp, new_fingerprint)

    # Threshold depends on profile maturity
    threshold = {
        "mature":     _FINGERPRINT_SIMILARITY_MATURE,
        "developing": _FINGERPRINT_SIMILARITY_DEVELOPING,
        "new":        _FINGERPRINT_SIMILARITY_NEW,
    }.get(profile.maturity_level, _FINGERPRINT_SIMILARITY_NEW)

    if similarity < threshold:
        # Template change detected — create new version record
        new_version_label = f"v{len(existing_versions) + 1}.0"
        new_version = AmcTemplateVersionRow(
            profile_id=profile.id,
            amc_id=amc_id,
            version_label=new_version_label,
            structural_fingerprint_json=json.dumps(new_fingerprint),
            is_active=True,
            document_count=1,
        )
        session.add(new_version)

        logger.warning(
            "TEMPLATE CHANGE DETECTED: AMC=%s | similarity=%.2f (threshold=%.2f) | "
            "new version=%s | "
            "page_count: %s→%s | software: %s→%s",
            amc_id, similarity, threshold, new_version_label,
            known_fp.get("total_pages"), new_fingerprint.get("total_pages"),
            known_fp.get("software"), new_fingerprint.get("software"),
        )
        return True

    # Same template — update document count
    latest.document_count += 1
    return False


def _fingerprint_similarity(fp1: dict, fp2: dict) -> float:
    """
    Compute similarity score between two document fingerprints.
    Simple weighted average of matching structural features.
    """
    if not fp1 or not fp2:
        return 0.5

    score = 0.0
    weights = 0.0

    # Page count similarity (weight: 2)
    p1 = fp1.get("total_pages", 0)
    p2 = fp2.get("total_pages", 0)
    if p1 > 0 and p2 > 0:
        page_sim = 1.0 - abs(p1 - p2) / max(p1, p2)
        score += page_sim * 2
        weights += 2

    # Software marker match (weight: 3)
    s1 = set(fp1.get("software", []))
    s2 = set(fp2.get("software", []))
    if s1 or s2:
        software_sim = len(s1 & s2) / max(len(s1 | s2), 1)
        score += software_sim * 3
        weights += 3

    # Form type match (weight: 3)
    f1 = fp1.get("form_type", "unknown")
    f2 = fp2.get("form_type", "unknown")
    if f1 != "unknown" or f2 != "unknown":
        form_sim = 1.0 if f1 == f2 else 0.0
        score += form_sim * 3
        weights += 3

    # Section headers overlap (weight: 2)
    h1 = set(fp1.get("section_headers_present", []))
    h2 = set(fp2.get("section_headers_present", []))
    if h1 or h2:
        header_sim = len(h1 & h2) / max(len(h1 | h2), 1)
        score += header_sim * 2
        weights += 2

    return score / weights if weights > 0 else 0.5


def _merge_fingerprints(existing: dict, new: dict) -> dict:
    """Merge new fingerprint data into existing profile fingerprint."""
    merged = dict(existing)
    # Update page count (running average conceptually — just update to latest)
    merged["total_pages"] = new.get("total_pages", existing.get("total_pages", 0))
    # Union software markers
    existing_sw = set(existing.get("software", []))
    new_sw = set(new.get("software", []))
    merged["software"] = list(existing_sw | new_sw)
    # Union section headers
    existing_h = set(existing.get("section_headers_present", []))
    new_h = set(new.get("section_headers_present", []))
    merged["section_headers_present"] = list(existing_h | new_h)
    return merged


def _update_maturity(profile) -> None:
    """Update maturity level based on document count."""
    count = profile.document_count
    if count >= 50:
        profile.maturity_level = "mature"
    elif count >= 10:
        profile.maturity_level = "developing"
    else:
        profile.maturity_level = "new"


def list_profiles() -> List[dict]:
    """Return all AMC profiles for the operations dashboard."""
    try:
        from app.database import get_db
        from app.models.db_models import AmcProfileRow
        with get_db() as session:
            profiles = session.query(AmcProfileRow).all()
            return [
                {
                    "amc_id": p.amc_id,
                    "amc_name": p.amc_name,
                    "document_count": p.document_count,
                    "maturity_level": p.maturity_level,
                    "terminology_entries": len(json.loads(p.terminology_mapping_json or "{}")),
                    "updated_at": p.updated_at.isoformat() if p.updated_at else None,
                }
                for p in profiles
            ]
    except Exception:
        return []
