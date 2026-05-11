"""Deterministic entity normalization and matching for cross-document QC."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from difflib import SequenceMatcher


_STREET_SUFFIXES = {
    "road": "rd",
    "rd": "rd",
    "street": "st",
    "st": "st",
    "avenue": "ave",
    "ave": "ave",
    "circle": "cir",
    "cir": "cir",
    "court": "ct",
    "ct": "ct",
    "drive": "dr",
    "dr": "dr",
    "lane": "ln",
    "ln": "ln",
    "boulevard": "blvd",
    "blvd": "blvd",
    "highway": "hwy",
    "hwy": "hwy",
    "trace": "trce",
    "tr": "trce",
}

_DIRECTIONS = {
    "north": "n",
    "south": "s",
    "east": "e",
    "west": "w",
    "northeast": "ne",
    "northwest": "nw",
    "southeast": "se",
    "southwest": "sw",
    "n": "n",
    "s": "s",
    "e": "e",
    "w": "w",
    "ne": "ne",
    "nw": "nw",
    "se": "se",
    "sw": "sw",
}


@dataclass
class AddressEntity:
    raw: str
    canonical: str
    house_number: str | None
    tokens: list[str]
    directional_tokens: list[str] = field(default_factory=list)
    directional_positions: list[int] = field(default_factory=list)


@dataclass
class EntityMatch:
    same_entity: bool
    status: str
    confidence: float
    reasons: list[str] = field(default_factory=list)


def build_address_entity(value: str | None) -> AddressEntity | None:
    if not value or not str(value).strip():
        return None
    raw = str(value).strip()
    cleaned = re.sub(r"[,#]", " ", raw.lower())
    cleaned = re.sub(r"\b(?:city|state|zip|county)\b", " ", cleaned)
    parts = re.findall(r"[a-z0-9]+", cleaned)
    normalized: list[str] = []
    directions: list[str] = []
    direction_positions: list[int] = []
    for part in parts:
        token = _DIRECTIONS.get(part, _STREET_SUFFIXES.get(part, part))
        if token in _DIRECTIONS.values():
            directions.append(token)
            direction_positions.append(len(normalized))
        normalized.append(token)
    house_number = next((p for p in normalized if p.isdigit()), None)
    return AddressEntity(
        raw=raw,
        canonical=" ".join(normalized),
        house_number=house_number,
        tokens=normalized,
        directional_tokens=directions,
        directional_positions=direction_positions,
    )


def match_addresses(left: str | None, right: str | None) -> EntityMatch:
    left_entity = build_address_entity(left)
    right_entity = build_address_entity(right)
    if not left_entity or not right_entity:
        return EntityMatch(False, "EXTRACTION_FAILED", 0.0, ["address_entity_missing"])

    reasons: list[str] = []
    if left_entity.house_number != right_entity.house_number:
        return EntityMatch(False, "CROSS_DOC_MISMATCH", 0.0, ["house_number_mismatch"])

    left_core = [t for t in left_entity.tokens if t not in _DIRECTIONS.values()]
    right_core = [t for t in right_entity.tokens if t not in _DIRECTIONS.values()]
    overlap = len(set(left_core) & set(right_core)) / max(1, len(set(left_core) | set(right_core)))
    sequence = SequenceMatcher(None, left_entity.canonical, right_entity.canonical).ratio()

    if set(left_entity.directional_tokens) != set(right_entity.directional_tokens):
        reasons.append("directional_variant")
    if left_entity.directional_positions != right_entity.directional_positions:
        reasons.append("directional_order_differs")

    confidence = round((overlap * 0.65) + (sequence * 0.35), 3)
    if confidence >= 0.92 and "directional_order_differs" not in reasons:
        return EntityMatch(True, "MATCH", confidence, reasons)
    if confidence >= 0.82:
        return EntityMatch(True, "REVIEW", confidence, reasons or ["probable_match_requires_review"])
    return EntityMatch(False, "CROSS_DOC_MISMATCH", confidence, reasons or ["low_address_similarity"])


def normalize_person_name(value: str | None) -> str:
    if not value:
        return ""
    return " ".join(re.findall(r"[a-z]+", value.lower()))
