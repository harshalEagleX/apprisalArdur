"""
Addendum rules (ADD-2, ADD-5, ADD-8, ADD-9 / USPAP + 1004MC content).

ADD-1 (canned language) lives in rules/commentary.py; ADD-4 (1004MC required
for FHA/USDA) lives in rules/fha_usda.py. These rules cover the 1004MC content
checks (which only fire when MCA fields were extracted) and the USPAP addendum
fields.
"""

from __future__ import annotations

import re

from app.qc.config import qc_config
from app.qc.context import QCContext
from app.qc.registry import rule
from app.qc.result import RuleStatus


from app.qc.helpers import section_result

_res = section_result("addendum")


# ---- ADD-2 comparable selection commentary explains WHY ---------------------

_SELECTION_WHY = re.compile(r"(because|due to|as they|since|represent|similar (in|to)|"
                            r"same (buyer|market)|most (similar|comparable))", re.I)


@rule(id="ADD-2", num="119", section="addendum", phase=5,
      name="Comparable selection commentary explains why")
def add2_selection(ctx: QCContext):
    text = (ctx.appraisal.value("sales_comparison_summary") or "").strip()
    ev = [ctx.appraisal.evidence("sales_comparison_summary")]
    if len(text) < 40:
        # SCA-14 already surfaces the missing-narrative case; stay quiet here
        # rather than double-flagging the same extraction gap
        return _res("ADD-2", "119", RuleStatus.NOT_APPLICABLE,
                    message="No substantive sales-comparison narrative extracted.")
    if _SELECTION_WHY.search(text):
        return _res("ADD-2", "119", RuleStatus.PASS,
                    fields=["sales_comparison_summary"], evidence=ev)
    addressed = None
    try:
        from app.extraction.llm_groq import assess_text
        addressed = assess_text(
            text, "Does this commentary EXPLAIN WHY the comparable sales were selected "
                  "(their similarity to the subject, shared buyer pool, market area) "
                  "rather than only describing what was done?")
    except Exception:
        addressed = None
    if addressed:
        return _res("ADD-2", "119", RuleStatus.PASS,
                    fields=["sales_comparison_summary"], evidence=ev)
    return _res("ADD-2", "119", RuleStatus.VERIFY,
                message=qc_config.template("ADD-2-selection"),
                fields=["sales_comparison_summary"],
                template_id="ADD-2-selection", evidence=ev, confidence=0.6)


# ---- ADD-5 1004MC inventory analysis completeness ----------------------------

# the shaded inventory cells per time period; only checked when the MCA was
# extracted at all (absence on FHA/USDA is ADD-4's finding, not ADD-5's)
_MCA_REQUIRED = {
    "mca_total_sales_prior_7_12": "Total Sales (7-12 mo)",
    "mca_total_sales_prior_4_6": "Total Sales (4-6 mo)",
    "mca_total_sales_current_3": "Total Sales (0-3 mo)",
    "mca_absorption_rate_prior_7_12": "Absorption Rate (7-12 mo)",
    "mca_absorption_rate_prior_4_6": "Absorption Rate (4-6 mo)",
    "mca_absorption_rate_current_3": "Absorption Rate (0-3 mo)",
    "mca_months_supply_prior_7_12": "Months of Supply (7-12 mo)",
    "mca_months_supply_current_3": "Months of Supply (0-3 mo)",
    "mca_median_sale_price_prior_7_12": "Median Sale Price (7-12 mo)",
    "mca_median_sale_price_current_3": "Median Sale Price (0-3 mo)",
}


def _mca_present(ctx: QCContext) -> bool:
    return any(ctx.appraisal.value(f) for f in _MCA_REQUIRED)


@rule(id="ADD-5", num="120", section="addendum", phase=4, applies_when=_mca_present,
      name="1004MC inventory analysis complete")
def add5_mca_fields(ctx: QCContext):
    missing = [label for f, label in _MCA_REQUIRED.items() if not ctx.appraisal.value(f)]
    ev = [ctx.appraisal.evidence(f) for f in list(_MCA_REQUIRED)[:4]]
    if not missing:
        return _res("ADD-5", "120", RuleStatus.PASS,
                    fields=list(_MCA_REQUIRED), evidence=ev)
    return _res("ADD-5", "120", RuleStatus.VERIFY,
                message=qc_config.template("ADD-5-fields", value=", ".join(missing[:6])),
                fields=list(_MCA_REQUIRED), template_id="ADD-5-fields",
                evidence=ev, confidence=0.6)


# ---- ADD-8 1004MC condo project section (1073 only) --------------------------

_MCA_CONDO = {
    "mca_project_total_sales_current_3": "project total sales (0-3 mo)",
    "mca_project_months_supply_current_3": "project months of supply (0-3 mo)",
    "project_name": "project name",
}


@rule(id="ADD-8", num="121", section="addendum", phase=4,
      applies_when=lambda ctx: ctx.form_type == "1073" and _mca_present(ctx),
      name="1004MC condo project section complete")
def add8_condo_mca(ctx: QCContext):
    missing = [label for f, label in _MCA_CONDO.items() if not ctx.appraisal.value(f)]
    ev = [ctx.appraisal.evidence(f) for f in _MCA_CONDO]
    if not missing:
        return _res("ADD-8", "121", RuleStatus.PASS, fields=list(_MCA_CONDO), evidence=ev)
    return _res("ADD-8", "121", RuleStatus.VERIFY,
                message=qc_config.template("ADD-8-condo", value=", ".join(missing)),
                fields=list(_MCA_CONDO), template_id="ADD-8-condo",
                evidence=ev, confidence=0.6)


# ---- ADD-9 USPAP addendum: report type / exposure time / prior services ------

_EXPOSURE_SPECIFIC = re.compile(r"\d+\s*(-|to|–)\s*\d+|\b\d+\s*(day|week|month)", re.I)


@rule(id="ADD-9", num="122", section="addendum", phase=4, name="USPAP addendum complete")
def add9_uspap(ctx: QCContext):
    out = []
    # nothing of the USPAP addendum extracted at all → ONE combined reviewer
    # ask, not a separate VERIFY per sub-field
    if not any(ctx.appraisal.value(f) for f in
               ("appraisal_report_type", "reasonable_exposure_time",
                "prior_services_performed")):
        return _res("ADD-9", "122", RuleStatus.VERIFY,
                    message="The USPAP addendum fields (report type, reasonable exposure "
                            "time, prior services) could not be extracted; manual review required.",
                    fields=["appraisal_report_type", "reasonable_exposure_time"],
                    confidence=0.5)
    # report type identification
    rtype = (ctx.appraisal.value("appraisal_report_type") or "").strip().lower()
    ev = [ctx.appraisal.evidence("appraisal_report_type")]
    if "restricted" in rtype or "appraisal report" in rtype or rtype in {"appraisal"}:
        out.append(_res("ADD-9", "122", RuleStatus.PASS,
                        fields=["appraisal_report_type"], evidence=ev))
    else:
        out.append(_res("ADD-9", "122", RuleStatus.VERIFY,
                        message=qc_config.template("ADD-9-type"),
                        fields=["appraisal_report_type"], template_id="ADD-9-type",
                        evidence=ev, confidence=0.5 if not rtype else 0.7))
    # reasonable exposure time must be specific
    exp = (ctx.appraisal.value("reasonable_exposure_time") or "").strip()
    ev = [ctx.appraisal.evidence("reasonable_exposure_time")]
    if exp and _EXPOSURE_SPECIFIC.search(exp):
        out.append(_res("ADD-9", "122", RuleStatus.PASS,
                        fields=["reasonable_exposure_time"], evidence=ev))
    else:
        out.append(_res("ADD-9", "122", RuleStatus.VERIFY,
                        message=qc_config.template("ADD-9-exposure"),
                        fields=["reasonable_exposure_time"], template_id="ADD-9-exposure",
                        evidence=ev, confidence=0.5 if not exp else 0.7))
    # prior services disclosed → must be described
    prior = (ctx.appraisal.value("prior_services_performed") or "").strip()
    low = prior.lower()
    if low and not low.startswith(("no", "false", "0", "have not")) and len(prior) < 40:
        # "HAVE performed" marked but no description of what was performed
        out.append(_res("ADD-9", "122", RuleStatus.VERIFY,
                        message=qc_config.template("ADD-9-services"),
                        fields=["prior_services_performed"], template_id="ADD-9-services",
                        evidence=[ctx.appraisal.evidence("prior_services_performed")],
                        confidence=0.6))
    return out
