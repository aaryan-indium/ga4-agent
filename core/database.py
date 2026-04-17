"""SQLite database layer — schema definition, initialisation, and helpers.

Provides the complete schema for the Player Feedback Intelligence System:

  • **reviews** — one row per scraped review with classification fields
    (sentiment, category, summary) that start as NULL and are populated
    by Agent 1.

  • **briefings** — one row per generated daily briefing produced by
    Agent 3, stored as Markdown.

Running this module directly (`python core/database.py`) will create the
database file at the path defined in `core.config.DATABASE_PATH`.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path

from core.config import DATABASE_PATH
from utils.logger import get_logger

logger = get_logger(__name__)

# ── SQL Statements ────────────────────────────────────────────────

_CREATE_REVIEWS_TABLE: str = """
CREATE TABLE IF NOT EXISTS reviews (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    review_id       TEXT    NOT NULL UNIQUE,
    author          TEXT    NOT NULL,
    rating          INTEGER NOT NULL CHECK (rating BETWEEN 1 AND 5),
    review_text     TEXT    NOT NULL,
    date_posted     TEXT,
    date_ingested   TEXT    NOT NULL DEFAULT (datetime('now')),
    source          TEXT    NOT NULL DEFAULT 'google_play',
    is_processed    INTEGER NOT NULL DEFAULT 0 CHECK (is_processed IN (0, 1)),
    sentiment       TEXT,
    category        TEXT,
    summary         TEXT
);
"""

_CREATE_BRIEFINGS_TABLE: str = """
CREATE TABLE IF NOT EXISTS briefings (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at          TEXT    NOT NULL DEFAULT (datetime('now')),
    review_count        INTEGER NOT NULL,
    briefing_markdown   TEXT    NOT NULL
);
"""

_CREATE_REVIEW_ID_INDEX: str = """
CREATE INDEX IF NOT EXISTS idx_reviews_review_id
ON reviews (review_id);
"""

_CREATE_REVIEWS_PROCESSED_INDEX: str = """
CREATE INDEX IF NOT EXISTS idx_reviews_is_processed
ON reviews (is_processed);
"""


# ── Public API ────────────────────────────────────────────────────

def get_connection(db_path: Path | None = None) -> sqlite3.Connection:
    """Return a new SQLite connection with row-factory enabled.

    Parameters
    ----------
    db_path:
        Override for the database file location.  Falls back to
        ``DATABASE_PATH`` from ``core.config``.

    Returns
    -------
    sqlite3.Connection
        A connection with ``row_factory`` set to ``sqlite3.Row`` so that
        query results are accessible by column name.
    """
    path: Path = db_path or DATABASE_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    conn: sqlite3.Connection = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA foreign_keys=ON;")
    return conn


def initialize_db(db_path: Path | None = None) -> None:
    """Create all tables and indexes if they do not already exist.

    Safe to call multiple times — every statement uses
    ``IF NOT EXISTS``.

    Parameters
    ----------
    db_path:
        Override for the database file location.  Falls back to
        ``DATABASE_PATH`` from ``core.config``.
    """
    conn: sqlite3.Connection = get_connection(db_path)
    try:
        cursor: sqlite3.Cursor = conn.cursor()
        cursor.execute(_CREATE_REVIEWS_TABLE)
        cursor.execute(_CREATE_BRIEFINGS_TABLE)
        cursor.execute(_CREATE_REVIEW_ID_INDEX)
        cursor.execute(_CREATE_REVIEWS_PROCESSED_INDEX)
        conn.commit()
        logger.info("Database initialised at %s", db_path or DATABASE_PATH)
    finally:
        conn.close()


def insert_reviews(reviews: list[dict]) -> tuple[int, int]:
    """Bulk-insert reviews using INSERT OR IGNORE; return (inserted, duplicates)."""
    conn: sqlite3.Connection = get_connection()
    try:
        cursor: sqlite3.Cursor = conn.cursor()
        inserted: int = 0
        for review in reviews:
            cursor.execute(
                """
                INSERT OR IGNORE INTO reviews
                    (review_id, author, rating, review_text, date_posted, source, is_processed)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    review["review_id"],
                    review["author"],
                    review["rating"],
                    review["review_text"],
                    review.get("date_posted"),
                    review.get("source", "google_play"),
                    review.get("is_processed", 0),
                ),
            )
            inserted += cursor.rowcount
        conn.commit()
        duplicates: int = len(reviews) - inserted
        return inserted, duplicates
    finally:
        conn.close()


def get_unprocessed_reviews() -> list[dict]:
    """Return all reviews where is_processed = 0."""
    conn: sqlite3.Connection = get_connection()
    try:
        cursor: sqlite3.Cursor = conn.cursor()
        cursor.execute("SELECT * FROM reviews WHERE is_processed = 0")
        return [dict(row) for row in cursor.fetchall()]
    finally:
        conn.close()


def get_reviews_by_ids(review_ids: list[str]) -> list[dict]:
    """Return reviews matching a list of review_id values."""
    if not review_ids:
        return []

    conn: sqlite3.Connection = get_connection()
    try:
        cursor: sqlite3.Cursor = conn.cursor()
        placeholders: str = ",".join("?" for _ in review_ids)
        cursor.execute(
            f"SELECT * FROM reviews WHERE review_id IN ({placeholders})",
            review_ids,
        )
        return [dict(row) for row in cursor.fetchall()]
    finally:
        conn.close()


def get_all_reviews() -> list[dict]:
    """Return all reviews ordered by date_posted descending."""
    conn: sqlite3.Connection = get_connection()
    try:
        cursor: sqlite3.Cursor = conn.cursor()
        cursor.execute("SELECT * FROM reviews ORDER BY date_posted DESC")
        return [dict(row) for row in cursor.fetchall()]
    finally:
        conn.close()


def get_reviews_by_category(category: str) -> list[dict]:
    """Return reviews filtered by category for UI drill-down."""
    conn: sqlite3.Connection = get_connection()
    try:
        cursor: sqlite3.Cursor = conn.cursor()
        cursor.execute("SELECT * FROM reviews WHERE category = ? ORDER BY date_posted DESC", (category,))
        return [dict(row) for row in cursor.fetchall()]
    finally:
        conn.close()


def mark_reviews_processed(review_ids: list[str]) -> None:
    """Set is_processed = 1 for the given review_id values."""
    if not review_ids:
        return
    conn: sqlite3.Connection = get_connection()
    try:
        cursor: sqlite3.Cursor = conn.cursor()
        placeholders: str = ",".join("?" for _ in review_ids)
        cursor.execute(
            f"UPDATE reviews SET is_processed = 1 WHERE review_id IN ({placeholders})",
            review_ids,
        )
        conn.commit()
    finally:
        conn.close()


def update_review_classification(review_id: str, sentiment: str, category: str, summary: str) -> None:
    """Write Agent 1 classification results back to the reviews row in the DB."""
    conn = get_connection()
    conn.execute(
        """UPDATE reviews
           SET sentiment = ?, category = ?, summary = ?, is_processed = 1
           WHERE review_id = ?""",
        (sentiment, category, summary, review_id)
    )
    conn.commit()
    conn.close()


def save_briefing(review_count: int, briefing_markdown: str) -> int:
    """Insert a new briefing and return its row id."""
    conn: sqlite3.Connection = get_connection()
    try:
        cursor: sqlite3.Cursor = conn.cursor()
        now: str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cursor.execute(
            "INSERT INTO briefings (created_at, review_count, briefing_markdown) VALUES (?, ?, ?)",
            (now, review_count, briefing_markdown),
        )
        conn.commit()
        return cursor.lastrowid
    finally:
        conn.close()


def get_all_briefings() -> list[dict]:
    """Return all briefings ordered by created_at descending."""
    conn: sqlite3.Connection = get_connection()
    try:
        cursor: sqlite3.Cursor = conn.cursor()
        cursor.execute(
            "SELECT id, created_at, review_count, briefing_markdown "
            "FROM briefings ORDER BY created_at DESC"
        )
        return [dict(row) for row in cursor.fetchall()]
    finally:
        conn.close()


def get_briefing_by_id(briefing_id: int) -> dict | None:
    """Return a single briefing by id, or None if not found."""
    conn: sqlite3.Connection = get_connection()
    try:
        cursor: sqlite3.Cursor = conn.cursor()
        cursor.execute("SELECT * FROM briefings WHERE id = ?", (briefing_id,))
        row = cursor.fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


# ── CLI Entry Point ──────────────────────────────────────────────

if __name__ == "__main__":
    initialize_db()
