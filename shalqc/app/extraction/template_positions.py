"""
extraction.template_positions (tpl-1.1.0) — SHALqc-CORE §2/§9/§10 loader.

Loads config/template_positions.yaml and exposes:
  * detect_vendor(pdf) — PDF producer/creator metadata → vendor key (§9).
  * acroform_aliases() — the widget-name → canonical map (§10).
  * field_anchor(field, vendor) — {page, anchor, region?} for a mapped field,
    vendor block deep-merged over `_default`.

Vendor-unknown falls back to `_default`; the caller widens region tolerance and
notes `vendor: unknown` on the run (§9).
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, Optional

import yaml

__version__ = "tpl-1.1.0"

logger = logging.getLogger(__name__)

_PATH = Path(__file__).parent.parent.parent / "config" / "template_positions.yaml"
_RAW: Optional[Dict[str, Any]] = None


def _load() -> Dict[str, Any]:
    global _RAW
    if _RAW is None:
        _RAW = yaml.safe_load(_PATH.read_text(encoding="utf-8")) if _PATH.exists() else {}
    return _RAW or {}


def version() -> str:
    return (_load().get("meta") or {}).get("version", "unknown")


def acroform_aliases() -> Dict[str, str]:
    return dict(_load().get("acroform_aliases") or {})


def detect_vendor(pdf_path) -> str:
    """Return the vendor key from PDF metadata, or 'unknown' (→ _default)."""
    try:
        import fitz
        doc = fitz.open(str(pdf_path))
        meta = " ".join(str(v) for v in (doc.metadata or {}).values()).lower()
        doc.close()
    except Exception:
        return "unknown"
    for vendor, needles in (_load().get("vendor_detect") or {}).items():
        if any(n in meta for n in needles):
            return vendor
    return "unknown"


def field_anchor(field: str, vendor: str = "unknown") -> Optional[Dict[str, Any]]:
    vendors = _load().get("vendors") or {}
    base = ((vendors.get("_default") or {}).get("fields") or {})
    over = ((vendors.get(vendor) or {}).get("fields") or {}) if vendor != "unknown" else {}
    entry = {**(base.get(field) or {}), **(over.get(field) or {})}
    return entry or None
