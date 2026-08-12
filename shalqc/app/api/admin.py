"""
api.admin (api-1.0.0) — SHALqc.md §9 admin/config endpoints.

Implemented: /schema/fields, /schema/reload, /qc/rules, /routing/config
(GET/PUT), /amc/profiles (GET), /amc/profiles/reload. These are the "no-deploy
config" surface — a business analyst tunes thresholds/profiles without a
release (P4). Persisted-run dump (GET /runs/{run_id}) needs persistence (§15) —
not in this build pass.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

from fastapi import APIRouter, Body

from app.extraction.schema import schema_loader
from app.normalize.normalizer import normalizer
from app.profiles.loader import profile_loader
from app.report.wording import wording_book
from app.routing.router import router as conf_router
from app.rules.registry import all_rules

__version__ = "api-1.0.0"

router = APIRouter(tags=["admin"])


@router.get("/schema/fields")
def schema_fields():
    return {
        "schema_version": schema_loader.schema_version,
        "count": len(schema_loader.all_fields()),
        "fields": [
            {"canonical_name": f.canonical_name, "data_type": f.data_type,
             "required": f.required, "sections": f.sections}
            for f in schema_loader.all_fields()
        ],
    }


@router.post("/schema/reload")
def schema_reload():
    schema_loader.reload()
    normalizer.reload()
    return {"status": "reloaded", "schema_version": schema_loader.schema_version,
            "normalizer_version": normalizer.version}


@router.get("/qc/rules")
def qc_rules():
    return {
        "count": len(all_rules()),
        "rules": [
            {"rule_id": r.rule_id, "checklist": r.checklist_num, "section": r.section,
             "version": r.version, "tier": r.tier, "needs": r.needs, "name": r.name}
            for r in all_rules()
        ],
    }


@router.get("/routing/config")
def get_routing():
    return {"version": conf_router.version, "config": conf_router._raw}  # noqa: SLF001 (read-only dump)


@router.put("/routing/config")
def put_routing(config: Dict[str, Any] = Body(...)):
    # §17 config audit: record before/after content hashes of the change.
    from app.report.versions import _file_hash
    from pathlib import Path
    routing_path = Path(__file__).parent.parent.parent / "config" / "routing.yaml"
    before = _file_hash(routing_path)
    conf_router.update_config(config)
    after = _file_hash(routing_path)
    _audit("routing.yaml", before, after)
    return {"status": "updated", "version": conf_router.version, "before_hash": before, "after_hash": after}


def _audit(what: str, before: str, after: str, who: str = "api") -> None:
    """§17 config audit — best-effort; a no-op when persistence is off."""
    try:
        from app.persistence import repo
        from app.persistence.models import ConfigAudit
        with repo._session() as s:  # noqa: SLF001
            if s is not None:
                s.add(ConfigAudit(who=who, what=what, before_hash=before, after_hash=after))
    except Exception:
        pass


@router.delete("/runs/{order_id}/cache")
def purge_cache(order_id: str):
    """§17 PII — purge this order's cached LLM prompts/responses from Redis
    (borrower PII). Best-effort; no-op when no LLM cache is configured."""
    from app.llm.client import get_client
    client = get_client()
    if client is None or getattr(client, "_redis", None) is None:
        return {"purged": 0, "reason": "no LLM cache configured"}
    try:
        keys = list(client._redis.scan_iter(match="shalqc:llm:*"))  # noqa: SLF001
        if keys:
            client._redis.delete(*keys)
        return {"purged": len(keys)}
    except Exception as exc:
        return {"purged": 0, "error": str(exc)}


# ── runtime settings (the frontend's config surface) ─────────────────────────
#
# These back the settings screen. The contract the UI depends on:
#   GET  returns every editable setting WITH its provenance, so the screen can
#        show whether a value was set here or is falling through to a deploy
#        env var — those are fixed in different places.
#   PUT  is all-or-nothing and returns a field-level error message on rejection,
#        so a bad value lands next to its input instead of as a 500.
#   DELETE clears an override so the setting falls back to the environment.

@router.get("/settings")
def get_settings():
    """Every runtime-editable setting: current value, where it came from, its
    type/range, and the label + help text the UI renders."""
    from app import runtime_config
    return {"settings": runtime_config.effective(),
            "groups": sorted({s["group"] for s in runtime_config.EDITABLE.values()})}


@router.put("/settings")
def put_settings(body: Dict[str, Any] = Body(...)):
    """Apply a batch of setting changes.

    Body: {"updates": {"vision_model": "...", "vision_dpi_grid": 150},
           "who": "harshal@..."}
    """
    from fastapi import HTTPException
    from app import runtime_config

    updates = body.get("updates")
    if not isinstance(updates, dict) or not updates:
        raise HTTPException(status_code=400, detail="'updates' must be a non-empty object")
    try:
        applied = runtime_config.set_many(updates, who=str(body.get("who") or "frontend"))
    except runtime_config.ConfigError as exc:
        # 400 with the message as-is: it is written to be shown to the operator.
        raise HTTPException(status_code=400, detail=str(exc)) from None
    return {"status": "updated", "applied": applied,
            "settings": runtime_config.effective()}


@router.delete("/settings/{key}")
def delete_setting(key: str, who: str = "frontend"):
    """Clear one override so it falls back to the environment."""
    from fastapi import HTTPException
    from app import runtime_config
    try:
        removed = runtime_config.unset([key], who=who)
    except runtime_config.ConfigError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None
    return {"status": "cleared" if removed else "not_set", "key": key,
            "settings": runtime_config.effective()}


@router.get("/amc/profiles")
def get_profiles():
    # list the profile files present; loading _base always works
    base = profile_loader.load(None)
    return {"available": _profile_names(), "base_version": base.version}


@router.post("/amc/profiles/reload")
def reload_profiles():
    profile_loader.reload()
    wording_book.reload()
    return {"status": "reloaded"}


def _profile_names():
    from pathlib import Path
    d = Path(__file__).parent.parent.parent / "config" / "amc_profiles"
    return sorted(p.stem for p in d.glob("*.yaml") if not p.name.endswith(".wording.yaml"))


# ── checklists (frontend-authored, per client and form version) ───────────────
#
# The AMC's checklist was a static YAML nobody could change without a deploy.
# These endpoints make it editable from the admin UI, keyed by (client, form
# version) because 2.6 and 3.6 are different documents — different wording,
# different numbering, and different item fields (3.6 carries polarity/proof/
# evidence_kind because its items are answered from page images).
#
# Saving always writes the CLIENT's own copy; the built-in catalogs are seeds
# and are never edited in place, or one client's edit would silently change
# every client still inheriting them.

_CHECKLIST_VERSIONS = ("2.6", "3.6")


@router.get("/checklists")
def list_checklists():
    """Which (client, version) checklists exist, and whether each is customised."""
    from app.rules.checklist_source import YamlChecklistSource
    src = YamlChecklistSource()
    root = Path(__file__).parent.parent.parent / "config" / "checklists"
    codes = sorted({p.name for p in root.glob("*") if p.is_dir()} |
                   set(_profile_names()) - {"_base"})
    out = []
    for code in codes:
        for ver in _CHECKLIST_VERSIONS:
            path = src.path_for(code, ver)
            own = src.target_path(code, ver)
            if path is None:
                continue
            items = src.load(code, ver)
            out.append({
                "amc_code": code,
                "uad_version": ver,
                "items": len(items),
                # False means this client is still reading the built-in seed, so
                # editing will fork it rather than change the shared file.
                "customised": path == own,
                "source_file": path.name,
                "unclassified": sum(1 for i in items if not i.classified),
            })
    return {"checklists": out, "versions": list(_CHECKLIST_VERSIONS)}


@router.get("/checklists/{amc_code}/{uad_version}")
def get_checklist(amc_code: str, uad_version: str):
    """One checklist, as rows the UI can render and edit."""
    from app.rules.checklist_source import YamlChecklistSource
    src = YamlChecklistSource()
    items = src.load(amc_code, uad_version)
    path = src.path_for(amc_code, uad_version)
    return {
        "amc_code": amc_code.upper(), "uad_version": uad_version,
        "customised": bool(path and path == src.target_path(amc_code, uad_version)),
        "source_file": path.name if path else None,
        "items": [i.as_dict() for i in items],
        # The UI renders these as dropdowns; sending them keeps the vocabulary in
        # one place instead of duplicated in TypeScript.
        "vocabulary": {
            "polarity": ["yes", "no", "unknown"],
            "evidence_kind": ["text", "photo", "map", "sketch", "arithmetic"],
            "proof": ["none", "bracketing", "consistency", "sum"],
        },
    }


@router.put("/checklists/{amc_code}/{uad_version}")
def put_checklist(amc_code: str, uad_version: str, body: Dict[str, Any] = Body(...)):
    """Replace a client's checklist for one form version.

    Validated before it is written, because an invalid checklist does not fail
    loudly at save time — it fails later, per order, as missing or wrong
    verdicts that look like extraction problems.
    """
    from fastapi import HTTPException
    from app.rules.checklist_source import YamlChecklistSource

    items = body.get("items")
    if not isinstance(items, list) or not items:
        raise HTTPException(status_code=400, detail="'items' must be a non-empty list")

    allowed_pol = {"yes", "no", "unknown"}
    seen_ids = set()
    cleaned = []
    for idx, raw in enumerate(items):
        if not isinstance(raw, dict):
            raise HTTPException(status_code=400, detail=f"item {idx} is not an object")
        question = str(raw.get("requirement") or raw.get("check_text") or "").strip()
        if not question:
            raise HTTPException(
                status_code=400,
                detail=f"item {idx} has no question text — an item nobody can read "
                       f"is an item nobody can answer")
        rid = str(raw.get("rule_id") or raw.get("item_id") or "").strip()
        if not rid:
            raise HTTPException(status_code=400, detail=f"item {idx} has no rule_id")
        if rid in seen_ids:
            raise HTTPException(
                status_code=400,
                detail=f"duplicate rule_id '{rid}' — verdicts are keyed by it, so a "
                       f"duplicate makes one item silently overwrite the other")
        seen_ids.add(rid)
        pol = str(raw.get("polarity") or "unknown").strip().lower()
        if pol not in allowed_pol:
            raise HTTPException(
                status_code=400,
                detail=f"item {rid}: polarity '{pol}' is not one of {sorted(allowed_pol)}")
        # An edited item is human-authored, so it counts as classified — that is
        # the whole point of letting a person set polarity in the UI.
        cleaned.append({**raw, "rule_id": rid, "requirement": question,
                        "polarity": pol, "classified": True})

    src = YamlChecklistSource()
    before = src.path_for(amc_code, uad_version)
    path = src.save(amc_code, uad_version, cleaned,
                    {"edited_by": str(body.get("who") or "frontend")})
    _audit(f"checklist:{amc_code.upper()}:{uad_version}",
           before.name if before else "(builtin)", f"{len(cleaned)} items",
           str(body.get("who") or "frontend"))
    return {"status": "saved", "amc_code": amc_code.upper(),
            "uad_version": uad_version, "items": len(cleaned), "file": path.name}


@router.post("/checklists/{amc_code}/{uad_version}/seed")
def seed_checklist(amc_code: str, uad_version: str):
    """Fork the built-in catalog into this client's editable copy."""
    from app.rules.checklist_source import YamlChecklistSource
    src = YamlChecklistSource()
    path = src.seed_from_builtin(amc_code, uad_version)
    if path is None:
        return {"status": "exists_or_empty",
                "detail": "this client already has its own copy, or there is no "
                          "built-in catalogue for that form version"}
    return {"status": "seeded", "file": path.name,
            "items": len(src.load(amc_code, uad_version))}
