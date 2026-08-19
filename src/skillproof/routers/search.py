from fastapi import APIRouter, Depends, Request
from sqlalchemy import desc
from sqlalchemy.orm import Session

from skillproof.config import get_settings
from skillproof.db import get_db
from skillproof.limiter import limiter
from skillproof.models import Candidate, EvidenceCard
from skillproof.schemas import SearchResponse, SearchResultOut

router = APIRouter(tags=["search"])


@router.get("/search", response_model=SearchResponse)
@limiter.limit(get_settings().search_rate_limit)
def search(request: Request, skill: str, min_score: float = 0.0, db: Session = Depends(get_db)) -> SearchResponse:
    """Unauthenticated, stateless, opt-in-only (issue 06). Rate limiting is
    enforced by the SlowAPI middleware wired in main.py.
    """
    settings = get_settings()
    rows = (
        db.query(Candidate, EvidenceCard)
        .join(EvidenceCard, EvidenceCard.candidate_id == Candidate.candidate_id)
        .filter(
            Candidate.searchable.is_(True),
            EvidenceCard.skill == skill,
            EvidenceCard.status == "complete",
            EvidenceCard.confidence_score >= min_score,
        )
        .order_by(desc(EvidenceCard.confidence_score))
        .limit(settings.search_result_limit)
        .all()
    )

    results = [
        SearchResultOut(
            candidate_id=candidate.candidate_id,
            github_login=candidate.github_login,
            github_profile_url=f"https://github.com/{candidate.github_login}",
            evidence_card_url=f"{str(request.base_url).rstrip('/')}/evidence-card/{candidate.candidate_id}",
            confidence_score=card.confidence_score,
        )
        for candidate, card in rows
    ]

    return SearchResponse(skill=skill, min_score=min_score, results=results)
