from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from skillproof import version
from skillproof.db import init_db
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


def create_app() -> FastAPI:
    app = FastAPI(title="SkillProof", lifespan=lifespan)

    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)  # type: ignore[arg-type]
    app.add_middleware(SlowAPIMiddleware)

    app.include_router(auth.router)
    app.include_router(taxonomy.router)
    app.include_router(verify.router)
    app.include_router(evidence_card.router)
    app.include_router(explain.router)
    app.include_router(search.router)

    @app.get("/health", include_in_schema=False)
    def health() -> dict[str, str]:
        """Reports which commit this container was actually built from, so a
        deploy can be verified instead of assumed (see `version.deployed_sha`).
        Registered before the SPA catch-all below, which would otherwise
        swallow this path and hand back index.html."""
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
