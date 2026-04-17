"""Ollama connectivity and model verification script.

Checks that Ollama is reachable, the configured model is pulled, and
a test chat completes successfully.  Designed for clean user-facing
output with no stack traces.

Usage:
    python check_ollama.py
"""

from __future__ import annotations

import sys

import ollama
import psutil

from core.config import OLLAMA_HOST, OLLAMA_MODEL


def main() -> None:
    """Run all three Ollama verification checks in sequence."""
    # ── Step 1: Check available RAM ──────────────────────────────
    available_ram_gb: float = psutil.virtual_memory().available / (1024**3)
    if available_ram_gb < 5.0:
        print(
            f"[WARN] Only {available_ram_gb:.1f}GB RAM available. "
            f"{OLLAMA_MODEL} may need ~5GB free. Close other apps."
        )
    else:
        print(f"[PASS] Available RAM: {available_ram_gb:.1f}GB")

    # ── Step 2: Check connectivity ───────────────────────────────
    try:
        client: ollama.Client = ollama.Client(host=OLLAMA_HOST)
        model_list = client.list()
    except Exception as exc:
        print(f"[FAIL] Ollama not reachable at {OLLAMA_HOST}. Is the Ollama app running?")
        print(f"       Error: {exc}")
        sys.exit(1)

    print(f"[PASS] Ollama reachable at {OLLAMA_HOST}")

    # ── Step 3: Check model availability ─────────────────────────
    available_models: list[str] = []
    try:
        for model_entry in model_list.models:
            available_models.append(model_entry.model)
    except Exception:
        # Fallback for different API response shapes
        pass

    # Match by prefix (e.g. configured model "foo:bar" matches "foo:bar" or "foo:bar-instruct")
    model_found: bool = any(
        m == OLLAMA_MODEL or m.startswith(OLLAMA_MODEL)
        for m in available_models
    )

    if not model_found:
        print(f"[FAIL] Model {OLLAMA_MODEL} not found. Run: ollama pull {OLLAMA_MODEL}")
        if available_models:
            print(f"       Available models: {', '.join(available_models)}")
        sys.exit(1)

    print(f"[PASS] Model {OLLAMA_MODEL} is available")

    # ── Step 4: Test chat ────────────────────────────────────────
    try:
        response = client.chat(
            model=OLLAMA_MODEL,
            messages=[
                {"role": "system", "content": "You are a test assistant."},
                {"role": "user", "content": "Reply with exactly the word: ONLINE"},
            ],
        )
        reply: str = response.message.content.strip()  # type: ignore[union-attr]
    except Exception as exc:
        print(f"[FAIL] Test chat failed: {exc}")
        sys.exit(1)

    print(f"[PASS] Test response: {reply}")
    print("\nAll checks passed. Ollama is ready.")


if __name__ == "__main__":
    main()
