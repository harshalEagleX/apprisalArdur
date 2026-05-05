"""
In-memory progress store keyed by an opaque token supplied by the caller
(typically the Java QC worker). Stages emit here as the QC pipeline runs;
the caller polls GET /qc/progress/{token} to render real-time updates.

Entries are evicted after PROGRESS_TTL_SECONDS to keep this map bounded
even if a caller forgets to poll the terminal stage.
"""

import threading
import time
from typing import Dict, Optional

PROGRESS_TTL_SECONDS = 600  # 10 minutes


class ProgressStore:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._entries: Dict[str, Dict] = {}

    def set(self, token: str, stage: str, message: str, sub_percent: float) -> None:
        if not token:
            return
        now = time.time()
        clamped = 0.0 if sub_percent is None else max(0.0, min(1.0, float(sub_percent)))
        with self._lock:
            existing = self._entries.get(token)
            started_at = existing["started_at"] if existing else now
            self._entries[token] = {
                "stage": stage,
                "message": message,
                "sub_percent": clamped,
                "started_at": started_at,
                "updated_at": now,
            }
            self._evict_expired_locked(now)

    def get(self, token: str) -> Optional[Dict]:
        if not token:
            return None
        now = time.time()
        with self._lock:
            self._evict_expired_locked(now)
            entry = self._entries.get(token)
            if not entry:
                return None
            return {
                "stage": entry["stage"],
                "message": entry["message"],
                "sub_percent": entry["sub_percent"],
                "started_at": entry["started_at"],
                "updated_at": entry["updated_at"],
                "elapsed_ms": int((now - entry["started_at"]) * 1000),
            }

    def clear(self, token: str) -> None:
        if not token:
            return
        with self._lock:
            self._entries.pop(token, None)

    def _evict_expired_locked(self, now: float) -> None:
        cutoff = now - PROGRESS_TTL_SECONDS
        stale = [k for k, v in self._entries.items() if v["updated_at"] < cutoff]
        for k in stale:
            self._entries.pop(k, None)


progress_store = ProgressStore()
