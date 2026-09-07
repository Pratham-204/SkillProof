import threading

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from skillproof import explain_service
from skillproof.db import get_db
from skillproof.deps import get_groq_client
from skillproof.groq_client import GroqClient
from skillproof.limiter import limiter
from skillproof.models import EvidenceCard
from skillproof.schemas import ExplainOut

router = APIRouter(tags=["explain"])

# Public and unauthenticated by design, same as GET /evidence-card/{candidate_id}
# (ADR-0016): the frontend calls this lazily from PublicEvidenceCard.tsx, which
# is deliberately session-blind so a Recruiter (no account, per ADR-0002) viewing
# a shared card link triggers the same explanation generation a Candidate would.
# Rate-limited rather than auth-gated for that reason, the same posture /search
# already takes on the same tradeoff.
EXPLAIN_RATE_LIMIT = "20/minute"

# One lock per (candidate_id, skill), so concurrent requests for the same
# not-yet-cached card serialize onto a single Groq call and a single commit
# instead of each independently reading the stale cache, calling Groq, and
# racing to commit (B4/D6). Only ever created for a pair that already has an
# EvidenceCard row — the lookup above 404s first — so this can't be grown
# unboundedly by probing nonexistent candidate_id/skill combinations.
_explain_locks: dict[tuple[str, str], threading.Lock] = {}
_explain_locks_guard = threading.Lock()


def _lock_for(candidate_id: str, skill: str) -> threading.Lock:
    key = (candidate_id, skill)
    with _explain_locks_guard:
        return _explain_locks.setdefault(key, threading.Lock())


@router.post("/explain/{candidate_id}/{skill}", response_model=ExplainOut)
@limiter.limit(EXPLAIN_RATE_LIMIT)
def explain(
    request: Request,
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

    with _lock_for(candidate_id, skill):
        db.refresh(card)  # pick up a winning concurrent request's commit, if one just landed
        if card.explanation and not card.explanation_is_fallback:
            return ExplainOut(skill=skill, explanation=card.explanation, explanation_is_fallback=False)

        explanation, is_fallback = explain_service.generate_explanation(card, groq_client)
        card.explanation = explanation
        card.explanation_is_fallback = is_fallback
        db.commit()

    return ExplainOut(skill=skill, explanation=explanation, explanation_is_fallback=is_fallback)
