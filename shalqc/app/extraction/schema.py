"""
extraction/schema.py — loads config/field_schema.yaml (sch-1.0.0) → FieldDef registry.

Hot-reloadable: call schema_loader.reload() — no service restart needed
(`PUT /schema/reload`, SHALqc.md §9). Every other module imports the
`schema_loader` singleton for field definitions, synonym lists, and
confidence thresholds.
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

__version__ = "ldr-1.0.0"

logger = logging.getLogger(__name__)

_SCHEMA_PATH = Path(__file__).parent.parent.parent / "config" / "field_schema.yaml"


@dataclass
class FieldDefinition:
    """Single field from the canonical schema."""

    canonical_name: str
    data_type: str
    required: str                          # required_cross_document | required | optional | derived
    synonyms: List[str]
    source_authority: str
    sections: List[str]
    required_for_review: bool = False
    allowed_values: List[str] = field(default_factory=list)
    value_range: Dict[str, Any] = field(default_factory=dict)
    notes: str = ""
    # SHALqc-CORE §1: explicit XML-vs-PDF ownership override from field_schema.yaml.
    # Empty ⇒ inferred (see primary_source/secondary_source below).
    primary_source_override: str = ""
    secondary_source_override: str = ""

    @property
    def all_labels(self) -> List[str]:
        return [self.canonical_name] + self.synonyms

    # SHALqc-CORE §1 field ownership — which extractor owns this field's value.
    # Inferred (overridable): engagement-authority → engagement; contract → contract;
    # a narrative/exhibit string on the report → PDF (XML truncates prose); every
    # other report field → XML (MISMO carries it natively at 0.97).
    @property
    def _is_narrative(self) -> bool:
        if self.data_type not in ("string", "string_list"):
            return False
        name = self.canonical_name.lower()
        return any(k in name for k in (
            "comment", "description", "summary", "narrative", "commentary",
            "analysis", "remarks", "explanation"))

    @property
    def primary_source(self) -> str:
        if self.primary_source_override:
            return self.primary_source_override
        if self.source_authority == "engagement_letter":
            return "engagement"
        if self.source_authority == "sales_contract":
            return "contract"
        return "pdf" if self._is_narrative else "xml"

    @property
    def secondary_source(self) -> str:
        if self.secondary_source_override:
            return self.secondary_source_override
        primary = self.primary_source
        if primary == "xml":
            return "pdf"
        if primary == "pdf":
            return "xml"
        return "pdf"

    def matches_label(self, label: str) -> bool:
        normalized = label.strip().lower()
        return any(s.lower() == normalized for s in self.all_labels)


@dataclass
class ConfidenceThresholds:
    auto_accept: float = 0.90
    review: float = 0.70
    reject: float = 0.30


class SchemaLoader:
    """
    Thread-safe loader for field_schema.yaml.

    Usage:
        from app.extraction.schema import schema_loader
        defn = schema_loader.get_field("property_address")
        thresholds = schema_loader.thresholds_for("contract_price")
    """

    def __init__(self, path: Path = _SCHEMA_PATH) -> None:
        self._path = path
        self._lock = threading.RLock()
        self._raw: Dict[str, Any] = {}
        self._fields: Dict[str, FieldDefinition] = {}
        self._alias_map: Dict[str, str] = {}   # lower(synonym) -> canonical_name
        self._thresholds: Dict[str, ConfidenceThresholds] = {}
        self._method_confidence: Dict[str, float] = {}
        self.reload()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def reload(self) -> None:
        """Re-read the YAML from disk. Thread-safe."""
        with self._lock:
            raw = yaml.safe_load(self._path.read_text(encoding="utf-8")) or {}
            self._raw = raw
            self._build_fields(raw.get("fields", {}))
            self._build_thresholds(raw.get("confidence_thresholds", {}))
            logger.info("Field schema loaded: %d fields from %s (%s)",
                        len(self._fields), self._path.name, self.schema_version)

    def get_field(self, name: str) -> Optional[FieldDefinition]:
        """Look up by canonical name or any synonym (case-insensitive)."""
        with self._lock:
            canonical = self._alias_map.get(name.strip().lower(), name.strip())
            return self._fields.get(canonical)

    def canonical_name(self, label: str) -> Optional[str]:
        with self._lock:
            return self._alias_map.get(label.strip().lower())

    def all_fields(self) -> List[FieldDefinition]:
        with self._lock:
            return list(self._fields.values())

    def fields_for_section(self, section: str) -> List[FieldDefinition]:
        with self._lock:
            return [f for f in self._fields.values() if section in f.sections]

    def thresholds_for(self, canonical: str) -> ConfidenceThresholds:
        with self._lock:
            return self._thresholds.get(canonical, self._thresholds["__default__"])

    @property
    def document_types(self) -> Dict[str, Any]:
        with self._lock:
            return dict(self._raw.get("document_types", {}))

    @property
    def schema_version(self) -> str:
        with self._lock:
            return self._raw.get("meta", {}).get("schema_version", "unknown")

    # ------------------------------------------------------------------
    # Internal builders
    # ------------------------------------------------------------------

    def _build_fields(self, raw_fields: Dict[str, Any]) -> None:
        fields: Dict[str, FieldDefinition] = {}
        alias_map: Dict[str, str] = {}

        for key, defn in raw_fields.items():
            if not isinstance(defn, dict):
                continue
            canonical = defn.get("canonical_name", key)
            synonyms = defn.get("synonyms", [])
            allowed = defn.get("allowed_values", [])

            flat_allowed: List[str] = []
            for item in allowed:
                if isinstance(item, str):
                    flat_allowed.extend([v.strip() for v in item.split(",") if v.strip()])
                elif isinstance(item, list):
                    flat_allowed.extend(item)

            fdef = FieldDefinition(
                canonical_name=canonical,
                data_type=defn.get("data_type", "string"),
                required=defn.get("required", "optional"),
                synonyms=synonyms if isinstance(synonyms, list) else [],
                source_authority=defn.get("source_authority", "appraisal_report"),
                sections=defn.get("sections", []),
                required_for_review=defn.get("required_for_review", False),
                allowed_values=flat_allowed,
                value_range=defn.get("value_range", {}),
                notes=defn.get("notes", ""),
                primary_source_override=defn.get("primary_source", ""),
                secondary_source_override=defn.get("secondary_source", ""),
            )
            fields[canonical] = fdef
            alias_map[canonical.lower()] = canonical
            for syn in fdef.synonyms:
                alias_map[syn.strip().lower()] = canonical

        self._fields = fields
        self._alias_map = alias_map

    def _build_thresholds(self, raw: Dict[str, Any]) -> None:
        defaults = raw.get("defaults", {})
        default_t = ConfidenceThresholds(
            auto_accept=defaults.get("auto_accept", 0.90),
            review=defaults.get("review", 0.70),
            reject=defaults.get("reject", 0.30),
        )
        thresholds: Dict[str, ConfidenceThresholds] = {"__default__": default_t}
        for field_name, overrides in raw.get("per_field", {}).items():
            thresholds[field_name] = ConfidenceThresholds(
                auto_accept=overrides.get("auto_accept", default_t.auto_accept),
                review=overrides.get("review", default_t.review),
                reject=overrides.get("reject", default_t.reject),
            )
        self._thresholds = thresholds

        method_conf: Dict[str, float] = {}
        for method, conf in raw.get("extraction_method_base_confidence", {}).items():
            method_conf[method] = float(conf)
        self._method_confidence = method_conf


# Singleton — import this everywhere
schema_loader = SchemaLoader()
