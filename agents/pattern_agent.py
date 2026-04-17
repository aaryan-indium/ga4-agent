"""Agent 2 — Cross-Review Pattern Detector.

Receives a batch of classified reviews and identifies recurring themes,
emerging trends, and statistically notable clusters. Produces a
structured pattern report that feeds into Agent 3's daily briefing.
"""

from __future__ import annotations

import json
from collections import Counter

from agents.base_agent import BaseAgent

# ── System prompt (module-level constant) ────────────────────────

SYSTEM_PROMPT: str = (
    "You are a pattern analyst for mobile game player feedback. You receive "
    "structured review data and identify meaningful patterns across the dataset.\n\n"
    "You will be given a summary of classified reviews as a JSON dataset. "
    "Analyze it and return ONLY a valid JSON object with exactly these fields:\n\n"
    "{\n"
    '  "category_counts": {"crashes": 4, "monetization": 3, "other_keys...": 0},\n'
    '  "dominant_sentiment": "<positive|negative|mixed>",\n'
    '  "sentiment_breakdown": {"positive": 10, "negative": 12, "mixed": 3},\n'
    '  "top_issues": [\n'
    '    {"category": "crashes", "count": 4, "severity": "high", "example_summary": "..."},\n'
    '    {"category": "monetization", "count": 3, "severity": "medium", "example_summary": "..."}\n'
    "  ],\n"
    '  "emerging_trends": [\n'
    '    "Crash complaints are concentrated in ranked match mode",\n'
    '    "Monetization complaints reference the battle pass specifically"\n'
    "  ],\n"
    '  "positive_highlights": [\n'
    '    "New map receiving consistent praise across multiple reviews"\n'
    "  ],\n"
    '  "uninstall_drivers": [\n'
    '    "Repeated crashes in ranked mode causing player frustration"\n'
    "  ]\n"
    "}\n\n"
    "Rules:\n"
    "- top_issues must be sorted by count descending, max 5 items\n"
    "- severity must be: high, medium, or low\n"
    "  - high = count >= 4 OR review mentions data loss/progress loss/account issues\n"
    "  - medium = count 2-3\n"
    "  - low = count 1\n"
    "- emerging_trends: 2-4 specific, actionable observations. No generic statements.\n"
    "- positive_highlights: 1-3 items, only if genuinely present in data\n"
    "- uninstall_drivers: 1-3 items, infer from strongly negative reviews\n"
    "- Return ONLY the JSON object. No markdown. No explanation. No extra text."
)


class PatternAgent(BaseAgent):
    """Detects broad patterns and insights across a batch of classified reviews."""

    @staticmethod
    def _compute_local_stats(classified_reviews: list[dict]) -> tuple[dict[str, int], dict[str, int]]:
        """Compute deterministic category and sentiment aggregates from reviews."""
        category_counts_dict: dict[str, int] = dict(
            Counter((r.get("category") or "other") for r in classified_reviews)
        )
        sentiment_breakdown_dict: dict[str, int] = dict(
            Counter((r.get("sentiment") or "mixed") for r in classified_reviews)
        )
        return category_counts_dict, sentiment_breakdown_dict

    @staticmethod
    def _build_review_summaries(classified_reviews: list[dict]) -> list[dict]:
        """Create compact per-review payloads for the LLM prompt."""
        return [
            {
                "sentiment": r.get("sentiment") or "mixed",
                "category": r.get("category") or "other",
                "summary": r.get("summary") or "Unprocessed",
                "rating": r.get("rating", 0),
            }
            for r in classified_reviews
        ]

    @staticmethod
    def _build_user_message(
        total_reviews: int,
        review_summaries: list[dict],
        category_counts_dict: dict[str, int],
        sentiment_breakdown_dict: dict[str, int],
    ) -> str:
        """Build the user prompt with compact review context plus deterministic counts."""
        return (
            f"Analyze these {total_reviews} classified mobile game reviews and identify patterns.\n\n"
            "Dataset:\n"
            f"{json.dumps(review_summaries, indent=2)}\n\n"
            f"Category counts for reference: {json.dumps(category_counts_dict)}\n"
            f"Sentiment breakdown: {json.dumps(sentiment_breakdown_dict)}"
        )

    @staticmethod
    def _apply_local_guarantees(
        result: dict,
        category_counts_dict: dict[str, int],
        sentiment_breakdown_dict: dict[str, int],
        total_reviews: int,
    ) -> dict:
        """Overwrite LLM-provided aggregates with deterministic local values."""
        result["category_counts"] = category_counts_dict
        result["sentiment_breakdown"] = sentiment_breakdown_dict
        result["total_reviews"] = total_reviews

        if sentiment_breakdown_dict:
            dominant: str = max(sentiment_breakdown_dict.items(), key=lambda t: t[1])[0]
            result["dominant_sentiment"] = dominant

        result.setdefault("top_issues", [])
        result.setdefault("emerging_trends", [])
        result.setdefault("positive_highlights", [])
        result.setdefault("uninstall_drivers", [])
        return result

    def run(self, classified_reviews: list[dict]) -> dict:
        """Process classified reviews to identify patterns and trends."""
        if not classified_reviews:
            self.logger.warning("No reviews provided for pattern detection")
            return self._empty_fallback()

        total_reviews: int = len(classified_reviews)
        category_counts_dict, sentiment_breakdown_dict = self._compute_local_stats(classified_reviews)
        review_summaries: list[dict] = self._build_review_summaries(classified_reviews)
        user_message: str = self._build_user_message(
            total_reviews,
            review_summaries,
            category_counts_dict,
            sentiment_breakdown_dict,
        )

        try:
            raw_response: str = self._call_ollama(SYSTEM_PROMPT, user_message)
            result: dict = self._parse_json_response(raw_response, expected_type=dict)
        except Exception as exc:
            self.logger.error("Pattern detection failed: %s", exc)
            result = self._empty_fallback()
            # We don't overwrite everything; we still insert local counts into result

        result = self._apply_local_guarantees(
            result,
            category_counts_dict,
            sentiment_breakdown_dict,
            total_reviews,
        )

        top_issue: str = "None"
        if result["top_issues"]:
            top_issue = result["top_issues"][0].get("category", "Unknown")

        self.logger.info(
            "Pattern analysis complete. Dominant sentiment: %s. Top issue: %s",
            result["dominant_sentiment"],
            top_issue,
        )

        return result

    @staticmethod
    def _empty_fallback() -> dict:
        """Return a safe empty fallback dict when processing can't continue."""
        return {
            "total_reviews": 0,
            "category_counts": {},
            "dominant_sentiment": "mixed",
            "sentiment_breakdown": {"positive": 0, "negative": 0, "mixed": 0},
            "top_issues": [],
            "emerging_trends": [],
            "positive_highlights": [],
            "uninstall_drivers": [],
        }
