"""Derivation unit tests — focused on appraisal_report_type_from_text, whose
whole value is being HIGH-PRECISION: it must never guess the USPAP reporting
option off a page that merely lists both checkbox labels."""

from app.rules.derivations import DERIVERS, appraisal_report_type_from_text


def _get(store):
    return lambda k: store.get(k)


def test_deriver_is_registered():
    assert DERIVERS["appraisal_report_type_from_text"] is appraisal_report_type_from_text


def test_restricted_assertion_yields_restricted():
    txt = "This appraisal is a Restricted Appraisal Report as defined by Standards Rule 2-2(b)."
    assert appraisal_report_type_from_text(_get({"addendum_text": txt})) == "Restricted Appraisal Report"


def test_plain_assertion_yields_appraisal_report():
    txt = "This is an Appraisal Report as defined by USPAP Standards Rule 2-2(a)."
    assert appraisal_report_type_from_text(_get({"intended_use_statement": txt})) == "Appraisal Report"


def test_option_list_with_both_labels_yields_none():
    # The safety case: a checkbox LIST shows both labels no matter which is ticked,
    # and text extraction drops the check mark — so we must NOT guess.
    txt = "Reporting Option: [ ] Appraisal Report  [ ] Restricted Appraisal Report"
    assert appraisal_report_type_from_text(_get({"addendum_text": txt})) is None


def test_restricted_wins_over_plain_when_both_asserted():
    txt = "Not an Appraisal Report — this is a Restricted Appraisal Report."
    assert appraisal_report_type_from_text(_get({"addendum_text": txt})) == "Restricted Appraisal Report"


def test_verbatim_value_wins():
    assert appraisal_report_type_from_text(_get({"appraisal_report_type": "Appraisal Report"})) == "Appraisal Report"


def test_no_source_text_yields_none():
    assert appraisal_report_type_from_text(_get({})) is None
