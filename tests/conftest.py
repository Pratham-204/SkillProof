import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import skillproof.models  # noqa: F401 - registers tables on Base.metadata
from skillproof.db import Base, get_db
from skillproof.deps import get_github_client, get_groq_client, get_session_factory
from skillproof.github_client import FakeGitHubClient
from skillproof.groq_client import FakeGroqClient
from skillproof.limiter import limiter
from skillproof.main import create_app


@pytest.fixture
def db_session_factory():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    yield sessionmaker(bind=engine, autoflush=False, autocommit=False)
    engine.dispose()


@pytest.fixture
def fake_github():
    return FakeGitHubClient()


@pytest.fixture
def fake_groq():
    return FakeGroqClient()


@pytest.fixture
def client(db_session_factory, fake_github, fake_groq):
    limiter.reset()
    app = create_app()

    def _get_db():
        db = db_session_factory()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = _get_db
    app.dependency_overrides[get_session_factory] = lambda: db_session_factory
    app.dependency_overrides[get_github_client] = lambda: fake_github
    app.dependency_overrides[get_groq_client] = lambda: fake_groq

    with TestClient(app) as test_client:
        yield test_client
