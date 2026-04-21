# Player Feedback Intelligence System

This capstone project ingests mobile game player reviews, runs them through a 3-agent AI pipeline, and produces a daily briefing for a non-technical Game Producer. It is built in Python 3.11+ with Ollama running locally (default: `gemma2:2b`, configurable in `.env`), uses SQLite for storage (no external database), and provides a Streamlit UI. Review ingestion supports Google Play scraping through `google-play-scraper` for app ID `com.activision.callofduty.shooter` (CoD Mobile) and JSON upload. Hardware tested: AMD Ryzen 7 5800U, 16GB RAM, CPU-only.

## Setup Instructions

1. Install prerequisites:
   - Python 3.11+
   - Ollama desktop app from https://ollama.com
   - Git
2. Clone the repository:

```bash
git clone <your-repo-url>
cd "GA-4 Agent"
```

3. Create and activate a virtual environment (Windows):

```bash
python -m venv venv
venv\Scripts\activate
```

4. Install dependencies:

```bash
pip install -r requirements.txt
pip install -e .
```

5. Copy environment template and fill values:

```bash
copy .env.example .env
```

Set these exact keys in `.env`:
- `OLLAMA_HOST`
- `OLLAMA_MODEL`
- `DATABASE_PATH`
- `SCRAPE_APP_ID`
- `SCRAPE_REVIEW_COUNT`
- `LOG_LEVEL`
- `AGENT_BATCH_SIZE`

6. Pull the local model:

```bash
ollama pull gemma2:2b
```

7. Verify Ollama and model setup:

```bash
python check_ollama.py
```

8. Run the Streamlit app:

```bash
streamlit run ui/app.py
```

Note: A full pipeline run on 200 reviews takes about 60-90 minutes on CPU-only hardware. A pre-processed briefing is included in the database for immediate demo use.

## Architecture Overview

The system follows a five-layer architecture. The Input Layer ingests reviews from Google Play scraping and Streamlit JSON upload, then stores them in SQLite. The Agent Layer contains three single-responsibility agents: `SentimentAgent` performs per-review classification, `PatternAgent` performs cross-review analysis, and `BriefingAgent` produces producer-ready markdown. The Orchestration Layer is a pure Python `Pipeline` class (no LangChain or CrewAI) that wires Agent 1 -> Agent 2 -> Agent 3 through `run_full_pipeline()` and `run_incremental_pipeline()`. The Storage Layer uses SQLite with `reviews` and `briefings` tables, deduplication through a UNIQUE constraint on `review_id`, and idempotent ingestion behavior. The UI Layer is Streamlit with four pages: Latest Briefing, Run Analysis, History, and Drill Down.

`BaseAgent` provides the shared Ollama client, `_call_ollama()`, and abstract `run()`. `SentimentAgent` (Agent 1) processes reviews in batches of 10, classifies sentiment (`positive`/`negative`/`mixed`) and category (`crashes`, `monetization`, `gameplay_balance`, `performance`, `ux_ui`, `server_issues`, `content_requests`, `positive_feedback`, `other`), and persists results to the database. `PatternAgent` (Agent 2) receives Agent 1 output, pre-computes counts locally with `collections.Counter`, sends compact summaries to Ollama for trend reasoning, and returns a 7-field pattern dictionary. `BriefingAgent` (Agent 3) receives classified reviews and pattern data, selects representative reviews (max 30 total, up to 3 per category), and generates a markdown briefing with 5 sections.

```text
Player Reviews (Google Play / JSON Upload)
        │
        ▼
┌─────────────────┐
│  Ingestion Layer │  scraper.py → SQLite
└────────┬────────┘
         │ unprocessed reviews
         ▼
┌─────────────────┐
│   Agent 1        │  SentimentAgent — per-review classification
│   (Sentiment)    │  sentiment + category + summary → saved to DB
└────────┬────────┘
         │ classified reviews
         ▼
┌─────────────────┐
│   Agent 2        │  PatternAgent — cross-review pattern detection
│   (Patterns)     │  counts (Python) + trends (Ollama) → pattern dict
└────────┬────────┘
         │ patterns + classified reviews
         ▼
┌─────────────────┐
│   Agent 3        │  BriefingAgent — synthesis
│   (Briefing)     │  markdown briefing → saved to DB
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  Streamlit UI    │  Latest Briefing / Run Analysis / History / Drill Down
└─────────────────┘
```

## Design Decisions

### Python over C#

Python over C#: The assignment recommends C# for backend logic, but Python was chosen because Ollama's official SDK is Python-first, the agentic AI ecosystem is Python-native, and this project prioritizes demonstrating orchestration principles clearly. Every design decision is defensible in a live code review.

### No LangChain or CrewAI

No LangChain or CrewAI: Orchestration is built from scratch in pure Python. This was deliberate because using a framework would require explaining framework decisions instead of developer decisions. The live review requires explaining every line. The trade-off is no built-in memory or tool-use abstractions. The gain is complete transparency and full ownership of orchestration logic.

### Deterministic Counting in Agent 2

Deterministic counting in Agent 2: Category counts and sentiment breakdowns are computed with Python `collections.Counter`, not by asking the LLM. LLMs are unreliable at arithmetic. This hybrid design uses Python for deterministic counting and Ollama for language reasoning and trend synthesis.

### Idempotent Ingestion with Stable Review IDs

Idempotent ingestion with stable review IDs: Play Store reviews use native `reviewId`. JSON uploads use a provided `review_id` when present, otherwise a generated UUID. SQLite enforces a UNIQUE constraint on `review_id`, and ingestion uses `INSERT OR IGNORE`, so duplicate records are safely skipped.

## Known Limitations

- Processing speed: ~8-22 seconds per review on CPU-only hardware. Full pipeline on 200 reviews takes 60-90 minutes. Not suitable for real-time analysis without GPU or cloud LLM.
- Agent 1 batch failures: if Ollama runs out of memory mid-batch, affected reviews remain unprocessed (`is_processed=0`) and are retried on next run. This is by design.
- Pattern detection quality scales with data volume: with small batches, emerging trends are limited. With 200+ reviews the pattern analysis becomes significantly richer.
- No authentication: the Streamlit UI has no login. Suitable for internal/local use only.
- Single model constraint: only one Ollama model runs at a time. All three agents use the same model. A future improvement would be using a larger model for Agent 3 (briefing synthesis) and a smaller/faster model for Agent 1 (classification).
- Google Play scraping is subject to rate limits and may return fewer reviews than requested.

*Built as Assignment 2 of the Gaming AI Capstone.*
