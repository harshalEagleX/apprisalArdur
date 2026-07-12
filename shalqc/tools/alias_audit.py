"""tools/alias_audit.py — find rule-vs-extraction field-name drift.

Runs the DETERMINISTIC pass only (no LLM), builds every fact packet, collects
every `missing_fields` entry the judge would have seen, and fuzzy-matches each
against the names actually present in extraction. Emits a candidate alias table
so the drift can be closed as schema synonyms / resolver aliases.

Usage:  PYTHONPATH=. python tools/alias_audit.py ESTX-0007568
Output: tools/out/<order>_alias_candidates.csv  (+ printed summary)
"""
import sys, os, glob, csv, logging, re
from collections import defaultdict
logging.basicConfig(level=logging.ERROR)

from app.extraction.merge import run_extraction
from app.extraction.engagement import extract_engagement
from app.rules.context import QCContext
from app.rules.engine import run_rules
from app.rules.packet import build_packet
from app.profiles.loader import load_profile
from app.profiles.engine_binding import active_rules
from app.routing.router import router

_SUFFIXES = ("_rating", "_type", "_flag", "_value", "_amount", "_desc",
             "_description", "_range", "_status", "_date")


def _tokens(name: str):
    n = name.lower()
    # collapse comp indexes so comp_1_x and comp_3_x share tokens
    n = re.sub(r"comp_\d+", "comp_n", n)
    for s in _SUFFIXES:
        if n.endswith(s):
            n = n[: -len(s)]
    n = n.rstrip("s")  # singular/plural
    return set(t for t in re.split(r"[_\s]+", n) if t)


def _score(missing: str, cand: str) -> float:
    a, b = _tokens(missing), _tokens(cand)
    if not a or not b:
        return 0.0
    jac = len(a & b) / len(a | b)
    # bonus when one is a substring family of the other (comp_n_quality ⊂ comp_n_quality_rating)
    sub = 0.15 if (a <= b or b <= a) else 0.0
    return round(min(1.0, jac + sub), 3)


def find_order(order_arg):
    base = f"testfiles/{order_arg}"
    if not os.path.isdir(base):
        base = next((c for c in glob.glob(f"testfiles/{order_arg}*") if os.path.isdir(c)), None)
    if not base:
        sys.exit(f"order not found: {order_arg}")
    pdf = next(iter(glob.glob(f"{base}/appraisal/*.pdf")), None)
    xml = next(iter(glob.glob(f"{base}/appraisal/*.xml")), None)
    eng = next(iter(glob.glob(f"{base}/engagement/*.pdf")), None)
    return base, pdf, xml, eng


def main():
    order = sys.argv[1] if len(sys.argv) > 1 else "ESTX-0007568"
    base, pdf, xml, eng = find_order(order)
    name = os.path.basename(base)

    appraisal = run_extraction(appraisal_pdf=pdf, xml_path=xml, engagement_letter=None)
    engagement = extract_engagement(eng) if eng else None
    router.apply(appraisal)
    if engagement:
        router.apply(engagement)
    prof = load_profile("EQUITYSOLUTIONS")
    ctx = QCContext(order_id=name, appraisal=appraisal, engagement=engagement,
                    profile=prof, review_conf=0.70, llm_client=None)

    # deterministic pass only — no LLM
    verdicts = run_rules(ctx, rules=active_rules(prof), llm_client=None, judge_mode=False)

    # collect every missing field the judge would see, with the rule that raised it
    missing_by_field = defaultdict(set)
    for v in verdicts:
        pkt = build_packet(v, ctx, requirement=v.rule_id)
        for m in pkt.missing_fields:
            missing_by_field[m].add(v.rule_id)

    # candidate pool = every extracted key name (appraisal + engagement)
    extracted = {}
    for docname, view in (("appraisal", ctx.appraisal), ("engagement", ctx.engagement)):
        for k in getattr(view, "_by_name", {}):
            ef = view._by_name[k]
            if ef.found:
                extracted[k] = (docname, ef.value)

    os.makedirs("tools/out", exist_ok=True)
    out = f"tools/out/{name}_alias_candidates.csv"
    rows = []
    for miss in sorted(missing_by_field):
        bare = miss.split(".", 1)[-1]
        scored = sorted(((_score(bare, k), k) for k in extracted),
                        reverse=True)[:3]
        top = [(s, k) for s, k in scored if s >= 0.34]
        rows.append({
            "missing_field": miss,
            "raised_by": ",".join(sorted(missing_by_field[miss])),
            "best_candidate": top[0][1] if top else "",
            "best_score": top[0][0] if top else 0,
            "cand_value": extracted.get(top[0][1], ("", ""))[1] if top else "",
            "other_candidates": " | ".join(f"{k}({s})" for s, k in top[1:]),
        })

    with open(out, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()) if rows else ["missing_field"])
        w.writeheader()
        w.writerows(rows)

    matched = [r for r in rows if r["best_score"] >= 0.5]
    weak = [r for r in rows if 0.34 <= r["best_score"] < 0.5]
    none = [r for r in rows if r["best_score"] < 0.34]
    print(f"order: {name}")
    print(f"total distinct missing fields: {len(rows)}")
    print(f"  strong alias candidate (>=0.50): {len(matched)}")
    print(f"  weak candidate (0.34-0.50):      {len(weak)}")
    print(f"  no candidate (likely real gap):  {len(none)}")
    print(f"CSV: {out}\n")
    print("=== STRONG CANDIDATES (missing -> extracted alias) ===")
    for r in matched:
        print(f"  {r['missing_field']:34} -> {r['best_candidate']:30} "
              f"[{r['best_score']}]  = {str(r['cand_value'])[:24]}")
    print("\n=== NO CANDIDATE (real absence or derive-only) ===")
    for r in none:
        print(f"  {r['missing_field']:34} (raised by {r['raised_by']})")


if __name__ == "__main__":
    main()
