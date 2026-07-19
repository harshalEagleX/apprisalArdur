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

import re
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
    # Multi-reject model: per-trigger fail branches [{trigger, reject_text}]. The
    # judge returns which branch fired; the fired branch's reject_text (with {slots}
    # filled from packet values) is the rejection wording. Empty ⇒ single reject_text.
    reject_branches: List[Dict[str, Any]] = field(default_factory=list)

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
        if self.reject_branches:
            # send only branch_id + trigger + reject_text — the judge picks which fired.
            out["reject_branches"] = [
                {"branch_id": i, "trigger": b.get("trigger", ""),
                 "reject_text": b.get("reject_text", "")}
                for i, b in enumerate(self.reject_branches)]
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


# Vendors overflow every section's prose into ONE addendum blob, delimited by
# section headers ("-:HIGHEST AND BEST USE:-" in ACI). Blind-capping that blob to
# _PROSE_CAP hands the judge only its head (the boilerplate scope paragraph) and
# hides the very comment a check asks for — ESMI-0049134's predominant-value
# comment (EQ-21), legal-nonconforming explanation (EQ-30) and drive-by commentary
# (EQ-127) all sat in later sections and read as "no comment found". So split the
# blob on its headers and hand over only the block matching THIS check's section.
_ADDENDUM_SECTION_RX = re.compile(r"-:\s*([^:]{3,70}?)\s*:-")

# checklist section -> keywords that identify its addendum header. Matched by
# substring on the lowercased header, so vendor wording variants still land.
_ADDENDUM_HINTS: Dict[str, tuple] = {
    "neighborhood":     ("market condition", "neighborhood"),
    "site":             ("highest and best use", "zoning", "site"),
    "improvements":     ("condition of the property", "improvement", "quality"),
    "sales_comparison": ("comments on sales comparison", "sales comparison", "prior sales"),
    "prior_sales":      ("prior sales", "sales comparison"),
    "contract":         ("analysis of the sales contract", "sales contract", "contract"),
    "reconciliation":   ("conditions of appraisal", "reconciliation"),
    "cost":             ("cost approach",),
    "subject":          ("listing history", "scope"),
    "mc_1004":          ("market condition",),
}

# A check that asks for a comment/explanation needs the prose even when its scope
# isn't narrative (EQ-21/EQ-30/EQ-127 are value/zoning/photo checks that hinge on a
# written comment). Detected from the check's own words — no per-item hardcoding.
# 2026-07-18: `describ(e|ed|ption)` could never match "description" — that word is
# spelt descriP-tion, not descriB-tion, so the alternation only ever caught
# "describe"/"described". Three checks whose language is explicitly about a
# DESCRIPTION (EQ-2 Legal Description, EQ-22 Present Land Use, EQ-36 General
# description) were therefore judged with no prose attached at all — asked whether
# a description was provided while the text carrying it was withheld. EQ-22 alone
# hedged on 6 of 15 orders. Also added summar(y|ise|ize) — a "summary of…" check is
# a prose check by definition.
_COMMENT_REQUIRING_RX = re.compile(
    r"\b(comment(s|ary)?|explain(ed|ation)?|narrative|descri(be|bed|ption|ptive)|"
    r"discuss(ed|ion)?|justif(y|ied|ication)|address(ed)?|summar(y|ies|ise|ize|ised|ized))\b",
    re.I)


def _stitch_addendum(blob: str) -> Dict[str, str]:
    """Split a delimited addendum blob into {HEADER: body}. Text before the first
    header is kept under "" (the preamble) so nothing is lost."""
    out: Dict[str, str] = {}
    if not blob:
        return out
    parts = _ADDENDUM_SECTION_RX.split(blob)
    out[""] = (parts[0] or "").strip()
    for i in range(1, len(parts) - 1, 2):
        header = (parts[i] or "").strip()
        body = (parts[i + 1] or "").strip()
        if header and body:
            out[header] = (out.get(header, "") + "\n" + body).strip() if header in out else body
    return out


_TERM_RX = re.compile(r"[a-z]{5,}")
_TERM_STOP = frozenset((
    "which", "there", "their", "these", "those", "where", "while", "shall", "must",
    "should", "would", "could", "provided", "present", "report", "appraisal",
    "appraiser", "property", "subject", "value", "required", "requirement", "comment",
    "commentary", "please", "verify", "section", "field", "blank",
))


def _terms(text: str) -> frozenset:
    return frozenset(_TERM_RX.findall((text or "").lower())) - _TERM_STOP


def _relevant_window(body: str, want: frozenset) -> str:
    """A _PROSE_CAP-sized excerpt centred on the densest run of `want` terms, so a
    long vendor block is quoted where it actually answers the check (not its head).
    Snaps to sentence boundaries; returns the head when nothing matches."""
    if len(body) <= _PROSE_CAP or not want:
        return body[:_PROSE_CAP]
    low = body.lower()
    hits = sorted(p for t in want for p in (low.find(t),) if p >= 0)
    if not hits:
        return body[:_PROSE_CAP]
    # centre on the median hit so a cluster of matches stays inside the window
    centre = hits[len(hits) // 2]
    start = max(0, centre - _PROSE_CAP // 2)
    end = min(len(body), start + _PROSE_CAP)
    start = max(0, end - _PROSE_CAP)
    snippet = body[start:end]
    if start:                                   # don't start mid-sentence
        dot = snippet.find(". ")
        if 0 <= dot < 200:
            snippet = snippet[dot + 2:]
    return snippet.strip()


def _addendum_for_section(blob: str, section: Optional[str],
                          check_text: Optional[str] = None) -> Optional[str]:
    """The addendum block(s) relevant to this check. Header match on `section` first,
    then a CONTENT match against the check's own distinctive words — appraisers file a
    comment under whatever heading they like, so the text EQ-21 (predominant value) and
    EQ-30 (legal non-conforming) need both sit under "COMMENTS ON SALES COMPARISON",
    not under their own sections. Falls back to the preamble/head, so a blob with no
    headers behaves exactly as before."""
    sections = _stitch_addendum(blob)
    if not sections:
        return None
    hints = _ADDENDUM_HINTS.get(section or "", ())
    picked = [body for header, body in sections.items()
              if header and any(h in header.lower() for h in hints)]
    if check_text:
        want = _terms(check_text)
        scored = sorted(((len(want & _terms(body)), header, body)
                         for header, body in sections.items() if header),
                        key=lambda t: t[0], reverse=True)
        # ≥2 shared distinctive words = this block is talking about the same thing
        if scored and scored[0][0] >= 2:
            # excerpt AROUND the match: these vendor blocks run for pages and the
            # sentence a check needs is often near the end (EQ-30's legal
            # non-conforming text tails a multi-page sales-comparison block), so a
            # head-cap would truncate the very evidence we routed here for.
            block = _relevant_window(scored[0][2], want)
            if block not in picked:
                picked.append(block)
    if picked:
        return "\n\n".join(picked)[:_PROSE_CAP]
    return (sections.get("") or blob).strip()[:_PROSE_CAP] or None


def _collect_narrative_text(appraisal: DocView, section: Optional[str],
                            already: Dict[str, Any], check_text: Optional[str] = None,
                            addendum_only: bool = False) -> Optional[Dict[str, str]]:
    """The section's captured prose (+ addendum overflow) for a narrative packet.
    Only PRESENT, non-empty fields are attached; anything already in the packet's
    `values` is skipped (no duplication). Returns None when there is no prose to
    show — the judge then falls back to the section snapshot as before.

    `addendum_only` trims the payload to the routed addendum block for the widened
    (non-narrative) arm, so answering "is the comment there?" costs one block rather
    than every prose field in the section."""
    wanted = (list(_SECTION_PROSE.get(section or "", [])) if not addendum_only else []) + _GENERAL_PROSE
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
        # the addendum is section+content routed, never blind-capped to its head
        out[name] = (_addendum_for_section(text, section, check_text)
                     if name == "addendum_text" else text[:_PROSE_CAP])
        if not out[name]:
            out.pop(name, None)
    return out or None


# ── cross-document comparison detection + availability (2026-07-18) ───────────
#
# A check like EQ-107 ("Subject property address same as engagement letter") is
# compiled scope=subject / judgeable=text, so the engagement side was never
# attached — the judge was asked to compare against a document it had not been
# given, and could only hedge to REVIEW. Detecting the intent from the check's
# OWN WORDS fixes that for any AMC without pinning item ids.
#
# Both arms are required. A doc reference ALONE is far too broad: "Contract Price
# & Date of Contract" mentions a contract but asks about the report's own contract
# section, and treating it as a cross-document comparison would wrongly excuse it
# whenever no contract PDF was supplied. Comparison language is what marks a check
# as "report value vs other document's value".
_DOC_REF_RX = re.compile(
    r"engagement\s+letter|order\s+form|assignment\s+order|purchase\s+contract|sales?\s+contract",
    re.I)
_DOC_CMP_RX = re.compile(
    r"\b(match(?:es|ing|ed)?|same\s+as|agree(?:s|ment)?\s+with|consistent\s+with"
    r"|identical|correspond(?:s|ing)?\s+(?:to|with)|as\s+per|reflect(?:s|ed)?)\b", re.I)


def _is_cross_doc_check(item: CompiledItem) -> bool:
    """True when this check compares a report value against another supplied
    document. Either an explicit compile-time signal, or the check text itself
    both NAMES a document and asks for a MATCH."""
    if item.scope == "cross_document" or item.judgeable == "needs_engagement":
        return True
    text = f"{item.check_text or ''} {item.expects or ''}"
    return bool(_DOC_REF_RX.search(text) and _DOC_CMP_RX.search(text))


# ── photo/visual aspect (2026-07-18, user directive) ─────────────────────────
#
# "if a check's language or any trigger asks for a photo or visual check, tell the
# reviewer the photo must be checked manually; but if the check states photo AND
# text, do the text part, report whatever it finds, and ALSO ask them to verify the
# photo — some checks have multiple scope."
#
# Deliberately NOT including "map": EQ-7 "Map Reference" is a form FIELD (a map
# reference number the appraiser types), and EQ-56's "Proximity to Subject" is a
# numeric distance — both are machine-checkable and must not be pushed at a human.
# The genuine map checks (EQ-130..133) are already compiled `judgeable=visual`.
_PHOTO_ASPECT_RX = re.compile(r"\bphotos?\b|\bphotograph|\bsketch\b|\bimages?\b", re.I)


def _has_photo_aspect(item: CompiledItem) -> bool:
    """True when this check's own words involve a photo/sketch/image — including
    when the reference sits only in a `Triggers:` clause (EQ-43 "if photo is
    provided of attic…"). The judge still judges the text aspect; the reviewer is
    additionally asked to confirm the image."""
    return bool(_PHOTO_ASPECT_RX.search(f"{item.check_text or ''} {item.expects or ''}"))


_ENGAGEMENT_REF_RX = re.compile(r"engagement\s+letter|order\s+form|assignment\s+order", re.I)
_CONTRACT_REF_RX = re.compile(r"purchase\s+contract|sales?\s+contract", re.I)


def _relevant_docs(item: CompiledItem) -> List[str]:
    """Which comparison document(s) THIS check is actually about.

    Emitting availability for every document is wrong and actively harmful: EQ-C
    compares the address to the ENGAGEMENT LETTER, but a blanket "no purchase
    contract was supplied" hint made the judge answer NOT_APPLICABLE citing the
    contract — on an order whose engagement letter was present and matched. Only
    the documents a check actually names can excuse it.
    """
    text = f"{item.check_text or ''} {item.expects or ''}"
    docs = []
    if _ENGAGEMENT_REF_RX.search(text) or item.judgeable == "needs_engagement":
        docs.append("engagement")
    if _CONTRACT_REF_RX.search(text):
        docs.append("contract")
    # scope=cross_document with no document named: fall back to the engagement
    # letter, which is the order-form counterpart every AMC supplies.
    return docs or ["engagement"]


def _cross_doc_availability(src: Sources, labels: List[str],
                            values: Dict[str, Dict[str, Any]],
                            relevant: List[str]) -> List[Dict[str, Any]]:
    """State plainly, per comparison document, whether this check CAN be decided.

    2026-07-18 (engagement-comparison investigation). Doctrine rule 3 tells the
    judge it cannot distinguish "the engine did not read it" from "the document
    does not state it", so any absent counterpart forces a hedge to REVIEW. For
    the engagement/contract side we DO know which it is, and withholding that
    turned a structurally undecidable check into a permanent human task.

    Measured over the 7 test orders: the engagement letter states the appraiser's
    NAME in 6/6 cases but their phone/email in 0/6 — those letters carry only the
    AMC's own letterhead contact (information@esusa.net / 248-579-9928) and the
    borrower's. So "Telephone number — should match the engagement letter" can
    never be satisfied by any extraction improvement: the datum is not in the
    source document. A reviewer opening that card can do nothing a machine
    cannot, which is precisely what NOT_APPLICABLE is for.
    """
    plain = [l for l in labels if not l.startswith(("engagement.", "contract."))]
    if not plain:
        return []
    docs = [(src.engagement, "engagement", "engagement letter"),
            (src.contract, "contract", "purchase contract")]
    docs = [d for d in docs if d[1] in relevant]

    # A label is unverifiable only when NO relevant document carries its
    # counterpart — one absent or silent document must never excuse a check that
    # another document can answer.
    unstated = [l for l in plain
                if not any(f"{p}.{l}" in values for _v, p, _h in docs)]
    if not unstated:
        return []

    hints: List[Dict[str, Any]] = []
    for doc_view, prefix, human in docs:
        if doc_view is None or not doc_view.present:
            hints.append({"hint": "cross_document_status", "labels": list(unstated),
                          "value": {"document": prefix, "status": "not_supplied",
                                    "detail": f"no {human} was supplied with this order"}})
        else:
            hints.append({"hint": "cross_document_status", "labels": list(unstated),
                          "value": {"document": prefix, "status": "does_not_state",
                                    "detail": (f"the {human} was read but does not state "
                                               f"{', '.join(unstated)}")}})
    return hints


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
    is_cross_doc = _is_cross_doc_check(item)
    if is_cross_doc:
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

    # P4 (F6): inject RUNTIME CONTEXT the judge cannot know from field values alone —
    # today's year and the report's effective year. A "reference year present" /
    # tax-year / "within the last N years" check was defaulting to REVIEW because the
    # packet never told the judge what "current" is. These are deterministic facts,
    # not report data, so they ride as computed_hints (trusted arithmetic, rule 4).
    computed.extend(_runtime_context_hints(src.appraisal))

    # Tell a comparison check whether the other document can answer it at all —
    # "not supplied" and "supplied but silent on this field" are both decidable
    # facts, not the unreadable-vs-unstated ambiguity of doctrine rule 3.
    if is_cross_doc:
        computed.extend(_cross_doc_availability(src, labels, values,
                                                _relevant_docs(item)))

    # The photo aspect is a HUMAN task; tell the judge to stay off it rather than
    # assert something about an image it was never shown.
    if _has_photo_aspect(item):
        computed.append({
            "hint": "manual_photo_verification", "labels": [],
            "value": {"detail": "this check also depends on photos/sketch that you "
                                "cannot see; a human will verify those separately"}})

    conditional = None
    if item.conditional:
        conditional = {
            "condition_labels": _expand(item.conditional.get("condition_labels", []), src.appraisal),
            "consequence_labels": _expand(item.conditional.get("consequence_labels", []), src.appraisal),
        }

    snapshot = _snapshot(src.appraisal, item.section) if (item.scope == "unbound" or not labels) else None

    # Row-3: hand narrative-class checks the real prose for their section — plus any
    # check whose OWN text asks for a comment/explanation, whatever its scope. Without
    # that second arm a value/zoning/photo check (EQ-21/EQ-30/EQ-127) is asked "is the
    # required comment present?" while the prose carrying it is withheld, so the only
    # honest answer is "not found" — a false reject against a report that DID comment.
    _is_narrative = item.scope in _NARRATIVE_SCOPES
    _asks_comment = bool(_COMMENT_REQUIRING_RX.search(item.check_text or "")
                         or _COMMENT_REQUIRING_RX.search(item.expects or ""))
    narrative_text = (_collect_narrative_text(
        src.appraisal, item.section, values, check_text=item.check_text,
        addendum_only=(not _is_narrative)) if (_is_narrative or _asks_comment) else None)

    # Pre-normalize cross-document comparison values (deterministic, upstream): for
    # every X that has an engagement./contract. counterpart, stamp both entries with
    # a canonical `cmp` form so a match is byte-identical to the judge. Kind is
    # inferred from the label name — general for any AMC, no per-item config.
    if is_cross_doc:
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
        reject_branches=list(item.reject_branches or []),
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


def _runtime_context_hints(appraisal: DocView) -> List[Dict[str, Any]]:
    """P4 (F6): the current year (and the report's effective year, when present) as
    trusted computed_hints. Lets a "reference year is provided / tax year is
    current / within the last N years" check resolve deterministically instead of
    hedging to REVIEW because the judge had no notion of 'now'."""
    import datetime
    hints: List[Dict[str, Any]] = [
        {"hint": "current_year", "value": datetime.date.today().year, "labels": []},
    ]
    eff = appraisal.value("effective_date")
    if eff:
        from app.normalize import dates as _d
        parsed = _d.parse_date(str(eff))
        if parsed is not None:
            hints.append({"hint": "effective_date_year", "value": parsed.year,
                          "labels": ["effective_date"]})
    return hints


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
