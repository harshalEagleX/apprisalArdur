"""
language.label_dictionary — the FIXED label contract handed to the binder (§3).

The whole anti-drift guarantee (§3, "why this kills the drift problem
permanently") is that a check can only ever bind to labels that actually exist in
extraction. So the binder is shown the canonical schema labels *themselves* — one
line of `label: meaning` per field — and nothing else. `comp_N_*` families are
kept as single template rows (the packet expands them to present comps at
runtime).

Static + cached: built once from config/field_schema.yaml (sch-1.0.0). Labels
never change; values change per property.
"""

from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path
from typing import Dict, List, Set

import yaml

_COMP_IDX = re.compile(r"^comp_\d+_")
_SCOPE_PATH = Path(__file__).parent.parent.parent / "config" / "section_scope.yaml"


def _meaning(fd) -> str:
    """One-line human meaning for a field label. Prefer the schema note; fall
    back to a readable rendering of the canonical name + type."""
    note = (getattr(fd, "notes", "") or "").strip().replace("\n", " ")
    if note:
        return note[:160]
    pretty = fd.canonical_name.replace("comp_N_", "comparable ").replace("_", " ")
    dt = getattr(fd, "data_type", "") or ""
    return f"{pretty}{f' ({dt})' if dt else ''}"[:160]


@lru_cache(maxsize=1)
def _build() -> Dict[str, str]:
    """label → one-line meaning. `comp_1_x`/`comp_2_x`/… collapse to `comp_N_x`."""
    from app.extraction.schema import schema_loader

    out: Dict[str, str] = {}
    for fd in schema_loader.all_fields():
        label = _COMP_IDX.sub("comp_N_", fd.canonical_name)
        if label not in out:
            out[label] = _meaning(fd)
    # A handful of runtime-derived presence labels the packet can carry that the
    # schema may not list as first-class fields (exhibit flags used by visual
    # checks); harmless if unused by a given AMC.
    for lbl, mean in (
        ("comp_count_present", "number of comparable sales actually present in the grid"),
        ("photo_front", "front photo of the subject present"),
        ("photo_rear", "rear photo of the subject present"),
        ("photo_street", "street scene photo present"),
        ("sketch_present", "floor-plan sketch present"),
        ("location_map_present", "location map present"),
    ):
        out.setdefault(lbl, mean)
    return dict(out)


def label_meanings() -> Dict[str, str]:
    """The full {label: meaning} dictionary (cached)."""
    return _build()


def known_labels() -> Set[str]:
    """Every label the binder is allowed to bind to (drift guard)."""
    return set(_build().keys())


def is_known(label: str) -> bool:
    """True if `label` (or its comp_N family) exists in extraction's schema."""
    return _COMP_IDX.sub("comp_N_", label) in _build()


def canonical_label(label: str) -> str:
    """Collapse a per-comp label to its comp_N family form."""
    return _COMP_IDX.sub("comp_N_", label)


def dictionary_text() -> str:
    """The ~600-line static block the binder call receives (§3 step 1)."""
    lines = [f"{lbl}: {mean}" for lbl, mean in sorted(_build().items())]
    return "\n".join(lines)


# ── section scoping (Step 1: narrow the binder's candidate labels) ────────────

@lru_cache(maxsize=1)
def _section_index() -> Dict[str, Set[str]]:
    """field_schema section → set of canonical (comp_N-collapsed) labels in it.

    Built once from the schema's per-field `sections:`. A field in two sections
    (e.g. condo_unit + improvements) appears under both."""
    from app.extraction.schema import schema_loader

    idx: Dict[str, Set[str]] = {}
    for fd in schema_loader.all_fields():
        label = _COMP_IDX.sub("comp_N_", fd.canonical_name)
        for sec in (getattr(fd, "sections", None) or []):
            idx.setdefault(sec, set()).add(label)
    return idx


@lru_cache(maxsize=1)
def _scope_config() -> Dict[str, object]:
    if not _SCOPE_PATH.exists():
        return {}
    return yaml.safe_load(_SCOPE_PATH.read_text(encoding="utf-8")) or {}


def field_sections_for(checklist_section: str) -> List[str]:
    """The field_schema sections whose labels are candidates for a check in this
    checklist section — its own groups plus the shared `_anchor` groups. Empty
    (no mapping) signals 'use the full dictionary' to the caller."""
    cfg = _scope_config()
    sections = (cfg.get("sections") or {})
    anchor = list(cfg.get("_anchor") or [])
    if checklist_section not in sections:
        return []                       # unknown → caller falls back to full dict
    own = list(sections.get(checklist_section) or [])
    out: List[str] = []
    for s in own + anchor:
        if s not in out:
            out.append(s)
    return out


def scoped_labels(checklist_section: str) -> Set[str]:
    """Every candidate label for a check in `checklist_section`. Empty scope
    config (unknown section) → the full known-label set (safe, wide)."""
    groups = field_sections_for(checklist_section)
    if not groups:
        return known_labels()
    idx = _section_index()
    out: Set[str] = set()
    for g in groups:
        out |= idx.get(g, set())
    # runtime-only presence labels are cheap to always offer.
    out |= {"comp_count_present", "photo_front", "photo_rear", "photo_street",
            "sketch_present", "location_map_present"}
    return out & known_labels()


def scoped_dictionary_text(checklist_section: str) -> str:
    """The section-scoped `label: meaning` block the binder receives — typically
    40-100 lines instead of ~600 (Step 1)."""
    meanings = _build()
    labels = sorted(scoped_labels(checklist_section))
    return "\n".join(f"{lbl}: {meanings[lbl]}" for lbl in labels if lbl in meanings)


def reset_cache() -> None:
    _build.cache_clear()
    _section_index.cache_clear()
    _scope_config.cache_clear()
