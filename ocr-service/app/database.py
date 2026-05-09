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
from sqlalchemy.schema import CreateColumn, CreateIndex
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
    Reconcile the Python service schema from the SQLAlchemy models.

    This service uses its ORM models as the runtime contract for local/product
    deployments where a separate migration step may not run before startup.
    The reconciliation is additive only: it creates missing tables and adds
    missing columns, but never drops, renames, or rewrites existing data.
    """
    try:
        from app.models.db_models import Base as DBBase

        DBBase.metadata.create_all(bind=engine, checkfirst=True)

        statements = _missing_column_statements(DBBase)
        if not statements:
            _create_missing_indexes(DBBase)
            return

        with engine.begin() as conn:
            for statement in statements:
                conn.execute(text(statement))
        _create_missing_indexes(DBBase)
        logger.info("Applied OCR ORM schema reconciliation: %s", ", ".join(statements))
    except Exception as exc:
        logger.info("OCR schema compatibility check skipped: %s", exc)


def _missing_column_statements(DBBase) -> list[str]:
    """Build additive ALTER statements from declared SQLAlchemy table columns."""
    inspector = inspect(engine)
    table_names = set(inspector.get_table_names())
    preparer = engine.dialect.identifier_preparer
    statements: list[str] = []

    for table in DBBase.metadata.sorted_tables:
        if table.name not in table_names:
            continue
        existing_columns = {column["name"] for column in inspector.get_columns(table.name)}
        for column in table.columns:
            if column.name in existing_columns:
                continue
            if column.primary_key:
                logger.warning("Skipping missing primary key column %s.%s", table.name, column.name)
                continue
            column_ddl = str(CreateColumn(column).compile(dialect=engine.dialect))
            statements.append(
                f"ALTER TABLE {preparer.format_table(table)} ADD COLUMN {column_ddl}"
            )

    return statements


def _create_missing_indexes(DBBase) -> None:
    """Create ORM-declared indexes that are missing on existing tables."""
    inspector = inspect(engine)
    table_names = set(inspector.get_table_names())

    for table in DBBase.metadata.sorted_tables:
        if table.name not in table_names:
            continue
        existing_indexes = {index["name"] for index in inspector.get_indexes(table.name)}
        for index in table.indexes:
            if index.name in existing_indexes:
                continue
            try:
                with engine.begin() as conn:
                    conn.execute(CreateIndex(index))
                logger.info("Created missing OCR index %s", index.name)
            except Exception as exc:
                logger.debug("Could not create OCR index %s: %s", index.name, exc)
