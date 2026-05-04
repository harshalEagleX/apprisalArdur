"""
Database connection and session management.

Connection URL is read from the DATABASE_URL env var.
Default points to the docker-compose PostgreSQL container.
"""

import os
import logging
from contextlib import contextmanager
from typing import Generator

from sqlalchemy import create_engine, event, inspect, text
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


@event.listens_for(engine, "connect")
def _set_session_timezone(dbapi_connection, connection_record):
    try:
        cursor = dbapi_connection.cursor()
        cursor.execute("SET TIME ZONE 'Asia/Kolkata'")
        cursor.close()
    except Exception as exc:
        logger.debug("Could not set DB session timezone: %s", exc)

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


def ensure_schema_compatibility():
    """
    Apply tiny, idempotent compatibility fixes for dev databases that were
    created before newer cache columns existed. Alembic remains the source of
    truth; this prevents stale local DBs from disabling OCR cache at runtime.
    """
    try:
        inspector = inspect(engine)
        table_names = set(inspector.get_table_names())
        if "page_ocr_results" not in table_names:
            return

        columns = {column["name"] for column in inspector.get_columns("page_ocr_results")}
        statements = []
        if "hocr_text" not in columns:
            statements.append("ALTER TABLE page_ocr_results ADD COLUMN hocr_text TEXT")
        if "word_json" not in columns:
            statements.append("ALTER TABLE page_ocr_results ADD COLUMN word_json TEXT")

        if "extracted_fields" in table_names:
            field_columns = {column["name"] for column in inspector.get_columns("extracted_fields")}
            for column_name in ("bbox_x", "bbox_y", "bbox_w", "bbox_h"):
                if column_name not in field_columns:
                    statements.append(f"ALTER TABLE extracted_fields ADD COLUMN {column_name} DOUBLE PRECISION")

        if not statements:
            return

        with engine.begin() as conn:
            for statement in statements:
                conn.execute(text(statement))
        logger.info("Applied OCR cache schema compatibility fixes: %s", ", ".join(statements))
    except Exception as exc:
        logger.info("OCR schema compatibility check skipped: %s", exc)
