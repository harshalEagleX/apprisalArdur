"""
Photo-presence detector — caption-based (deterministic).

Required-photo QC rules (front / rear / street / 4-side for FHA / interior
rooms) only need to know which photos are PRESENT. The TOTAL photo-addendum
pages caption each image ("Subject Front", "Subject Rear", "Street Scene",
"Kitchen", ...), and those captions are extractable text — so presence is read
from caption phrases rather than a slow vision model. Findings are advisory
(VERIFY): a reviewer confirms.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Set

import fitz

logger = logging.getLogger(__name__)

_FRONT = ("subject front", "front view", "front of subject", "front of the subject")
_REAR = ("subject rear", "rear view", "rear of subject", "rear of the subject")
_STREET = ("street scene", "subject street", "street view")
_LEFT = ("left side", "left exterior", "side (left", "left view")
_RIGHT = ("right side", "right exterior", "side (right", "right view")
_INTERIOR = {
    "kitchen": ("kitchen",),
    "living": ("living room", "living area", "family room", "great room"),
    "dining": ("dining",),
    "bedroom": ("bedroom",),
    "bathroom": ("bathroom", "bath "),
}


@dataclass
class PhotoPresence:
    has_front: bool = False
    has_rear: bool = False
    has_street: bool = False
    has_left: bool = False
    has_right: bool = False
    interior_rooms: Set[str] = field(default_factory=set)


def _any(text: str, phrases) -> bool:
    return any(p in text for p in phrases)


def detect_photos(pdf_path) -> PhotoPresence:
    pdf_path = Path(pdf_path)
    try:
        doc = fitz.open(str(pdf_path))
        text = " ".join(doc[i].get_text("text") for i in range(len(doc))).lower()
        doc.close()
    except Exception as exc:
        logger.warning("Photo detector could not read %s: %s", pdf_path, exc)
        return PhotoPresence()
    p = PhotoPresence(
        has_front=_any(text, _FRONT),
        has_rear=_any(text, _REAR),
        has_street=_any(text, _STREET),
        has_left=_any(text, _LEFT),
        has_right=_any(text, _RIGHT),
    )
    for room, phrases in _INTERIOR.items():
        if _any(text, phrases):
            p.interior_rooms.add(room)
    return p
