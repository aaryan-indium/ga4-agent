"""Main Streamlit app for Player Feedback Intelligence."""

from __future__ import annotations

import tempfile

import streamlit as st

from core.database import get_all_briefings
from core.database import get_briefing_by_id
from core.database import get_reviews_by_category
from core.database import get_unprocessed_reviews
from core.database import initialize_db
from core.database import insert_reviews
from ingestion.scraper import load_from_json_file, scrape_from_play_store
from orchestrator.pipeline import Pipeline
from ui.components import render_briefing
from ui.components import render_reviews_table


CATEGORIES: list[str] = [
  "crashes",
  "monetization",
  "gameplay_balance",
  "performance",
  "ux_ui",
  "server_issues",
  "content_requests",
  "positive_feedback",
  "other",
]


st.set_page_config(
  page_title="Player Feedback Intelligence",
    page_icon=None,
  layout="wide"
)

try:
    initialize_db()
except Exception as exc:
    st.error(f"Database initialization failed: {exc}")
    st.stop()

st.title("Player Feedback Intelligence")
st.markdown("*Daily briefing system for Game Producers*")

page: str = st.sidebar.radio(
  "Navigation",
  ["Latest Briefing", "Run Analysis", "History", "Drill Down"],
)


if page == "Latest Briefing":
    pipeline: Pipeline = Pipeline()
    briefing: dict | None = pipeline.get_latest_briefing()

    if briefing is None:
        st.warning("No briefings yet. Go to Run Analysis to generate your first briefing.")
    else:
        col_meta, col_btn = st.columns([3, 1])
        with col_meta:
            st.caption(f"Generated: {briefing['created_at']}  |  Reviews analyzed: {briefing['review_count']}")
        with col_btn:
            if st.button("Generate New Briefing", key="gen_from_latest", use_container_width=True):
                try:
                    uploaded_review_ids: list[str] = st.session_state.get("uploaded_review_ids", [])
                    pending_reviews: list[dict] = get_unprocessed_reviews()
                    inserted: int = 0
                    generated_from_upload: bool = False

                    if uploaded_review_ids:
                        spinner_text = "Classifying uploaded reviews → detecting patterns → generating briefing..."
                    elif pending_reviews:
                        spinner_text = "Classifying pending reviews → detecting patterns → generating briefing..."
                    else:
                        spinner_text = "Scraping reviews → classifying → detecting patterns → generating briefing..."

                    with st.spinner(spinner_text):
                        if uploaded_review_ids:
                            generated_from_upload = True
                            if hasattr(pipeline, "run_pipeline_for_review_ids"):
                                result = pipeline.run_pipeline_for_review_ids(uploaded_review_ids)
                            else:
                                result = {
                                    "success": False,
                                    "error": (
                                        "App is using a stale pipeline module. "
                                        "Please restart Streamlit and try again."
                                    ),
                                }
                        else:
                            if not pending_reviews:
                                scraped_reviews: list[dict] = scrape_from_play_store()
                                inserted, _ = insert_reviews(scraped_reviews)
                            result = pipeline.run_incremental_pipeline()
                except Exception as exc:
                    st.error(f"Failed to run briefing generation: {exc}")
                else:
                    if result.get("success"):
                        if result.get("skipped"):
                            st.info("No new reviews to process. Upload JSON reviews first or try scraping again.")
                        elif generated_from_upload:
                            st.success(f"Done. Generated briefing from {result['review_count']} uploaded reviews.")
                            st.session_state.pop("uploaded_review_ids", None)
                            st.rerun()
                        elif pending_reviews:
                            st.success(f"Done. Generated briefing from {result['review_count']} pending reviews.")
                            st.rerun()
                        else:
                            st.success(f"Done. {inserted} new reviews scraped. {result['review_count']} new reviews analyzed.")
                            st.rerun()
                    else:
                        st.error(result.get("error", "Pipeline failed. Is Ollama running?"))
        st.divider()
        render_briefing(briefing["briefing_markdown"])


elif page == "Run Analysis":
    st.subheader("Run New Analysis")
    st.caption("Upload a JSON file of reviews. Once added, use Generate New Briefing on the Latest Briefing page to generate a briefing from pending uploaded reviews.")
    st.markdown("#### Upload Reviews")
    uploaded_file = st.file_uploader("JSON file", type=["json"], key="json_upload", label_visibility="collapsed")
    if uploaded_file is not None:
        try:
            with tempfile.NamedTemporaryFile(delete=False, suffix=".json") as tmp_file:
                tmp_file.write(uploaded_file.getvalue())
                temp_path: str = tmp_file.name
            reviews: list[dict] = load_from_json_file(temp_path)
            inserted, dupes = insert_reviews(reviews)
        except Exception as exc:
            st.error(f"Upload failed: {exc}")
        else:
            st.session_state["uploaded_review_ids"] = [str(r.get("review_id", "")) for r in reviews if r.get("review_id")]
            st.success(f"{inserted} new reviews added. {dupes} duplicates skipped.")
            if inserted > 0:
                st.info("Go to Latest Briefing and click Generate New Briefing to generate a briefing for these newly added reviews.")
            else:
                st.info("No new rows were inserted, but Generate New Briefing can still use this uploaded batch if those review IDs already exist.")


elif page == "History":
    st.subheader("Briefing History")
    briefings: list[dict] = get_all_briefings()

    if not briefings:
        st.info("No briefing history yet.")
    else:
        options: list[str] = [
            f"#{b['id']}  —  {b['created_at']}  ({b['review_count']} reviews)"
            for b in briefings
        ]
        selection: str = st.selectbox("Select a briefing", options, label_visibility="collapsed")
        selected_index: int = options.index(selection)
        selected_id: int = int(briefings[selected_index]["id"])
        selected_briefing: dict | None = get_briefing_by_id(selected_id)

        if selected_briefing is None:
            st.error("Could not load selected briefing.")
        else:
            st.caption(f"Generated: {selected_briefing['created_at']}  |  Reviews analyzed: {selected_briefing['review_count']}")
            st.divider()
            render_briefing(selected_briefing["briefing_markdown"])


elif page == "Drill Down":
    st.subheader("Drill Down by Category")
    st.caption("View all reviews classified under a category by Agent 1.")
    st.divider()

    col1, col2 = st.columns(2)
    with col1:
        selected_category: str = st.selectbox("Category", CATEGORIES, label_visibility="collapsed")
    with col2:
        sentiment_filter: str = st.selectbox(
            "Sentiment",
            ["All", "negative", "positive", "mixed"],
            label_visibility="collapsed"
        )

    reviews: list[dict] = get_reviews_by_category(selected_category)
    if sentiment_filter != "All":
        reviews = [r for r in reviews if r.get("sentiment") == sentiment_filter]

    st.metric("Reviews", len(reviews))
    render_reviews_table(reviews)
