"""LLM call telemetry — attribute every Groq call's real cost to the rule or
pipeline stage that triggered it.

The QC engine sets the "span" to the current rule id before running a rule; the
transaction orchestrator sets it to the current stage name. llm_groq.chat_json
records one LLMCall per call into the active capture sink, separating the two
costs that look identical in plain wall-clock time but mean different things:

  * throttle_wait_ms — time we WAITED before/around the call (our own TPM token
    bucket pre-wait plus 429/503 retry-after backoffs). High → call frequency /
    rate-limit pressure → fix with queuing, not prompt size.
  * inference_ms — time the Groq API actually took to respond. High → prompt is
    large / model is slow → fix with prompt size, not queuing.

All values are measured (perf_counter); nothing here is estimated. Capture is
opt-in per request (start_capture/stop_capture); when no sink is active,
record() is a no-op so the LLM path is unaffected outside a measured run.

contextvars (not thread-locals) carry the span + sink: the rule engine and the
LLM overlay stages run on the calling thread, so the context propagates cleanly.
"""

from __future__ import annotations

import contextvars
from dataclasses import dataclass
from typing import List, Optional

_span: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar("llm_span", default=None)
_sink: contextvars.ContextVar[Optional[List]] = contextvars.ContextVar("llm_sink", default=None)


@dataclass
class LLMCall:
    span: Optional[str]            # rule id (e.g. "SCA-14") or stage (e.g. "subject_llm")
    model: str
    throttle_wait_ms: float        # pre-wait (TPM bucket) + 429/503 backoff sleeps
    inference_ms: float            # sum of the actual HTTP request latencies
    attempts: int
    rate_limited: bool             # any attempt returned 429
    ok: bool                       # a parsed result was returned


# ── span: which rule/stage is currently executing ──────────────────────────

def set_span(name: Optional[str]):
    """Set the current attribution span; returns a token for reset()."""
    return _span.set(name)


def reset_span(token) -> None:
    try:
        _span.reset(token)
    except (ValueError, LookupError):
        pass


def current_span() -> Optional[str]:
    return _span.get()


# ── capture: collect calls for one measured run ────────────────────────────

def start_capture() -> List[LLMCall]:
    """Begin capturing LLM calls; returns the list calls accumulate into."""
    calls: List[LLMCall] = []
    _sink.set(calls)
    return calls


def stop_capture() -> None:
    _sink.set(None)


def record(call: LLMCall) -> None:
    sink = _sink.get()
    if sink is not None:
        sink.append(call)
