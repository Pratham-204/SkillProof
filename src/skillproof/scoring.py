from __future__ import annotations

from dataclasses import dataclass

from skillproof import embeddings, taxonomy
from skillproof.config import get_settings
from skillproof.ingestion import EvidenceItem


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
    evidence_type: str  # "none" | "verified"
    source_commits: list[QualifyingEvidence]
    temporal_span_days: int


def score_skill(evidence_items: list[EvidenceItem], skill: str) -> ConfidenceResult:
    """Confidence Score = mean similarity of the top-N qualifying items, scaled
    by a temporal multiplier over the *full* qualifying set. Never touches an LLM
    (ADR-0001) — pure local embeddings + arithmetic.
    """
    settings = get_settings()
    target_vector = taxonomy.skill_embedding(skill)

    qualifying: list[tuple[EvidenceItem, float]] = []
    for item in evidence_items:
        similarity = embeddings.cosine_similarity(embeddings.embed(item.text), target_vector)
        if similarity >= settings.evidence_qualifying_floor:
            qualifying.append((item, similarity))

    if not qualifying:
        return ConfidenceResult(confidence_score=0.0, evidence_type="none", source_commits=[], temporal_span_days=0)

    qualifying.sort(key=lambda pair: pair[1], reverse=True)
    top_n = qualifying[: settings.top_n_evidence]
    top_n_mean = sum(sim for _, sim in top_n) / len(top_n)

    dates = [item.date for item, _ in qualifying]
    span_days = (max(dates) - min(dates)).days
    temporal_multiplier = _temporal_multiplier(span_days, settings)

    confidence_score = max(0.0, min(1.0, top_n_mean * temporal_multiplier))

    # source_commits mirrors top_n, not the full qualifying set: it's meant to
    # show exactly what drove the score (spec: "the same qualifying Evidence
    # Items used in scoring"), not the wider set that only feeds the temporal
    # span. A viewer should never see more evidence than the number reflects.
    source_commits = [
        QualifyingEvidence(kind=item.kind, repo=item.repo, ref=item.ref, url=item.url, similarity=round(sim, 4))
        for item, sim in top_n
    ]

    return ConfidenceResult(
        confidence_score=round(confidence_score, 4),
        evidence_type="verified",
        source_commits=source_commits,
        temporal_span_days=span_days,
    )


def _temporal_multiplier(span_days: int, settings) -> float:
    if span_days >= settings.temporal_full_credit_days:
        return 1.0
    fraction = span_days / settings.temporal_full_credit_days
    return settings.temporal_min_multiplier + (1.0 - settings.temporal_min_multiplier) * fraction
