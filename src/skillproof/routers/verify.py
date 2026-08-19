from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy.orm import Session

from skillproof import taxonomy, verify_service
from skillproof.db import get_db
from skillproof.deps import get_github_client, get_session_factory
from skillproof.github_client import GitHubClient
from skillproof.models import Candidate
from skillproof.schemas import VerifyAccepted, VerifyRequest

router = APIRouter(tags=["verify"])


@router.post("/verify", response_model=VerifyAccepted, status_code=202)
def verify(
    payload: VerifyRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    github_client: GitHubClient = Depends(get_github_client),
    session_factory=Depends(get_session_factory),
) -> VerifyAccepted:
    """Returns immediately; scoring runs as an in-process background task (issue 04)."""
    candidate = db.get(Candidate, payload.candidate_id)
    if candidate is None:
        raise HTTPException(status_code=404, detail="Unknown candidate_id")

    for skill in payload.skills:
        if not taxonomy.is_known_skill(skill):
            raise HTTPException(status_code=400, detail=f"'{skill}' is not a recognized Skill Tag")

    if payload.searchable is not None:
        candidate.searchable = payload.searchable
        db.commit()

    verify_service.start_verification(db, candidate, payload.skills)

    background_tasks.add_task(
        verify_service.run_verification, session_factory, payload.candidate_id, payload.skills, github_client
    )

    return VerifyAccepted(candidate_id=payload.candidate_id, skills=payload.skills)
