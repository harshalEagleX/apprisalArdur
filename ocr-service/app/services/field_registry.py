"""
Canonical OCR field registry.

This is the product contract for extractable fields. Extraction code may use
different mechanics (spatial anchors, regex, value-stream parsing, LLM
fallbacks), but field ownership, normalization, validation, and confidence
semantics should be declared here rather than scattered across endpoints.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Dict, Iterable, Optional

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class FieldDefinition:
    name: str
    section: str
    owner: str
    extraction_strategy: str
    normalization: str = "string_trim"
    validation: str = "optional"
    confidence_model: str = "method_raw_then_reviewer_calibrated"
    aliases: tuple[str, ...] = field(default_factory=tuple)
    required_for_review: bool = False


class FieldRegistry:
    def __init__(self, definitions: Iterable[FieldDefinition]):
        self._by_name: Dict[str, FieldDefinition] = {definition.name: definition for definition in definitions}
        self._aliases: Dict[str, str] = {}
        for definition in definitions:
            for alias in definition.aliases:
                self._aliases[alias] = definition.name

    def get(self, field_name: str) -> Optional[FieldDefinition]:
        canonical = self.canonical_name(field_name)
        return self._by_name.get(canonical)

    def canonical_name(self, field_name: Optional[str]) -> str:
        if not field_name:
            return ""
        normalized = field_name.strip()
        return self._aliases.get(normalized, normalized)

    def known(self, field_name: Optional[str]) -> bool:
        return self.get(field_name) is not None

    def validate_meta(self, section: str, field_names: Iterable[str]) -> None:
        """Log unknown fields so new extraction logic gets registered explicitly."""
        unknown = sorted({
            field_name for field_name in field_names
            if field_name and not self.known(field_name)
        })
        if unknown:
            logger.info(
                "Unregistered OCR field(s) emitted",
                extra={"section": section, "fields": unknown},
            )

    def names_for_section(self, section: str) -> list[str]:
        return sorted(
            name for name, definition in self._by_name.items()
            if definition.section == section
        )


def _field(
    name: str,
    section: str,
    extraction_strategy: str,
    *,
    normalization: str = "string_trim",
    validation: str = "optional",
    owner: str = "phase2_extraction",
    confidence_model: str = "method_raw_then_reviewer_calibrated",
    aliases: tuple[str, ...] = (),
    required_for_review: bool = False,
) -> FieldDefinition:
    return FieldDefinition(
        name=name,
        section=section,
        owner=owner,
        extraction_strategy=extraction_strategy,
        normalization=normalization,
        validation=validation,
        confidence_model=confidence_model,
        aliases=aliases,
        required_for_review=required_for_review,
    )


FIELD_DEFINITIONS: tuple[FieldDefinition, ...] = (
    _field("property_address", "subject", "spatial_anchor_or_value_stream", validation="required_cross_document", aliases=("propertyAddress",), required_for_review=True),
    _field("city", "subject", "address_parser", validation="required_cross_document", required_for_review=True),
    _field("state", "subject", "address_parser", normalization="state_code", validation="required_cross_document", required_for_review=True),
    _field("zip_code", "subject", "address_parser", normalization="zip5", validation="required_cross_document", required_for_review=True),
    _field("county", "subject", "spatial_anchor_or_regex"),
    _field("borrower_name", "subject", "spatial_anchor_or_regex", validation="required_cross_document", aliases=("borrowerName",), required_for_review=True),
    _field("co_borrower_name", "subject", "spatial_anchor_or_regex", aliases=("coBorrowerName",)),
    _field("owner_of_public_record", "subject", "spatial_anchor_or_regex"),
    _field("legal_description", "subject", "spatial_anchor_or_regex"),
    _field("assessors_parcel_number", "subject", "spatial_anchor_or_regex", aliases=("apn",)),
    _field("tax_year", "subject", "spatial_anchor_or_regex", normalization="year"),
    _field("real_estate_taxes", "subject", "spatial_anchor_or_regex", normalization="money"),
    _field("neighborhood_name", "subject", "spatial_anchor_or_regex"),
    _field("map_reference", "subject", "spatial_anchor_or_regex"),
    _field("census_tract", "subject", "spatial_anchor_or_regex", normalization="census_tract"),
    _field("occupant_status", "subject", "checkbox_or_regex"),
    _field("special_assessments", "subject", "spatial_anchor_or_regex", normalization="money"),
    _field("hoa_dues", "subject", "spatial_anchor_or_regex", normalization="money"),
    _field("hoa_period", "subject", "spatial_anchor_or_regex"),
    _field("is_pud_checked", "subject", "checkbox_or_vision", normalization="boolean"),
    _field("lender_name", "subject", "spatial_anchor_or_regex", validation="required_cross_document", required_for_review=True),
    _field("lender_address", "subject", "spatial_anchor_or_regex"),
    _field("property_rights", "subject", "checkbox_or_regex"),
    _field("offered_for_sale_12mo", "subject", "checkbox_or_vision", normalization="boolean"),
    _field("data_source", "subject", "regex"),
    _field("mls_number", "subject", "regex"),
    _field("market_value_opinion", "subject", "regex", normalization="money"),
    _field("condition_rating", "subject", "regex", normalization="uad_condition"),
    _field("quality_rating", "subject", "regex", normalization="uad_quality"),

    _field("location", "neighborhood", "checkbox_or_context"),
    _field("built_up", "neighborhood", "checkbox_or_context"),
    _field("growth_rate", "neighborhood", "checkbox_or_context"),
    _field("property_values", "neighborhood", "checkbox_or_context"),
    _field("demand_supply", "neighborhood", "checkbox_or_context"),
    _field("marketing_time", "neighborhood", "checkbox_or_context"),
    _field("price_low", "neighborhood", "grid_or_value_stream", normalization="money"),
    _field("price_high", "neighborhood", "grid_or_value_stream", normalization="money"),
    _field("predominant_price", "neighborhood", "grid_or_value_stream", normalization="money"),
    _field("age_low", "neighborhood", "grid_or_value_stream", normalization="integer"),
    _field("age_high", "neighborhood", "grid_or_value_stream", normalization="integer"),
    _field("predominant_age", "neighborhood", "grid_or_value_stream", normalization="integer"),
    _field("land_use_one_unit", "neighborhood", "grid_or_value_stream", normalization="percent"),
    _field("land_use_2_4_unit", "neighborhood", "grid_or_value_stream", normalization="percent"),
    _field("land_use_multi_family", "neighborhood", "grid_or_value_stream", normalization="percent"),
    _field("land_use_commercial", "neighborhood", "grid_or_value_stream", normalization="percent"),
    _field("land_use_other", "neighborhood", "grid_or_value_stream", normalization="percent"),
    _field("land_use_total", "neighborhood", "derived_sum", normalization="percent"),
    _field("neighborhood_boundaries", "neighborhood", "text_block"),
    _field("neighborhood_description", "neighborhood", "text_block"),
    _field("market_conditions_commentary", "neighborhood", "text_block_or_llm"),

    _field("site_dimensions", "site", "value_stream_or_regex", owner="phase2_extraction_and_site_extractor", aliases=("siteDimensions",)),
    _field("site_area", "site", "value_stream_or_regex", normalization="area", owner="phase2_extraction_and_site_extractor", aliases=("siteArea",)),
    _field("site_area_unit", "site", "value_stream_or_regex", owner="phase2_extraction_and_site_extractor", aliases=("siteAreaUnit",)),
    _field("site_shape", "site", "value_stream_or_regex", owner="phase2_extraction_and_site_extractor"),
    _field("site_view", "site", "value_stream_or_regex", owner="phase2_extraction_and_site_extractor"),
    _field("zoning_compliance", "site", "regex", owner="site_extractor", aliases=("zoningCompliance",)),
    _field("highest_and_best_use", "site", "regex", normalization="boolean", owner="site_extractor", aliases=("highestAndBestUse",)),
    _field("design_style", "improvements", "regex", owner="site_extractor", aliases=("designStyle",)),
    _field("year_built", "improvements", "regex", normalization="year", owner="site_extractor", aliases=("yearBuilt",)),
    _field("comparable_count", "sales_comparison", "regex_count", normalization="integer", owner="site_extractor", aliases=("comparableCount",)),

    _field("assignment_type", "contract", "checkbox_or_regex", owner="extraction_service"),
    _field("did_analyze_contract", "contract", "checkbox_or_regex", normalization="boolean", owner="extraction_service"),
    _field("sale_type", "contract", "checkbox_or_regex", owner="extraction_service"),
    _field("contract_analysis_comment", "contract", "text_block", owner="extraction_service"),
    _field("contract_price", "contract", "regex", normalization="money", owner="extraction_service"),
    _field("contract_date", "contract", "regex", normalization="date", owner="extraction_service"),
    _field("is_seller_owner_of_record", "contract", "checkbox_or_regex", normalization="boolean", owner="extraction_service"),
    _field("owner_record_data_source", "contract", "regex", owner="extraction_service"),
    _field("has_financial_assistance", "contract", "checkbox_or_regex", normalization="boolean", owner="extraction_service"),
    _field("financial_assistance_amount", "contract", "regex", normalization="money", owner="extraction_service"),
    _field("financial_assistance_description", "contract", "text_block", owner="extraction_service"),
    _field("personal_property_items", "contract", "regex_list", owner="extraction_service"),
    _field("personal_property_contributes_to_value", "contract", "checkbox_or_regex", normalization="boolean", owner="extraction_service"),
    _field("seller_concessions", "contract", "regex", normalization="money", owner="extraction_service"),
    _field("loan_type", "engagement", "regex", owner="extraction_service"),
    _field("seller_name", "engagement", "regex", owner="extraction_service"),
    _field("concessions_amount", "engagement", "regex", normalization="money", owner="extraction_service"),
)


field_registry = FieldRegistry(FIELD_DEFINITIONS)
