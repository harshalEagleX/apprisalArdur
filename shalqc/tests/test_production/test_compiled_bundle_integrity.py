"""Compiled-bundle integrity gate (2026-07-18).

The runtime hard-depends on a signed compiled bundle: orchestrator resolves
`compiled_path(amc)` (the file named by the CURRENT source hash) and hard-stops
unless its meta.status == active (app/pipeline/orchestrator.py). With
`binding_overrides` retired, that bundle is also the ONLY home for its hand-tuned
`bound_by: manual` bindings — a `--force` recompile regenerates every binding and
resets status→draft, so the compiled file is genuinely source-of-record and must
be committed.

This gate catches the drift vectors that broke us before, WITHOUT the playbook's
"recompile-from-source and diff" (which is fatal here: a keyless deterministic
recompile produces zero manual/llm bindings and status=draft — running it in CI
and committing the result would erase every tuned binding). Instead it asserts,
per AMC, cheap deterministic invariants against the committed artifact:

  1. the current-source-hash bundle EXISTS on disk (catches an untracked bundle:
     a fresh CI checkout / teammate pull simply won't have it → the runtime would
     hard-stop) and is tracked by git;
  2. exactly ONE bundle in the AMC dir is status=active (no ambiguity for the
     runtime's status gate);
  3. that active bundle IS the current-source-hash bundle (catches "source edited
     but bundle not recompiled + re-approved");
  4. its item count matches the source checklist row count;
  5. it still carries real (manual/llm) bindings — i.e. it is NOT a degraded
     keyless recompile that someone force-approved.
"""
import glob
import os
import subprocess

import pytest
import yaml

from app.language import compiler as C

_COMPILED_DIR = C._COMPILED_DIR


def _amc_dirs():
    # AMC codes never start with "_"; that prefix marks non-AMC helper dirs
    # (`_fixtures` golden JSON, `__pycache__`). An AMC dir holds compiled *.yaml.
    if not _COMPILED_DIR.exists():
        return []
    return sorted(p for p in _COMPILED_DIR.iterdir()
                  if p.is_dir() and not p.name.startswith("_")
                  and any(p.glob("*.yaml")))


_AMCS = [p.name for p in _amc_dirs()]


def _is_git_tracked(path) -> bool:
    try:
        r = subprocess.run(["git", "ls-files", "--error-unmatch", str(path)],
                           cwd=str(_COMPILED_DIR), capture_output=True)
        return r.returncode == 0
    except (OSError, FileNotFoundError):
        pytest.skip("git not available")


def test_at_least_one_amc_bundle_present():
    # A codebase with no compiled bundle at all can't run a live order; the fixture
    # AMC (EQUITYSOLUTIONS) must always be present.
    assert _AMCS, "no compiled/<AMC>/ bundles found — the runtime has nothing to run"


@pytest.mark.parametrize("amc", _AMCS)
def test_current_source_hash_bundle_exists_and_tracked(amc):
    src = C.checklist_for(amc)
    bundle = C.compiled_path(amc, src)
    assert bundle.exists(), (
        f"{amc}: no compiled bundle at the current source hash ({bundle.name}). "
        f"Source changed without a recompile, or the bundle was never committed — "
        f"the runtime resolves exactly this path and will hard-stop.")
    assert _is_git_tracked(bundle), (
        f"{amc}: {bundle.name} exists locally but is UNTRACKED. Commit it — an "
        f"untracked runtime artifact is invisible to CI and to teammates.")


@pytest.mark.parametrize("amc", _AMCS)
def test_exactly_one_active_bundle_and_it_is_current(amc):
    src = C.checklist_for(amc)
    current = C.compiled_path(amc, src)
    active = [p for p in _COMPILED_DIR.joinpath(amc).glob("*.yaml")
              if C.bundle_status(p) == C.STATUS_ACTIVE]
    assert len(active) == 1, (
        f"{amc}: expected exactly one status=active bundle, found {len(active)}: "
        f"{[p.name for p in active]}. The runtime's sign-off gate needs one.")
    assert active[0] == current, (
        f"{amc}: the active bundle is {active[0].name} but the current source hashes "
        f"to {current.name}. Recompile from source and re-approve.")


@pytest.mark.parametrize("amc", _AMCS)
def test_active_bundle_count_matches_source_and_bindings_intact(amc):
    src = C.checklist_for(amc)
    bundle = C.compiled_path(amc, src)
    if not bundle.exists():
        pytest.skip(f"{amc}: bundle missing (covered by existence test)")
    raw = yaml.safe_load(bundle.read_text(encoding="utf-8")) or {}
    items = raw.get("items", [])
    src_rows = C.load_checklist(src)
    assert len(items) == len(src_rows), (
        f"{amc}: bundle has {len(items)} items but the source checklist has "
        f"{len(src_rows)} — the bundle is stale relative to its source.")
    bound_by = [(it.get("bound_by") or "") for it in items]
    real = sum(1 for b in bound_by if b in ("manual", "llm"))
    assert real > 0, (
        f"{amc}: the active bundle carries zero manual/llm bindings — this is the "
        f"signature of a keyless deterministic recompile. The signed bundle must "
        f"not be a degraded regeneration.")
