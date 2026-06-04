"""Name normalization / matching (middle-initial insensitivity)."""

from app.qc import matching


def test_middle_initial_ignored():
    # "Riley C Freese" vs "riley freese" — same party, differs only by middle initial.
    mr = matching.match_text("Riley C Freese", "riley freese", kind="name")
    assert mr.verdict == "match" and mr.score >= 0.99


def test_order_and_case_insensitive():
    mr = matching.match_text("DEINEKO, ANTON", "Anton Deineko", kind="name")
    assert mr.verdict == "match"


def test_different_surnames_still_mismatch():
    mr = matching.match_text("Riley Freese", "Jordan Whitman", kind="name")
    assert mr.verdict == "mismatch"


def test_normalize_drops_single_letter_tokens():
    assert matching.normalize_name("Riley C Freese") == matching.normalize_name("Riley Freese")
