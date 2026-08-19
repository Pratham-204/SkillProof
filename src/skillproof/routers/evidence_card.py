from fastapi import APIRouter, Depends, HTTPException
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

    cards = db.query(EvidenceCard).filter_by(candidate_id=candidate_id).order_by(EvidenceCard.skill).all()

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
                explanation=c.explanation,
                explanation_is_fallback=c.explanation_is_fallback,
            )
            for c in cards
        ],
    )
