"""Centralised logging — consistent formatting across all modules.

Provides a single factory function that returns a named logger writing to
both the console and a persistent log file (logs/app.log).  Calling
get_logger() multiple times with the same name returns the same logger
instance with no duplicate handlers.

Usage:
    from utils.logger import get_logger
    logger = get_logger(__name__)
    logger.info("Scraped %d reviews", count)
"""

from __future__ import annotations

import logging
from pathlib import Path

from core.config import LOG_DIR, LOG_LEVEL

# ── Module-level constants ───────────────────────────────────────
_LOG_FORMAT: str = "[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s"
_DATE_FORMAT: str = "%Y-%m-%d %H:%M:%S"
_LOG_FILE: Path = LOG_DIR / "app.log"


def get_logger(name: str) -> logging.Logger:
    """Return a named logger with console + file handlers (no duplicates)."""
    logger: logging.Logger = logging.getLogger(name)

    # If handlers already attached, return immediately to prevent duplicates
    if logger.handlers:
        return logger

    logger.setLevel(getattr(logging, LOG_LEVEL.upper(), logging.INFO))

    formatter: logging.Formatter = logging.Formatter(_LOG_FORMAT, datefmt=_DATE_FORMAT)

    # Console handler
    console_handler: logging.StreamHandler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    # File handler — create logs/ directory if needed
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    file_handler: logging.FileHandler = logging.FileHandler(str(_LOG_FILE), encoding="utf-8")
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    return logger
