from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from skillproof.config import get_settings


class Base(DeclarativeBase):
    pass


def _normalize_database_url(url: str) -> str:
    """Railway (and most Postgres hosts) inject DATABASE_URL as a driver-less
    postgres:// or postgresql:// URL, but SQLAlchemy needs an explicit driver
    named in the scheme — "postgres://" isn't even a recognized alias anymore,
    and driver-less "postgresql://" only resolves if psycopg2 happens to be
    installed, which it isn't (this app installs psycopg, v3, instead). A URL
    that already names a driver (e.g. "postgresql+psycopg://") passes through
    unchanged, as does every SQLite URL.
    """
    if url.startswith("postgres://"):
        return "postgresql+psycopg://" + url.removeprefix("postgres://")
    if url.startswith("postgresql://"):
        return "postgresql+psycopg://" + url.removeprefix("postgresql://")
    return url


def make_engine(database_url: str | None = None):
    url = _normalize_database_url(database_url or get_settings().database_url)
    if url.startswith("sqlite"):
        return create_engine(url, connect_args={"check_same_thread": False})

    # Postgres (production, per ADR-0010) only: pool_pre_ping discards a
    # connection Postgres or an intermediary (e.g. Railway's proxy) silently
    # closed while idle, instead of handing it out dead and 500ing whatever
    # request drew it; pool_recycle=1800s (30min) recycles connections before
    # they're likely to hit such a timeout in the first place. pool_size=10 +
    # max_overflow=20 (30 total) is sized for this workload specifically: a
    # /verify background job holds one session checked out for its whole
    # GitHub-scan-plus-scoring run (ADR-0015 budgets ~1 minute), so the pool
    # needs headroom for several of those running concurrently on top of
    # ordinary short-lived request sessions, not just SQLAlchemy's default
    # 5+10=15.
    return create_engine(
        url,
        pool_pre_ping=True,
        pool_recycle=1800,
        pool_size=10,
        max_overflow=20,
    )


engine = make_engine()
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def init_db(bind_engine=None) -> None:
    from skillproof import models  # noqa: F401  (ensure models are registered)

    # create_all() only creates tables that don't exist yet — it never ALTERs
    # an already-existing table, so it can't apply a future schema change to
    # production. Alembic is now scaffolded (alembic.ini, migrations/) for
    # that, but is deliberately NOT invoked from here yet: production's live
    # Postgres schema was itself created by this same create_all() call, so
    # it needs a one-time, human-run `alembic stamp head` (marking it already
    # at the baseline revision, without touching data) before any real
    # migration is authored or `alembic upgrade` is ever wired in here.
    Base.metadata.create_all(bind=bind_engine or engine)


def get_db() -> Iterator[Session]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
