"""
Mock LLM server — OpenAI/Groq-compatible chat-completions endpoint.

Purpose: run the QC pipeline's LLM code path with ZERO external dependency, so a
load test measures the *system's* capacity (OCR + rules + DB + Java↔Python) instead
of the Groq TPM ceiling or network latency. Point GROQ_BASE_URL at this server.

It accepts any POST (…/chat/completions), returns a well-formed completion whose
content is a minimal JSON object, and reports tiny token usage so the client-side
TPM throttle never trips. Deterministic + instant.

Run:  uvicorn scripts.loadtest.mock_llm:app --host 127.0.0.1 --port 5099
"""
from __future__ import annotations

import time
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

app = FastAPI(title="Mock LLM (Groq-compatible)")

# Counters so the load report can show how many LLM calls the pipeline actually made.
STATE = {"calls": 0}


@app.get("/healthz")
async def healthz():
    return {"ok": True, "calls": STATE["calls"]}


@app.post("/{full_path:path}")
async def chat_completions(full_path: str, request: Request):
    STATE["calls"] += 1
    # Body is ignored on purpose — we never call a real model. Return an empty JSON
    # object as the assistant content; the extractor parses it and falls back to its
    # deterministic readers, so the full pipeline still runs end-to-end.
    body = {
        "id": f"mock-{STATE['calls']}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": "mock-llm",
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": "{}"},
                "finish_reason": "stop",
            }
        ],
        # Tiny usage so the TPM token-bucket never throttles.
        "usage": {"prompt_tokens": 5, "completion_tokens": 2, "total_tokens": 7},
    }
    return JSONResponse(body)
