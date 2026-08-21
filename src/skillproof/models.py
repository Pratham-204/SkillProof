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


class EvidenceCard(Base):
    __tablename__ = "evidence_cards"
    __table_args__ = (UniqueConstraint("candidate_id", "skill", name="uq_candidate_skill"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    candidate_id: Mapped[str] = mapped_column(ForeignKey("candidates.candidate_id"), index=True)
    skill: Mapped[str] = mapped_column(String, index=True)

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
