from __future__ import annotations

from dataclasses import dataclass

from skillproof import embeddings, taxonomy
from skillproof.config import get_settings
from skillproof.ingestion import EvidenceBundle, EvidenceItem
from skillproof.taxonomy import DetectionPattern

# Confidence Score = weighted sum of four Signals (ADR-0004). Named constants,
# not inlined, so recalibration against outcome data later is a one-line change.
PRESENCE_WEIGHT = 0.20
VOLUME_WEIGHT = 0.40
DEPTH_WEIGHT = 0.25
SPAN_WEIGHT = 0.15

VOLUME_SATURATION_CONSTANT = 5  # volume = n_commits / (n_commits + this)
SPAN_SATURATION_DAYS = 90  # span = span_days / (span_days + this)
DEPTH_TOP_N = 3

# Applied to EvidenceItem.is_self_authored items (see its docstring for why) so
# Depth isn't inflatable just by writing an elaborate commit message
# (hybrid-scoring ticket 03, ADR-0004).
DEPTH_COMMIT_MESSAGE_DISCOUNT = 0.6


@dataclass(frozen=True)
class QualifyingEvidence:
    kind: str
    repo: str
    ref: str
    url: str
    similarity: float


@dataclass(frozen=True)
class ConfidenceResult:
    confidence_score: float
    evidence_type: str  # "none" | "declared_only" | "verified"
    source_commits: list[QualifyingEvidence]
    temporal_span_days: int


def score_skill(bundle: EvidenceBundle, skill: str) -> ConfidenceResult:
    """Confidence Score = 0.20*presence + 0.40*volume + 0.25*depth + 0.15*span (ADR-0004).

    Presence and Volume are plain deterministic Detection Pattern lookups — no
    embedding model involved. Depth is the one Signal that embeds, comparing
    Volume-qualifying items' text against the Skill Tag's canonical description.
    Never touches an LLM (ADR-0001).
    """
    settings = get_settings()
    pattern = taxonomy.get_skill(skill).detection_pattern
    target_vector = taxonomy.skill_embedding(skill)

    matching_items = [item for item in bundle.items if item.matches(pattern)]
    n_commits = sum(1 for item in matching_items if item.kind == "commit")
    volume = n_commits / (n_commits + VOLUME_SATURATION_CONSTANT)

    manifest_declared = _manifest_declares(bundle.manifests, pattern)
    presence = 1.0 if (manifest_declared or n_commits > 0) else 0.0

    if presence == 0.0:
        evidence_type = "none"
    elif n_commits == 0:
        evidence_type = "declared_only"
    else:
        evidence_type = "verified"

    # Qualification (the 0.35 floor) always uses the raw similarity — an item
    # either is or isn't real evidence, independent of how much it counts
    # toward Depth's average. The discount only affects that second part.
    #
    # One batched embed_batch() call for all of this skill's matching items,
    # not one embed() call per item (ticket 01) — a prerequisite for any future
    # embeddings backend with real per-call (e.g. network) overhead. A failure
    # here propagates out of score_skill uncaught; the caller is responsible
    # for isolating it to this one skill's Evidence Card.
    # Each qualifying item carries both its raw similarity (what cleared the
    # floor above, and what source_commits shows) and its depth_similarity
    # (raw, discounted for a self-authored item) used only for ranking/
    # averaging below — conflating the two in source_commits let a
    # legitimately-qualifying commit-message match display as if its
    # similarity were below the documented 0.35 floor (skillproof-
    # explanation-legibility issue 01).
    qualifying: list[tuple[EvidenceItem, float, float]] = []
    if matching_items:
        item_vectors = embeddings.embed_batch([item.text for item in matching_items])
        for item, item_vector in zip(matching_items, item_vectors, strict=True):
            raw_similarity = embeddings.cosine_similarity(item_vector, target_vector)
            if raw_similarity < settings.evidence_qualifying_floor:
                continue
            depth_similarity = (
                raw_similarity * DEPTH_COMMIT_MESSAGE_DISCOUNT if item.is_self_authored else raw_similarity
            )
            qualifying.append((item, raw_similarity, depth_similarity))

    depth = 0.0
    span = 0.0
    span_days = 0
    top_n: list[tuple[EvidenceItem, float, float]] = []
    if qualifying:
        qualifying.sort(key=lambda triple: triple[2], reverse=True)
        top_n = qualifying[:DEPTH_TOP_N]
        depth = sum(depth_sim for _, _, depth_sim in top_n) / len(top_n)

        dates = [item.date for item, _, _ in qualifying]
        span_days = (max(dates) - min(dates)).days
        span = span_days / (span_days + SPAN_SATURATION_DAYS)

    confidence_score = PRESENCE_WEIGHT * presence + VOLUME_WEIGHT * volume + DEPTH_WEIGHT * depth + SPAN_WEIGHT * span
    confidence_score = max(0.0, min(1.0, confidence_score))

    # source_commits mirrors top_n, not the full qualifying set: it's meant to
    # show exactly what drove the score, not the wider set that only feeds Span.
    source_commits = [
        QualifyingEvidence(kind=item.kind, repo=item.repo, ref=item.ref, url=item.url, similarity=round(raw_sim, 4))
        for item, raw_sim, _ in top_n
    ]

    return ConfidenceResult(
        confidence_score=round(confidence_score, 4),
        evidence_type=evidence_type,
        source_commits=source_commits,
        temporal_span_days=span_days,
    )


def _manifest_declares(manifests: dict[str, dict[str, str]], pattern: DetectionPattern) -> bool:
    if not pattern.manifest_packages:
        return False
    for files in manifests.values():
        for content in files.values():
            if any(pkg.name.lower() in content.lower() for pkg in pattern.manifest_packages):
                return True
    return False
