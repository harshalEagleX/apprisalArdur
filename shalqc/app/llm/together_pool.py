"""
llm.together_pool (pool-1.0.0) — per-key token-bucket + in-flight governor for
the (single-provider, Together-only) LLM subsystem.

2026-07-13: replaces the Together→Groq failover chain. The chain reacted to a
429/413 AFTER sending a request the provider's tier couldn't take; this stops
the request from being SENT in the first place when a key doesn't have the
budget, by tracking each key's remaining tokens-per-minute allowance and
in-flight request count locally. Picking the key with the most headroom (not
strict round-robin) means a burst of calls spreads itself across keys instead
of queueing behind whichever key happens to be next.

Not a distributed rate limiter — state is per-process (per-worker), which
matches the deployment model (each worker owns whole orders end-to-end, all
sharing the process-local pool instance).
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import List, Optional

__version__ = "pool-1.0.0"

_CHARS_PER_TOKEN = 4.0  # rough estimate — good enough for a budget reservation,
                        # not an exact tokenizer match.


def estimate_tokens(system: str, user: str, max_tokens: int) -> float:
    """Estimate the token cost of one call: prompt tokens (rough chars/4) plus
    the FULL requested output budget (max_tokens) — reserved up front, since
    the provider counts the requested ceiling against tokens-per-minute
    quotas even before generation finishes."""
    prompt_chars = len(system) + len(user)
    return prompt_chars / _CHARS_PER_TOKEN + max_tokens


@dataclass
class _KeyState:
    key: str
    tpm_budget: float
    available: float
    last_refill: float
    max_inflight: int
    inflight: int = 0

    def refill_locked(self) -> None:
        """Caller must hold the pool lock. Leaky-bucket refill proportional to
        elapsed wall time."""
        now = time.monotonic()
        elapsed = now - self.last_refill
        self.last_refill = now
        if elapsed > 0:
            self.available = min(self.tpm_budget, self.available + elapsed / 60.0 * self.tpm_budget)


class TogetherPool:
    """Pick a Together API key with enough token budget AND a free in-flight
    slot; debit the estimate before sending, credit the in-flight slot back
    on release. `acquire()` blocks briefly (polling) if every key is
    momentarily saturated — a real burst drains in well under a second once
    any key's bucket refills, rather than failing the call outright."""

    def __init__(self, keys: List[str], tpm_budget_per_key: float, max_inflight_per_key: int) -> None:
        self._lock = threading.Lock()
        now = time.monotonic()
        self._states = [
            _KeyState(key=k, tpm_budget=tpm_budget_per_key, available=tpm_budget_per_key,
                      last_refill=now, max_inflight=max_inflight_per_key)
            for k in keys
        ]

    @property
    def num_keys(self) -> int:
        return len(self._states)

    def acquire(self, estimated_tokens: float, timeout: float = 20.0) -> Optional[str]:
        """Return a key with capacity for `estimated_tokens`, or None if no key
        freed up within `timeout` seconds (the pool is genuinely saturated —
        the caller should treat this like any other call failure, not retry
        indefinitely)."""
        deadline = time.monotonic() + timeout
        while True:
            with self._lock:
                candidates = sorted(self._states, key=lambda s: -s.available)
                for st in candidates:
                    st.refill_locked()
                    if st.available >= estimated_tokens and st.inflight < st.max_inflight:
                        st.available -= estimated_tokens
                        st.inflight += 1
                        return st.key
            if time.monotonic() >= deadline:
                return None
            time.sleep(0.05)

    def release(self, key: str) -> None:
        """Free the in-flight slot. The token debit is NOT refunded — it
        decays back via the bucket's normal per-minute refill, which is
        simpler and safe (a slight under-estimate of true throughput, never
        an over-commit)."""
        with self._lock:
            for st in self._states:
                if st.key == key:
                    st.inflight = max(0, st.inflight - 1)
                    return
