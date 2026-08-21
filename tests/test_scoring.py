"""Focused tests for the hybrid Presence/Volume/Depth/Span formula (ADR-0004):
pure computation over an EvidenceBundle, no external systems, so nothing here
needs faking. Embeddings run for real, same as the HTTP-level suite.
"""

from datetime import datetime, timedelta, timezone

from skillproof import scoring
from skillproof.ingestion import EvidenceBundle, EvidenceItem
from tests.fixtures.github_fixtures import QUALIFYING_COMMIT_MESSAGE, QUALIFYING_DIFF_TEXT, QUALIFYING_REVIEW_COMMENT

_NOW = datetime.now(timezone.utc)

# Calibrated against the real all-MiniLM-L6-v2 model: unrelated enough to any
# Skill Tag's canonical description to stay well under the 0.35 qualifying
# floor, so these commits contribute Volume/Presence but zero Depth/Span.
UNRELATED_COMMIT_MESSAGE = "Bump internal counter, no behavior change."


def test_depth_uses_top_three_while_span_uses_the_full_qualifying_set():
    # Five higher-similarity commits (clustered within an 80-day span) plus one
    # lower-similarity, later review comment that still clears the qualifying
    # floor. All six count toward Span; only the three highest-similarity
    # should end up in source_commits, since Depth is top_3 (not top_5).
    top_five_items = [
        EvidenceItem(
            kind="commit",
            repo="octodev/skillproof-lib",
            ref=f"c{i}",
            url=f"https://example.com/c{i}",
            text=QUALIFYING_COMMIT_MESSAGE,
            date=_NOW - timedelta(days=80 - i * 20),
            diff_text=QUALIFYING_DIFF_TEXT,
        )
        for i in range(5)
    ]
    sixth_lower_similarity_item = EvidenceItem(
        kind="pr_comment",
        repo="octodev/skillproof-lib",
        ref="review-1",
        url="https://example.com/review-1",
        text=QUALIFYING_REVIEW_COMMENT,
        date=_NOW - timedelta(days=150),
    )
    bundle = EvidenceBundle(items=[*top_five_items, sixth_lower_similarity_item], manifests={})

    result = scoring.score_skill(bundle, "FastAPI")

    assert result.evidence_type == "verified"
    assert len(result.source_commits) == 3
    assert {ref.ref for ref in result.source_commits} == {"c0", "c1", "c2"}
    # The other three qualifying items are excluded from source_commits but still widen the span.
    assert result.temporal_span_days == 150


def test_volume_and_presence_from_matching_commits_with_no_depth_or_span_below_floor():
    # Three Dockerfile-touching commits with an unrelated message: Volume and
    # Presence come from the file match alone, Depth/Span stay at zero because
    # the text never clears the qualifying floor.
    items = [
        EvidenceItem(
            kind="commit",
            repo="octodev/skillproof-lib",
            ref=f"d{i}",
            url=f"https://example.com/d{i}",
            text=UNRELATED_COMMIT_MESSAGE,
            date=_NOW - timedelta(days=i),
            files=("Dockerfile",),
        )
        for i in range(3)
    ]
    bundle = EvidenceBundle(items=items, manifests={})

    result = scoring.score_skill(bundle, "Docker")

    assert result.evidence_type == "verified"
    assert result.source_commits == []
    assert result.temporal_span_days == 0
    # confidence = 0.20*presence(1) + 0.40*volume(3/8) + 0.25*depth(0) + 0.15*span(0)
    assert result.confidence_score == round(0.20 * 1 + 0.40 * (3 / 8), 4)


def test_declared_only_when_manifest_lists_a_dependency_never_touched_by_a_commit():
    bundle = EvidenceBundle(
        items=[],
        manifests={"octodev/skillproof-lib": {"requirements.txt": "Django==4.2\ngunicorn==21.2\n"}},
    )

    result = scoring.score_skill(bundle, "Django")

    assert result.evidence_type == "declared_only"
    assert result.source_commits == []
    # confidence = 0.20*presence(1) + everything else 0
    assert result.confidence_score == 0.20


def test_commit_message_mentioning_a_skill_does_not_count_toward_volume_on_its_own():
    """A commit message is freely candidate-authored prose, not evidence of code
    touched — only the diff content (or changed files) can make a commit match a
    Detection Pattern. Otherwise a candidate could inflate Volume just by naming
    the skill in unrelated commit messages."""
    items = [
        EvidenceItem(
            kind="commit",
            repo="octodev/skillproof-lib",
            ref="c1",
            url="https://example.com/c1",
            text="Mentions fastapi here but touches nothing fastapi-related.",
            date=_NOW,
            files=("README.md",),
            diff_text="+# bump changelog date",
        )
    ]
    bundle = EvidenceBundle(items=items, manifests={})

    result = scoring.score_skill(bundle, "FastAPI")

    assert result.evidence_type == "none"
    assert result.confidence_score == 0.0


def test_none_when_neither_declared_nor_touched():
    bundle = EvidenceBundle(items=[], manifests={})

    result = scoring.score_skill(bundle, "Django")

    assert result.evidence_type == "none"
    assert result.confidence_score == 0.0
    assert result.source_commits == []
