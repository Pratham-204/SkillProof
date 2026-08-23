from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from skillproof.db import init_db
from skillproof.limiter import limiter
from skillproof.routers import auth, evidence_card, explain, search, taxonomy, verify

# The built frontend (ticket 02): FastAPI serves it directly so the app is
# single-origin (ADR-0006) — no dist/ yet is a normal state for pure-backend
# dev/tests, so serving it is skipped entirely rather than erroring.
FRONTEND_DIST = Path(__file__).resolve().parent.parent.parent / "frontend" / "dist"


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

    if FRONTEND_DIST.is_dir():
        app.mount("/assets", StaticFiles(directory=FRONTEND_DIST / "assets"), name="frontend-assets")

        @app.get("/{full_path:path}", include_in_schema=False)
        def serve_frontend(full_path: str) -> FileResponse:
            """SPA fallback: serves a matching static file from dist/ (e.g.
            favicon.svg) if one exists, otherwise index.html so client-side
            routing (react-router) handles the path. Registered last, so every
            API route above always wins for its own path first."""
            candidate = FRONTEND_DIST / full_path
            if full_path and candidate.is_file():
                return FileResponse(candidate)
            return FileResponse(FRONTEND_DIST / "index.html")

    return app


app = create_app()
