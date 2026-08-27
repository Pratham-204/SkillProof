"""Focused tests for the hybrid Presence/Volume/Depth/Span formula (ADR-0004):
pure computation over an EvidenceBundle, no external systems to fake for most
of it. The tests below this module's docstring run embeddings for real,
same as the HTTP-level suite, calibrated against the live model's actual
output. The tests at the bottom instead use the fake_embeddings fixture to pin
exact expected similarities — useful for Depth-specific edge cases (the
qualifying floor, the discount) where an exact number is easier to state and
more robust than calibrated prose that happens to land on the right side of a
threshold today.
"""

from datetime import datetime, timedelta, timezone

import numpy as np

from skillproof import scoring, taxonomy
from skillproof.ingestion import EvidenceBundle, EvidenceItem
from tests.fixtures.github_fixtures import QUALIFYING_COMMIT_MESSAGE, QUALIFYING_DIFF_TEXT, QUALIFYING_REVIEW_COMMENT

_NOW = datetime.now(timezone.utc)

# Calibrated against the real all-MiniLM-L6-v2 model: unrelated enough to any
# Skill Tag's canonical description to stay well under the 0.35 qualifying
# floor, so these commits contribute Volume/Presence but zero Depth/Span.
UNRELATED_COMMIT_MESSAGE = "Bump internal counter, no behavior change."


LOWER_SIMILARITY_COMMIT_MESSAGE = "Wrote a quick FastAPI helper for the health check route."


def test_depth_uses_top_three_while_span_uses_the_full_qualifying_set():
    # Five higher-similarity commits (clustered within an 80-day span) plus one
    # lower-similarity, later commit that still clears the qualifying floor.
    # Same kind throughout so the Depth discount (ticket 03) scales both sides
    # equally and doesn't interfere with this test's own concern: all six count
    # toward Span; only the three highest-similarity end up in source_commits,
    # since Depth is top_3 (not top_5).
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
        kind="commit",
        repo="octodev/skillproof-lib",
        ref="review-1",
        url="https://example.com/review-1",
        text=LOWER_SIMILARITY_COMMIT_MESSAGE,
        date=_NOW - timedelta(days=150),
        diff_text=QUALIFYING_DIFF_TEXT,
    )
    bundle = EvidenceBundle(items=[*top_five_items, sixth_lower_similarity_item], manifests={})

    result = scoring.score_skill(bundle, "FastAPI")

    assert result.evidence_type == "verified"
    assert len(result.source_commits) == 3
    assert {ref.ref for ref in result.source_commits} == {"c0", "c1", "c2"}
    # The other three qualifying items are excluded from source_commits but still widen the span.
    assert result.temporal_span_days == 150


def test_depth_discounts_commit_message_similarity_relative_to_pr_comment():
    """Ticket 03: identical topical content, produced identical raw similarity —
    the only difference is that one arrives as a commit message and the other
    as a PR comment, so only the discount can explain their different Depth
    contribution, with the commit message counting for less."""
    identical_text = QUALIFYING_REVIEW_COMMENT
    items = [
        EvidenceItem(
            kind="commit",
            repo="octodev/skillproof-lib",
            ref="c1",
            url="https://example.com/c1",
            text=identical_text,
            date=_NOW,
            diff_text=QUALIFYING_DIFF_TEXT,
        ),
        EvidenceItem(
            kind="pr_comment",
            repo="octodev/skillproof-lib",
            ref="p1",
            url="https://example.com/p1",
            text=identical_text,
            date=_NOW,
        ),
    ]
    bundle = EvidenceBundle(items=items, manifests={})

    result = scoring.score_skill(bundle, "FastAPI")

    by_kind = {ref.kind: ref.similarity for ref in result.source_commits}
    assert by_kind["commit"] < by_kind["pr_comment"]
    assert abs(by_kind["commit"] - round(by_kind["pr_comment"] * scoring.DEPTH_COMMIT_MESSAGE_DISCOUNT, 4)) < 1e-4


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


# --- Fake-backend tests ---
# Depth-specific edge cases below pin an exact expected similarity rather than
# relying on prose hand-calibrated against the real model's actual output.


def _skill_embedding_key(skill: str) -> str:
    return f"{skill}: {taxonomy.get_skill(skill).description}"


def _unit_vector_at_cosine(cos_theta: float) -> np.ndarray:
    """A 2D unit vector whose cosine similarity to [1, 0] is exactly cos_theta."""
    return np.array([cos_theta, (1 - cos_theta**2) ** 0.5])


def test_fake_backend_precisely_excludes_similarity_just_below_the_qualifying_floor(fake_embeddings):
    fake_embeddings.vectors_by_text[_skill_embedding_key("FastAPI")] = np.array([1.0, 0.0])
    fake_embeddings.vectors_by_text["just below the floor"] = _unit_vector_at_cosine(0.34)
    items = [
        EvidenceItem(
            kind="commit",
            repo="octodev/skillproof-lib",
            ref="c1",
            url="https://example.com/c1",
            text="just below the floor",
            date=_NOW,
            diff_text=QUALIFYING_DIFF_TEXT,  # matches the Detection Pattern regardless of embedding similarity
        )
    ]
    bundle = EvidenceBundle(items=items, manifests={})

    result = scoring.score_skill(bundle, "FastAPI")

    assert result.evidence_type == "verified"  # Volume-qualifying (diff matched), just not Depth-qualifying
    assert result.source_commits == []
    assert result.temporal_span_days == 0


def test_fake_backend_precisely_includes_similarity_just_above_the_qualifying_floor(fake_embeddings):
    fake_embeddings.vectors_by_text[_skill_embedding_key("FastAPI")] = np.array([1.0, 0.0])
    fake_embeddings.vectors_by_text["just above the floor"] = _unit_vector_at_cosine(0.36)
    items = [
        EvidenceItem(
            kind="commit",
            repo="octodev/skillproof-lib",
            ref="c1",
            url="https://example.com/c1",
            text="just above the floor",
            date=_NOW,
            diff_text=QUALIFYING_DIFF_TEXT,
        )
    ]
    bundle = EvidenceBundle(items=items, manifests={})

    result = scoring.score_skill(bundle, "FastAPI")

    assert len(result.source_commits) == 1
    assert result.source_commits[0].similarity == round(0.36 * scoring.DEPTH_COMMIT_MESSAGE_DISCOUNT, 4)


def test_score_skill_issues_one_batched_embeddings_call_per_skill(fake_embeddings, monkeypatch):
    """Ticket 01: score_skill used to call embed() once per matching Evidence
    Item; it must now collect all of a skill's matching items and issue a
    single embed_batch() call — a prerequisite for a future embeddings backend
    with real per-call (e.g. network) overhead."""
    fake_embeddings.vectors_by_text[_skill_embedding_key("FastAPI")] = np.array([1.0, 0.0])
    taxonomy.skill_embedding("FastAPI")  # warm the disk-cache-backed lru_cache before counting calls

    calls: list[list[str]] = []
    original_embed_batch = fake_embeddings.embed_batch

    def counting_embed_batch(texts: list[str]) -> np.ndarray:
        calls.append(list(texts))
        return original_embed_batch(texts)

    monkeypatch.setattr(fake_embeddings, "embed_batch", counting_embed_batch)

    items = [
        EvidenceItem(
            kind="commit",
            repo="octodev/skillproof-lib",
            ref=f"c{i}",
            url=f"https://example.com/c{i}",
            text=f"item text {i}",
            date=_NOW - timedelta(days=i),
            diff_text=QUALIFYING_DIFF_TEXT,
        )
        for i in range(3)
    ]
    bundle = EvidenceBundle(items=items, manifests={})

    scoring.score_skill(bundle, "FastAPI")

    assert len(calls) == 1
    assert calls[0] == ["item text 0", "item text 1", "item text 2"]


def test_score_skill_matches_each_batched_vector_back_to_its_own_item(fake_embeddings):
    """The real risk a batching refactor introduces is index misalignment —
    item i getting item j's vector back. Two items in the SAME embed_batch
    call with deliberately different similarities (one clearly qualifying,
    one clearly not) proves the zip lines them up correctly, not just that
    scores stay unchanged when every item behaves identically."""
    fake_embeddings.vectors_by_text[_skill_embedding_key("FastAPI")] = np.array([1.0, 0.0])
    fake_embeddings.vectors_by_text["clearly qualifying text"] = np.array([1.0, 0.0])  # similarity 1.0
    fake_embeddings.vectors_by_text["clearly non-qualifying text"] = _unit_vector_at_cosine(0.1)  # below the floor
    items = [
        EvidenceItem(
            kind="commit",
            repo="octodev/skillproof-lib",
            ref="c1",
            url="https://example.com/c1",
            text="clearly non-qualifying text",
            date=_NOW,
            diff_text=QUALIFYING_DIFF_TEXT,
        ),
        EvidenceItem(
            kind="commit",
            repo="octodev/skillproof-lib",
            ref="c2",
            url="https://example.com/c2",
            text="clearly qualifying text",
            date=_NOW,
            diff_text=QUALIFYING_DIFF_TEXT,
        ),
    ]
    bundle = EvidenceBundle(items=items, manifests={})

    result = scoring.score_skill(bundle, "FastAPI")

    assert {ref.ref for ref in result.source_commits} == {"c2"}


def test_fake_backend_pins_the_exact_discount_on_commit_message_depth(fake_embeddings):
    text = "uses fastapi for the api layer"
    fake_embeddings.vectors_by_text[_skill_embedding_key("FastAPI")] = np.array([1.0, 0.0])
    fake_embeddings.vectors_by_text[text] = np.array([1.0, 0.0])  # cosine similarity to the skill vector: exactly 1.0
    items = [
        EvidenceItem(
            kind="commit",
            repo="octodev/skillproof-lib",
            ref="c1",
            url="https://example.com/c1",
            text=text,
            date=_NOW,
            diff_text=QUALIFYING_DIFF_TEXT,
        ),
        EvidenceItem(
            kind="pr_comment",
            repo="octodev/skillproof-lib",
            ref="p1",
            url="https://example.com/p1",
            text=text,
            date=_NOW,
        ),
    ]
    bundle = EvidenceBundle(items=items, manifests={})

    result = scoring.score_skill(bundle, "FastAPI")

    by_kind = {ref.kind: ref.similarity for ref in result.source_commits}
    assert by_kind["pr_comment"] == 1.0
    assert by_kind["commit"] == scoring.DEPTH_COMMIT_MESSAGE_DISCOUNT == 0.6
