"""
LLM Response Cache — Phase 4

Caches ollama/LLM responses by SHA-256 hash of the (task + input_text).
Same commentary → same response instantly, no repeated model inference.

Why: ollama calls take 1–5 seconds. For reprocessed documents, this is free.
"""

import hashlib
import logging
from typing import Optional

logger = logging.getLogger(__name__)

try:
    from app.database import get_db
    from app.models.db_models import LLMResponseCache
    from app.services.cache_service import _db_ok
    LLM_CACHE_AVAILABLE = True
except Exception:
    LLM_CACHE_AVAILABLE = False


def _make_key(task: str, text: str) -> str:
    return hashlib.sha256(f"{task}::{text}".encode()).hexdigest()


def get_cached_llm(task: str, text: str) -> Optional[str]:
    """Return cached LLM response if available, else None."""
    if not LLM_CACHE_AVAILABLE or not _db_ok():
        return None
    try:
        key = _make_key(task, text)
        with get_db() as db:
            row = db.query(LLMResponseCache).filter(LLMResponseCache.input_hash == key).first()
            if row:
                row.hit_count = (row.hit_count or 0) + 1
                logger.debug("LLM cache HIT task=%s key=%s", task, key[:10])
                return row.response
        return None
    except Exception as e:
        logger.info("LLM cache get failed: %s", e)
        return None


def save_llm_response(task: str, text: str, response: str, model_name: str = ""):
    """Persist an LLM response to the cache."""
    if not LLM_CACHE_AVAILABLE or not _db_ok():
        return
    try:
        key = _make_key(task, text)
        with get_db() as db:
            exists = db.query(LLMResponseCache).filter(LLMResponseCache.input_hash == key).first()
            if not exists:
                db.add(LLMResponseCache(
                    input_hash=key,
                    task=task,
                    response=response,
                    model_name=model_name,
                ))
    except Exception as e:
        logger.info("LLM cache save failed: %s", e)
