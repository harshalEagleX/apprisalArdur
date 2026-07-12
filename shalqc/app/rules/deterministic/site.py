"""
Deterministic site-section rules (T1) — SHALqc.md §5.

Presence + a small format check. Zoning compliance and highest-and-best-use are
single-document (appraisal) checks, so their needs[] name only the appraisal
field; the gate handles missing/low-confidence, leaving the body to judge the
value on trusted data.
"""

from __future__ import annotations

import re

from app.rules import helpers as H
from app.rules.context import QCContext
from app.rules.registry import rule
from app.rules.verdict import Status, Verdict


# ── ST-5 Zoning compliance marked ───────────────────────────────────────────

@rule(id="ST-5", checklist="19", section="site", version=1,
      needs=["zoning_compliance"], name="Zoning compliance marked")
def st5_zoning(ctx: QCContext) -> Verdict:
    return H.passed(ctx, "ST-5", "zoning_compliance")


# ── ST-6 Highest & best use is present ──────────────────────────────────────

@rule(id="ST-6", checklist="20", section="site", version=1,
      needs=["highest_and_best_use"], name="Highest & best use present")
def st6_hbu(ctx: QCContext) -> Verdict:
    return H.passed(ctx, "ST-6", "highest_and_best_use")


# ── ST-8 FEMA flood zone format ─────────────────────────────────────────────

_FEMA_ZONE = re.compile(r"^(A|AE|AH|AO|AR|A99|V|VE|X|B|C|D)$", re.I)


@rule(id="ST-8", checklist="24", section="site", version=1,
      needs=["flood_zone_id"], name="FEMA flood zone valid")
def st8_flood(ctx: QCContext) -> Verdict:
    zone = (ctx.appraisal.value("flood_zone_id") or "").strip()
    # Regex used ONLY for format validation (a legitimate regex job, SHALqc.md
    # §5 T1) — never to render the verdict from raw text.
    if _FEMA_ZONE.match(zone):
        return H.passed(ctx, "ST-8", "flood_zone_id")
    return H.fail(ctx, "ST-8", "flood_zone_id",
                  message_key="ST-8.flood_zone_invalid",
                  message=f"FEMA flood zone '{zone}' is not a recognized zone code.")
