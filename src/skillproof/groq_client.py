from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field

import httpx

from skillproof.config import get_settings


class GroqUnavailableError(Exception):
    """Raised on any Groq failure (timeout, error status, rate limit) — callers fall back to a template."""


class GroqClient(ABC):
    @abstractmethod
    def generate_explanation(self, prompt: str) -> str: ...


class RealGroqClient(GroqClient):
    def __init__(self, api_key: str | None = None, model: str | None = None, base_url: str | None = None):
        settings = get_settings()
        self._api_key = api_key or settings.groq_api_key
        self._model = model or settings.groq_model
        self._base_url = base_url or settings.groq_base_url

    def generate_explanation(self, prompt: str) -> str:
        try:
            response = httpx.post(
                f"{self._base_url}/chat/completions",
                headers={"Authorization": f"Bearer {self._api_key}"},
                json={
                    "model": self._model,
                    "messages": [
                        {
                            "role": "system",
                            "content": "You write one concise, factual sentence explaining a developer's "
                            "skill confidence score from their GitHub evidence. No preamble.",
                        },
                        {"role": "user", "content": prompt},
                    ],
                    "max_tokens": 120,
                    "temperature": 0.3,
                },
                timeout=10,
            )
            response.raise_for_status()
            data = response.json()
            return data["choices"][0]["message"]["content"].strip()
        except (httpx.HTTPError, KeyError, IndexError, ValueError) as exc:
            raise GroqUnavailableError(str(exc)) from exc


@dataclass
class FakeGroqClient(GroqClient):
    """Test double: returns a canned explanation, or raises to exercise the fallback path."""

    canned_response: str | None = "Fake explanation grounded in the candidate's evidence."
    should_fail: bool = False
    calls: list[str] = field(default_factory=list)

    def generate_explanation(self, prompt: str) -> str:
        self.calls.append(prompt)
        if self.should_fail or self.canned_response is None:
            raise GroqUnavailableError("Fake Groq client configured to fail")
        return self.canned_response
