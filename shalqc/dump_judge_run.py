"""Run ONE order in judge-mode, capture EVERY raw LLM response + every full
verdict, and write them to readable files. Reports wall-clock time + LLM calls.

Usage:  PYTHONPATH=. python dump_judge_run.py ESTX-0007568
"""
import sys, os, time, json, glob, logging
logging.basicConfig(level=logging.ERROR)

from app.llm.client import get_client
from app.extraction.merge import run_extraction
from app.extraction.engagement import extract_engagement
from app.rules.context import QCContext
from app.rules.engine import run_rules
from app.profiles.loader import load_profile
from app.profiles.engine_binding import active_rules, apply_severity
from app.routing.router import router


def find_order(order_arg):
    base = f"testfiles/{order_arg}"
    if not os.path.isdir(base):
        cands = glob.glob(f"testfiles/{order_arg}*")
        base = next((c for c in cands if os.path.isdir(c)), None)
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

    client = get_client()

    # ---- wrap complete() to capture the RAW response of every call ----
    raw_calls = []
    _orig = client.complete

    def _capture(call_type, system, user, max_tokens=1024):
        res = _orig(call_type, system, user, max_tokens=max_tokens)
        raw_calls.append({
            "call_type": call_type,
            "provider": res.call.provider,
            "cached": res.call.cached,
            "ok": res.ok,
            "ms": round(res.call.ms, 1),
            "user_prompt": user,
            "response": res.data,   # the parsed JSON the LLM returned
        })
        return res

    client.complete = _capture

    t0 = time.time()
    a = run_extraction(appraisal_pdf=pdf, xml_path=xml, engagement_letter=None)
    e = extract_engagement(eng) if eng else None
    router.apply(a)
    if e:
        router.apply(e)
    prof = load_profile("EQUITYSOLUTIONS")
    ctx = QCContext(order_id=name, appraisal=a, engagement=e, profile=prof,
                    review_conf=0.70, llm_client=client)
    c0 = len(client.telemetry)
    verdicts = run_rules(ctx, rules=active_rules(prof), llm_client=client, judge_mode=True)
    apply_severity(prof, verdicts)
    dt = time.time() - t0
    calls = len(client.telemetry) - c0

    # ---- dump full verdicts (JSON + readable txt) ----
    outdir = "judge_runs"
    os.makedirs(outdir, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")

    vdump = []
    for v in verdicts:
        vdump.append({
            "rule": v.rule_id,
            "status": v.status.value,
            "judged_by": getattr(v, "judged_by", None),
            "reason": getattr(v, "reason_plain", None) or v.message,
            "values": [f"{ev.document}.{ev.field}={ev.value}"
                       for ev in v.evidence if getattr(ev, "value", None)][:8],
        })

    vjson = f"{outdir}/{name}_{stamp}_verdicts.json"
    rjson = f"{outdir}/{name}_{stamp}_raw_llm.json"
    txt = f"{outdir}/{name}_{stamp}_readable.txt"
    json.dump(vdump, open(vjson, "w"), indent=2)
    json.dump(raw_calls, open(rjson, "w"), indent=2)

    order_status = ["PASS", "FAIL", "VERIFY", "HOLD", "NA"]
    with open(txt, "w") as fh:
        fh.write(f"JUDGE RUN — {name}\n")
        fh.write(f"time: {dt:.1f}s   LLM calls: {calls}   verdicts: {len(verdicts)}\n")
        fh.write("=" * 70 + "\n\n")
        for st in order_status:
            group = [v for v in vdump if v["status"].upper().startswith(st[:4])]
            if not group:
                continue
            fh.write(f"----- {st}  ({len(group)}) -----\n")
            for v in group:
                fh.write(f"[{v['status']}] {v['rule']}  (judged_by={v['judged_by']})\n")
                fh.write(f"    reason: {v['reason']}\n")
                if v["values"]:
                    fh.write(f"    values: {', '.join(v['values'])}\n")
                fh.write("\n")

    print(f"TIME: {dt:.1f}s   LLM CALLS: {calls}   VERDICTS: {len(verdicts)}")
    counts = {}
    for v in vdump:
        counts[v["status"]] = counts.get(v["status"], 0) + 1
    print("STATUS:", counts)
    print("RAW LLM RESPONSES CAPTURED:", len(raw_calls))
    print("FILES:")
    print("  ", txt)
    print("  ", vjson)
    print("  ", rjson)


if __name__ == "__main__":
    main()
