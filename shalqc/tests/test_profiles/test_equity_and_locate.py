"""
Equity Solutions profile + dynamic resolution + engagement.city + Back-Locator.

These lock the "real AMC, stay dynamic, no hardcoding" work: the profile is
selected by config-declared resolve rules, the engagement parser splits city at
the USPS suffix, and the CORE §3 back-locator stamps location_quality.
"""

from pathlib import Path

import pytest

import app.rules  # register rules
from app.extraction.engagement import parse_address
from app.profiles.engine_binding import apply_severity
from app.profiles.loader import load_profile, profile_loader
from app.report.wording import wording_book
from app.rules.verdict import Status, Verdict

_TESTFILES = Path(__file__).parent.parent.parent / "testfiles"


def setup_function(_):
    profile_loader.reload()


# ── dynamic AMC resolution (config-declared, no engine hardcoding) ───────────

def test_resolve_by_order_id_prefix():
    assert profile_loader.resolve_amc("", "ESTX-0007568") == "EQUITYSOLUTIONS"
    assert profile_loader.resolve_amc("", "ESCA-0019968") == "EQUITYSOLUTIONS"


def test_resolve_by_alias_text():
    assert profile_loader.resolve_amc("Processed by Equity Solutions USA", "X-1") == "EQUITYSOLUTIONS"


def test_resolve_unknown_returns_none():
    assert profile_loader.resolve_amc("some other amc", "ZZ-1") is None


# ── Equity profile: wording + severity remap (config only) ───────────────────

def test_equity_wording_renders_catalog_text():
    p = load_profile("EQUITYSOLUTIONS")
    assert p.name == "Equity Solutions"
    got = wording_book.render(p.wording_file, "S-1.address_mismatch", {}, "fb")
    assert got == "Property address does not match with order form."


def test_equity_hbu_severity_remap_is_config_not_verdict_force():
    # profile remaps a FAIL to HOLD; it does NOT invent the FAIL — the rule must
    # still produce it. Here we feed a real FAIL and assert only the remap.
    p = load_profile("EQUITYSOLUTIONS")
    vs = [Verdict(rule_id="ST-6", status=Status.FAIL, section="site")]
    apply_severity(p, vs)
    assert vs[0].status == Status.HOLD
    # a PASS is never remapped to HOLD (no forcing)
    vs2 = [Verdict(rule_id="ST-6", status=Status.PASS, section="site")]
    apply_severity(p, vs2)
    assert vs2[0].status == Status.PASS


# ── engagement.city split at USPS suffix ─────────────────────────────────────

@pytest.mark.parametrize("blob,exp_city,exp_state", [
    ("7243 Foxtail Mdw Ct Humble TX 77338", "Humble", "TX"),
    ("6901 Camp Fire Rd Las Vegas NV 89145", "Las Vegas", "NV"),   # two-word city
    ("545 Old Airport Road Auburn CA 95603", "Auburn", "CA"),
])
def test_engagement_city_splits_at_suffix(blob, exp_city, exp_state):
    out = parse_address(blob)
    assert out.get("city") == exp_city
    assert out.get("state") == exp_state
    assert exp_city not in out.get("property_address", "")   # city not glued into street


def test_engagement_city_unset_when_no_suffix():
    # no recognizable street suffix → city stays UNSET (VERIFY), never guessed
    out = parse_address("Parcel 12 Blkville ZZ 00000")
    assert "city" not in out or out.get("city") in (None, "")


# ── CORE §3 back-locator ─────────────────────────────────────────────────────

@pytest.mark.skipif(not (_TESTFILES / "ESTX-0007568").exists(), reason="testfiles not present")
def test_back_locator_stamps_location_quality():
    from app.extraction.merge import run_extraction
    base = _TESTFILES / "ESTX-0007568" / "appraisal"
    fs = run_extraction(appraisal_pdf=base / "7243 Foxtail Meadow Ct.pdf",
                        xml_path=base / "7243 Foxtail Meadow Ct.xml", engagement_letter=None)
    found = [ef for _n, ef in fs if ef.found]
    # DoD #8: 0 fields silently missing a location_quality
    assert all(ef.location_quality in ("exact", "region", "page", "none") for ef in found)
    # DoD #8: the great majority of fields reach exact (L1/L2).
    # Threshold recalibrated 0.88 -> 0.78 on 2026-07-20 with loc-2.0.0: "exact"
    # now requires the match to be CORROBORATED (unique on the doc, near its
    # template anchor, or next to its own label tokens). The old first-match-wins
    # scan claimed 0.88+ but ~80% of those values occur more than once in the
    # report and the box routinely sat on the WRONG instance (a date matched by
    # its bare year, an address by its house number). A smaller, verified-correct
    # exact set is the honest click-to-scroll promise; ambiguous values degrade
    # to page/none instead of guessing.
    exact = sum(1 for ef in found if ef.location_quality == "exact")
    assert exact / len(found) >= 0.78, f"only {exact}/{len(found)} exact"
    addr = fs.get("property_address")
    assert addr.location_quality == "exact" and addr.page >= 1 and addr.bbox is not None

    # loc-2.0.0 correctness gate: every exact box must actually CONTAIN its value
    # (string, printed-date, or numeric rendering) — a box on the wrong text is
    # worse than no box. This is what "exact" promises the reviewer.
    import re as _re

    import fitz
    _n = lambda s: _re.sub(r"[^a-z0-9]+", "", str(s).lower())  # noqa: E731
    doc = fitz.open(base / "7243 Foxtail Meadow Ct.pdf")
    wrong = []
    for _name, ef in fs:
        if not (ef.found and ef.location_quality == "exact" and ef.bbox and ef.page
                and ef.page <= len(doc)):
            continue
        page = doc[ef.page - 1]
        pw, ph = page.rect.width, page.rect.height
        b = ef.bbox
        clip = fitz.Rect(b["x"] * pw - 2, b["y"] * ph - 2,
                         (b["x"] + b["w"]) * pw + 2, (b["y"] + b["h"]) * ph + 2)
        raw_under = page.get_text("text", clip=clip)
        under, v = _n(raw_under), _n(ef.value)
        ok = bool(v and (v in under or under in v))
        if not ok:  # ISO date printed as MM/DD/YYYY
            m = _re.match(r"^(\d{4})(\d{2})(\d{2})$", v)
            if m and (f"{m.group(2)}{m.group(3)}{m.group(1)}" in under
                      or f"{int(m.group(2))}{int(m.group(3))}{m.group(1)}" in under):
                ok = True
        if not ok:  # numeric rendering ($1,234.00 for 1234)
            mnum = _re.search(r"\d[\d]*\.?\d*", raw_under.replace(",", ""))
            try:
                ok = mnum is not None and float(mnum.group(0)) == float(
                    str(ef.value).replace(",", "").replace("$", ""))
            except ValueError:
                pass
        if not ok:
            wrong.append((ef.canonical_name, str(ef.value)[:30]))
    doc.close()
    # L1 boxes (grid/checkbox witnesses) can legitimately sit on a label rather
    # than verbatim text — allow a small tail, but wrong boxes must stay rare.
    assert len(wrong) <= max(3, int(0.02 * exact)), f"wrong exact boxes: {wrong[:10]}"

    # loc-2.1.0 comp-column guard: NO two comparables may share the same box for
    # the same grid row. Repeated grid values (0sf, None, ArmLth, "N;Res;") used
    # to collapse onto one comp's cell, so clicking "Comp 3" scrolled to Comp 2.
    # This order has 7 comps across three grid pages — strong coverage.
    import re as _re2
    cells: dict = {}
    for name, ef in fs:
        m = _re2.match(r"^comp_(\d+)_(.+)$", name)
        if not (m and ef.found and ef.location_quality == "exact" and ef.bbox and ef.page):
            continue
        key = (m.group(2), ef.page, round(ef.bbox["x"], 2), round(ef.bbox["y"], 2))
        cells.setdefault(key, set()).add(int(m.group(1)))
    collisions = {k: sorted(v) for k, v in cells.items() if len(v) > 1}
    assert not collisions, f"comparables sharing a box: {list(collisions.items())[:6]}"

    # loc-2.1.0 prose guard: long narratives (condition/site/addendum comments)
    # wrap across rows and cannot match verbatim; they must still get a jump
    # target at their FIRST line rather than landing at `none`. At least a few of
    # this report's long comments should be located (and correct, checked above).
    prose_rx = _re.compile(r"comment|description|narrative|addend|remark|analysis")
    prose_exact = sum(1 for n, ef in fs
                      if prose_rx.search(n) and ef.found and ef.location_quality == "exact"
                      and ef.bbox is not None)
    assert prose_exact >= 8, f"only {prose_exact} narrative/comment fields located"
