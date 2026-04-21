from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from uuid import uuid4

from core.database import get_existing_review_ids
from core.config import SCRAPE_APP_ID, SCRAPE_REVIEW_COUNT
from utils.logger import get_logger

logger = get_logger("scraper")

# Capability A — Google Play Store scraping

def scrape_from_play_store() -> list[dict]:
    from google_play_scraper import Sort, reviews as gp_reviews

    collected: list[dict] = []
    # Give each star bucket an equal base share of the total target.
    base_per_rating: int = SCRAPE_REVIEW_COUNT // 5
    # Keep the leftover count when the total is not divisible by 5.
    remainder: int = SCRAPE_REVIEW_COUNT % 5
    # Spread leftovers by giving +1 to the first few star buckets.
    per_rating_targets: dict[int, int] = {
        star: base_per_rating + (1 if star <= remainder else 0)
        for star in range(1, 6)
    }
    # Stop after this many pages per star to keep runtime bounded.
    max_pages_per_star: int = 12

    for star in range(1, 6):
        target_for_star: int = per_rating_targets[star]
        if target_for_star <= 0:
            continue

        # Token used by the API to fetch the next page.
        continuation_token = None
        star_unique: list[dict] = []
        # Track IDs already accepted in this star bucket.
        seen_this_star: set[str] = set()

        try:
            logger.info(
                "Fetching up to %d new reviews for %d-star from %s",
                target_for_star,
                star,
                SCRAPE_APP_ID,
            )

            # Keep paging until target met, pages run out, or API has no next page.
            for page_num in range(1, max_pages_per_star + 1):
                # Remaining unique reviews needed for this star bucket.
                needed: int = target_for_star - len(star_unique)
                if needed <= 0:
                    break

                # Ask for enough items to make progress, but stay within safe limits.
                request_count: int = min(100, max(20, needed))
                result, continuation_token = gp_reviews(
                    SCRAPE_APP_ID,
                    lang="en",
                    country="us",
                    sort=Sort.NEWEST,
                    count=request_count,
                    filter_score_with=star,
                    continuation_token=continuation_token,
                )

                if not result:
                    break

                mapped_page: list[dict] = [_map_play_review(raw) for raw in result]
                # Check only IDs we have not already accepted in this bucket.
                candidate_ids: list[str] = [
                    review["review_id"]
                    for review in mapped_page
                    if review["review_id"] not in seen_this_star
                ]
                # Ask DB which of these IDs already exist from previous runs.
                existing_ids: set[str] = get_existing_review_ids(candidate_ids)

                added_in_page: int = 0
                for review in mapped_page:
                    review_id: str = review["review_id"]
                    # Skip if seen in this run or already stored in DB.
                    if review_id in seen_this_star or review_id in existing_ids:
                        continue
                    seen_this_star.add(review_id)
                    star_unique.append(review)
                    added_in_page += 1
                    if len(star_unique) >= target_for_star:
                        break

                logger.info(
                    "Star %d page %d: fetched=%d, added_new=%d, progress=%d/%d",
                    star,
                    page_num,
                    len(result),
                    added_in_page,
                    len(star_unique),
                    target_for_star,
                )

                # No token means the API has no more pages for this query.
                if continuation_token is None:
                    break

            collected.extend(star_unique)
            logger.info(
                "Collected %d new unique reviews for %d-star (target=%d)",
                len(star_unique),
                star,
                target_for_star,
            )
        except Exception as exc:
            logger.error("Error fetching %d-star reviews: %s", star, exc)

    logger.info("Total new unique scraped: %d reviews (target=%d)", len(collected), SCRAPE_REVIEW_COUNT)
    return collected


def _map_play_review(raw: dict) -> dict:
    """Map a google-play-scraper result dict to our DB schema."""
    date_posted: str | None = None
    # Keep timestamps in ISO format when the source gives a datetime object.
    if raw.get("at"):
        date_posted = raw["at"].isoformat() if isinstance(raw["at"], datetime) else str(raw["at"])

    return {
        # Use a UUID when the source reviewId is missing.
        "review_id": raw.get("reviewId", str(uuid4())),
        "author": raw.get("userName", "Unknown"),
        "rating": raw.get("score", 3),
        "review_text": raw.get("content", ""),
        "date_posted": date_posted,
        # Label this row as coming from Google Play.
        "source": "google_play",
        # New rows start unprocessed for later classification.
        "is_processed": 0,
    }

# Capability B — JSON file import

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

        # Convert rating to int for consistent validation and storage.
        try:
            rating: int = int(entry["rating"])
        except (TypeError, ValueError):
            logger.warning("Skipping entry at index %d — invalid rating value: %r", idx, entry.get("rating"))
            continue

        # Accept only the valid 1-5 rating range.
        if rating < 1 or rating > 5:
            logger.warning("Skipping entry at index %d — rating out of range (1-5): %d", idx, rating)
            continue

        mapped.append({
            # Use a UUID when uploaded review_id is missing.
            "review_id": entry.get("review_id", str(uuid4())),
            "author": entry.get("author", "Anonymous"),
            "rating": rating,
            "review_text": entry["review_text"],
            "date_posted": entry.get("date_posted", datetime.now().isoformat()),
            # Label this row as coming from JSON upload.
            "source": "json_upload",
            # Uploaded rows also start unprocessed.
            "is_processed": 0,
        })

    # Log how many rows were accepted and how many were skipped.
    logger.info("Loaded %d valid reviews from %s (%d skipped)", len(mapped), path, len(raw_list) - len(mapped))
    return mapped


