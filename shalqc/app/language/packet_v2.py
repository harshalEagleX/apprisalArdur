"""
language.packet_v2 (pkt-2.0.0) — the slim judge packet (§4.1).

Every rule for slimming was learned from the last run's failures:
  * a missing value appears ONLY as a name in `absent_labels` — never as a null
    object (packet size −70%, and the judge can't confuse "unread" with "absent");
  * repeated-N labels auto-expand from PRESENT comps only (§7 S-10);
  * `computed_hints` are the generic arithmetic (hints.py) — no per-rule code;
  * visual items never reach here (they precompile to a constant card, §3).

The packet carries ONLY packet-scoped facts (values + coordinates + hints +
optional section snapshot) — never the whole document (anti-injection, §4.1).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from app.language import hints as H
from app.language.label_dictionary import canonical_label
from app.language.spec import CompiledItem
from app.rules.context import DocView

_MAX_COMPS = 12
_SNAPSHOT_CAP = 60
_PROSE_CAP = 2000   # per prose field, chars — bound packet size, keep the head

# A narrative check judges PROSE (market-conditions commentary, the sales-
# comparison summary, reconciliation remarks…), but many narrative items bind to
# no field or to structured fields only, so the commentary the extractor DID
# capture (xml_extractor: _MarketConditionsDescription, _ReviewComment,
# _SummaryComment, AppraisalAddendumText…) never reached the judge — it was
# left to guess from numbers, forcing REVIEW (2026-07-13 audit row 3). This map
# names, per checklist section, the prose fields to attach to any narrative-class
# packet so the judge reads the actual text.
_SECTION_PROSE: Dict[str, List[str]] = {
    "neighborhood": ["neighborhood_description", "market_conditions_commentary",
                     "mca_neighborhood_analysis_comment", "neighborhood_boundaries"],
    "contract":     ["contract_analysis_comment"],
    "improvements": ["improvements_comments", "condition_comments"],
    "site":         ["site_comments", "zoning_comments"],
    "sales_comparison": ["sales_comparison_summary", "sca_comment", "prior_sale_analysis_comment"],
    "prior_sales":  ["sales_comparison_summary", "prior_sale_analysis_comment"],
    "reconciliation": ["final_reconciliation_comment"],
    "mc_1004":      ["market_conditions_commentary", "mca_neighborhood_analysis_comment"],
    "cost":         ["cost_approach_comment", "final_reconciliation_comment"],
}
# AppraisalAddendumText is overflow narrative that can carry ANY section's
# commentary — attach it to every narrative packet as the general fallback.
_GENERAL_PROSE: List[str] = ["addendum_text"]
_NARRATIVE_SCOPES = ("narrative", "cross_section", "unbound")


@dataclass
class Packet:
    item_id: str
    check_text: str
    reject_text: Optional[str]
    values: Dict[str, Dict[str, Any]]         # label → {v, page, bbox, lq, conflict?}
    absent_labels: List[str]
    computed_hints: List[Dict[str, Any]]
    section_snapshot: Optional[Dict[str, Any]]
    source_notes: Dict[str, Any]
    scope: str = "unbound"
    # AnnexB Part 2: expanded condition/consequence label lists for a conditional
    # check, so the judge (rule 8) evaluates the condition before the consequence.
    conditional: Optional[Dict[str, List[str]]] = None
    # Row-3: the actual narrative prose for the item's section (commentary /
    # summaries / addendum), attached to narrative-class packets so a text check
    # is judged on text, not on a numbers-only snapshot. label → prose.
    narrative_text: Optional[Dict[str, str]] = None

    def raw_values(self) -> Dict[str, Any]:
        """label → scalar value, for the hint layer + grounding."""
        return {k: v.get("v") for k, v in self.values.items()}

    def _judge_values(self) -> Dict[str, Dict[str, Any]]:
        """The judge-facing value map: a cross-document value that carries a
        pre-normalized comparison form (`cmp`) is sent in THAT canonical form, so
        two values that match are byte-identical and the judge has no formatting
        difference to reject on. Everything else (evidence, hints, reviewer display)
        keeps the original `v`. `cmp` is never sent verbatim to the judge."""
        out: Dict[str, Dict[str, Any]] = {}
        for lbl, entry in self.values.items():
            if "cmp" in entry:
                e = {k: v for k, v in entry.items() if k != "cmp"}
                e["v"] = entry["cmp"]
                out[lbl] = e
            else:
                out[lbl] = entry
        return out

    def to_json(self) -> Dict[str, Any]:
        out = {
            "item_id": self.item_id,
            "check_text": self.check_text,
            "reject_text": self.reject_text,
            "values": self._judge_values(),
            "absent_labels": self.absent_labels,
            "computed_hints": self.computed_hints,
            "section_snapshot": self.section_snapshot,
            "source_notes": self.source_notes,
        }
        if self.conditional:
            out["conditional"] = self.conditional
        if self.narrative_text:
            out["narrative_text"] = self.narrative_text
        return out


@dataclass
class Sources:
    """The three DocViews a packet is built from (appraisal is the default doc)."""
    appraisal: DocView
    engagement: Optional[DocView] = None
    contract: Optional[DocView] = None

    @classmethod
    def of(cls, appraisal_fs, engagement_fs=None, contract_fs=None) -> "Sources":
        return cls(
            appraisal=DocView("appraisal", appraisal_fs),
            engagement=DocView("engagement", engagement_fs) if engagement_fs is not None else None,
            contract=DocView("contract", contract_fs) if contract_fs is not None else None,
        )


def _present_comps(appraisal: DocView) -> List[int]:
    return [i for i in range(1, _MAX_COMPS + 1)
            if appraisal.value(f"comp_{i}_sale_price") not in (None, "")]


def _expand(bound_labels: List[str], appraisal: DocView) -> List[str]:
    """comp_N_x → comp_1_x..comp_k_x for the k comps that actually exist."""
    comps = _present_comps(appraisal)
    out: List[str] = []
    for lbl in bound_labels:
        fam = canonical_label(lbl)
        if fam.startswith("comp_N_"):
            attr = fam[len("comp_N_"):]
            out += [f"comp_{i}_{attr}" for i in comps]
        else:
            out.append(lbl)
    # dedupe, keep order
    seen: set = set()
    return [x for x in out if not (x in seen or seen.add(x))]


def _value_entry(view: DocView, name: str) -> Optional[Dict[str, Any]]:
    ev = view.evidence(name)
    if ev.value is None:
        return None
    entry: Dict[str, Any] = {"v": ev.value, "page": ev.page,
                             "lq": ev.location_quality or "none",
                             "source": ev.source, "confidence": ev.confidence}
    if ev.bbox:
        entry["bbox"] = ev.bbox
    # S-8: surface a retained cross-source conflict inline with both coordinates.
    f = view.field(name)
    conflicts = getattr(f, "conflicts", None) if f else None
    if conflicts:
        c = conflicts[0]
        entry["conflict"] = {"v": c.value, "source": c.source,
                             "page": c.page, "bbox": c.bbox}
    return entry


def _snapshot(appraisal: DocView, section: Optional[str] = None) -> Dict[str, Any]:
    """A capped snapshot of present appraisal values — the section context an
    UNBOUND check works from instead of specific fields (§3, S-5).

    When the item's `section` is known (it always is — the checklist defines it),
    the snapshot is SCOPED to that section's labels (the same section_scope.yaml
    map the binder uses). So an unbound "Heating/Cooling" check still reaches the
    judge with the improvements-section values, not a random 60-field slice — the
    binder may have failed, but the section context lets the LLM judge it anyway."""
    from app.language import label_dictionary as LD

    scoped = LD.scoped_labels(section) if section else None
    # scoped_labels returns the FULL set when the section is unknown/empty; treat
    # that as "no scoping" so we fall back to the capped snapshot below.
    if scoped is not None and scoped != LD.known_labels():
        out: Dict[str, Any] = {}
        for name, ef in appraisal._by_name.items():
            if ef.found and canonical_label(name) in scoped:
                out[name] = ef.value
            if len(out) >= _SNAPSHOT_CAP:
                break
        if out:
            return out

    out = {}
    for name, ef in appraisal._by_name.items():
        if ef.found:
            out[name] = ef.value
        if len(out) >= _SNAPSHOT_CAP:
            break
    return out


def _collect_narrative_text(appraisal: DocView, section: Optional[str],
                            already: Dict[str, Any]) -> Optional[Dict[str, str]]:
    """The section's captured prose (+ addendum overflow) for a narrative packet.
    Only PRESENT, non-empty fields are attached; anything already in the packet's
    `values` is skipped (no duplication). Returns None when there is no prose to
    show — the judge then falls back to the section snapshot as before."""
    wanted = list(_SECTION_PROSE.get(section or "", [])) + _GENERAL_PROSE
    out: Dict[str, str] = {}
    seen: set = set()
    for name in wanted:
        if name in seen or name in already:
            continue
        seen.add(name)
        v = appraisal.value(name)
        if v is None:
            continue
        text = str(v).strip()
        if not text:
            continue
        out[name] = text[:_PROSE_CAP]
    return out or None


def build_packet(item: CompiledItem, src: Sources) -> Packet:
    """Assemble the slim §4.1 packet for one compiled item (AnnexB: conditional
    labels are carried too, so a cross-section check sees condition + consequence)."""
    labels = _expand(item.all_labels, src.appraisal)

    values: Dict[str, Dict[str, Any]] = {}
    absent: List[str] = []

    for lbl in labels:
        entry = _value_entry(src.appraisal, lbl)
        if entry is not None:
            values[lbl] = entry
        else:
            absent.append(lbl)

    # cross-document / needs-engagement: also carry the engagement + contract side.
    # A missing counterpart is recorded explicitly (not just left out) — the
    # judge must be able to tell "the other document doesn't extract this fact,
    # so there is nothing to mismatch" apart from "we never asked" (2026-07-13
    # dry-run cause #2: ten needs_engagement packets carried only the appraisal
    # side, so the judge had no choice but REVIEW on a comparison it could
    # never have resolved either way).
    if item.scope in ("cross_document",) or item.judgeable == "needs_engagement":
        for doc_view, prefix in ((src.engagement, "engagement"), (src.contract, "contract")):
            if doc_view is None:
                continue
            for lbl in labels:
                if lbl.startswith(("engagement.", "contract.")):
                    continue
                key = f"{prefix}.{lbl}"
                entry = _value_entry(doc_view, lbl)
                if entry is not None:
                    values[key] = entry
                elif key not in absent:
                    absent.append(key)

    raw = {k: v.get("v") for k, v in values.items()}
    computed = H.compute_hints(raw, labels, expects=item.expects,
                               comp_count=len(_present_comps(src.appraisal)))
    # AnnexB Part 2: a derived-age hint the judge can use for age-triggered
    # conditionals ("if actual age > 30 …") without re-deriving arithmetic.
    age = _derived_age(src.appraisal)
    if age is not None:
        computed.append({"hint": "derived_age_from_year_built", "value": age, "labels": ["year_built"]})

    conditional = None
    if item.conditional:
        conditional = {
            "condition_labels": _expand(item.conditional.get("condition_labels", []), src.appraisal),
            "consequence_labels": _expand(item.conditional.get("consequence_labels", []), src.appraisal),
        }

    snapshot = _snapshot(src.appraisal, item.section) if (item.scope == "unbound" or not labels) else None

    # Row-3: hand narrative-class checks the real prose for their section.
    narrative_text = (_collect_narrative_text(src.appraisal, item.section, values)
                      if item.scope in _NARRATIVE_SCOPES else None)

    # Pre-normalize cross-document comparison values (deterministic, upstream): for
    # every X that has an engagement./contract. counterpart, stamp both entries with
    # a canonical `cmp` form so a match is byte-identical to the judge. Kind is
    # inferred from the label name — general for any AMC, no per-item config.
    if item.scope == "cross_document" or item.judgeable == "needs_engagement":
        _stamp_compare_forms(values)

    source_notes = {
        "xml_present": _has_source(src.appraisal, "xml"),
        "engagement_present": src.engagement is not None and src.engagement.present,
        "contract_present": src.contract is not None and src.contract.present,
        "scope": item.scope,
    }

    return Packet(
        item_id=item.item_id, check_text=item.check_text, reject_text=item.reject_text,
        values=values, absent_labels=absent, computed_hints=computed,
        section_snapshot=snapshot, source_notes=source_notes, scope=item.scope,
        conditional=conditional, narrative_text=narrative_text,
    )


def _stamp_compare_forms(values: Dict[str, Dict[str, Any]]) -> None:
    """For each non-prefixed label X that has an engagement./contract. counterpart,
    stamp BOTH entries with `cmp` = the canonical comparison form (kind inferred
    from the label name). Purely additive — `v` is untouched, so only the
    judge-facing to_json() uses `cmp` (see Packet._judge_values)."""
    from app.normalize.normalizer import canonicalize
    for lbl in list(values.keys()):
        if lbl.startswith(("engagement.", "contract.")):
            continue
        for prefix in ("engagement.", "contract."):
            other = values.get(f"{prefix}{lbl}")
            if other is None:
                continue
            kind = H._xdoc_kind(lbl)
            values[lbl]["cmp"] = canonicalize(values[lbl].get("v"), kind)
            other["cmp"] = canonicalize(other.get("v"), kind)


def _derived_age(appraisal: DocView) -> Optional[int]:
    import datetime
    yb = appraisal.value("year_built")
    if not yb:
        return None
    m = __import__("re").search(r"(1[89]\d\d|20\d\d)", str(yb))
    if not m:
        return None
    age = datetime.date.today().year - int(m.group(1))
    return age if 0 <= age <= 300 else None


def _has_source(view: DocView, src_kind: str) -> bool:
    for _n, ef in view._by_name.items():
        if not ef.found:
            continue
        # ef.source is usually a Source str-enum member, but a derived field
        # (app/rules/field_resolution.py) stamps a bare "derived" string — get
        # the plain value either way. On py3.11+, str(Source.XML) == "Source.XML"
        # (Enum.__str__ takes precedence over the str mixin), so comparing the
        # stringified repr against the lowercase src_kind was always False.
        source_value = getattr(ef.source, "value", ef.source)
        if str(source_value).endswith(src_kind):
            return True
    return False
