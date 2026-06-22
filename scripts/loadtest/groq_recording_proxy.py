"""
Groq recording proxy — forwards chat-completions to REAL Groq and records token usage.

Purpose: measure the EXACT token cost per document of the real gpt-oss-120b pipeline
without a code change, and with a hard daily-quota guard. Point GROQ_BASE_URL at this
server; it relays the request (with the caller's Authorization header) to api.groq.com,
logs `usage`, and refuses to forward once a cumulative token cap is hit.

Run:  PROBE_TOKEN_CAP=40000 uvicorn groq_recording_proxy:app --host 127.0.0.1 --port 5099
"""
from __future__ import annotations

import json
import os
import threading
import time

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

REAL_ROOT = "https://api.groq.com"
CAP = int(os.getenv("PROBE_TOKEN_CAP", "40000"))
LOG = os.getenv("PROBE_LOG", "/tmp/apprisal-loadtest/groq_usage.jsonl")

app = FastAPI(title="Groq recording proxy")
STATE = {"calls": 0, "total_tokens": 0, "prompt_tokens": 0, "completion_tokens": 0,
         "halted": False, "cap": CAP}
_lock = threading.Lock()


@app.get("/stats")
async def stats():
    return STATE


@app.post("/{path:path}")
async def forward(path: str, request: Request):
    with _lock:
        if STATE["halted"] or STATE["total_tokens"] >= CAP:
            STATE["halted"] = True
            return JSONResponse(status_code=429,
                                content={"error": {"message": "probe token cap reached"}})
    body = await request.body()
    headers = {k: v for k, v in request.headers.items()
               if k.lower() in ("authorization", "content-type")}
    try:
        async with httpx.AsyncClient(timeout=90) as c:
            r = await c.post(f"{REAL_ROOT}/{path}", content=body, headers=headers)
    except Exception as exc:
        return JSONResponse(status_code=502, content={"error": {"message": f"proxy: {exc}"}})

    try:
        data = r.json()
    except Exception:
        return JSONResponse(status_code=r.status_code, content={"raw": r.text[:500]})

    usage = (data.get("usage") or {}) if isinstance(data, dict) else {}
    tt = int(usage.get("total_tokens") or 0)
    pt = int(usage.get("prompt_tokens") or 0)
    ct = int(usage.get("completion_tokens") or 0)
    with _lock:
        STATE["calls"] += 1
        STATE["total_tokens"] += tt
        STATE["prompt_tokens"] += pt
        STATE["completion_tokens"] += ct
    try:
        with open(LOG, "a") as f:
            f.write(json.dumps({"t": round(time.time(), 3), "call": STATE["calls"],
                                "status": r.status_code, "prompt": pt, "completion": ct,
                                "total": tt}) + "\n")
    except OSError:
        pass
    return JSONResponse(status_code=r.status_code, content=data)
