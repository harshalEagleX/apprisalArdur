"""
tools/compile_amc.py — the AMC onboarding compile step (Step 1).

Onboarding an AMC = compile its checklist ONCE (offline, best model), validate the
compiled bindings against the fixture orders, let a human eyeball the flagged
items, then approve. The runtime only ever selects an APPROVED (status=active)
bundle — a guessed/unvalidated binding can never reach production and falsely
reject an appraiser.

Usage:
  # compile + validate (writes compiled/<AMC>/<hash>.yaml at status draft|validated)
  PYTHONPATH=. python tools/compile_amc.py EQUITYSOLUTIONS

  # after eyeballing REVIEW_NEEDED.yaml, sign it off (status → active)
  PYTHONPATH=. python tools/compile_amc.py EQUITYSOLUTIONS --approve --by "Harshal"

  # recompile even if a compiled artifact already exists
  PYTHONPATH=. python tools/compile_amc.py EQUITYSOLUTIONS --force
"""

from __future__ import annotations

import argparse
import json
import logging
import sys

logging.basicConfig(level=logging.WARNING, format="%(message)s")


def _summary(report: dict, diff: dict) -> str:
    lines = [
        f"  fixtures used : {', '.join(report['fixtures']) or '(none)'}",
        f"  items         : {report['items_total']} total, {report['items_bindable']} bindable",
        f"  confidence    : {report[[k for k in report if k.startswith('pct_confidence')][0]]}% ≥ floor",
        f"  unbound       : {report['unbound_count']}  {report['unbound_items'][:12]}",
        f"  low-confidence: {report['low_confidence_count']}  {report['low_confidence_items'][:12]}",
        f"  SUSPECT       : {report['suspect_count']}  (bound only to labels no fixture ever carries)",
        f"  verdict       : {report['verdict'].upper()}",
    ]
    if diff.get("has_previous"):
        lines.append(f"  binding diff  : {diff['changed_count']} items changed vs previous compile")
    for s in report["suspect_items"][:20]:
        lines.append(f"    · {s['item_id']:8} [{s['section']}] {s['bound_labels']}  — {s['check_text']}")
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description="Compile + validate + sign off an AMC checklist.")
    ap.add_argument("amc_code")
    ap.add_argument("--approve", action="store_true", help="flip status → active (sign-off)")
    ap.add_argument("--by", default="unknown", help="approver name (with --approve)")
    ap.add_argument("--force", action="store_true", help="recompile even if cached")
    ap.add_argument("--refresh-fixtures", action="store_true", help="re-extract fixtures (ignore cache)")
    ap.add_argument("--no-llm", action="store_true", help="compile without the LLM binder (debug)")
    args = ap.parse_args()

    from app.language import compiler as C
    from app.language.compile_gate import validate_compiled, diff_against_previous

    path = C.compiled_path(args.amc_code)

    # Sign-off path: just flip status on the existing artifact (no recompile).
    if args.approve and not args.force:
        if not path.exists():
            print(f"✗ no compiled artifact for {args.amc_code} — compile first.")
            return 2
        meta = C.bundle_meta(path)
        rep = meta.get("validation_report", {})
        if rep.get("verdict") == "review" and rep.get("suspect_count"):
            print(f"⚠ {rep['suspect_count']} suspect binding(s) still flagged. "
                  f"Approving anyway on your authority ({args.by}).")
        C.set_bundle_status(path, C.STATUS_ACTIVE, approved_by=args.by)
        print(f"✓ {args.amc_code} bundle {C.bundle_meta(path).get('checklist_hash')} "
              f"→ ACTIVE (approved_by={args.by})")
        return 0

    # Compile path.
    client = None if args.no_llm else _get_client()
    if client is None and not args.no_llm:
        print("⚠ no LLM client available — bindings will be unbound/authored only. "
              "Set TOGETHER_API_KEY_1/2 to run the real binder.")
    prev = C.load_compiled(path) if path.exists() else None
    prev_snapshot = None
    if prev is not None:
        # stash a copy for the diff before we overwrite.
        import tempfile, yaml, pathlib
        prev_snapshot = pathlib.Path(tempfile.mkstemp(suffix=".yaml")[1])
        prev_snapshot.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")

    print(f"Compiling {args.amc_code} …")
    items = C.compile_checklist(args.amc_code, client=client, force=True)
    report = validate_compiled(items, refresh_fixtures=args.refresh_fixtures)
    diff = diff_against_previous(items, prev_snapshot)

    status = C.STATUS_VALIDATED if report["verdict"] == "ok" else C.STATUS_DRAFT
    C.set_bundle_status(path, status, validation_report=report)

    print(f"\n{args.amc_code} → status={status}")
    print(_summary(report, diff))
    print(f"\nCompiled : {path}")
    print(f"Review   : {path.parent / 'REVIEW_NEEDED.yaml'}")
    if status == C.STATUS_VALIDATED:
        print(f"\nNext: eyeball the flagged items, then\n"
              f"  PYTHONPATH=. python tools/compile_amc.py {args.amc_code} --approve --by <you>")
    else:
        print(f"\nGate verdict=review — resolve suspects/unbound above, or approve on your "
              f"authority with --approve.")
    return 0


def _get_client():
    try:
        from app.llm.client import get_client
        c = get_client()
        return c if (c and getattr(c, "available", False)) else None
    except Exception as exc:  # pragma: no cover
        print(f"⚠ LLM client init failed: {exc}")
        return None


if __name__ == "__main__":
    sys.exit(main())
