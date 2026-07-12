"""
rules.packet (pkt-1.0.0) — SHALqc-CORE §4.1 Fact Packet builder.

Code assembles a structured packet per rule — no LLM involvement — that the C2
judge reasons over. Per CORE §0, the deterministic rule body already ran and
produced a provisional verdict; that verdict + its comparison become the
packet's `machine_observations` — "sworn testimony" the judge is handed so it
stops re-deriving arithmetic and spends capacity on meaning. The judge has final
say (CORE §0), but the validator re-checks any numeric claim it makes.

A packet carries ONLY packet-scoped facts (field values, norms, confidences,
pages, machine observations, page-scoped snippets) — never the whole document
(anti-drift / anti-injection, CORE §4.1).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional

from app.normalize import normalize as _normalize
from app.rules.context import QCContext
from app.rules.verdict import Verdict

__version__ = "pkt-1.0.0"


@dataclass
class FactPacket:
    rule_id: str
    rule_version: int
    requirement: str
    fields: Dict[str, Dict[str, Any]]
    machine_observations: List[Dict[str, Any]]
    context_snippets: List[Dict[str, Any]]
    missing_fields: List[str]
    amc_notes: str = ""
    # the deterministic pass's provisional status — testimony, not the verdict.
    provisional_status: str = ""

    def to_json(self) -> Dict[str, Any]:
        return asdict(self)


def _field_entry(ev) -> Dict[str, Any]:
    from app.extraction.schema import schema_loader
    fd = schema_loader.get_field(ev.field.split(".", 1)[-1]) if ev.field else None
    return {
        "value": ev.value,
        "norm": _normalize(fd, ev.value) if ev.value is not None else None,
        "source": ev.source,
        "confidence": round(ev.confidence, 3),
        "page": ev.page,
        "location_quality": ev.location_quality,
        "document": ev.document,
    }


def build_packet(provisional: Verdict, ctx: QCContext, requirement: str = "",
                 amc_notes: str = "") -> FactPacket:
    """Assemble the CORE §4.1 packet from a rule's provisional (deterministic)
    verdict. The provisional status + message become a machine observation."""
    fields: Dict[str, Dict[str, Any]] = {}
    snippets: List[Dict[str, Any]] = []
    missing: List[str] = []

    for ev in provisional.evidence:
        key = ev.field if ev.document == "appraisal" else f"{ev.document}.{ev.field}"
        fields[key] = _field_entry(ev)
        if ev.value is None:
            missing.append(key)
        elif ev.page:
            snippets.append({"doc": ev.document, "page": ev.page, "text": str(ev.value)})

    machine_observations = [{
        "id": "MO1",
        "check": requirement or provisional.rule_id,
        "deterministic_status": provisional.status.value,
        "detail": provisional.message or f"deterministic pass returned {provisional.status.value}",
    }]

    return FactPacket(
        rule_id=provisional.rule_id,
        rule_version=1,
        requirement=requirement or provisional.rule_id,
        fields=fields,
        machine_observations=machine_observations,
        context_snippets=snippets,
        missing_fields=missing,
        amc_notes=amc_notes,
        provisional_status=provisional.status.value,
    )
