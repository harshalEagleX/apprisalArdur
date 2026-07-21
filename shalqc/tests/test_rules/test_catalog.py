"""
Catalog interpreter tests (cat-1.0.0) — the whole AMC checklist as rules.

Confirms the catalog drives rules dynamically, dedups against hand-coded ones,
never fakes a pass, and flags vision items for MANUAL review (no automated
vision, per directive).
"""

import app.rules as R
from app.rules.catalog import load_catalog, register_catalog_rules
from app.rules.registry import all_rules


def test_catalog_loaded_and_registered():
    items = load_catalog()
    assert len(items) > 100                      # the full checklist
    ids = {r.rule_id for r in all_rules()}
    # a spread of catalog sections became real rules
    assert {"SCA-2", "I-1", "N-1", "CA-1", "R-1", "SIG-1"} <= ids


def test_hand_coded_rules_not_duplicated_by_catalog():
    ids = [r.rule_id for r in all_rules()]
    # S-1 is hand-coded; the catalog must not register a second S-1
    assert ids.count("S-1") == 1
    assert ids.count("S-2") == 1


def test_registration_is_idempotent():
    before = len(all_rules())
    added = register_catalog_rules()
    assert added == 0                            # everything already registered
    assert len(all_rules()) == before


def test_no_automated_vision_rules_flag_manual():
    # cross_modal items with no XML presence flag must be MANUAL VISION, VERIFY
    from app.rules.catalog import _body_cross_modal
    body = _body_cross_modal({"rule_id": "X", "item": "Comparable photos", "check_type": "cross_modal",
                              "sources": [{"doc": "appraisal", "fields": ["comp_photo_commentary"]}]})

    class _Doc:
        def value(self, f): return None
        def evidence(self, f):
            from app.rules.verdict import Evidence
            return Evidence(field=f)

    class _Ctx:
        appraisal = _Doc()
    v = body(_Ctx())
    assert v.status.value == "VERIFY"
    assert v.degraded_reason == "manual_vision_required"
    # 2026-07-20 tone contract: soft asking language that still names the
    # photos/sketch/map scope — never a shouted "MANUAL VISION CHECK".
    assert "photos/sketch/map" in v.message
    assert "could you please" in v.message.lower()
