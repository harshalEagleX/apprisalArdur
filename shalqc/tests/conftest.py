"""Shared test fixtures/guards.

The golden order (ESTX-0007568) is split by design: its MISMO **XML is tracked**
in git, but the appraisal and engagement **PDFs are not** — raw appraisal
documents carry borrower PII (SHALqc.md §17), so they stay out of git history.

That means a clean CI checkout has the fixture DIRECTORY (the XML is in it) but
none of the PDFs. Guards written as `skipif(not FIXTURE_DIR.exists())` therefore
did not fire in CI: the directory existed, the test ran, and it failed on a
missing PDF. Eight tests failed that way on every CI run since the workflow was
added.

`requires_fixture_docs` keys on the PDF that is actually absent, so those tests
skip in CI and still run locally for anyone who has the documents.
"""
from pathlib import Path

import pytest

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "ESTX-0007568"
FIXTURE_XML = FIXTURE_DIR / "appraisal" / "7243 Foxtail Meadow Ct.xml"
FIXTURE_PDF = FIXTURE_DIR / "appraisal" / "7243 Foxtail Meadow Ct.pdf"
FIXTURE_ENGAGEMENT = FIXTURE_DIR / "engagement" / "EngagementLetter - 2026-07-09T203634.806.pdf"

#: True only when the PII documents are present on this machine.
HAVE_FIXTURE_DOCS = FIXTURE_PDF.exists()

#: True when the tracked XML is available (it is, in every checkout) — use this
#: for tests that only need the MISMO side and no PDF.
HAVE_FIXTURE_XML = FIXTURE_XML.exists()

requires_fixture_docs = pytest.mark.skipif(
    not HAVE_FIXTURE_DOCS,
    reason="appraisal/engagement PDFs are PII and are not committed "
           "(see tests/conftest.py) — run locally with the documents present",
)

requires_fixture_xml = pytest.mark.skipif(
    not HAVE_FIXTURE_XML, reason="fixture XML not present")

# `testfiles/` is the local corpus of real orders — gitignored in full (raw
# appraisals, borrower PII). Tests that read it must skip where it is absent.
TESTFILES_DIR = Path(__file__).parent.parent / "testfiles"
HAVE_TESTFILES = (TESTFILES_DIR / "ESNV-0000885").exists()

requires_testfiles = pytest.mark.skipif(
    not HAVE_TESTFILES,
    reason="testfiles/ is the local PII order corpus and is gitignored — "
           "run locally with the orders present",
)
