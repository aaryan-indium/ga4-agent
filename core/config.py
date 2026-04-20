from __future__ import annotations
import os
from pathlib import Path
from dotenv import load_dotenv

# ── Load .env from project root ──────────────────────────────────
_PROJECT_ROOT: Path = Path(__file__).resolve().parent.parent
load_dotenv(_PROJECT_ROOT / ".env")

# ── Ollama ────────────────────────────────────────────────────────
OLLAMA_HOST: str = os.getenv("OLLAMA_HOST", "http://localhost:11434")
OLLAMA_MODEL: str = os.getenv("OLLAMA_MODEL", "gemma2:2b")

# ── Database ──────────────────────────────────────────────────────
DATABASE_PATH: Path = _PROJECT_ROOT / os.getenv("DATABASE_PATH", "data/reviews.db")

# ── Scraper ───────────────────────────────────────────────────────
SCRAPE_APP_ID: str = os.getenv("SCRAPE_APP_ID", "com.activision.callofduty.shooter")
SCRAPE_REVIEW_COUNT: int = int(os.getenv("SCRAPE_REVIEW_COUNT", "200"))

# ── Application ───────────────────────────────────────────────────
LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")

# ── Derived / Convenience ────────────────────────────────────────
LOG_DIR: Path = _PROJECT_ROOT / "logs"
AGENT_BATCH_SIZE: int = int(os.getenv("AGENT_BATCH_SIZE", "10"))


if __name__ == "__main__": 
    # direct-run diagnostic block
    print("=== GA-4 Agent — Configuration ===")
    print(f"  OLLAMA_HOST        = {OLLAMA_HOST}")
    print(f"  OLLAMA_MODEL       = {OLLAMA_MODEL}")
    print(f"  DATABASE_PATH      = {DATABASE_PATH}")
    print(f"  SCRAPE_APP_ID      = {SCRAPE_APP_ID}")
    print(f"  SCRAPE_REVIEW_COUNT= {SCRAPE_REVIEW_COUNT}")
    print(f"  LOG_LEVEL          = {LOG_LEVEL}")
    print(f"  LOG_DIR            = {LOG_DIR}")
    print(f"  AGENT_BATCH_SIZE   = {AGENT_BATCH_SIZE}")