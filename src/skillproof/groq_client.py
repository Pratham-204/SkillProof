from __future__ import annotations

import json
from abc import ABC, abstractmethod
from dataclasses import dataclass, field

import httpx

from skillproof.config import get_settings
from skillproof.taxonomy import SkillTag


class GroqUnavailableError(Exception):
    """Raised on any Groq failure (timeout, error status, rate limit, malformed
    response). `/explain` callers fall back to a template; `taxonomy_growth`
    callers skip the Sighting for this run without recording a decision, since a
    failure is an infrastructure problem, not a judgment (round 8, ADR-0008)."""


@dataclass(frozen=True)
class SkillTagDraft:
    """What `draft_skill_tag` proposes for one Sighting that clears the deterministic
    registry-existence and exact-name-dedup guards. `category` is validated by the
    caller against the taxonomy's fixed five categories — a value outside that set
    is treated as an abstain, not trusted verbatim (round 8, ADR-0008)."""

    name: str
    category: str
    description: str


class GroqClient(ABC):
    @abstractmethod
    def generate_explanation(self, prompt: str) -> str: ...

    @abstractmethod
    def draft_skill_tag(self, package_name: str, ecosystem: str, existing_skills: list[SkillTag]) -> SkillTagDraft | None:
        """Drafts a new Skill Tag for a Sighting, or returns None to abstain — either
        because it judges the package isn't a genuine claimable skill, or because it's
        a semantic duplicate of one of `existing_skills` even though it already
        cleared the exact-name dedup check."""
        ...


class RealGroqClient(GroqClient):
    def __init__(self, api_key: str | None = None, model: str | None = None, base_url: str | None = None):
        settings = get_settings()
        self._api_key = api_key or settings.groq_api_key
        self._model = model or settings.groq_model
        self._base_url = base_url or settings.groq_base_url

    def _post_chat(self, system: str, user: str, *, max_tokens: int, temperature: float) -> str:
        """Shared request/error-handling shape behind both `generate_explanation` and
        `draft_skill_tag` — returns the raw completion text; each caller does its own
        post-processing (a stripped sentence, or JSON to parse)."""
        try:
            response = httpx.post(
                f"{self._base_url}/chat/completions",
                headers={"Authorization": f"Bearer {self._api_key}"},
                json={
                    "model": self._model,
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user", "content": user},
                    ],
                    "max_tokens": max_tokens,
                    "temperature": temperature,
                },
                timeout=10,
            )
            response.raise_for_status()
            data = response.json()
            content = data["choices"][0]["message"]["content"].strip()
        except (httpx.HTTPError, KeyError, IndexError, ValueError) as exc:
            raise GroqUnavailableError(str(exc)) from exc

        if not content:
            # A reasoning model can spend its whole completion budget on hidden
            # `reasoning` tokens and return empty `content` with a 200 and no
            # exception raised anywhere above — that is not a real explanation
            # and must not be cached as one (this actually happened in production).
            raise GroqUnavailableError("Groq returned an empty completion")
        return content

    def generate_explanation(self, prompt: str) -> str:
        return self._post_chat(
            "You write one concise, factual sentence explaining a developer's skill confidence score "
            "from their GitHub evidence. No preamble.",
            prompt,
            max_tokens=120,
            temperature=0.3,
        )

    def draft_skill_tag(self, package_name: str, ecosystem: str, existing_skills: list[SkillTag]) -> SkillTagDraft | None:
        existing_text = "\n".join(f"- {s.name}: {s.description}" for s in existing_skills)
        prompt = (
            f"A package named '{package_name}' (ecosystem: {ecosystem}) has been declared as a "
            "dependency across multiple candidates' repositories, but it isn't in SkillProof's "
            "taxonomy of claimable Skill Tags yet.\n\n"
            f"Existing Skill Tags (name: description):\n{existing_text}\n\n"
            "Decide whether this package represents a genuine, distinct claimable technical skill "
            "not already covered by one of the existing Skill Tags above — in name OR meaning (e.g. "
            "a database driver package is the same skill as the database itself, not a new one). "
            'If it is: respond with exactly {"name": "<Skill Tag name>", "category": '
            '"<one of language, framework, infra, datastore, tool>", "description": "<one-sentence '
            'canonical description>"}. If it is not (a duplicate of an existing entry, a private or '
            "internal-looking package, or too narrow/trivial to be a claimable skill): respond with "
            'exactly {"skip": true}. Respond with JSON only, no other text.'
        )
        try:
            content = self._post_chat(
                "You curate a taxonomy of verifiable technical skills. Respond with JSON only.",
                prompt,
                max_tokens=200,
                temperature=0.2,
            )
            parsed = json.loads(content)
        except ValueError as exc:
            raise GroqUnavailableError(str(exc)) from exc

        if not isinstance(parsed, dict):
            raise GroqUnavailableError(f"Malformed draft_skill_tag response: expected a JSON object, got {parsed!r}")

        if parsed.get("skip"):
            return None
        try:
            return SkillTagDraft(name=parsed["name"], category=parsed["category"], description=parsed["description"])
        except KeyError as exc:
            raise GroqUnavailableError(f"Malformed draft_skill_tag response: missing {exc}") from exc


@dataclass
class FakeGroqClient(GroqClient):
    """Test double: returns a canned explanation/draft, or raises to exercise the
    fallback (`generate_explanation`) or skip-without-deciding (`draft_skill_tag`)
    paths."""

    canned_response: str | None = "Fake explanation grounded in the candidate's evidence."
    should_fail: bool = False
    calls: list[str] = field(default_factory=list)
    draft_response: SkillTagDraft | None = None
    draft_should_fail: bool = False
    draft_calls: list[tuple[str, str]] = field(default_factory=list)

    def generate_explanation(self, prompt: str) -> str:
        self.calls.append(prompt)
        if self.should_fail or self.canned_response is None:
            raise GroqUnavailableError("Fake Groq client configured to fail")
        return self.canned_response

    def draft_skill_tag(self, package_name: str, ecosystem: str, existing_skills: list[SkillTag]) -> SkillTagDraft | None:
        self.draft_calls.append((package_name, ecosystem))
        if self.draft_should_fail:
            raise GroqUnavailableError("Fake Groq client configured to fail on draft_skill_tag")
        return self.draft_response
