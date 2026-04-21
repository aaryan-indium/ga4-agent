"""Base Agent — abstract parent class for all LLM-powered agents.

Provides shared Ollama client initialisation and a single _call_ollama()
method so that subclasses only need to implement run().
"""

from __future__ import annotations

import json
import re
from typing import Any

import ollama

from core import config
from utils.logger import get_logger


class BaseAgent:
    """Abstract base for all agents; manages the Ollama client lifecycle."""

    def __init__(
        self,
        model: str = config.OLLAMA_MODEL,
        host: str = config.OLLAMA_HOST,
    ) -> None:
        """Initialise the agent with model name, host, logger, and client."""
        self.model: str = model
        self.host: str = host
        # Logger scoped by subclass name (e.g. "SentimentAgent", "PatternAgent")
        # allows caller to trace which agent produced each log message.
        self.logger = get_logger(self.__class__.__name__)
        self.client: ollama.Client = ollama.Client(host=self.host)
        self.logger.info("Initialised %s with model=%s", self.__class__.__name__, self.model)

    def _call_ollama(self, system_prompt: str, user_message: str) -> str:
        """Send a system + user message to Ollama and return the response text.
        
        System prompt establishes agent behavior/role (e.g. 'You are a sentiment classifier').
        User message contains the actual task input (e.g. batch of reviews to classify).
        """
        try:
            response = self.client.chat(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_message},
                ],
            )
            return response.message.content  # type: ignore[return-value]
        except Exception as exc:
            self.logger.error("Ollama call failed: %s", exc)
            raise

    def _parse_json_response(
        self,
        raw: str,
        expected_type: type,
        expected_count: int | None = None,
    ) -> Any:
        """Parse and validate JSON returned by an LLM response."""
        cleaned: str = raw.strip()

        # Strip markdown code fences that LLMs sometimes add around JSON.
        # Pattern 1: removes opening fence (e.g. ``` or ```json or ```json\n)
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        # Pattern 2: removes closing fence (e.g. \n``` or ``` )
        cleaned = re.sub(r"\s*```$", "", cleaned)
        cleaned = cleaned.strip()

        try:
            result: Any = json.loads(cleaned)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid JSON response: {exc}") from exc

        if not isinstance(result, expected_type):
            raise ValueError(
                f"Expected JSON {expected_type.__name__}, got {type(result).__name__}"
            )

        if expected_count is not None:
            # Sanity check: verify caller is trying to count-validate a list, not a scalar/dict.
            if not isinstance(result, list):
                raise ValueError("expected_count is only valid for JSON arrays")
            # Enforce exact match: e.g. batch of N reviews should yield exactly N classifications.
            if len(result) != expected_count:
                raise ValueError(f"Expected {expected_count} items, got {len(result)}")

        return result

    def run(self, input_data: Any) -> Any:
        """Execute the agent's core logic — must be overridden by subclasses.
        
        Raising NotImplementedError here enforces the contract that every subclass
        (SentimentAgent, PatternAgent, BriefingAgent) must provide its own concrete
        run() method with domain-specific behavior.
        """
        raise NotImplementedError("Subclasses must implement run()")
