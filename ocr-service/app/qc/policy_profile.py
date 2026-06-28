"""
PolicyProfile — per-case rule activation and threshold overrides.

CURRENT SETUP — NO DATABASE AMC PROFILES YET:
  Build entirely from engagement letter extraction + UAD/GSE hardcoded defaults.
  The database AMC profile layer (from_amc_id) is implemented but returns
  defaults until real clients are onboarded with known policy variations.
  When that time comes, slot in the DB load between defaults and engagement
  overlays without changing anything else.

Layering order (highest priority wins):
  1. EngagementOverlay   — what THIS letter specifically instructs
  2. AMC database profile — what THIS AMC always requires (empty for now)
  3. Global qc_thresholds.yaml defaults — UAD/GSE baseline

Every rule reads thresholds and activation flags from ctx.policy — never from
hardcoded constants or scattered qc_config calls inside rule functions.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class PolicyProfile:
    """
    Complete policy configuration for one QC case.

    Threshold fields (Optional[X]):
      None   → fall back to global qc_thresholds.yaml via get_threshold()
      Set    → override the global default for this case

    Flag fields (Optional[bool]):
      None   → use the rule's built-in default (typically off / not required)
      True   → activation is on for this case
      False  → activation is explicitly suppressed for this case
    """
    # ── Client identity ──────────────────────────────────────────────────────
    amc_id: Optional[str] = None
    client_name: Optional[str] = None
    engagement_hash: Optional[str] = None   # for detecting EL changes between reviews

    # ── Commentary trigger thresholds ────────────────────────────────────────
    # These are COMMENTARY TRIGGERS not hard rejection limits.
    # When a comp exceeds these, the rule checks for explanation — it does NOT auto-fail.
    # Sourced verbatim from Equity Solutions USA engagement letter body:
    #   "Sales Over 6 Months Old: Please provide an EXPLANATION"
    #   "Suburban area, sales exceeding 1 mile: please COMMENT"
    #   "Urban area, sales exceeding 1/2 mile: please COMMENT"
    #   "Adjustment >10% line / >15% net / >25% gross: client requires appraiser to EXPLAIN"
    comp_age_commentary_trigger_months: Optional[int] = None    # None → 6 (EL default)
    distance_commentary_trigger_urban_miles: Optional[float] = None   # None → 0.5
    distance_commentary_trigger_suburban_miles: Optional[float] = None  # None → 1.0
    distance_commentary_trigger_rural_miles: Optional[float] = None  # None → 10.0 (GSE default)

    # Hard rejection limits (separate from commentary triggers):
    # These override the commentary trigger — a comp beyond this cannot be explained away.
    # None = no hard limit (commentary trigger is the only gate).
    comp_age_hard_limit_months: Optional[int] = None     # None → no hard limit (12 for FHA)
    comp_distance_hard_limit_miles: Optional[float] = None  # None → no hard limit

    # Adjustment commentary thresholds (from EL body: 10/15/25)
    adjustment_commentary_line_pct: Optional[float] = None    # None → 10.0
    adjustment_commentary_net_pct: Optional[float] = None     # None → 15.0
    adjustment_commentary_gross_pct: Optional[float] = None   # None → 25.0

    # ── Value / contract thresholds ──────────────────────────────────────────
    value_vs_contract_pct: Optional[float] = None       # hold band
    listing_price_pct: Optional[float] = None           # listing vs value comment threshold

    # ── Rule activation flags ────────────────────────────────────────────────
    require_listing_comp_declining: Optional[bool] = None    # required in declining market
    require_listing_comp_unconditional: Optional[bool] = None  # required regardless of market
    require_cost_approach: Optional[bool] = None
    require_income_approach_rental: Optional[bool] = None
    require_smco_comment: Optional[bool] = None          # smoke/CO detector confirmation
    require_fha_case_all_pages: Optional[bool] = None
    stop_on_unsigned_contract: Optional[bool] = None     # HOLD when contract not fully executed
    require_co_borrower_in_appraisal: Optional[bool] = None
    # Required content from EL body (all true for Equity Solutions USA)
    require_economic_life: Optional[bool] = None
    require_hbu_summary: Optional[bool] = None
    require_zoning_detail: Optional[bool] = None
    require_exposure_time: Optional[bool] = None
    require_prior_services_disclosure: Optional[bool] = None
    require_listing_analysis_12months: Optional[bool] = None  # not just dates — written analysis
    require_prior_sale_analysis_3years: Optional[bool] = None
    require_license_attachment: Optional[bool] = None
    require_flood_map: Optional[bool] = None             # if in flood zone
    require_aerial_map: Optional[bool] = None
    # Blocking stops
    stop_on_c5_c6: Optional[bool] = None
    stop_on_lava_zone: Optional[bool] = None
    stop_on_pre1976_manufactured: Optional[bool] = None

    # ── Named requirements ───────────────────────────────────────────────────
    required_addenda: List[str] = field(default_factory=list)
    stop_conditions: List[str] = field(default_factory=list)

    # ── Raw overlays (for debugging / audit) ────────────────────────────────
    engagement_overlays: Dict[str, Any] = field(default_factory=dict)

    # ── Threshold resolution ─────────────────────────────────────────────────

    def get_threshold(self, key: str, default: float) -> float:
        """
        Resolve a numeric threshold with 3-level priority.

        1. Instance field (engagement letter override or AMC DB override)
        2. engagement_overlays dict (raw overlay key-value pairs)
        3. Global qc_thresholds.yaml
        """
        # Instance field (set by apply_overlay or from_amc_id)
        val = getattr(self, key, None)
        if val is not None:
            try:
                return float(val)
            except (TypeError, ValueError):
                pass

        # Raw overlay dict (catch-all for keys not mapped to named fields)
        val = self.engagement_overlays.get(key)
        if val is not None:
            try:
                return float(val)
            except (TypeError, ValueError):
                pass

        # Global config fallback
        try:
            from app.qc.config import qc_config
            return float(qc_config.semantic(key, default))
        except Exception:
            return default

    def is_active(self, flag: str, default: bool = False) -> bool:
        """Resolve a boolean activation flag."""
        val = getattr(self, flag, None)
        if val is not None:
            return bool(val)
        val = self.engagement_overlays.get(flag)
        if val is not None:
            return bool(val)
        return default

    def comp_age_commentary_trigger(self, loan_type: str = "conventional") -> int:
        """Return the commentary trigger age (months) for comp age per loan type.
        Commentary trigger = "explain if older than X months" (not hard rejection).
        Hard limit (comp_age_hard_limit_months) is separate and used for FHA only."""
        if loan_type == "fha" and self.comp_age_hard_limit_months is not None:
            return self.comp_age_hard_limit_months
        if self.comp_age_commentary_trigger_months is not None:
            return self.comp_age_commentary_trigger_months
        try:
            from app.qc.config import qc_config
            default = int(qc_config.semantic("comp_sale_window_months", 12))
        except Exception:
            default = 12
        return 6 if loan_type == "fha" else default

    # Legacy alias so existing rules that call comp_age_limit() still work
    def comp_age_limit(self, loan_type: str = "conventional") -> int:
        return self.comp_age_commentary_trigger(loan_type)

    def distance_commentary_trigger(self, location_type: str) -> float:
        """Return the commentary trigger distance (miles) for the area type.
        Commentary trigger = "explain if farther than X miles" (not hard rejection)."""
        if "urban" in location_type.lower():
            return self.distance_commentary_trigger_urban_miles or \
                   self.get_threshold("comp_distance_urban_miles", 1.0)
        if "rural" in location_type.lower():
            return self.distance_commentary_trigger_rural_miles or \
                   self.get_threshold("comp_distance_rural_miles", 10.0)
        return self.distance_commentary_trigger_suburban_miles or \
               self.get_threshold("comp_distance_suburban_miles", 5.0)

    def distance_limit(self, location_type: str) -> float:
        """Legacy alias — routes to distance_commentary_trigger()."""
        return self.distance_commentary_trigger(location_type)

    def _distance_limit_old(self, location_type: str) -> float:
        """Return the effective comp distance limit for this area type."""
        mapping = {
            "urban":    (self.distance_commentary_trigger_urban_miles, "comp_distance_urban_miles", 1.0),
            "suburban": (self.distance_commentary_trigger_suburban_miles, "comp_distance_suburban_miles", 5.0),
            "rural":    (self.distance_commentary_trigger_rural_miles, "comp_distance_rural_miles", 10.0),
        }
        instance_val, yaml_key, fallback = mapping.get(
            location_type.lower(), (None, "comp_distance_suburban_miles", 5.0)
        )
        if instance_val is not None:
            return float(instance_val)
        return self.get_threshold(yaml_key, fallback)

    # ── Constructors ─────────────────────────────────────────────────────────

    @classmethod
    def default(cls) -> "PolicyProfile":
        """All-defaults profile — used when nothing overrides global thresholds."""
        return cls()

    @classmethod
    def from_amc_id(cls, amc_id: Optional[str]) -> "PolicyProfile":
        """
        Load AMC policy from config/amc_policies.yaml (primary source).

        The instruction body of engagement letters is AMC-level policy — identical
        across all orders from the same AMC. It is read ONCE into amc_policies.yaml
        rather than extracted per-case. This is cheaper, more reliable, and avoids
        misclassifying operational prose as case-specific policy overrides.

        Priority:
          1. config/amc_policies.yaml (policy baked from reading real EL bodies)
          2. amc_profiles DB table (for future per-client DB-driven overrides)
          3. __default__ section of amc_policies.yaml (UAD/GSE defaults)
        """
        static = _load_amc_policy(amc_id)
        profile = cls._from_policy_dict(amc_id, static)
        logger.debug("PolicyProfile loaded: amc=%s fields=%d", amc_id, len(static))
        return profile

    @classmethod
    def _from_policy_dict(cls, amc_id: Optional[str], d: dict) -> "PolicyProfile":
        """Build a PolicyProfile from a flat policy dict (from amc_policies.yaml)."""
        p = cls(amc_id=amc_id, client_name=d.get("amc_name"))
        # Map every key in the dict to the matching field if it exists
        for key, val in d.items():
            if key.startswith("amc_") or key in ("known_order_prefixes", "fha"):
                continue
            if hasattr(p, key):
                setattr(p, key, val)
            else:
                # Store unrecognized keys in engagement_overlays for get_threshold()
                p.engagement_overlays[key] = val
        return p

    def apply_overlay(self, overlay: "EngagementOverlay") -> "PolicyProfile":
        """
        Merge an EngagementOverlay into this profile and return self.

        Overlay values are the HIGHEST priority — they override AMC defaults.
        Only non-None overlay values are applied so silence = keep existing value.
        """
        from app.qc.engagement_overlay import EngagementOverlay as _EO
        if not isinstance(overlay, _EO) or not overlay.has_any_override():
            return self

        if overlay.comp_age_limit_months is not None:
            self.comp_age_commentary_trigger_months = overlay.comp_age_limit_months
        if overlay.comp_distance_limit_miles is not None:
            # Apply uniformly when the letter gives one distance without area-type distinction
            self.distance_commentary_trigger_urban_miles = overlay.comp_distance_limit_miles
            self.distance_commentary_trigger_suburban_miles = overlay.comp_distance_limit_miles
            self.distance_commentary_trigger_rural_miles = overlay.comp_distance_limit_miles
        if overlay.stop_on_unsigned_contract is not None:
            self.stop_on_unsigned_contract = overlay.stop_on_unsigned_contract
        if overlay.require_listing_comp_unconditional is not None:
            self.require_listing_comp_unconditional = overlay.require_listing_comp_unconditional
        if overlay.require_listing_comp_declining is not None:
            self.require_listing_comp_declining = overlay.require_listing_comp_declining
        if overlay.require_cost_approach is not None:
            self.require_cost_approach = overlay.require_cost_approach
        if overlay.require_smco_comment is not None:
            self.require_smco_comment = overlay.require_smco_comment
        if overlay.require_fha_case_all_pages is not None:
            self.require_fha_case_all_pages = overlay.require_fha_case_all_pages

        # Merge lists — deduplicate
        for item in overlay.required_addenda:
            if item not in self.required_addenda:
                self.required_addenda.append(item)
        for item in overlay.stop_conditions:
            if item not in self.stop_conditions:
                self.stop_conditions.append(item)

        if overlay.letter_text_snippet:
            self.engagement_overlays["_letter_snippet"] = overlay.letter_text_snippet

        logger.info(
            "PolicyProfile overlay applied: age_limit=%s, stop_unsigned=%s, "
            "listing_unconditional=%s, listing_declining=%s, cost_req=%s",
            self.comp_age_commentary_trigger_months, self.stop_on_unsigned_contract,
            self.require_listing_comp_unconditional, self.require_listing_comp_declining,
            self.require_cost_approach,
        )
        return self

    @classmethod
    def build(
        cls,
        amc_id: Optional[str] = None,
        loan_type: Optional[str] = None,
        overlay: Optional["EngagementOverlay"] = None,
        engagement_hash: Optional[str] = None,
    ) -> "PolicyProfile":
        """
        Full build: static AMC policy → loan-type sub-profile → engagement overlay.

        1. Load base AMC policy from amc_policies.yaml
        2. Merge loan-type-specific sub-profile (e.g. fha: {...})
        3. Apply per-case engagement overlay (commentary triggers extracted from letter)
        4. Apply engagement_hash for change detection

        This is the single entry point used by the transaction runner.
        """
        profile = cls.from_amc_id(amc_id)
        profile.engagement_hash = engagement_hash

        # Merge loan-type sub-profile (e.g. FHA adds comp_age_hard_limit_months: 12)
        if loan_type:
            sub = _load_amc_loan_subprofile(amc_id, loan_type)
            for key, val in sub.items():
                if hasattr(profile, key):
                    setattr(profile, key, val)
                else:
                    profile.engagement_overlays[key] = val

        # Per-case overlay: only apply what the letter explicitly states differently
        # from the AMC base policy. For Equity Solutions USA this is almost nothing
        # since the body is static — but future AMCs may have case-specific content.
        if overlay is not None:
            profile.apply_overlay(overlay)
        return profile


# ── Module-level helpers ──────────────────────────────────────────────────────

_AMC_POLICY_CACHE: Optional[dict] = None
_AMC_POLICY_PATH = (
    __import__("pathlib").Path(__file__).parent.parent.parent / "config" / "amc_policies.yaml"
)


def _load_all_amc_policies() -> dict:
    """Load and cache config/amc_policies.yaml."""
    global _AMC_POLICY_CACHE
    if _AMC_POLICY_CACHE is not None:
        return _AMC_POLICY_CACHE
    try:
        import yaml
        with open(_AMC_POLICY_PATH) as f:
            _AMC_POLICY_CACHE = yaml.safe_load(f) or {}
    except Exception as exc:
        logger.warning("amc_policies.yaml load failed: %s — using empty policy", exc)
        _AMC_POLICY_CACHE = {}
    return _AMC_POLICY_CACHE


def _load_amc_policy(amc_id: Optional[str]) -> dict:
    """
    Return the flat policy dict for an AMC, or the __default__ section.

    Tries fuzzy matching: "equity_solutions_usa" matches keys containing "equity"
    so minor spelling variants in the classifier don't break the lookup.
    """
    all_policies = _load_all_amc_policies()
    if not amc_id:
        return dict(all_policies.get("__default__", {}))

    # Exact match first
    if amc_id in all_policies:
        base = dict(all_policies.get("__default__", {}))
        base.update(all_policies[amc_id])
        return base

    # Fuzzy: any AMC key that is a substring of amc_id or vice-versa
    amc_lower = amc_id.lower()
    for key in all_policies:
        if key == "__default__":
            continue
        kl = key.lower()
        if kl in amc_lower or amc_lower in kl:
            base = dict(all_policies.get("__default__", {}))
            base.update(all_policies[key])
            logger.info("AMC policy fuzzy match: '%s' → '%s'", amc_id, key)
            return base

    logger.info("No AMC policy found for '%s' — using defaults", amc_id)
    return dict(all_policies.get("__default__", {}))


def _load_amc_loan_subprofile(amc_id: Optional[str], loan_type: str) -> dict:
    """Return the loan-type sub-profile dict (e.g. amc_policies[amc_id]['fha'])."""
    all_policies = _load_all_amc_policies()
    amc_policy = None
    if amc_id and amc_id in all_policies:
        amc_policy = all_policies[amc_id]
    if amc_policy is None:
        return {}
    return dict(amc_policy.get(loan_type.lower(), {}))
