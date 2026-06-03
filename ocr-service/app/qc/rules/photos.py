"""
Photograph rules (PH-1, PH-2, FHA-9 / checklist 124-126).

Read the photo-presence pseudo-fields produced by the transaction photo overlay
(caption detection). All findings are VERIFY (advisory) — caption text can miss
an unlabeled photo, so a reviewer confirms. Phase 6.
"""

from __future__ import annotations

from app.qc.config import qc_config
from app.qc.context import QCContext
from app.qc.registry import rule
from app.qc.result import RuleResult, RuleStatus


def _true(ctx, field) -> bool:
    return str(ctx.appraisal.value(field) or "").lower() == "true"


# ---- PH-1 subject front / rear / street required --------------------------

@rule(id="PH-1", num="124", section="photos", phase=6, name="Subject front/rear/street photos")
def ph1_subject(ctx: QCContext):
    missing = []
    if not _true(ctx, "photo_front"):
        missing.append("front")
    if not _true(ctx, "photo_rear"):
        missing.append("rear")
    if not _true(ctx, "photo_street"):
        missing.append("street scene")
    ev = [ctx.appraisal.evidence("photo_front"), ctx.appraisal.evidence("photo_rear"),
          ctx.appraisal.evidence("photo_street")]
    if not missing:
        return RuleResult(rule_id="PH-1", checklist_num="124", section="photos",
                          status=RuleStatus.PASS,
                          fields_involved=["photo_front", "photo_rear", "photo_street"], evidence=ev)
    return RuleResult(rule_id="PH-1", checklist_num="124", section="photos",
                      status=RuleStatus.VERIFY,
                      message=qc_config.template("PH-1-missing", which=", ".join(missing)),
                      fields_involved=["photo_front", "photo_rear", "photo_street"],
                      template_id="PH-1-missing", evidence=ev, confidence=0.6)


# ---- PH-2 interior photos (kitchen, living, bedroom, bath) -----------------

_REQUIRED_INTERIOR = ["kitchen", "living", "bedroom", "bathroom"]


@rule(id="PH-2", num="125", section="photos", phase=6, name="Interior photos present")
def ph2_interior(ctx: QCContext):
    rooms = set((ctx.appraisal.value("photo_interior_rooms") or "").split(","))
    missing = [r for r in _REQUIRED_INTERIOR if r not in rooms]
    ev = [ctx.appraisal.evidence("photo_interior_rooms")]
    if not missing:
        return RuleResult(rule_id="PH-2", checklist_num="125", section="photos",
                          status=RuleStatus.PASS, fields_involved=["photo_interior_rooms"], evidence=ev)
    return RuleResult(rule_id="PH-2", checklist_num="125", section="photos",
                      status=RuleStatus.VERIFY,
                      message=qc_config.template("PH-2-interior", which=", ".join(missing)),
                      fields_involved=["photo_interior_rooms"], template_id="PH-2-interior",
                      evidence=ev, confidence=0.55)


# ---- FHA-9 four-side photos (FHA only) ------------------------------------

@rule(id="FHA-9", num="FHA", section="fha", phase=8,
      applies_when=lambda ctx: ctx.loan_type == "fha", name="FHA four-side photos")
def fha9_sides(ctx: QCContext):
    missing = []
    for side, fieldname in (("front", "photo_front"), ("rear", "photo_rear"),
                            ("left", "photo_left"), ("right", "photo_right")):
        if not _true(ctx, fieldname):
            missing.append(side)
    ev = [ctx.appraisal.evidence("photo_left"), ctx.appraisal.evidence("photo_right")]
    if not missing:
        return RuleResult(rule_id="FHA-9", checklist_num="FHA", section="fha",
                          status=RuleStatus.PASS,
                          fields_involved=["photo_left", "photo_right"], evidence=ev)
    return RuleResult(rule_id="FHA-9", checklist_num="FHA", section="fha",
                      status=RuleStatus.VERIFY,
                      message=qc_config.template("FHA-9-sides", which=", ".join(missing)),
                      fields_involved=["photo_left", "photo_right"], template_id="FHA-9-sides",
                      evidence=ev, confidence=0.6)
