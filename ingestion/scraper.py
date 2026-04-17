"""Review ingestion — scrape from Google Play or load from JSON.

Two ingestion capabilities in one module:
  A) scrape_from_play_store()  — live scraping via google-play-scraper
  B) load_from_json_file()     — import from a local JSON file
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from uuid import uuid4

from core.config import SCRAPE_APP_ID, SCRAPE_REVIEW_COUNT
from utils.logger import get_logger

logger = get_logger("scraper")


# ══════════════════════════════════════════════════════════════════
# Capability A — Google Play Store scraping
# ══════════════════════════════════════════════════════════════════

def scrape_from_play_store() -> list[dict]:
    """Scrape reviews from Google Play, balanced across all 5 star ratings."""
    from google_play_scraper import Sort, reviews as gp_reviews

    collected: list[dict] = []
    per_rating: int = SCRAPE_REVIEW_COUNT // 5

    for star in range(1, 6):
        try:
            logger.info("Fetching %d reviews for %d-star from %s", per_rating, star, SCRAPE_APP_ID)
            result, _ = gp_reviews(
                SCRAPE_APP_ID,
                lang="en",
                country="us",
                sort=Sort.NEWEST,
                count=per_rating,
                filter_score_with=star,
            )
            for raw in result:
                collected.append(_map_play_review(raw))
            logger.info("Got %d reviews for %d-star", len(result), star)
        except Exception as exc:
            logger.error("Error fetching %d-star reviews: %s", star, exc)

    logger.info("Total scraped: %d reviews", len(collected))
    return collected


def _map_play_review(raw: dict) -> dict:
    """Map a google-play-scraper result dict to our DB schema."""
    date_posted: str | None = None
    if raw.get("at"):
        date_posted = raw["at"].isoformat() if isinstance(raw["at"], datetime) else str(raw["at"])

    return {
        "review_id": raw.get("reviewId", str(uuid4())),
        "author": raw.get("userName", "Unknown"),
        "rating": raw.get("score", 3),
        "review_text": raw.get("content", ""),
        "date_posted": date_posted,
        "source": "google_play",
        "is_processed": 0,
    }


# ══════════════════════════════════════════════════════════════════
# Capability B — JSON file import
# ══════════════════════════════════════════════════════════════════

def load_from_json_file(file_path: str) -> list[dict]:
    """Read reviews from a JSON file, validating required fields."""
    path: Path = Path(file_path)
    if not path.exists():
        logger.error("JSON file not found: %s", path)
        return []

    with open(path, "r", encoding="utf-8") as fh:
        try:
            raw_list: list = json.load(fh)
        except json.JSONDecodeError as exc:
            logger.error("Invalid JSON in %s: %s", path, exc)
            return []

    if not isinstance(raw_list, list):
        logger.error("Expected a JSON array in %s, got %s", path, type(raw_list).__name__)
        return []

    mapped: list[dict] = []
    for idx, entry in enumerate(raw_list):
        if not isinstance(entry, dict):
            logger.warning("Skipping non-object entry at index %d", idx)
            continue
        if "review_text" not in entry or "rating" not in entry:
            logger.warning("Skipping entry at index %d — missing review_text or rating", idx)
            continue

        try:
            rating: int = int(entry["rating"])
        except (TypeError, ValueError):
            logger.warning("Skipping entry at index %d — invalid rating value: %r", idx, entry.get("rating"))
            continue

        if rating < 1 or rating > 5:
            logger.warning("Skipping entry at index %d — rating out of range (1-5): %d", idx, rating)
            continue

        mapped.append({
            "review_id": entry.get("review_id", str(uuid4())),
            "author": entry.get("author", "Anonymous"),
            "rating": rating,
            "review_text": entry["review_text"],
            "date_posted": entry.get("date_posted", datetime.now().isoformat()),
            "source": "json_upload",
            "is_processed": 0,
        })

    logger.info("Loaded %d valid reviews from %s (%d skipped)", len(mapped), path, len(raw_list) - len(mapped))
    return mapped


