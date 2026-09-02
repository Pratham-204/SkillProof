from __future__ import annotations

import logging

from skillproof.groq_client import GroqClient, GroqUnavailableError
from skillproof.models import EvidenceCard

logger = logging.getLogger(__name__)


def build_prompt(card: EvidenceCard) -> str:
    refs = card.source_commits or []
    evidence_lines = "\n".join(f"- ({ref['kind']}) {ref['repo']}: similarity {ref['similarity']}" for ref in refs)
    instruction = "Write one sentence explaining why this candidate's evidence supports (or doesn't support) this score."
    if not refs and card.evidence_type == "verified":
        # Volume/Presence/Span can produce a real score from matching commits even when
        # none cleared the Depth similarity floor — the LLM must not read the empty
        # evidence list as "nothing was found" and contradict `verified` (see
        # template_fallback's twin of this same case).
        instruction += (
            " Commits matching this skill's pattern were found, but none were similar enough to the "
            "skill's description to count as strong evidence — say that, don't say no evidence was found."
        )
    return (
        f"Skill: {card.skill}\n"
        f"Confidence score: {card.confidence_score}\n"
        f"Evidence type: {card.evidence_type}\n"
        f"Qualifying evidence ({len(refs)} items):\n{evidence_lines or '(none)'}\n\n"
        f"{instruction}"
    )


def _pluralize(count: int, noun: str) -> str:
    return f"{count} {noun}{'s' if count != 1 else ''}"


def template_fallback(card: EvidenceCard) -> str:
    refs = card.source_commits or []
    if not refs:
        # confidence_score isn't necessarily 0 here: a declared_only card (Presence
        # only, never committed to) and a verified card where Volume/Presence/Span
        # carried the score but no single commit or PR comment cleared the Depth
        # qualifying floor both reach this branch with a nonzero score. Only the
        # first of those actually has zero matching commits, though — a verified
        # card gets its own wording so it doesn't falsely claim no evidence exists.
        if card.evidence_type == "verified":
            return (
                f"Commits matching {card.skill}'s pattern were found, but none were similar enough to "
                f"{card.skill}'s description to count as Depth evidence, producing a confidence score "
                f"of {card.confidence_score}."
            )
        return (
            f"No individual commit or PR comment qualified as evidence for {card.skill}, "
            f"producing a confidence score of {card.confidence_score}."
        )

    commit_count = sum(1 for r in refs if r["kind"] == "commit")
    review_count = sum(1 for r in refs if r["kind"] == "pr_comment")
    repo_count = len({r["repo"] for r in refs})
    parts = []
    if commit_count:
        parts.append(_pluralize(commit_count, "commit"))
    if review_count:
        parts.append(_pluralize(review_count, "PR review comment"))
    evidence_desc = " and ".join(parts) if parts else "some evidence"

    return (
        f"{evidence_desc.capitalize()} across {_pluralize(repo_count, 'repo')} "
        f"over {_pluralize(card.temporal_span_days, 'day')} produced "
        f"a confidence score of {card.confidence_score} for {card.skill}."
    )


def generate_explanation(card: EvidenceCard, groq_client: GroqClient) -> tuple[str, bool]:
    """Returns (explanation_text, is_fallback)."""
    try:
        return groq_client.generate_explanation(build_prompt(card)), False
    except GroqUnavailableError as exc:
        logger.warning(
            "generate_explanation failed for candidate=%s skill=%s; using template fallback: %s",
            card.candidate_id,
            card.skill,
            exc,
        )
        return template_fallback(card), True
