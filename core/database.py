"""SQLite database layer — schema definition, initialisation, and helpers.
"""

from __future__ import annotations

import sqlite3                        # Python's built-in library to talk to SQLite databases
from datetime import datetime         # Used to stamp the exact time a briefing was saved
from pathlib import Path              # Treats file paths as objects instead of raw strings

from core.config import DATABASE_PATH # The file path to our .db file, read from .env once
from utils.logger import get_logger   # Our custom logger so we can write messages to the log file

logger = get_logger(__name__)         # Creates a logger tagged with this file's name (core.database)

# ── SQL Statements ────────────────────────────────────────────────
# These are just SQL strings stored in variables — nothing runs yet.
# They're defined up top so the actual functions below stay clean and readable.

_CREATE_REVIEWS_TABLE: str = """
CREATE TABLE IF NOT EXISTS reviews (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,  -- auto-incrementing row number, DB handles it
    review_id       TEXT    NOT NULL UNIQUE,            -- the ID that came from Google Play, must be unique
    author          TEXT    NOT NULL,                   -- reviewer's name
    rating          INTEGER NOT NULL CHECK (rating BETWEEN 1 AND 5),  -- only 1–5 stars allowed
    review_text     TEXT    NOT NULL,                   -- the actual review body
    date_posted     TEXT,                               -- when the user posted it on the store (optional)
    date_ingested   TEXT    NOT NULL DEFAULT (datetime('now')),  -- when WE pulled it in, auto-filled by DB
    source          TEXT    NOT NULL DEFAULT 'google_play',     -- where it came from, defaults to Play Store
    is_processed    INTEGER NOT NULL DEFAULT 0 CHECK (is_processed IN (0, 1)),  -- 0 = not yet analysed, 1 = done
    sentiment       TEXT,   -- filled in by Agent 1: e.g. "positive", "negative"
    category        TEXT,   -- filled in by Agent 1: e.g. "bug", "feature request"
    summary         TEXT    -- filled in by Agent 1: short one-liner describing the review
);
"""

_CREATE_BRIEFINGS_TABLE: str = """
CREATE TABLE IF NOT EXISTS briefings (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,       -- row number, auto-handled
    created_at          TEXT    NOT NULL DEFAULT (datetime('now')), -- timestamp of when this report was made
    review_count        INTEGER NOT NULL,                        -- how many reviews went into this briefing
    briefing_markdown   TEXT    NOT NULL                         -- the full report text in markdown format
);
"""

# Indexes make lookups faster — like an index in a book.
# Without these, every search would scan every row one by one.

_CREATE_REVIEW_ID_INDEX: str = """
CREATE INDEX IF NOT EXISTS idx_reviews_review_id
ON reviews (review_id);
"""
# Speeds up "find review by its Google Play ID" queries

_CREATE_REVIEWS_PROCESSED_INDEX: str = """
CREATE INDEX IF NOT EXISTS idx_reviews_is_processed
ON reviews (is_processed);
"""
# Speeds up "give me all unprocessed reviews" queries

# ── Public API ────────────────────────────────────────────────────

def get_connection(db_path: Path | None = None) -> sqlite3.Connection:
    """Return a new SQLite connection with row-factory enabled."""
    path: Path = db_path or DATABASE_PATH          # use the override if given, else fall back to config
    path.parent.mkdir(parents=True, exist_ok=True) # create the data/ folder if it doesn't exist yet
    conn: sqlite3.Connection = sqlite3.connect(str(path))  # open (or create) the .db file
    conn.row_factory = sqlite3.Row   # makes query results accessible as dict-like objects, e.g. row["author"]
    conn.execute("PRAGMA journal_mode=WAL;")    # WAL mode: allows reads while a write is happening (safer)
    conn.execute("PRAGMA foreign_keys=ON;")     # enforces foreign key rules (not used yet but good practice)
    return conn


def initialize_db(db_path: Path | None = None) -> None:
    """Create all tables and indexes if they do not already exist."""
    conn: sqlite3.Connection = get_connection(db_path)  # open the DB
    try:
        cursor: sqlite3.Cursor = conn.cursor()           # cursor is the object we use to send SQL commands
        cursor.execute(_CREATE_REVIEWS_TABLE)            # create reviews table if missing
        cursor.execute(_CREATE_BRIEFINGS_TABLE)          # create briefings table if missing
        cursor.execute(_CREATE_REVIEW_ID_INDEX)          # create review_id index if missing
        cursor.execute(_CREATE_REVIEWS_PROCESSED_INDEX)  # create is_processed index if missing
        conn.commit()                                    # save all the above changes to disk
        logger.info("Database initialised at %s", db_path or DATABASE_PATH)  # log success
    finally:
        conn.close()   # always close the connection, even if something crashed above


def insert_reviews(reviews: list[dict]) -> tuple[int, int]:
    """Bulk-insert reviews using INSERT OR IGNORE; return (inserted, duplicates)."""
    conn: sqlite3.Connection = get_connection()
    try:
        cursor: sqlite3.Cursor = conn.cursor()
        inserted: int = 0
        for review in reviews:
            cursor.execute(
                """
                INSERT OR IGNORE INTO reviews           -- skip silently if review_id already exists
                    (review_id, author, rating, review_text, date_posted, source, is_processed)
                VALUES (?, ?, ?, ?, ?, ?, ?)            -- ? placeholders prevent SQL injection
                """,
                (
                    review["review_id"],
                    review["author"],
                    review["rating"],
                    review["review_text"],
                    review.get("date_posted"),          # .get() returns None if key is missing
                    review.get("source", "google_play"),
                    review.get("is_processed", 0),
                ),
            )
            inserted += cursor.rowcount  # rowcount is 1 if inserted, 0 if it was a duplicate and ignored
        conn.commit()
        duplicates: int = len(reviews) - inserted  # anything not inserted was a duplicate
        return inserted, duplicates
    finally:
        conn.close()


def get_unprocessed_reviews() -> list[dict]:
    """Return all reviews where is_processed = 0."""
    conn: sqlite3.Connection = get_connection()
    try:
        cursor: sqlite3.Cursor = conn.cursor()
        cursor.execute("SELECT * FROM reviews WHERE is_processed = 0")  # fetch reviews Agent 1 hasn't seen yet
        return [dict(row) for row in cursor.fetchall()]  # convert each sqlite3.Row into a plain Python dict
    finally:
        conn.close()


def get_reviews_by_ids(review_ids: list[str]) -> list[dict]:
    """Return reviews matching a list of review_id values."""
    if not review_ids:
        return []   # short-circuit: no point hitting the DB with an empty list

    conn: sqlite3.Connection = get_connection()
    try:
        cursor: sqlite3.Cursor = conn.cursor()
        placeholders: str = ",".join("?" for _ in review_ids)  # builds "?,?,?" — one ? per ID
        cursor.execute(
            f"SELECT * FROM reviews WHERE review_id IN ({placeholders})",
            review_ids,   # sqlite3 maps each ? to the corresponding ID safely
        )
        return [dict(row) for row in cursor.fetchall()]
    finally:
        conn.close()


def get_all_reviews() -> list[dict]:
    """Return all reviews ordered by date_posted descending."""
    conn: sqlite3.Connection = get_connection()
    try:
        cursor: sqlite3.Cursor = conn.cursor()
        cursor.execute("SELECT * FROM reviews ORDER BY date_posted DESC")  # newest reviews first
        return [dict(row) for row in cursor.fetchall()]
    finally:
        conn.close()


def get_existing_review_ids(review_ids: list[str]) -> set[str]:
    """Return the subset of review_ids that already exist in the reviews table."""
    if not review_ids:
        return set()  # empty input → empty output, no DB call needed

    conn: sqlite3.Connection = get_connection()
    try:
        cursor: sqlite3.Cursor = conn.cursor()
        placeholders: str = ",".join("?" for _ in review_ids)
        cursor.execute(
            f"SELECT review_id FROM reviews WHERE review_id IN ({placeholders})",
            review_ids,
        )
        return {str(row["review_id"]) for row in cursor.fetchall()}  # return as a set for O(1) lookups
    finally:
        conn.close()


def get_reviews_by_category(category: str) -> list[dict]:
    """Return reviews filtered by category for UI drill-down."""
    conn: sqlite3.Connection = get_connection()
    try:
        cursor: sqlite3.Cursor = conn.cursor()
        cursor.execute(
            "SELECT * FROM reviews WHERE category = ? ORDER BY date_posted DESC",  # filter by Agent 1's label
            (category,)  # tuple with one item — the trailing comma is required by Python
        )
        return [dict(row) for row in cursor.fetchall()]
    finally:
        conn.close()


def mark_reviews_processed(review_ids: list[str]) -> None:
    """Set is_processed = 1 for the given review_id values."""
    if not review_ids:
        return   # nothing to do
    conn: sqlite3.Connection = get_connection()
    try:
        cursor: sqlite3.Cursor = conn.cursor()
        placeholders: str = ",".join("?" for _ in review_ids)
        cursor.execute(
            f"UPDATE reviews SET is_processed = 1 WHERE review_id IN ({placeholders})",  # bulk-flag as done
            review_ids,
        )
        conn.commit()   # persist the update
    finally:
        conn.close()


def update_review_classification(review_id: str, sentiment: str, category: str, summary: str) -> None:
    """Write Agent 1 classification results back to the reviews row in the DB."""
    conn = get_connection()
    conn.execute(
        """UPDATE reviews
           SET sentiment = ?, category = ?, summary = ?, is_processed = 1  -- write all 3 fields + mark done
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
        now: str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")  # e.g. "2025-04-20 14:32:01"
        cursor.execute(
            "INSERT INTO briefings (created_at, review_count, briefing_markdown) VALUES (?, ?, ?)",
            (now, review_count, briefing_markdown),
        )
        conn.commit()
        return cursor.lastrowid   # the auto-assigned id of the row we just inserted
    finally:
        conn.close()


def get_all_briefings() -> list[dict]:
    """Return all briefings ordered by created_at descending."""
    conn: sqlite3.Connection = get_connection()
    try:
        cursor: sqlite3.Cursor = conn.cursor()
        cursor.execute(
            "SELECT id, created_at, review_count, briefing_markdown "
            "FROM briefings ORDER BY created_at DESC"  # most recent report first
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
        row = cursor.fetchone()         # fetchone returns a single row or None
        return dict(row) if row else None   # convert to dict if found, otherwise return None explicitly
    finally:
        conn.close()

if __name__ == "__main__":
    initialize_db()   # if you run this file directly, it bootstraps the database