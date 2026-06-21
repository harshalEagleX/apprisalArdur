"""Layer-B / Layer-C shared engine (app.qc.layer_b).

Locks in the MIRA three-layer behaviour: keyword detection of whether the
narrative addresses a concern (deterministic — never LLM in tests), and severity
calibration (explained -> lower confidence; unexplained -> full). The reviewer
reasoning text is folded into the message either way.
"""

from app.qc.result import Evidence, RuleStatus
from app.qc import layer_b


class _FakeDoc:
    def __init__(self, fields):
        self._f = fields
        self.present = True

    def value(self, name):
        return self._f.get(name)

    def evidence(self, name):
        return Evidence(document="appraisal", value=self._f.get(name),
                        confidence=0.9, field=name)


class _FakeCtx:
    def __init__(self, **fields):
        self.appraisal = _FakeDoc(fields)


def test_is_explained_detects_narrative_keywords():
    ctx = _FakeCtx(sales_comparison_summary=
                   "Due to limited inventory of recent sales, the best available "
                   "comparables were used.")
    assert layer_b.is_explained(ctx, "dated_comp") is True


def test_is_explained_false_when_narrative_silent():
    ctx = _FakeCtx(sales_comparison_summary="The subject is a nice home.")
    assert layer_b.is_explained(ctx, "dated_comp") is False


def test_unknown_concern_is_not_explained():
    ctx = _FakeCtx(sales_comparison_summary="anything")
    assert layer_b.is_explained(ctx, "no_such_concern") is False


def test_assess_calibrates_severity_and_folds_reasoning():
    explained = _FakeCtx(sales_comparison_summary=
                         "An exhaustive search shows these are the best available "
                         "comparables given limited recent sales.")
    v = layer_b.assess(explained, concern="dated_comp",
                       base_message="Comp 1 sold 14 months before the effective date.",
                       facts="comp 1 is dated")
    assert v.explained is True
    assert v.confidence == 0.4                       # explained -> lower severity
    assert v.status == RuleStatus.VERIFY
    assert "Comp 1 sold 14 months" in v.message       # base message preserved
    assert v.reasoning and v.reasoning in v.message   # reasoning folded in

    silent = _FakeCtx(sales_comparison_summary="The home is well maintained.")
    v2 = layer_b.assess(silent, concern="dated_comp",
                        base_message="Comp 1 sold 14 months before the effective date.",
                        facts="comp 1 is dated")
    assert v2.explained is False
    assert v2.confidence == 0.7                       # unexplained -> full severity


def test_assess_respects_custom_status_mapping():
    # SCA-2 listings: explained -> VERIFY, unexplained -> FAIL.
    silent = _FakeCtx(sales_comparison_summary="No commentary here.")
    v = layer_b.assess(silent, concern="comp_selection",
                       base_message="Only 0 listing comparables were included.",
                       facts="no listing comp",
                       explained_status=RuleStatus.VERIFY,
                       unexplained_status=RuleStatus.FAIL)
    assert v.status == RuleStatus.FAIL
