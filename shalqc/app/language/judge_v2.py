"""
language.judge_v2 (judge_v2) — one prompt for every check of every AMC (§4).

Zero per-rule code: the judge receives a batch of slim packets (one section) and
returns one verdict per item_id. Batches are fired CONCURRENTLY (§8) so LLM wall
time ≈ the slowest batch, not the sum. The two API keys give two lanes; a batch
that fails/twice-bad-JSON is reported as failed so run.py can apply the S-6
fallback (REVIEW llm_unavailable, packet attached) — the judge itself never
guesses.
"""

from __future__ import annotations

import json
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

__version__ = "judge_v2"
PROMPT_VERSION = "judge_v2"
_MAX_LANES = 3
# §8: "Batch = section, ~8–12 items/batch". A big section is sub-chunked so the
# reply never exceeds the token budget and truncates into unparseable JSON.
_CHUNK = 8

_PROMPTS_DIR = Path(__file__).parent.parent.parent / "prompts"


def _system() -> str:
    p = _PROMPTS_DIR / f"{PROMPT_VERSION}.txt"
    return p.read_text(encoding="utf-8") if p.exists() else ""


def _batch_meta(section: str, res) -> Dict[str, object]:
    """The audit metadata for one batched judge call — stamped onto every item's
    stored interaction so a reviewer can see exactly which model/lane judged it."""
    call = getattr(res, "call", None)
    return {
        "call_type": f"judge2:{PROMPT_VERSION}:{section}",
        "prompt_version": PROMPT_VERSION,
        "batch_id": section,
        "provider": getattr(call, "provider", "") if call else "",
        "model": getattr(call, "model", "") if call else "",
        "ms": getattr(call, "ms", 0.0) if call else 0.0,
        "cached": getattr(call, "cached", False) if call else False,
        "raw_response": getattr(res, "raw", None),
    }


def _judge_batch(client, section: str, packets: List
                 ) -> Tuple[str, Optional[Dict[str, dict]], Dict[str, object]]:
    """One batched call over one section's packets. Returns (section, verdicts-by-
    item_id | None, batch_meta). batch_meta always describes the call made."""
    payload = {"packets": [p.to_json() for p in packets]}
    res = client.complete(f"judge2:{PROMPT_VERSION}:{section}", _system(),
                          json.dumps(payload), max_tokens=3500)
    meta = _batch_meta(section, res)
    if not res.ok or not isinstance(res.data, dict):
        return section, None, meta
    verdicts = _normalize_reply(res.data)
    if verdicts is None:
        return section, None, meta
    out: Dict[str, dict] = {}
    for v in verdicts:
        if isinstance(v, dict) and v.get("item_id"):
            out[str(v["item_id"])] = v
    return section, out, meta


def _normalize_reply(data: dict):
    """Accept {verdicts:[...]}, {final:{verdicts:[...]}}, or a bare list wrapped in
    a key (the last-run wrapper bug, §4.4). Returns the verdict list or None."""
    if isinstance(data.get("verdicts"), list):
        return data["verdicts"]
    final = data.get("final")
    if isinstance(final, dict) and isinstance(final.get("verdicts"), list):
        return final["verdicts"]
    # single verdict object returned bare
    if data.get("item_id") and data.get("status"):
        return [data]
    return None


def judge_all(client, packets_by_section: Dict[str, List]
              ) -> Tuple[Dict[str, dict], List[str], Dict[str, dict]]:
    """Judge every section concurrently. Returns (verdicts keyed by item_id,
    item_ids whose batch failed → caller applies the S-6 fallback, and metas keyed
    by item_id → the batch call's audit metadata for the stored interaction)."""
    if client is None or not getattr(client, "available", False):
        failed = [p.item_id for ps in packets_by_section.values() for p in ps]
        return {}, failed, {}

    verdicts: Dict[str, dict] = {}
    metas: Dict[str, dict] = {}
    # sub-chunk each section into ~_CHUNK-item batches (§8) so no reply truncates.
    batches: List[tuple] = []
    for sec, ps in packets_by_section.items():
        if not ps:
            continue
        for i in range(0, len(ps), _CHUNK):
            batches.append((f"{sec}#{i // _CHUNK}", ps[i:i + _CHUNK]))

    def _absorb(sec, ps, got, meta, failed_chunks):
        for p in ps:                                       # every item gets the call meta
            metas[p.item_id] = meta
        if got is None:                                    # whole-batch failure
            failed_chunks.append((sec, ps))
            return
        for p in ps:
            jr = got.get(p.item_id)
            (verdicts.__setitem__(p.item_id, jr) if jr is not None
             else failed_chunks.append((sec, [p])))        # per-item omission → retry that item

    failed_chunks: List[tuple] = []
    with ThreadPoolExecutor(max_workers=min(_MAX_LANES, max(1, len(batches)))) as pool:
        futures = {pool.submit(_judge_batch, client, sec, ps): (sec, ps) for sec, ps in batches}
        for fut in as_completed(futures):
            sec, ps = futures[fut]
            try:
                _sec, got, meta = fut.result()
            except Exception as exc:                       # never let one batch sink the run
                logger.warning("judge_v2 batch %s crashed: %s", sec, exc)
                got, meta = None, {"batch_id": sec, "error": str(exc)}
            _absorb(sec, ps, got, meta, failed_chunks)

    # §8 / §7 S-6: retry failed chunks SEQUENTIALLY once — a rate-limit 429 under
    # concurrency clears when the batches are spaced out. Anything still failing
    # after this becomes an honest llm_unavailable REVIEW (never a blind PASS).
    still_failed: List[str] = []
    for sec, ps in failed_chunks:
        try:
            _sec, got, meta = _judge_batch(client, sec, ps)
        except Exception as exc:
            got, meta = None, {"batch_id": sec, "error": str(exc)}
        for p in ps:
            metas[p.item_id] = meta
        if got is None:
            still_failed += [p.item_id for p in ps]
        else:
            for p in ps:
                jr = got.get(p.item_id)
                if jr is not None:
                    verdicts[p.item_id] = jr
                else:
                    still_failed.append(p.item_id)
    return verdicts, still_failed, metas
