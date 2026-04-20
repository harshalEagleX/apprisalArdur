import os
import sqlite3
from datetime import datetime
from typing import Any, Dict, Optional


def _is_postgres_url(url: str) -> bool:
    return url.startswith("postgresql://") or url.startswith("postgres://")


class FeedbackStore:
    def __init__(self) -> None:
        self.database_url = os.getenv("DATABASE_URL", "").strip()
        self.db_path = os.getenv("FEEDBACK_DB_PATH", "logs/feedback.sqlite3")
        self._pg_conn = None
        self._pg_driver = None

        if _is_postgres_url(self.database_url):
            self._init_postgres()
        else:
            os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
            self._ensure_sqlite_schema()

    def _init_postgres(self) -> None:
        try:
            import psycopg2  # type: ignore
        except ImportError as exc:
            raise RuntimeError(
                "DATABASE_URL is set to PostgreSQL but psycopg2 is not installed"
            ) from exc
        self._pg_driver = psycopg2
        self._pg_conn = self._pg_driver.connect(self.database_url)
        self._pg_conn.autocommit = True
        self._ensure_postgres_schema()

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.db_path)

    def _ensure_sqlite_schema(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS field_corrections (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    document_id TEXT NOT NULL,
                    field_name TEXT NOT NULL,
                    section TEXT,
                    predicted_value TEXT,
                    corrected_value TEXT,
                    confidence_score REAL,
                    was_correct INTEGER NOT NULL,
                    operator_id TEXT,
                    created_at TEXT NOT NULL
                )
                """
            )
            conn.commit()

    def _ensure_postgres_schema(self) -> None:
        assert self._pg_conn is not None
        with self._pg_conn.cursor() as cur:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS field_corrections (
                    id SERIAL PRIMARY KEY,
                    document_id VARCHAR(255) NOT NULL,
                    field_name VARCHAR(100) NOT NULL,
                    section VARCHAR(50),
                    predicted_value TEXT,
                    corrected_value TEXT,
                    confidence_score FLOAT,
                    was_correct BOOLEAN NOT NULL,
                    operator_id VARCHAR(100),
                    created_at TIMESTAMP NOT NULL DEFAULT NOW()
                )
                """
            )

    def save_correction(self, payload: Dict[str, Any]) -> int:
        if self._pg_conn is not None:
            return self._save_postgres(payload)
        return self._save_sqlite(payload)

    def _save_sqlite(self, payload: Dict[str, Any]) -> int:
        with self._connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO field_corrections (
                    document_id, field_name, section, predicted_value, corrected_value,
                    confidence_score, was_correct, operator_id, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    payload["document_id"],
                    payload["field_name"],
                    payload.get("section"),
                    payload.get("predicted_value"),
                    payload.get("corrected_value"),
                    payload.get("confidence_score"),
                    1 if payload.get("was_correct") else 0,
                    payload.get("operator_id"),
                    datetime.utcnow().isoformat(),
                ),
            )
            conn.commit()
            return int(cursor.lastrowid)

    def _save_postgres(self, payload: Dict[str, Any]) -> int:
        assert self._pg_conn is not None
        with self._pg_conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO field_corrections (
                    document_id, field_name, section, predicted_value, corrected_value,
                    confidence_score, was_correct, operator_id, created_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id
                """,
                (
                    payload["document_id"],
                    payload["field_name"],
                    payload.get("section"),
                    payload.get("predicted_value"),
                    payload.get("corrected_value"),
                    payload.get("confidence_score"),
                    bool(payload.get("was_correct")),
                    payload.get("operator_id"),
                    datetime.utcnow(),
                ),
            )
            row = cur.fetchone()
            return int(row[0]) if row else 0

    def fetch_recent_incorrect(self, limit: int = 50) -> list[Dict[str, Optional[str]]]:
        if self._pg_conn is not None:
            return self._fetch_recent_incorrect_postgres(limit)
        return self._fetch_recent_incorrect_sqlite(limit)

    def _fetch_recent_incorrect_sqlite(self, limit: int) -> list[Dict[str, Optional[str]]]:
        with self._connect() as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """
                SELECT field_name, predicted_value, corrected_value, created_at
                FROM field_corrections
                WHERE was_correct = 0
                ORDER BY datetime(created_at) DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
            return [dict(r) for r in rows]

    def _fetch_recent_incorrect_postgres(self, limit: int) -> list[Dict[str, Optional[str]]]:
        assert self._pg_conn is not None
        with self._pg_conn.cursor() as cur:
            cur.execute(
                """
                SELECT field_name, predicted_value, corrected_value, created_at
                FROM field_corrections
                WHERE was_correct = FALSE
                ORDER BY created_at DESC
                LIMIT %s
                """,
                (limit,),
            )
            rows = cur.fetchall()
            return [
                {
                    "field_name": r[0],
                    "predicted_value": r[1],
                    "corrected_value": r[2],
                    "created_at": str(r[3]),
                }
                for r in rows
            ]


feedback_store = FeedbackStore()
