"""Pipeline orchestrator that wires all three feedback analysis agents."""

from __future__ import annotations

from agents.briefing_agent import BriefingAgent
from agents.pattern_agent import PatternAgent
from agents.sentiment_agent import SentimentAgent
from core.database import get_all_briefings
from core.database import get_all_reviews
from core.database import get_reviews_by_ids
from core.database import get_unprocessed_reviews
from core.database import save_briefing
from utils.logger import get_logger


class Pipeline:
  """Coordinate classification, pattern detection, and daily briefing generation."""

  def __init__(self) -> None:
    """Initialize pipeline agents and logger."""
    self.sentiment_agent: SentimentAgent = SentimentAgent()
    self.pattern_agent: PatternAgent = PatternAgent()
    self.briefing_agent: BriefingAgent = BriefingAgent()
    self.logger = get_logger(__name__)

  def run_full_pipeline(self) -> dict:
    """Run the complete pipeline: classify all unprocessed reviews, detect patterns, generate briefing."""
    try:
      unprocessed_reviews: list[dict] = get_unprocessed_reviews()
      if unprocessed_reviews:
        self.sentiment_agent.run(unprocessed_reviews)
        self.logger.info("Classified %d unprocessed reviews", len(unprocessed_reviews))
      else:
        self.logger.info("No new reviews to classify")

      all_reviews: list[dict] = get_all_reviews()
      classified_reviews: list[dict] = [
        review for review in all_reviews if review.get("sentiment") is not None
      ]

      if not classified_reviews:
        self.logger.error("No classified reviews available")
        return {"success": False, "error": "No classified reviews available"}

      pattern_data: dict = self.pattern_agent.run(classified_reviews)
      briefing_markdown: str = self.briefing_agent.run(classified_reviews, pattern_data)
      briefing_id: int = save_briefing(len(classified_reviews), briefing_markdown)

      self.logger.info(
        "Pipeline complete. Briefing id=%s, reviews=%d",
        briefing_id,
        len(classified_reviews),
      )

      return {
        "success": True,
        "briefing_id": briefing_id,
        "briefing_markdown": briefing_markdown,
        "review_count": len(classified_reviews),
        "pattern_data": pattern_data,
      }
    except Exception as e:
      self.logger.error(f"Pipeline failed: {e}")
      return {"success": False, "error": str(e)}

  def run_incremental_pipeline(self) -> dict:
    """Run pipeline for only new (unprocessed) reviews and skip if none exist."""
    try:
      unprocessed_reviews: list[dict] = get_unprocessed_reviews()
      if not unprocessed_reviews:
        self.logger.info("No new reviews to process")
        return {"success": True, "skipped": True, "message": "No new reviews"}

      classified_reviews: list[dict] = self.sentiment_agent.run(unprocessed_reviews)
      self.logger.info("Classified %d new reviews", len(classified_reviews))

      if not classified_reviews:
        self.logger.error("No classified reviews available from incremental run")
        return {"success": False, "error": "No classified reviews available"}

      pattern_data: dict = self.pattern_agent.run(classified_reviews)
      briefing_markdown: str = self.briefing_agent.run(classified_reviews, pattern_data)
      briefing_id: int = save_briefing(len(classified_reviews), briefing_markdown)

      self.logger.info(
        "Incremental pipeline complete. Briefing id=%s, new_reviews=%d",
        briefing_id,
        len(classified_reviews),
      )

      return {
        "success": True,
        "briefing_id": briefing_id,
        "briefing_markdown": briefing_markdown,
        "review_count": len(classified_reviews),
        "pattern_data": pattern_data,
        "incremental": True,
      }
    except Exception as e:
      self.logger.error(f"Incremental pipeline failed: {e}")
      return {"success": False, "error": str(e)}

  def run_pipeline_for_review_ids(self, review_ids: list[str]) -> dict:
    """Generate a briefing for a specific review_id batch (e.g., uploaded JSON file)."""
    try:
      selected_reviews: list[dict] = get_reviews_by_ids(review_ids)
      if not selected_reviews:
        self.logger.info("No selected reviews found for provided ids")
        return {"success": True, "skipped": True, "message": "No selected reviews found"}

      selected_unprocessed: list[dict] = [
        review for review in selected_reviews if review.get("is_processed") == 0
      ]

      if selected_unprocessed:
        self.sentiment_agent.run(selected_unprocessed)
        self.logger.info("Classified %d selected unprocessed reviews", len(selected_unprocessed))

      # Re-fetch to ensure we use the latest DB state after any classification updates.
      refreshed_selected: list[dict] = get_reviews_by_ids(review_ids)
      classified_selected: list[dict] = [
        review for review in refreshed_selected if review.get("sentiment") is not None
      ]

      if not classified_selected:
        self.logger.error("No classified reviews available for selected batch")
        return {"success": False, "error": "No classified reviews available for selected batch"}

      pattern_data: dict = self.pattern_agent.run(classified_selected)
      briefing_markdown: str = self.briefing_agent.run(classified_selected, pattern_data)
      briefing_id: int = save_briefing(len(classified_selected), briefing_markdown)

      self.logger.info(
        "Selected-batch pipeline complete. Briefing id=%s, selected_reviews=%d",
        briefing_id,
        len(classified_selected),
      )

      return {
        "success": True,
        "briefing_id": briefing_id,
        "briefing_markdown": briefing_markdown,
        "review_count": len(classified_selected),
        "pattern_data": pattern_data,
        "selected_batch": True,
      }
    except Exception as e:
      self.logger.error(f"Selected-batch pipeline failed: {e}")
      return {"success": False, "error": str(e)}

  def get_latest_briefing(self) -> dict | None:
    """Fetch the most recent briefing from the database."""
    briefings = get_all_briefings()
    return briefings[0] if briefings else None
