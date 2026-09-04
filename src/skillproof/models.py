import uuid
from datetime import datetime, timezone

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from skillproof.db import Base


def _uuid() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Candidate(Base):
    __tablename__ = "candidates"

    candidate_id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    github_user_id: Mapped[int] = mapped_column(Integer, unique=True, index=True)
    github_login: Mapped[str] = mapped_column(String)
    github_token_encrypted: Mapped[str] = mapped_column(Text)
    needs_reconnect: Mapped[bool] = mapped_column(Boolean, default=False)
    searchable: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    evidence_cards: Mapped[list["EvidenceCard"]] = relationship(
        back_populates="candidate", cascade="all, delete-orphan"
    )


class CandidateSession(Base):
    """An opaque session id → candidate_id mapping, set as an HttpOnly cookie at
    OAuth callback (ADR-0006). candidate_id is intentionally public (it's in
    Evidence Card URLs), so it can't itself be trusted as an auth credential;
    this is what /verify and the searchable toggle authenticate against instead."""

    __tablename__ = "candidate_sessions"

    session_id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    candidate_id: Mapped[str] = mapped_column(ForeignKey("candidates.candidate_id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class EvidenceCard(Base):
    __tablename__ = "evidence_cards"
    __table_args__ = (
        UniqueConstraint("candidate_id", "skill", "taxonomy_version", name="uq_candidate_skill_taxonomy_version"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    candidate_id: Mapped[str] = mapped_column(ForeignKey("candidates.candidate_id"), index=True)
    skill: Mapped[str] = mapped_column(String, index=True)
    # The taxonomy_version this card was scored under (ADR-0005). A re-verify under the
    # same version overwrites this row in place; a re-verify under a newer version forks
    # a new row instead of mutating this one.
    taxonomy_version: Mapped[int] = mapped_column(Integer)

    # "processing" | "complete" | "failed"
    status: Mapped[str] = mapped_column(String, default="processing")
    error: Mapped[str | None] = mapped_column(String, nullable=True)

    confidence_score: Mapped[float] = mapped_column(Float, default=0.0)
    # "none" | "declared_only" | "verified"
    evidence_type: Mapped[str] = mapped_column(String, default="none")
    source_commits: Mapped[list] = mapped_column(JSON, default=list)
    temporal_span_days: Mapped[int] = mapped_column(Integer, default=0)

    explanation: Mapped[str | None] = mapped_column(Text, nullable=True)
    explanation_is_fallback: Mapped[bool] = mapped_column(Boolean, default=False)

    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)

    candidate: Mapped[Candidate] = relationship(back_populates="evidence_cards")


class Sighting(Base):
    """A manifest-declared package matching no existing Skill Tag's Detection Pattern
    (round 8, ADR-0008) — raw material for the self-extending taxonomy's batch publish
    job (`taxonomy_growth.py`). Not evidence, never scored. A given (ecosystem,
    package_name, candidate_id, repo) is recorded at most once, so a candidate
    re-verifying repeatedly never inflates the distinct-candidate count the batch
    job aggregates over."""

    __tablename__ = "sightings"
    __table_args__ = (
        UniqueConstraint("ecosystem", "package_name", "candidate_id", "repo", name="uq_sighting_candidate_repo"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ecosystem: Mapped[str] = mapped_column(String, index=True)
    package_name: Mapped[str] = mapped_column(String, index=True)
    candidate_id: Mapped[str] = mapped_column(ForeignKey("candidates.candidate_id"), index=True)
    repo: Mapped[str] = mapped_column(String)
    seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class RepoProvenanceFlag(Base):
    """A permanent record that one repo's earliest commit was found to already
    exist in another public repo not owned by this repo's owner (round 11,
    ADR-0012) — evidence its history was imported rather than genuinely
    authored. Every EvidenceItem from a flagged repo is excluded from Volume,
    Depth, and Span for whichever Candidate owns it; Presence is unaffected.
    Keyed by repo alone (not per-candidate): whether a repo's history was
    imported is a fact about that repo, independent of who's verifying.
    A clean result (no match found) is deliberately never recorded here — the
    absence of a match today doesn't guarantee one tomorrow, so a clean repo
    is re-checked on every `/verify`, never cached as clear."""

    __tablename__ = "repo_provenance_flags"

    repo: Mapped[str] = mapped_column(String, primary_key=True)
    matched_sha: Mapped[str] = mapped_column(String)
    flagged_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class SightingDecision(Base):
    """A terminal outcome (published / rejected_duplicate / abstained) for one
    (ecosystem, package_name) pair `taxonomy_growth.publish_new_skill_tags` has
    already evaluated, so a package that keeps getting sighted isn't re-evaluated
    (and re-billed against the LLM) on every batch run (round 8, ADR-0008). A
    registry-existence miss is deliberately never recorded here — that check is
    cheap and worth retrying, since the package might genuinely get published
    later."""

    __tablename__ = "sighting_decisions"
    __table_args__ = (UniqueConstraint("ecosystem", "package_name", name="uq_sighting_decision"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ecosystem: Mapped[str] = mapped_column(String)
    package_name: Mapped[str] = mapped_column(String)
    decision: Mapped[str] = mapped_column(String)  # "published" | "rejected_duplicate" | "abstained"
    decided_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
