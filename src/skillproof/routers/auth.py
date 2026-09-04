from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from skillproof import security
from skillproof.config import get_settings
from skillproof.db import get_db
from skillproof.deps import get_current_candidate, get_github_client, get_session_by_cookie
from skillproof.github_client import GitHubClient
from skillproof.models import Candidate, CandidateSession
from skillproof.schemas import CandidateOut, SearchableUpdate

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


@router.get("/callback")
def callback(
    code: str,
    request: Request,
    db: Session = Depends(get_db),
    github_client: GitHubClient = Depends(get_github_client),
) -> RedirectResponse:
    """First login creates a Candidate keyed by GitHub user ID; a later login
    from the same account reuses the existing candidate_id (issue 01). A
    session cookie already present on the request — a reconnect, or a login as
    a *different* GitHub identity (skillproof-connect-github-account) — has its
    old CandidateSession row deleted here rather than left orphaned forever,
    since no session ever otherwise expires server-side.

    Issues an HttpOnly session cookie and redirects into the app, rather than
    returning the Candidate as JSON (a browser mid-OAuth-redirect has nowhere
    to receive that) or handing back candidate_id for the client to self-report
    on future writes — the latter is exactly the trust ADR-0006 removes, since
    candidate_id is intentionally public.
    """
    settings = get_settings()
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

    db.flush()  # populates candidate.candidate_id for a brand-new Candidate before the session row references it

    previous_session = get_session_by_cookie(request, db)
    if previous_session is not None:
        db.delete(previous_session)

    session = CandidateSession(session_id=security.generate_session_token(), candidate_id=candidate.candidate_id)
    db.add(session)
    db.commit()

    response = RedirectResponse(settings.github_oauth_success_redirect)
    response.set_cookie(
        key=settings.session_cookie_name,
        value=session.session_id,
        httponly=True,
        secure=settings.session_cookie_secure,
        samesite="lax",
        path="/",
        max_age=settings.session_max_age_days * 24 * 60 * 60,
    )
    return response


@router.get("/me", response_model=CandidateOut)
def me(candidate: Candidate = Depends(get_current_candidate)) -> CandidateOut:
    return CandidateOut.model_validate(candidate)


@router.patch("/me/searchable", response_model=CandidateOut)
def update_searchable(
    payload: SearchableUpdate,
    candidate: Candidate = Depends(get_current_candidate),
    db: Session = Depends(get_db),
) -> CandidateOut:
    """Lets a Candidate flip `searchable` on its own, without a full `/verify`
    call — identity comes from the session (ADR-0006), same as `/verify`."""
    candidate.searchable = payload.searchable
    db.commit()
    return CandidateOut.model_validate(candidate)
