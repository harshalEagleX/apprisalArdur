"""
extraction.acroform (acr-1.0.0) — SHALqc-CORE §10 AcroForm layer.

Runs before the template/PDF pass. If the appraisal PDF has embedded form
widgets (PyMuPDF `doc.is_form_pdf` / widget walk), every widget is harvested as
`{field_name, value, page, widget_rect}` and mapped to the canonical schema via
a name-alias table. Confidence 0.95, and the widget rect IS the bbox — so these
fields are `location_quality: exact` for free (no back-locator needed). When
AcroForm covers a field the template/PDF read still runs as the second witness;
merge arbitrates as usual.

Most production appraisal PDFs are flattened (no widgets), so this is a no-op
that costs ~nothing; when it DOES hit, the payoff (exact boxes, 0.95 conf) is
outsized (CORE §10).
"""

from __future__ import annotations

import logging
import re
from typing import Dict, List, Optional

from app.extraction.result import ExtractedField, ExtractedFieldSet, Source

__version__ = "acr-1.0.0"

logger = logging.getLogger(__name__)

# widget field-name (normalized) → canonical schema field. Vendor widget names
# vary; this covers the common UAD widget names. Unmapped widgets are skipped
# (never guessed into a wrong field). Extend via config/template_positions.yaml's
# alias table later (CORE §10) — kept inline here for the first cut.
_NAME_ALIAS: Dict[str, str] = {
    "borrower": "borrower_name", "borrowername": "borrower_name",
    "propertyaddress": "property_address", "address": "property_address",
    "city": "city", "state": "state", "zipcode": "zip_code", "zip": "zip_code",
    "county": "county", "lender": "lender_name", "lenderclient": "lender_name",
    "apn": "apn", "parcelnumber": "apn", "legaldescription": "legal_description",
    "taxyear": "tax_year", "retaxes": "real_estate_taxes",
    "censustract": "census_tract", "neighborhoodname": "neighborhood_name",
    "occupant": "occupant_status", "yearbuilt": "year_built",
    "appraisedvalue": "appraised_value", "effectivedate": "effective_date",
    "appraisername": "appraiser_name",
}


def _norm_name(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", (name or "").lower())


def _canonical(widget_name: str) -> Optional[str]:
    # prefer the template map's alias table (CORE §10 single source); fall back
    # to the inline defaults so acroform works even without the template file.
    try:
        from app.extraction.template_positions import acroform_aliases
        table = {**_NAME_ALIAS, **acroform_aliases()}
    except Exception:
        table = _NAME_ALIAS
    return table.get(_norm_name(widget_name))


def extract_acroform(pdf_path) -> ExtractedFieldSet:
    """Harvest embedded form widgets → canonical ExtractedFieldSet (bbox=widget
    rect, conf 0.95, location_quality exact). Empty set when the PDF is flat."""
    fs = ExtractedFieldSet()
    try:
        import fitz
        doc = fitz.open(str(pdf_path))
    except Exception as exc:
        logger.warning("acroform: cannot open %s: %s", pdf_path, exc)
        return fs

    try:
        if not getattr(doc, "is_form_pdf", False):
            return fs
        count = 0
        for page_idx in range(len(doc)):
            page = doc[page_idx]
            for w in (page.widgets() or []):
                value = (w.field_value or "").strip() if isinstance(w.field_value, str) else w.field_value
                canonical = _canonical(w.field_name or "")
                if not canonical or value in (None, ""):
                    continue
                r = w.rect
                pw, ph = float(page.rect.width), float(page.rect.height)
                bbox = {"x": round(r.x0 / pw, 5), "y": round(r.y0 / ph, 5),
                        "w": round((r.x1 - r.x0) / pw, 5), "h": round((r.y1 - r.y0) / ph, 5)}
                fs.add(ExtractedField(
                    canonical_name=canonical, value=str(value), raw_value=str(value),
                    source=Source.ACROFORM, confidence=0.95, page=page_idx + 1,
                    bbox=bbox, location_quality="exact"))
                count += 1
        if count:
            logger.info("acroform: harvested %d widget field(s) from %s", count, pdf_path)
    finally:
        doc.close()
    return fs
