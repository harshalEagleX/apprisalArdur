#!/usr/bin/env python
"""Stage A grading harness — LLM comprehension ACCURACY in isolation (no verdicts).

Runs the Stage-2 LLM comprehension pass (app/qc/llm_comprehension.py) on the
exttestfile order corpus and grades the STRUCTURED FACTS it returns against a
hand-built answer key. It never looks at a rule verdict — this measures the
*reading*, which is the test of whether the LLM earns its place (Stage A precedes
Stage B, which measures end-to-end verdict deltas).

This is a MANUAL grading tool, not part of the QC path. The deterministic
guardrail assertions it exercises are ALSO pinned as always-on unit tests in
app/qc/tests/test_llm_comprehension.py — this script adds the live, key-dependent
reading-accuracy grade the unit tests cannot run.

Two halves, each self-contained:

  LIVE grading   — runs only when a provider is configured (Groq/Together keys via
                   .env). Enables the pass, runs comprehend() on each order, prints
                   emitted llm_* facts side-by-side with the answer key, marks
                   MATCH / MISS, and runs each order twice to check determinism.

  GUARDRAIL      — runs ALWAYS (no keys) by stubbing the provider. Proves the four
  PROBES           safety properties: grounding drops a hallucinated quote, strict
                   schema drops a bad enum, an "unknown" read emits nothing (→ rule
                   falls back to VERIFY), and the pass is a strict no-op when
                   disabled or when no provider is configured.

Usage:
    # offline — guardrails + answer key + narrative floor only:
    python scripts/qc/stage_a_comprehension_grade.py
    # live grading — keys come from ocr-service/.env (or the environment):
    LLM_EXTRACTION_ENABLED=true LLM_COMPREHENSION_ENABLED=true \
        python scripts/qc/stage_a_comprehension_grade.py
"""
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
OCR = REPO / "ocr-service"
CORPUS = OCR / "exttestfile"
CASES = ["ESMI-0048528", "ESMI-0048541", "ESMI-0048569", "ESNV-0000872"]

# ── ANSWER KEY — hand-verified from the actual XML narratives (2026-07-10) ─────
# Each order records the TRUE reading of the two concerns. "expect" is the value
# the llm_* fact SHOULD carry; None means the fact should NOT be emitted (the
# narrative does not state it, so the rule must fall back). This is what we grade.
ANSWER_KEY = {
    "ESMI-0048528": {
        "llm_trend_property_values": "stable",      # "values ... mainly flat", "stabilizing"
        "llm_trend_financing_rates": "stable",      # "mortgages remain relatively low"
        "llm_updates_described": "yes",             # kitchen/bath 11-15 yrs; paint/flooring/HWH/furnace
        "_notes": "values flat + rates low; substantive updates w/ 11-15yr recency",
    },
    "ESMI-0048541": {                               # THE critical value-vs-rate case
        "llm_trend_property_values": "stable",      # "mostly stable comparable property values"
        "llm_trend_financing_rates": "increasing",  # "financing rates have increased"
        "llm_updates_described": "yes",             # kitchen; bath; flooring; paint; furnace; AC; doors; porch
        "_notes": "MUST separate stable VALUES from increasing RATES — the N-2 fix",
    },
    "ESMI-0048569": {
        "llm_trend_property_values": "stable",      # historically rising but "now ... stabilizing"
        "llm_trend_financing_rates": "stable",      # "Interest rates appear to be stable"
        "llm_updates_described": "yes",             # EWP, paint, generator, doors, fence, fans
        "_notes": "trap: values rose historically but CURRENT trend is stable (elided-quote grounding case)",
    },
    "ESNV-0000872": {                               # the genuine NO-UPDATES / inverse case
        "llm_trend_property_values": "stable",      # "market is considered stable"
        "llm_trend_financing_rates": None,          # no rate-trend stated → must NOT emit
        "llm_updates_described": None,              # "No updates in the prior 15 years" → must NOT claim yes
        "_notes": "INVERSE: explicit no-updates -> updates fact must stay absent -> age VERIFY",
    },
}
GRADED_FIELDS = ["llm_trend_property_values", "llm_trend_financing_rates", "llm_updates_described"]


# ── rs builder (cheap path — XML + the two narrative overlays comprehend reads) ─
def build_rs(case):
    from app.extraction.xml_extractor import extract_xml
    from app.qc import transaction as tx
    d = CORPUS / case / "apprisal"
    xml = (list(d.glob("*.xml")) + list(d.glob("*.XML")))[0]
    pdf = [p for p in d.glob("*.pdf") if "contract" not in p.name.lower()][0]
    rs = extract_xml(xml)
    rs = tx._overlay_narrative(rs, pdf, "appraisal_report")
    rs = tx._overlay_certification_addendum(rs, pdf, "appraisal_report")
    return rs


def _llm_facts(rs):
    return {n: str(r.value) for n, r in rs if n.startswith("llm_")}


# ── LIVE grading ──────────────────────────────────────────────────────────────
def run_live():
    from app import config
    from app.extraction import llm_groq
    from app.qc.llm_comprehension import comprehend
    config.LLM_COMPREHENSION_ENABLED = True
    if not (llm_groq.together_extraction_available() or llm_groq.groq_extraction_available()):
        return False  # not configured — caller runs offline path

    print("\n" + "=" * 78)
    print("LIVE Stage A grading  (comprehension facts vs answer key)")
    print("=" * 78)
    passed = True
    for case in CASES:
        if not (CORPUS / case).exists():
            print(f"\n[{case}] SKIPPED — not extracted under exttestfile/")
            continue
        facts1 = _llm_facts(comprehend(build_rs(case), "appraisal_report"))
        facts2 = _llm_facts(comprehend(build_rs(case), "appraisal_report"))
        determinism = "OK" if facts1 == facts2 else "*** NON-DETERMINISTIC ***"
        key = ANSWER_KEY[case]
        print(f"\n[{case}]  {key['_notes']}")
        print(f"  determinism (2 runs identical): {determinism}")
        for f in GRADED_FIELDS:
            want, got = key[f], facts1.get(f)
            if want is None:
                ok = got is None
                verdict = "MATCH (absent)" if ok else f"MISS  got {got!r}, must be ABSENT"
            else:
                ok = got == want
                verdict = "MATCH" if ok else f"MISS  want {want!r}, got {got!r}"
            passed = passed and ok
            print(f"    {f:<30} {verdict}")
        detail = {k: facts1[k] for k in sorted(facts1) if k not in GRADED_FIELDS}
        if detail:
            print(f"    supporting facts: {detail}")
    print("\n" + ("STAGE A: PASS" if passed else "STAGE A: FAIL — see MISS lines above"))
    return True


# ── GUARDRAIL probes (no keys — stub the provider) ─────────────────────────────
class _Swap:
    """Minimal monkeypatch: set attrs, restore on exit."""
    def __init__(self): self._saved = []
    def set(self, obj, name, val):
        self._saved.append((obj, name, getattr(obj, name)))
        setattr(obj, name, val)
    def __enter__(self): return self
    def __exit__(self, *a):
        for obj, name, val in reversed(self._saved):
            setattr(obj, name, val)


def _enable(sw, reply):
    from app import config
    from app.extraction import llm_groq
    sw.set(config, "LLM_COMPREHENSION_ENABLED", True)
    sw.set(llm_groq, "together_extraction_available", lambda: True)
    sw.set(llm_groq, "groq_extraction_available", lambda: False)
    sw.set(llm_groq, "chat_json", lambda messages, **kw: reply(messages[1]["content"]))


def _mkt_rs():
    from app.core.result import ExtractionResult, ExtractionResultSet
    rs = ExtractionResultSet(document_path="t.pdf", document_type="appraisal_report")
    rs.add(ExtractionResult(canonical_name="market_conditions_commentary",
           document_type="appraisal_report",
           value="Property values remained stable while financing rates increased sharply.",
           confidence=0.9, extraction_method="xml", source_page=1))
    rs.finalize()
    return rs


def run_guardrails():
    from app import config
    from app.qc.llm_comprehension import comprehend
    print("=" * 78)
    print("GUARDRAIL probes  (deterministic, no keys required)")
    print("=" * 78)
    results = []

    with _Swap() as sw:  # 1. GROUNDING — quote absent from the text is dropped.
        _enable(sw, lambda u: {"property_value_trend": "declining",
                               "property_value_quote": "values are falling fast",
                               "financing_rate_trend": "unknown"})
        results.append(("grounding drops hallucinated quote",
                        _llm_facts(comprehend(_mkt_rs(), "appraisal_report")) == {}))

    with _Swap() as sw:  # 2. STRICT SCHEMA — bad enum coerces to drop.
        _enable(sw, lambda u: {"property_value_trend": "sideways-ish",
                               "property_value_quote": "remained stable"})
        results.append(("strict schema drops bad enum",
                        _llm_facts(comprehend(_mkt_rs(), "appraisal_report")) == {}))

    with _Swap() as sw:  # 3. CONFIDENCE FLOOR — 'unknown' emits nothing → VERIFY.
        _enable(sw, lambda u: {"property_value_trend": "unknown",
                               "financing_rate_trend": "unknown",
                               "explicit_stable_values_statement": False})
        results.append(("unknown read emits nothing (falls back to VERIFY)",
                        _llm_facts(comprehend(_mkt_rs(), "appraisal_report")) == {}))

    with _Swap() as sw:  # 4a. NO-OP when disabled.
        sw.set(config, "LLM_COMPREHENSION_ENABLED", False)
        rs = _mkt_rs()
        results.append(("no-op when disabled (same object back)", comprehend(rs) is rs))

    with _Swap() as sw:  # 4b. NO-OP when no provider configured.
        from app.extraction import llm_groq
        sw.set(config, "LLM_COMPREHENSION_ENABLED", True)
        sw.set(llm_groq, "together_extraction_available", lambda: False)
        sw.set(llm_groq, "groq_extraction_available", lambda: False)
        rs = _mkt_rs()
        results.append(("no-op when no provider (same object back)", comprehend(rs) is rs))

    with _Swap() as sw:  # 5. DETERMINISM (stubbed) — identical reply → identical facts.
        _enable(sw, lambda u: {"property_value_trend": "stable",
                               "property_value_quote": "values remained stable",
                               "financing_rate_trend": "increasing",
                               "financing_rate_quote": "financing rates increased"})
        a = _llm_facts(comprehend(_mkt_rs(), "appraisal_report"))
        b = _llm_facts(comprehend(_mkt_rs(), "appraisal_report"))
        results.append(("determinism: identical input → identical facts", a == b and a != {}))

    for name, ok in results:
        print(f"  [{'PASS' if ok else 'FAIL'}] {name}")
    print("\n" + ("ALL GUARDRAILS PASS" if all(o for _, o in results)
                  else "GUARDRAIL FAILURE — investigate before Stage B"))
    return all(o for _, o in results)


def print_answer_key():
    print("=" * 78)
    print("ANSWER KEY  (hand-verified from XML narratives)")
    print("=" * 78)
    for case in CASES:
        k = ANSWER_KEY[case]
        print(f"  {case}: {k['_notes']}")
        for f in GRADED_FIELDS:
            print(f"      {f:<30} -> {k[f]!r}")
    print()


def main():
    print_answer_key()
    run_guardrails()
    if not run_live():
        print("\n(LIVE grading skipped — no provider configured. Set "
              "LLM_EXTRACTION_ENABLED + LLM_COMPREHENSION_ENABLED + a key to grade "
              "the reading against the answer key above.)")


if __name__ == "__main__":
    sys.path.insert(0, str(OCR))
    main()
