"""
language.compile_gate (Step 1) — the compile VALIDATION gate.

A compiled checklist cannot go live on the strength of the binder alone. Before a
bundle can be approved (status → active) it must pass this gate against the real
fixture orders:

  * every bound_label must EXIST in the schema (drift guard — already enforced by
    the compiler), AND
  * be SEEN with a plausible value in at least one fixture. A binding to a label
    that never carries data in any fixture is the signature of a wrong binding
    (the "# of Stories → bath_floor_material" class of bug) — it is flagged
    suspect so a human eyeballs it, and it holds the bundle out of `active`.

The gate produces a validation_report (stored in the bundle meta) and a verdict:
  ok       — no suspect/unbound items; safe to approve.
  review   — some items need a human look before approval.

It never edits bindings. It measures them. Editing/approval is the human's job
(tools/compile_amc.py --approve).
"""

from __future__ import annotations

import glob
import json
import logging
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from app.language import label_dictionary as LD
from app.language.spec import CompiledItem

logger = logging.getLogger(__name__)

__version__ = "gate-1.0.0"

_COMP_IDX = re.compile(r"^comp_\d+_")
_TESTFILES = Path(__file__).parent.parent.parent / "testfiles"
_FIXTURE_CACHE = Path(__file__).parent.parent.parent / "compiled" / "_fixtures"
_CONF_FLOOR = 0.8   # "% bound with confidence ≥ 0.8" headline metric.


# ── fixture value maps (cached: extraction is expensive) ──────────────────────

def _fixture_dirs() -> List[Path]:
    if not _TESTFILES.exists():
        return []
    return sorted(p for p in _TESTFILES.iterdir()
                  if p.is_dir() and (p / "appraisal").is_dir())


def _seen_labels_for(order_dir: Path, refresh: bool = False) -> Set[str]:
    """Collapsed labels found with a non-empty value in one fixture order.
    Cached to compiled/_fixtures/<order>.json so re-validation is a file read."""
    from app.extraction.schema import schema_loader

    cache = _FIXTURE_CACHE / f"{order_dir.name}.json"
    schema_ver = getattr(schema_loader, "schema_version", "?")
    if cache.exists() and not refresh:
        blob = json.loads(cache.read_text(encoding="utf-8"))
        if blob.get("schema_version") == schema_ver:
            return set(blob.get("seen", []))

    pdf = next(iter(glob.glob(str(order_dir / "appraisal" / "*.pdf"))), None)
    xml = next(iter(glob.glob(str(order_dir / "appraisal" / "*.[xX][mM][lL]"))), None)
    eng = next(iter(glob.glob(str(order_dir / "engagement" / "*.pdf"))), None)
    if not pdf:
        return set()

    from app.extraction.merge import run_extraction
    fs = run_extraction(pdf, xml_path=xml, engagement_letter=eng)
    seen: Set[str] = set()
    for f in fs.found_fields():
        v = (f.value or "").strip()
        if v:
            seen.add(_COMP_IDX.sub("comp_N_", f.canonical_name))

    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps({"schema_version": schema_ver, "seen": sorted(seen)}),
                     encoding="utf-8")
    return seen


def fixture_seen_union(refresh: bool = False) -> Tuple[Set[str], List[str]]:
    """Union of labels seen across ALL fixtures, and the fixture names used."""
    union: Set[str] = set()
    names: List[str] = []
    for d in _fixture_dirs():
        union |= _seen_labels_for(d, refresh=refresh)
        names.append(d.name)
    return union, names


# ── the gate ──────────────────────────────────────────────────────────────────

def validate_compiled(items: List[CompiledItem], refresh_fixtures: bool = False
                      ) -> Dict[str, Any]:
    """Run the compile gate over compiled items. Returns a validation_report dict
    (JSON-safe) with per-item flags and a headline verdict."""
    seen, fixtures = fixture_seen_union(refresh=refresh_fixtures)
    have_fixtures = bool(fixtures) and bool(seen)

    suspect: List[Dict[str, Any]] = []   # bound to label(s) never seen in any fixture
    unbound: List[str] = []              # nothing bound, not intentionally visual
    low_conf: List[str] = []             # binder_confidence < floor
    judged = 0                           # items subject to binding at all

    for it in items:
        if it.judgeable == "visual" or it.scope == "visual":
            continue                     # visual = human card, never bound
        judged += 1
        labels = [LD.canonical_label(l) for l in it.all_labels]
        if not labels:
            unbound.append(it.item_id)
            continue
        if it.binder_confidence < _CONF_FLOOR:
            low_conf.append(it.item_id)
        if have_fixtures:
            missing = [l for l in labels if l not in seen]
            if missing and len(missing) == len(labels):
                # EVERY bound label is unseen in every fixture → almost certainly
                # a wrong binding. (Partial-miss is normal: optional fields.)
                suspect.append({"item_id": it.item_id, "section": it.section,
                                "bound_labels": labels,
                                "check_text": it.check_text[:120]})

    pct_conf = round(100.0 * (judged - len(low_conf)) / judged, 1) if judged else 0.0
    ok = not suspect and not unbound and (pct_conf >= 90.0)

    report = {
        "gate_version": __version__,
        "fixtures": fixtures,
        "have_fixtures": have_fixtures,
        "items_total": len(items),
        "items_bindable": judged,
        "pct_confidence_ge_%.1f" % _CONF_FLOOR: pct_conf,
        "unbound_count": len(unbound),
        "unbound_items": unbound,
        "low_confidence_count": len(low_conf),
        "low_confidence_items": low_conf,
        "suspect_count": len(suspect),
        "suspect_items": suspect,
        "verdict": "ok" if ok else "review",
    }
    return report


def diff_against_previous(items: List[CompiledItem], prev_path: Optional[Path]
                          ) -> Dict[str, Any]:
    """Binding diff vs the previously-compiled version (if any) — which items
    changed which labels. Empty when there is no prior compile to compare to."""
    if not prev_path or not prev_path.exists():
        return {"has_previous": False}
    from app.language.compiler import load_compiled
    prev = {it.item_id: it for it in load_compiled(prev_path)}
    changed: List[Dict[str, Any]] = []
    for it in items:
        p = prev.get(it.item_id)
        if p is None:
            changed.append({"item_id": it.item_id, "from": None, "to": it.bound_labels})
        elif sorted(p.bound_labels) != sorted(it.bound_labels):
            changed.append({"item_id": it.item_id, "from": p.bound_labels,
                            "to": it.bound_labels})
    return {"has_previous": True, "changed_count": len(changed), "changed": changed}
