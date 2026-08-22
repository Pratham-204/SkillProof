from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from skillproof import explain_service
from skillproof.db import get_db
from skillproof.deps import get_groq_client
from skillproof.groq_client import GroqClient
from skillproof.models import EvidenceCard
from skillproof.schemas import ExplainOut

router = APIRouter(tags=["explain"])


@router.post("/explain/{candidate_id}/{skill}", response_model=ExplainOut)
def explain(
    candidate_id: str,
    skill: str,
    db: Session = Depends(get_db),
    groq_client: GroqClient = Depends(get_groq_client),
) -> ExplainOut:
    # A skill can have more than one card across taxonomy_versions (ADR-0005);
    # explanations are only generated for the latest one.
    card = (
        db.query(EvidenceCard)
        .filter_by(candidate_id=candidate_id, skill=skill)
        .order_by(EvidenceCard.taxonomy_version.desc())
        .first()
    )
    if card is None:
        raise HTTPException(status_code=404, detail="No Evidence Card exists for this candidate + skill")
    if card.status != "complete":
        raise HTTPException(status_code=409, detail=f"Evidence Card is not ready yet (status={card.status})")

    # Only a real (non-fallback) cached explanation short-circuits the LLM call —
    # a cached fallback is retried transparently on the next call (issue 05).
    if card.explanation and not card.explanation_is_fallback:
        return ExplainOut(skill=skill, explanation=card.explanation, explanation_is_fallback=False)

    explanation, is_fallback = explain_service.generate_explanation(card, groq_client)
    card.explanation = explanation
    card.explanation_is_fallback = is_fallback
    db.commit()

    return ExplainOut(skill=skill, explanation=explanation, explanation_is_fallback=is_fallback)
