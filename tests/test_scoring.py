"""Focused tests for the scoring formula itself: pure computation over
EvidenceItem objects, no external systems, so nothing here needs faking.
Embeddings run for real, same as the HTTP-level suite.
"""

from datetime import datetime, timedelta, timezone

from skillproof import scoring
from skillproof.ingestion import EvidenceItem
from tests.fixtures.github_fixtures import QUALIFYING_COMMIT_MESSAGE, QUALIFYING_REVIEW_COMMENT

_NOW = datetime.now(timezone.utc)


def test_source_commits_reflects_only_the_top_n_while_temporal_span_uses_the_full_qualifying_set():
    # Five higher-similarity commits (clustered within an 80-day span) plus one
    # lower-similarity, later review comment that still clears the qualifying
    # floor. All six count toward the temporal span; only the five highest
    # should end up in source_commits, since that's what the score is built from.
    top_five_items = [
        EvidenceItem(
            kind="commit",
            repo="octodev/skillproof-lib",
            ref=f"c{i}",
            url=f"https://example.com/c{i}",
            text=QUALIFYING_COMMIT_MESSAGE,
            date=_NOW - timedelta(days=80 - i * 20),
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

    result = scoring.score_skill([*top_five_items, sixth_lower_similarity_item], "FastAPI")

    assert result.evidence_type == "verified"
    assert len(result.source_commits) == 5
    assert {ref.ref for ref in result.source_commits} == {"c0", "c1", "c2", "c3", "c4"}
    # The 6th item is excluded from source_commits but still widens the span.
    assert result.temporal_span_days == 150
