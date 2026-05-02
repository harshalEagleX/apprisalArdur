"""
Database connection and session management.

Connection URL is read from the DATABASE_URL env var.
Default points to the docker-compose PostgreSQL container.
"""

import os
import logging
from contextlib import contextmanager
from typing import Generator

from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, Session, DeclarativeBase

logger = logging.getLogger(__name__)

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://qc_user:qc_password@localhost:5432/appraisal_qc"
)

# Sync engine — OCR pipeline runs in threadpool (sync), so sync engine is simpler.
# pool_pre_ping=True: verify connections before use (handles Docker restarts).
engine = create_engine(
    DATABASE_URL,
    pool_size=5,
    max_overflow=10,
    pool_pre_ping=True,
    echo=False,  # set True to log all SQL
)

SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)


class Base(DeclarativeBase):
    """Base class for all ORM models."""
    pass


@contextmanager
def get_db() -> Generator[Session, None, None]:
    """
    Provide a transactional database session.
    Usage:
        with get_db() as db:
            db.query(...)
    """
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def is_db_available() -> bool:
    """Quick connectivity check — used at startup and in health endpoint."""
    try:
        with engine.connect() as conn:
            conn.execute(__import__("sqlalchemy").text("SELECT 1"))
        return True
    except Exception as e:
        logger.info("Database not available: %s", e)
        return False


def create_all_tables():
    """Create all tables if they don't exist (idempotent, used for tests)."""
    from app.models.db_models import Base as DBBase  # noqa: import triggers registration
    DBBase.metadata.create_all(bind=engine)
