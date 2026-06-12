"""
Neighborhood / Site / Improvements rule upgrades — unit coverage.

Covers the MIRA-spec behaviors: trend splits + MCA consistency, range and
predominant checks, land-use Other cascade, boundary abbreviation/map-only,
site dimensions/shape/view/unit logic, FEMA data completeness, adverse
cascades, general-description completeness, effective-age consistency, and
the condition-vs-grid cross-match.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.qc.context import QCContext
from app.qc.result import RuleStatus


from tests.rule_helpers import as_list as _list
from tests.rule_helpers import by_template as _by_template
from tests.rule_helpers import rs as _rs
from tests.rule_helpers import statuses as _statuses


class TestN1N2:
    def test_builtup_landuse_contradiction(self):
        from app.qc.rules.neighborhood import n1_characteristics
        ctx = QCContext("t", appraisal=_rs(location="Suburban", built_up="Under 25%",
                                           growth_rate="Stable", land_use_one_unit="90"))
        hits = _by_template(n1_characteristics(ctx), "N-1-landuse-x")
        assert hits and hits[0].status == RuleStatus.VERIFY

    def test_builtup_consistent_quiet(self):
        from app.qc.rules.neighborhood import n1_characteristics
        ctx = QCContext("t", appraisal=_rs(location="Suburban", built_up="Over 75%",
                                           growth_rate="Stable", land_use_one_unit="90"))
        assert not _by_template(n1_characteristics(ctx), "N-1-landuse-x")

    def test_mca_trend_inconsistency(self):
        from app.qc.rules.neighborhood import n2_trends
        ctx = QCContext("t", appraisal=_rs(property_values="Increasing",
                                           demand_supply="Shortage",
                                           marketing_time="Under 3 mths",
                                           mca_trend_median_sale_price="Declining"))
        hits = _by_template(n2_trends(ctx), "N-2-mca")
        assert hits and hits[0].status == RuleStatus.VERIFY


class TestN3:
    def test_predominant_outside_range(self):
        from app.qc.rules.neighborhood import n3_range
        ctx = QCContext("t", appraisal=_rs(price_low="300", price_high="500",
                                           predominant_price="600"))
        assert _by_template(n3_range(ctx), "N-3-predominant")

    def test_comp_price_outside_range(self):
        from app.qc.rules.neighborhood import n3_range
        ctx = QCContext("t", appraisal=_rs(price_low="300", price_high="400",
                                           comp_1_sale_price="550000"))
        assert _by_template(n3_range(ctx), "N-3-comprange")

    def test_value_vs_predominant_band(self):
        from app.qc.rules.neighborhood import n3_range
        ctx = QCContext("t", appraisal=_rs(price_low="300", price_high="500",
                                           predominant_price="400",
                                           appraised_value="500000"))
        assert _by_template(n3_range(ctx), "N-3-valuepred")


class TestN4N5:
    def test_other_landuse_needs_description(self):
        from app.qc.rules.neighborhood import n4_landuse
        ctx = QCContext("t", appraisal=_rs(land_use_one_unit="90", land_use_other="10"))
        assert _by_template(n4_landuse(ctx), "N-4-other")

    def test_map_only_boundaries_fail(self):
        from app.qc.rules.neighborhood import n5_boundaries
        ctx = QCContext("t", appraisal=_rs(neighborhood_boundaries="See location map."))
        assert n5_boundaries(ctx).status == RuleStatus.FAIL

    def test_single_letter_directions_verify(self):
        from app.qc.rules.neighborhood import n5_boundaries
        ctx = QCContext("t", appraisal=_rs(
            neighborhood_boundaries="N: FM 1093; S: Bay Hill Blvd; E: Katy Fwy; W: FM 1463"))
        r = n5_boundaries(ctx)
        assert r.status == RuleStatus.VERIFY and r.template_id == "N-5-abbrev"


class TestSite:
    def test_dimensions_format_pass(self):
        from app.qc.rules.site import st1_dimensions
        ctx = QCContext("t", appraisal=_rs(site_dimensions="50 x 100"))
        assert st1_dimensions(ctx).status == RuleStatus.PASS

    def test_irregular_dimensions_verify(self):
        from app.qc.rules.site import st1_dimensions
        ctx = QCContext("t", appraisal=_rs(site_dimensions="Irregular"))
        assert st1_dimensions(ctx).status == RuleStatus.VERIFY

    def test_large_sf_should_be_acres(self):
        from app.qc.rules.site import st2_area
        ctx = QCContext("t", appraisal=_rs(site_area="87,120", site_area_unit="sf"))
        r = st2_area(ctx)
        assert r.status == RuleStatus.VERIFY and r.template_id == "ST-2-area"

    def test_small_sf_pass(self):
        from app.qc.rules.site import st2_area
        ctx = QCContext("t", appraisal=_rs(site_area="6,307", site_area_unit="sf"))
        assert st2_area(ctx).status == RuleStatus.PASS

    def test_view_uad_format_pass(self):
        from app.qc.rules.site import st4_view
        ctx = QCContext("t", appraisal=_rs(site_view="N;Res"))
        assert RuleStatus.PASS in _statuses(st4_view(ctx))

    def test_view_grid_mismatch(self):
        from app.qc.rules.site import st4_view
        ctx = QCContext("t", appraisal=_rs(site_view="N;Res", subject_grid_view="B;Wtr"))
        assert _by_template(st4_view(ctx), "ST-4-grid")

    def test_private_septic_cascade(self):
        from app.qc.rules.site import st7_utilities
        ctx = QCContext("t", appraisal=_rs(utilities_electricity="Public",
                                           utilities_gas="Public",
                                           utilities_sewer="Private septic"))
        assert _by_template(st7_utilities(ctx), "ST-7-wellseptic")

    def test_fema_data_incomplete(self):
        from app.qc.rules.site import st8_flood
        ctx = QCContext("t", appraisal=_rs(fema_flood_hazard="No"))
        assert _by_template(st8_flood(ctx), "ST-8-femadata")

    def test_adverse_yes_verifies(self):
        from app.qc.rules.site import st10_adverse
        ctx = QCContext("t", appraisal=_rs(adverse_site_conditions="Yes"))
        r = st10_adverse(ctx)
        assert r.status == RuleStatus.VERIFY and r.template_id == "ST-10-adverse"

    def test_adverse_no_passes(self):
        from app.qc.rules.site import st10_adverse
        ctx = QCContext("t", appraisal=_rs(adverse_site_conditions="No"))
        assert st10_adverse(ctx).status == RuleStatus.PASS


class TestImprovements:
    def test_partial_general_description_names_missing(self):
        from app.qc.rules.improvements import i1_general
        ctx = QCContext("t", appraisal=_rs(design_style="DT2;Traditional",
                                           year_built="2012", stories="2",
                                           units_count="1"))
        hits = _by_template(i1_general(ctx), "I-1-fields")
        assert hits and "Effective Age" in hits[0].message

    def test_effective_age_exceeds_actual_fails(self):
        from app.qc.rules.improvements import i1_general
        ctx = QCContext("t", appraisal=_rs(design_style="Traditional", year_built="2012",
                                           stories="2", units_count="1",
                                           dwelling_type="Det", effective_age="30",
                                           effective_date="03/15/2026"))
        hits = _by_template(i1_general(ctx), "I-1-age")
        assert hits and hits[0].status == RuleStatus.FAIL

    def test_condition_grid_mismatch_fails(self):
        from app.qc.rules.improvements import i9_condition
        ctx = QCContext("t", appraisal=_rs(condition_rating="C3",
                                           subject_grid_condition_rating="C4"))
        hits = _by_template(i9_condition(ctx), "I-9-grid")
        assert hits and hits[0].status == RuleStatus.FAIL

    def test_good_condition_effage_equal_actual_verifies(self):
        from app.qc.rules.improvements import i9_condition
        ctx = QCContext("t", appraisal=_rs(condition_rating="C3", year_built="2000",
                                           effective_age="26",
                                           effective_date="03/15/2026"))
        assert _by_template(i9_condition(ctx), "I-9-effage")

    def test_addition_keyword_verifies(self):
        from app.qc.rules.improvements import i12_additions
        ctx = QCContext("t", appraisal=_rs(
            sales_comparison_summary="The subject features a converted garage used as a bonus room."))
        assert i12_additions(ctx).status == RuleStatus.VERIFY

    def test_no_addition_passes(self):
        from app.qc.rules.improvements import i12_additions
        ctx = QCContext("t", appraisal=_rs(
            sales_comparison_summary="All comparables are similar in quality and condition."))
        assert i12_additions(ctx).status == RuleStatus.PASS


class TestSiteFormGate:
    def test_condo_form_skips_dimensions(self):
        from app.qc.rules.site import _has_site_detail
        ctx = QCContext("t", appraisal=_rs(form_type="1073 condo"))
        assert not _has_site_detail(ctx)

    def test_1004_form_checks_dimensions(self):
        from app.qc.rules.site import _has_site_detail
        ctx = QCContext("t", appraisal=_rs(form_type="1004"))
        assert _has_site_detail(ctx)
