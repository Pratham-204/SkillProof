"""RealGroqClient previously had zero direct test coverage. Mirrors
test_real_github_client.py's approach: httpx.post is monkeypatched per test
rather than adding a new test dependency.
"""

import json

import httpx
import pytest

from skillproof.groq_client import GroqUnavailableError, RealGroqClient


def _client() -> RealGroqClient:
    return RealGroqClient(api_key="test-key", model="test-model", base_url="https://example.test")


def _respond(monkeypatch, body: dict, capture: dict | None = None) -> None:
    def fake_post(url, **kwargs):
        if capture is not None:
            capture["json"] = kwargs["json"]
        return httpx.Response(200, json=body, request=httpx.Request("POST", url))

    monkeypatch.setattr(httpx, "post", fake_post)


def test_generate_explanation_raises_groq_unavailable_on_null_content(monkeypatch):
    """Groq can return a 200 with `choices[0].message.content` set to JSON
    `null` (a refusal or a tool-call-only completion) — this must degrade to
    GroqUnavailableError like every other Groq failure mode, not crash with
    an uncaught AttributeError from `None.strip()` (B19)."""
    _respond(monkeypatch, {"choices": [{"message": {"content": None}}]})

    with pytest.raises(GroqUnavailableError):
        _client().generate_explanation("prompt")


def test_draft_skill_tag_raises_groq_unavailable_on_null_content(monkeypatch):
    """Same null-content gap on the draft_skill_tag path — a malformed Groq
    response must not abort the whole taxonomy_growth batch run."""
    _respond(monkeypatch, {"choices": [{"message": {"content": None}}]})

    with pytest.raises(GroqUnavailableError):
        _client().draft_skill_tag("some-package", "npm", [])


def test_draft_skill_tag_sanitizes_control_characters_and_caps_length_in_prompt(monkeypatch):
    """package_name is candidate-controlled (a manifest dependency name) and is
    f-string-interpolated into the LLM prompt (B5) — control characters must be
    stripped and length capped before it reaches the prompt."""
    capture: dict = {}
    _respond(monkeypatch, {"choices": [{"message": {"content": json.dumps({"skip": True})}}]}, capture)

    malicious_name = "evil\x00\x01\x1fpkg\n" + ("x" * 500)
    _client().draft_skill_tag(malicious_name, "npm", [])

    prompt = capture["json"]["messages"][1]["content"]
    assert "\x00" not in prompt
    assert "\x01" not in prompt
    assert "\x1f" not in prompt
    assert malicious_name not in prompt  # the raw, oversized string must not appear verbatim

    interpolated_name = prompt.split("A package named '", 1)[1].split("' (ecosystem:", 1)[0]
    assert len(interpolated_name) <= 100


def test_draft_skill_tag_returns_none_on_skip(monkeypatch):
    _respond(monkeypatch, {"choices": [{"message": {"content": json.dumps({"skip": True})}}]})

    assert _client().draft_skill_tag("some-package", "npm", []) is None
