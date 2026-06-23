#!/usr/bin/env python3
"""
Capture the REAL data sent to the LLM for one transaction — text vs image, and the
exact content — with ZERO Groq calls. Patches chat_json / vision_chat_json to dump
each call's payload to /tmp/shal-loadtest/prompts/ and return a stub.

Run (project root): PYTHONPATH=ocr-service python3 scripts/loadtest/dump_llm_prompts.py <appraisal> [contract] [engagement]
"""
import sys
from pathlib import Path

OUT = Path("/tmp/shal-loadtest/prompts")


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    for f in OUT.glob("*.txt"):
        f.unlink()
    import app.extraction.llm_groq as g
    idx = {"n": 0}

    def _label(messages):
        blob = " ".join(m.get("content", "") for m in messages).lower()
        if "comparable" in blob and ("sale price" in blob or "grid" in blob or "adjustment" in blob):
            return "SCA_GRID"
        if "neighborhood" in blob or "one-unit housing" in blob or "land use" in blob:
            return "NEIGHBORHOOD"
        if "contract" in blob and "price" in blob:
            return "CONTRACT"
        if "owner of public record" in blob or "assessor" in blob or "subject" in blob:
            return "SUBJECT"
        if "json object {\"answer\"" in blob or "answer with only" in blob:
            return "JUDGMENT(assess_text)"
        return "OTHER"

    def _dump_text(messages, **kw):
        idx["n"] += 1
        n = idx["n"]
        label = _label(messages)
        body = []
        for m in messages:
            body.append(f"--- role={m.get('role')} ---\n{m.get('content','')}")
        text = "\n".join(body)
        approx = len(text) // 4
        (OUT / f"call_{n:02d}_{label}.txt").write_text(
            f"# CALL {n}  type=TEXT  label={label}  approx_tokens={approx}  "
            f"reasoning_effort={kw.get('reasoning_effort')}  max_tokens={kw.get('max_tokens')}\n\n{text}\n"
        )
        return {}

    def _dump_vision(image_bytes, prompt):
        idx["n"] += 1
        n = idx["n"]
        (OUT / f"call_{n:02d}_VISION.txt").write_text(
            f"# CALL {n}  type=VISION(IMAGE)  image_bytes={len(image_bytes)}  "
            f"prompt_chars={len(prompt)}\n\nPROMPT:\n{prompt}\n"
        )
        return {}

    g.chat_json = _dump_text
    g.vision_chat_json = _dump_vision

    from app.qc.transaction import run_transaction_qc_paths
    args = sys.argv[1:]
    appraisal = Path(args[0])
    contract = Path(args[1]) if len(args) > 1 else None
    engagement = Path(args[2]) if len(args) > 2 else None
    print(f"appraisal={appraisal}\ncontract={contract}\nengagement={engagement}")
    run_transaction_qc_paths(appraisal, engagement, contract, transaction_id="dump", persist=False)

    files = sorted(OUT.glob("*.txt"))
    print(f"\n{len(files)} LLM calls captured -> {OUT}")
    for f in files:
        head = f.read_text().splitlines()[0]
        print(f"  {f.name:40} {head}")


if __name__ == "__main__":
    main()
