import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Response
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from starlette.middleware.base import BaseHTTPMiddleware

from skillproof import version
from skillproof.db import engine, init_db
from skillproof.limiter import limiter
from skillproof.routers import auth, evidence_card, explain, search, taxonomy, verify

# The built frontend (ticket 02): FastAPI serves it directly so the app is
# single-origin (ADR-0006) — no dist/ yet is a normal state for pure-backend
# dev/tests, so serving it is skipped entirely rather than erroring.
FRONTEND_DIST = Path(__file__).resolve().parent.parent.parent / "frontend" / "dist"

# The public marketing page — a static file (frontend/public/landing.html,
# copied verbatim into dist/ by Vite) rather than a React route, so it can
# ship without translating hand-authored CSS into Tailwind. It runs its own
# /auth/github/me check and redirects an already-authenticated Candidate to
# /dashboard client-side, so a returning Candidate still gets the fast-path
# round 10 established — landing.html is what a stranger sees at "/".
LANDING_PAGE = FRONTEND_DIST / "landing.html"


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Baseline anti-clickjacking/anti-sniffing headers on every response —
    nothing in the app set any of these before, leaving the SPA framable by
    any origin (see the OAuth-callback/searchable-toggle clickjacking risk)."""

    async def dispatch(self, request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        return response


def create_app() -> FastAPI:
    # uvicorn's own logging dictConfig only ever attaches handlers to its own
    # 'uvicorn'/'uvicorn.error'/'uvicorn.access' loggers, never to root — left
    # unconfigured, every skillproof.* logger call fell through to logging's
    # bare last-resort handler (WARNING+ only, no timestamp/level/name).
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    app = FastAPI(title="SkillProof", lifespan=lifespan)

    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)  # type: ignore[arg-type]
    app.add_middleware(SlowAPIMiddleware)
    app.add_middleware(SecurityHeadersMiddleware)

    app.include_router(auth.router)
    app.include_router(taxonomy.router)
    app.include_router(verify.router)
    app.include_router(evidence_card.router)
    app.include_router(explain.router)
    app.include_router(search.router)

    @app.get("/health", include_in_schema=False)
    def health(response: Response) -> dict[str, str]:
        """Reports which commit this container was actually built from, so a
        deploy can be verified instead of assumed (see `version.deployed_sha`).
        Registered before the SPA catch-all below, which would otherwise
        swallow this path and hand back index.html.

        Also runs a cheap SELECT 1 against the configured DB engine: this is
        the only liveness signal Railway's health probe ever sees, so an
        unconditional 200 would keep routing traffic to (and never restart)
        an instance whose database is actually unreachable."""
        try:
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
        except SQLAlchemyError:
            response.status_code = 503
            return {"status": "degraded", "git_sha": version.deployed_sha()}
        return {"status": "ok", "git_sha": version.deployed_sha()}

    if FRONTEND_DIST.is_dir():
        app.mount("/assets", StaticFiles(directory=FRONTEND_DIST / "assets"), name="frontend-assets")

        if LANDING_PAGE.is_file():

            @app.get("/", include_in_schema=False)
            def serve_landing() -> FileResponse:
                return FileResponse(LANDING_PAGE)

        @app.get("/{full_path:path}", include_in_schema=False)
        def serve_frontend(full_path: str) -> FileResponse:
            """SPA fallback: serves a matching static file from dist/ (e.g.
            favicon.svg) if one exists, otherwise index.html so client-side
            routing (react-router) handles the path. Registered last, so every
            API route above always wins for its own path first.

            Confirmed live, unauthenticated arbitrary-file-read otherwise:
            `full_path` is Starlette's raw `{full_path:path}` capture, and
            `FRONTEND_DIST / full_path` does not strip or normalize `..`
            segments — `GET /../../.env` served the repo's real .env file
            (in production: the GitHub OAuth secret, token-encryption key,
            and DATABASE_URL) with a plain 200, no auth required. Resolving
            the candidate path and checking it's actually still inside
            FRONTEND_DIST closes this the same way Starlette's own
            StaticFiles already guards its mounted paths.
            """
            candidate = (FRONTEND_DIST / full_path).resolve()
            if full_path and candidate.is_relative_to(FRONTEND_DIST) and candidate.is_file():
                return FileResponse(candidate)
            return FileResponse(FRONTEND_DIST / "index.html")

    return app


app = create_app()
