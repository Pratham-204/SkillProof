from fastapi import APIRouter, Depends, Request
from sqlalchemy import desc, func
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

    # A candidate can have more than one card for this skill across taxonomy_versions
    # (ADR-0005/ticket 04); without this, a re-verify under a bumped taxonomy_version
    # would surface the same candidate twice here under two different scores.
    latest_per_candidate = (
        db.query(EvidenceCard.candidate_id, func.max(EvidenceCard.taxonomy_version).label("taxonomy_version"))
        .filter(EvidenceCard.skill == skill)
        .group_by(EvidenceCard.candidate_id)
        .subquery()
    )

    rows = (
        db.query(Candidate, EvidenceCard)
        .join(EvidenceCard, EvidenceCard.candidate_id == Candidate.candidate_id)
        .join(
            latest_per_candidate,
            (EvidenceCard.candidate_id == latest_per_candidate.c.candidate_id)
            & (EvidenceCard.taxonomy_version == latest_per_candidate.c.taxonomy_version),
        )
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
            evidence_type=card.evidence_type,
        )
        for candidate, card in rows
    ]

    return SearchResponse(skill=skill, min_score=min_score, results=results)
