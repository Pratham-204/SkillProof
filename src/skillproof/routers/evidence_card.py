from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import case, func
from sqlalchemy.orm import Session

from skillproof.db import get_db
from skillproof.models import Candidate, EvidenceCard
from skillproof.schemas import CandidateEvidenceOut, CandidateOut, EvidenceCardOut, EvidenceRefOut

router = APIRouter(tags=["evidence-card"])


@router.get("/evidence-card/{candidate_id}", response_model=CandidateEvidenceOut)
def get_evidence_card(candidate_id: str, db: Session = Depends(get_db)) -> CandidateEvidenceOut:
    candidate = db.get(Candidate, candidate_id)
    if candidate is None:
        raise HTTPException(status_code=404, detail="Unknown candidate_id")

    # A re-verify under a bumped taxonomy_version forks a new card rather than
    # mutating the old one (ADR-0005), so a skill can have more than one row here;
    # this endpoint surfaces only the latest taxonomy_version per skill by default.
    latest_per_skill = (
        db.query(EvidenceCard.skill, func.max(EvidenceCard.taxonomy_version).label("taxonomy_version"))
        .filter_by(candidate_id=candidate_id)
        .group_by(EvidenceCard.skill)
        .subquery()
    )
    cards = (
        db.query(EvidenceCard)
        .join(
            latest_per_skill,
            (EvidenceCard.skill == latest_per_skill.c.skill)
            & (EvidenceCard.taxonomy_version == latest_per_skill.c.taxonomy_version),
        )
        .filter(EvidenceCard.candidate_id == candidate_id)
        # Strongest evidence first. A "failed" card carries no meaningful score —
        # _fail_card only flips status/error, never clearing a prior run's stale
        # confidence_score — so it's ranked last regardless of that stored value,
        # ahead of the score-descending order applied to every other card.
        .order_by(
            case((EvidenceCard.status == "failed", 1), else_=0),
            EvidenceCard.confidence_score.desc(),
            EvidenceCard.skill.asc(),
        )
        .all()
    )

    return CandidateEvidenceOut(
        **CandidateOut.model_validate(candidate).model_dump(),
        cards=[
            EvidenceCardOut(
                skill=c.skill,
                status=c.status,
                error=c.error,
                confidence_score=c.confidence_score,
                evidence_type=c.evidence_type,
                source_commits=[EvidenceRefOut(**ref) for ref in c.source_commits],
                temporal_span_days=c.temporal_span_days,
                taxonomy_version=c.taxonomy_version,
                explanation=c.explanation,
                explanation_is_fallback=c.explanation_is_fallback,
            )
            for c in cards
        ],
    )
