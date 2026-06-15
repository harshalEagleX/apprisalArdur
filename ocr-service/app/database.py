"""
Day 3 — Database Connection

Single SQLAlchemy engine and session factory for all Python-owned tables.
Tables are created/dropped via `python manage_db.py` — never via Alembic.
"""

import os
from contextlib import contextmanager
from typing import Generator

from sqlalchemy import create_engine, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import DATABASE_URL


# Pool is sized PER PROCESS. With N Celery workers the totals multiply, so keep each
# worker small to stay within Postgres max_connections (Scaling Phase 2 §4.1
# connection arithmetic: Java 30 + 7 workers × 5 ≈ 70 < 200). Configurable (P-4).
engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,          # detect stale connections
    pool_size=int(os.getenv("DB_POOL_SIZE", "2")),
    max_overflow=int(os.getenv("DB_MAX_OVERFLOW", "3")),
    echo=False,
)

SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)


class Base(DeclarativeBase):
    pass


@contextmanager
def get_db() -> Generator[Session, None, None]:
    """Context manager for database sessions."""
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def verify_connection() -> bool:
    """Return True if the database is reachable."""
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False
