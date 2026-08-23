from functools import lru_cache

from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from skillproof.config import get_settings
from skillproof.db import SessionLocal, get_db
from skillproof.github_client import GitHubClient, RealGitHubClient
from skillproof.groq_client import GroqClient, RealGroqClient
from skillproof.models import Candidate, CandidateSession


@lru_cache
def get_github_client() -> GitHubClient:
    return RealGitHubClient()


@lru_cache
def get_groq_client() -> GroqClient:
    return RealGroqClient()


def get_session_factory():
    """Session factory handed to background tasks, which must open their own
    session after the request that scheduled them has already returned.
    Overridden in tests so background work lands in the same test database.
    """
    return SessionLocal


def get_current_candidate(request: Request, db: Session = Depends(get_db)) -> Candidate:
    """Resolves the session cookie set at OAuth callback (ADR-0006) to a Candidate.
    Raises 401 on a missing, unknown, or stale session rather than falling back to
    any client-supplied identity — that trust is exactly what ADR-0006 removes.
    """
    session_id = request.cookies.get(get_settings().session_cookie_name)
    if session_id is None:
        raise HTTPException(status_code=401, detail="Not authenticated")

    session = db.get(CandidateSession, session_id)
    if session is None:
        raise HTTPException(status_code=401, detail="Not authenticated")

    candidate = db.get(Candidate, session.candidate_id)
    if candidate is None:
        raise HTTPException(status_code=401, detail="Not authenticated")

    return candidate
