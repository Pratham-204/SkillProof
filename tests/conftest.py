import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import skillproof.models  # noqa: F401 - registers tables on Base.metadata
from skillproof import embeddings, taxonomy
from skillproof.db import Base, get_db
from skillproof.deps import get_github_client, get_groq_client, get_session_factory
from skillproof.embeddings import FakeEmbeddingsBackend, SentenceTransformerBackend
from skillproof.github_client import FakeGitHubClient
from skillproof.groq_client import FakeGroqClient
from skillproof.limiter import limiter
from skillproof.main import create_app


@pytest.fixture
def db_session_factory():
    # A bare `sqlite:///:memory:` + StaticPool (the previous setup) shares ONE
    # raw sqlite3 connection across every Session, including ones created on
    # different threads by concurrent request handling (e.g.
    # test_explain_concurrent_requests_for_...). check_same_thread=False only
    # lifts sqlite3's same-thread restriction — it does not make two Sessions'
    # BEGIN/COMMIT sequences interleaving on that one physical connection
    # safe, and empirically it isn't: genuinely concurrent threads hit
    # "sqlite3.InterfaceError: bad parameter or other API misuse", spurious
    # StaleDataErrors, and rows a just-committed write should have made
    # visible reading back as missing, at a high, reproducible rate (11-19
    # failures per 20 trials in a standalone repro). SQLite's own
    # `cache=shared` URI mode instead gives each thread a genuinely separate
    # connection that all still see the same in-memory data, coordinated by
    # SQLite's own internal locking rather than by sharing one raw connection
    # object — 0 failures in 70 repro trials. The db name must be unique per
    # fixture instance so parallel/sequential tests don't leak into each
    # other's shared-cache database.
    db_name = f"file:memdb_{uuid.uuid4().hex}?mode=memory&cache=shared"
    engine = create_engine(f"sqlite:///{db_name}", connect_args={"check_same_thread": False, "uri": True})
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
def isolated_taxonomy_file(tmp_path, monkeypatch):
    """Test seam for taxonomy_growth: it writes real file mutations (new entries,
    a version bump) to `taxonomy.SKILLS_PATH` — isolate them to a throwaway copy so
    a test run never mutates the checked-in `skills.json`. Clears taxonomy's caches
    before and after so no test leaks a stale in-memory taxonomy into another."""
    temp_path = tmp_path / "skills.json"
    temp_path.write_text(taxonomy.SKILLS_PATH.read_text(encoding="utf-8"), encoding="utf-8")
    monkeypatch.setattr(taxonomy, "SKILLS_PATH", temp_path)
    taxonomy._invalidate_caches()
    yield temp_path
    taxonomy._invalidate_caches()


@pytest.fixture
def fake_embeddings():
    """Installs a FakeEmbeddingsBackend and clears taxonomy's embeddings cache so
    skill-tag vectors are recomputed through it instead of served from the real,
    disk-cached ones. Restores the real backend on teardown so later tests
    aren't left running against fakes."""
    fake = FakeEmbeddingsBackend()
    embeddings.set_backend(fake)
    taxonomy._embeddings_cache.cache_clear()
    yield fake
    embeddings.set_backend(SentenceTransformerBackend())
    taxonomy._embeddings_cache.cache_clear()


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
