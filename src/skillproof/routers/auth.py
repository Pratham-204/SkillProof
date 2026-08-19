from fastapi import APIRouter, Depends
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from skillproof import security
from skillproof.config import get_settings
from skillproof.db import get_db
from skillproof.deps import get_github_client
from skillproof.github_client import GitHubClient
from skillproof.models import Candidate
from skillproof.schemas import CandidateOut

router = APIRouter(prefix="/auth/github", tags=["auth"])


@router.get("/login")
def login() -> RedirectResponse:
    settings = get_settings()
    url = (
        "https://github.com/login/oauth/authorize"
        f"?client_id={settings.github_client_id}"
        f"&redirect_uri={settings.github_oauth_redirect_uri}"
        f"&scope={settings.github_oauth_scope}"
    )
    return RedirectResponse(url)


@router.get("/callback", response_model=CandidateOut)
def callback(
    code: str,
    db: Session = Depends(get_db),
    github_client: GitHubClient = Depends(get_github_client),
) -> CandidateOut:
    """First login creates a Candidate keyed by GitHub user ID; a later login
    from the same account reuses the existing candidate_id (issue 01).
    """
    token = github_client.exchange_code_for_token(code)
    user = github_client.get_authenticated_user(token)

    candidate = db.query(Candidate).filter_by(github_user_id=user.id).one_or_none()
    if candidate is None:
        candidate = Candidate(
            github_user_id=user.id,
            github_login=user.login,
            github_token_encrypted=security.encrypt_token(token),
        )
        db.add(candidate)
    else:
        candidate.github_login = user.login
        candidate.github_token_encrypted = security.encrypt_token(token)
        candidate.needs_reconnect = False

    db.commit()
    db.refresh(candidate)

    return CandidateOut.model_validate(candidate)
