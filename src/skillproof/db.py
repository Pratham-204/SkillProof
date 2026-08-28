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
    connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}
    return create_engine(url, connect_args=connect_args)


engine = make_engine()
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def init_db(bind_engine=None) -> None:
    from skillproof import models  # noqa: F401  (ensure models are registered)

    Base.metadata.create_all(bind=bind_engine or engine)


def get_db() -> Iterator[Session]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
