"""Daily briefing agent for synthesizing player feedback insights."""

from __future__ import annotations

import json

from agents.base_agent import BaseAgent


SYSTEM_PROMPT: str = """You are a senior product analyst writing a daily briefing for a non-technical Game Producer at a mobile gaming studio. Your briefing must be readable in under 2 minutes and drive immediate action.

You will receive two inputs:
1. A pattern analysis summary (from automated analysis across all reviews)
2. A sample of individual review summaries (the most representative ones)

Write a daily briefing in clean Markdown with EXACTLY these five sections:

## Today's Snapshot
One paragraph. Overall sentiment, total reviews analyzed, one-sentence characterization of the day's feedback.

## Top Issues
Ranked list of the most important problems. For each: issue name, how many reviews mention it, severity (Critical/High/Medium), and one specific example from the reviews.

## What Players Love
2-3 bullet points of genuine praise. Only include if clearly present in data. If no positives exist, write "No significant positive feedback in this batch."

## Emerging Trends
2-3 specific observations about patterns signaling future risk or opportunity. Name the feature, mode, or update being referenced.

## Recommended Actions
Exactly 3 actions. Each labeled Priority 1, Priority 2, Priority 3. Each must be specific (name the issue or feature), actionable (something a producer can do), and prioritized.

Tone rules:
- Write like a sharp human analyst, not an AI
- No jargon, no JSON artifacts, no technical terms
- No phrases like "As an AI" or "Based on the data provided"
- Short sentences. Active voice. Producer-friendly."""


class BriefingAgent(BaseAgent):
    """Generate a producer-friendly markdown briefing from review analysis."""

    def _select_representative_reviews(self, reviews: list[dict]) -> list[dict]:
        """Select up to 3 representative reviews per category, capped at 30 total."""
        selected: list[dict] = []
        by_category: dict[str, list[dict]] = {}

        for review in reviews:
            category: str = review.get("category", "other")
            by_category.setdefault(category, []).append(review)

        for category_reviews in by_category.values():
            prioritized: list[dict] = sorted(
                category_reviews,
                key=lambda r: (
                    0 if r.get("sentiment") == "negative" and r.get("rating", 5) <= 2 else 1,
                    r.get("rating", 5),
                ),
            )

            for review in prioritized[:3]:
                selected.append(
                    {
                        "summary": review.get("summary", ""),
                        "sentiment": review.get("sentiment", "mixed"),
                        "category": review.get("category", "other"),
                        "rating": review.get("rating", 0),
                    }
                )

                if len(selected) >= 30:
                    return selected

        return selected

    def run(self, classified_reviews: list[dict], pattern_data: dict) -> str:
        """Synthesize classified reviews and pattern data into a markdown daily briefing."""
        if not classified_reviews or not pattern_data:
            self.logger.warning("No reviews or pattern data available for briefing generation")
            return "## No Data\nNo reviews available for analysis."

        representative_reviews: list[dict] = self._select_representative_reviews(classified_reviews)

        user_message: str = f"""Here is today's player feedback analysis:

PATTERN ANALYSIS:
- Total reviews: {pattern_data['total_reviews']}
- Dominant sentiment: {pattern_data['dominant_sentiment']}
- Sentiment breakdown: {pattern_data['sentiment_breakdown']}
- Top issues: {json.dumps(pattern_data['top_issues'], indent=2)}
- Emerging trends: {pattern_data['emerging_trends']}
- What players love: {pattern_data['positive_highlights']}
- Uninstall drivers: {pattern_data['uninstall_drivers']}

REPRESENTATIVE REVIEW SUMMARIES ({len(representative_reviews)} reviews):
{json.dumps(representative_reviews, indent=2)}

Write the daily briefing now."""

        response: str = self._call_ollama(SYSTEM_PROMPT, user_message)
        self.logger.info(f"Briefing generated. Length: {len(response)} chars")
        return response
