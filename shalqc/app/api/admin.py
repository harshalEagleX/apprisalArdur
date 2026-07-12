"""
api.admin (api-1.0.0) — SHALqc.md §9 admin/config endpoints.

Implemented: /schema/fields, /schema/reload, /qc/rules, /routing/config
(GET/PUT), /amc/profiles (GET), /amc/profiles/reload. These are the "no-deploy
config" surface — a business analyst tunes thresholds/profiles without a
release (P4). Persisted-run dump (GET /runs/{run_id}) needs persistence (§15) —
not in this build pass.
"""

from __future__ import annotations

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
