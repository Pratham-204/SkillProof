"""Direct unit tests for explain_service.py — pure functions over an
EvidenceCard, previously only exercised indirectly through /explain in
test_api_flow.py (which only reaches two of the possible template_fallback
shapes: zero evidence, and commits + a PR comment together).
"""

from skillproof.explain_service import build_prompt, generate_explanation, template_fallback
from skillproof.groq_client import FakeGroqClient
from skillproof.models import EvidenceCard


def _card(**overrides) -> EvidenceCard:
    """Builds a bare EvidenceCard with no DB session. mapped_column(default=...)
    only applies at flush/INSERT, not at plain construction, so every column not
    listed here (status, evidence_type, etc.) is None rather than its declared
    default — fine only because build_prompt/template_fallback/generate_explanation
    never read those columns."""
    defaults = dict(
        skill="FastAPI",
        confidence_score=0.72,
        source_commits=[],
        temporal_span_days=0,
    )
    return EvidenceCard(**{**defaults, **overrides})


def test_build_prompt_includes_skill_and_score():
    card = _card(skill="Rust", confidence_score=0.5)

    prompt = build_prompt(card)

    assert "Rust" in prompt
    assert "0.5" in prompt


def test_build_prompt_lists_each_qualifying_item():
    card = _card(
        source_commits=[
            {"kind": "commit", "repo": "octodev/lib", "ref": "c1", "url": "https://x/c1", "similarity": 0.9},
            {"kind": "pr_comment", "repo": "octodev/lib", "ref": "p1", "url": "https://x/p1", "similarity": 0.8},
        ]
    )

    prompt = build_prompt(card)

    assert "(commit) octodev/lib: similarity 0.9" in prompt
    assert "(pr_comment) octodev/lib: similarity 0.8" in prompt


def test_build_prompt_states_none_when_no_qualifying_evidence():
    card = _card(source_commits=[])

    assert "(none)" in build_prompt(card)


def test_build_prompt_warns_against_no_evidence_claim_when_verified_with_no_qualifying_items():
    card = _card(source_commits=[], evidence_type="verified")

    prompt = build_prompt(card)

    assert "don't say no evidence was found" in prompt


def test_build_prompt_omits_no_evidence_warning_when_declared_only():
    card = _card(source_commits=[], evidence_type="declared_only")

    prompt = build_prompt(card)

    assert "don't say no evidence was found" not in prompt


def test_template_fallback_with_no_evidence_and_zero_score():
    card = _card(source_commits=[], confidence_score=0.0)

    text = template_fallback(card)

    assert "FastAPI" in text
    assert "0.0" in text


def test_template_fallback_with_no_qualifying_items_reports_actual_nonzero_score():
    """A verified card can reach zero qualifying (Depth-floor-clearing) items while
    Presence/Volume/Span still produced a real nonzero score (round 6) — the fallback
    text must report that actual score, not silently claim it's 0."""
    card = _card(source_commits=[], confidence_score=0.27, evidence_type="verified")

    text = template_fallback(card)

    assert "FastAPI" in text
    assert "0.27" in text
    assert "confidence score is 0" not in text


def test_template_fallback_with_no_qualifying_items_does_not_claim_no_evidence_when_verified():
    """The `verified` + empty-source_commits case has real matching commits behind
    it (Volume found them; Depth's floor just discarded all of them) — the fallback
    must not say "no individual commit or PR comment qualified", which would
    contradict evidence_type='verified' and imply nothing was ever found."""
    card = _card(source_commits=[], confidence_score=0.27, evidence_type="verified")

    text = template_fallback(card)

    assert "No individual commit or PR comment qualified" not in text
    assert "were found" in text


def test_template_fallback_with_declared_only_still_reports_no_evidence():
    """A declared_only card genuinely has zero matching commits — this is the one
    case the original "no individual commit or PR comment" wording is accurate for."""
    card = _card(source_commits=[], confidence_score=0.20, evidence_type="declared_only")

    text = template_fallback(card)

    assert "No individual commit or PR comment qualified" in text


def test_template_fallback_pluralizes_singular_commit_correctly():
    card = _card(
        source_commits=[
            {"kind": "commit", "repo": "octodev/lib", "ref": "c1", "url": "https://x/c1", "similarity": 0.9},
        ],
        temporal_span_days=1,
    )

    text = template_fallback(card)

    assert "1 commit " in text
    assert "commits" not in text
    assert "1 day" in text
    assert "days" not in text


def test_template_fallback_pluralizes_multiple_commits_and_reviews():
    card = _card(
        source_commits=[
            {"kind": "commit", "repo": "octodev/lib", "ref": "c1", "url": "https://x/c1", "similarity": 0.9},
            {"kind": "commit", "repo": "octodev/lib", "ref": "c2", "url": "https://x/c2", "similarity": 0.8},
            {"kind": "pr_comment", "repo": "someorg/proj", "ref": "p1", "url": "https://x/p1", "similarity": 0.7},
        ],
        temporal_span_days=45,
    )

    text = template_fallback(card)

    assert "2 commits" in text
    assert "1 pr review comment" in text  # evidence_desc.capitalize() lowercases the rest
    assert "2 repos" in text  # octodev/lib and someorg/proj
    assert "45 days" in text


def test_template_fallback_with_only_commits_omits_review_comment_phrase():
    card = _card(
        source_commits=[
            {"kind": "commit", "repo": "octodev/lib", "ref": "c1", "url": "https://x/c1", "similarity": 0.9},
        ],
        temporal_span_days=1,
    )

    text = template_fallback(card)

    assert "1 commit" in text
    assert "review comment" not in text


def test_template_fallback_with_only_reviews_omits_commit_phrase():
    card = _card(
        source_commits=[
            {"kind": "pr_comment", "repo": "octodev/lib", "ref": "p1", "url": "https://x/p1", "similarity": 0.9},
        ],
        temporal_span_days=1,
    )

    text = template_fallback(card)

    assert "1 pr review comment" in text
    assert "commit" not in text


def test_generate_explanation_returns_groq_response_when_it_succeeds():
    card = _card()
    groq = FakeGroqClient(canned_response="A real explanation.")

    text, is_fallback = generate_explanation(card, groq)

    assert text == "A real explanation."
    assert is_fallback is False


def test_generate_explanation_falls_back_to_template_when_groq_is_unavailable():
    card = _card(source_commits=[])
    groq = FakeGroqClient(should_fail=True)

    text, is_fallback = generate_explanation(card, groq)

    assert is_fallback is True
    assert text == template_fallback(card)
