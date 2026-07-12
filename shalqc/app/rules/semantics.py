"""
rules.semantics (sem-1.0.0) — the SIGNIFICANCE resolver (pkt-1.1.0 pre-stage).

When a rule-needed field is MISSING, blanket-VERIFY is wrong: a blank contract
on a refinance is CORRECT; a blank basement on a slab is CORRECT; a blank AMC
email is IRRELEVANT; and a blank that should have come from the XML is OUR bug,
not the appraiser's. This layer, authored in config/field_semantics.yaml, tells
the engine WHY a blank is blank. Nothing here is probabilistic — it is a YAML
dictionary + condition evaluator over already-extracted values.

resolve(field, ctx) → (resolution, meaning):
  PRESENT        value is there (caller shouldn't call us then)
  EXPECTED_BLANK required_when condition is false → requirement satisfied
  INFO_MISSING   informational field → never a finding
  VERIFY_MISSING material/critical, PDF-sourced or condition unevaluable → reviewer
  EXTRACTION_GAP material/critical, XML-sourced AND XML present → engine health

Hard safety rule: a condition we cannot evaluate NEVER yields EXPECTED_BLANK — it
degrades to VERIFY_MISSING so a real defect is never hidden by a blind assumption.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Optional, Tuple

import yaml

from app.rules.context import QCContext

__version__ = "sem-1.0.0"

logger = logging.getLogger(__name__)

_PATH = Path(__file__).parent.parent.parent / "config" / "field_semantics.yaml"

PRESENT = "PRESENT"
EXPECTED_BLANK = "EXPECTED_BLANK"
INFO_MISSING = "INFO_MISSING"
VERIFY_MISSING = "VERIFY_MISSING"
EXTRACTION_GAP = "EXTRACTION_GAP"

_RAW = None


def _load():
    global _RAW
    if _RAW is None:
        _RAW = yaml.safe_load(_PATH.read_text(encoding="utf-8")) if _PATH.exists() else {}
    return _RAW or {}


def reload():
    global _RAW
    _RAW = None


def _semantics_for(field: str):
    cfg = _load()
    if field in (cfg.get("informational") or []):
        return {"materiality": "informational"}
    fields = cfg.get("fields") or {}
    if field in fields:
        return fields[field]
    # section default via schema
    from app.extraction.schema import schema_loader
    fd = schema_loader.get_field(field)
    sections = getattr(fd, "sections", []) if fd else []
    for sec in sections:
        d = (cfg.get("section_defaults") or {}).get(sec)
        if d:
            return d
    return {"materiality": "material"}


def _expected_source(field: str, sem: dict) -> str:
    if sem.get("expected_source"):
        return sem["expected_source"]
    from app.extraction.schema import schema_loader
    fd = schema_loader.get_field(field)
    return fd.primary_source if fd else "xml"


# ── condition evaluator (tiny, safe) ────────────────────────────────────────

def _field_val(ctx: QCContext, name: str) -> Optional[str]:
    # allow assignment_type to fall through to the derived transaction_type
    v = ctx.appraisal.value(name) or ctx.engagement.value(name)
    if name == "assignment_type" and not v:
        return ctx.transaction_type
    return v


def _eval_atom(ctx: QCContext, atom: str) -> Optional[bool]:
    """Evaluate one '<field> <op> <value>' clause. None = unevaluable."""
    atom = atom.strip()
    m = re.match(r"(\w+)\s+in\s*\[([^\]]*)\]", atom, re.I)
    if m:
        field, opts = m.group(1), [o.strip().lower() for o in m.group(2).split(",") if o.strip()]
        v = _field_val(ctx, field)
        if v is None:
            return None
        return v.strip().lower() in opts
    m = re.match(r"(\w+)\s+contains\s+(.+)", atom, re.I)
    if m:
        field, val = m.group(1), m.group(2).strip().strip('"').lower()
        v = _field_val(ctx, field)
        if v is None:
            return None
        return val in v.strip().lower()
    m = re.match(r"(\w+)\s*(==|!=)\s*(.+)", atom)
    if m:
        field, op, val = m.group(1), m.group(2), m.group(3).strip().strip('"').lower()
        v = _field_val(ctx, field)
        if v is None:
            return None
        eq = v.strip().lower() == val
        return eq if op == "==" else (not eq)
    return None


def _eval_condition(ctx: QCContext, cond: str) -> Optional[bool]:
    """AND-joined clauses. None if ANY clause is unevaluable (safety)."""
    if not cond or cond.strip().lower() == "always":
        return True
    result = True
    for clause in re.split(r"\bAND\b", cond, flags=re.I):
        r = _eval_atom(ctx, clause)
        if r is None:
            return None
        result = result and r
    return result


# ── resolver ────────────────────────────────────────────────────────────────

def resolve(field: str, ctx: QCContext) -> Tuple[str, str]:
    """Resolve a MISSING rule-needed field to a resolution + plain meaning."""
    sem = _semantics_for(field)
    materiality = (sem.get("materiality") or "material").lower()

    if materiality == "informational":
        return INFO_MISSING, f"{field} is informational — a blank is acceptable."

    required = _eval_condition(ctx, sem.get("required_when", "always"))
    if required is None:
        return VERIFY_MISSING, f"{field} may be required (condition could not be evaluated) — please confirm."
    if required is False:
        return EXPECTED_BLANK, f"{field} is correctly blank ({sem.get('required_when')} is not met)."

    # required — decide whose fault a blank is
    src = _expected_source(field, sem)
    has_xml = ctx.appraisal.present  # appraisal set includes XML-sourced fields
    if src == "xml" and has_xml:
        return EXTRACTION_GAP, f"{field} should be in the XML but was not read — engine extraction gap."
    return VERIFY_MISSING, f"{field} is required but not present — please check the report."


# maps a resolution → how the engine gate should render it
def gate_verdict(spec, field: str, ctx: QCContext, Verdict, Status):
    """Build the gate Verdict for a missing needed field, using the resolver."""
    resolution, meaning = resolve(field, ctx)
    ev = [ctx.resolve(field)]
    common = dict(rule_id=spec.rule_id, section=spec.section, checklist_num=spec.checklist_num,
                  tier=spec.tier, evidence=ev, fields_involved=[field])
    if resolution == EXPECTED_BLANK:
        return Verdict(status=Status.PASS, message=meaning, degraded_reason="expected_blank", **common)
    if resolution == INFO_MISSING:
        return Verdict(status=Status.NOT_APPLICABLE, message=meaning,
                       degraded_reason="info_missing", **common)
    if resolution == EXTRACTION_GAP:
        return Verdict(status=Status.VERIFY, confidence=0.5, message=meaning,
                       degraded_reason="extraction_gap", actionable_by="engine", **common)
    # VERIFY_MISSING → reviewer
    return Verdict(status=Status.VERIFY, confidence=0.5, message=meaning,
                   degraded_reason="verify_missing", **common)
