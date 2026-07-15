"""
rules.context — the QCContext the rule engine evaluates against (SHALqc.md §5).

One QC case spans up to three documents (appraisal, engagement letter, sales
contract). QCContext holds one DocView per document, each an
`ExtractedField`-by-name view over that document's ExtractedFieldSet. Rules
never touch extractor internals — they ask the context for a field's value +
evidence (P12: stable contract between extraction and rules).

needs[] resolution (SHALqc.md §5): a bare field name ("property_address")
resolves against the appraisal doc; a "engagement."-prefixed name against the
engagement doc; "contract." against the contract doc. This mirrors the fact-
packet keys in SHALqc-CORE §4.1 exactly ("appraisal.property_address",
"engagement.property_address").
"""

from __future__ import annotations

import re
from typing import Optional

from app.extraction.result import ExtractedField, ExtractedFieldSet
from app.rules.verdict import Evidence

# Below this a structured value is "uncertain" → a rule may only VERIFY, never
# auto-FAIL on it (SHALqc.md §7 routing default `review`; P4). The router
# (Part 7) will drive this per-field; until then this is the single default.
DEFAULT_REVIEW_CONF = 0.70


class DocView:
    """By-field-name view of one document's extraction results."""

    def __init__(self, label: str, field_set: Optional[ExtractedFieldSet]):
        self.label = label
        self.present = field_set is not None
        self._by_name = {}
        if field_set is not None:
            for name, ef in field_set:
                self._by_name[name] = ef

    def field(self, name: str) -> Optional[ExtractedField]:
        ef = self._by_name.get(name)
        if ef is not None and ef.found:
            return ef
        # Rule-vs-extraction name drift: resolve via alias / schema-synonym /
        # derive before declaring the field missing (rules/field_resolution).
        from app.rules.field_resolution import resolve_field
        return resolve_field(name, self._by_name)

    def value(self, name: str) -> Optional[str]:
        ef = self.field(name)
        return ef.value if ef else None

    def confidence(self, name: str) -> float:
        ef = self.field(name)
        return ef.confidence if ef else 0.0

    def evidence(self, name: str) -> Evidence:
        ef = self.field(name)
        if not ef:
            return Evidence(field=name, value=None, confidence=0.0, document=self.label)
        return Evidence(
            field=name, value=ef.value, source=str(ef.source),
            confidence=ef.confidence, page=ef.page, bbox=ef.bbox,
            location_quality=ef.location_quality, document=self.label,
        )


class QCContext:
    def __init__(
        self,
        order_id: str,
        appraisal: Optional[ExtractedFieldSet] = None,
        engagement: Optional[ExtractedFieldSet] = None,
        contract: Optional[ExtractedFieldSet] = None,
        review_conf: float = DEFAULT_REVIEW_CONF,
        profile=None,
        llm_client=None,
    ):
        self.order_id = order_id
        self.appraisal = DocView("appraisal", appraisal)
        self.engagement = DocView("engagement", engagement)
        self.contract = DocView("contract", contract)
        self.review_conf = review_conf
        # AmcProfile (Part 6) — thresholds/severity/rule-toggles. None ⇒ base
        # defaults (profiles/engine_binding applies it before the run).
        self.profile = profile
        # Part-10 LLM client for tier-2/3 rule bodies. None ⇒ the engine degrades
        # those rules to VERIFY before the body runs (SHALqc-CORE §4.0), so a body
        # that DOES run can trust ctx.llm_client is present + available.
        self.llm_client = llm_client

    # -- document + needs[] access ----------------------------------------
    def doc(self, label: str) -> DocView:
        return {"appraisal": self.appraisal, "engagement": self.engagement,
                "contract": self.contract}[label]

    def resolve(self, need: str) -> Evidence:
        """Resolve a needs[] token → Evidence. "engagement.X"/"contract.X" pick
        that doc; a bare name picks the appraisal doc."""
        doc_label, name = self._split_need(need)
        return self.doc(doc_label).evidence(name)

    def value_of(self, need: str) -> Optional[str]:
        doc_label, name = self._split_need(need)
        return self.doc(doc_label).value(name)

    @staticmethod
    def _split_need(need: str):
        if "." in need:
            prefix, name = need.split(".", 1)
            if prefix in ("appraisal", "engagement", "contract"):
                return prefix, name
        return "appraisal", need

    @property
    def has_engagement(self) -> bool:
        return self.engagement.present

    @property
    def has_contract(self) -> bool:
        return self.contract.present

    # -- derived transaction attributes (gate which rules fire) -----------
    @property
    def transaction_type(self) -> str:
        """purchase | refinance | other | unknown."""
        raw = (self.appraisal.value("assignment_type")
               or self.engagement.value("assignment_type") or "")
        t = raw.lower()
        if "purchase" in t:
            return "purchase"
        if "refinance" in t or "refi" in t:
            return "refinance"
        return "other" if t else "unknown"

    @property
    def loan_type(self) -> str:
        """conventional | fha | usda | va | unknown — engagement is authority."""
        raw = (self.engagement.value("loan_program")
               or self.engagement.value("form_type")
               or self.appraisal.value("loan_program") or "")
        t = raw.lower()
        for key in ("fha", "usda", "va", "conventional"):
            if key in t:
                return key
        return "unknown"

    @property
    def form_type(self) -> str:
        """1004 | 1073 | 1025 | unknown."""
        raw = (self.engagement.value("form_type")
               or self.appraisal.value("form_type") or "")
        m = re.search(r"\b(1004mc|1004|1073|1025|1007|216)\b", raw.lower())
        return m.group(1) if m else "unknown"
