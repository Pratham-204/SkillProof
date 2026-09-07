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


def test_source_commits_similarity_is_undiscounted_even_for_a_commit_message_match():
    """The Depth discount (ticket 03/ADR-0004) weights a commit-message match's
    contribution to the Depth *score* down relative to a PR comment's — but
    source_commits.similarity must always show the raw similarity that actually
    cleared the 0.35 qualifying floor, not that discounted ranking value, or a
    legitimately-qualifying commit-message match can display as if it were
    below the documented floor (skillproof-explanation-legibility issue 01).
    Identical text produces identical raw similarity for both kinds here; the
    discount's effect on the actual score is pinned exactly in
    test_fake_backend_pins_the_exact_discount_on_commit_message_depth below."""
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
    assert by_kind["commit"] == by_kind["pr_comment"]


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


def test_manifest_declares_rejects_aws_sdk_as_websockets_evidence():
    """"ws" is a raw substring of "aws-sdk" -- the real WebSockets Skill Tag's
    manifest_packages includes npm package "ws", and "aws-sdk" is an extremely
    common, wholly unrelated npm dependency. A naive substring check flips
    Presence for WebSockets purely from this collision."""
    bundle = EvidenceBundle(
        items=[],
        manifests={"octodev/skillproof-lib": {"package.json": '{"dependencies": {"aws-sdk": "^2.1.0"}}'}},
    )

    result = scoring.score_skill(bundle, "WebSockets")

    assert result.evidence_type == "none"
    assert result.confidence_score == 0.0


def test_manifest_declares_still_detects_the_real_ws_package():
    """Positive control for the fix above: a regression that makes the false
    positive disappear by also killing the true positive would be worse than
    the original bug."""
    bundle = EvidenceBundle(
        items=[],
        manifests={"octodev/skillproof-lib": {"package.json": '{"dependencies": {"ws": "^8.0.0"}}'}},
    )

    result = scoring.score_skill(bundle, "WebSockets")

    assert result.evidence_type == "declared_only"
    assert result.confidence_score == 0.20


def test_manifest_declares_rejects_react_native_as_react_evidence():
    """"react" (the React Skill Tag's manifest package) is a literal substring
    of "react-native" (React Native's own npm package)."""
    bundle = EvidenceBundle(
        items=[],
        manifests={"octodev/skillproof-lib": {"package.json": '{"dependencies": {"react-native": "^0.72.0"}}'}},
    )

    result = scoring.score_skill(bundle, "React")

    assert result.evidence_type == "none"
    assert result.confidence_score == 0.0


def test_manifest_declares_rejects_node_sass_as_sass_evidence():
    """"sass" (the Sass Skill Tag's manifest package) is a substring of the
    still-common legacy package "node-sass"."""
    bundle = EvidenceBundle(
        items=[],
        manifests={"octodev/skillproof-lib": {"package.json": '{"dependencies": {"node-sass": "^7.0.0"}}'}},
    )

    result = scoring.score_skill(bundle, "Sass")

    assert result.evidence_type == "none"
    assert result.confidence_score == 0.0


def test_manifest_declares_does_not_credit_dynamodb_from_a_bare_boto3_dependency():
    """DynamoDB's Detection Pattern previously listed the generic pip "boto3"
    package (the whole-of-AWS SDK, also legitimately AWS's own manifest
    package) with no ecosystem/context scoping — any Python project using
    boto3 for a completely unrelated AWS service (S3, SQS, ...) flipped
    DynamoDB's Presence. DynamoDB already has a specific, correct signal
    (content_markers=["dynamodb"]); the redundant boto3 entry was removed."""
    bundle = EvidenceBundle(
        items=[],
        manifests={"octodev/skillproof-lib": {"requirements.txt": "boto3==1.34.0\n"}},
    )

    result = scoring.score_skill(bundle, "DynamoDB")

    assert result.evidence_type == "none"
    assert result.confidence_score == 0.0


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
    assert result.source_commits[0].similarity == 0.36  # raw similarity, undiscounted


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

    # source_commits shows each item's raw (undiscounted) qualifying similarity...
    by_kind = {ref.kind: ref.similarity for ref in result.source_commits}
    assert by_kind["pr_comment"] == 1.0
    assert by_kind["commit"] == 1.0

    # ...but the discount still lowers the commit message's actual contribution
    # to Depth: depth = mean(1.0 * DEPTH_COMMIT_MESSAGE_DISCOUNT, 1.0) = 0.8, so
    # confidence = 0.20*presence(1) + 0.40*volume(1/6) + 0.25*depth(0.8) + 0.15*span(0)
    expected_depth = (1.0 * scoring.DEPTH_COMMIT_MESSAGE_DISCOUNT + 1.0) / 2
    assert expected_depth == 0.8
    expected_confidence = round(0.20 * 1 + 0.40 * (1 / 6) + 0.25 * expected_depth + 0.15 * 0, 4)
    assert result.confidence_score == expected_confidence


def test_a_qualifying_pr_comment_with_zero_commits_does_not_inflate_declared_only(fake_embeddings):
    """Per the Evidence Item term (CONTEXT.md): an item only counts toward
    Depth "if its commit already matched that Skill Tag's Detection Pattern
    (i.e. is Volume-qualifying) ... without a Volume-qualifying commit behind
    it, it isn't evidence at all." A PR comment has no commit of its own, so
    with zero Volume-qualifying commits for this skill, it must not
    contribute Depth/Span — declared_only promises "a small nonzero
    Confidence Score from Presence alone", i.e. exactly PRESENCE_WEIGHT."""
    # The comment text must itself match Django's Detection Pattern (manifest
    # package name "django", checked via _text_matches) for this PR comment
    # to even enter matching_items in the first place — "django" needs to
    # actually appear in the text, not just conceptually be "about" Django.
    comment_text = "This Django view could use select_related to cut the query count."
    fake_embeddings.vectors_by_text[_skill_embedding_key("Django")] = np.array([1.0, 0.0])
    fake_embeddings.vectors_by_text[comment_text] = np.array([1.0, 0.0])
    bundle = EvidenceBundle(
        items=[
            EvidenceItem(
                kind="pr_comment",
                repo="octodev/skillproof-lib",
                ref="p1",
                url="https://example.com/p1",
                text=comment_text,
                date=_NOW,
            )
        ],
        manifests={"octodev/skillproof-lib": {"requirements.txt": "Django==4.2\n"}},
    )

    result = scoring.score_skill(bundle, "Django")

    assert result.evidence_type == "declared_only"
    assert result.confidence_score == scoring.PRESENCE_WEIGHT
    assert result.source_commits == []


def test_a_qualifying_pr_comment_with_zero_commits_and_no_manifest_scores_zero(fake_embeddings):
    """Same gap, but for evidence_type == "none": a comment-only match with no
    manifest declaration and no commits must not produce any nonzero score."""
    comment_text = "This Django view could use select_related to cut the query count."
    fake_embeddings.vectors_by_text[_skill_embedding_key("Django")] = np.array([1.0, 0.0])
    fake_embeddings.vectors_by_text[comment_text] = np.array([1.0, 0.0])
    bundle = EvidenceBundle(
        items=[
            EvidenceItem(
                kind="pr_comment",
                repo="octodev/skillproof-lib",
                ref="p1",
                url="https://example.com/p1",
                text=comment_text,
                date=_NOW,
            )
        ],
        manifests={},
    )

    result = scoring.score_skill(bundle, "Django")

    assert result.evidence_type == "none"
    assert result.confidence_score == 0.0
    assert result.source_commits == []


def test_pr_comment_still_counts_toward_depth_when_a_qualifying_commit_exists(fake_embeddings):
    """Positive control: the fix must not disqualify a PR comment sitting
    alongside a real Volume-qualifying commit for the same skill — only the
    comment-with-zero-commits case should be excluded."""
    fake_embeddings.vectors_by_text[_skill_embedding_key("FastAPI")] = np.array([1.0, 0.0])
    fake_embeddings.vectors_by_text[QUALIFYING_REVIEW_COMMENT] = np.array([1.0, 0.0])
    fake_embeddings.vectors_by_text["unrelated commit message"] = _unit_vector_at_cosine(0.1)  # below floor
    bundle = EvidenceBundle(
        items=[
            EvidenceItem(
                kind="commit",
                repo="octodev/skillproof-lib",
                ref="c1",
                url="https://example.com/c1",
                text="unrelated commit message",
                date=_NOW,
                diff_text=QUALIFYING_DIFF_TEXT,
            ),
            EvidenceItem(
                kind="pr_comment",
                repo="octodev/skillproof-lib",
                ref="p1",
                url="https://example.com/p1",
                text=QUALIFYING_REVIEW_COMMENT,
                date=_NOW,
            ),
        ],
        manifests={},
    )

    result = scoring.score_skill(bundle, "FastAPI")

    assert result.evidence_type == "verified"
    assert {ref.ref for ref in result.source_commits} == {"p1"}


def test_source_commits_are_displayed_in_descending_similarity_order(fake_embeddings):
    """Selection into the top-N is by depth_similarity (the discounted
    ranking value — a self-authored commit message is discounted relative to
    an undiscounted PR comment), but the DISPLAYED similarity is always raw
    and undiscounted. Without sorting the display list by that same raw
    value, a public Evidence Card could show a lower number listed ahead of a
    higher one purely because the higher one came from a discounted commit
    message that ranked lower for selection."""
    fake_embeddings.vectors_by_text[_skill_embedding_key("FastAPI")] = np.array([1.0, 0.0])
    # PR comment: raw similarity 0.50, no discount -> depth_similarity 0.50.
    fake_embeddings.vectors_by_text[QUALIFYING_REVIEW_COMMENT] = _unit_vector_at_cosine(0.50)
    # Commit message: raw similarity 0.70, discounted (*0.6) -> depth_similarity 0.42,
    # so the PR comment outranks it for SELECTION despite the commit's raw
    # similarity being higher.
    commit_text = "Fix bug in the FastAPI verify handler after review feedback."
    fake_embeddings.vectors_by_text[commit_text] = _unit_vector_at_cosine(0.70)
    bundle = EvidenceBundle(
        items=[
            EvidenceItem(
                kind="pr_comment",
                repo="octodev/skillproof-lib",
                ref="p1",
                url="https://example.com/p1",
                text=QUALIFYING_REVIEW_COMMENT,
                date=_NOW,
            ),
            EvidenceItem(
                kind="commit",
                repo="octodev/skillproof-lib",
                ref="c1",
                url="https://example.com/c1",
                text=commit_text,
                date=_NOW,
                diff_text=QUALIFYING_DIFF_TEXT,
            ),
        ],
        manifests={},
    )

    result = scoring.score_skill(bundle, "FastAPI")

    similarities = [ref.similarity for ref in result.source_commits]
    assert similarities == sorted(similarities, reverse=True)
    assert result.source_commits[0].ref == "c1"  # 0.70, listed first despite ranking below p1 for selection


def test_blank_commit_message_is_never_embedded_or_treated_as_qualifying(fake_embeddings):
    """A commit with a blank/whitespace-only message (kept only for its diff,
    e.g. a bot commit or `git commit --allow-empty-message`) must not reach
    the embedding call at all — skipped defensively rather than relying on an
    empty string happening to land under the qualifying floor for whatever
    embedding model/target-vector pair is in use."""
    fake_embeddings.vectors_by_text[_skill_embedding_key("FastAPI")] = np.array([1.0, 0.0])
    embedded_texts: list[str] = []
    original_embed_batch = fake_embeddings.embed_batch

    def recording_embed_batch(texts: list[str]) -> np.ndarray:
        embedded_texts.extend(texts)
        return original_embed_batch(texts)

    fake_embeddings.embed_batch = recording_embed_batch  # type: ignore[method-assign]

    bundle = EvidenceBundle(
        items=[
            EvidenceItem(
                kind="commit",
                repo="octodev/skillproof-lib",
                ref="c1",
                url="https://example.com/c1",
                text="   ",
                date=_NOW,
                diff_text=QUALIFYING_DIFF_TEXT,
            )
        ],
        manifests={},
    )

    result = scoring.score_skill(bundle, "FastAPI")

    assert "   " not in embedded_texts
    assert result.evidence_type == "verified"  # Volume-qualifying via diff_text
    assert result.source_commits == []  # never reached Depth
