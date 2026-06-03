"""
Reviewer-facing QC report builder.

Reads the persisted QC results for a transaction from adaptive_validation_results
and assembles the structured report a reviewer dashboard / demo consumes:
overall outcome, counts, and findings grouped by section — each with its status,
the verbatim message, the fields involved, and the evidence (document, value,
confidence, page) for the side-by-side view.

Kept separate from the engine so the read path (dashboard/API) does not depend
on re-running extraction — it serves whatever the last QC run persisted.
"""

from __future__ import annotations

import json
from typing import Dict, List

# DB result column (pass|fail|warning|info|skipped) -> our 5-state name.
_STATUS_FROM_DB = {
    "pass": "PASS", "fail": "FAIL", "warning": "VERIFY",
    "info": "NOT_APPLICABLE", "skipped": "SKIPPED",
}
_EXCEPTION = {"FAIL", "VERIFY", "HOLD"}


def _empty(transaction_id: str) -> Dict:
    return {"transaction_id": transaction_id, "overall": "PASS", "counts": {},
            "exception_count": 0, "rule_count": 0, "sections": {}}


def _overall(statuses: List[str]) -> str:
    s = set(statuses)
    if "HOLD" in s:
        return "HOLD"
    if "FAIL" in s:
        return "FAIL"
    if "VERIFY" in s:
        return "VERIFY"
    return "PASS"


def transaction_report(transaction_id: str) -> Dict:
    """Build the reviewer JSON for a transaction's most recent QC results."""
    from app.database import get_db
    from app.models.db_models import ValidationResultRow

    with get_db() as session:
        rows = (session.query(ValidationResultRow)
                .filter_by(transaction_id=transaction_id)
                .order_by(ValidationResultRow.validated_at.desc())
                .all())
        if not rows:
            return _empty(transaction_id)
        # Scope to the most recent QC run only: every row of one run is persisted
        # within seconds, so keep rows within 3 minutes of the newest timestamp.
        # This prevents stale findings from earlier runs leaking into the report.
        import datetime as _dt
        newest = rows[0].validated_at
        cutoff = newest - _dt.timedelta(minutes=3)
        latest: Dict[str, ValidationResultRow] = {}
        for r in rows:
            if r.validated_at < cutoff:
                break
            key = f"{r.rule_id}|{r.fields_involved}"
            if key not in latest:
                latest[key] = r

        findings = []
        for r in latest.values():
            snap = json.loads(r.field_values_snapshot or "{}")
            status = snap.get("status") or _STATUS_FROM_DB.get(r.result, r.result.upper())
            findings.append({
                "rule_id": r.rule_id,
                "checklist_num": snap.get("checklist_num"),
                "section": r.rule_category,
                "status": status,
                "message": r.explanation,
                "fields": json.loads(r.fields_involved or "[]"),
                "confidence": r.confidence,
                "template_id": snap.get("template_id"),
                "evidence": snap.get("evidence", []),
            })

    statuses = [f["status"] for f in findings]
    counts: Dict[str, int] = {}
    for s in statuses:
        counts[s] = counts.get(s, 0) + 1

    # group by section, exceptions first
    sections: Dict[str, List] = {}
    for f in sorted(findings, key=lambda f: (f["status"] not in _EXCEPTION, f["rule_id"])):
        sections.setdefault(f["section"], []).append(f)

    return {
        "transaction_id": transaction_id,
        "overall": _overall(statuses),
        "counts": counts,
        "exception_count": sum(1 for s in statuses if s in _EXCEPTION),
        "rule_count": len(findings),
        "sections": sections,
    }


_ICON = {"PASS": "✓", "FAIL": "✗", "VERIFY": "?", "HOLD": "!",
         "NOT_APPLICABLE": "–", "SKIPPED": "·"}


def render_report_text(report: Dict) -> str:
    """Render the reviewer report as a readable text/markdown document."""
    L = []
    L.append(f"# QC Report — {report['transaction_id']}")
    L.append(f"\n**Overall: {report['overall']}**  ·  "
             f"{report['exception_count']} exception(s) of {report['rule_count']} rules")
    c = report["counts"]
    L.append("  ·  ".join(f"{_ICON.get(k,'')} {k} {v}" for k, v in c.items()))
    L.append("\n## Findings requiring attention\n")
    any_exc = False
    for section, findings in report["sections"].items():
        exc = [f for f in findings if f["status"] in _EXCEPTION]
        if not exc:
            continue
        any_exc = True
        L.append(f"### {section.replace('_', ' ').title()}")
        for f in exc:
            L.append(f"- {_ICON[f['status']]} **{f['rule_id']}** ({f['status']}): {f['message']}")
            for e in f.get("evidence", []):
                if e.get("value"):
                    L.append(f"    - {e['document']}: `{e['value']}`"
                             f" (conf {e.get('confidence', 0):.2f}"
                             f"{', p'+str(e['page']) if e.get('page') else ''})")
        L.append("")
    if not any_exc:
        L.append("_No exceptions — all checked rules passed._\n")
    # passed rules summary
    passed = [f["rule_id"] for sec in report["sections"].values()
              for f in sec if f["status"] == "PASS"]
    if passed:
        L.append(f"## Auto-cleared ({len(passed)}): " + ", ".join(sorted(set(passed))))
    return "\n".join(L)
