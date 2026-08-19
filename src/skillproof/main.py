from contextlib import asynccontextmanager

from fastapi import FastAPI
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from skillproof.db import init_db
from skillproof.limiter import limiter
from skillproof.routers import auth, evidence_card, explain, search, taxonomy, verify


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

    return app


app = create_app()
