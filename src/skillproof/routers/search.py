from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import func
from sqlalchemy.orm import Session

from skillproof.config import get_settings
from skillproof.db import get_db
from skillproof.limiter import limiter
from skillproof.models import Candidate, EvidenceCard
from skillproof.schemas import SearchMatchOut, SearchResponse, SearchResultOut

router = APIRouter(tags=["search"])

MAX_SEARCH_SKILLS = 8


def _qualifying_cards_for_skill(db: Session, skill: str) -> dict[str, EvidenceCard]:
    """Searchable, complete Evidence Cards for one skill, keyed by candidate_id.

    A candidate can have more than one card for this skill across
    taxonomy_versions (ADR-0005/ticket 04); without this dedup, a re-verify
    under a bumped taxonomy_version would surface the same candidate twice.
    """
    latest_per_candidate = (
        db.query(EvidenceCard.candidate_id, func.max(EvidenceCard.taxonomy_version).label("taxonomy_version"))
        .filter(EvidenceCard.skill == skill)
        .group_by(EvidenceCard.candidate_id)
        .subquery()
    )

    rows = (
        db.query(EvidenceCard)
        .join(Candidate, EvidenceCard.candidate_id == Candidate.candidate_id)
        .join(
            latest_per_candidate,
            (EvidenceCard.candidate_id == latest_per_candidate.c.candidate_id)
            & (EvidenceCard.taxonomy_version == latest_per_candidate.c.taxonomy_version),
        )
        .filter(
            Candidate.searchable.is_(True),
            EvidenceCard.skill == skill,
            EvidenceCard.status == "complete",
        )
        .all()
    )
    return {card.candidate_id: card for card in rows}


@router.get("/search", response_model=SearchResponse)
@limiter.limit(get_settings().search_rate_limit)
def search(request: Request, skill: list[str] = Query(...), db: Session = Depends(get_db)) -> SearchResponse:
    """Unauthenticated, stateless, opt-in-only (issue 06). Rate limiting is
    enforced by the SlowAPI middleware wired in main.py.

    Multiple `skill` values are matched with AND semantics (ADR-0007): a
    candidate appears only if they have a qualifying card for every selected
    skill. `declared_only` still counts as qualifying. Results are ranked by
    the average Confidence Score across exactly the selected skills.
    """
    settings = get_settings()

    skills = list(dict.fromkeys(skill))  # dedupe, preserve query order
    if len(skills) > MAX_SEARCH_SKILLS:
        raise HTTPException(status_code=400, detail=f"At most {MAX_SEARCH_SKILLS} skills per search")

    per_skill = {s: _qualifying_cards_for_skill(db, s) for s in skills}
    candidate_ids = set.intersection(*(set(cards) for cards in per_skill.values()))

    candidates = {
        c.candidate_id: c for c in db.query(Candidate).filter(Candidate.candidate_id.in_(candidate_ids))
    }

    results = []
    for candidate_id in candidate_ids:
        candidate = candidates[candidate_id]
        matches = []
        for s in skills:
            card = per_skill[s][candidate_id]
            matches.append(SearchMatchOut(skill=s, confidence_score=card.confidence_score, evidence_type=card.evidence_type))
        average_score = sum(m.confidence_score for m in matches) / len(matches)
        results.append(
            SearchResultOut(
                candidate_id=candidate.candidate_id,
                github_login=candidate.github_login,
                github_profile_url=f"https://github.com/{candidate.github_login}",
                evidence_card_url=f"{str(request.base_url).rstrip('/')}/evidence-card/{candidate.candidate_id}",
                average_score=average_score,
                matches=matches,
            )
        )

    results.sort(key=lambda r: r.average_score, reverse=True)
    results = results[: settings.search_result_limit]

    return SearchResponse(skills=skills, results=results)
