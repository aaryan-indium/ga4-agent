"""Agent 1 — Sentiment & Category Classifier.

Receives a list of reviews, calls the local Ollama LLM in batches, and
returns each review enriched with sentiment, category, and summary fields.
"""

from __future__ import annotations

from core import config
from core.database import update_review_classification
from agents.base_agent import BaseAgent

# ── System prompt (module-level constant) ────────────────────────

SYSTEM_PROMPT: str = (
    "You are a mobile game review analyst. Your job is to classify player reviews "
    "accurately and consistently.\n\n"
    "For each review, return ONLY a valid JSON array. Each element must have exactly these fields:\n"
    "{\n"
    '  "sentiment": "<positive|negative|mixed>",\n'
    '  "category": "<one of the allowed categories>",\n'
    '  "summary": "<one sentence, max 15 words, plain English>"\n'
    "}\n\n"
    "Allowed categories: crashes, monetization, gameplay_balance, performance, "
    "ux_ui, server_issues, content_requests, positive_feedback, other\n\n"
    "Rules:\n"
    "- sentiment must be exactly: positive, negative, or mixed\n"
    "- category must be exactly one from the allowed list above\n"
    "- summary must be plain English, no jargon, max 15 words\n"
    "- Return ONLY the JSON array. No explanation. No markdown fences. No extra text.\n"
    "- The array must have exactly as many elements as reviews given."
)


class SentimentAgent(BaseAgent):
    """Classifies each review's sentiment, category, and summary via LLM."""

    def run(self, reviews: list[dict]) -> list[dict]:
        """Process reviews in batches, enrich with sentiment/category/summary."""
        if not reviews:
            self.logger.warning("No reviews to process — returning empty list")
            return []

        batch_size: int = config.AGENT_BATCH_SIZE
        total_batches: int = (len(reviews) + batch_size - 1) // batch_size
        all_results: list[dict] = []

        for batch_num in range(1, total_batches + 1):
            start: int = (batch_num - 1) * batch_size
            end: int = start + batch_size
            batch: list[dict] = reviews[start:end]
            batch_failed: bool = False

            self.logger.info("Processing batch %d/%d (%d reviews)", batch_num, total_batches, len(batch))

            user_message: str = self._build_user_message(batch)
            raw_response: str = ""

            try:
                raw_response = self._call_ollama(SYSTEM_PROMPT, user_message)
                classifications: list[dict] = self._parse_json_response(
                    raw_response,
                    expected_type=list,
                    expected_count=len(batch),
                )
            except Exception as exc:
                batch_failed = True
                self.logger.error("Batch %d failed: %s", batch_num, exc)
                classifications = self._fallback(len(batch))

            # Validate count
            if len(classifications) != len(batch):
                batch_failed = True
                self.logger.warning(
                    "Batch %d: expected %d results, got %d — using fallback. Raw: %s",
                    batch_num, len(batch), len(classifications), raw_response[:300],
                )
                classifications = self._fallback(len(batch))

            # Merge classifications into review dicts; persist only on successful batch
            for review, classification in zip(batch, classifications):
                review["sentiment"] = classification.get("sentiment", "mixed")
                review["category"] = classification.get("category", "other")
                review["summary"] = classification.get("summary", "Classification failed")
                if not batch_failed:
                    update_review_classification(
                        review["review_id"],
                        review["sentiment"],
                        review["category"],
                        review["summary"],
                    )

            all_results.extend(batch)

        return all_results

    def _build_user_message(self, batch: list[dict]) -> str:
        """Format a batch of reviews into the numbered prompt format."""
        lines: list[str] = [
            f"Classify these {len(batch)} reviews. "
            "Return a JSON array with one object per review, in the same order.\n"
        ]
        for idx, review in enumerate(batch, start=1):
            rating: int = review.get("rating", 0)
            text: str = review.get("review_text", "")
            lines.append(f'Review {idx} (Rating: {rating}/5): "{text}"')
        return "\n".join(lines)

    @staticmethod
    def _fallback(count: int) -> list[dict]:
        """Return fallback classifications when LLM parsing fails."""
        return [
            {"sentiment": "mixed", "category": "other", "summary": "Classification failed"}
            for _ in range(count)
        ]
