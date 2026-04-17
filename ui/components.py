"""Reusable Streamlit UI components for briefing, charts, and review tables."""

from __future__ import annotations

import pandas as pd
import streamlit as st


def render_briefing(briefing_markdown: str) -> None:
	"""Render briefing markdown inside a container."""
	st.markdown(briefing_markdown, unsafe_allow_html=False)


def render_reviews_table(reviews: list[dict]) -> None:
	"""Render review rows as a dataframe with selected visible columns."""
	if not reviews:
		st.info("No reviews found for this category.")
		return

	df: pd.DataFrame = pd.DataFrame(reviews)
	visible_columns: list[str] = [
		"author",
		"rating",
		"review_text",
		"sentiment",
		"category",
		"date_posted",
	]

	for col in visible_columns:
		if col not in df.columns:
			df[col] = None

	st.dataframe(df[visible_columns], use_container_width=True)


def render_sentiment_chart(pattern_data: dict) -> None:
	"""Render bar chart for sentiment breakdown."""
	st.subheader("Sentiment Breakdown")
	sentiment_breakdown: dict = pattern_data.get("sentiment_breakdown", {})
	chart_df: pd.DataFrame = pd.DataFrame.from_dict(
		sentiment_breakdown,
		orient="index",
		columns=["count"],
	)
	st.bar_chart(chart_df)


def render_category_chart(pattern_data: dict) -> None:
	"""Render bar chart for category counts."""
	st.subheader("Issues by Category")
	category_counts: dict = pattern_data.get("category_counts", {})
	chart_df: pd.DataFrame = pd.DataFrame.from_dict(
		category_counts,
		orient="index",
		columns=["count"],
	)
	st.bar_chart(chart_df)
