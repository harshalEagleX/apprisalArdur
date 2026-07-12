"""
worker.celery_app — SHALqc.md §9 async path.

Configures Celery from REDIS_URL (broker + result backend). When REDIS_URL is
unset, `celery_available()` is False and the API serves QC on the synchronous
path instead (SHALqc.md §9 keeps /qc/process working regardless) — no Redis on
this device is a supported topology (the .env note), not an error.
"""

from __future__ import annotations

import logging

from app.config import settings

__version__ = "api-1.0.0"

logger = logging.getLogger(__name__)

celery_app = None


def celery_available() -> bool:
    return celery_app is not None


if settings.redis_url:
    try:
        from celery import Celery
        celery_app = Celery("shalqc", broker=settings.redis_url, backend=settings.redis_url)
        celery_app.conf.update(
            task_serializer="json", result_serializer="json", accept_content=["json"],
            task_track_started=True, task_time_limit=600,
        )
        # import tasks so they register on this app
        from app.worker import tasks  # noqa: F401,E402
        logger.info("Celery configured (broker=%s)", settings.redis_url)
    except Exception as exc:
        logger.warning("Celery unavailable (%s) — async path disabled, sync path stands.", exc)
        celery_app = None
else:
    logger.info("REDIS_URL unset — async path disabled; QC runs synchronously.")
