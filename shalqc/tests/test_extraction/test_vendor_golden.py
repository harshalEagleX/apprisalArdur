"""B1 — per-vendor canonical-output golden test (playbook adapter-deliverable #6).

MISMO 2.6 GSE is one spec that each vendor (a la mode TOTAL, ACI, ClickForms,
Bradford) implements as a subset + private extensions. xml_extractor detects the
vendor and isolates the per-dialect quirks inline (e.g. ATTIC._ExistsIndicator on
ACI vs ATTIC_FEATURE on TOTAL). None of that was pinned — a regression in vendor
detection or a dialect branch would ship silently. This test freezes, per committed
fixture: (1) the detected `xml_vendor`, and (2) a curated set of canonical values
that ride vendor-divergent branches. Any change that alters the canonical output
fails here — then you update the pin deliberately, not by accident.

Adding a vendor is a one-line entry once its fixture is committed. ACI is present
locally under testfiles/0260729624.XML (detects as 'ACI') but that tree is not
committed (real appraisal data / PII, §17) — commit an ACI fixture under
tests/fixtures/ and add its GOLDEN row to extend cross-vendor coverage.
"""
from pathlib import Path

import pytest

from app.extraction.xml_extractor import extract_xml

_ROOT = Path(__file__).resolve().parents[2]      # …/shalqc

GOLDEN = {
    "ESTX-0007568 (a la mode TOTAL)": {
        "path": "tests/fixtures/ESTX-0007568/appraisal/7243 Foxtail Meadow Ct.xml",
        "vendor": "TOTAL",
        "canonical": {
            "uad_version": "UAD Version 9/2011",
            "amc_name": "Equity Solutions, USA",
            "management_company": "Equity Solutions, USA",
            "total_rooms": "7",
            "bedrooms": "4",
            "year_built": "2018",
            "design_style": "Ranch",
            "foundation_type": "Slab",
            "heating": "ForcedWarmAir",
            "site_area": "4800 sf",
            "zoning_classification": "Deed Restricted SFR",
            "appraised_value": "245000",
        },
    },
    # ACI: add a committed tests/fixtures/<ACI order>/…/*.XML row here (vendor "ACI").
}


def _fs(rel_path: str):
    p = _ROOT / rel_path
    assert p.exists(), f"golden fixture missing: {p}"
    return extract_xml(str(p))


@pytest.mark.parametrize("name", list(GOLDEN))
def test_vendor_detected(name):
    g = GOLDEN[name]
    ef = _fs(g["path"]).get("xml_vendor")
    assert ef is not None, f"{name}: xml_vendor not extracted"
    assert ef.value == g["vendor"], f"{name}: vendor {ef.value!r} != {g['vendor']!r}"


@pytest.mark.parametrize("name", list(GOLDEN))
def test_canonical_output_pinned(name):
    g = GOLDEN[name]
    fs = _fs(g["path"])
    mismatches = {}
    for canon, expected in g["canonical"].items():
        ef = fs.get(canon)
        got = ef.value if ef else None
        if got != expected:
            mismatches[canon] = {"expected": expected, "got": got}
    assert not mismatches, f"{name}: canonical output drifted: {mismatches}"
