"""
language.compiler (cmp-1.0.0) — the Checklist Compiler (§3).

Turns ANY AMC's checklist (their language verbatim) into compiled CompiledItems,
ONCE per checklist version, cached by checklist hash. The runtime NEVER re-binds
— it reads compiled/<amc>/<hash>.yaml.

Binding order per item (§3 step 1):
  1. The checklist's own authored `sources` fields (aliased → canonical, filtered
     to labels that ACTUALLY exist in extraction — the anti-drift guarantee).
  2. An LLM binder call (bind_v1) when a client is available: it reads the check
     text + the full canonical label dictionary and returns {bound_labels, scope,
     expects, judgeable}. Its labels are filtered to known labels too — the binder
     can only ever bind to real names, so `comp_1_quality` can never be asked for
     as `comp_1_quality_rating`'s ghost.
  3. Heuristic fallback (no client): keyword scan of the check text against label
     meanings.

Visual checks (photos/sketch/maps) never call the LLM — they compile to a
constant reviewer card (§3, saves 2+ calls/order). A check that binds to nothing
compiles as scope=unbound (the packet then carries a section snapshot, §7 S-5).
"""

from __future__ import annotations

import hashlib
import logging
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import yaml

from app.language import label_dictionary as LD
from app.language.spec import CompiledItem

logger = logging.getLogger(__name__)

__version__ = "cmp-1.1.0"
BINDER_PROMPT_VERSION = "binder_v2"

# Bundle sign-off states written to compiled/<amc>/<hash>.yaml meta.status.
# draft     — compiled, not yet validated against fixtures.
# validated — passed the compile gate (all bindings execute + seen in fixtures).
# active    — a human approved it; the ONLY state the runtime will select.
STATUS_DRAFT, STATUS_VALIDATED, STATUS_ACTIVE = "draft", "validated", "active"

_COMPILED_DIR = Path(__file__).parent.parent.parent / "compiled"
_DEFAULT_CHECKLIST = (Path(__file__).parent.parent.parent
                      / "readme" / "exampleAMC" / "qc_rejection_catalog.yaml")

_VISUAL_RX = re.compile(r"\b(photo|photograph|sketch|floor ?plan|map|image|exhibit|picture)\b", re.I)
_COUNT_RX = re.compile(r"(?:min(?:imum)?|at least|>=|no fewer than)\s*(\d+)", re.I)
# AnnexB Part 2: conditional check language.
_COND_RX = re.compile(r"\b(if|when|whenever|where)\b", re.I)
_THEN_RX = re.compile(r"\b(then|must|should|shall|require[sd]?|needs? to|has to)\b", re.I)
_AGE_RX = re.compile(r"\b(age|year built|yr built|built|old|remodel|updat|renovat)\b", re.I)
_REVIEW_CONF_FLOOR = 0.7


# ── checklist normalisation (AMC language → item rows) ────────────────────────

def load_checklist(path: Path = _DEFAULT_CHECKLIST) -> List[Dict[str, Any]]:
    """Read an AMC checklist file → normalized rows {item_id, section, check_text,
    reject_text, check_type, sources}. Accepts BOTH the native language format
    ("our new way": an item already carries `check_text`/`section`, no rule_id or
    hand-authored sources) AND the legacy rejection-catalog schema. Unknown keys
    are ignored; any AMC file with these keys works."""
    if not path.exists():
        logger.warning("compiler: checklist %s not found", path)
        return []
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    rows: List[Dict[str, Any]] = []
    for it in raw.get("items", []):
        # native format (from tools/xlsx_to_checklist.py): the AMC's own words.
        if it.get("check_text") and not it.get("requirement") and not it.get("rule_id"):
            rows.append({
                "item_id": str(it.get("item_id") or f"CAT-{it.get('id','?')}"),
                "section": it.get("section") or _section_of(str(it.get("item_id", ""))),
                "check_text": it["check_text"],
                "reject_text": it.get("reject_text"),
                "check_type": it.get("check_type", "presence"),
                "sources": it.get("sources") or [],
            })
            continue
        # legacy rejection-catalog schema.
        rid = it.get("rule_id")
        if not rid or rid == "~":
            rid = f"CAT-{it.get('id', '?')}"
        parts = [it.get("item", ""), it.get("requirement", ""), it.get("cross_check", "")]
        check_text = " — ".join(p for p in parts if p).strip() or str(it.get("item", rid))
        reject = it.get("reject_as") or it.get("reject_text")
        if isinstance(reject, list):
            reject = reject[0] if reject else None
        rows.append({
            "item_id": rid,
            "section": _section_of(rid),
            "check_text": check_text,
            "reject_text": reject,
            "check_type": it.get("check_type", "presence"),
            "sources": it.get("sources") or [],
        })
    return rows


def checklist_for(amc_code: str) -> Path:
    """Prefer a per-AMC native checklist (`checklist_<amc>.yaml`) if present, else
    the default rejection catalog — dynamic onboarding, zero engine change."""
    cand = _DEFAULT_CHECKLIST.parent / f"checklist_{amc_code.lower()}.yaml"
    return cand if cand.exists() else _DEFAULT_CHECKLIST


def checklist_hash(path: Path = _DEFAULT_CHECKLIST) -> str:
    """Stable content hash pinning a compiled artifact to a checklist version +
    binder prompt + schema (§7 S-11). A schema or prompt change reflows bindings."""
    from app.extraction.schema import schema_loader
    h = hashlib.sha256()
    h.update(path.read_bytes() if path.exists() else b"")
    h.update(BINDER_PROMPT_VERSION.encode())
    h.update(schema_loader.schema_version.encode())
    return h.hexdigest()[:16]


# ── source-field binding (deterministic, always available) ────────────────────

def _canon(field: str) -> str:
    from app.rules.catalog import _canon as cat_canon
    return cat_canon(field)


def _labels_from_sources(sources: List[dict]) -> Tuple[List[str], bool]:
    """Canonical, known-only labels named by the checklist's `sources`. Also
    returns whether any source references the engagement/contract doc."""
    labels: List[str] = []
    needs_other_doc = False
    for src in sources or []:
        doc = src.get("doc", "appraisal")
        if doc in ("engagement", "contract"):
            needs_other_doc = True
        for f in (src.get("fields") or []):
            lbl = LD.canonical_label(_canon(f))
            if LD.is_known(lbl) and lbl not in labels:
                labels.append(lbl)
        if src.get("maps") or src.get("photos"):
            needs_other_doc = needs_other_doc  # visual handled separately
    return labels, needs_other_doc


def _heuristic_labels(check_text: str, limit: int = 6) -> List[str]:
    """Keyword scan of the check text against label meanings — the no-LLM binder."""
    text = check_text.lower()
    scored: List[Tuple[int, str]] = []
    for lbl, mean in LD.label_meanings().items():
        tokens = set(re.findall(r"[a-z]{4,}", lbl.replace("comp_N_", "") + " " + mean.lower()))
        hits = sum(1 for t in tokens if t in text)
        if hits:
            scored.append((hits, lbl))
    scored.sort(key=lambda x: (-x[0], x[1]))
    return [lbl for _s, lbl in scored[:limit]]


def _expects_from(check_text: str) -> str:
    m = _COUNT_RX.search(check_text)
    if m:
        return f"count(comp_* present) >= {m.group(1)}"
    return ""


# ── LLM binder (§3 step 1) ────────────────────────────────────────────────────

def _binder_prompt() -> str:
    p = Path(__file__).parent.parent.parent / "prompts" / f"{BINDER_PROMPT_VERSION}.txt"
    return p.read_text(encoding="utf-8") if p.exists() else _BINDER_SYSTEM


_BINDER_SYSTEM = (
    "You bind ONE appraisal-QC check to the canonical field labels that exist in "
    "extraction. You are given the check's section, the check text, and the "
    "candidate labels IN SCOPE for that section (label: meaning). Return JSON "
    "only: {\"bound_labels\":[...only labels copied verbatim from candidate_labels, "
    "the MINIMAL set the check is about...], \"scope\":\"subject|comps|"
    "cross_document|narrative|visual|unbound\", \"expects\":\"short machine hint "
    "e.g. count(comp_* >= 6)\", \"judgeable\":\"text|visual|needs_engagement\", "
    "\"binder_confidence\":0.0-1.0}. Never invent a label. A confident wrong "
    "binding is the worst outcome — if nothing fits, bound_labels=[], "
    "scope=unbound, low confidence."
)


def _llm_bind(client, check_text: str, section: str) -> Optional[Dict[str, Any]]:
    """Section-scoped binder call (Step 1). The candidate labels are narrowed to
    the check's section (+ anchors), so the model disambiguates by meaning within
    a small set instead of token-matching across the whole ~260-label schema."""
    if client is None or not getattr(client, "available", False):
        return None
    import json
    system = _binder_prompt()
    user = json.dumps({
        "section": section,
        "check_text": check_text,
        "candidate_labels": LD.scoped_dictionary_text(section),
    })
    res = client.complete(f"bind:{BINDER_PROMPT_VERSION}:{section}", system, user, max_tokens=1200)
    if not res.ok or not isinstance(res.data, dict):
        return None
    return res.data


# ── the compile step ─────────────────────────────────────────────────────────

def _compile_item(row: Dict[str, Any], client) -> CompiledItem:
    check_text = row["check_text"]
    item = CompiledItem(
        item_id=row["item_id"], check_text=check_text,
        reject_text=row.get("reject_text"), section=row.get("section", "other"),
    )

    # Visual → constant card, never the LLM (§3).
    if row.get("check_type") == "cross_modal" or _VISUAL_RX.search(check_text):
        item.scope = "visual"
        item.judgeable = "visual"
        item.bound_by = "constant"
        item.bound_labels, _ = _labels_from_sources(row.get("sources", []))
        return item

    src_labels, needs_other = _labels_from_sources(row.get("sources", []))
    item.bound_labels = list(src_labels)
    item.expects = _expects_from(check_text)
    is_conditional = bool(_COND_RX.search(check_text) and _THEN_RX.search(check_text))

    data = _llm_bind(client, check_text, item.section)
    if data:
        # Section scoping guarantees the candidates were already in-scope; still
        # filter to known labels (drift guard) and to the section's candidate set
        # so a hallucinated out-of-scope label can never survive. `_label_token`
        # strips any "label: meaning" the model copied verbatim back to the label.
        scoped = LD.scoped_labels(item.section)
        extra = [LD.canonical_label(_label_token(l)) for l in (data.get("bound_labels") or [])
                 if LD.is_known(_label_token(l)) and LD.canonical_label(_label_token(l)) in scoped]
        for l in extra:
            if l not in item.bound_labels:
                item.bound_labels.append(l)
        scope = data.get("scope")
        if scope in ("subject", "comps", "cross_document", "cross_section", "narrative", "unbound"):
            item.scope = scope
        item.expects = item.expects or (data.get("expects") or "")
        jd = data.get("judgeable")
        if jd in ("text", "visual", "needs_engagement", "needs_contract"):
            item.judgeable = "needs_engagement" if jd == "needs_contract" else jd
        cond = data.get("conditional")
        if isinstance(cond, dict):
            item.conditional = _filter_conditional(cond)
        item.bound_by = "llm"
        item.binder_confidence = float(data.get("binder_confidence", 0.85) or 0.85)
    elif item.bound_labels:
        item.bound_by = "authored"
        item.binder_confidence = 0.9   # authored source fields — trustworthy
    else:
        # No LLM client and no authored sources: DO NOT token-soup a binding.
        # A guessed binding is exactly what caused the false rejects. Leave it
        # unbound + zero confidence so the gate flags it and it cannot go active.
        item.bound_by = "unbound"
        item.binder_confidence = 0.0

    # AnnexB Part 2: no LLM conditional structure → derive one heuristically.
    if is_conditional and not item.conditional:
        item.conditional = _heuristic_conditional(check_text)
        item.scope = "cross_section"
        item.binder_confidence = min(item.binder_confidence, 0.6)

    # scope/judgeable defaults from deterministic signals.
    if item.scope == "unbound" and item.bound_labels:
        if needs_other or row.get("check_type") == "cross_document":
            item.scope = "cross_document"
        elif any(l.startswith("comp_N_") or l.startswith("comp_") for l in item.bound_labels):
            item.scope = "comps"
        else:
            item.scope = "subject"
    if (needs_other or row.get("check_type") == "cross_document") and item.judgeable == "text":
        item.judgeable = "needs_engagement"
    # Only truly label-less items are unbound. A conditional check carries its
    # labels in `conditional` (all_labels), not `bound_labels` — don't reset it.
    if not item.all_labels:
        item.scope = "unbound"
    return item


def _label_token(raw: str) -> str:
    """A binder may echo a candidate line verbatim ("label: meaning (type)"); we
    only ever want the label token before the first colon."""
    return (raw or "").split(":", 1)[0].strip()


def _filter_conditional(cond: dict) -> Optional[Dict[str, List[str]]]:
    c = [LD.canonical_label(_label_token(l)) for l in (cond.get("condition_labels") or [])
         if LD.is_known(_label_token(l))]
    q = [LD.canonical_label(_label_token(l)) for l in (cond.get("consequence_labels") or [])
         if LD.is_known(_label_token(l))]
    return {"condition_labels": c, "consequence_labels": q} if (c or q) else None


def _heuristic_conditional(check_text: str) -> Dict[str, List[str]]:
    """Split "if <condition> then/must <consequence>" and bind each clause to
    known labels. Age-triggered conditions always include year_built/actual_age
    so the runtime can derive age even when the clause names it only in prose."""
    m = _THEN_RX.search(check_text)
    cond_clause = check_text[:m.start()] if m else check_text
    cons_clause = check_text[m.end():] if m else ""
    cond_labels = _heuristic_labels(cond_clause, limit=4)
    if _AGE_RX.search(cond_clause):
        for l in ("year_built", "actual_age", "effective_age"):
            if LD.is_known(l) and l not in cond_labels:
                cond_labels.append(l)
    cons_labels = _heuristic_labels(cons_clause, limit=4) if cons_clause else []
    return {"condition_labels": cond_labels, "consequence_labels": cons_labels}


def compile_checklist(amc_code: str, path: Optional[Path] = None,
                      client=None, force: bool = False) -> List[CompiledItem]:
    """Compile (or load cached) the checklist for `amc_code`. The checklist is the
    per-AMC native file when present, else the default catalog. Cached by hash, so
    a second call is a file read; recompiles when the checklist/schema/prompt
    change the hash. `client=None` → deterministic (source+heuristic) bindings."""
    path = path or checklist_for(amc_code)
    chash = checklist_hash(path)
    out_path = _COMPILED_DIR / amc_code / f"{chash}.yaml"
    if out_path.exists() and not force:
        return load_compiled(out_path)

    rows = load_checklist(path)
    items = [_compile_item(r, client) for r in rows]
    _write_compiled(out_path, amc_code, chash, items, status=STATUS_DRAFT)
    review = _review_needed(items)
    if review:
        _write_review_needed(out_path.parent / "REVIEW_NEEDED.yaml", amc_code, chash, review)
    logger.info("compiler: compiled %d items for %s (%d need review, status=draft) → %s",
                len(items), amc_code, len(review), out_path)
    return items


def _review_needed(items: List[CompiledItem]) -> List[CompiledItem]:
    """AnnexB Part 1 Step 3/4: items a human must eyeball — empty bindings (that
    aren't intentional visual/unbound) or binder confidence below the floor."""
    out = []
    for it in items:
        if it.judgeable == "visual":
            continue
        if not it.bound_labels and not it.conditional:
            out.append(it)
        elif it.binder_confidence < _REVIEW_CONF_FLOOR:
            out.append(it)
    return out


def _write_review_needed(path: Path, amc_code: str, chash: str,
                         items: List[CompiledItem]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    doc = {
        "meta": {"amc_code": amc_code, "checklist_hash": chash,
                 "note": "Human review: fix a binding (edit a label id) or confirm "
                         "unbound. Never write logic here.", "count": len(items)},
        "items": [{**it.to_yaml()} for it in items],
    }
    path.write_text(yaml.safe_dump(doc, sort_keys=False, allow_unicode=True), encoding="utf-8")


def load_compiled(path: Path) -> List[CompiledItem]:
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return [CompiledItem.from_yaml(d) for d in raw.get("items", [])]


def compiled_path(amc_code: str, path: Optional[Path] = None) -> Path:
    """Path of the compiled artifact for this AMC's current checklist version."""
    path = path or checklist_for(amc_code)
    return _COMPILED_DIR / amc_code / f"{checklist_hash(path)}.yaml"


def bundle_meta(path: Path) -> Dict[str, Any]:
    """Read just the `meta` block of a compiled artifact (status, hash, report)."""
    if not path.exists():
        return {}
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return raw.get("meta", {}) or {}


def bundle_status(path: Path) -> str:
    """Sign-off state of a compiled artifact: draft | validated | active | (none)."""
    return bundle_meta(path).get("status", STATUS_DRAFT) if path.exists() else "none"


def set_bundle_status(path: Path, status: str, approved_by: Optional[str] = None,
                      validation_report: Optional[Dict[str, Any]] = None) -> None:
    """Flip a compiled artifact's status in place (draft→validated→active). Keeps
    every item untouched — only the meta changes (§ sign-off)."""
    import datetime
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    meta = raw.setdefault("meta", {})
    meta["status"] = status
    if validation_report is not None:
        meta["validation_report"] = validation_report
    if status == STATUS_ACTIVE:
        meta["approved_by"] = approved_by or "unknown"
        meta["approved_at"] = datetime.datetime.utcnow().isoformat(timespec="seconds") + "Z"
    path.write_text(yaml.safe_dump(raw, sort_keys=False, allow_unicode=True), encoding="utf-8")


def _write_compiled(path: Path, amc_code: str, chash: str, items: List[CompiledItem],
                    status: str = STATUS_DRAFT) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    doc = {
        "meta": {"amc_code": amc_code, "checklist_hash": chash,
                 "binder_prompt": BINDER_PROMPT_VERSION, "compiler": __version__,
                 "count": len(items), "status": status},
        "items": [it.to_yaml() for it in items],
    }
    path.write_text(yaml.safe_dump(doc, sort_keys=False, allow_unicode=True), encoding="utf-8")


def _section_of(rule_id: str) -> str:
    rid = (rule_id or "").upper()
    for prefix, sec in (("ORD", "order"), ("S-", "subject"), ("N-", "neighborhood"),
                        ("ST", "site"), ("I-", "improvements"), ("SCA", "sales_comparison"),
                        ("CA", "cost"), ("R-", "reconciliation"), ("C-", "contract"),
                        ("SIG", "signature"), ("ADD", "addendum"), ("VAL", "reconciliation"),
                        ("CG", "sales_comparison"), ("DOC", "order"), ("FHA", "fha")):
        if rid.startswith(prefix):
            return sec
    return "other"
