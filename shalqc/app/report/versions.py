"""
report.versions — assembles the SHALqc.md §1 run fingerprint.

`report.versions` must appear in every response (§12 DoD #5): the semver of
every component that touched the run, plus content hashes of the active config
files, so any result is reproducible/auditable. A run's fingerprint = hash of
all these + the document content hash (the document hash is added by the caller
that has the package bytes — §14 G-3 idempotency).
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Dict

_CONFIG_DIR = Path(__file__).parent.parent.parent / "config"


def _mod_version(dotted: str) -> str:
    try:
        mod = __import__(dotted, fromlist=["__version__"])
        return getattr(mod, "__version__", "unknown")
    except Exception:
        return "unavailable"


def _file_hash(path: Path) -> str:
    if not path.exists():
        return "absent"
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()[:16]


def component_versions() -> Dict[str, str]:
    """Every component's semver (SHALqc.md §1 table), for the ones that exist."""
    from app.extraction.schema import schema_loader
    from app.normalize.normalizer import normalizer
    from app.routing.router import router

    return {
        "schema": schema_loader.schema_version,
        "normalizer": normalizer.version,
        "confidence_router": router.version,
        "extractor.xml": _mod_version("app.extraction.xml_extractor"),
        "extractor.pdf_digital": _mod_version("app.extraction.pdf_digital"),
        "extractor.pdf_scanned": _mod_version("app.extraction.pdf_scanned"),
        "extractor.grid": _mod_version("app.extraction.grid_extractor"),
        "extractor.engagement": _mod_version("app.extraction.engagement"),
        "extractor.llm_gapfill": _mod_version("app.extraction.llm_gapfill"),
        "extractor.merge": _mod_version("app.extraction.merge"),
        "plausibility": _mod_version("app.extraction.plausibility"),
        "rule_library": _mod_version("app.rules"),
        "rule_engine": _mod_version("app.rules.engine"),
        "profile_loader": _mod_version("app.profiles.loader"),
        "report_builder": _mod_version("app.report.builder"),
        "api": _mod_version("app.api.health"),
    }


_PROMPTS_DIR = Path(__file__).parent.parent.parent / "prompts"


def config_hashes() -> Dict[str, str]:
    """Content hashes of the config that shapes a run (SHALqc.md §17 / CORE §6:
    fingerprint includes config AND prompt hashes so a threshold or prompt edit
    changes the fingerprint)."""
    return {
        "field_schema.yaml": _file_hash(_CONFIG_DIR / "field_schema.yaml"),
        "normalizer.yaml": _file_hash(_CONFIG_DIR / "normalizer.yaml"),
        "routing.yaml": _file_hash(_CONFIG_DIR / "routing.yaml"),
        "prompt.judge_v1": _file_hash(_PROMPTS_DIR / "judge_v1.txt"),
    }


def report_versions(profile=None) -> Dict[str, object]:
    v = {"components": component_versions(), "config_hashes": config_hashes()}
    if profile is not None:
        v["amc_profile"] = getattr(profile, "version", "") or getattr(profile, "amc_code", "")
    return v


def fingerprint(profile=None, document_hash: str = "") -> str:
    """One-line reproducibility fingerprint = hash(all versions + config + doc)."""
    payload = repr(report_versions(profile)) + "|" + document_hash
    return "sha256:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()
