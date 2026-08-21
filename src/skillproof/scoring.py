from __future__ import annotations

from dataclasses import dataclass

from skillproof import embeddings, heuristics, taxonomy
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

    matching_items = [item for item in bundle.items if _matches_pattern(item, pattern)]
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

    qualifying: list[tuple[EvidenceItem, float]] = []
    for item in matching_items:
        similarity = embeddings.cosine_similarity(embeddings.embed(item.text), target_vector)
        if similarity >= settings.evidence_qualifying_floor:
            qualifying.append((item, similarity))

    depth = 0.0
    span = 0.0
    span_days = 0
    top_n: list[tuple[EvidenceItem, float]] = []
    if qualifying:
        qualifying.sort(key=lambda pair: pair[1], reverse=True)
        top_n = qualifying[:DEPTH_TOP_N]
        depth = sum(sim for _, sim in top_n) / len(top_n)

        dates = [item.date for item, _ in qualifying]
        span_days = (max(dates) - min(dates)).days
        span = span_days / (span_days + SPAN_SATURATION_DAYS)

    confidence_score = PRESENCE_WEIGHT * presence + VOLUME_WEIGHT * volume + DEPTH_WEIGHT * depth + SPAN_WEIGHT * span
    confidence_score = max(0.0, min(1.0, confidence_score))

    # source_commits mirrors top_n, not the full qualifying set: it's meant to
    # show exactly what drove the score, not the wider set that only feeds Span.
    source_commits = [
        QualifyingEvidence(kind=item.kind, repo=item.repo, ref=item.ref, url=item.url, similarity=round(sim, 4))
        for item, sim in top_n
    ]

    return ConfidenceResult(
        confidence_score=round(confidence_score, 4),
        evidence_type=evidence_type,
        source_commits=source_commits,
        temporal_span_days=span_days,
    )


def _matches_pattern(item: EvidenceItem, pattern: DetectionPattern) -> bool:
    """A commit matches via its changed files or its own diff content — never its
    message, which is freely candidate-authored prose, not evidence of code touched.
    A PR comment (no diff of its own) can only match via its body text."""
    if item.kind == "commit":
        if any(_file_matches(f, pattern) for f in item.files):
            return True
        return _text_matches(item.diff_text, pattern)
    return _text_matches(item.text, pattern)


def _file_matches(path: str, pattern: DetectionPattern) -> bool:
    if any(path.lower().endswith(ext.lower()) for ext in pattern.file_extensions):
        return True
    return heuristics.matches_any_filename(path, pattern.config_files)


def _text_matches(text: str, pattern: DetectionPattern) -> bool:
    lower = text.lower()
    if any(marker.lower() in lower for marker in pattern.content_markers):
        return True
    return any(pkg.name.lower() in lower for pkg in pattern.manifest_packages)


def _manifest_declares(manifests: dict[str, dict[str, str]], pattern: DetectionPattern) -> bool:
    if not pattern.manifest_packages:
        return False
    for files in manifests.values():
        for content in files.values():
            if any(pkg.name.lower() in content.lower() for pkg in pattern.manifest_packages):
                return True
    return False
