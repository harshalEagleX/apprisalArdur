"""
pipeline.progress (prog-1.0.0) — in-process QC progress registry.

The Java side generates a `progress_token`, hands it to `/qc/process`, and polls
`GET /qc/progress/{token}` every ~1.5s to drive the admin "Background activity"
bar (see PythonClientService.pollSubProgress → QCProgressService.smoothedPercent).
Before this module the endpoint was an unimplemented stub, so the poller only ever
got 404s and the bar sat frozen at the file-level base percent for the whole run.

Design notes
------------
* **In-process, not Redis.** `/qc/process` is synchronous and single-order; the
  handler and the progress poll are served by the same uvicorn process, so a
  thread-safe module-level dict is sufficient (SHALqc.md §9's Redis token store
  is only needed for the Celery/async trio, which this build does not run).

* **Time-based easing between real stage markers.** The dominant cost is the LLM
  judge phase, which has no per-item callback — a purely event-driven percent
  would jump 0.35 → 0.90 in one step and sit frozen for minutes in between. So a
  stage sets a `floor` (its real starting percent) and a `ceil` (the next stage's
  floor); `snapshot()` eases from floor toward ceil asymptotically with elapsed
  time. The bar therefore always creeps forward during a long stage, but is
  re-grounded to the real percent every time a stage actually advances, and it
  never overshoots the ceiling or reaches 1.0 until `finish()` is called.

Tokens are evicted after `_TTL_S` so a crashed run cannot leak entries.
"""

from __future__ import annotations

import math
import threading
import time
from typing import Dict, Optional

__version__ = "prog-1.0.0"

_TTL_S = 1800.0            # evict a token 30 min after its last write
_DEFAULT_TAU_S = 45.0      # easing time-constant when a stage doesn't set one


class _Entry:
    __slots__ = ("stage", "message", "floor", "ceil", "tau",
                 "stage_started", "run_started", "last_touch", "done")

    def __init__(self, now: float):
        self.stage = "queued"
        self.message = "Preparing…"
        self.floor = 0.0
        self.ceil = 0.05
        self.tau = _DEFAULT_TAU_S
        self.stage_started = now
        self.run_started = now
        self.last_touch = now
        self.done = False

    def eased(self, now: float) -> float:
        """Percent (0..1) eased from floor toward ceil by elapsed stage time."""
        if self.done:
            return 1.0
        span = self.ceil - self.floor
        if span <= 0:
            return self.floor
        elapsed = max(0.0, now - self.stage_started)
        frac = 1.0 - math.exp(-elapsed / max(self.tau, 1.0))
        return min(self.ceil, self.floor + span * frac)


_lock = threading.Lock()
_entries: Dict[str, _Entry] = {}


def _evict_locked(now: float) -> None:
    stale = [t for t, e in _entries.items() if now - e.last_touch > _TTL_S]
    for t in stale:
        _entries.pop(t, None)


def start(token: Optional[str]) -> None:
    """Register a token at the very start of a run. No-op when token is falsy."""
    if not token:
        return
    now = time.monotonic()
    with _lock:
        _evict_locked(now)
        _entries[token] = _Entry(now)


def update(token: Optional[str], stage: str, message: str,
           floor: float, ceil: float, tau: float = _DEFAULT_TAU_S) -> None:
    """Mark that the run entered `stage`. `floor` is where the bar is NOW, `ceil`
    is the percent it should ease toward while this stage lasts (typically the
    next stage's floor). Monotonic: floor never moves backward."""
    if not token:
        return
    now = time.monotonic()
    with _lock:
        e = _entries.get(token)
        if e is None:
            e = _Entry(now)
            _entries[token] = e
        e.stage = stage
        e.message = message
        e.floor = max(e.floor, min(1.0, max(0.0, floor)))
        e.ceil = min(1.0, max(e.floor, ceil))
        e.tau = tau
        e.stage_started = now
        e.last_touch = now


def finish(token: Optional[str]) -> None:
    """Pin the token to 100% (its last poll reads complete), then let TTL evict."""
    if not token:
        return
    now = time.monotonic()
    with _lock:
        e = _entries.get(token)
        if e is not None:
            e.done = True
            e.stage = "complete"
            e.last_touch = now


def snapshot(token: str) -> Optional[dict]:
    """The current progress for the Java poller, or None when unknown (→ 404).
    Keys match PythonClientService.pollSubProgress: stage, message, sub_percent,
    elapsed_ms."""
    now = time.monotonic()
    with _lock:
        e = _entries.get(token)
        if e is None:
            return None
        e.last_touch = now
        return {
            "stage": e.stage,
            "message": e.message,
            "sub_percent": round(e.eased(now), 4),
            "elapsed_ms": int((now - e.run_started) * 1000),
        }


def clear() -> None:
    """Drop all tokens (tests)."""
    with _lock:
        _entries.clear()
