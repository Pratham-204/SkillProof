import logging
import secrets

from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from skillproof import security
from skillproof.config import get_settings
from skillproof.db import get_db
from skillproof.deps import get_current_candidate, get_github_client, get_session_by_cookie
from skillproof.github_client import GitHubAuthError, GitHubClient
from skillproof.limiter import limiter
from skillproof.models import Candidate, CandidateSession
from skillproof.schemas import CandidateOut, SearchableUpdate

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth/github", tags=["auth"])

# Short-lived: only needs to survive one round trip through GitHub's own
# consent screen, never a returning session.
OAUTH_STATE_COOKIE_NAME = "skillproof_oauth_state"
OAUTH_STATE_MAX_AGE_SECONDS = 600


@router.get("/login")
def login() -> RedirectResponse:
    """Generates a fresh, unguessable `state` value per login attempt and
    carries it two ways: appended to GitHub's authorize URL, and in a
    short-lived cookie on this browser. callback() below requires both to
    match before it trusts a `code` — without this, nothing bound the
    callback's code-exchange to the browser/session that actually initiated
    the login (classic OAuth login-CSRF): an attacker who captures their own
    still-valid `code` could lure a victim into GET /auth/github/callback?
    code=<attacker's code>, and the victim's browser would silently end up
    holding a session cookie authenticated as the ATTACKER's GitHub identity
    — SameSite=Lax does not block this, since it's a plain top-level GET
    navigation, exactly the case Lax carves out as allowed.
    """
    settings = get_settings()
    state = security.generate_oauth_state()
    url = (
        "https://github.com/login/oauth/authorize"
        f"?client_id={settings.github_client_id}"
        f"&redirect_uri={settings.github_oauth_redirect_uri}"
        f"&scope={settings.github_oauth_scope}"
        f"&state={state}"
    )
    response = RedirectResponse(url)
    response.set_cookie(
        key=OAUTH_STATE_COOKIE_NAME,
        value=state,
        httponly=True,
        secure=settings.session_cookie_secure,
        samesite="lax",
        path="/",
        max_age=OAUTH_STATE_MAX_AGE_SECONDS,
    )
    return response


@router.get("/callback")
def callback(
    code: str,
    state: str,
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

    # `state` must both be present (FastAPI 422s a request missing the query
    # param entirely — fails closed for the simplest attack, a bare crafted
    # link with no state at all) and match what login() set on THIS browser.
    # secrets.compare_digest avoids a timing side-channel on the comparison
    # itself; a mismatch (or no cookie at all — e.g. it expired, or this
    # callback was never preceded by our own /login) is treated exactly like
    # the already-consumed-code case below: bounce back into the app rather
    # than exchange a code nothing has vouched for.
    cookie_state = request.cookies.get(OAUTH_STATE_COOKIE_NAME)
    if not cookie_state or not secrets.compare_digest(cookie_state, state):
        logger.warning(
            "OAuth callback rejected: state mismatch (cookie_present=%s)", cookie_state is not None
        )
        response = RedirectResponse(settings.github_oauth_success_redirect)
        response.delete_cookie(OAUTH_STATE_COOKIE_NAME, path="/")
        return response

    try:
        token = github_client.exchange_code_for_token(code)
        user = github_client.get_authenticated_user(token)
    except GitHubAuthError:
        # GitHub's OAuth `code` is single-use and short-lived — a double-submitted
        # callback (browser back/reload, link prefetch, or a stale/reused link)
        # hits this route again with an already-consumed code and would
        # otherwise surface as a raw 500. Send the Candidate back into the app
        # instead, where "Connect GitHub Account" is safe to click again with a
        # fresh code.
        logger.warning("OAuth callback rejected: code exchange with GitHub failed")
        response = RedirectResponse(settings.github_oauth_success_redirect)
        response.delete_cookie(OAUTH_STATE_COOKIE_NAME, path="/")
        return response

    candidate = db.query(Candidate).filter_by(github_user_id=user.id).one_or_none()
    is_new_candidate = candidate is None
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

    logger.info(
        "OAuth callback succeeded: candidate_id=%s github_login=%s new_candidate=%s "
        "previous_session_replaced=%s redirect=%s",
        candidate.candidate_id,
        candidate.github_login,
        is_new_candidate,
        previous_session is not None,
        settings.github_oauth_success_redirect,
    )

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
    response.delete_cookie(OAUTH_STATE_COOKIE_NAME, path="/")  # single-use, spent on this exchange
    return response


@router.get("/me", response_model=CandidateOut)
def me(candidate: Candidate = Depends(get_current_candidate)) -> CandidateOut:
    return CandidateOut.model_validate(candidate)


@router.patch("/me/searchable", response_model=CandidateOut)
@limiter.limit("20/minute")
def update_searchable(
    request: Request,
    payload: SearchableUpdate,
    candidate: Candidate = Depends(get_current_candidate),
    db: Session = Depends(get_db),
) -> CandidateOut:
    """Lets a Candidate flip `searchable` on its own, without a full `/verify`
    call — identity comes from the session (ADR-0006), same as `/verify`.

    A session-authenticated write is cheap per call, but nothing else stops a
    replayed/leaked session cookie from hitting it in a tight unbounded loop
    (unlike GET /search, this previously had no limiter at all); a literal
    limit (rather than a config.py setting like search_rate_limit) is fine
    here since this route has no product reason to ever be tuned per-deploy.
    """
    candidate.searchable = payload.searchable
    db.commit()
    return CandidateOut.model_validate(candidate)
